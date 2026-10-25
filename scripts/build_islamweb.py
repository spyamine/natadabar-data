#!/usr/bin/env python3
"""Convert a finished islamweb-scraper DB into the standard schema.

    python3 scripts/build_islamweb.py <bk_no> [<bk_no> ...]

Input DBs live in ~/Developer/islamweb-scraper/output/<db_name>.db (db_name from work/islamweb_queue.txt).
islamweb "books" (the sidebar divisions: كتاب/أبواب) become chapters; entries before the first division
become the intro. Sub-chapters (باب) stay inside the entry text, one level below the book as agreed.
"""
import json
import sqlite3
import sys
from pathlib import Path

from common import DBS, ROOT, create_db, finalize, normalize, update_manifest

SRC = Path.home() / "Developer" / "islamweb-scraper" / "output"


def queue():
    out = {}
    for line in "\n".join(f.read_text() for f in sorted((ROOT / "work").glob("islamweb_queue*.txt"))).split("\n"):
        if line.strip():
            bk, name = line.split()
            out[int(bk)] = name
    return out


def open_source(name):
    """The scraper DB for `name`; if range-worker parts (`name_p1.db` ...) exist, merge them (dedupe by page)."""
    parts = sorted(SRC.glob(f"{name}_p[0-9]*.db"))
    if not parts:
        return sqlite3.connect(SRC / f"{name}.db")
    mem = sqlite3.connect(":memory:")
    mem.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY, book_number INTEGER, name TEXT);
        CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_number INTEGER, book_id INTEGER,
            page_number INTEGER UNIQUE, text_clean TEXT, text_vocalized TEXT);
        CREATE TABLE verse_references (entry_id INTEGER, surah_number INTEGER, ayah_number INTEGER);
    """)
    base = SRC / f"{name}.db"
    for path in parts + ([base] if base.exists() else []):
        c = sqlite3.connect(path)
        try:
            mem.executemany("INSERT OR IGNORE INTO books VALUES (?,?,?)", c.execute("SELECT id, book_number, name FROM books"))
            for eid, num, bid, page, tc, tv in c.execute(
                "SELECT id, entry_number, book_id, page_number, text_clean, text_vocalized FROM entries ORDER BY page_number"
            ):
                cur = mem.execute("INSERT OR IGNORE INTO entries(entry_number,book_id,page_number,text_clean,text_vocalized) "
                                  "VALUES (?,?,?,?,?)", (num, bid, page, tc, tv))
                if cur.rowcount:
                    mem.executemany("INSERT INTO verse_references VALUES (?,?,?)",
                                    [(cur.lastrowid, a, b) for a, b in c.execute(
                                        "SELECT surah_number, ayah_number FROM verse_references WHERE entry_id=?", (eid,))])
        except sqlite3.Error as e:
            print("skip part", path.name, e)
        c.close()
    mem.commit()
    return mem


def build(bk_no, book):
    name = queue()[bk_no]
    src = open_source(name)
    path = DBS / f"{book['id']}.db"
    conn = create_db(path)
    conn.execute(
        "INSERT INTO books VALUES (1,?,?,?,?,?,?,?,?,?)",
        (book["id"], book["title_ar"] or book["title_en"], book.get("author_ar"), book.get("death_ah"),
         book["category"], "islamweb", book["source_ref"], "islamweb.net library", book["license"]),
    )
    ord_ = 0
    sec_for = {}  # islamweb book_id (None for intro) -> our section id
    sections = [(None, "المقدمة", "intro")] + [
        (r[0], r[1], "chapter") for r in src.execute("SELECT id, name FROM books ORDER BY book_number, id")
    ]
    has_intro = src.execute("SELECT COUNT(*) FROM entries WHERE book_id IS NULL").fetchone()[0] > 0
    for wid, title, kind in sections:
        if wid is None and not has_intro:
            continue
        ord_ += 1
        cur = conn.execute("INSERT INTO sections(book_id,ordinal,kind,title) VALUES (1,?,?,?)", (ord_, kind, title.strip()))
        sec_for[wid] = cur.lastrowid
    seq_in = {}
    ent_map = {}
    for eid, num, wid, page, tclean, tvoc in src.execute(
        "SELECT id, entry_number, book_id, page_number, text_clean, text_vocalized FROM entries ORDER BY page_number, id"
    ):
        sid = sec_for.get(wid)
        if sid is None:
            continue
        seq_in[sid] = seq_in.get(sid, 0) + 1
        text = tvoc or tclean
        cur = conn.execute(
            "INSERT INTO entries(book_id,section_id,seq,number,page,text_clean,text_vocalized) VALUES (1,?,?,?,?,?,?)",
            (sid, seq_in[sid], num, page, normalize(tclean or text), text),
        )
        ent_map[eid] = cur.lastrowid
    for eid, s, a in src.execute("SELECT entry_id, surah_number, ayah_number FROM verse_references"):
        if eid in ent_map:
            conn.execute("INSERT INTO verse_references(entry_id,surah,ayah) VALUES (?,?,?)", (ent_map[eid], s, a))
    entry = finalize(conn, path)
    entry.update(title_ar=book["title_ar"], title_en=book["title_en"], category=book["category"],
                 source=book["source"], source_ref=book["source_ref"], license=book["license"])
    update_manifest(book["id"], entry)
    return entry


if __name__ == "__main__":
    catalog = json.loads((ROOT / "catalog" / "books.json").read_text())
    by_bk = {int(b["source_ref"].split("=")[1]): b for b in catalog if b["source"] == "islamweb"}
    for bk in map(int, sys.argv[1:]):
        e = build(bk, by_bk[bk])
        print(f'{by_bk[bk]["id"]}: {e["sections"]} sections, {e["entries"]} entries, {e["deflate_bytes"]//1024} KB')
