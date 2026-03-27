import copy
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": MAIN_NS, "r": OFFICE_REL_NS, "pr": PACKAGE_REL_NS}

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", OFFICE_REL_NS)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BLENDS_PATH = DATA_DIR / "Blends.xlsx"
FORMR_PATH = DATA_DIR / "blendScenes_prolific.xlsx"


def col_to_idx(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref).group(1)
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def idx_to_col(idx: int) -> str:
    idx += 1
    out = []
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def load_workbook_parts(xlsx_path: Path):
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", NS):
                shared_strings.append("".join(t.text or "" for t in si.iterfind(".//a:t", NS)))

        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall("pr:Relationship", NS)
        }
        sheet = workbook_root.find("a:sheets/a:sheet", NS)
        rel_id = sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]
        sheet_target = "xl/" + rel_map[rel_id]
        sheet_root = ET.fromstring(zf.read(sheet_target))

        return shared_strings, sheet_target, sheet_root, zf.namelist()


def read_rows(sheet_root, shared_strings):
    rows = []
    for row in sheet_root.find("a:sheetData", NS).findall("a:row", NS):
        values = []
        for cell in row.findall("a:c", NS):
            idx = col_to_idx(cell.attrib["r"])
            while len(values) <= idx:
                values.append(None)

            value = None
            cell_type = cell.attrib.get("t")
            cell_value = cell.find("a:v", NS)
            if cell_type == "s" and cell_value is not None:
                value = shared_strings[int(cell_value.text)]
            elif cell_type == "inlineStr":
                text_node = cell.find("a:is/a:t", NS)
                value = text_node.text if text_node is not None else ""
            elif cell_value is not None:
                value = cell_value.text

            values[idx] = value
        rows.append(values)
    return rows


def parse_trial_number(name: str):
    if not name:
        return None
    match = re.fullmatch(r"note_(\d+)", name)
    return int(match.group(1)) if match else None


def resolved_cell_text(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    cell_value = cell.find("a:v", NS)
    if cell_type == "s" and cell_value is not None:
        return shared_strings[int(cell_value.text)]
    if cell_type == "inlineStr":
        text_node = cell.find("a:is/a:t", NS)
        return text_node.text if text_node is not None else ""
    if cell_value is not None:
        return cell_value.text
    return None


def build_version_sheet_with_strings(sheet_root, shared_strings, selected_trials):
    new_root = copy.deepcopy(sheet_root)
    sheet_data = new_root.find("a:sheetData", NS)
    original_rows = list(sheet_data.findall("a:row", NS))

    keep_rows = []
    current_group = []
    current_block_order = None

    def flush_group():
        nonlocal keep_rows, current_group, current_block_order
        if not current_group:
            return

        if current_block_order is None:
            keep_rows.extend(row for _values, row in current_group)
        else:
            trial_number = None
            for values, _row in current_group:
                trial_number = parse_trial_number(values.get("C"))
                if trial_number is not None:
                    break
            if trial_number in selected_trials:
                keep_rows.extend(row for _values, row in current_group)

        current_group = []
        current_block_order = None

    for row in original_rows:
        values = {}
        for cell in row.findall("a:c", NS):
            col = re.match(r"[A-Z]+", cell.attrib["r"]).group(0)
            values[col] = resolved_cell_text(cell, shared_strings)

        block_order = values.get("J")
        if current_group and block_order != current_block_order:
            flush_group()

        current_group.append((values, row))
        current_block_order = block_order

    flush_group()

    if keep_rows:
        header_name = None
        first_row_values = {
            re.match(r"[A-Z]+", cell.attrib["r"]).group(0): resolved_cell_text(cell, shared_strings)
            for cell in keep_rows[0].findall("a:c", NS)
        }
        header_name = first_row_values.get("C")
        if header_name != "name":
            keep_rows.insert(0, copy.deepcopy(original_rows[0]))

    for row in list(sheet_data):
        sheet_data.remove(row)

    max_col = 0
    for new_idx, row in enumerate(keep_rows, start=1):
        row.attrib["r"] = str(new_idx)
        for cell in row.findall("a:c", NS):
            col = re.match(r"[A-Z]+", cell.attrib["r"]).group(0)
            cell.attrib["r"] = f"{col}{new_idx}"
            max_col = max(max_col, col_to_idx(cell.attrib["r"]) + 1)
        sheet_data.append(row)

    dimension = new_root.find("a:dimension", NS)
    if dimension is not None:
        last_col = idx_to_col(max(0, max_col - 1))
        dimension.attrib["ref"] = f"A1:{last_col}{len(keep_rows)}"

    return new_root


def write_version(source_xlsx: Path, output_xlsx: Path, sheet_target: str, sheet_root):
    xml_bytes = ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(source_xlsx) as src, zipfile.ZipFile(output_xlsx, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = xml_bytes if item.filename == sheet_target else src.read(item.filename)
            dst.writestr(item, data)


def read_blend_rows():
    shared_strings, _, sheet_root, _ = load_workbook_parts(BLENDS_PATH)
    rows = read_rows(sheet_root, shared_strings)
    records = []
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        trial = int(float(row[0]))
        c1 = row[1].strip()
        c2 = row[2].strip()
        records.append((trial, c1, c2))
    return records


def write_summary(summary_path: Path, version_trials):
    blend_rows = read_blend_rows()
    lines = []
    for version, selected_trials in version_trials.items():
        cat_counts = Counter()
        pair_counts = Counter()
        for trial, c1, c2 in blend_rows:
            if trial not in selected_trials:
                continue
            cat_counts[c1] += 1
            cat_counts[c2] += 1
            pair_counts["-".join(sorted((c1, c2)))] += 1

        lines.append(f"Version {version}")
        lines.append(f"Trials ({len(selected_trials)}): {', '.join(str(x) for x in sorted(selected_trials))}")
        lines.append(
            "Category counts: "
            + ", ".join(f"{key}={cat_counts[key]}" for key in sorted(cat_counts))
        )
        lines.append(
            "Category-pair counts: "
            + ", ".join(f"{key}={pair_counts[key]}" for key in sorted(pair_counts))
        )
        lines.append("")

    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    shared_strings, sheet_target, sheet_root, _ = load_workbook_parts(FORMR_PATH)

    version_trials = {
        version: {trial for trial in range(1, 201) if (trial - version) % 4 == 0}
        for version in range(1, 5)
    }

    for version, selected_trials in version_trials.items():
        new_sheet = build_version_sheet_with_strings(sheet_root, shared_strings, selected_trials)
        output_path = DATA_DIR / f"blendScenes_prolific_v{version}.xlsx"
        write_version(FORMR_PATH, output_path, sheet_target, new_sheet)

    write_summary(DATA_DIR / "blendScenes_split_summary.txt", version_trials)


if __name__ == "__main__":
    main()
