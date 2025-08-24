# -*- coding: utf-8 -*-
"""
make_digest.py – versione HTML-first (PAGE)
Legge 'feeds.txt' con righe tipo:
  LABEL | PAGE | URL
Per ogni URL HTML prova a estrarre i link più recenti e titoli.
Scrive digest.md in Markdown.
"""

import os, re, sys
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EU-DigestBot/1.0; +https://github.com/)"
}
TIMEOUT = 20
MAX_PER_SOURCE = 5

def read_feeds(path="feeds.txt"):
    feeds = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            # supporta sia "LABEL | PAGE | URL" sia "LABEL | URL"
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

def is_probably_news_href(href):
    if not href: 
        return False
    href_l = href.lower()
    # eur-lex/oeil/consilium/presscorner ecc. spesso in queste directory
    keywords = ["news", "press", "article", "stories", "updates", "communi", "notizie", "actualites", "en-pr", "press-releases", "statement", "story"]
    return any(k in href_l for k in keywords)

def extract_links_from_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERR] GET {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")

    # 1) prova blocchi <article>
    items = []
    for art in soup.find_all("article"):
        a = art.find("a", href=True)
        if not a: 
            continue
        title = clean_text(a.get_text())
        href = urljoin(url, a["href"])
        if title and href:
            items.append((title, href))

    # 2) fallback: H1/H2 con link
    if len(items) < MAX_PER_SOURCE:
        for tag in soup.find_all(["h1", "h2"]):
            a = tag.find("a", href=True)
            if not a: 
                continue
            title = clean_text(a.get_text())
            href = urljoin(url, a["href"])
            if title and href:
                items.append((title, href))

    # 3) fallback: tutti <a> “news/press…”
    if len(items) < MAX_PER_SOURCE:
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            title = clean_text(a.get_text())
            if is_probably_news_href(href) and len(title) > 4:
                items.append((title, href))

    # de-duplica preservando l’ordine
    seen = set()
    dedup = []
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

    total_items = 0
    for label, kind, url in feeds:
        lines.append(f"## {label}\n")
        items = []
        if kind == "PAGE":
            items = extract_links_from_page(url)
        else:
            # per estensioni future (RSS ecc.)
            items = extract_links_from_page(url)

        if not items:
            lines.append("- _(nessuna novità rilevante o pagina non leggibile)_\n\n")
            continue

        for title, href in items:
            lines.append(f"- [{title}]({href})\n")
            total_items += 1
        lines.append("\n")

    if total_items == 0:
        lines.append("\n> Nessuna novità trovata nelle fonti elencate.\n")

    return "".join(lines)

def main():
    feeds = read_feeds("feeds.txt")
    content = build_digest(feeds)
    with open("digest.md", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
