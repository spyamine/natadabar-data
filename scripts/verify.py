#!/usr/bin/env python3
"""Sanity-check every built DB in work/dbs: integrity, schema, FTS, ordering, intro placement."""
import sqlite3
import sys
from pathlib import Path

DBS = Path(__file__).resolve().parent.parent / "work" / "dbs"
bad = 0
for p in sorted(DBS.glob("*.db")):
    c = sqlite3.connect(p)
    problems = []
    if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        problems.append("integrity")
    if c.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
        problems.append("journal not DELETE")
    n_sec, n_ent = (c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("sections", "entries"))
    if not n_sec or not n_ent:
        problems.append("empty")
    if c.execute("SELECT COUNT(*) FROM entries WHERE section_id NOT IN (SELECT id FROM sections)").fetchone()[0]:
        problems.append("orphan entries")
    if c.execute("SELECT COUNT(*) FROM sections WHERE kind='intro' AND ordinal>3").fetchone()[0]:
        problems.append("late intro")
    if c.execute("SELECT COUNT(*) FROM entries WHERE LENGTH(text_clean)=0").fetchone()[0]:
        problems.append("blank entries")
    hits = c.execute("SELECT COUNT(*) FROM entry_fts WHERE entry_fts MATCH 'الله'").fetchone()[0]
    longest = c.execute("SELECT MAX(LENGTH(text_vocalized)) FROM entries").fetchone()[0]
    if longest > 15000:
        problems.append(f"entry too long ({longest})")
    print(f'{"FAIL" if problems else "ok  "} {p.stem:46} {n_sec:5} sec {n_ent:6} ent  fts("الله")={hits:5}  {", ".join(problems)}')
    bad += bool(problems)
sys.exit(1 if bad else 0)
