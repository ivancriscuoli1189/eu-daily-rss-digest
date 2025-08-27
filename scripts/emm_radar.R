# scripts/emm_radar.R
suppressPackageStartupMessages({
  library(httr2)
  library(xml2)
  library(rvest)
  library(dplyr)
  library(stringr)
  library(purrr)
  library(tibble)
  library(jsonlite)
})

# --- Parametri da env con fallback sensati ---
urls_raw   <- Sys.getenv("EMM_URLS",
  "https://emm.newsbrief.eu/NewsBrief/countryedition/it/TN.html,https://emm.newsbrief.eu/NewsBrief/countryedition/it/IT.html"
)
urls       <- strsplit(urls_raw, ",")[[1]] |> trimws()
out_path   <- Sys.getenv("EMM_OUTPUT", "data/sources/emm_radar.json")
max_items  <- as.integer(Sys.getenv("EMM_MAX_ITEMS", "40"))
if (is.na(max_items) || max_items < 1) max_items <- 40

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)

ua <- "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) EMMRadar/1.0 Safari/537.36"

fetch_one <- function(u) {
  message("Fetching: ", u)
  req <- request(u) |>
    req_user_agent(ua) |>
    req_timeout(30) |>
    req_headers(`Accept-Language` = "it,en;q=0.8")

  resp <- tryCatch(req_perform(req), error = function(e) NULL)
  if (is.null(resp)) return(tibble())

  html <- tryCatch(read_html(resp_body_string(resp)), error = function(e) NULL)
  if (is.null(html)) return(tibble())

  # Ancore candidate: link esterni alle fonti (non EMM), con testo “abbastanza lungo”
  anchors <- html |>
    html_elements("a[target='_blank'][href^='http'], a[href^='http']")

  titles <- anchors |> html_text2() |> str_squish()
  hrefs  <- anchors |> html_attr("href")

  df <- tibble(title = titles, url = hrefs) |>
    filter(
      str_detect(url, "^https?://"),
      !str_detect(url, "emm\\.newsbrief\\.eu"),
      nchar(title) >= 35
    ) |>
    distinct(url, .keep_all = TRUE) |>
    mutate(
      source = str_remove(str_extract(url, "^https?://([^/]+)"), "^https?://"),
      page   = u
    )

  if (nrow(df) == 0) return(tibble())
  df
}

items <- urls |>
  map(fetch_one) |>
  list_rbind() |>
  slice_head(n = max_items)

payload <- list(
  generated_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  pages = urls,
  items = items |>
    transmute(
      title = title,
      source = source,
      url = url,
      page = page
    )
)

write_json(payload, out_path, auto_unbox = TRUE, pretty = TRUE)
message("Wrote: ", out_path, " (", nrow(items), " items)")

