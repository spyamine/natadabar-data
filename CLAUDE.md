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
`text_clean` is normalized for search (no diacritics, unified alef/taa marbuta, see islamweb-scraper `normalize.py`); `text_vocalized` is the display text. Dictionaries use `entries` for each headword with `number` = root/headword order.

## Build rules
- SQLite journal mode DELETE (not WAL), then VACUUM; iOS cannot open WAL DBs from the bundle.
- Publish as `<slug>.db.deflate` (raw deflate) release assets with a SHA-256 in the release notes (same as `qurtubi-v1`).
- OpenITI input: mARkdown, headings `### |`/`### ||` mark sections, `~~` continues a line, `PageV01P001` marks pages; strip the `#META#` header into `books`.
- islamweb input: pages at `/ar/library/content/{bk_no}/{page}/`; reuse `~/Developer/islamweb-scraper`.
- Record source and license per book in `books`; keep `catalog/books.json` in sync.

## Integrating into naTadabar (~/Developer/naTadabar-ios)
1. Download via the `TafsirDownloadService` pattern (`remoteAsset`), or bundle small DBs in Resources (add via project.yml).
2. Copy to App Support before opening; follow `IhyaDatabaseManager` for the manager.
3. Text: `SelectableFlowText` (single tap -> Lissan with `verseText:`, long press -> excerpt into a tadabbur). Accent color in `BookExcerptBlockView`, card in `MoreTab`.
4. Check `license` first: OpenITI data is CC BY-NC-SA.
