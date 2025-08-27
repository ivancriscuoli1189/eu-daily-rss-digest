# scripts/emm_radar.R
# Produce /tmp/emm_radar.json con gli ultimi item EMM filtrati per Tunisia/MENA

# 1) dipendenze (installa una volta in CI; se già presenti, viene saltato)
if (!requireNamespace("remotes", quietly = TRUE)) install.packages("remotes")
if (!requireNamespace("jsonlite", quietly = TRUE)) install.packages("jsonlite")
# quotefinder non è su CRAN; installa da GitHub (cachato in CI)
if (!requireNamespace("quotefinder", quietly = TRUE)) {
  remotes::install_github("edjnet/quotefinder", upgrade = "never")
}

library(quotefinder)
library(jsonlite)

# 2) parametri “radar”
langs <- c("en","fr","it","ar")        # multi-lingua
hours_back <- 6                        # finestra fresca
max_items <- 15                        # quante righe mostrare nel digest
# filtri semplici su titolo+descrizione (tunisia/area MENA e migrazioni/UE)
rx <- "(tunisi|tunis|tunisia|tunisie|تونس|maghreb|algeria|libya|eu|migration|asylum|migrant|frontex)"

# 3) fetch + filtri
# qf_get_emm_newsbrief ritorna un data frame stile “newsbrief”
nb <- qf_get_emm_newsbrief(languages = langs, hours = hours_back)

# normalizza colonne disponibili (titolo, descr, url originale, sorgente, lingua, data)
cols <- intersect(names(nb), c("title","description","url","source","language","date"))
nb2  <- nb[, cols, drop = FALSE]

# filtro testuale su titolo+descrizione
txt <- paste(nb2$title, nb2$description)
keep <- grepl(rx, txt, ignore.case = TRUE)
nb2  <- nb2[keep, , drop = FALSE]

# ordina per data desc e limita
if ("date" %in% names(nb2)) {
  nb2 <- nb2[order(nb2$date, decreasing = TRUE), ]
}
nb2 <- head(nb2, max_items)

# 4) output JSON (solo campi utili al digest)
out <- within(nb2, {
  # fallback se manca la descrizione
  if (!"description" %in% names(nb2)) description <- ""
})
write_json(out, "/tmp/emm_radar.json", pretty = TRUE, auto_unbox = TRUE)
cat(sprintf("EMM Radar: wrote %d items to /tmp/emm_radar.json\n", nrow(out)))
