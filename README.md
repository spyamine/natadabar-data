# natadabar-data

Study databases for the [naTadabar](https://github.com/spyamine) iOS app, built so other apps can reuse them. Databases are published as **release assets** (raw-deflate `.db.deflate` + SHA-256), not committed to git.

- `BOOKS.md`: human-readable list of all books (in app, planned, tiers)
- `catalog/books.json`: the same list, machine-readable, with source IDs and licenses
- `REFERENCES.md`: where every text came from and under what terms
- `scripts/build_catalog.py`: regenerates the catalog from OpenITI metadata
- `CLAUDE.md`: guide for an agent integrating these databases into an app

Status: the catalog is a draft; scraping and database builds follow tier by tier.
