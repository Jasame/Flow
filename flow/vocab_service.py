"""Flow vocabulary memory: word books, a daily plan and FSRS reviews, tied to the articles.

Everything a learner remembers is a row in next_cards: words from a word book, words and
expressions saved while reading, and imported lists share one FSRS queue (see fsrs.py).
Example sentences come from Flow's own narrated materials, so a word is reviewed inside a
real sentence and can be heard in it.
"""
import datetime
import json
import math
import os
import random
import re
import time
from pathlib import Path

import fsrs
import next_service as nx

BOOKS = {  # id -> (title, first rank, last rank, blurb); ranks are word-frequency ranks in the reference dictionary
    'core': ('基础词汇', 1, 2000, '最常用的词，读懂日常文章的地基'),
    'mid': ('进阶词汇', 2001, 5000, '读懂一般报刊、课本文章需要的常用词'),
    'high': ('高阶词汇', 5001, 8000, '读懂深度文章和学术入门材料的常见词'),
    'adv': ('精通词汇', 8001, 13000, '面向英语专业和高阶考试的较低频词'),
    'ext': ('拓展词汇', 13001, 20200, '更少见的词，适合继续扩充词汇量'),
}
EXAM_BOOKS = {  # id -> (title, blurb); word lists from ECDICT's exam tags, most frequent words first
    'cet4': ('四级词汇', '大学英语四级考试大纲词汇'),
    'cet6': ('六级词汇', '大学英语六级考试大纲词汇'),
    'ky': ('考研词汇', '全国硕士研究生招生考试英语大纲词汇'),
    'ielts': ('雅思词汇', 'IELTS 常考词汇'),
    'toefl': ('托福词汇', 'TOEFL 常考词汇'),
    'gre': ('GRE 词汇', 'GRE 常考词汇，难度最高'),
}
LEVEL_BOOK = {'A2': 'core', 'B1': 'mid', 'B2': 'high', 'C1': 'adv'}
DAILY_NEW = (5, 10, 15, 20, 30)
RETENTION = (0.8, 0.85, 0.9, 0.95)
MASTERED = 21  # days of stability from which an item counts as mastered
SPELL_FROM, RECALL_FROM = 21, 3  # stability (days) at which reviews move to spelling / active recall
LEVEL_ORDER = {'A2': 0, 'B1': 1, 'B2': 2, 'C1': 3}
# Made-up words for the vocabulary test: saying you know them reveals guessing, which the estimate corrects for.
PSEUDO = ('plimsate', 'tranculate', 'fendrous', 'corvality', 'quindary', 'benestry', 'lorrimate', 'vospery',
          'chanderize', 'mispleen', 'drastonic', 'gorphical', 'stremble', 'pellucate', 'ambrosk', 'wendle')
WORD_AUDIO_DIR = Path(os.getenv('FLOW_AUDIO_DIR') or Path(__file__).resolve().parent / 'audio') / 'words'
ACCENTS = ('us', 'uk')

_BOOK = None
_EX = None
_WA = {'mtime': None, 'index': {}}


def schema(c):
    cols = {r[1] for r in c.execute('PRAGMA table_info(next_cards)')}
    fresh = 'stability' not in cols
    for name, decl in (('state', "TEXT NOT NULL DEFAULT 'new'"), ('step', 'INTEGER NOT NULL DEFAULT 0'), ('stability', 'REAL'),
                       ('difficulty', 'REAL'), ('source', "TEXT NOT NULL DEFAULT 'saved'"), ('rank', 'INTEGER'),
                       ('known', 'INTEGER NOT NULL DEFAULT 0')):
        if name not in cols:
            c.execute(f'ALTER TABLE next_cards ADD COLUMN {name} {decl}')
    if fresh:  # carry progress made under the old SM-2 scheduler over to FSRS
        for r in c.execute('SELECT id, interval, ease, reps FROM next_cards').fetchall():
            st = fsrs.from_sm2(r['interval'], r['ease'], r['reps'])
            c.execute('UPDATE next_cards SET state=?, stability=?, difficulty=? WHERE id=?', (st['state'], st['stability'], st['difficulty'], r['id']))
    rcols = {r[1] for r in c.execute('PRAGMA table_info(next_reviews)')}
    for name, decl in (('mode', 'TEXT'), ('ms', 'INTEGER'), ('elapsed', 'REAL'), ('stability', 'REAL')):
        if name not in rcols:
            c.execute(f'ALTER TABLE next_reviews ADD COLUMN {name} {decl}')
    c.executescript('''
CREATE TABLE IF NOT EXISTS next_vocab_plans(user_id INTEGER PRIMARY KEY REFERENCES users(id), book TEXT NOT NULL,
 daily_new INTEGER NOT NULL DEFAULT 10, retention REAL NOT NULL DEFAULT 0.9, estimate INTEGER, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS next_cards_source ON next_cards(user_id, source, created);
CREATE INDEX IF NOT EXISTS next_reviews_card ON next_reviews(card, created);''')
    c.commit()


# ---------- data ----------

def book_words():
    """book id -> [(rank, word)] in frequency order: plain lower-case words that have a Chinese meaning.

    Frequency books use the reference list only (so their contents never shift); exam books use ECDICT's tags."""
    global _BOOK
    if _BOOK is None:
        out = {k: [] for k in (*BOOKS, *EXAM_BOOKS)}
        for norm, e in nx.dictionary().items():
            if not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', norm) or len(norm) < 2 or not e['meaning'] or e['word'][:1].isupper():
                continue
            if e.get('ref', True):
                for k, (_, lo, hi, _) in BOOKS.items():
                    if lo <= e['rank'] <= hi:
                        out[k].append((e['rank'], norm))
                        break
            for t in e.get('tags') or ():
                if t in EXAM_BOOKS:
                    out[t].append((e['rank'], norm))
        for v in out.values():
            v.sort()
        _BOOK = out
    return _BOOK


def book_title(book):
    return (BOOKS.get(book) or EXAM_BOOKS.get(book) or ('词书',))[0]


def examples_index():
    """(lemma -> [(material id, sentence index, form used)], material id -> (material, sentences)) over the narrated corpus."""
    global _EX
    if _EX is None:
        from content_v50 import v5_materials
        idx, mats = {}, {}
        for p in v5_materials():
            sents = nx.sentences(p['body'])
            mats[p['id']] = (p, sents)
            for i, s in enumerate(sents):
                forms = {}
                for w in nx.WORD.findall(s):
                    hit = nx.lookup(w)
                    if hit:
                        forms.setdefault(hit['lemma'], w)
                for lm, form in forms.items():
                    idx.setdefault(lm, []).append((p['id'], i, form))
        _EX = (idx, mats)
    return _EX


def examples(norm, level='B1', limit=2, skip=''):
    """Sentences from Flow's materials that use this word, closest to the learner's level and short ones first."""
    idx, mats = examples_index()
    want = LEVEL_ORDER.get(level, 1)
    scored = []
    for pid, i, form in idx.get(norm, []):
        p, sents = mats[pid]
        s = sents[i]
        if skip and s.strip() == skip.strip():
            continue
        scored.append((abs(LEVEL_ORDER.get(nx.cefr(p), 1) - want), abs(len(s) - 90), pid, i, s, p['title'], form))
    scored.sort()
    index, version = nx.audio_index()
    out, seen = [], set()
    for _, _, pid, i, s, title, form in scored:
        if pid in seen:  # one sentence per material, so examples show different situations
            continue
        seen.add(pid)
        # form: the word as it appears in the sentence (for gaps and highlighting)
        # audio: the narration version to request (0 = no recording, read it with the browser voice)
        out.append({'pack': pid, 'i': i, 'text': s, 'form': form, 'title': title, 'audio': version if index.get(pid) else 0})
        if len(out) >= limit:
            break
    return out


def word_audio(norm):
    """{accent: [sprite, start, end]} for a word's pre-generated pronunciation (tools/gen_word_audio.py)."""
    f = WORD_AUDIO_DIR / 'index.json'
    try:
        m = f.stat().st_mtime
    except OSError:
        return {}
    if _WA['mtime'] != m:
        _WA['index'], _WA['mtime'] = json.loads(f.read_text()), m
    return {a: _WA['index'][a][norm] for a in ACCENTS if norm in _WA['index'].get(a, {})}


def word_audio_file(accent, sprite):
    if accent not in ACCENTS or not re.fullmatch(r'[wx]\d{3}', sprite or ''):
        return None
    f = WORD_AUDIO_DIR / accent / f'{sprite}.m4a'
    return f if f.is_file() else None


# ---------- helpers ----------

def _day_start(now=None):
    d = datetime.datetime.fromtimestamp(now or time.time(), nx.TZ)
    return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def plan(c, uid):
    r = c.execute('SELECT * FROM next_vocab_plans WHERE user_id=?', (uid,)).fetchone()
    return dict(r) if r else None


def _retention(c, uid):
    p = plan(c, uid)
    return p['retention'] if p else 0.9


def recall_now(r, now=None):
    if r['state'] == 'new' or not r['stability'] or not r['last']:
        return None
    return fsrs.retrievability(r['stability'], ((now or time.time()) - r['last']) / fsrs.DAY)


def mode(r):
    """How to review this item now: recognise (see the word), recall (meaning + gapped sentence), spell (hear and type)."""
    if r['kind'] != 'word':
        return 'cloze' if r['context'] and r['text'].lower() in r['context'].lower() else 'recall'
    s = r['stability'] or 0
    if r['state'] != 'review' or s < RECALL_FROM:
        return 'recognize'
    return 'spell' if s >= SPELL_FROM else 'recall'


def card_out(r, now=None, level=None, rich=False):
    out = {k: r[k] for k in ('id', 'text', 'meaning', 'context', 'pack', 'kind', 'created', 'due', 'reps', 'lapses', 'state',
                             'stability', 'difficulty', 'last', 'source', 'known')}
    rv = recall_now(r, now)
    out['recall'] = None if rv is None else round(rv, 3)
    out['mastered'] = bool(r['known'] or (r['stability'] or 0) >= MASTERED)
    if rich:
        entry = nx.dictionary().get(r['norm']) if r['kind'] == 'word' else None
        out['phonetic'] = entry['phonetic'] if entry else ''
        out['mode'] = mode(r)
        out['examples'] = examples(r['norm'], level or 'B1', 2, r['context']) if r['kind'] == 'word' else []
        out['audio'] = word_audio(r['norm']) if r['kind'] == 'word' else {}
    return out


def _level(c, uid):
    return (nx.profile(c, uid) or {}).get('level') or 'B1'


# ---------- daily queue ----------

def introduce(c, uid, now=None):
    """Top up today's new words from the learner's word book, without piling up unstudied ones."""
    p = plan(c, uid)
    if not p or p['book'] not in book_words():
        return 0
    now = now or time.time()
    today_new = c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND source='book' AND created>=?", (uid, _day_start(now))).fetchone()[0]
    waiting = c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND source='book' AND state='new' AND known=0", (uid,)).fetchone()[0]
    need = min(p['daily_new'] - today_new, p['daily_new'] - waiting)
    if need <= 0:
        return 0
    have = {r[0] for r in c.execute('SELECT norm FROM next_cards WHERE user_id=?', (uid,))}
    d = nx.dictionary()
    added = 0
    for rank, w in book_words()[p['book']]:
        if w in have:
            continue
        e = d[w]
        c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,rank) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid, e['word'], w, e['meaning'][:300], '', None, 'word', now, now, 'new', 'book', rank))
        added += 1
        if added >= need:
            break
    c.commit()
    return added


def queue(c, uid, limit=40):
    """Today's session: items most at risk of being forgotten first, then ones still in learning steps, then new words."""
    now = time.time()
    introduce(c, uid, now)
    rows = c.execute('SELECT * FROM next_cards WHERE user_id=? AND known=0 AND due<=?', (uid, now)).fetchall()
    reviews = sorted((r for r in rows if r['state'] == 'review'), key=lambda r: recall_now(r, now) or 0)
    steps = sorted((r for r in rows if r['state'] in ('learning', 'relearning')), key=lambda r: r['due'])
    new = sorted((r for r in rows if r['state'] == 'new'), key=lambda r: (r['source'] == 'book', r['rank'] or 0, r['created']))
    level = _level(c, uid)
    picked = (reviews + steps + new)[:limit]
    return {'items': [card_out(r, now, level, rich=True) for r in picked], **counts(c, uid, now)}


def counts(c, uid, now=None):
    now = now or time.time()
    q = lambda sql: c.execute(sql, (uid, now)).fetchone()[0]
    due = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND known=0 AND state!='new' AND due<=?")
    new = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND known=0 AND state='new' AND due<=?")
    done = c.execute('SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND created>=?', (uid, _day_start(now))).fetchone()[0]
    return {'due': due, 'new': new, 'done_today': done, 'minutes': max(1, round(due * 0.12 + new * 0.4))}


def rate(c, uid, data):
    rating = data.get('rating')
    if rating not in fsrs.GRADES:
        return {'error': '评分不正确'}, 400
    r = c.execute('SELECT * FROM next_cards WHERE id=? AND user_id=?', (int(data['id']), uid)).fetchone()
    if not r:
        return {'error': '记录不存在'}, 404
    now = time.time()
    m = data.get('mode') if data.get('mode') in ('recognize', 'recall', 'spell', 'cloze') else None
    ms = data.get('ms') if isinstance(data.get('ms'), int) and 0 <= data.get('ms') < 3600000 else None
    elapsed = (now - r['last']) / fsrs.DAY if r['last'] else None
    n = fsrs.review(dict(r), rating, now, _retention(c, uid))
    c.execute('UPDATE next_cards SET state=?, step=?, stability=?, difficulty=?, last=?, due=?, lapses=?, interval=?, reps=reps+1 WHERE id=?',
              (n['state'], n['step'], n['stability'], n['difficulty'], n['last'], n['due'], n['lapses'], n['interval'], r['id']))
    c.execute('INSERT INTO next_reviews(user_id,card,rating,created,mode,ms,elapsed,stability) VALUES(?,?,?,?,?,?,?,?)',
              (uid, r['id'], rating, now, m, ms, elapsed, n['stability']))
    c.commit()
    r2 = c.execute('SELECT * FROM next_cards WHERE id=?', (r['id'],)).fetchone()
    return {'card': card_out(r2, now), **counts(c, uid, now)}, 200


def set_known(c, uid, data):
    known = 1 if data.get('known', True) else 0
    n = c.execute('UPDATE next_cards SET known=? WHERE id=? AND user_id=?', (known, int(data['id']), uid)).rowcount
    if known:
        c.execute('INSERT INTO next_reviews(user_id,card,rating,created,mode) VALUES(?,?,?,?,?)', (uid, int(data['id']), 'known', time.time(), 'known'))
    c.commit()
    return ({'ok': True, **counts(c, uid)}, 200) if n else ({'error': '记录不存在'}, 404)


def met_in_reading(c, uid, word):
    """Looking a word up while reading means it was not remembered: bring its next review forward to now."""
    hit = nx.lookup(word)
    if not uid or not hit:
        return None
    r = c.execute("SELECT * FROM next_cards WHERE user_id=? AND norm=? AND known=0 AND state='review'", (uid, hit['lemma'])).fetchone()
    if not r:
        return None
    now = time.time()
    if r['due'] > now and (now - (r['last'] or 0)) > 3600:
        c.execute('UPDATE next_cards SET due=? WHERE id=?', (now, r['id']))
        c.execute('INSERT INTO next_reviews(user_id,card,rating,created,mode) VALUES(?,?,?,?,?)', (uid, r['id'], 'lookup', now, 'reading'))
        c.commit()
        return {'id': r['id'], 'moved': True}
    return {'id': r['id'], 'moved': False}


def mine_in_text(c, uid, text):
    """The learner's words (being learned, not yet mastered) that appear in a text, for highlighting while reading."""
    if not uid:
        return []
    rows = c.execute("SELECT id, norm FROM next_cards WHERE user_id=? AND kind='word' AND known=0 AND (stability IS NULL OR stability<?)",
                     (uid, MASTERED)).fetchall()
    if not rows:
        return []
    want = {r['norm']: r['id'] for r in rows}
    found = {}
    for w in set(nx.WORD.findall(text)):
        hit = nx.lookup(w)
        if hit and hit['lemma'] in want:
            found[w.lower()] = want[hit['lemma']]
    return [{'form': k, 'id': v} for k, v in found.items()]


# ---------- plan, stats, test, import ----------

def books_meta():
    bw = book_words()
    return ([{'id': k, 'kind': 'freq', 'title': v[0], 'blurb': v[3], 'size': len(bw[k]), 'range': f'{v[1]}–{v[2]}'} for k, v in BOOKS.items()]
            + [{'id': k, 'kind': 'exam', 'title': v[0], 'blurb': v[1], 'size': len(bw[k])} for k, v in EXAM_BOOKS.items()])


def overview(c, uid):
    now = time.time()
    p = plan(c, uid)
    rows = c.execute('SELECT state, stability, due, known, source, kind, last, norm FROM next_cards WHERE user_id=?', (uid,)).fetchall()
    mastered = sum(1 for r in rows if r['known'] or (r['stability'] or 0) >= MASTERED)
    learning = sum(1 for r in rows if not r['known'] and r['state'] != 'new' and (r['stability'] or 0) < MASTERED)
    start = _day_start(now)
    forecast = [0] * 7
    for r in rows:
        if r['known'] or r['state'] == 'new':
            continue
        k = int(max(0, r['due'] - start) // fsrs.DAY)
        if k < 7:
            forecast[k] += 1
    days = {}
    for (t,) in c.execute('SELECT created FROM next_reviews WHERE user_id=? AND created>?', (uid, start - 34 * fsrs.DAY)):
        d = nx._day(t)
        days[d] = days.get(d, 0) + 1
    calendar = [{'day': nx._day(start - i * fsrs.DAY + 3600), 'n': days.get(nx._day(start - i * fsrs.DAY + 3600), 0)} for i in range(34, -1, -1)]
    book = None
    if p and p['book'] in book_words():
        words = book_words()[p['book']]
        norms = {r['norm'] for r in rows}
        started = sum(1 for _, w in words if w in norms)
        left = len(words) - started
        book = {'id': p['book'], 'title': book_title(p['book']), 'size': len(words), 'started': started,
                'finish': nx._day(now + math.ceil(left / max(1, p['daily_new'])) * fsrs.DAY) if left else None}
    return {'plan': p, 'book': book, 'books': books_meta(), 'daily_new_options': list(DAILY_NEW), 'retention_options': list(RETENTION),
            'suggested_book': LEVEL_BOOK.get(_level(c, uid), 'mid'), 'mastered': mastered, 'learning': learning, 'total': len(rows),
            'forecast': forecast, 'calendar': calendar, **counts(c, uid, now)}


def save_plan(c, uid, data):
    book = data.get('book')
    if book not in BOOKS and book not in EXAM_BOOKS:
        return {'error': '请选择词书'}, 400
    daily = data.get('daily_new', 10)
    retention = data.get('retention', 0.9)
    if daily not in DAILY_NEW or retention not in RETENTION:
        return {'error': '计划设置不正确'}, 400
    now = time.time()
    c.execute('''INSERT INTO next_vocab_plans(user_id,book,daily_new,retention,created,updated) VALUES(?,?,?,?,?,?)
                 ON CONFLICT(user_id) DO UPDATE SET book=excluded.book, daily_new=excluded.daily_new, retention=excluded.retention, updated=excluded.updated''',
              (uid, book, daily, retention, now, now))
    c.commit()
    return overview(c, uid), 200


def test_items(seed=None):
    """About 46 words: 8 sampled from each book band plus 6 made-up words, shuffled."""
    rng = random.Random(seed)
    real = nx.dictionary()
    items = []
    for k in BOOKS:
        words = book_words()[k]
        items += [w for _, w in rng.sample(words, min(8, len(words)))]
    fakes = [w for w in PSEUDO if w not in real]
    items += rng.sample(fakes, min(6, len(fakes)))
    rng.shuffle(items)
    return {'items': items}


def score_test(c, uid, data):
    answers = data.get('answers')
    if not isinstance(answers, dict) or not 10 <= len(answers) <= 80:
        return {'error': '测试结果不完整'}, 400
    real = nx.dictionary()
    band_of = {w: k for k in BOOKS for _, w in book_words()[k]}
    per = {k: [0, 0] for k in BOOKS}
    fake = [0, 0]
    for w, yes in answers.items():
        w = str(w).lower()[:40]
        if w in PSEUDO and w not in real:
            fake[0] += bool(yes); fake[1] += 1
        elif w in band_of:
            per[band_of[w]][0] += bool(yes); per[band_of[w]][1] += 1
    fa = fake[0] / fake[1] if fake[1] else 0
    sizes = {k: len(book_words()[k]) for k in BOOKS}
    known = {}
    for k, (y, n) in per.items():
        p = y / n if n else 0
        known[k] = max(0.0, (p - fa) / (1 - fa)) if fa < 1 else 0.0  # correct for guessing
    estimate = int(round(sum(known[k] * sizes[k] for k in BOOKS), -2))
    suggest = next((k for k in BOOKS if known[k] < 0.8), 'ext')
    if uid:
        c.execute('UPDATE next_vocab_plans SET estimate=?, updated=? WHERE user_id=?', (estimate, time.time(), uid))
        c.commit()
    return {'estimate': estimate, 'suggest': suggest, 'bands': {k: round(v, 2) for k, v in known.items()},
            'guessing': fa > 0.2}, 200


def import_words(c, uid, data):
    raw = data.get('text')
    if not isinstance(raw, str) or len(raw) > 20000:
        return {'error': '内容太长了，一次最多导入约 500 个词'}, 400
    items = [x.strip() for x in re.split(r'[\n,，;；\t]+', raw) if x.strip()]
    items = [x for x in items if re.fullmatch(r"[A-Za-z][A-Za-z' -]{0,58}", x)][:500]
    if not items:
        return {'error': '没有识别到英文单词或短语，请每行一个'}, 400
    now = time.time()
    added = skipped = 0
    for x in items:
        norm = nx._norm(x)
        if c.execute('SELECT 1 FROM next_cards WHERE user_id=? AND norm=?', (uid, norm)).fetchone():
            skipped += 1
            continue
        words = len(nx.WORD.findall(x))
        hit = nx.lookup(x) if words == 1 else None
        text = hit['word'] if hit and hit['lemma'] == norm else x
        c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,rank) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid, text, norm, hit['meaning'][:300] if hit else '', '', None, 'word' if words == 1 else 'phrase', now, now, 'new', 'import',
                   hit['rank'] if hit else None))
        added += 1
    c.commit()
    return {'added': added, 'skipped': skipped}, 200


def detail(c, uid, cid):
    r = c.execute('SELECT * FROM next_cards WHERE id=? AND user_id=?', (cid, uid)).fetchone()
    if not r:
        return {'error': '记录不存在'}, 404
    hist = [dict(h) for h in c.execute('SELECT rating, created, mode FROM next_reviews WHERE card=? AND user_id=? ORDER BY created', (cid, uid))]
    return {'card': card_out(r, level=_level(c, uid), rich=True), 'history': hist, 'retention': _retention(c, uid)}, 200


# ---------- routing ----------

def get(c, uid, path, q):
    one = lambda k, d='': (q.get(k) or [d])[0]
    if path == '/api/next/vocab/test':
        return test_items(), 200
    if not uid:
        return ({'error': '请先登录'}, 401) if path.startswith('/api/next/vocab') else None
    if path == '/api/next/vocab':
        return overview(c, uid), 200
    if path == '/api/next/vocab/card':
        return detail(c, uid, int(one('id', '0') or 0))
    if path == '/api/next/review':
        return queue(c, uid), 200
    return None


def post_public(c, uid, path, data):
    if path == '/api/next/vocab/test':
        return score_test(c, uid, data)
    return None


def post(c, uid, path, data):
    if path == '/api/next/vocab/plan':
        return save_plan(c, uid, data)
    if path == '/api/next/vocab/import':
        return import_words(c, uid, data)
    if path == '/api/next/vocab/known':
        return set_known(c, uid, data)
    if path == '/api/next/review':
        return rate(c, uid, data)
    return None
