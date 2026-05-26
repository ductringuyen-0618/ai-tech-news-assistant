"""Quick RSS reachability probe for the five default sources.

Used to identify which feed is failing when ``/health/detailed`` reports
``Feeds accessible: N/5``. Runs feedparser against each URL and prints
the HTTP status + bozo flag + entry count.

Run from ``backend/`` either locally or on Fly via
``flyctl ssh console -C 'python scripts/probe_feeds.py'``.
"""
from __future__ import annotations

import feedparser

FEEDS = [
    ("O'Reilly Radar",        "https://feeds.feedburner.com/oreilly/radar"),
    ("TechCrunch",            "https://techcrunch.com/feed/"),
    ("Ars Technica",          "https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge",             "https://www.theverge.com/rss/index.xml"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
]


def main() -> int:
    failures = 0
    for name, url in FEEDS:
        parsed = feedparser.parse(url)
        status = getattr(parsed, "status", "n/a")
        bozo = parsed.bozo
        entries = len(parsed.entries)
        ok = (not bozo) and (status == 200) and entries > 0
        mark = "OK " if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"{mark} {name:25} status={status:>4} bozo={int(bozo)} entries={entries:>3}  {url}")
        if bozo and getattr(parsed, "bozo_exception", None) is not None:
            print(f"     bozo_exception: {type(parsed.bozo_exception).__name__}: {parsed.bozo_exception}")
    print()
    print(f"Total failing: {failures}/{len(FEEDS)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
