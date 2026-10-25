# natadabar-data: guide for agents

This repo holds the book catalog, build scripts and (as release assets) SQLite databases for the naTadabar iOS app. Other apps may reuse them. Read `BOOKS.md` for the book list and `REFERENCES.md` for provenance and licenses before using any text.

## Structure rule
Two levels below the book, no more: **book -> sections (introduction, then chapters) -> entries**. Do not model sub-chapters; fold them into the chapter title. Books without chapters get a single section.

## Standard schema (every book DB)
```
books    (id, slug, title_ar, author_ar, death_ah, source, source_ref, license)
sections (id, book_id, ordinal, kind CHECK(kind IN ('intro','chapter')), title, first_entry_id)
entries  (id, book_id, section_id, seq, number, part, page, text_clean, text_vocalized)
entry_fts   FTS5 over entries.text_clean (content=entries)
verse_references (id, entry_id, surah, ayah, ayah_end, start_offset, end_offset)   -- optional
```
`headword` is set only where the source format makes it certain (e.g. Mufradat al-Raghib, Lisan-style dictionaries); otherwise NULL.
`lead` is always set: the first two normalized words of the entry. For dictionaries whose headword is simply the entry's first word, look up a tapped word with
`WHERE headword = :w OR lead LIKE :w || '%'` (normalize `:w` with the same rules), then fall back to FTS.
`kind` of a dictionary (quran_vocab, hadith_vocab, lexicon, terminology) is in `catalog/books.json`, not in the DB.
`text_clean` is normalized for search (no diacritics, unified alef/taa marbuta, see islamweb-scraper `normalize.py`); `text_vocalized` is the display text. Dictionaries use `entries` for each headword with `number` = root/headword order.

## Build rules
- SQLite journal mode DELETE (not WAL), then VACUUM; iOS cannot open WAL DBs from the bundle.
- Publish as `<slug>.db.deflate` (raw deflate) release assets with a SHA-256 in the release notes (same as `qurtubi-v1`).
- OpenITI input: mARkdown, headings `### |`/`### ||` mark sections, `~~` continues a line, `PageV01P001` marks pages; strip the `#META#` header into `books`.
- islamweb input: pages at `/ar/library/content/{bk_no}/{page}/`; reuse `~/Developer/islamweb-scraper`.
- Record source and license per book in `books`; keep `catalog/books.json` in sync.

## Integrating into naTadabar (~/Developer/naTadabar-ios)
Automatic: the app reads `catalog/library.json` (bundled copy + remote refresh) and downloads `download_url` assets from the `library-v1` release.
1. Build the DB (`scripts/build_openiti.py <id>` or `build_islamweb.py <bk_no>`), run `scripts/verify.py`.
2. `gh release upload library-v1 dist/<id>.db.deflate dist/manifest.json --clobber`, copy `dist/manifest.json` to `catalog/manifest.json`.
3. `python3 scripts/export_app_catalog.py`, commit and push. The book now appears under More → Library (or Dictionaries).
4. Optional: refresh the app's bundled copy: `cp catalog/library.json <app>/naTadabar/naTadabar/Resources/library.json`.
Check `license` first: OpenITI data is CC BY-NC-SA (fine while the app is free).

## Discovering books
`catalog/manifest.json` (also a release asset) maps every published book id to `download_url`, `sha256` (of the deflate file), `sha256_db`, sizes and counts. `catalog/books.json` adds titles, authors, tier, kind and license. A generic reader can be driven entirely from these two files.
