"""Extract the part of ECDICT that Flow needs into flow/corpus_data/ecdict-flow.json.

ECDICT (https://github.com/skywind3000/ECDICT) is an MIT-licensed English-Chinese dictionary.
Flow's own reference list (yl-reference.json) gives one part of speech per word ("even" -> 偶数的 only),
so word books and look-ups take their meanings from ECDICT, which lists every part of speech, and its
exam tags (CET-4/6, 考研, IELTS, TOEFL, GRE) define the exam word books.

Kept: every word in the reference list, plus every word with an exam tag. Per word:
  [phonetic, translation lines, exam tags, collins stars, in Oxford 3000, BNC rank, frequency rank]

Optionally also writes flow/corpus_data/wordroots-flow.json from ECDICT's wordroot.txt:
  {word: [[root, meaning, class], ...]} for the words above, so word cards can show 词根词缀.

usage: build_ecdict_subset.py <ecdict.csv> <flow dir> [wordroot.txt]
"""
import csv, json, re, sys
from pathlib import Path

SRC, FLOW = Path(sys.argv[1]), Path(sys.argv[2])
TAGS = ('cet4', 'cet6', 'ky', 'ielts', 'toefl', 'gre')
NOTICE = ('ECDICT (https://github.com/skywind3000/ECDICT), MIT License, Copyright (c) 2025 Linwei (full text in corpus_data/ECDICT-LICENSE.txt). '
          'Subset extracted by tools/build_ecdict_subset.py.')

ref = json.loads((FLOW / 'corpus_data' / 'yl-reference.json').read_text(encoding='utf-8'))
want = {t['norm'] for t in ref['terms']}
out = {}
csv.field_size_limit(10 ** 7)
with SRC.open(encoding='utf-8', newline='') as f:
    for row in csv.DictReader(f):
        w = (row.get('word') or '').strip()
        key = w.lower()
        if not re.fullmatch(r"[a-z]+(?:[-' ][a-z]+)*", key):
            continue
        tags = [t for t in (row.get('tag') or '').split() if t in TAGS]
        if key not in want and not tags:
            continue
        lines = [ln.strip() for ln in (row.get('translation') or '').replace('\\n', '\n').split('\n') if ln.strip()]
        lines = [ln for ln in lines if not ln.startswith('[网络]')][:6]  # web-sourced glosses are noisy
        if not lines:
            continue
        if key in out and w != key:  # prefer the lower-case headword ("china" the dishes vs "China")
            continue
        out[key] = [row.get('phonetic') or '', lines, tags, int(row.get('collins') or 0), int(row.get('oxford') or 0),
                    int(row.get('bnc') or 0), int(row.get('frq') or 0)]

dest = FLOW / 'corpus_data' / 'ecdict-flow.json'
dest.write_text(json.dumps({'notice': NOTICE, 'fields': ['phonetic', 'translation', 'tags', 'collins', 'oxford', 'bnc', 'frq'],
                            'words': dict(sorted(out.items()))}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
covered = sum(1 for k in want if k in out)
print(f'{len(out)} words written to {dest} ({dest.stat().st_size / 1e6:.1f} MB); reference list covered {covered}/{len(want)}')
for t in TAGS:
    print(f'  {t}: {sum(1 for v in out.values() if t in v[2])}')

if len(sys.argv) > 3:
    roots = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
    words = want | set(out)
    inv = {}
    for root, v in roots.items():
        if not v.get('meaning'):
            continue
        for w in v.get('example') or []:
            w = w.lower()
            if w in words and len(inv.setdefault(w, [])) < 3:
                inv[w].append([root, v['meaning'][:60], v.get('class', '')])
    rdest = FLOW / 'corpus_data' / 'wordroots-flow.json'
    rdest.write_text(json.dumps({'notice': NOTICE.replace('Subset', 'Word roots subset'), 'words': dict(sorted(inv.items()))},
                                ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(inv)} words with roots written to {rdest} ({rdest.stat().st_size / 1e3:.0f} KB)')
