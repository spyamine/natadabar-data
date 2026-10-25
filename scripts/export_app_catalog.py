#!/usr/bin/env python3
"""Export catalog/library.json: the compact list the naTadabar app reads (bundled copy + remote refresh).

Joins catalog/books.json with catalog/manifest.json. Only books that are published and not already in the app.
Adding a book = build it, run this, push: the app picks it up on its next catalog refresh.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# islamweb books have no Arabic title in the catalog: bk_no -> (title_ar, author_ar, death_ah, kind)
ISLAMWEB = {
    402: ("رياض الصالحين", "النووي", 676, None), 2: ("سنن الترمذي", "الترمذي", 279, None),
    3: ("سنن النسائي", "النسائي", 303, None), 4: ("سنن أبي داود", "أبو داود", 275, None),
    5: ("سنن ابن ماجه", "ابن ماجه", 273, None), 8: ("سنن الدارمي", "الدارمي", 255, None),
    1016: ("الأدب المفرد", "البخاري", 256, None), 6: ("مسند الإمام أحمد", "أحمد بن حنبل", 241, None),
    74: ("المستدرك على الصحيحين", "الحاكم", 405, None), 314: ("صحيح ابن حبان", "ابن حبان", 354, None),
    75: ("صحيح ابن خزيمة", "ابن خزيمة", 311, None), 1009: ("شرح السنة", "البغوي", 516, None),
    121: ("النهاية في غريب الحديث والأثر", "ابن الأثير", 606, "hadith_vocab"),
    123: ("القاموس المحيط", "الفيروزآبادي", 817, "lexicon"),
    124: ("معجم مقاييس اللغة", "ابن فارس", 395, "lexicon"),
    125: ("مختار الصحاح", "الرازي", 666, "lexicon"),
    45: ("المصباح المنير", "الفيومي", 770, "terminology"),
    1084: ("غريب الحديث للخطابي", "الخطابي", 388, "hadith_vocab"),
    1085: ("غريب الحديث لأبي عبيد", "أبو عبيد القاسم بن سلام", 224, "hadith_vocab"),
    1088: ("غريب الحديث للحربي", "إبراهيم الحربي", 285, "hadith_vocab"),
}
GHAZALI_AR = "أبو حامد الغزالي"


def main():
    books = {b["id"]: b for b in json.loads((ROOT / "catalog" / "books.json").read_text())}
    manifest = json.loads((ROOT / "catalog" / "manifest.json").read_text())
    out = []
    for bid, m in manifest.items():
        b = books[bid]
        title, author, death, kind = b["title_ar"], b.get("author_ar", ""), b.get("death_ah"), b.get("kind")
        if b["source"] == "islamweb":
            title, author, death, k = ISLAMWEB[int(b["source_ref"].split("=")[1])]
            kind = kind or k
        if b["category"] == "ghazali":
            author, death = GHAZALI_AR, 505
        is_dict = b["category"] == "dictionary"
        out.append({
            "id": bid, "title": title, "title_en": b["title_en"], "author": author, "death_ah": death,
            "group": "dictionary" if is_dict else b["category"], "kind": (kind or "lexicon") if is_dict else "book",
            "tier": b["tier"], "sections": m["sections"], "entries": m["entries"],
            "bytes": m["deflate_bytes"], "db_bytes": m["db_bytes"], "sha256_db": m["sha256_db"],
            "url": m["download_url"], "license": b["license"].split(" (")[0], "ocr": bool(b.get("ocr")),
        })
    out.sort(key=lambda x: (x["group"], x["tier"], x["title"]))
    (ROOT / "catalog" / "library.json").write_text(json.dumps({"version": 1, "books": out}, ensure_ascii=False, separators=(",", ":")))
    print(len(out), "books ->", (ROOT / "catalog" / "library.json").stat().st_size // 1024, "KB")


main()
