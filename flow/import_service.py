"""我的文章: learners paste any English text (a paper, a news story, a chapter) and study it with Flow's tools.

An imported article becomes a private material (lab_packs.owner = the learner), so the whole study page works
on it: tap a word, AI sentence explanations, pre-reading words, read-along with the browser voice, saving
words, dictation, shadowing and output practice. An optional AI pass adds a Chinese summary, two questions,
useful expressions and key vocabulary, all checked against the text.
"""
import hashlib
import json
import re
import time

import next_service as nx

MAX_ARTICLES = 60


def _level(body):
    """Rough CEFR from word frequency: share of words outside the most common bands."""
    ranks = [nx.easiest_rank(w) for w in nx.WORD.findall(body)]
    ranks = [r for r in ranks if r < 99999] or [3000]
    hard = sum(r > 3000 for r in ranks) / len(ranks)
    rare = sum(r > 8000 for r in ranks) / len(ranks)
    words = len(ranks)
    avg_len = words / max(1, len(nx.sentences(body)))
    if rare > 0.06 or (hard > 0.18 and avg_len > 22):
        return 'C1'
    if hard > 0.12 or avg_len > 20:
        return 'B2'
    if hard > 0.06 or avg_len > 13:
        return 'B1'
    return 'A2'


def save(c, uid, data):
    title = data.get('title') if isinstance(data.get('title'), str) else ''
    body = data.get('text') if isinstance(data.get('text'), str) else ''
    body = re.sub(r'[ \t]+', ' ', body.replace('\r', '')).strip()
    body = re.sub(r'\s*\n+\s*', ' ', body)  # one paragraph, like Flow's own materials
    if not 200 <= len(body) <= 8000:
        return {'error': '文章需要 200–8000 个字符'}, 400
    letters = len(re.findall(r'[A-Za-z]', body))
    if letters < 0.6 * len(re.sub(r'\s', '', body)):
        return {'error': '这看起来不是英文文章'}, 400
    if len(nx.sentences(body)) < 3:
        return {'error': '至少需要 3 个句子'}, 400
    if c.execute("SELECT COUNT(*) FROM lab_packs WHERE owner=? AND origin='import'", (uid,)).fetchone()[0] >= MAX_ARTICLES:
        return {'error': f'最多保存 {MAX_ARTICLES} 篇，先删掉几篇旧的'}, 400
    title = ' '.join(title.split())[:80] or ' '.join(body.split()[:8]) + '…'
    pid = 'imp-' + hashlib.sha256(f'{uid}|{body}'.encode()).hexdigest()[:16]
    if c.execute('SELECT 1 FROM lab_packs WHERE id=?', (pid,)).fetchone():
        return {'id': pid, 'existing': True}, 200
    level = _level(body)
    p = {'id': pid, 'title': title, 'title_en': '', 'summary_zh': '', 'level': 'B2' if level == 'C1' else level, 'cefr': level,
         'theme': 'life', 'genre': 'article', 'body': body, 'source': '我导入的文章', 'vocabulary': [], 'expressions': [], 'questions': [],
         'knowledge': [], 'grammar': [], 'imported': True}
    c.execute('INSERT INTO lab_packs VALUES(?,?,?,?,?)', (pid, uid, 'import', json.dumps(p, ensure_ascii=False), time.time()))
    c.commit()
    return {'id': pid, 'level': level, 'existing': False}, 200


def articles(c, uid):
    out = []
    for r in c.execute("SELECT content, created FROM lab_packs WHERE owner=? AND origin='import' ORDER BY created DESC", (uid,)):
        p = json.loads(r['content'])
        out.append({'id': p['id'], 'title': p['title'], 'level': p.get('cefr') or p['level'], 'words': len(nx.WORD.findall(p['body'])),
                    'enriched': bool(p.get('questions')), 'created': r['created'], 'preview': p['body'][:120]})
    return {'items': out, 'max': MAX_ARTICLES}


def delete(c, uid, data):
    n = c.execute("DELETE FROM lab_packs WHERE id=? AND owner=? AND origin='import'", (str(data.get('id', '')), uid)).rowcount
    c.commit()
    return ({'ok': True}, 200) if n else ({'error': '文章不存在'}, 404)


def enrich(c, uid, data):
    """One AI pass: Chinese summary, two questions, expressions and key words, each checked against the text."""
    from lab_service import run_job, text as clean
    from chat_service import request_model
    row = c.execute("SELECT * FROM lab_packs WHERE id=? AND owner=? AND origin='import'", (str(data.get('id', '')), uid)).fetchone()
    if not row:
        return {'error': '文章不存在'}, 404
    p = json.loads(row['content'])
    body = p['body']
    system = '你是英语阅读老师，为中国学习者准备一篇英文文章的学习材料。所有引用都必须是原文里一字不差的片段。只输出 JSON。'
    user = ('文章：\n' + body + '\n\n输出 JSON：{"summary_zh":"两三句中文导读","level":"A2|B1|B2|C1",'
            '"questions":[{"prompt":"英文理解题","options":["四个选项"],"answer":正确选项序号0-3,"evidence":"原文中的依据（原样片段）"}],'
            '"expressions":[{"text":"原文里的地道搭配（原样）","meaning":"中文","note":"用法说明"}],'
            '"vocabulary":[{"term":"原文里的重点词（原样）","meaning":"中文","example":"一个新例句"}]}。questions 恰好 2 道；expressions 3–5 个；vocabulary 3–5 个。')

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        qs = []
        for q in (raw.get('questions') or [])[:2]:
            opts = q.get('options') if isinstance(q, dict) else None
            if (isinstance(opts, list) and len(opts) == 4 and all(isinstance(o, str) and o for o in opts) and isinstance(q.get('answer'), int)
                    and 0 <= q['answer'] < 4 and isinstance(q.get('evidence'), str) and q['evidence'] in body):
                qs.append({'prompt': clean(q.get('prompt'), 3, 300), 'options': [clean(o, 1, 200) for o in opts], 'answer': q['answer'], 'evidence': q['evidence']})
        ex = [{'text': e['text'], 'meaning': clean(e.get('meaning') or '', 0, 120), 'note': clean(e.get('note') or '', 0, 200)}
              for e in (raw.get('expressions') or [])[:5] if isinstance(e, dict) and isinstance(e.get('text'), str) and e['text'] and e['text'] in body]
        vo = [{'term': v['term'], 'meaning': clean(v.get('meaning') or '', 0, 120), 'example': clean(v.get('example') or '', 0, 240)}
              for v in (raw.get('vocabulary') or [])[:5] if isinstance(v, dict) and isinstance(v.get('term'), str) and v['term'] and v['term'] in body]
        if not qs and not ex:
            raise ValueError('nothing usable')
        return {'summary_zh': clean(raw.get('summary_zh') or '', 0, 400), 'level': raw.get('level') if raw.get('level') in ('A2', 'B1', 'B2', 'C1') else None,
                'questions': qs, 'expressions': ex, 'vocabulary': vo}

    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-enrich', p['id'], 'reading', {'id': p['id']},
                             lambda: request_model([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]), convert)
    if status == 200:
        r = result['result']
        p.update({'summary_zh': r['summary_zh'], 'questions': r['questions'], 'expressions': r['expressions'], 'vocabulary': r['vocabulary']})
        if r['level']:
            p['cefr'], p['level'] = r['level'], 'B2' if r['level'] == 'C1' else r['level']
        c.execute('UPDATE lab_packs SET content=? WHERE id=? AND owner=?', (json.dumps(p, ensure_ascii=False), p['id'], uid))
        c.commit()
    return result, status


def get(c, uid, path, q):
    if path == '/api/next/import':
        return articles(c, uid), 200
    return None


def post(c, uid, path, data):
    if path == '/api/next/import':
        return save(c, uid, data)
    if path == '/api/next/import/delete':
        return delete(c, uid, data)
    if path == '/api/next/import/enrich':
        return enrich(c, uid, data)
    return None
