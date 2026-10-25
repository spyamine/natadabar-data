"""Shared helpers: normalization, standard schema, packaging."""
import hashlib
import json
import re
import sqlite3
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DBS = ROOT / "work" / "dbs"
RELEASE_TAG = "library-v1"

_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۤۧۨ-ۭـ]")


def normalize(text: str) -> str:
    """Search form: no diacritics/tatweel, unified alef, taa marbuta -> haa, alef maqsura -> yaa."""
    text = _DIACRITICS.sub("", text)
    for a in "آأإٱ":
        text = text.replace(a, "ا")
    return text.replace("ة", "ه").replace("ى", "ي")


SCHEMA = """
CREATE TABLE books (id INTEGER PRIMARY KEY, slug TEXT NOT NULL, title_ar TEXT NOT NULL, author_ar TEXT,
    death_ah INTEGER, category TEXT, source TEXT, source_ref TEXT, edition TEXT, license TEXT);
CREATE TABLE sections (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('intro','chapter')), title TEXT NOT NULL,
    first_entry_id INTEGER, entry_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE entries (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL, section_id INTEGER NOT NULL,
    seq INTEGER NOT NULL, number INTEGER, part INTEGER, page INTEGER, headword TEXT,
    text_clean TEXT NOT NULL, text_vocalized TEXT NOT NULL);
CREATE TABLE verse_references (id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL, surah INTEGER,
    ayah INTEGER, ayah_end INTEGER, start_offset INTEGER, end_offset INTEGER);
CREATE INDEX idx_entries_section ON entries(section_id, seq);
CREATE INDEX idx_entries_book ON entries(book_id, seq);
CREATE INDEX idx_entries_headword ON entries(headword) WHERE headword IS NOT NULL;
CREATE INDEX idx_sections_book ON sections(book_id, ordinal);
CREATE INDEX idx_verses_entry ON verse_references(entry_id);
"""


def create_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript("PRAGMA journal_mode=DELETE;" + SCHEMA)
    return conn


def finalize(conn: sqlite3.Connection, path: Path) -> dict:
    """Build FTS, section counts, VACUUM, then package as raw-deflate + sha256. Returns manifest entry."""
    conn.executescript("""
        UPDATE sections SET
          first_entry_id = (SELECT MIN(id) FROM entries e WHERE e.section_id = sections.id),
          entry_count = (SELECT COUNT(*) FROM entries e WHERE e.section_id = sections.id);
        CREATE VIRTUAL TABLE entry_fts USING fts5(text_clean, content='entries', content_rowid='id', tokenize='unicode61');
        INSERT INTO entry_fts(entry_fts) VALUES('rebuild');
    """)
    conn.commit()
    stats = {
        "sections": conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0],
        "entries": conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
        "chars": conn.execute("SELECT COALESCE(SUM(LENGTH(text_clean)),0) FROM entries").fetchone()[0],
    }
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.close()
    c = sqlite3.connect(path)
    c.execute("VACUUM")
    c.close()
    raw = path.read_bytes()
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate, as TafsirDownloadService expects
    data = comp.compress(raw) + comp.flush()
    DIST.mkdir(exist_ok=True)
    out = DIST / (path.name + ".deflate")
    out.write_bytes(data)
    return {
        "file": out.name, "db_bytes": len(raw), "deflate_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(), "sha256_db": hashlib.sha256(raw).hexdigest(), **stats,
    }


def update_manifest(slug: str, entry: dict):
    mp = DIST / "manifest.json"
    m = json.loads(mp.read_text()) if mp.exists() else {}
    entry["download_url"] = f"https://github.com/spyamine/natadabar-data/releases/download/{RELEASE_TAG}/{entry['file']}"
    m[slug] = entry
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True))
