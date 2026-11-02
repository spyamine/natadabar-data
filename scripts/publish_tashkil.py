#!/usr/bin/env python3
"""Validate and optionally upload a generated book, then export its catalog entry.

Without --upload this only validates. With --upload it publishes NEW assets and
updates catalog/tashkil.json + catalog/library.json; commit/push remains explicit.
"""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import zlib
from pathlib import Path
from generate_tashkil import bare, sha

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('book_id')
    p.add_argument('database', type=Path)
    p.add_argument('--upload', action='store_true')
    args = p.parse_args()
    path = args.database.resolve()
    metadata_path = path.with_suffix('.manifest.json')
    metadata = json.loads(metadata_path.read_text())
    original = json.loads((ROOT/'catalog/manifest.json').read_text())[args.book_id]
    source_path = ROOT/'work/dbs'/f'{args.book_id}.db'
    if metadata['source_sha256'] != original['sha256_db'] or sha(source_path) != original['sha256_db']:
        raise ValueError('Generated version does not match the published source database')
    if sha(path) != metadata['sha256_db']:
        raise ValueError('Generated database checksum mismatch')
    packed = path.with_suffix('.db.deflate')
    if sha(packed) != metadata['sha256'] or zlib.decompress(packed.read_bytes(), -15) != path.read_bytes():
        raise ValueError('Compressed asset mismatch')
    source = sqlite3.connect(f'file:{source_path}?mode=ro', uri=True)
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity failed')
    columns = [row[1] for row in source.execute('PRAGMA table_info(entries)')]
    sql = 'SELECT '+','.join(columns)+' FROM entries ORDER BY id'
    if source.execute(sql).fetchall() != db.execute(sql).fetchall():
        raise ValueError('Original entry fields changed')
    for table in ('books', 'sections', 'verse_references'):
        if source.execute(f'SELECT * FROM {table}').fetchall() != db.execute(f'SELECT * FROM {table}').fetchall():
            raise ValueError(f'Original {table} changed')
    rows = db.execute('SELECT text_vocalized,text_tashkil FROM entries ORDER BY id').fetchall()
    if len(rows) != original['entries'] or any(not b or bare(a) != bare(b) for a,b in rows):
        raise ValueError('Incomplete or invalid generated text')
    print(f'Validated {len(rows)} entries: original fields, IDs, structure and base text unchanged; deflate and SHA checks passed.')
    source.close()
    db.close()
    if not args.upload:
        print('Validation only. Use --upload to publish assets and update local catalog.')
        return
    subprocess.run(['gh', 'release', 'upload', 'library-v1', '--repo', 'spyamine/natadabar-data', str(packed), str(metadata_path)], check=True)
    registry_path = ROOT/'catalog/tashkil.json'
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    registry[args.book_id] = {**metadata, 'download_url': 'https://github.com/spyamine/natadabar-data/releases/download/library-v1/'+packed.name}
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2)+'\n')
    subprocess.run([sys.executable, str(ROOT/'scripts/export_app_catalog.py')], check=True)
    print('Uploaded. Review and commit catalog/tashkil.json + catalog/library.json to publish catalog selection.')


if __name__ == '__main__':
    main()
