#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, time, json
from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import tz

# -------------------------
# Config
# -------------------------

FEEDS_FILE = "feeds.txt"
OUTPUT_FILE = "digest.md"
MAX_ITEMS_PER_SOURCE = 10  # quanti link tenere per ogni fonte
REQUEST_TIMEOUT = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "en,it,fr;q=0.8",
}

# parole/URL da scartare (navigation, footer, social, ecc.)
STOPWORD_TEXT = {
    "read more", "more", "leggi", "continua", "continua a leggere",
    "share", "condividi", "tweet", "print", "stampa", "contact",
    "privacy", "cookie", "terms", "about", "credits",
    "rss", "feed", "newsletter", "subscribe", "login", "sign in"
}
STOPWORD_HREF_FRAG = (
    "/tag/", "/tags/", "/topic/", "/category/", "/categorie/",
    "/comment", "/comments", "/search", "?s=",
    "/share", "/print", "/download", "/login", "/sign", "/signup",
    "/privacy", "/cookies", "/cookie", "/terms", "/about",
    "/rss", "/feed", "/feeds"
)

# Regole per alcuni domini / fonti (filtri per Tunisia quando serve).
# Chiave: dominio (senza schema). Valori opzionali:
#   - must_href_contains: elenco di frammenti che DEVONO comparire nell’URL
#   - prefer_href_contains: se presenti, si cerca di preferirli,
#   - title_min_len: lunghezza minima del testo titolo
# Regole di filtraggio per dominio (frammenti in minuscolo).
# Chiave = dominio (netloc). Valori:
#  - must_href_contains: almeno uno di questi frammenti deve comparire nell’URL
#  - prefer_href_contains: se presenti, ordina/prioritizza i link che li contengono
#  - title_min_len: scarta titoli troppo corti
DOMAIN_RULES = {
    # -----------------------
    # UE / ISTITUZIONI
    # -----------------------
    "www.consilium.europa.eu": {
        "prefer_href_contains": [
            "/press/press-releases", "/press/statements",
            "tunisia", "migration", "home-affairs"
        ],
        "title_min_len": 12,
    },
    "consilium.europa.eu": {
        "prefer_href_contains": [
            "/press/press-releases", "/press/statements",
            "tunisia", "migration", "home-affairs"
        ],
        "title_min_len": 12,
    },
    "commission.europa.eu": {
        "prefer_href_contains": [
            "/news", "/press", "presscorner", "news-and-media",
            "tunisia", "migration", "neighbourhood", "home-affairs"
        ],
        "title_min_len": 14,
    },
    "ec.europa.eu": {
        "must_href_contains": ["presscorner", "press"],
        "prefer_href_contains": ["tunisia", "migration"],
        "title_min_len": 14,
    },
    "www.eeas.europa.eu": {
        "must_href_contains": ["tunisia", "/delegations/tunisia"],
        "prefer_href_contains": ["/news", "/press", "/statements", "/delegations/"],
        "title_min_len": 14,
    },
    "neighbourhood-enlargement.ec.europa.eu": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/news", "/stories", "/publications", "/factsheet"],
        "title_min_len": 14,
    },
    "home-affairs.ec.europa.eu": {
        "prefer_href_contains": ["/news", "/press", "migration", "tunisia"],
        "title_min_len": 14,
    },
    "www.europarl.europa.eu": {
        "must_href_contains": ["/news/"],
        "prefer_href_contains": ["press-room", "tunisia", "migration", "libe"],
        "title_min_len": 14,
    },
    "europarl.europa.eu": {
        "must_href_contains": ["/news/"],
        "prefer_href_contains": ["press-room", "tunisia", "migration", "libe"],
        "title_min_len": 14,
    },
    "frontex.europa.eu": {
        "prefer_href_contains": [
            "/media-centre/news", "/news", "/press",
            "tunisia", "north-africa", "mediterran"
        ],
        "title_min_len": 14,
    },
    "data.europa.eu": {
        # dataset: spesso non utile come “notizia”
        "prefer_href_contains": ["tunisia", "near", "assistance"],
        "title_min_len": 12,
    },
    "ue-tunisie.org": {
        "prefer_href_contains": ["/project", "/actualites", "/news", "/activites", "/evenements"],
        "title_min_len": 14,
    },

    # -----------------------
    # ITALIA / ISTITUZIONI
    # -----------------------
    "www.esteri.it": {
        "prefer_href_contains": ["/sala_stampa", "/comunicati", "tunisia"],
        "title_min_len": 12,
    },
    "aics.gov.it": {
        "must_href_contains": ["/comunicati-stampa"],
        "title_min_len": 12,
    },
    "www.governo.it": {
        "must_href_contains": ["/archivio-riunioni"],
        "title_min_len": 12,
    },
    "www.interno.gov.it": {
        "prefer_href_contains": ["dati-e-statistiche", "sbarchi", "migranti"],
        "title_min_len": 12,
    },

    # -----------------------
    # TUNISIA / ISTITUZIONI
    # -----------------------
    "pm.gov.tn": {
        "prefer_href_contains": ["/en", "/fr", "/actualites", "/news"],
        "title_min_len": 12,
    },
    "www.diplomatie.gov.tn": {
        "prefer_href_contains": ["/en", "/fr", "news", "communique"],
        "title_min_len": 12,
    },
    "www.ins.tn": {
        "prefer_href_contains": ["actualite", "publication", "news"],
        "title_min_len": 12,
    },
    "www.interieur.gov.tn": {
        "prefer_href_contains": ["/fr", "/ar", "/en", "actualites", "communiques", "news"],
        "title_min_len": 12,
    },
    "www.carthage.tn": {
        "prefer_href_contains": ["/fr", "/ar", "/en", "activites", "actualites", "news"],
        "title_min_len": 12,
    },

    # -----------------------
    # AGENZIE
    # -----------------------
    "www.ansa.it": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/notizie", "/rubriche", "/mediterraneo"],
        "title_min_len": 12,
    },
    "www.tap.info.tn": {
        "must_href_contains": ["/en"],
        "prefer_href_contains": ["/news", "/national", "/economy", "/world", "/culture"],
        "title_min_len": 12,
    },

    # -----------------------
    # MEDIA TUNISIA
    # -----------------------
    "africanmanager.com": {
        "prefer_href_contains": ["/category/politics", "tun"],
        "title_min_len": 12,
    },
    "lapresse.tn": {
        "prefer_href_contains": ["/politique", "tunisie"],
        "title_min_len": 16,
    },

    # -----------------------
    # NGO
    # -----------------------
    "www.amnesty.org": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/news", "/press", "/report", "/latest"],
        "title_min_len": 14,
    },
    "www.hrw.org": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/news", "/report", "/press"],
        "title_min_len": 14,
    },
    "www.icj.org": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/news", "/press", "/report", "/statement"],
        "title_min_len": 14,
    },

    # -----------------------
    # THINK TANK / MAGAZINES
    # -----------------------
    "carnegie-mec.org": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/diwan", "/commentary", "/publication", "/article"],
        "title_min_len": 14,
    },
    "carnegieendowment.org": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/sada", "/carnegie-mec", "/commentary", "/publication", "/article"],
        "title_min_len": 14,
    },
    "www.ispionline.it": {
        "must_href_contains": ["tunisia", "migraz"],
        "prefer_href_contains": ["/it/analisi", "/it/pubblicazione", "/it/commento", "/it/eventi"],
        "title_min_len": 14,
    },
    "www.iai.it": {
        "must_href_contains": ["tunisia", "migraz"],
        "prefer_href_contains": ["/it/pubblicazioni", "/en/pubblicazioni", "/it/analisi"],
        "title_min_len": 14,
    },
    "www.cespi.it": {
        "must_href_contains": ["tunisia", "migraz"],
        "prefer_href_contains": ["/it"],
        "title_min_len": 12,
    },
    "www.limesonline.com": {
        "must_href_contains": ["tunisia"],
        "title_min_len": 12,
    },
    "www.ecfr.eu": {
        "must_href_contains": ["mena", "tunisia"],
        "prefer_href_contains": ["/publications", "/analysis", "/commentary", "/article"],
        "title_min_len": 14,
    },
    "www.brookings.edu": {
        "must_href_contains": ["middle-east", "north-africa", "tunisia"],
        "prefer_href_contains": ["/research", "/blog", "/article", "/report"],
        "title_min_len": 14,
    },
    "www.crisisgroup.org": {
        "must_href_contains": ["north-africa", "tunisia"],
        "prefer_href_contains": ["/report", "/briefing", "/statement", "/update"],
        "title_min_len": 14,
    },
    "www.jeuneafrique.com": {
        "must_href_contains": ["tunisie"],
        "prefer_href_contains": ["/politique", "/economie", "/societe"],
        "title_min_len": 14,
    },

    # -----------------------
    # IFI / BANCHE
    # -----------------------
    "www.worldbank.org": {
        "must_href_contains": ["tunisia"],
        "prefer_href_contains": ["/news", "/press", "/publications", "/projects", "/brief"],
        "title_min_len": 14,
    },
    "www.imf.org": {
        "must_href_contains": ["/en/"],
        "prefer_href_contains": [
            "/countries/tun", "/countries/tunisia",
            "/news", "/publications", "/press"
        ],
        "title_min_len": 14,
    },
}


# -------------------------
# Utils
# -------------------------

def now_rome_str():
    tz_rome = ZoneInfo("Europe/Rome")
    dt = datetime.now(tz_rome)
    # Es: 26 Aug 2025, 08:30 CEST
    return dt.strftime("%d %b %Y, %H:%M %Z")

def read_feeds(path=FEEDS_FILE):
    feeds = []
    if not os.path.exists(path):
        print(f"[ERROR] {path} non trovato.")
        return feeds
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            label, method, url = parts[0], parts[1].lower(), parts[2]
            feeds.append((label, method, url))
    return feeds

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        # 403/401 → probabile blocco/JS necessario
        if r.status_code in (401, 403):
            return None, f"HTTP {r.status_code} (autorizzazione/blocco)"
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}"
        # qualche sito serve HTML minimo (JS-heavy)
        if r.text and len(r.text) < 600:
            return r.text, "Possibile pagina JS-heavy (contenuto minimo)"
        return r.text, None
    except requests.RequestException as e:
        return None, f"Request error: {e}"

def clean_text(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s

def looks_like_article(url, title):
    """Heuristica semplice per decidere se è un articolo vero e non un link di navigazione."""
    if not url:
        return False
    t = (title or "").lower()
    if len(t) < 10:
        return False
    for bad in STOPWORD_TEXT:
        if bad in t:
            return False
    lower_url = url.lower()
    if any(b in lower_url for b in STOPWORD_HREF_FRAG):
        return False
    # segnali "buoni"
    if re.search(r"/20\d{2}/\d{2}/\d{2}/", lower_url):  # URL con data
        return True
    # slug lungo con trattini
    last = urlparse(lower_url).path.rsplit("/", 1)[-1]
    if "-" in last and len(last) >= 14:
        return True
    # parole chiave “news / press / article”
    if any(k in lower_url for k in ("/news", "/press", "/article", "/comunicati", "/notizie", "/communique", "/communiques")):
        return True
    # fallback
    return len(title) >= 18

def filter_by_domain_rules(items, domain):
    rule = DOMAIN_RULES.get(domain) or {}
    must = rule.get("must_href_contains") or []
    pref = rule.get("prefer_href_contains") or []
    title_min = rule.get("title_min_len", 14)

    out = []
    for title, href in items:
        if not href:
            continue
        t = clean_text(title)
        if len(t) < title_min:
            continue
        L = href.lower()
        # SE c'è una regola "must", l'URL deve contenerne almeno una
        if must and not any(m.lower() in L for m in must):
            continue
        # applico filtro generale
        if not looks_like_article(href, t):
            continue
        out.append((t, href))

    # Se c'è "prefer", ordina per preferenza
    if pref:
        def pref_score(u):
            L = u[1].lower()
            return sum(1 for p in pref if p.lower() in L)
        out.sort(key=pref_score, reverse=True)
    return out

def extract_items_from_html(html, base_url):
    """Estrattore generico: cerca <article> e poi <a> significativi; fallback su h1/h2/h3/a."""
    soup = BeautifulSoup(html, "lxml")

    # 1) Candidati: <article>…<a>
    anchors = []
    for art in soup.find_all(["article", "li", "div"], limit=300):
        # prendi ancore con testo
        for a in art.find_all("a", href=True):
            title = clean_text(a.get_text(" ", strip=True))
            href = urljoin(base_url, a["href"])
            anchors.append((title, href))
    # 2) Fallback: titoli diretti
    if not anchors:
        for sel in ["h1 a", "h2 a", "h3 a", "a"]:
            for a in soup.select(sel):
                if not a.get("href"):
                    continue
                title = clean_text(a.get_text(" ", strip=True))
                href = urljoin(base_url, a["href"])
                anchors.append((title, href))
            if anchors:
                break

    # pulizia: togli duplicati grezzi per href
    seen = set()
    uniq = []
    for title, href in anchors:
        if href in seen:
            continue
        seen.add(href)
        uniq.append((title, href))
    return uniq

def harvest_page(url):
    html, err = fetch(url)
    if html is None:
        return [], err or "Pagina non leggibile"
    domain = urlparse(url).netloc.lower()
    items_raw = extract_items_from_html(html, url)
    items = filter_by_domain_rules(items_raw, domain)
    # se non ha trovato nulla, prova a salvare qualcosa di “decente” dal grezzo
    if not items:
        # fallback: prendi i primi che sembrano notizie
        fallback = []
        for title, href in items_raw:
            if looks_like_article(href, title):
                fallback.append((title, href))
            if len(fallback) >= MAX_ITEMS_PER_SOURCE:
                break
        if fallback:
            items = fallback
    return items[:MAX_ITEMS_PER_SOURCE], err

def harvest_rss(url):
    # opzionale per futuro; qui manteniamo struttura in modo che non esploda se compare "rss"
    try:
        import feedparser
    except Exception:
        return [], "feedparser non installato"
    try:
        d = feedparser.parse(url)
        out = []
        for e in d.entries[:MAX_ITEMS_PER_SOURCE]:
            title = clean_text(getattr(e, "title", "") or "")
            link = getattr(e, "link", "")
            if title and link:
                out.append((title, link))
        return out, None if out else "RSS vuoto"
    except Exception as e:
        return [], f"RSS error: {e}"

def build_digest(feeds_results):
    parts = []
    parts.append(f"# Daily EU/Tunisia Digest\n\n*Generato: {now_rome_str()}*\n")
    current_section = None

    for label, ok_items, err in feeds_results:
        # Sezione
        if current_section != label:
            parts.append(f"\n## {label}\n")

        if ok_items:
            for (title, link) in ok_items:
                parts.append(f"- [{title}]({link})")
        else:
            msg = err or "nessuna novità rilevante o pagina non leggibile"
            parts.append(f"- _(nessun elemento) — {msg}_")

        current_section = label

    return "\n".join(parts) + "\n"

def main():
    feeds = read_feeds(FEEDS_FILE)
    if not feeds:
        print("[ERROR] Nessuna fonte in feeds.txt")
        sys.exit(1)

    results = []
    for (label, method, url) in feeds:
        label_str = label.strip()
        method = method.strip().lower()
        url = url.strip()
        print(f"[INFO] {label_str} → {method.upper()} → {url}")
        items, err = (harvest_rss(url) if method == "rss" else harvest_page(url))
        results.append((label_str, items, err))

    md = build_digest(results)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[OK] Scritto {OUTPUT_FILE} ({len(results)} sezioni)")

if __name__ == "__main__":
    main()

