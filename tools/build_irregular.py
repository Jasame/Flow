"""Write flow/corpus_data/irregular-flow.json: irregular word forms -> base word, from ECDICT's inflection table.

Look-ups turn regular forms back into base words by rule (cities -> city, hoping -> hope), but a learner who taps
"went", "bought", "mice" or "worse" needs the table. ECDICT (MIT, https://github.com/skywind3000/ECDICT) lists each
word's forms in its `exchange` column (p: past, d: past participle, i: -ing, 3: third person, s: plural,
r: comparative, t: superlative) and, for a form, its base word (0:).

Kept: forms of words in Flow's dictionary that the rules cannot reach and that are not dictionary words themselves
("left", "found", "saw" keep their own entries, whose meanings already mention leave/find/see).

usage: build_irregular.py <ecdict.csv> <flow dir>
"""
import csv, json, re, sys
from pathlib import Path

SRC, FLOW = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(FLOW))
import next_service as nx  # noqa: E402

nx._IRREG = {}  # build from the rules alone
d = nx.dictionary()
CODES = set('pdi3srt')
pairs = {}
csv.field_size_limit(10 ** 7)
with SRC.open(encoding='utf-8', newline='') as f:
    for row in csv.DictReader(f):
        w = (row.get('word') or '').strip().lower()
        parts = dict(x.split(':', 1) for x in (row.get('exchange') or '').split('/') if ':' in x)
        if w in d:  # a base word: its forms
            for code, form in parts.items():
                if code in CODES:
                    for v in form.split(','):
                        pairs.setdefault(v.strip().lower(), set()).add(w)
        base = parts.get('0', '').strip().lower()
        if base and base in d and base != w:  # a form: its base word
            pairs.setdefault(w, set()).add(base)

for form in ('is', 'are', 'was', 'were', 'been', 'being'):  # ECDICT does not list the forms of "be"
    pairs.setdefault(form, set()).add('be')
NOT_BASES = {'am'}  # "amer", "ams": noise in the table
forms = {}
for form, bases in pairs.items():
    if not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', form) or form in d:
        continue
    if any(c in d for c in nx.lemma_candidates(form)[1:]):
        continue  # the rules already find a base word
    bases = sorted(b for b in bases if b != form and b not in NOT_BASES)
    if bases:
        forms[form] = min(bases, key=lambda b: d[b]['rank'])  # the most common base word
out = FLOW / 'corpus_data' / 'irregular-flow.json'
out.write_text(json.dumps({'notice': 'Irregular forms from ECDICT (MIT, https://github.com/skywind3000/ECDICT); built by tools/build_irregular.py.',
                           'forms': dict(sorted(forms.items()))}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(len(forms), 'forms ->', out, out.stat().st_size, 'bytes')
