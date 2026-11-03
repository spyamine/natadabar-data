#!/usr/bin/env python3
"""Generate, validate, publish and push automatic tashkil for many books, resumably.

Each book counts as done only after its release asset is re-downloaded and matches,
and the pushed catalog selects it. A failed book is reported and skipped; rerun to retry.
Events are appended to work/tashkil-batch/status.jsonl.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'work/tashkil-batch'
VENV_PY = ROOT/'work/.venv-tashkil/bin/python'
QURAN = ROOT.parent/'naTadabar-ios/naTadabar/naTadabar/Resources/Data/surah'
REPO = 'spyamine/natadabar-data'
AR = re.compile('[ء-غف-يٱ]')
PAIRS = ('()', '[]', '{}')


def run(*cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=True, **kw).stdout


def retry(action, attempts=6, delay=30):
    """Survive transient network failures with increasing waits."""
    for attempt in range(1, attempts+1):
        try:
            return action()
        except (OSError, subprocess.CalledProcessError):
            if attempt == attempts:
                raise
            time.sleep(delay*attempt)


def download(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def event(**data):
    STATE.mkdir(parents=True, exist_ok=True)
    data['utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with (STATE/'status.jsonl').open('a') as f:
        f.write(json.dumps(data, ensure_ascii=False)+'\n')


def bracket_spans(text):
    """Outermost balanced bracket spans containing Arabic; unmatched brackets are ignored."""
    spans = []
    for opener, closer in PAIRS:
        stack = []
        for i, c in enumerate(text):
            if c == opener:
                stack.append(i)
            elif c == closer and stack:
                start = stack.pop()
                if not stack and AR.search(text[start:i+1]):
                    spans.append([start, i+1])
    return sorted(spans)


def protection_file(book_id):
    """Keep a hand-checked file if present, otherwise protect all bracketed passages."""
    path = ROOT/'catalog/tashkil-protection'/f'{book_id}.json'
    if not path.exists():
        db = sqlite3.connect(f"file:{ROOT/'work/dbs'/(book_id+'.db')}?mode=ro", uri=True)
        ranges = {str(i): s for i, t in db.execute('SELECT id,text_vocalized FROM entries') if (s := bracket_spans(t))}
        db.close()
        path.write_text(json.dumps(ranges, ensure_ascii=False)+'\n')
    return path


def generate(book_id):
    output = ROOT/'dist'/f'{book_id}-tashkil-v1.db'
    if output.exists():
        return output
    with (STATE/f'{book_id}.log').open('a') as log:
        subprocess.run([str(VENV_PY), 'scripts/generate_tashkil.py', f'work/dbs/{book_id}.db', str(output),
                        '--quran-dir', str(QURAN), '--protected-spans', str(protection_file(book_id))],
                       cwd=ROOT, check=True, stdout=log, stderr=subprocess.STDOUT)
    return output


def quality_gate(output):
    """Every protected span must survive verbatim; report vowel coverage of generated text."""
    review = json.loads(output.with_suffix('.review.json').read_text())
    letters = marked = spans = 0
    for row in review:
        for piece in row['protected_text']:
            spans += 1
            if piece not in row['generated']:
                raise ValueError(f"Protected span altered in entry {row['entry_id']}")
        marks = re.findall('[ء-غف-يٱ][ً-ْ]?', row['generated'])
        letters += len(marks)
        marked += sum(len(m) > 1 for m in marks)
    return spans, round(100*marked/max(letters, 1), 1)


def publish(book_id, output):
    run(sys.executable, 'scripts/publish_tashkil.py', book_id, str(output), '--upload')
    meta = json.loads((ROOT/'catalog/tashkil.json').read_text())[book_id]
    if hashlib.sha256(retry(lambda: download(meta['download_url']))).hexdigest() != meta['sha256']:
        raise ValueError('Downloaded release asset does not match its checksum')
    protection = f'catalog/tashkil-protection/{book_id}.json'
    run('git', 'add', 'catalog/tashkil.json', 'catalog/library.json', protection)
    run('git', 'commit', '-m', f'Publish automatic tashkil for {book_id}\n\n'
        'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')
    retry(lambda: run('git', 'push', 'origin', 'main'))
    pushed = retry(lambda: run('gh', 'api', f'repos/{REPO}/contents/catalog/tashkil.json', '-H', 'Accept: application/vnd.github.raw'))
    if json.loads(pushed).get(book_id, {}).get('sha256') != meta['sha256']:
        raise ValueError('Pushed catalog does not select the new asset')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--groups', default='ghazali', help='Comma-separated catalog groups')
    p.add_argument('--workers', type=int, default=2)
    args = p.parse_args()
    groups = args.groups.split(',')
    STATE.mkdir(parents=True, exist_ok=True)
    books = json.loads((ROOT/'catalog/library.json').read_text())['books']
    registry = json.loads((ROOT/'catalog/tashkil.json').read_text())
    queue = sorted((b for b in books if b['group'] in groups and b['id'] not in registry),
                   key=lambda b: (b['id'] != '0505ghazali_jawahirquran', groups.index(b['group']), int(b['db_bytes'])))
    event(type='start', queued=[b['id'] for b in queue])
    titles = {b['id']: b['title'] for b in books}
    with ThreadPoolExecutor(args.workers) as pool:
        pending = {pool.submit(generate, b['id']): b['id'] for b in queue}
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                book_id = pending.pop(future)
                try:
                    output = future.result()
                    spans, coverage = quality_gate(output)
                    publish(book_id, output)
                    event(type='done', id=book_id, title=titles[book_id], protected_spans=spans, vowel_coverage=coverage)
                except Exception as error:
                    detail = getattr(error, 'stderr', '') or ''
                    event(type='failed', id=book_id, title=titles[book_id], error=f'{error} {detail}'[:800])
    event(type='finished')


if __name__ == '__main__':
    main()
