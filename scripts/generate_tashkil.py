#!/usr/bin/env python3
"""Build a source-preserving book DB with optional automatic tashkīl.

Setup on macOS (CPU):
 uv venv --python 3.11 .venv-tashkil
 uv pip install --python .venv-tashkil/bin/python --no-deps catt-tashkeel==1.0.2
 uv pip install --python .venv-tashkil/bin/python onnxruntime==1.31.1 numpy==2.4.6 tqdm==4.70.1

Input and output MUST differ. Original entries/search/IDs are never overwritten.
Output includes text_tashkil, tashkil_metadata, raw-deflate asset and checksums.
Automatic output is not a reviewed edition. Quran quotation matching is conservative,
not exhaustive; inspect the quote report and supply additional protected spans before publishing.
"""
import argparse
import hashlib
import importlib.metadata
import json
import re
import sqlite3
import tempfile
import os
import zlib
from pathlib import Path

MARKS = re.compile('[\u064b-\u0652]')
AR = re.compile('[\u0621-\u063a\u0641-\u064a\u0671]')
WORDS = re.compile(r'\S+')
NOTICE = 'التشكيل آليّ وقد يتضمّن أخطاء.'


def bare(s):
    return MARKS.sub('', s)


def normalized(s):
    s = ''.join(c for c in s if AR.fullmatch(c))
    return s.translate(str.maketrans('أإآٱى', 'ااااي'))


def quote_index(folder):
    grams = set()
    for path in sorted(folder.glob('*.json')):
        for verse in json.loads(path.read_text(encoding='utf-8')).get('verse', {}).values():
            words = [normalized(w) for w in verse.split()]
            words = [w for w in words if w]
            if len(words) <= 3:
                grams.add(tuple(words))
            for i in range(len(words)-2):
                grams.add(tuple(words[i:i+3]))
    if not grams:
        raise ValueError('No Quran quotation index loaded')
    return grams


def protected_spans(text, grams):
    spans = [(m.start(), m.end()) for m in re.finditer(r"«[^»]*»|﴿[^﴾]*﴾|\"[^\"\n]*\"|'[^']*'", text)]
    words = [(m.start(), m.end(), normalized(m.group())) for m in WORDS.finditer(text)]
    words = [w for w in words if w[2]]
    for n in (1, 2, 3):
        for i in range(len(words)-n+1):
            if tuple(w[2] for w in words[i:i+n]) in grams:
                spans.append((words[i][0], words[i+n-1][1]))
    return spans


def overlay(source, prediction, protected=()):
    """Transfer only model vowel marks onto identical original Arabic letters.

    Model preprocessing drops punctuation; it is never copied back. Source vowels win.
    Every original non-vowel codepoint, including whitespace and spelling, is preserved.
    """
    predicted = []
    for c in prediction:
        if AR.fullmatch(c):
            predicted.append([c, ''])
        elif MARKS.fullmatch(c) and predicted:
            predicted[-1][1] += c
    original = [(m.start(), m.group()) for m in AR.finditer(source)]
    canonical = lambda c: 'ا' if c == 'ٱ' else c
    if [canonical(c) for _, c in original] != [canonical(c) for c, _ in predicted]:
        raise ValueError('Model changed Arabic base letters; refusing output')
    vowels = {offset: marks for (offset, _), (_, marks) in zip(original, predicted)}
    out = []
    for i, c in enumerate(source):
        out.append(c)
        if i not in vowels or any(a <= i < b for a, b in protected):
            continue
        if i+1 < len(source) and MARKS.fullmatch(source[i+1]):
            continue
        out.append(vowels[i])
    result = ''.join(out)
    if bare(result) != bare(source):
        raise ValueError('Source-preservation invariant failed')
    return result


def chunks(text, limit=320):
    """Bound context by characters, split only at whitespace; keep original positions."""
    start = 0
    for m in re.finditer(r'\s+', text):
        if m.end()-start >= limit:
            yield start, text[start:m.end()]
            start = m.end()
    if start < len(text):
        yield start, text[start:]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--quran-dir', type=Path, required=True)
    p.add_argument('--protected-spans', type=Path, help='JSON: entry ID -> [[start,end], ...], Python codepoint offsets')
    args = p.parse_args()
    if args.source.resolve() == args.output.resolve() or args.output.exists():
        p.error('Output must be a new file, separate from the source')
    grams = quote_index(args.quran_dir)
    extra = json.loads(args.protected_spans.read_text()) if args.protected_spans else {}
    from catt_tashkeel import CATTEncoderDecoder
    # Short autoregressive sequences run faster without CPU thread oversubscription.
    import onnxruntime as ort
    class CPUModel(CATTEncoderDecoder):
        def _load_onnx_sessions(self, encoder_path, decoder_path):
            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            self.encoder_session = ort.InferenceSession(encoder_path, sess_options=options, providers=['CPUExecutionProvider'])
            self.decoder_session = ort.InferenceSession(decoder_path, sess_options=options, providers=['CPUExecutionProvider'])
    model = CPUModel()
    model_files = Path(importlib.metadata.distribution('catt-tashkeel').locate_file('catt_tashkeel/onnx_models/ed_model'))
    provenance = {'model': 'CATT encoder-decoder v2 ONNX', 'package': importlib.metadata.version('catt-tashkeel'),
                  'model_sha256': {f.name: sha(f) for f in sorted(model_files.glob('*.onnx'))},
                  'source_sha256': sha(args.source), 'notice': NOTICE, 'reviewed': False}
    checkpoint = args.output.with_suffix('.checkpoint.json')
    cached = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    source = sqlite3.connect(f'file:{args.source.resolve()}?mode=ro', uri=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(dir=args.output.parent, suffix='.db', delete=False)
    temp.close()
    tmp = Path(temp.name)
    report = []
    try:
        db = sqlite3.connect(tmp)
        source.backup(db)
        db.execute('ALTER TABLE entries ADD COLUMN text_tashkil TEXT')
        db.execute('CREATE TABLE tashkil_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        for key, value in provenance.items():
            db.execute('INSERT INTO tashkil_metadata VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))
        rows = source.execute('SELECT id,text_vocalized FROM entries ORDER BY id').fetchall()
        for entry_id, text in rows:
            spans = protected_spans(text, grams) + extra.get(str(entry_id), [])
            for a,b in spans:
                if not (0 <= a < b <= len(text)):
                    raise ValueError(f'Invalid protected span in entry {entry_id}')
            parts = []
            for offset, chunk in chunks(text):
                if not AR.search(chunk):
                    parts.append(chunk)
                    continue
                local = [(a-offset, b-offset) for a, b in spans]
                if all(any(a <= m.start() < b for a, b in local) for m in AR.finditer(chunk)):
                    parts.append(chunk)  # Fully protected: inference could not change it.
                    continue
                cache_key = hashlib.sha256((json.dumps(provenance, sort_keys=True) + chunk).encode()).hexdigest()
                predicted = cached.get(cache_key)
                if predicted is None:
                    predicted = model.do_tashkeel(chunk, verbose=False)
                    cached[cache_key] = predicted
                    cache_tmp = checkpoint.with_suffix('.tmp')
                    cache_tmp.write_text(json.dumps(cached, ensure_ascii=False))
                    os.replace(cache_tmp, checkpoint)
                parts.append(overlay(chunk, predicted, local))
            generated = ''.join(parts)
            if bare(generated) != bare(text):
                raise ValueError(f'Entry {entry_id} changed source')
            db.execute('UPDATE entries SET text_tashkil=? WHERE id=?', (generated,entry_id))
            report.append({'entry_id': entry_id, 'protected_spans': spans,
                           'protected_text': [text[a:b] for a,b in spans],
                           'source': text, 'generated': generated})
            print(f'{len(report)}/{len(rows)} entry {entry_id}', flush=True)
        db.commit()
        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity failed')
        db.close()
        os.replace(tmp, args.output)
    finally:
        source.close()
        tmp.unlink(missing_ok=True)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    asset = args.output.with_suffix('.db.deflate')
    asset.write_bytes(compressor.compress(args.output.read_bytes()) + compressor.flush())
    metadata = {**provenance, 'entries': len(report), 'db_bytes': args.output.stat().st_size,
                'deflate_bytes': asset.stat().st_size, 'sha256_db': sha(args.output), 'sha256': sha(asset)}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    args.output.with_suffix('.review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
