#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(ellmer)
  library(purrr)
  library(readr)
  library(tibble)
})

args <- commandArgs(trailingOnly = TRUE)

manifest_csv <- if (length(args) >= 1) args[[1]] else
  "data/deep_features/version_A_places365_alexnet/image_manifest.csv"
output_csv <- if (length(args) >= 2) args[[2]] else
  "data/deep_features/version_A_places365_alexnet/image_manifest_chatgpt_typicality.csv"
n_repeats <- if (length(args) >= 3) as.integer(args[[3]]) else 3L
model <- if (length(args) >= 4) args[[4]] else Sys.getenv("BLENDSCENES_TYPICALITY_MODEL", unset = "gpt-4.1-mini")

api_key <- Sys.getenv("OPENAI_API_KEY", unset = "")
if (identical(api_key, "")) {
  stop("OPENAI_API_KEY is not set.")
}

manifest_csv <- normalizePath(manifest_csv, winslash = "/", mustWork = TRUE)
output_csv <- normalizePath(output_csv, winslash = "/", mustWork = FALSE)
dir.create(dirname(output_csv), recursive = TRUE, showWarnings = FALSE)

image_manifest <- readr::read_csv(manifest_csv, show_col_types = FALSE)

existing <- if (file.exists(output_csv)) {
  readr::read_csv(output_csv, show_col_types = FALSE)
} else {
  tibble::tibble()
}

done_paths <- if (nrow(existing)) unique(existing$image_path) else character()
pending <- image_manifest |>
  filter(!image_path %in% done_paths)

message("Completed rows already on disk: ", length(done_paths))
message("Images pending: ", nrow(pending))

evaluate_image_once <- function(image_path) {
  chat <- ellmer::chat_openai(
    model = model,
    system_prompt = paste(
      "You will be presented with a single scene image.",
      "Rate its visual typicality on a 0 to 100 scale.",
      "0 means extremely atypical, odd, or implausible for a scene image.",
      "100 means highly typical, natural, and prototypical as a scene image."
    )
  )

  typ <- chat$extract_data(
    ellmer::content_image_file(image_path),
    type = ellmer::type_object(
      typicality = ellmer::type_number()
    )
  )
  as.numeric(typ$typicality)
}

score_one_image <- function(image_path) {
  scores <- purrr::map_dbl(seq_len(n_repeats), ~ evaluate_image_once(image_path))
  tibble::tibble(
    typ_chatgpt_m = mean(scores),
    typ_chatgpt_sd = stats::sd(scores),
    typ_chatgpt_min = min(scores),
    typ_chatgpt_max = max(scores),
    typ_chatgpt_n = length(scores),
    typ_chatgpt_model = model
  )
}

append_row <- function(row_df) {
  if (!file.exists(output_csv)) {
    readr::write_csv(row_df, output_csv)
  } else {
    readr::write_csv(row_df, output_csv, append = TRUE, col_names = FALSE)
  }
}

if (!nrow(pending)) {
  message("Nothing to do.")
  quit(save = "no")
}

for (i in seq_len(nrow(pending))) {
  row <- pending[i, , drop = FALSE]
  message(sprintf("[%d/%d] %s", i, nrow(pending), row$image_name[[1]]))
  scores <- score_one_image(row$image_path[[1]])
  out_row <- bind_cols(row, scores)
  append_row(out_row)
}

message("Done: ", normalizePath(output_csv, winslash = "/", mustWork = TRUE))
