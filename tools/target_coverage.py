"""How often each target word appears (in any inflected form) in the bodies of some corpus files.

Used when writing materials that deliberately recycle word-book vocabulary: every target should appear
in at least --min different materials.

usage: target_coverage.py --min 2 --words w1,w2,... flow/corpus_data/v5/science.B2.3.json [...]
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flow'))
import next_service as nx  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--words', required=True, help='comma-separated base forms')
ap.add_argument('--min', type=int, default=2, help='minimum number of materials each word must appear in')
ap.add_argument('files', nargs='+')
a = ap.parse_args()
targets = [w.strip().lower() for w in a.words.split(',') if w.strip()]
seen = {w: [] for w in targets}
for f in a.files:
    for p in json.loads(Path(f).read_text(encoding='utf-8')):
        lemmas = set()
        for w in nx.WORD.findall(p['body']):
            hit = nx.lookup(w)
            lemmas.add(hit['lemma'] if hit else w.lower())
            lemmas.update(nx.lemma_candidates(w))  # "stunned" counts for "stun" even though it has its own entry
        for t in targets:
            if t in lemmas:
                seen[t].append(p['id'])
short = {t: ids for t, ids in seen.items() if len(ids) < a.min}
for t in targets:
    print(f"{'ok ' if len(seen[t]) >= a.min else 'LOW'} {t:16} {len(seen[t])}  {', '.join(seen[t])}")
print(f'\n{len(targets) - len(short)}/{len(targets)} words reach {a.min} materials')
sys.exit(1 if short else 0)
