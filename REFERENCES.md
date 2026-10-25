# References and provenance

Every dataset in this repo is derived from one of the sources below. Per-book source IDs are in `catalog/books.json` (`source`, `source_ref`, `source_url`).

## Sources

| Source | What we take | URL | License / terms |
|---|---|---|---|
| OpenITI RELEASE (2025.1.9) | Ghazali works, some hadith and dictionaries, as OpenITI mARkdown text | https://github.com/OpenITI/RELEASE | **CC BY-NC-SA 4.0** (Zenodo record 3082464). Non-commercial and share-alike: attribution required, derivative databases must carry the same license |
| OpenITI metadata TSV | Author, title, death date, edition info per text | https://github.com/OpenITI/RELEASE/tree/master/metadata | same |
| islamweb.net library | Hadith collections and Arabic dictionaries, page by page | https://www.islamweb.net/ar/library/ (book pattern `/ar/library/content/{bk_no}/{page}/`) | Site content; edition copyright not stated. Check before commercial redistribution |
| islamweb.net book index | Catalogue (bk_no, title, author, subject, page count) | https://www.islamweb.net/ar/library/index.php?page=bookslist | same |
| Tafsir al-Qurtubi (existing release `qurtubi-v1`) | Already published here | islamweb bk_no source, see naTadabar CLAUDE.md | same as islamweb |

OpenITI texts originate from Shamela, Jami' al-Kutub (JK), Rafed, Shia Online Library, Al-Maktaba al-Shamila and others; the original edition (editor, publisher, year) is preserved in each text's `#META#` header and recorded per book in the catalog.

Citation for OpenITI: Romanov, Maxim and Masoumeh Seydi. "OpenITI: A Machine-Readable Corpus of Islamicate Texts." Zenodo. https://doi.org/10.5281/zenodo.3082463

## Licensing caution

OpenITI is non-commercial. If naTadabar's premium tier is a paid product, bundling or distributing OpenITI-derived databases needs either permission from the OpenITI maintainers or a fallback source for those books. Decide this before shipping Ghazali data in a paid build.
