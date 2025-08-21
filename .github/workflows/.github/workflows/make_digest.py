
import argparse, feedparser, datetime, sys, pathlib
from dateutil import tz

def read_feeds(feed_list_path, max_items_per_feed=10):
    feeds = []
    for line in pathlib.Path(feed_list_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        feeds.append(line)

    items = []
    for url in feeds:
        d = feedparser.parse(url)
        for e in d.entries[:max_items_per_feed]:
            title = getattr(e, "title", "").replace("\n"," ").strip()
            link = getattr(e, "link", "").strip()
            published = getattr(e, "published", "") or getattr(e, "updated", "")
            items.append({"title": title, "link": link, "published": published, "source": url})
    # sort by published (best-effort)
    def key(it):
        return it.get("published","")
    items.sort(key=key, reverse=True)
    return items

def to_markdown(items, out_path):
    today = datetime.datetime.utcnow().date().isoformat()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Daily Digest — {today} (UTC)\n\n")
        for it in items[:120]:
            t = it["title"] or "(no title)"
            f.write(f"- {t}\n  {it['link']}\n\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", default="feeds.txt")
    ap.add_argument("--max-per-feed", type=int, default=10)
    ap.add_argument("--out", default="digest.md")
    args = ap.parse_args()
    items = read_feeds(args.feeds, args.max_per_feed)
    to_markdown(items, args.out)
    print(f"Wrote {args.out} with {len(items)} items (max-per-feed={args.max_per_feed}).")
