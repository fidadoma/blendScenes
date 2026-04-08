build_raw_results_workbook <- function(results_json, output_xlsx) {
  suppressPackageStartupMessages({
    library(jsonlite)
    library(openxlsx)
  })

  results_raw <- jsonlite::fromJSON(results_json, simplifyDataFrame = TRUE)
  output_xlsx <- normalizePath(output_xlsx, winslash = "/", mustWork = FALSE)
  dir.create(dirname(output_xlsx), recursive = TRUE, showWarnings = FALSE)

  wb <- openxlsx::createWorkbook()
  header_style <- openxlsx::createStyle(textDecoration = "bold")
  openxlsx::addWorksheet(wb, "raw_results")
  openxlsx::writeData(wb, "raw_results", results_raw, withFilter = TRUE)
  openxlsx::addStyle(
    wb,
    "raw_results",
    header_style,
    rows = 1,
    cols = seq_len(ncol(results_raw)),
    gridExpand = TRUE
  )
  openxlsx::freezePane(wb, "raw_results", firstRow = TRUE)
  openxlsx::setColWidths(wb, "raw_results", cols = seq_len(min(ncol(results_raw), 12)), widths = "auto")
  openxlsx::saveWorkbook(wb, output_xlsx, overwrite = TRUE)
  output_xlsx
}


build_long_results_workbook <- function(results_json, blends_xlsx, output_xlsx, images_source_dir = "images/source") {
  suppressPackageStartupMessages({
    library(jsonlite)
    library(openxlsx)
    library(readxl)
  })

  normalize_image_key <- function(x) {
    x <- as.character(x)
    x <- trimws(x)
    x <- sub("[\r\n].*$", "", x)
    x <- sub("\\.(png|jpg|jpeg)$", "", x, ignore.case = TRUE)
    x <- sub("^O([0-9a-fA-F])", "0\\1", x)
    x
  }

  results_raw <- jsonlite::fromJSON(results_json, simplifyDataFrame = TRUE)
  blends_raw <- readxl::read_excel(blends_xlsx)
  source_dir <- normalizePath(images_source_dir, winslash = "/", mustWork = TRUE)

  all_files <- list.files(source_dir, recursive = TRUE, full.names = TRUE)
  all_files <- all_files[file.info(all_files)$isdir %in% FALSE]
  file_keys <- normalize_image_key(tools::file_path_sans_ext(basename(all_files)))
  file_map <- stats::setNames(normalizePath(all_files, winslash = "/", mustWork = FALSE), file_keys)

  slider_cols <- grep("^slider_([0-9]+|catch[0-9]+)$", names(results_raw), value = TRUE)
  slider_cols <- slider_cols[order(vapply(
    slider_cols,
    function(x) {
      if (grepl("^slider_catch", x)) {
        1000000L + as.integer(sub("^slider_catch", "", x))
      } else {
        as.integer(sub("^slider_", "", x))
      }
    },
    integer(1)
  ))]

  blend_lookup <- data.frame(
    trial_id = as.integer(blends_raw$id_blendu),
    blend_image = as.character(blends_raw$blend_name),
    left_image = as.character(blends_raw$img_name1),
    right_image = as.character(blends_raw$img_name2),
    stringsAsFactors = FALSE
  )
  blend_lookup$blend_key <- normalize_image_key(blend_lookup$blend_image)
  blend_lookup$left_key <- normalize_image_key(blend_lookup$left_image)
  blend_lookup$right_key <- normalize_image_key(blend_lookup$right_image)
  blend_lookup$blend_path <- unname(file_map[blend_lookup$blend_key])
  blend_lookup$left_path <- unname(file_map[blend_lookup$left_key])
  blend_lookup$right_path <- unname(file_map[blend_lookup$right_key])

  participant_cols <- c("session_id", "session", "iteration", "prolific_code", "study_id", "created", "modified", "ended")
  participant_cols <- participant_cols[participant_cols %in% names(results_raw)]

  long_rows <- do.call(
    rbind,
    lapply(seq_len(nrow(results_raw)), function(i) {
      participant <- results_raw[i, participant_cols, drop = FALSE]
      do.call(
        rbind,
        lapply(slider_cols, function(col) {
          is_catch <- grepl("^slider_catch", col)
          trial_id <- if (is_catch) NA_integer_ else as.integer(sub("^slider_", "", col))
          lookup_row <- if (!is.na(trial_id)) {
            blend_lookup[blend_lookup$trial_id == trial_id, , drop = FALSE]
          } else {
            blend_lookup[0, , drop = FALSE]
          }

          data.frame(
            participant,
            trial_var = col,
            trial_type = if (is_catch) "catch" else "trial",
            trial_id = trial_id,
            rating = suppressWarnings(as.numeric(results_raw[[col]][i])),
            blend_image = if (nrow(lookup_row)) lookup_row$blend_image[[1]] else NA_character_,
            left_image = if (nrow(lookup_row)) lookup_row$left_image[[1]] else NA_character_,
            right_image = if (nrow(lookup_row)) lookup_row$right_image[[1]] else NA_character_,
            blend_path = if (nrow(lookup_row)) lookup_row$blend_path[[1]] else NA_character_,
            left_path = if (nrow(lookup_row)) lookup_row$left_path[[1]] else NA_character_,
            right_path = if (nrow(lookup_row)) lookup_row$right_path[[1]] else NA_character_,
            stringsAsFactors = FALSE
          )
        })
      )
    })
  )

  for (col in c("blend_image", "left_image", "right_image", "blend_path", "left_path", "right_path")) {
    long_rows[[col]][long_rows$trial_type == "catch"] <- NA_character_
  }

  long_rows <- long_rows[, c(
    participant_cols, "trial_var", "trial_type", "trial_id", "rating",
    "blend_image", "left_image", "right_image",
    "blend_path", "left_path", "right_path"
  )]
  rownames(long_rows) <- NULL

  output_xlsx <- normalizePath(output_xlsx, winslash = "/", mustWork = FALSE)
  dir.create(dirname(output_xlsx), recursive = TRUE, showWarnings = FALSE)

  wb <- openxlsx::createWorkbook()
  header_style <- openxlsx::createStyle(textDecoration = "bold")
  openxlsx::addWorksheet(wb, "long_results")
  openxlsx::writeData(wb, "long_results", long_rows, withFilter = TRUE)
  openxlsx::addStyle(
    wb,
    "long_results",
    header_style,
    rows = 1,
    cols = seq_len(ncol(long_rows)),
    gridExpand = TRUE
  )
  openxlsx::freezePane(wb, "long_results", firstRow = TRUE)
  openxlsx::setColWidths(wb, "long_results", cols = seq_len(ncol(long_rows)), widths = "auto")
  openxlsx::saveWorkbook(wb, output_xlsx, overwrite = TRUE)
  output_xlsx
}


run_places365_feature_extraction <- function(workbook_xlsx, model_path, script_path, output_dir, python_bin = Sys.getenv("BLENDSCENES_PYTHON", unset = "C:/Users/filip/miniconda3/python.exe")) {
  output_dir <- normalizePath(output_dir, winslash = "/", mustWork = FALSE)
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  args <- c(
    normalizePath(script_path, winslash = "/", mustWork = TRUE),
    "--workbook", normalizePath(workbook_xlsx, winslash = "/", mustWork = TRUE),
    "--output-dir", output_dir,
    "--weights", "places365",
    "--places-weights-path", normalizePath(model_path, winslash = "/", mustWork = TRUE)
  )
  status <- system2(python_bin, args = args)
  if (!identical(status, 0L)) {
    stop("PyTorch feature extraction failed.")
  }

  normalizePath(
    c(
      file.path(output_dir, "image_manifest.csv"),
      file.path(output_dir, "feature_summary.json"),
      file.path(output_dir, "conv1_features.npy"),
      file.path(output_dir, "conv2_features.npy"),
      file.path(output_dir, "conv3_features.npy"),
      file.path(output_dir, "conv4_features.npy"),
      file.path(output_dir, "conv5_features.npy"),
      file.path(output_dir, "fc6_features.npy"),
      file.path(output_dir, "fc7_features.npy")
    ),
    winslash = "/",
    mustWork = TRUE
  )
}


export_feature_csvs <- function(feature_dir, script_path, upstream_files = character(), python_bin = Sys.getenv("BLENDSCENES_PYTHON", unset = "C:/Users/filip/miniconda3/python.exe")) {
  feature_dir <- normalizePath(feature_dir, winslash = "/", mustWork = TRUE)
  status <- system2(
    python_bin,
    args = c(normalizePath(script_path, winslash = "/", mustWork = TRUE), "--input-dir", feature_dir)
  )
  if (!identical(status, 0L)) {
    stop("Feature CSV export failed.")
  }

  normalizePath(
    file.path(
      feature_dir,
      c(
        "conv1_features.csv",
        "conv2_features.csv",
        "conv3_features.csv",
        "conv4_features.csv",
        "conv5_features.csv",
        "fc6_features.csv",
        "fc7_features.csv"
      )
    ),
    winslash = "/",
    mustWork = TRUE
  )
}


render_quarto_report <- function(qmd_path, output_html = NULL, depends_on = character(), quarto_bin = Sys.getenv("BLENDSCENES_QUARTO", unset = "C:/Program Files/RStudio/resources/app/bin/quarto/bin/quarto.exe")) {
  qmd_path <- normalizePath(qmd_path, winslash = "/", mustWork = TRUE)
  if (is.null(output_html)) {
    output_html <- sub("\\.qmd$", ".html", qmd_path)
  }
  output_html <- normalizePath(output_html, winslash = "/", mustWork = FALSE)

  status <- system2(quarto_bin, args = c("render", qmd_path))
  if (!identical(status, 0L)) {
    stop("Quarto render failed.")
  }

  normalizePath(output_html, winslash = "/", mustWork = TRUE)
}
