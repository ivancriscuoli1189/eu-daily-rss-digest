# -*- coding: utf-8 -*-
"""
make_digest.py – versione HTML-first con profili per dominio
Legge 'feeds.txt' con righe tipo:
  LABEL | PAGE | URL
o anche:
  LABEL | URL
Estrae 3–5 link recenti per fonte e scrive digest.md (Markdown).
"""

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EU-DigestBot/1.0; +https://github.com/)"
}
TIMEOUT = 25
MAX_PER_SOURCE = 5

# Selettori mirati per domini "UE & co."
DOMAIN_SELECTORS = {
    # Commissione (Press Corner / News hub)
    "ec.europa.eu": [
        ".ecl-list-illustration__link",
        ".ecl-news-item__title a",
        "a.ecl-link.ecl-link--standalone",
    ],
    "commission.europa.eu": [
        ".ecl-list-illustration__link",
        ".ecl-news-item__title a",
        "a.ecl-link.ecl-link--standalone",
    ],
    # Consiglio (Consilium)
    "consilium.europa.eu": [
        "a.coh-card__link",
        ".coh-list__item a",
    ],
    # Parlamento (Press room)
    "europarl.europa.eu": [
        ".er__result-title a",
        ".ep-article__title a",
        ".link a",
    ],
    # EEAS
    "eeas.europa.eu": [
        "article a",
        ".ecl-list-illustration__link",
        ".ecl-news-item__title a",
    ],
    # MAECI (esteri)
    "esteri.it": [
        "a[href*='/comunicati/']",
        "main a[href*='/comunicati/']",
        "a[href*='/sala_stampa/']",
    ],
    # World Bank / IMF
    "worldbank.org": [
        ".card__title a",
        ".news-card a",
        ".listing__title a",
    ],
    "imf.org": [
        ".teaser__title a",
        ".teaser a",
    ],
}

# Testi da scartare (link di navigazione)
BLACKLIST_TEXT = {
    "reset",
    "salta al contenuto",
    "archivio",
    "interviste e articoli",
    "press corner",
    "news & events",
    "visual stories",
    "cookie",
}

def read_feeds(path="feeds.txt"):
    feeds = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 3:
                label, kind, url = parts
                kind = kind.upper()
            elif len(parts) == 2:
                label, url = parts
                kind = "PAGE"
            else:
                print(f"[WARN] Riga non riconosciuta: {line}")
                continue
            feeds.append((label, kind, url))
    return feeds

def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()

def is_probably_news_href(href: str) -> bool:
    if not href:
        return False
    href_l = href.lower()
    keywords = [
        "news", "press", "article", "stories", "updates",
        "communic", "comunic", "notizie", "actualites",
        "en-pr", "press-releases", "statement", "story", "event"
    ]
    return any(k in href_l for k in keywords)

def fetch(url: str):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def extract_links_from_page(url: str):
    try:
        html = fetch(url)
    except Exception as e:
        print(f"[ERR] GET {url}: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    items = []

    # 0) selettori specifici per dominio
    netloc = urlparse(url).netloc.lower()
    for sel in DOMAIN_SELECTORS.get(netloc, []):
        for a in soup.select(sel):
            if not a or not a.get("href"):
                continue
            title = clean_text(a.get_text())
            href = urljoin(url, a["href"])
            if not title or not href:
                continue
            if title.lower() in BLACKLIST_TEXT:
                continue
            items.append((title, href))
            if len(items) >= MAX_PER_SOURCE:
                break
        if len(items) >= MAX_PER_SOURCE:
            break

    # 1) fallback <article>
    if len(items) < MAX_PER_SOURCE:
        for art in soup.find_all("article"):
            a = art.find("a", href=True)
            if not a:
                continue
            title = clean_text(a.get_text())
            href = urljoin(url, a["href"])
            if title and href and title.lower() not in BLACKLIST_TEXT:
                items.append((title, href))
                if len(items) >= MAX_PER_SOURCE:
                    break

    # 2) fallback H1/H2 con link
    if len(items) < MAX_PER_SOURCE:
        for tag in soup.find_all(["h1", "h2"]):
            a = tag.find("a", href=True)
            if not a:
                continue
            title = clean_text(a.get_text())
            href = urljoin(url, a["href"])
            if title and href and title.lower() not in BLACKLIST_TEXT:
                items.append((title, href))
                if len(items) >= MAX_PER_SOURCE:
                    break

    # 3) fallback <a> con pattern "news/press..."
    if len(items) < MAX_PER_SOURCE:
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            title = clean_text(a.get_text())
            if is_probably_news_href(href) and len(title) > 4 and title.lower() not in BLACKLIST_TEXT:
                items.append((title, href))
                if len(items) >= MAX_PER_SOURCE:
                    break

    # de-duplica preservando ordine
    seen, dedup = set(), []
    for t, h in items:
        key = (t.lower(), h)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((t, h))
        if len(dedup) >= MAX_PER_SOURCE:
            break

    return dedup

def build_digest(feeds):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    lines.append(f"Daily Digest — {today} (UTC)\n")

    total = 0
    for label, kind, url in feeds:
        lines.append(f"## {label}\n")
        if kind != "PAGE":
            kind = "PAGE"  # per ora trattiamo tutto come PAGE
        items = extract_links_from_page(url)

        if not items:
            lines.append("- _(nessuna novità rilevante o pagina non leggibile)_\n\n")
            continue

        for title, href in items:
            lines.append(f"- [{title}]({href})\n")
            total += 1
        lines.append("\n")

    if total == 0:
        lines.append("\n> Nessuna novità trovata nelle fonti elencate.\n")
    return "".join(lines)

def main():
    feeds = read_feeds("feeds.txt")
    content = build_digest(feeds)
    with open("digest.md", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
