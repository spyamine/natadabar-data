#!/usr/bin/env python3
"""Build a standard-schema DB from an OpenITI mARkdown text.

    python3 scripts/build_openiti.py <catalog id> [<catalog id> ...]

Sections: `### |` headings if the text has them, else `# |` headings, else one section.
Content before the first heading (or headings such as مقدمة/توطئة) becomes kind='intro'.
Entries are paragraph groups of ~TARGET chars (never splitting a paragraph); for dictionaries
(category 'dictionary') each detected headword starts a new entry.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

from common import DBS, ROOT, create_db, finalize, normalize, update_manifest

TARGET = 1400
CACHE = ROOT / "work" / "openiti"
INTRO_RE = re.compile(r"^(مقدمة|المقدمة|توطئة|تمهيد|خطبة|بسم الله|مدخل|فاتحة)")
NOISE = re.compile(r"PageV\d+P\d+|\bms\d+\b|@[A-Z]+@|%~%|\$[A-Z_]+\$|\bAUTO\b|ms\d+")
PAGE = re.compile(r"PageV(\d+)P(\d+)")
ARABIC_WORD = re.compile(r"^[\u0621-\u065F\u0671-\u06D3]{2,8}$")
COLON_HEAD = re.compile(r"^([\u0621-\u065F\u0671-\u06D3]{1,14}) : ")


# Per-book overrides. heading_filter: only headings matching it become sections.
# verse_re: lines marking a verse ("### || [s.a]"); no_group: one entry per paragraph.
LETTER_SPLIT = {"0502raghibisbahani_mufradat"}
BOOK_CFG = {
    "0276ibnqutaybadinawari_gharibquran": dict(heading_filter=r"^(باب|مقدمة|كتاب|سورة)", no_group=True),
    "0330ibncuzayzsijistani_gharibquran": dict(verse_re=r"^### \|\| \[(\d+)\.(\d+)\]", no_group=True,
                                              headword_re=r"^\{ ?(.+?) ?\}"),
}
LETTERS = "الألف|الباء|التاء|الثاء|الجيم|الحاء|الخاء|الدال|الذال|الراء|الزاي|السين|الشين|الصاد|الضاد|الطاء|الظاء|العين|الغين|الفاء|القاف|الكاف|اللام|الميم|النون|الواو|الهاء|الياء"
LETTER_MARK = re.compile(r"=\s*كتاب(?:\s|~~)+(" + LETTERS + r")(?:\s*=)?|(?<![ء-ي])كتاب (" + LETTERS + r") =")
INLINE_BOOK = re.compile(r"=\s*(كتاب [^=]{1,25}?)\s*=")


def fetch(book):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (book["id"] + ".txt")
    if not p.exists():
        p.write_bytes(urllib.request.urlopen(book["source_url"]).read())
    return p.read_text(encoding="utf8")


def header(text):
    meta = {}
    for m in re.finditer(r"^#META# (\S+)\s+:: (.*)$", text, re.M):
        meta[m.group(1)] = m.group(2).strip()
    edition = " | ".join(v for k, v in meta.items() if k.startswith("04") and v != "NODATA")
    return meta, edition


def clean(s):
    s = NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_long(txt, limit=2200, target=1400):
    """Split an over-long paragraph at sentence ends (. ؟ ؛ !) after ~target chars."""
    out = []
    while len(txt) > limit:
        m = re.search(r"[.؟!؛] ", txt[target:limit + 600])
        if not m:
            break
        cut = target + m.end()
        out.append(txt[:cut].strip())
        txt = txt[cut:].strip()
    if txt:
        out.append(txt)
    return out


def parse(body, heading_re, heading_filter=None, verse_re=None):
    """Yield ('heading', title) / ('para', text, part, page) events."""
    events, cur, part, page, cur_pos = [], [], 0, 0, (0, 0)

    def flush():
        nonlocal cur
        if cur:
            txt = clean(" ".join(cur))
            for piece in split_long(txt):
                events.append(("para", piece, cur_pos[0], cur_pos[1]))
            cur = []

    for line in body.split("\n"):
        m = PAGE.search(line)
        if m:
            part, page = int(m.group(1)), int(m.group(2))
        if line.startswith("~~"):
            cur.append(line[2:])
            continue
        if verse_re:
            vm = verse_re.match(line)
            if vm:
                flush()
                events.append(("verse", int(vm.group(1)), int(vm.group(2))))
                continue
        ib = INLINE_BOOK.search(line)
        if ib and heading_re and line.startswith("# "):
            flush()
            events.append(("heading", clean(ib.group(1))))
            continue
        h = heading_re.match(line) if heading_re else None
        if h:
            flush()
            title = clean(h.group(1))
            if title and (not heading_filter or heading_filter.search(title)):
                events.append(("heading", title))
            continue
        if line.startswith("# ") or line.startswith("### "):
            flush()
            cur_pos = (part, page)
            cur = [re.sub(r"^#+ \|*\s*", "", line)]
            continue
        if line.strip() == "":
            continue
    flush()
    return events


def build(book, rows_cat):
    text = fetch(book)
    meta, edition = header(text)
    body = text.split("#META#Header#End#")[-1]
    heading_re = None
    if book["id"] in LETTER_SPLIT:
        body = LETTER_MARK.sub(lambda m: "\n# | كتاب " + (m.group(1) or m.group(2)) + "\n# ", body)
    if re.search(r"^### \|", body, re.M):
        heading_re = re.compile(r"^### \|(?!\|)\s*(.*)$")
    elif len(re.findall(r"^# \| (?!PageV)\S", body, re.M)) >= 3:
        heading_re = re.compile(r"^# \| (?!PageV\d+P\d+\s*$)(.*)$")
    if heading_re is None and len(INLINE_BOOK.findall(body)) >= 3:
        heading_re = re.compile(r"^\x00$")  # sections come from inline "= كتاب X =" markers only
    cfg = BOOK_CFG.get(book["id"], {})
    hf = re.compile(cfg["heading_filter"]) if "heading_filter" in cfg else None
    vre = re.compile(cfg["verse_re"]) if "verse_re" in cfg else None
    hre = re.compile(cfg["headword_re"]) if "headword_re" in cfg else None
    events = parse(body, heading_re, hf, vre)
    no_group = cfg.get("no_group", False)
    n_heads = sum(1 for e in events if e[0] == "para" and (COLON_HEAD.match(e[1]) or ARABIC_WORD.match(e[1])))
    is_dict = book["category"] == "dictionary" and n_heads >= 100
    path = DBS / (book["id"] + ".db")
    conn = create_db(path)
    conn.execute(
        "INSERT INTO books VALUES (1,?,?,?,?,?,?,?,?,?)",
        (book["id"], book["title_ar"], book["author_ar"], book.get("death_ah"), book["category"],
         "openiti", book["source_ref"], edition, book["license"]),
    )
    sections, ordinal, seq, sec_id, buf, buf_pos, eid = 0, 0, 0, None, [], (0, 0), 0
    sec_intro_possible = True
    cur_verse = None

    def new_section(title, kind):
        nonlocal sections, ordinal, sec_id, seq
        flush_buf()
        ordinal += 1
        cur = conn.execute("INSERT INTO sections(book_id,ordinal,kind,title) VALUES (1,?,?,?)", (ordinal, kind, title))
        sec_id, seq = cur.lastrowid, 0

    def flush_buf(headword=None):
        nonlocal buf, seq
        if not buf:
            return
        txt = " ".join(buf)
        seq += 1
        cur = conn.execute(
            "INSERT INTO entries(book_id,section_id,seq,part,page,headword,text_clean,text_vocalized) VALUES (1,?,?,?,?,?,?,?)",
            (sec_id, seq, buf_pos[0] or None, buf_pos[1] or None, buf_head[0], normalize(txt), txt),
        )
        if cur_verse:
            conn.execute("INSERT INTO verse_references(entry_id,surah,ayah) VALUES (?,?,?)", (cur.lastrowid, *cur_verse))
        buf = []
        buf_head[0] = None

    buf_head = [None]
    for ev in events:
        if ev[0] == "verse":
            flush_buf()
            cur_verse = (ev[1], ev[2])
            continue
        if ev[0] == "heading":
            kind = "intro" if (sec_intro_possible and INTRO_RE.match(ev[1])) else "chapter"
            if kind == "chapter":
                sec_intro_possible = False
            new_section(ev[1], kind)
            continue
        _, txt, part, page = ev
        if sec_id is None:
            new_section("المقدمة" if heading_re else book["title_ar"], "intro" if heading_re else "chapter")
        ch = COLON_HEAD.match(txt) if is_dict else None
        if ch:
            flush_buf()
            buf_head[0] = ch.group(1)
            buf, buf_pos = [txt], (part, page)
            continue
        if is_dict and ARABIC_WORD.match(txt):
            flush_buf()
            buf_head[0] = txt
            buf, buf_pos = [txt], (part, page)
            continue
        if not buf:
            buf_pos = (part, page)
            if hre and (hm := hre.match(txt)):
                buf_head[0] = hm.group(1)
        buf.append(txt)
        if no_group or (not is_dict and sum(len(x) for x in buf) >= TARGET):
            flush_buf()
    flush_buf()
    entry = finalize(conn, path)
    entry.update(title_ar=book["title_ar"], title_en=book["title_en"], category=book["category"],
                 source=book["source"], source_ref=book["source_ref"], license=book["license"])
    update_manifest(book["id"], entry)
    return entry


if __name__ == "__main__":
    catalog = json.loads((ROOT / "catalog" / "books.json").read_text())
    by_id = {b["id"]: b for b in catalog}
    for bid in sys.argv[1:]:
        e = build(by_id[bid], None)
        print(f'{bid}: {e["sections"]} sections, {e["entries"]} entries, {e["chars"]//1000}k chars, {e["deflate_bytes"]//1024} KB')
