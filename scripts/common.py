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
    seq INTEGER NOT NULL, number INTEGER, part INTEGER, page INTEGER, headword TEXT, lead TEXT,
    text_clean TEXT NOT NULL, text_vocalized TEXT NOT NULL);
CREATE TABLE verse_references (id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL, surah INTEGER,
    ayah INTEGER, ayah_end INTEGER, start_offset INTEGER, end_offset INTEGER);
CREATE INDEX idx_entries_section ON entries(section_id, seq);
CREATE INDEX idx_entries_book ON entries(book_id, seq);
CREATE INDEX idx_entries_lead ON entries(lead);
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


_LEAD_JUNK = re.compile(r"^[^\u0621-\u064A]+")


def lead_of(text_clean: str, n: int = 2) -> str:
    """First n words of an entry, normalized: lets an app look up entries that begin with a tapped word
    (dictionaries whose headword is simply the first word, with no delimiter)."""
    return " ".join(_LEAD_JUNK.sub("", text_clean).split()[:n])


_BAB_HEAD = re.compile(r"^(?:\(\s*\d+\s*\)|\d+\s*-)?\s*\(?باب\b")
_LEAD_NUM = re.compile(r"^\D{0,3}(\d{1,6})\b")
_BAB_TITLE_END = re.compile(r"\s+(?:\d+|قال الله|قال تعالى|قال العلماء|وعن |حدثنا|أخبرنا)\b|[:：]")


def bab_title(text: str, maxlen: int = 90) -> str:
    t = re.sub(r"^(?:\(\s*\d+\s*\)|\d+\s*-)\s*", "", text.strip())
    t = re.sub(r"^\(|\)", "", t)
    m = _BAB_TITLE_END.search(t, 8)
    t = t[:m.start()] if m else t
    if len(t) > maxlen:
        t = t[:maxlen].rsplit(" ", 1)[0] + "…"
    return t.strip()


def split_big_sections(conn, limit: int = 300, min_heads: int = 8, min_part: int = 6):
    """Hadith books keep a whole كتاب in one section; a 1,000-hadith كتاب الصلاة is unreadable. Cut sections
    longer than `limit` entries at the entries that open a باب, titling each part "كتاب X — باب Y".
    Sections without باب heads stay whole (nothing reliable to cut at)."""
    for sid, title in conn.execute("SELECT id, title FROM sections ORDER BY ordinal").fetchall():
        rows = conn.execute("SELECT id, text_vocalized FROM entries WHERE section_id=? ORDER BY seq", (sid,)).fetchall()
        heads = [i for i, (_, t) in enumerate(rows) if _BAB_HEAD.match(t or "")]
        if len(rows) <= limit or len(heads) < min_heads:
            continue
        cuts = sorted(set([0] + heads))
        parts = [(cuts[k], cuts[k + 1] if k + 1 < len(cuts) else len(rows)) for k in range(len(cuts))]
        merged = []   # runs of one-hadith abwab would give hundreds of near-empty sections: join them up to min_part
        for a, b in parts:
            if merged and merged[-1][1] - merged[-1][0] < min_part:
                merged[-1][1] = b
                merged[-1][2].append(a)
            else:
                merged.append([a, b, [a]])
        parts = [(a, b, heads_in) for a, b, heads_in in merged]
        extra = title == "أبواب متنوعة"
        ordinal_shift = len(parts) - 1
        conn.execute("UPDATE sections SET ordinal = ordinal + ? WHERE ordinal > (SELECT ordinal FROM sections WHERE id=?)",
                     (ordinal_shift, sid))
        base = conn.execute("SELECT ordinal FROM sections WHERE id=?", (sid,)).fetchone()[0]
        for k, (a, b, heads_in) in enumerate(parts):
            first = [h for h in heads_in if h in heads]
            head = bab_title(rows[first[0]][1]) if first else ""
            if len(first) > 1:
                head += " …"
            ttl = head or title if extra or not head else f"{title} — {head}"
            if k == 0:
                conn.execute("UPDATE sections SET title=? WHERE id=?", (ttl, sid))
                new_id = sid
            else:
                new_id = conn.execute("INSERT INTO sections(book_id,ordinal,kind,title) VALUES (1,?,?,?)",
                                      (base + k, "chapter", ttl)).lastrowid
            for seq, (eid, _) in enumerate(rows[a:b], 1):
                conn.execute("UPDATE entries SET section_id=?, seq=? WHERE id=?", (new_id, seq, eid))
    chunk_big_sections(conn)
    conn.commit()


def chunk_big_sections(conn, limit: int = 600, size: int = 400):
    """Sections still over `limit` entries (no باب heads to cut at, e.g. Musnad Ahmad): cut into runs of ~`size`
    entries titled by the hadith numbers they span."""
    for sid, title in conn.execute("SELECT id, title FROM sections ORDER BY ordinal").fetchall():
        rows = conn.execute("SELECT id, text_vocalized FROM entries WHERE section_id=? ORDER BY seq", (sid,)).fetchall()
        if len(rows) <= limit:
            continue
        parts = -(-len(rows) // size)
        step = -(-len(rows) // parts)
        chunks = [rows[i:i + step] for i in range(0, len(rows), step)]
        conn.execute("UPDATE sections SET ordinal = ordinal + ? WHERE ordinal > (SELECT ordinal FROM sections WHERE id=?)",
                     (len(chunks) - 1, sid))
        base = conn.execute("SELECT ordinal FROM sections WHERE id=?", (sid,)).fetchone()[0]
        for k, chunk in enumerate(chunks):
            a, b = (_LEAD_NUM.match(chunk[0][1] or ""), _LEAD_NUM.match(chunk[-1][1] or ""))
            span = f"الأحاديث {a.group(1)}–{b.group(1)}" if a and b else f"الجزء {k + 1}"
            ttl = f"{title} — {span}"
            if k == 0:
                conn.execute("UPDATE sections SET title=? WHERE id=?", (ttl, sid))
                new_id = sid
            else:
                new_id = conn.execute("INSERT INTO sections(book_id,ordinal,kind,title) VALUES (1,?,?,?)",
                                      (base + k, "chapter", ttl)).lastrowid
            for seq, (eid, _) in enumerate(chunk, 1):
                conn.execute("UPDATE entries SET section_id=?, seq=? WHERE id=?", (new_id, seq, eid))


def finalize(conn: sqlite3.Connection, path: Path) -> dict:
    """Build FTS, section counts, VACUUM, then package as raw-deflate + sha256. Returns manifest entry."""
    conn.executemany("UPDATE entries SET lead=? WHERE id=?",
                     [(lead_of(t), i) for i, t in conn.execute("SELECT id, text_clean FROM entries").fetchall()])
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
