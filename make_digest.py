#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily EU/Tunisia Digest builder
- Legge feeds.txt (formato: LABEL|TIPO|URL)
- TIPO: rss -> parse_rss ; html -> parse_html_links (con selettori per dominio)
- Filtra voci di navigazione / duplicati
- Scrive digest.md con timestamp Europe/Rome
"""

from __future__ import annotations
import os, sys, time, hashlib
from datetime import datetime
from urllib.parse import urlparse, urljoin
from zoneinfo import ZoneInfo

import requests
import feedparser
import certifi
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

# Evita voci di menu / accessibilità
BLACKLIST_TEXT = {
    "salta al contenuto", "vai al contenuto", "passa al contenuto",
    "access to page content", "direct access to language menu",
    "direct access to search menu", "access to search field",
    "raggiungi il piè di pagina", "vai a piè di pagina", "footer",
    "amministrazione trasparente", "privacy", "cookies", "search", "language",
    "visual stories"
}
MIN_TEXT_LEN = 20

# Limiti
HTML_LIMIT = 12
RSS_LIMIT = 8

# Selettori per dominio (fallback: 'a[href]')
DOMAIN_SELECTORS = {
    # ITALIA
    "www.esteri.it": "article a[href], .news-list a[href]",
    "www.governo.it": ".view-content a[href]",
    "www.aics.gov.it": "article a[href], .post-list a[href], .list a[href]",
    "www.interno.gov.it": ".view-content a[href], .field--name-body a[href], article a[href]",
    # TUNISIA / ISTITUZIONI
    "pm.gov.tn": "article a[href], .view-content a[href], .grid a[href]",
    "www.ins.tn": ".view-content a[href], article a[href]",
    "www.carthage.tn": ".views-row a[href], article a[href]",
    # UE / ISTITUZIONI
    "eur-lex.europa.eu": ".home__teaser a[href], a.ecl-link[href]",
    "oeil.secure.europarl.europa.eu": "a[href^='/oeil/en/'], a[href^='/oeil/']",
    "www.europarl.europa.eu": "article a[href^='/news/'], a[href*='/press-room/']",
    "commission.europa.eu": ".ecl-list a[href], article a[href], .ecl-link a[href]",
    "ec.europa.eu": ".ecl-list a[href], article a[href]",
    "www.consilium.europa.eu": ".ecl-listing a[href], article a[href], .listing a[href]",
    "www.eeas.europa.eu": "article a[href], .ecl-u-margin-bottom-l a[href], .ecl-link a[href]",
    "enlargement.ec.europa.eu": ".ecl-list a[href], article a[href]",
    "home-affairs.ec.europa.eu": ".ecl-list a[href], article a[href]",
    # UE–Tunisie
    "ue-tunisie.org": ".box-project a[href^='/projet-'], .box-cat a[href], .pagination a[href]",
    # MEDIA/NGO/TT
    "lapresse.tn": "article a[href], .entry-title a[href]",
    "www.jeuneafrique.com": "article a[href], .c-listing__item a[href]",
    "www.hrw.org": "article a[href], .c-block-list a[href], .content-list a[href]",
    "www.amnesty.org": "article a[href], .o-archive-list__item a[href]",
    "www.icj.org": ".posts-list a[href], article a[href]",
    "www.iai.it": "article a[href], .views-row a[href]",
    "www.cespi.it": "article a[href], .view-content a[href]",
    "www.limesonline.com": "article a[href], .article-card a[href]",
    "scuoladilimes.it": "a[href]",
    "www.brookings.edu": "article a[href], .river__item a[href]",
    "www.worldbank.org": ".wbg-cards a[href], article a[href], a.wbg-link[href]",
    "www.imf.org": "article a[href], .o_news a[href], .o_article a[href]",
}

def log(*args):
    print(*args, file=sys.stderr)

def is_nav(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or len(t) < MIN_TEXT_LEN:
        return True
    return any(k in t for k in BLACKLIST_TEXT)

def fetch(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    last_err = None
    for _ in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, verify=certifi.where())
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise last_err

def get_selector_for_url(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return DOMAIN_SELECTORS.get(netloc, "a[href]")

def parse_rss(url: str, limit: int = RSS_LIMIT):
    items = []
    feed = feedparser.parse(url)
    for e in feed.entries[:limit]:
        title = getattr(e, "title", "").strip()
        link = getattr(e, "link", "").strip()
        if title and link and not is_nav(title):
            items.append((title, link))
    return items

def parse_html_links(url: str, limit: int = HTML_LIMIT):
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    selector = get_selector_for_url(url)
    out = []
    for a in soup.select(selector):
        txt = (a.get_text(strip=True) or "")
        href = a.get("href")
        if not href or is_nav(txt):
            continue
        full = urljoin(url, href)
        out.append((txt, full))
        if len(out) >= limit:
            break
    # ripuliture semplici
    cleaned = []
    for t, u in out:
        lt = t.lower()
        if lt.startswith("aller au projet") or lt in {"vai al contenuto", "salta al contenuto"}:
            continue
        cleaned.append((t, u))
    return cleaned

def dedup(items):
    seen, out = set(), []
    for t, u in items:
        key = hashlib.sha1(u.encode("utf-8")).hexdigest()
        if key not in seen:
            seen.add(key); out.append((t, u))
    return out

def read_feeds(path: str):
    feeds = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                log("IGNORA riga malformata:", line)
                continue
            label, kind, url = parts[0], parts[1].lower(), parts[2]
            feeds.append((label, kind, url))
    return feeds

def build_section(label: str, items):
    if not items:
        return None
    lines = [f"## {label}", ""]
    for t, u in items:
        lines.append(f"- [{t}]({u})")
    lines.append("")  # newline finale
    return "\n".join(lines)

def main():
    root = os.getcwd()
    feeds_path = os.path.join(root, "feeds.txt")
    out_path = os.path.join(root, "digest.md")

    feeds = read_feeds(feeds_path)
    rome = datetime.now(ZoneInfo("Europe/Rome"))
    header = [
        "# Daily EU/Tunisia Digest",
        "",
        f"*Generato: {rome.strftime('%d %b %Y, %H:%M %Z')}*",
        "",
        ""
    ]

    sections = []
    for label, kind, url in feeds:
        try:
            if kind == "rss":
                items = parse_rss(url)
            elif kind == "html":
                items = parse_html_links(url)
            else:
                log(f"TIPO sconosciuto '{kind}' per {label} -> {url}")
                items = []
            items = dedup(items)
            sec = build_section(label, items)
            if sec:
                sections.append(sec)
            else:
                log(f"[VUOTO] {label} ({url})")
        except Exception as e:
            log(f"[ERRORE] {label} ({url}): {e}")
            continue

    content = "\n".join(header + sections).rstrip() + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    log("Digest scritto:", out_path)

if __name__ == "__main__":
    main()

