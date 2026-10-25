#!/usr/bin/env python3
"""Show build progress for every tier-1 (or --all planned) book.   python3 scripts/progress.py [--tier N]"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path.home() / "Developer" / "islamweb-scraper" / "output"


def bar(frac, w=20):
    n = int(frac * w)
    return "█" * n + "░" * (w - n)


def main():
    tier = int(sys.argv[sys.argv.index("--tier") + 1]) if "--tier" in sys.argv else 1
    catalog = json.loads((ROOT / "catalog" / "books.json").read_text())
    mp = ROOT / "dist" / "manifest.json"
    manifest = json.loads(mp.read_text()) if mp.exists() else {}
    q = {}
    for line in "\n".join(f.read_text() for f in sorted((ROOT / "work").glob("islamweb_queue*.txt"))).split("\n"):
        if line.strip():
            bk, name = line.split()
            q[int(bk)] = name
    print(f'{"book":44} {"source":9} {"progress":30} result')
    done = total = 0
    for b in sorted(catalog, key=lambda b: (b["category"], b["title_en"])):
        if b["tier"] != tier:
            continue
        total += 1
        m = manifest.get(b["id"])
        frac, note = 0.0, "queued"
        if b["source"] == "islamweb":
            bk = int(b["source_ref"].split("=")[1])
            db = SRC / f"{q.get(bk, '')}.db"
            parts = sorted(SRC.glob(f"{q.get(bk, '')}_p[0-9]*.db"))
            if parts:
                tot = sqlite3.connect(parts[0]).execute("SELECT total_pages FROM scrape_progress").fetchone()[0]
                done_pages = sum(sqlite3.connect(x).execute("SELECT COUNT(*) FROM entries").fetchone()[0] for x in parts)
                frac, note = min(done_pages / max(tot, 1), 1), f"scraping {done_pages}/{tot} pages ({len(parts)} workers)"
                if frac >= 0.995:
                    frac, note = 1.0, "scraped"
            elif db.exists():
                try:
                    last, tot = sqlite3.connect(db).execute("SELECT last_page,total_pages FROM scrape_progress").fetchone()
                    frac, note = last / max(tot, 1), f"scraping {last}/{tot} pages"
                    if last >= tot:
                        note = "scraped"
                except (sqlite3.Error, TypeError):
                    note = "starting"
        if m and (b["source"] == "openiti" or frac >= 1):
            frac, note = 1.0, "built"
        if note == "built":
            done += 1
        res = f'{m["sections"]} sections, {m["entries"]} entries, {m["deflate_bytes"]//1024} KB' if m and note == "built" else ""
        print(f'{b["title_en"][:44]:44} {b["source"]:9} {bar(frac)} {frac*100:5.1f}% {note:24} {res}')
    print(f"\n{done}/{total} built (tier {tier})")


main()
