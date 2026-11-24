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
_NAME = re.compile(r'(campus|travel|life|work|culture|science)\.(A2|B1|B2|C1)(?:\.\d+)?\.json')  # e.g. work.B2.json, work.B2.2.json


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


# Question types (SPEC v5.1): 主旨 the gist, 推断 what the text implies, 词义 a word or phrase in context, 细节 a stated fact.
QUESTION_TYPES = {'main': '主旨', 'inference': '推断', 'vocab': '词义', 'detail': '细节'}
_QKEYS = ('prompt', 'options', 'answer', 'evidence')


def additive(old, new):
    """True when new only adds to old: the same text, title and source, and old's questions kept, in order, as the
    first ones (a type label may be added to them). Learners' answers are stored by question number, so earlier
    questions must never move or change; everything else (guide, tags, purposes, more questions) may grow."""
    if any(old.get(k) != new.get(k) for k in ('body', 'title', 'source', 'level', 'cefr')):
        return False
    oq, nq = old.get('questions') or [], new.get('questions') or []
    return len(nq) >= len(oq) and all({k: a.get(k) for k in _QKEYS} == {k: b.get(k) for k in _QKEYS} for a, b in zip(oq, nq))


def sync(c):
    """Bring additive edits of published v5 materials into the database (r27 content line).

    lab_packs is written once per material (INSERT OR IGNORE), so a third and fourth question, question types or the
    purposes tags added to a file would otherwise never reach a running site. Only additive edits are applied (see
    additive()); any other change to a published material needs a new id. A material's review state is bound to its
    content hash (quality_service), so the latest review is carried over to the new content: an operator's decision
    (for example a disabled material) still holds. Returns the ids updated."""
    import hashlib
    def digest(p):
        return hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    has_reviews = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='material_reviews'").fetchone()
    done = []
    for p in v5_materials():
        row = c.execute('SELECT content FROM lab_packs WHERE id=? AND owner IS NULL', (p['id'],)).fetchone()
        if not row:
            continue
        text = json.dumps(p, ensure_ascii=False)
        if row['content'] == text:
            continue
        old = json.loads(row['content'])
        if old == p or not additive(old, p):
            continue
        c.execute('UPDATE lab_packs SET content=? WHERE id=? AND owner IS NULL', (text, p['id']))
        if has_reviews:
            r = c.execute('SELECT status, checks, note, actor FROM material_reviews WHERE pack=? AND content_hash=? ORDER BY id DESC LIMIT 1',
                          (p['id'], digest(old))).fetchone()
            if r:
                c.execute('INSERT INTO material_reviews(pack,content_hash,status,checks,note,actor,created) VALUES(?,?,?,?,?,?,?)',
                          (p['id'], digest(p), r['status'], r['checks'], (r['note'] or '') + '（内容只做了增补，沿用上次的审核状态）', r['actor'], __import__('time').time()))
        done.append(p['id'])
    if done:
        c.commit()
    return done
