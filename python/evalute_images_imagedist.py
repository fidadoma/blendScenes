from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms

from places365_alexnet import Places365AlexNet


DEFAULT_WORKBOOK = Path(
    "data/formr_downloads/blendScenes_prolific_A/results_version_A_long_with_images_and_paths.xlsx"
)
DEFAULT_OUTPUT_DIR = Path("data/deep_features/version_A_alexnet")
DEFAULT_PLACES_WEIGHTS = Path("python/models/places365/alexnet_places365.pth.tar")

LAYER_MAP = {
    "imagenet": {
        "conv1": "features.0",
        "conv2": "features.3",
        "conv3": "features.6",
        "conv4": "features.8",
        "conv5": "features.10",
        "fc6": "classifier.1",
        "fc7": "classifier.4",
    },
    "places365": {
        "conv1": "conv1",
        "conv2": "conv2",
        "conv3": "conv3",
        "conv4": "conv4",
        "conv5": "conv5",
        "fc6": "fc6",
        "fc7": "fc7",
    },
}
DEFAULT_LAYERS = list(LAYER_MAP["imagenet"].keys())
PATH_COLUMNS = ("blend_path", "left_path", "right_path")
NAME_COLUMNS = {
    "blend_path": "blend_image",
    "left_path": "left_image",
    "right_path": "right_image",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract AlexNet deep features in PyTorch for all images referenced in the "
            "version A workbook."
        )
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default="long_results")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--layers",
        nargs="+",
        default=DEFAULT_LAYERS,
        choices=DEFAULT_LAYERS,
        help="AlexNet layers to export.",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="Inference device.",
    )
    parser.add_argument(
        "--weights",
        choices=("auto", "places365", "imagenet"),
        default="auto",
        help="Which pretrained AlexNet weights to use.",
    )
    parser.add_argument(
        "--places-weights-path",
        type=Path,
        default=DEFAULT_PLACES_WEIGHTS,
        help="Path to alexnet_places365.pth.tar if available locally.",
    )
    return parser.parse_args()


def resolve_device(device_arg: str) -> torch.device:
    if device_arg == "cpu":
        return torch.device("cpu")
    if device_arg == "cuda":
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def read_manifest(workbook: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(workbook, sheet_name=sheet_name)
    records: Dict[str, dict] = {}

    for path_col in PATH_COLUMNS:
        name_col = NAME_COLUMNS[path_col]
        role = path_col.replace("_path", "")
        subset = df[[path_col, name_col]].dropna().copy()
        if subset.empty:
            continue

        for row in subset.itertuples(index=False):
            image_path = Path(getattr(row, path_col))
            image_name = getattr(row, name_col)
            key = str(image_path.resolve())
            if key not in records:
                records[key] = {
                    "image_path": key,
                    "image_name": image_name,
                    "roles": {role},
                    "n_references": 1,
                }
            else:
                records[key]["roles"].add(role)
                records[key]["n_references"] += 1

    manifest = pd.DataFrame(records.values())
    manifest["roles"] = manifest["roles"].map(lambda x: ";".join(sorted(x)))
    manifest = manifest.sort_values(["image_name", "image_path"]).reset_index(drop=True)
    return manifest


def load_alexnet(weights_mode: str, places_weights_path: Path) -> tuple[nn.Module, str]:
    effective_mode = weights_mode
    if weights_mode == "auto":
        effective_mode = "places365" if places_weights_path.exists() else "imagenet"

    if effective_mode == "places365":
        checkpoint = torch.load(places_weights_path, map_location="cpu", weights_only=False)
        state_dict = checkpoint.get("state_dict", checkpoint)

        if any(key.startswith("features.module.") for key in state_dict):
            model = models.alexnet(num_classes=365)
            state_dict = {
                key.replace("features.module.", "features.").replace("classifier.module.", "classifier."): value
                for key, value in state_dict.items()
            }
            model.load_state_dict(state_dict)
            return model.eval(), "places365"

        model = Places365AlexNet(num_classes=365)
        state_dict = {key.replace("module.", ""): value for key, value in state_dict.items()}
        model.load_state_dict(state_dict)
        return model.eval(), "places365"

    weights = models.AlexNet_Weights.IMAGENET1K_V1
    model = models.alexnet(weights=weights)
    return model.eval(), "imagenet"


def build_transform(model_name: str) -> transforms.Compose:
    if model_name == "places365":
        return transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    return transforms.Compose(
        [
            transforms.Resize((256, 256)),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )


def register_hooks(model: nn.Module, layers: Iterable[str], store: Dict[str, torch.Tensor]):
    handles = []
    named_modules = dict(model.named_modules())
    model_name = "places365" if isinstance(model, Places365AlexNet) else "imagenet"

    for layer in layers:
        module_name = LAYER_MAP[model_name][layer]
        module = named_modules[module_name]

        def capture(_module, _inputs, output, layer_name=layer):
            store[layer_name] = output.detach().cpu()

        handles.append(module.register_forward_hook(capture))

    return handles


def load_batch(paths: List[str], transform: transforms.Compose) -> torch.Tensor:
    tensors = []
    for path in paths:
        with Image.open(path) as image:
            tensors.append(transform(image.convert("RGB")))
    return torch.stack(tensors, dim=0)


def extract_features(
    manifest: pd.DataFrame,
    model: nn.Module,
    layers: List[str],
    device: torch.device,
    batch_size: int,
    model_name: str,
) -> Dict[str, np.ndarray]:
    transform = build_transform(model_name)
    layer_batches: Dict[str, List[np.ndarray]] = defaultdict(list)
    hook_outputs: Dict[str, torch.Tensor] = {}
    handles = register_hooks(model, layers, hook_outputs)

    model.to(device)
    with torch.inference_mode():
        image_paths = manifest["image_path"].tolist()
        for start in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[start : start + batch_size]
            batch_tensor = load_batch(batch_paths, transform).to(device)
            _ = model(batch_tensor)

            for layer in layers:
                values = hook_outputs[layer].reshape(len(batch_paths), -1).numpy().astype(np.float32)
                layer_batches[layer].append(values)

    for handle in handles:
        handle.remove()

    return {layer: np.concatenate(chunks, axis=0) for layer, chunks in layer_batches.items()}


def save_outputs(
    output_dir: Path,
    manifest: pd.DataFrame,
    features: Dict[str, np.ndarray],
    workbook: Path,
    sheet_name: str,
    model_name: str,
    device: torch.device,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "image_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    summary = {
        "workbook": str(workbook.resolve()),
        "sheet_name": sheet_name,
        "model_name": model_name,
        "device": str(device),
        "n_unique_images": int(len(manifest)),
        "layers": {},
    }

    for layer_name, values in features.items():
        np.save(output_dir / f"{layer_name}_features.npy", values)
        summary["layers"][layer_name] = {
            "shape": list(values.shape),
            "dtype": str(values.dtype),
            "file": f"{layer_name}_features.npy",
        }

    (output_dir / "feature_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    workbook = args.workbook.resolve()
    output_dir = args.output_dir.resolve()
    device = resolve_device(args.device)

    manifest = read_manifest(workbook, args.sheet_name)
    if manifest.empty:
        raise SystemExit("No image paths found in the workbook.")

    model, model_name = load_alexnet(args.weights, args.places_weights_path.resolve())
    features = extract_features(
        manifest=manifest,
        model=model,
        layers=args.layers,
        device=device,
        batch_size=args.batch_size,
        model_name=model_name,
    )
    save_outputs(
        output_dir=output_dir,
        manifest=manifest,
        features=features,
        workbook=workbook,
        sheet_name=args.sheet_name,
        model_name=model_name,
        device=device,
    )

    print(f"Saved manifest and {len(features)} feature matrices to {output_dir}")
    print(f"Model: {model_name}")
    print(f"Unique images: {len(manifest)}")
    for layer_name, values in features.items():
        print(f"{layer_name}: {values.shape}")


if __name__ == "__main__":
    main()
