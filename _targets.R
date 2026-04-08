library(targets)

tar_option_set(
  packages = c("jsonlite", "readxl", "openxlsx", "dplyr", "readr", "tidyr", "tibble")
)

source("R/pipeline_functions.R")

list(
  tar_target(
    formr_results_json,
    "data/formr_downloads/blendScenes_prolific_A/results.json",
    format = "file"
  ),
  tar_target(
    blends_xlsx,
    "data/Blends.xlsx",
    format = "file"
  ),
  tar_target(
    places365_model,
    "python/models/places365/alexnet_places365.pth.tar",
    format = "file"
  ),
  tar_target(
    feature_extractor_script,
    "python/evalute_images_imagedist.py",
    format = "file"
  ),
  tar_target(
    feature_csv_script,
    "python/export_feature_csvs.py",
    format = "file"
  ),
  tar_target(
    deepfeatures_report_qmd,
    "reports/deepfeatures_report.qmd",
    format = "file"
  ),
  tar_target(
    typicality_similarity_report_qmd,
    "reports/typicality_similarity_report.qmd",
    format = "file"
  ),
  tar_target(
    results_report_qmd,
    "reports/results_report.qmd",
    format = "file"
  ),
  tar_target(
    raw_results_workbook,
    build_raw_results_workbook(
      formr_results_json,
      "data/formr_downloads/blendScenes_prolific_A/results_version_A_raw_only.xlsx"
    ),
    format = "file"
  ),
  tar_target(
    long_results_workbook,
    build_long_results_workbook(
      formr_results_json,
      blends_xlsx,
      "data/formr_downloads/blendScenes_prolific_A/results_version_A_long_with_images_and_paths.xlsx"
    ),
    format = "file"
  ),
  tar_target(
    places365_feature_npy,
    run_places365_feature_extraction(
      workbook_xlsx = long_results_workbook,
      model_path = places365_model,
      script_path = feature_extractor_script,
      output_dir = "data/deep_features/version_A_places365_alexnet"
    ),
    format = "file"
  ),
  tar_target(
    places365_feature_csv,
    export_feature_csvs(
      feature_dir = "data/deep_features/version_A_places365_alexnet",
      script_path = feature_csv_script,
      upstream_files = places365_feature_npy
    ),
    format = "file"
  ),
  tar_target(
    chatgpt_typicality_csv,
    "data/deep_features/version_A_places365_alexnet/image_manifest_chatgpt_typicality.csv",
    format = "file"
  ),
  tar_target(
    deepfeatures_report_html,
    render_quarto_report(
      deepfeatures_report_qmd,
      depends_on = c(long_results_workbook, places365_feature_csv)
    ),
    format = "file"
  ),
  tar_target(
    typicality_similarity_report_html,
    render_quarto_report(
      typicality_similarity_report_qmd,
      depends_on = c(long_results_workbook, places365_feature_csv, chatgpt_typicality_csv)
    ),
    format = "file"
  ),
  tar_target(
    results_report_html,
    render_quarto_report(
      results_report_qmd,
      depends_on = c(formr_results_json, blends_xlsx)
    ),
    format = "file"
  )
)
