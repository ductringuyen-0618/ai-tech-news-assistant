#!/usr/bin/env python3
"""Read-only readiness verdict for a TechPulse backend instance.

Exit 0 when the instance is worth driving, 1 when it is not.
Stdlib only, so it runs under any interpreter without an install step.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

TIMEOUT = 20


def get(base, path, parse=True):
    try:
        with urllib.request.urlopen(base + path, timeout=TIMEOUT) as r:
            if not parse:
                r.read()
                return r.status, None
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return None, {"error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://127.0.0.1:8000")
    ap.add_argument("--frontend", default="http://localhost:3000")
    ap.add_argument("--require-articles", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    base = args.backend.rstrip("/")
    checks = []

    status, body = get(base, "/health")
    checks.append(
        {
            "check": "backend_up",
            "ok": status == 200,
            "detail": "GET /health status=%s" % status,
        }
    )
    if status != 200:
        return report(checks, args)

    status, detailed = get(base, "/health/detailed")
    comps = (detailed or {}).get("components", {})

    def comp(name):
        c = comps.get(name) or {}
        return c.get("status"), c.get("message")

    db_status, db_msg = comp("database")
    checks.append(
        {"check": "database", "ok": db_status == "healthy", "detail": db_msg}
    )

    news_status, news_msg = comp("news_service")
    checks.append(
        {"check": "feeds_reachable", "ok": news_status == "healthy", "detail": news_msg}
    )

    emb_status, emb_msg = comp("embedding_service")
    checks.append(
        {
            "check": "embeddings",
            "ok": True,
            "advisory": emb_status != "healthy",
            "detail": "%s (%s). Semantic search and the knowledge graph stay empty "
            "without this." % (emb_status, emb_msg),
        }
    )

    sum_status, sum_msg = comp("summarization_service")
    checks.append(
        {
            "check": "summarization",
            "ok": True,
            "advisory": sum_status != "healthy",
            "detail": "%s (%s). Summaries, digest and research stay empty without "
            "this." % (sum_status, sum_msg),
        }
    )

    ing_status, ing = get(base, "/api/ingest/stats")
    news_status_code, stats = get(base, "/api/news/stats")
    written = (ing or {}).get("total_articles")
    readable = ((stats or {}).get("data") or {}).get("total_articles")
    checks.append(
        {
            "check": "article_store_agreement",
            "ok": written == readable,
            "detail": "ingest store=%s, news read store=%s. A mismatch means the "
            "write path and the read path are on different databases; the UI feed "
            "renders empty no matter how much you ingest."
            % (written, readable),
        }
    )
    if args.require_articles:
        checks.append(
            {
                "check": "articles_readable",
                "ok": bool(readable),
                "detail": "GET /api/news/stats total_articles=%s" % readable,
            }
        )

    status, _ = get(args.frontend.rstrip("/"), "/", parse=False)
    checks.append(
        {
            "check": "frontend_up",
            "ok": True,
            "advisory": status != 200,
            "detail": "GET %s status=%s. Needed only for UI drives."
            % (args.frontend, status),
        }
    )

    return report(checks, args)


def report(checks, args):
    failed = [c for c in checks if not c["ok"]]
    advisory = [c for c in checks if c["ok"] and c.get("advisory")]
    if args.json:
        print(json.dumps({"ok": not failed, "checks": checks}, indent=2))
    else:
        for c in checks:
            mark = "FAIL" if not c["ok"] else ("WARN" if c.get("advisory") else "ok")
            print("[%4s] %-26s %s" % (mark, c["check"], c["detail"]))
        print()
        print(
            "verdict: %s (%d failed, %d degraded)"
            % ("DRIVE" if not failed else "DO NOT DRIVE", len(failed), len(advisory))
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
