# Automatic book tashkīl

`generate_tashkil.py` prepares a separate SQLite database using CATT encoder-decoder v2 (ONNX). It retains the original `text_vocalized`, `text_clean`, FTS, entry IDs, sections and references. It adds nullable `entries.text_tashkil` and a `tashkil_metadata` table. Older apps continue displaying source text.

## CPU setup (macOS)

```sh
uv venv --python 3.11 .venv-tashkil
uv pip install --python .venv-tashkil/bin/python --no-deps catt-tashkeel==1.0.2
uv pip install --python .venv-tashkil/bin/python onnxruntime==1.31.1 numpy==2.4.6 tqdm==4.70.1
```

The package declares a GPU-only ONNX dependency unavailable on Apple Silicon. The CPU `onnxruntime` distribution exposes the same imported API. Models download from the official CATT release on first use. Model hashes and runtime versions should be recorded when comparing outputs. No Python or model runtime is embedded in the iOS app.

```sh
.venv-tashkil/bin/python scripts/generate_tashkil.py \
  work/dbs/0505ghazali_munqidh.db \
  dist/0505ghazali_munqidh-tashkil-v1.db \
  --quran-dir ../naTadabar-ios/naTadabar/naTadabar/Resources/Data/surah
python3 -m unittest discover -s scripts/tests -p test_generate_tashkil.py
```

Output must not exist and must differ from input. Interrupted inference resumes from a chunk checkpoint; checkpoint keys include source/model provenance. Remove the final output to explicitly rebuild after a successful run; retain checkpoints to reuse predictions. Inference happens in bounded word-aligned chunks, so grammatical context across chunk boundaries is limited.

## Validation and publication

- Review `.review.json`, including protected quotations. Automatic Quran n-gram matching and quoted-span protection are conservative and not exhaustive. Supply additional reviewed ranges with `--protected-spans` (entry ID -> Python codepoint offset pairs). Short or paraphrased quotations may need manual protection.
- Letter changes abort generation. The overlay transfers vowel marks only, preserving every original non-vowel codepoint, punctuation, whitespace, and existing source vowels. This does not establish linguistic correctness.
- Validate integrity, entry counts, unchanged original columns/IDs, generated coverage, and a raw-deflate roundtrip.
- Upload the versioned `.db.deflate` and `.manifest.json` as new assets under `library-v1`; do not overwrite the original source asset.
- Record generated metadata plus `download_url` in `catalog/tashkil.json` under the original book ID. `export_app_catalog.py` uses this variant only while its recorded `source_sha256` matches the current original manifest database hash. A later source rebuild automatically falls back to original until generation is redone.
- Export and publish `catalog/library.json`. This gives existing installs an update indicator. The reader needs the new app implementation to use the generated column. Keep updated bundled catalog in the iOS branch.

Always display: **التشكيل آليّ وقد يتضمّن أخطاء.** Generated tashkīl is a reading aid, not an editorially verified edition. Corpus attribution/license still applies. CATT is an initial reproducible candidate, not a proven best model on these books.

The publication helper enforces the checks above:

```sh
python3 scripts/publish_tashkil.py 0505ghazali_munqidh dist/0505ghazali_munqidh-tashkil-v1.db
# After reviewing the generated passages:
python3 scripts/publish_tashkil.py 0505ghazali_munqidh dist/0505ghazali_munqidh-tashkil-v1.db --upload
```

It uploads new assets without `--clobber`, keeps the original manifest/download unchanged, and updates the local catalog. It does not commit or push. Use a new versioned output filename for a later generation run.

For **أصناف المغرورين**, also pass
`--protected-spans catalog/tashkil-protection/0505ghazali_asnafmaghrurin.json`.
This source uses parentheses for Quran/hadith quotations; the checked source-specific ranges preserve all 34 parenthesized passages. They refer to the exact original source revision used in the generated asset. Recheck ranges whenever the source changes.

For **المقصد الأسنى في شرح أسماء الله الحسنى**, pass
`--protected-spans catalog/tashkil-protection/0505ghazali_maqsadasna.json`.
This source has unparenthesized verse citations. The source-specific protection file conservatively covers 56 ranges ending in explicit ayah-number markers (including a plural الآيات marker), starting at a nearby quotation introducer where available. Automatic Quran n-gram protection also applies. These ranges supplement matching; neither method proves exhaustive identification of every quotation.
