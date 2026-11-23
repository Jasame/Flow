"""Extract the part of ECDICT that Flow needs into flow/corpus_data/ecdict-flow.json.

ECDICT (https://github.com/skywind3000/ECDICT) is an MIT-licensed English-Chinese dictionary.
Flow's own reference list (yl-reference.json) gives one part of speech per word ("even" -> 偶数的 only),
so word books and look-ups take their meanings from ECDICT, which lists every part of speech, and its
exam tags (CET-4/6, 考研, IELTS, TOEFL, GRE) define the exam word books.

Kept: every word in the reference list, plus every word with an exam tag (中考 zk and 高考 gk too, for the
open word books in tools/build_open_wordbooks.py), plus every headword of the --keep lists. Per word:
  [phonetic, translation lines, exam tags, collins stars, in Oxford 3000, BNC rank, frequency rank]

--keep takes a word list: one headword per line, or a CSV whose first column is the headword (lines starting with #
are skipped). Flow passes the NAWL and BSL lists (corpus_data/NGSL-LICENSE.txt), so their academic and business
words have dictionary entries; see flow/WORDBOOKS-OPEN.md for the exact command.

Optionally also writes flow/corpus_data/wordroots-flow.json from ECDICT's wordroot.txt:
  {word: [[root, meaning, class], ...]} for the words above, so word cards can show 词根词缀.

usage: build_ecdict_subset.py <ecdict.csv> <flow dir> [wordroot.txt] [--keep LIST ...]
"""
import csv, json, re, sys
from pathlib import Path

ARGS, KEEP = [], []
_argv = iter(sys.argv[1:])
for _a in _argv:
    if _a == '--keep':
        KEEP.append(Path(next(_argv)))
    else:
        ARGS.append(_a)
SRC, FLOW = Path(ARGS[0]), Path(ARGS[1])
EXAM_TAGS = ('cet4', 'cet6', 'ky', 'ielts', 'toefl', 'gre')  # the exam word books (vocab_service.EXAM_BOOKS)
TAGS = EXAM_TAGS + ('zk', 'gk')  # 中考, 高考: the open word books (corpus_data/wordbooks-open.json)


def keep_words(path):
    """Headwords of a word list: the first field of each line (plain list or CSV), lower-case."""
    out = set()
    for ln in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        head = re.split(r'[,\t]', ln.strip(), maxsplit=1)[0].strip().lower()
        if head and not head.startswith('#'):
            out.add(head)
    return out


extra = set().union(*map(keep_words, KEEP)) if KEEP else set()
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
        if key not in want and not tags and key not in extra:
            continue
        if w != key and key not in want and not any(t in EXAM_TAGS for t in tags):
            continue  # names (Canada, February) come in only through the reference list or an exam tag, as before
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
if KEEP:
    print(f'  --keep lists: {sum(1 for k in extra if k in out)}/{len(extra)} headwords have an entry')

if len(ARGS) > 2:
    roots = json.loads(Path(ARGS[2]).read_text(encoding='utf-8'))
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
