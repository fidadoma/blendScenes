library(magick)

root_dir <- getwd()
input_dir <- file.path(root_dir, "images")
output_dir <- file.path(root_dir, "reports", "report_images")
max_geometry <- "1200x1200>"
quality <- 70

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

image_paths <- list.files(input_dir, pattern = "_kolaz[.]png$", full.names = TRUE)

if (!length(image_paths)) {
  stop("No collage PNG files found in ", input_dir)
}

for (path in image_paths) {
  img <- image_read(path)
  img_small <- image_scale(img, max_geometry)
  out_path <- file.path(output_dir, basename(path))
  image_write(img_small, path = out_path, format = "png", quality = quality)
  cat("Wrote:", out_path, "\n")
}

cat("Done. Resized", length(image_paths), "images into", output_dir, "\n")
