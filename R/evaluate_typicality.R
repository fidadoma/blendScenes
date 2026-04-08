library(ellmer)
library(tidyverse)
library(here)

stimuli_info <- readxl::read_excel(here("stimuli/140_stimuli/stimuli_info_140.xlsx"))

evaluate_image <- function(fpath) {
  chat <- chat_openai(
    model = "gpt-4.1-mini",
    system_prompt = "You will be presented with image of rooms. Your task is to evalute the typicality of the image within the category. You will be given values 0 - 100. Zero means completely untypical, 100 means completely typical."
  )
  
  typ <- chat$extract_data(
    content_image_file(fpath),
    type = type_object(
      typicality = type_number())
  )
  typ$typicality
}

process_stimulus <- function(stimulus_path) {
  fpath <- here(stimulus_path)
  typicality_scores <- purrr::map_dbl(1:10, ~ evaluate_image(fpath))
  return(list(
    typ_chatgpt_m = mean(typicality_scores),
    typ_chatgpt_sd = sd(typicality_scores),
    typ_chatgpt_min = min(typicality_scores),
    typ_chatgpt_max = max(typicality_scores)
  ))
}

results_list <- purrr::map(stimuli_info$stimulus, process_stimulus, .progress = TRUE) 

my_tibble <- tibble(
  typ_chatgpt_m = map_dbl(results_list, "typ_chatgpt_m"),
  typ_chatgpt_sd = map_dbl(results_list, "typ_chatgpt_sd"),
  typ_chatgpt_min = map_dbl(results_list, "typ_chatgpt_min"),
  typ_chatgpt_max = map_dbl(results_list, "typ_chatgpt_max")
)
stimuli_info <- stimuli_info %>% bind_cols(my_tibble)
saveRDS(stimuli_info, "stimuli_info_chatgpt.rds")
c <- cor.test(stimuli_info$typicality, stimuli_info$typ_chatgpt_m)

stimuli_info %>% 
  ggplot(aes(x = typicality, y = typ_chatgpt_m)) + 
  geom_point() + 
  coord_cartesian(xlim = c(0,100),ylim = c(0,100)) + 
  theme_minimal() + 
  ggtitle("Typicality ratings by ChatGPT vs. human typicality ratings", subtitle = paste0("Correlation: ", round(c$estimate, 2), " (p = ", round(c$p.value, 3), ")"))

          