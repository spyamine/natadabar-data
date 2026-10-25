#!/usr/bin/env python3
"""Build catalog/books.json and BOOKS.md: the master list of books to scrape and sync.

Ghazali entries are derived from the OpenITI metadata (fetched, not stored);
hadith and dictionary entries are curated below against the islamweb.net library index.

    python3 scripts/build_catalog.py
"""
import csv
import io
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENITI_TSV = "https://raw.githubusercontent.com/OpenITI/RELEASE/master/metadata/OpenITI_metadata_2025-1-9.tsv"
OPENITI_RAW = "https://raw.githubusercontent.com/OpenITI/RELEASE/master/"
ISLAMWEB_BOOK = "https://www.islamweb.net/ar/library/content/{bk}/1/"

LIC_OPENITI = "CC BY-NC-SA 4.0 (OpenITI corpus; non-commercial, share-alike)"
LIC_ISLAMWEB = "islamweb.net library; edition copyright not stated, verify before redistribution"

# OpenITI book key -> (English title, Arabic title, tier, note)
GHAZALI = {
    "Wasit": ("Al-Wasit fi al-Madhhab", "الوسيط في المذهب", 3, "Shafi'i fiqh, very large (1.6M chars)"),
    "Mustasfa": ("Al-Mustasfa min Ilm al-Usul", "المستصفى من علم الأصول", 2, "Also on islamweb bk_no=33"),
    "Mankhul": ("Al-Mankhul min Taliqat al-Usul", "المنخول من تعليقات الأصول", 3, ""),
    "Munqidh": ("Al-Munqidh min al-Dalal", "المنقذ من الضلال", 1, "Autobiography; short"),
    "BidayatHidaya": ("Bidayat al-Hidaya", "بداية الهداية", 1, "Daily conduct manual"),
    "MinhajCabidin": ("Minhaj al-Abidin", "منهاج العابدين", 1, "OCR source: needs proofreading"),
    "MizanCamal": ("Mizan al-Amal", "ميزان العمل", 1, ""),
    "MaqsadAsna": ("Al-Maqsad al-Asna", "المقصد الأسنى في شرح أسماء الله الحسنى", 1, "Names of God"),
    "JawahirQuran": ("Jawahir al-Quran", "جواهر القرآن", 1, "Directly Quran-related"),
    "MishkatAnwar": ("Mishkat al-Anwar", "مشكاة الأنوار", 1, "Light verse commentary"),
    "Iqtisad": ("Al-Iqtisad fi al-Itiqad", "الاقتصاد في الاعتقاد", 2, "Creed"),
    "Tahafut": ("Tahafut al-Falasifa", "تهافت الفلاسفة", 2, ""),
    "QawacidCaqaid": ("Qawaid al-Aqaid", "قواعد العقائد", 2, "Creed summary from Ihya book 2"),
    "Fadaih": ("Fadaih al-Batiniyya", "فضائح الباطنية", 3, ""),
    "ShifaGhalil": ("Shifa al-Ghalil", "شفاء الغليل", 3, "Usul / qiyas"),
    "MaqasidFalasifa": ("Maqasid al-Falasifa", "مقاصد الفلاسفة", 3, ""),
    "MicyarCilm": ("Miyar al-Ilm", "معيار العلم", 3, "Logic"),
    "MihakkNazar": ("Mihakk al-Nazar", "محك النظر", 3, "Logic; OCR source"),
    "MacarijQuds": ("Maarij al-Quds", "معارج القدس في مدارج معرفة النفس", 2, ""),
    "SirrCalamin": ("Sirr al-Alamin", "سر العالمين وكشف ما في الدارين", 3, "Attribution disputed"),
    "TibrMasbuk": ("Al-Tibr al-Masbuk", "التبر المسبوك في نصيحة الملوك", 2, "Advice to rulers"),
    "AsnafMaghrurin": ("Asnaf al-Maghrurin", "أصناف المغرورين", 1, "Excerpt of Ihya, short"),
    "KimiyaSacada": ("Kimiya-yi Sa'adat (Arabic excerpt)", "كيمياء السعادة", 2, "Very short"),
    "RaddJamil": ("Al-Radd al-Jamil", "الرد الجميل لإلهية عيسى بصريح الإنجيل", 3, "Attribution disputed"),
    "MajmucatRasail": ("Majmuat Rasail al-Imam al-Ghazali", "مجموعة رسائل الإمام الغزالي", 1,
                       "Collection incl. Ayyuha al-Walad, Iljam al-Awamm, Faysal al-Tafriqa; split into treatises"),
}
GHAZALI_PERSIAN_SKIPPED = ["AyFarzand", "ZadAkhirat"]

# Hadith: (islamweb bk_no, English, tier, note)
HADITH = [
    (0, "Sahih al-Bukhari", 0, "In app"),
    (1, "Sahih Muslim", 0, "In app"),
    (7, "Muwatta Malik", 0, "In app"),
    (402, "Riyad al-Salihin", 1, "Nawawi; thematic, ideal for tadabbur"),
    (2, "Sunan al-Tirmidhi", 1, ""),
    (4, "Sunan Abi Dawud", 1, ""),
    (3, "Sunan al-Nasai", 1, ""),
    (5, "Sunan Ibn Majah", 1, ""),
    (8, "Sunan al-Darimi", 2, ""),
    (1016, "Al-Adab al-Mufrad (Bukhari)", 2, "Ethics; short"),
    (6, "Musnad Ahmad", 3, "26k pages: largest, last"),
    (74, "Al-Mustadrak (Hakim)", 3, ""),
    (314, "Sahih Ibn Hibban", 3, ""),
    (75, "Sahih Ibn Khuzayma", 3, ""),
    (1009, "Sharh al-Sunna (Baghawi)", 3, ""),
]
# Hadith extras only available on OpenITI (not islamweb)
HADITH_OPENITI = [
    ("0676Nawawi.ArbacunaNawawiyya", "Forty Hadith of Nawawi", 1, "Very short, add alongside Riyad"),
    ("0852IbnHajarCasqalani.BulughMaram", "Bulugh al-Maram", 2, ""),
    ("0510IbnMascudBaghawi.MasabihSunna", "Masabih al-Sunna", 3, ""),
    ("0656IbnCabdQawiMundhiri.TarghibWaTarhib", "Al-Targhib wa al-Tarhib", 2, "Virtues and warnings"),
]

# Dictionaries: (islamweb bk_no | OpenITI key, English, tier, note)
DICT_ISLAMWEB = [
    (122, "Lisan al-Arab", 0, "In app (Lissan engine)"),
    (123, "Al-Qamus al-Muhit", 1, ""),
    (124, "Maqayis al-Lugha (Ibn Faris)", 1, "Root-based: best fit for word lookup"),
    (125, "Mukhtar al-Sihah", 1, "Compact"),
    (45, "Al-Misbah al-Munir", 2, "Fiqh vocabulary"),
    (121, "Al-Nihaya fi Gharib al-Hadith", 1, "Hadith vocabulary"),
    (1084, "Gharib al-Hadith (Khattabi)", 3, ""),
    (1085, "Gharib al-Hadith (Abu Ubayd)", 3, ""),
    (1088, "Gharib al-Hadith (Harbi)", 3, ""),
]
DICT_OPENITI = [
    ("0393IbnHammadJawhari.SihahTajLugha", "Al-Sihah (Jawhari)", 2, ""),
    ("0538JarAllahZamakhshari.AsasBalagha", "Asas al-Balagha", 1, "Metaphorical usages, good for Quranic nuance"),
    ("0370AbuMansurAzhari.TahdhibLugha", "Tahdhib al-Lugha", 3, "Large"),
    ("1205MurtadaZabidi.TajCarus", "Taj al-Arus", 3, "Very large"),
    ("0911Suyuti.MuzhirFiCulumLugha", "Al-Muzhir fi Ulum al-Lugha", 3, "Language sciences"),
]
DICT_GAPS = [
    "Mufradat Alfaz al-Quran (Raghib al-Isfahani): top-priority for tadabbur; not found on islamweb or OpenITI; try Shamela/other source",
    "Al-Ayn (Farahidi), Jamharat al-Lugha (Ibn Durayd), Al-Muhkam (Ibn Sida): not found in sources checked",
    "Gharib al-Quran books (Ibn Qutayba, Sijistani)",
]


def openiti_rows():
    raw = urllib.request.urlopen(OPENITI_TSV).read().decode("utf8")
    csv.field_size_limit(10**9)
    return list(csv.DictReader(io.StringIO(raw), delimiter="\t"))


def pick_version(rows, book_uri):
    """Best OpenITI version of a book: Arabic, not OCR, primary status, longest."""
    cands = [r for r in rows if r["book"] == book_uri and r["language"] == "ara"]
    if not cands:
        return None
    cands.sort(key=lambda r: (r["uncorrected_OCR"] == "True", r["status"] != "pri", -int(r["char_length"] or 0)))
    return cands[0]


def oi_entry(row, category, en, tier, note, ar=None):
    path = row["local_path"]
    return {
        "id": slug(row["book"]),
        "category": category,
        "title_ar": ar or clean_title(row["title_ar"]) or row["book"],
        "title_en": en,
        "author_ar": (row["author_ar"].split("::")[0].strip()),
        "death_ah": int(row["date"]) if row["date"].isdigit() else None,
        "source": "openiti",
        "source_ref": row["version_uri"],
        "source_url": OPENITI_RAW + path,
        "size_chars": int(row["char_length"] or 0),
        "ocr": row["uncorrected_OCR"] == "True",
        "tier": tier,
        "status": "planned",
        "license": LIC_OPENITI,
        "note": note,
    }


def clean_title(t):
    return re.sub(r"\s*-\s*الجزء.*$", "", t.split("::")[0]).strip(" \u200c")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def main():
    rows = openiti_rows()
    catalog = []

    # Ihya is already in the app
    catalog.append({
        "id": "ihya_uloom_al_din", "category": "ghazali", "title_ar": "إحياء علوم الدين",
        "title_en": "Ihya Ulum al-Din", "author_ar": "أبو حامد الغزالي", "death_ah": 505,
        "source": "ihya-scraper", "source_ref": "Shamela 9472 (see ihya-scraper)", "source_url": "",
        "tier": 0, "status": "in_app", "license": "see ihya-scraper", "note": "Done: DB v8",
    })

    for key, (en, ar, tier, note) in GHAZALI.items():
        row = pick_version(rows, f"0505Ghazali.{key}")
        if not row:
            print("missing in OpenITI:", key)
            continue
        catalog.append(oi_entry(row, "ghazali", en, tier, note, ar))

    for bk, en, tier, note in HADITH:
        catalog.append({
            "id": slug(en), "category": "hadith", "title_ar": "", "title_en": en,
            "source": "islamweb", "source_ref": f"bk_no={bk}", "source_url": ISLAMWEB_BOOK.format(bk=bk),
            "tier": tier, "status": "in_app" if tier == 0 else "planned",
            "license": LIC_ISLAMWEB, "note": note,
        })
    for book_uri, en, tier, note in HADITH_OPENITI:
        row = pick_version(rows, book_uri)
        if row:
            catalog.append(oi_entry(row, "hadith", en, tier, note))

    for bk, en, tier, note in DICT_ISLAMWEB:
        catalog.append({
            "id": slug(en), "category": "dictionary", "title_ar": "", "title_en": en,
            "source": "islamweb", "source_ref": f"bk_no={bk}", "source_url": ISLAMWEB_BOOK.format(bk=bk),
            "tier": tier, "status": "in_app" if tier == 0 else "planned",
            "license": LIC_ISLAMWEB, "note": note,
        })
    for book_uri, en, tier, note in DICT_OPENITI:
        row = pick_version(rows, book_uri)
        if row:
            catalog.append(oi_entry(row, "dictionary", en, tier, note))

    (ROOT / "catalog").mkdir(exist_ok=True)
    (ROOT / "catalog" / "books.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf8")
    write_markdown(catalog)
    print(f"{len(catalog)} books -> catalog/books.json, BOOKS.md")


def write_markdown(catalog):
    tiers = {0: "In app already", 1: "Tier 1: scrape first", 2: "Tier 2", 3: "Tier 3: large or niche"}
    names = {"ghazali": "Imam al-Ghazali", "hadith": "Hadith", "dictionary": "Dictionaries & vocabulary"}
    out = ["# Book catalog (draft)", "",
           "Generated by `scripts/build_catalog.py`. Edit the lists in that script, not this file.", ""]
    for cat, label in names.items():
        out += [f"## {label}", "", "| Tier | Book | Source | Size | Note |", "|---|---|---|---|---|"]
        for b in sorted((b for b in catalog if b["category"] == cat), key=lambda b: (b["tier"], b["title_en"])):
            size = f'{b["size_chars"] // 1000}k chars' if b.get("size_chars") else ""
            if b.get("ocr"):
                size += " (OCR)"
            title = b["title_en"] + (f' / {b["title_ar"]}' if b.get("title_ar") else "")
            out.append(f'| {b["tier"]} | {title} | {b["source"]} `{b["source_ref"].split(".")[-1] if b["source"] == "openiti" else b["source_ref"]}` | {size} | {b["note"]} |')
        out.append("")
    out += ["## Known gaps", ""] + [f"- {g}" for g in DICT_GAPS]
    out += [f"- Persian works by Ghazali skipped (Arabic app): {', '.join(GHAZALI_PERSIAN_SKIPPED)}",
            "- Ghazali works not in OpenITI: Ayyuha al-Walad (inside Majmuat Rasail), Iljam al-Awamm, Al-Wajiz, Al-Basit, Faysal al-Tafriqa (check inside Majmuat Rasail)", ""]
    (ROOT / "BOOKS.md").write_text("\n".join(out), encoding="utf8")


if __name__ == "__main__":
    main()
