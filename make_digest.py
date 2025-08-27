#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
make_digest.py
Genera un digest Markdown da:
  - feeds tipizzati in feeds.txt  (formato: LABEL|TIPO|URL)
  - (opzionale) EMM Radar JSON prodotto da scripts/emm_radar.R

TIPO supportati:
  - rss  -> parsing via feedparser
  - html -> scraping generico con BeautifulSoup; usa selettori di fallback
            + qualche selettore specifico per dominio quando noto

ENV opzionali:
  OUTPUT_MD=README.md
  PER_SECTION_LIMIT=10
  EMM_RADAR_JSON=/tmp/emm_radar.json
  EMM_RADAR_TITLE=EMM Radar – ultime 12 ore
  EMM_RADAR_LOOKBACK_HOURS=12
  TIMEZONE=Europe/Rome
"""

from __future__ import annotations

import os
import re
import json
import html
import time
import socket
import logging
from urllib.parse import urlparse, urljoin
from datetime import datetime, timedelta

import requests
import feedparser
from bs4 import BeautifulSoup

try:
    import pytz
except Exception:
    pytz = None

# ----------------------- Config base -----------------------

OUTPUT_MD = os.getenv("OUTPUT_MD", "README.md")
PER_SECTION_LIMIT = int(os.getenv("PER_SECTION_LIMIT", "10"))
EMM_RADAR_JSON = os.getenv("EMM_RADAR_JSON", "/tmp/emm_radar.json")
EMM_RADAR_TITLE = os.getenv("EMM_RADAR_TITLE", "EMM Radar – ultime 12 ore")
EMM_RADAR_LOOKBACK_HOURS = int(os.getenv("EMM_RADAR_LOOKBACK_HOURS", "12"))
TZ_NAME = os.getenv("TIMEZONE", "Europe/Rome")

HEADERS = {
    "User-Agent": "eu-daily-digest-bot/1.0 (+https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = (10, 20)  # (conn, read)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

# ----------------------- Util -----------------------

def now_tz():
    if pytz:
        tz = pytz.timezone(TZ_NAME)
        return datetime.now(tz)
    # fallback naive
    return datetime.now()

def fmt_generated(dt: datetime) -> str:
    # Esempio: 27 Aug 2025, 13:39 CEST
    return dt.strftime("%d %b %Y, %H:%M %Z") if dt.tzinfo else dt.strftime("%d %b %Y, %H:%M")

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def dedupe_by_url(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = set()
    out = []
    for title, url in items:
        key = url.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append((title, url))
    return out

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def safe_get(url: str) -> requests.Response | None:
    try:
        return requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logging.warning(f"GET fallita: {url} -> {e}")
        return None

# ----------------------- Feeds config -----------------------

def load_feeds_config(path: str = "feeds.txt") -> list[dict]:
    """
    Legge linee tipo:
      LABEL|TIPO|URL
    dove TIPO è 'rss' o 'html'
    """
    feeds = []
    if not os.path.exists(path):
        logging.warning("feeds.txt non trovato; nessuna sezione istituzionale verrà generata.")
        return feeds

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                logging.warning(f"Riga feeds.txt non valida (attese 3 colonne): {line}")
                continue
            label, tipo, url = parts[0], parts[1].lower(), parts[2]
            feeds.append({"label": label, "type": tipo, "url": url})
    return feeds

# ----------------------- Parsers -----------------------

# Selettori specifici per alcuni domini (tendono a cambiare: fallback generici sotto)
DOMAIN_SELECTORS: dict[str, list[str]] = {
    # MAECI
    "www.esteri.it": [
        "article h3 a",
        "ul li h3 a",
        "ul li a",
        "a.title",
        "a[href*='/comunicati/']",
    ],
    # Governo
    "www.governo.it": [
        "article h2 a",
        ".views-row h3 a",
        "ul li h3 a",
        "ul li a",
    ],
    # Viminale
    "www.interno.gov.it": [
        "article h3 a",
        ".view-content .views-row h3 a",
        ".view-content .views-row a",
    ],
    # Europarl Press Room
    "www.europarl.europa.eu": [
        "article h3 a",
        ".ep-press-release__title a",
        ".ecl-list-unstyled a",
    ],
    # INS Tunisia
    "www.ins.tn": [
        "article h2 a",
        ".node__title a",
        ".views-row h3 a",
        ".views-row a",
    ],
    # La Presse de Tunisie
    "lapresse.tn": [
        "h3.entry-title a",
        "article h2 a",
        "article h3 a",
        ".post-title a",
    ],
    # Amnesty
    "www.amnesty.org": [
        "article h2 a",
        ".search-content h3 a",
        ".o-archive__item a",
    ],
    # HRW
    "www.hrw.org": [
        ".views-row h3 a",
        "article h3 a",
        ".promo__title a",
    ],
    # ICJ
    "www.icj.org": [
        "article h2 a",
        ".blog-roll h2 a",
        ".post-title a",
    ],
    # ECFR
    "ecfr.eu": [
        "article h2 a",
        ".archive__list h2 a",
        ".card a.title",
    ],
    # Brookings (pagina articoli ME)
    "www.brookings.edu": [
        "article h2 a",
        ".list-content h3 a",
        ".c-article-card__title a",
    ],
    # Jeune Afrique
    "www.jeuneafrique.com": [
        "article h3 a",
        ".c-article__title a",
        ".c-list__item a",
    ],
    # LIMES
    "www.limesonline.com": [
        "article h2 a",
        ".post-title a",
        "h3 a",
    ],
    # DG HOME/NEAR/Commissioni (Drupal/EU styles)
    "home-affairs.ec.europa.eu": [
        "article h3 a",
        ".ecl-link--standalone",
        ".view-content .views-row a",
    ],
    "neighbourhood-enlargement.ec.europa.eu": [
        "article h3 a",
        ".ecl-link--standalone",
        ".view-content .views-row a",
    ],
    "commission.europa.eu": [
        "article h3 a",
        ".ecl-link--standalone",
        ".view-content .views-row a",
    ],
    # PM Tunisia
    "pm.gov.tn": [
        "article h2 a",
        ".node__title a",
        ".views-row a",
    ],
    # Carthage (presidenza Tunisia)
    "www.carthage.tn": [
        "article h2 a",
        "h3 a",
        ".views-row a",
    ],
}

FALLBACK_SELECTORS: list[str] = [
    "article h2 a",
    "article h3 a",
    "ul li h3 a",
    "ul li a",
    "ol li a",
    "h2 a",
    "h3 a",
    "a[href]",
]

def parse_rss(url: str, limit: int) -> list[tuple[str, str]]:
    fp = feedparser.parse(url)
    items = []
    for entry in fp.entries[: limit * 2]:  # prendo qualcosa in più, poi dedupe
        title = clean_text(entry.get("title") or entry.get("summary") or "")
        link = entry.get("link") or ""
        if title and link:
            items.append((title, link))
    return dedupe_by_url(items)[:limit]

def parse_html_links(url: str, limit: int) -> list[tuple[str, str]]:
    resp = safe_get(url)
    if not resp or resp.status_code >= 400:
        logging.warning(f"HTML non raggiungibile: {url} ({getattr(resp, 'status_code', 'n/a')})")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    domain = get_domain(url)

    selectors = DOMAIN_SELECTORS.get(domain, []) + FALLBACK_SELECTORS
    found: list[tuple[str, str]] = []

    for css in selectors:
        for a in soup.select(css):
            href = (a.get("href") or "").strip()
            text = clean_text(a.get_text(" ").strip())
            if not href or not text:
                continue
            if href.startswith("#"):
                continue
            link = urljoin(url, href)
            found.append((text, link))
        if len(found) >= limit:
            break

    return dedupe_by_url(found)[:limit]

# ----------------------- EMM Radar -----------------------

def load_emm_radar(json_path: str = EMM_RADAR_JSON,
                   lookback_hours: int = EMM_RADAR_LOOKBACK_HOURS,
                   limit: int = 20) -> list[dict]:
    """
    Legge il JSON creato da scripts/emm_radar.R:
      [{"title","description","url","source","language","date"}]
    Filtra per le ultime N ore e ordina per data desc.
    """
    if not os.path.exists(json_path):
        logging.info("EMM Radar: JSON non trovato, salto sezione.")
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.warning(f"EMM Radar: JSON non leggibile ({e}), salto.")
        return []

    # normalizza e filtra timeframe
    now = now_tz()
    earliest = now - timedelta(hours=lookback_hours)
    items = []

    for it in data:
        try:
            title = clean_text(it.get("title", ""))
            url = it.get("url", "").strip()
            source = clean_text(it.get("source", ""))
            lang = (it.get("language") or "").strip()
            datestr = it.get("date", "")
            # date può essere ISO o RFC; proviamo parse semplice
            dt = None
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %Z"):
                try:
                    dt = datetime.strptime(datestr, fmt)
                    break
                except Exception:
                    continue
            if dt is None:
                # tentativo: senza tz
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        dt = datetime.strptime(datestr, fmt)
                        break
                    except Exception:
                        continue
            if dt is None:
                continue

            if pytz and dt.tzinfo is None:
                dt = pytz.timezone(TZ_NAME).localize(dt)

            if dt < earliest:
                continue

            items.append({
                "title": title,
                "url": url,
                "source": source,
                "language": lang,
                "date": dt,
            })
        except Exception:
            continue

    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:limit]

def render_emm_radar_md(items: list[dict], title: str = EMM_RADAR_TITLE) -> str:
    if not items:
        return ""
    lines = [f"## {title}", ""]
    for it in items:
        t = it["title"]
        u = it["url"]
        src = it.get("source") or ""
        lang = it.get("language") or ""
        dt = it["date"]
        when = dt.strftime("%d %b %Y, %H:%M %Z") if dt.tzinfo else dt.strftime("%d %b %Y, %H:%M")
        meta_bits = [b for b in [src, lang.upper() if lang else None, when] if b]
        meta = " · ".join(meta_bits)
        lines.append(f"- [{t}]({u})  \n  _{meta}_")
    lines.append("")
    return "\n".join(lines)

# ----------------------- Build digest -----------------------

def build_section_md(label: str, items: list[tuple[str, str]]) -> str:
    if not items:
        return ""
    out = [f"## {label}", ""]
    for title, link in items:
        out.append(f"- [{title}]({link})")
    out.append("")
    return "\n".join(out)

def build_digest_md(feeds_cfg: list[dict]) -> str:
    dt = now_tz()
    header = [
        "# Daily EU/Tunisia Digest",
        "",
        f"*Generato: {fmt_generated(dt)}*",
        "",
    ]

    # EMM Radar (se disponibile)
    emm_items = load_emm_radar()
    emm_md = render_emm_radar_md(emm_items)
    if emm_md:
        header.append(emm_md)

    body_sections = []
    for feed in feeds_cfg:
        label = feed["label"]
        tipo = feed["type"]
        url = feed["url"]

        try:
            if tipo == "rss":
                items = parse_rss(url, PER_SECTION_LIMIT)
            elif tipo == "html":
                items = parse_html_links(url, PER_SECTION_LIMIT)
            else:
                logging.warning(f"Tipo non supportato '{tipo}' per {label} -> {url}")
                items = []
        except Exception as e:
            logging.warning(f"Errore parsing {label}: {e}")
            items = []

        sec_md = build_section_md(label, items)
        if sec_md:
            body_sections.append(sec_md)

    parts = header + body_sections
    return "\n".join(parts).strip() + "\n"

# ----------------------- Main -----------------------

def main():
    feeds_cfg = load_feeds_config("feeds.txt")
    md = build_digest_md(feeds_cfg)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    logging.info(f"Digest scritto in {OUTPUT_MD} ({len(md)} chars)")

if __name__ == "__main__":
    main()


