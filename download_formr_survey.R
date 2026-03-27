#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(formr)
  library(jsonlite)
})

host <- "https://www.uklab.cz"
survey_name <- "blendScenes_prolific_A"
survey_id <- 3270L

args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args) >= 1) args[[1]] else
  file.path("data", "formr_downloads")
overwrite <- if (length(args) >= 2)
  tolower(args[[2]]) %in% c("1", "true", "yes") else TRUE

email <- Sys.getenv("FORMR_EMAIL", unset = "")
password <- Sys.getenv("FORMR_PASSWORD", unset = "")
keyring_name <- Sys.getenv("FORMR_KEYRING", unset = "")

if (email == "" && password == "" && keyring_name == "") {
  stop(
    paste(
      "Set FORMR_EMAIL and FORMR_PASSWORD, or FORMR_KEYRING, before running this script.",
      "Example:",
      "FORMR_EMAIL=you@example.org FORMR_PASSWORD=secret Rscript download_formr_survey.R",
      sep = "\n"
    ),
    call. = FALSE
  )
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
survey_dir <- file.path(output_dir, survey_name)
dir.create(survey_dir, recursive = TRUE, showWarnings = FALSE)

if (keyring_name != "") {
  formr_connect(keyring = keyring_name, host = host)
} else {
  formr_connect(email = email, password = password, host = host)
}

on.exit(try(formr_disconnect(host = host), silent = TRUE), add = TRUE)

message(
  "Downloading survey backup from ",
  host,
  " for ",
  survey_name,
  " (survey ID ",
  survey_id,
  ")."
)

item_list <- formr_items(survey_name = survey_name, host = host)
item_table <- as.data.frame(item_list)

write_json(
  list(
    host = host,
    survey_name = survey_name,
    survey_id = survey_id,
    downloaded_at = format(Sys.time(), tz = "UTC", usetz = TRUE),
    formr_version = as.character(utils::packageVersion("formr"))
  ),
  path = file.path(survey_dir, "download_metadata.json"),
  pretty = TRUE,
  auto_unbox = TRUE
)

saveRDS(item_list, file = file.path(survey_dir, "item_list.rds"))
utils::write.csv(
  item_table,
  file = file.path(survey_dir, "item_table.csv"),
  row.names = FALSE,
  na = ""
)

formr_backup_surveys(
  survey_names = survey_name,
  surveys = setNames(list(item_list), survey_name),
  save_path = output_dir,
  overwrite = overwrite,
  host = host
)

message(
  "Saved backup to: ",
  normalizePath(survey_dir, winslash = "/", mustWork = FALSE)
)
