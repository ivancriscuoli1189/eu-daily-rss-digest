# scripts/emm_radar.R
# EMM Radar (multi-lingua) per Tunisia/area MENA
# - usa quotefinder::qf_get_emm_newsbrief() se disponibile
# - filtra per parole chiave Tunisia/Tunis/TN (configurabile via env)
# - salva JSON in data/emm_radar.json e un box Markdown in .cache/emm_radar.md

suppressPackageStartupMessages({
  library(jsonlite)
  library(dplyr)
  library(stringr)
  library(purrr)
  library(lubridate)
  library(tidyr)
})

# Carico quotefinder solo se presente (viene installato dal workflow CI)
has_qf <- requireNamespace("quotefinder", quietly = TRUE)

# --------- Parametri via env (con default sicuri) ----------
get_env <- function(name, default) {
  val <- Sys.getenv(name, unset = "")
  if (identical(val, "")) default else val
}

RADAR_HOURS   <- as.numeric(get_env("RADAR_HOURS", "6"))          # finestra temporale
RADAR_LANGS   <- strsplit(get_env("RADAR_LANGS", "en,fr,it"), ",")[[1]] |> trimws()
RADAR_MAX     <- as.integer(get_env("RADAR_MAX", "25"))           # massimo elementi
RADAR_QUERY   <- get_env("RADAR_QUERY", "Tunisia|Tunisie|Tunis\\b|\\bTN\\b")
RADAR_SECTION <- get_env("RADAR_SECTION_TITLE", "EMM Radar – Tunisia (ultime ore)")

# --------- Helper robusti ----------
coalesce_col <- function(df, candidates, to = NULL) {
  for (nm in candidates) if (nm %in% names(df)) return(df[[nm]])
  if (is.null(to)) return(rep(NA, nrow(df))) else return(rep(to, nrow(df)))
}

normalise_news <- function(df) {
  if (is.null(df) || nrow(df) == 0) return(tibble::tibble())
  # flessibile ai nomi colonne di qf_get_emm_newsbrief (o futuri)
  title   <- coalesce_col(df, c("title", "headline"))
  link    <- coalesce_col(df, c("url", "link"))
  source  <- coalesce_col(df, c("source", "publisher", "outlet"))
  lang    <- coalesce_col(df, c("language", "lang"))
  # data/ora (varianti possibili)
  dt_raw  <- coalesce_col(df, c("date", "datetime", "time", "pubdate", "published"))
  # prova a parsare le date in UTC
  dt <- suppressWarnings({
    if (inherits(dt_raw, "POSIXt")) dt_raw else
      if (inherits(dt_raw, "Date")) as.POSIXct(dt_raw) else
        parse_date_time(dt_raw, orders = c(
          "Ymd HMS", "Y-m-d H:M:S", "Ymd HM", "Y-m-d H:M",
          "Ymd", "Y-m-d", "d b Y H:M", "d b Y"
        ), tz = "UTC")
  })
  tibble::tibble(
    title = as.character(title),
    link  = as.character(link),
    source = as.character(source),
    language = as.character(lang),
    date = as.POSIXct(dt, tz = "UTC")
  )
}

write_outputs <- function(items_tbl) {
  dir.create("data", showWarnings = FALSE, recursive = TRUE)
  dir.create(".cache", showWarnings = FALSE, recursive = TRUE)

  meta <- list(
    generated_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    hours = RADAR_HOURS,
    langs = RADAR_LANGS
  )

  # JSON
  items_json <- purrr::pmap(items_tbl, function(title, link, source, language, date) {
    list(
      title = title,
      link = link,
      source = source,
      language = language,
      date = if (!is.na(date)) format(date, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") else NA
    )
  })

  jsonlite::write_json(
    list(meta = meta, items = items_json),
    "data/emm_radar.json",
    pretty = TRUE, auto_unbox = TRUE
  )

  # Markdown (box per il digest)
  if (nrow(items_tbl) > 0) {
    lines <- paste0(
      "- [", items_tbl$title, "](", items_tbl$link, ") — ",
      items_tbl$source %||% "sconosciuta",
      ifelse(is.na(items_tbl$date), "", paste0(" (", format(items_tbl$date, "%d %b %H:%M", tz = "UTC"), " UTC)"))
    )
    md <- c(paste0("### ", RADAR_SECTION), "", lines, "")
  } else {
    md <- c(paste0("### ", RADAR_SECTION), "", "_Nessun aggiornamento nelle ultime ore._", "")
  }
  writeLines(md, ".cache/emm_radar.md")
}

`%||%` <- function(a, b) if (is.null(a) || length(a) == 0) b else a

# --------- 1) Tentativo principale: quotefinder ---------
df <- NULL
if (has_qf) {
  message("Using quotefinder::qf_get_emm_newsbrief()")
  df <- tryCatch(
    {
      # NB: la funzione accetta un vettore di codici lingua ISO 2
      qf <- quotefinder::qf_get_emm_newsbrief(langs = RADAR_LANGS, hours = RADAR_HOURS)
      as.data.frame(qf)
    },
    error = function(e) {
      message("quotefinder failed: ", conditionMessage(e))
      NULL
    }
  )
} else {
  message("Package 'quotefinder' non disponibile: salto al fallback (nessuno scraping a runtime).")
}

news <- normalise_news(df)

# --------- Filtro Tunisia / regex personalizzabile ----------
if (nrow(news) > 0) {
  news <- news |>
    filter(
      str_detect(
        paste(title, collapse = " "),
        regex(RADAR_QUERY, ignore_case = TRUE)
      )
    ) |>
    arrange(desc(coalesce(date, as.POSIXct(0, origin = "1970-01-01", tz = "UTC")))) |>
    distinct(link, .keep_all = TRUE) |>
    slice_head(n = RADAR_MAX)
}

# --------- Uscite ----------
write_outputs(news)

message(sprintf("Radar prodotto: %d elementi (finestra: %sh, lingue: %s)",
                nrow(news), RADAR_HOURS, paste(RADAR_LANGS, collapse = ",")))
