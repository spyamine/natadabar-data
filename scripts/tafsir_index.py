"""Ayah index for verse-ordered tafsir books.

islamweb tafsir pages link every quoted verse with explicit surah/ayah data (scraped into verse_references,
in document order). A passage's *head* is the first quote on a page that keeps the walk moving forward in the
current surah; passages run from one head to the next. The result, `ayah_index(surah, ayah, first_entry_id,
last_entry_id)`, answers "which pages explain this ayah" for all 6,236 ayahs the book covers.
"""
import json
import re
from pathlib import Path

from common import ROOT, normalize

SURAHS = json.loads((ROOT / "data" / "surahs.json").read_text())
AYAHS = {s["n"]: s["ayahs"] for s in SURAHS}
MAX_JUMP = 40        # a head may move at most this many ayahs ahead of the previous head
NEXT_SURAH_MAX = 8   # ...or open a later surah at one of its first ayahs

_ALIASES = {1: ["فاتحه الكتاب", "ام القران", "الحمد", "ام الكتاب"], 17: ["الاسراء", "بني اسرائيل"], 9: ["براءه", "التوبه"],
            40: ["غافر", "المومن"], 41: ["فصلت", "حم السجده"], 47: ["محمد", "القتال"], 76: ["الانسان", "الدهر"], 114: ["الناس"]}


def _name_table():
    table = {}
    for s in SURAHS:
        names = [normalize(s["name_ar"])] + _ALIASES.get(s["n"], [])
        for n in names:
            table[n.replace("ة", "ه")] = s["n"]
    return table


NAMES = _name_table()


def surah_hint(title: str):
    """Surah number named in a section title such as 'تفسير سورة آل عمران', else None."""
    words = normalize(title).split()
    for i, w in enumerate(words):
        if w == "سوره":
            rest = words[i + 1:i + 4]
            for k in range(len(rest), 0, -1):  # longest name first
                n = NAMES.get(" ".join(rest[:k]))
                if n:
                    return n
    return None


def build_index(pages, conn):
    """pages: [(entry_id, section_title, section_first_page_flag, [(surah, ayah), ...])] in book order.
    Writes ayah_index into conn; returns stats."""
    conn.execute("CREATE TABLE IF NOT EXISTS ayah_index (surah INTEGER, ayah INTEGER, first_entry_id INTEGER, "
                 "last_entry_id INTEGER, PRIMARY KEY (surah, ayah))")
    surah, head = 0, 0
    heads = []  # (surah, ayah, first_entry_id)
    rejected = 0
    # Books whose sections name their surah settle the surah from the TOC; others (volumes, topics) follow the quotes.
    hinted = any(surah_hint(title) for _, title, first, _ in pages if first)
    for entry_id, title, section_start, refs in pages:
        if section_start:
            hint = surah_hint(title)
            if hint and hint >= surah:
                surah, head = hint, 1
                if not heads or heads[-1][:2] != (surah, 1):
                    heads.append((surah, 1, entry_id))
        for i, (s, a) in enumerate(refs):
            if s == surah and head <= a <= head + MAX_JUMP:
                if a != head or not heads:
                    heads.append((surah, a, entry_id))
                head = a
                break
            # A new surah opens at its first ayahs: always trusted without hints; with hints only for the next
            # surah, as the first quote on the page (a section may cover several short surahs).
            opens = (s == surah + 1 and a <= 3 and i == 0) if hinted else (surah < s <= surah + 1 and a <= NEXT_SURAH_MAX and i == 0)
            if opens and (surah >= 1 or not hinted):
                surah, head = s, a
                heads.append((surah, a, entry_id))
                break
        else:
            rejected += 1 if refs else 0
    last_entry = pages[-1][0] if pages else 0
    # collapse to passages: consecutive heads with the same (surah, ayah) were already merged above
    passages = []
    for i, (s, a, first) in enumerate(heads):
        nxt_first = heads[i + 1][2] if i + 1 < len(heads) else last_entry + 1
        passages.append((s, a, first, max(first, nxt_first - 1) if nxt_first > first else first))
    rows = {}
    by_surah = {}
    for p in passages:
        by_surah.setdefault(p[0], []).append(p)
    for s, ps in by_surah.items():
        ps.sort(key=lambda p: (p[1], p[2]))
        for i, (_, a, first, last) in enumerate(ps):
            start = 1 if i == 0 else a
            end = ps[i + 1][1] - 1 if i + 1 < len(ps) else AYAHS[s]
            for ayah in range(start, max(start, end) + 1):
                if ayah <= AYAHS[s]:
                    rows[(s, ayah)] = (first, last)
    conn.executemany("INSERT OR REPLACE INTO ayah_index VALUES (?,?,?,?)", [(s, a, f, l) for (s, a), (f, l) in rows.items()])
    covered = len(rows)
    surahs = len(by_surah)
    return {"passages": len(passages), "ayahs_covered": covered, "surahs_covered": surahs, "pages_without_head": rejected}
