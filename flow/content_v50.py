"""Flow Corpus v5: the production corpus (see corpus_data/v5/SPEC.md).

Every file corpus_data/v5/<theme>.<CEFR>.json is a list of complete materials. They are
appended after the earlier corpus so existing ids, attempts and work keep their meaning.
C1 materials are stored with level 'B2' for the classic site and carry the real level in 'cefr'.
"""
import json
import re
from pathlib import Path

from content_v30 import all_materials as previous_materials, SUPERSEDED  # noqa: F401 (re-exported)

V5_DIR = Path(__file__).resolve().parent / 'corpus_data' / 'v5'
_NAME = re.compile(r'(campus|travel|life|work|culture|science)\.(A2|B1|B2|C1)\.json')


def v5_materials():
    out = []
    for f in sorted(V5_DIR.glob('*.json')):
        if not _NAME.fullmatch(f.name):
            continue  # EXAMPLE and work-in-progress files are not published
        for p in json.loads(f.read_text(encoding='utf-8')):
            p.setdefault('family', p['id'])
            p.setdefault('grading_basis', {'method': 'authored-v5', 'rationale': 'Flow 编辑部按 CEFR ' + p.get('cefr', p['level']) + ' 原创与校验', 'certified': False})
            out.append(p)
    return out


V5_IDS = {p['id'] for p in v5_materials()}


def all_materials():
    return previous_materials() + v5_materials()
