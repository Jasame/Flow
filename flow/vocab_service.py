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
import sys
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
EXAM_GROUP = {'cet4': '大学英语', 'cet6': '大学英语', 'ky': '大学英语', 'ielts': '出国留学', 'toefl': '出国留学', 'gre': '出国留学'}
# The picker shows books under these headings, in this order; a data book's own group not listed here comes last.
GROUPS = ('按词频', '中学英语', '大学英语', '英语专业', '出国留学', '学术与职场')
# Data books (专四、专八、中考、高考…): flow/corpus_data/wordbooks*.json, read in file-name order, each
#   {"notice": "...", "books": {"tem4": {"title", "group", "blurb", "basis", "words": [norm, … in study order]}}}
# FLOW_WORDBOOKS (paths joined by os.pathsep) or WORDBOOK_FILES (a list, for tests) replaces the default files.
WORDBOOK_FILES = None
BOOK_ID = re.compile(r'[a-z][a-z0-9_-]{0,23}')
LEVEL_BOOK = {'A2': 'core', 'B1': 'mid', 'B2': 'high', 'C1': 'adv'}
# 「你在准备什么考试？」 at the top of the plan page: one tap picks that exam's book (「不考试」 picks suggested_book).
# A chip shows only when its book is in the registry (the data books can be missing).
EXAM_GOALS = (('中考', 'zk'), ('高考', 'gk'), ('四级', 'cet4'), ('六级', 'cet6'), ('考研', 'ky'), ('专四', 'tem4'),
              ('专八', 'tem8'), ('雅思', 'ielts'), ('托福', 'toefl'), ('GRE', 'gre'))
CORE_SKIP = 150  # "the", "be", "of"…: everyone knows them, and a flashcard of their dictionary entry helps no one
DAILY_NEW = (5, 10, 15, 20, 30, 50, 80, 100)  # suggested; any number from 1 to DAILY_MAX is accepted
DAILY_MAX = 200
MORE_MAX = 50  # one extra batch of new words today, on request
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
_DATA = None
_EX = None
_ROOTS = None
_WA = {'mtime': None, 'index': {}}
ROOT_CLASS = {'root': '词根', 'prefix': '前缀', 'noun-forming suffix': '名词后缀', 'adjective-forming suffix': '形容词后缀',
              'verb-forming suffix': '动词后缀', 'adverb-forming suffix': '副词后缀', 'adjective- and noun-forming suffix': '后缀'}
_ROOT_ZH = None
REMIND_HOURS = tuple(range(6, 24))


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
    # 撤销: the latest rating of each learner can be taken back for ten minutes (the card as it was, and that review)
    c.execute('CREATE TABLE IF NOT EXISTS next_undo(user_id INTEGER PRIMARY KEY, card INTEGER NOT NULL, review INTEGER NOT NULL, prior TEXT NOT NULL, created REAL NOT NULL)')
    c.executescript('''
CREATE TABLE IF NOT EXISTS next_vocab_plans(user_id INTEGER PRIMARY KEY REFERENCES users(id), book TEXT NOT NULL,
 daily_new INTEGER NOT NULL DEFAULT 10, retention REAL NOT NULL DEFAULT 0.9, estimate INTEGER, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS next_cards_source ON next_cards(user_id, source, created);
CREATE INDEX IF NOT EXISTS next_reviews_card ON next_reviews(card, created);
CREATE TABLE IF NOT EXISTS next_word_examples(norm TEXT PRIMARY KEY, sentence TEXT NOT NULL, translation TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS next_reminders(user_id INTEGER PRIMARY KEY REFERENCES users(id), enabled INTEGER NOT NULL DEFAULT 0,
 hour INTEGER NOT NULL DEFAULT 20, last_sent TEXT, updated REAL NOT NULL);''')
    pcols = {r[1] for r in c.execute('PRAGMA table_info(next_vocab_plans)')}
    if 'skip_rank' not in pcols:
        c.execute('ALTER TABLE next_vocab_plans ADD COLUMN skip_rank INTEGER NOT NULL DEFAULT 0')
    if 'suggest' not in pcols:  # the book the vocabulary test recommended
        c.execute('ALTER TABLE next_vocab_plans ADD COLUMN suggest TEXT')
    if 'test_skip' not in pcols:  # what the test said may be skipped, kept so "skip known words" can be turned back on
        c.execute('ALTER TABLE next_vocab_plans ADD COLUMN test_skip INTEGER NOT NULL DEFAULT 0')
        c.execute('UPDATE next_vocab_plans SET test_skip=skip_rank')
    # review rows of deleted cards: unlink them (a new card may get the same id), keep them for statistics
    c.execute('UPDATE next_reviews SET card=-card WHERE card>0 AND NOT EXISTS (SELECT 1 FROM next_cards k WHERE k.id=next_reviews.card AND k.user_id=next_reviews.user_id)')
    c.commit()


# ---------- data ----------

def _warn(msg):
    print(f'word books: {msg}', file=sys.stderr, flush=True)


def wordbook_files():
    if WORDBOOK_FILES is not None:
        return [Path(f) for f in WORDBOOK_FILES]
    if os.getenv('FLOW_WORDBOOKS') is not None:
        return [Path(f) for f in os.environ['FLOW_WORDBOOKS'].split(os.pathsep) if f.strip()]
    return sorted((Path(__file__).resolve().parent / 'corpus_data').glob('wordbooks*.json'))


def _line(v, limit):
    return ' '.join(v.split())[:limit] if isinstance(v, str) else ''


def data_books():
    """Word books from the data files: id -> {title, group, blurb, basis, words, file}, in file order.

    A missing or broken file adds nothing; a book with a bad or taken id (a built-in book, or one from an earlier
    file) is left out. Words are checked against the dictionary in book_words(). Problems are logged, never raised."""
    global _DATA
    if _DATA is None:
        out = {}
        for f in wordbook_files():
            try:
                books = json.loads(f.read_text(encoding='utf-8'))['books']
                if not isinstance(books, dict):
                    raise ValueError('"books" is not an object')
            except FileNotFoundError:
                _warn(f'{f.name}: not found'); continue
            except (OSError, ValueError, KeyError, TypeError) as e:
                _warn(f'{f.name}: not used ({type(e).__name__}: {e})'); continue
            for bid, b in books.items():
                if not isinstance(bid, str) or not BOOK_ID.fullmatch(bid):
                    _warn(f'{f.name}: book id {bid!r} is not a short lower-case id, left out'); continue
                if bid in BOOKS or bid in EXAM_BOOKS or bid in out:
                    _warn(f"{f.name}: book id {bid!r} is already {'built in' if bid not in out else 'used by ' + out[bid]['file']}, left out"); continue
                if not isinstance(b, dict) or not _line(b.get('title'), 30) or not isinstance(b.get('words'), list):
                    _warn(f'{f.name}: {bid} has no title or no word list, left out'); continue
                words = [w.strip().lower() for w in b['words'] if isinstance(w, str) and w.strip()]
                out[bid] = {'title': _line(b['title'], 30), 'group': _line(b.get('group'), 12) or '其他词书', 'blurb': _line(b.get('blurb'), 80),
                            'basis': _line(b.get('basis'), 400), 'words': list(dict.fromkeys(words)), 'file': f.name}
        _DATA = out
    return _DATA


def book_words():
    """book id -> [(rank, word)]: plain lower-case words that have a Chinese meaning (rank: frequency rank).

    Frequency books use the reference list only (so their contents never shift); exam books use ECDICT's tags; both
    are in frequency order. Data books keep their file's study order, without the words the dictionary lacks; a data
    book left with no word is not offered at all."""
    global _BOOK
    if _BOOK is None:
        d = nx.dictionary()
        out = {k: [] for k in (*BOOKS, *EXAM_BOOKS)}
        for norm, e in d.items():
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
        for bid, b in data_books().items():
            ok = [(d[w].get('rank') or 99999, w) for w in b['words'] if re.fullmatch(r'[a-z]+(?:-[a-z]+)*', w) and (d.get(w) or {}).get('meaning')]
            if len(ok) < len(b['words']):
                kept = {w for _, w in ok}
                gone = [w for w in b['words'] if w not in kept]
                _warn(f"{b['file']}: {bid} skips {len(gone)} of {len(b['words'])} words not in the dictionary or without a meaning, e.g. {gone[:5]}")
            if ok:
                out[bid] = ok
            else:
                _warn(f"{b['file']}: {bid} has no usable word, not offered")
        _BOOK = out
    return _BOOK


def book_title(book):
    if book in BOOKS or book in EXAM_BOOKS:
        return (BOOKS.get(book) or EXAM_BOOKS.get(book))[0]
    return (data_books().get(book) or {}).get('title') or '词书'


def registry():
    """Every word book a learner can choose, grouped in GROUPS order (books keep their order inside a group):
    [{id, kind (freq | exam | data), title, group, blurb, count, size (= count), range (freq), basis (data)}]."""
    bw = book_words()
    items = ([{'id': k, 'kind': 'freq', 'title': v[0], 'group': '按词频', 'blurb': v[3], 'range': f'{v[1]}–{v[2]}'} for k, v in BOOKS.items()]
             + [{'id': k, 'kind': 'exam', 'title': v[0], 'group': EXAM_GROUP.get(k, '其他词书'), 'blurb': v[1]} for k, v in EXAM_BOOKS.items()]
             + [{'id': k, 'kind': 'data', 'title': b['title'], 'group': b['group'], 'blurb': b['blurb'], 'basis': b['basis']}
                for k, b in data_books().items() if k in bw])
    for b in items:
        b['count'] = b['size'] = len(bw[b['id']])
    order = list(GROUPS) + list(dict.fromkeys(b['group'] for b in items if b['group'] not in GROUPS))
    return sorted(items, key=lambda b: order.index(b['group']))


def book_groups(books):
    """The group headings, in order, that have at least one book."""
    return list(dict.fromkeys(b['group'] for b in books))


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


def roots(norm):
    """词根词缀 from ECDICT's word-root list: [{'part', 'meaning', 'kind'}]."""
    global _ROOTS, _ROOT_ZH
    if _ROOTS is None:
        base = Path(__file__).resolve().parent / 'corpus_data'
        try:
            _ROOTS = json.loads((base / 'wordroots-flow.json').read_text(encoding='utf-8'))['words']
        except OSError:
            _ROOTS = {}
        try:
            _ROOT_ZH = json.loads((base / 'wordroots-zh.json').read_text(encoding='utf-8'))['glosses']
        except (OSError, ValueError, KeyError):
            _ROOT_ZH = {}
    clean = lambda part: re.sub(r'(?<=[a-z-])\d', '', part)
    return [{'part': clean(r), 'meaning': _ROOT_ZH.get(m, m), 'kind': ROOT_CLASS.get(k, '后缀' if 'suffix' in k else '词缀')} for r, m, k in _ROOTS.get(norm, [])]


def brief_meaning(meaning, k=3):
    """The first part of speech and its first few senses ("n. 音高, 程度, 坡度"): enough to recognise a word while reading."""
    first = (meaning or '').split('；')[0]
    pos, sep, rest = first.partition('. ')
    if not sep or len(pos) > 6:
        pos, rest = '', first
    senses = [x.strip() for x in rest.split(', ') if x.strip()][:k]
    return ((pos + '. ') if pos else '') + ', '.join(senses)


def short_meaning(meaning, n=2):
    """First parts of speech of a dictionary meaning, for compact lists; cut at a gloss boundary, never mid-gloss."""
    s = '；'.join(meaning.split('；')[:n])
    if len(s) > 60:
        s = s[:60]
        cut = max(s.rfind(', '), s.rfind('；'))
        s = s[:cut] if cut > 20 else s
    return s.rstrip(' ,，；;')


EXAMPLE_SPLIT = re.compile(r"^([^\u4e00-\u9fff]+?[.?!])\s*([\u4e00-\u9fff].*)?$")


def extra_examples(c, norm):
    """When Flow's materials never use a word: the reference list's own example, else an AI example cached site-wide."""
    out = []
    m = EXAMPLE_SPLIT.match((nx.dictionary().get(norm) or {}).get('example') or '')
    if m and re.search(r'(?<![A-Za-z])' + re.escape(norm[:max(3, len(norm) - 2)]), m.group(1), re.I):
        out.append({'pack': None, 'i': None, 'text': m.group(1).strip(), 'form': norm, 'title': '词典例句', 'zh': (m.group(2) or '').strip(), 'audio': 0})
    if c is not None and not out:
        r = c.execute('SELECT sentence, translation FROM next_word_examples WHERE norm=?', (norm,)).fetchone()
        if r:
            out.append({'pack': None, 'i': None, 'text': r['sentence'], 'form': norm, 'title': 'AI 例句', 'zh': r['translation'], 'audio': 0, 'ai': True})
    return out


def word_audio(norm):
    """{accent: [sprite, start, end]} for a word's pre-generated pronunciation (tools/gen_word_audio.py)."""
    f = __import__('media').path('words/index.json', WORD_AUDIO_DIR / 'index.json')  # kept in step with R2 when in use
    try:
        m = f.stat().st_mtime
    except (OSError, AttributeError):
        return {}
    if _WA['mtime'] != m:
        _WA['index'], _WA['mtime'] = json.loads(f.read_text()), m
    return {a: _WA['index'][a][norm] for a in ACCENTS if norm in _WA['index'].get(a, {})}


def word_audio_file(accent, sprite):
    if accent not in ACCENTS or not re.fullmatch(r'[wxpb]\d{3}', sprite or ''):
        return None
    return __import__('media').path(f'words/{accent}/{sprite}.m4a', WORD_AUDIO_DIR / accent / f'{sprite}.m4a')


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
    """How to review this item now: recognise (see the word), recall (meaning + gapped sentence), spell (hear and type).
    Mistakes are reviewed in their own way: fix (rewrite the corrected phrase), question (answer again), sound (say it)."""
    if r['kind'] in ('fix', 'question', 'sound'):
        return r['kind']
    if r['kind'] != 'word':
        return 'cloze' if r['context'] and r['text'].lower() in r['context'].lower() else 'recall'
    s = r['stability'] or 0
    if r['state'] != 'review' or s < RECALL_FROM:
        return 'recognize'
    return 'spell' if s >= SPELL_FROM else 'recall'


def card_out(r, now=None, level=None, rich=False, c=None):
    out = {k: r[k] for k in ('id', 'text', 'meaning', 'context', 'pack', 'kind', 'created', 'due', 'reps', 'lapses', 'state',
                             'stability', 'difficulty', 'last', 'source', 'known')}
    rv = recall_now(r, now)
    out['recall'] = None if rv is None else round(rv, 3)
    out['mastered'] = bool(r['known'] or (r['stability'] or 0) >= MASTERED)
    if r['kind'] == 'word' and r['source'] in ('book', 'import'):
        entry = nx.dictionary().get(r['norm'])
        if entry and entry['meaning']:
            out['meaning'] = entry['meaning'][:300]
    if rich:
        entry = nx.dictionary().get(r['norm']) if r['kind'] == 'word' else None
        out['phonetic'] = entry['phonetic'] if entry else ''
        out['mode'] = mode(r)
        out['examples'] = examples(r['norm'], level or 'B1', 2, r['context']) if r['kind'] == 'word' else []
        if r['kind'] == 'word' and not out['examples']:
            out['examples'] = extra_examples(c, r['norm'])
        out['audio'] = word_audio(r['norm']) if r['kind'] == 'word' else {}
        out['roots'] = roots(r['norm']) if r['kind'] == 'word' else []
        if r['source'] == 'mistake':
            out['extra'] = json.loads(r['extra'] or '{}') if 'extra' in r.keys() else {}
            norm = r['norm'] or ''
            if r['kind'] == 'question' and norm.startswith('q:') and c is not None:
                out['passage'] = nx.excerpt(c, r['pack'], out['extra'].get('evidence') or r['meaning'] or '')
            elif r['kind'] == 'question' and norm.startswith('wq:'):
                # starting with the question after the one that was missed, so review never repeats the miss first
                out['variant'] = __import__('word_links').variant(norm[3:], out['extra'].get('item', -1) + 1 + (r['reps'] or 0))
            elif r['kind'] == 'question' and norm.startswith('gq:') and c is not None and r['node']:
                out['variant'] = __import__('grammar_bank').variant(c, r['node'], int(norm[3:]) if norm[3:].isdigit() else -1, r['reps'] or 0)
            out['skill'] = r['skill'] if 'skill' in r.keys() else None
            node = r['node'] if 'node' in r.keys() else None
            out['node'] = {'id': node, 'title': nx.nodes_meta(c).get(node, {}).get('title', node)} if node and c is not None else None
            if r['kind'] == 'sound':
                out['audio'] = word_audio(r['norm'][6:]) if r['norm'].startswith('sound:') else {}
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
    skip = _skip_below(p['book'], p.get('skip_rank'))
    added = 0
    for rank, w in book_words()[p['book']]:
        if w in have or (skip and rank <= skip):
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
    return {'items': [card_out(r, now, level, rich=True, c=c) for r in picked], **counts(c, uid, now)}


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
    at = data.get('at')  # reviews done offline are synced later with the time they happened
    if isinstance(at, (int, float)) and not isinstance(at, bool) and now - 3 * 86400 <= at <= now + 60 and at >= (r['last'] or 0):
        now = float(min(at, now))
    m = data.get('mode') if data.get('mode') in ('recognize', 'recall', 'spell', 'cloze') else None
    ms = data.get('ms') if isinstance(data.get('ms'), int) and 0 <= data.get('ms') < 3600000 else None
    elapsed = (now - r['last']) / fsrs.DAY if r['last'] else None
    n = fsrs.review(dict(r), rating, now, _retention(c, uid))
    known, outcome = r['known'], _lifecycle(c, uid, r, rating, n, now)
    if outcome in ('passed', 'reread'):
        known = 1  # done with: it leaves the review queue (the same mistake made again brings it back)
    c.execute('UPDATE next_cards SET state=?, step=?, stability=?, difficulty=?, last=?, due=?, lapses=?, interval=?, reps=reps+1, known=? WHERE id=?',
              (n['state'], n['step'], n['stability'], n['difficulty'], n['last'], n['due'], n['lapses'], n['interval'], known, r['id']))
    rid = c.execute('INSERT INTO next_reviews(user_id,card,rating,created,mode,ms,elapsed,stability) VALUES(?,?,?,?,?,?,?,?)',
                    (uid, r['id'], rating, now, m, ms, elapsed, n['stability'])).lastrowid
    c.execute('INSERT OR REPLACE INTO next_undo VALUES(?,?,?,?,?)', (uid, r['id'], rid, json.dumps({k: r[k] for k in UNDO_FIELDS}), time.time()))
    c.commit()
    r2 = c.execute('SELECT * FROM next_cards WHERE id=?', (r['id'],)).fetchone()
    return {'card': card_out(r2, now), 'outcome': outcome, **counts(c, uid, now)}, 200


UNDO_FIELDS = ('state', 'step', 'stability', 'difficulty', 'last', 'due', 'lapses', 'interval', 'reps', 'known')
UNDO_SECONDS = 600


def undo(c, uid, data):
    """Take back the learner's latest rating (a slip of the finger): the card as it was, that review gone. Only the
    latest, only within ten minutes, only for the card named."""
    u = c.execute('SELECT * FROM next_undo WHERE user_id=?', (uid,)).fetchone()
    try:
        card = int(data.get('id') or 0)
    except (TypeError, ValueError):
        card = 0
    if not u or u['card'] != card or time.time() - u['created'] > UNDO_SECONDS:
        return {'error': '这一张已经不能撤销了'}, 409
    prior = json.loads(u['prior'])
    c.execute('UPDATE next_cards SET ' + ', '.join(f'{k}=?' for k in UNDO_FIELDS) + ' WHERE id=? AND user_id=?',
              (*[prior[k] for k in UNDO_FIELDS], card, uid))
    c.execute('DELETE FROM next_reviews WHERE id=? AND user_id=?', (u['review'], uid))
    c.execute('DELETE FROM next_undo WHERE user_id=?', (uid,))
    c.commit()
    now = time.time()
    return {'card': card_out(c.execute('SELECT * FROM next_cards WHERE id=?', (card,)).fetchone(), now), **counts(c, uid, now)}, 200


MISSES_A_DAY = 2  # a card missed this many times today waits for tomorrow: a review session always ends


def _lifecycle(c, uid, r, rating, n, now):
    """Each kind of item has its own way out, so nothing goes round in circles (changes n in place).

    - any card: missed a second time today -> tomorrow, not again in a few minutes;
    - a reading question got wrong: redone once with its passage; right -> passed (it leaves the queue); wrong
      again -> put down with a pointer back to the text (re-reading helps, drilling the same question does not);
    - a grammar question got wrong: reviewed on a different question of the same point each time; two right in
      a row -> passed (the point's own spaced re-checks take over).
    Returns what happened: None, 'tomorrow', 'later', 'passed', 'reread' or 'once-more'."""
    norm = r['norm'] or ''
    misses = c.execute("SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND card=? AND rating='again' AND created>=?",
                       (uid, r['id'], _day_start(now))).fetchone()[0] + (rating == 'again')
    if r['source'] == 'mistake' and r['kind'] == 'question' and norm.startswith('q:'):
        if rating != 'again':
            return 'passed'
        if c.execute("SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND card=? AND rating='again'", (uid, r['id'])).fetchone()[0]:
            return 'reread'
        n.update(state='review', due=now + 2 * fsrs.DAY)  # once more, the day after tomorrow, with the passage
        return 'later'
    if r['source'] == 'mistake' and r['kind'] == 'question' and norm.startswith(('gq:', 'wq:')) and rating != 'again':
        last = c.execute('SELECT rating FROM next_reviews WHERE user_id=? AND card=? ORDER BY id DESC LIMIT 1', (uid, r['id'])).fetchone()
        return 'passed' if last and last[0] in ('good', 'easy') else 'once-more'
    if rating == 'again' and misses >= MISSES_A_DAY:
        n['due'] = max(n['due'], _day_start(now) + fsrs.DAY + 4 * 3600)  # tomorrow morning
        return 'tomorrow'
    return None


def more_new(c, uid, data):
    """Learn more new words today than the plan says: one extra batch now, on top of today's (the plan is unchanged)."""
    n = data.get('n', 10)
    if type(n) is not int or not 1 <= n <= MORE_MAX:
        return {'error': f'一次可以多学 1–{MORE_MAX} 个'}, 400
    p = plan(c, uid)
    if not p or p['book'] not in book_words():
        return {'error': '先选一本词书'}, 400
    waiting = c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND source='book' AND state='new' AND known=0", (uid,)).fetchone()[0]
    if waiting >= DAILY_MAX:
        return {'error': f'已经有 {waiting} 个新词没学，先学完它们吧'}, 400
    now = time.time()
    have = {r[0] for r in c.execute('SELECT norm FROM next_cards WHERE user_id=?', (uid,))}
    d = nx.dictionary()
    skip = _skip_below(p['book'], p.get('skip_rank'))
    added = 0
    for rank, w in book_words()[p['book']]:
        if w in have or (skip and rank <= skip):
            continue
        e = d[w]
        c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,rank) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid, e['word'], w, e['meaning'][:300], '', None, 'word', now, now, 'new', 'book', rank))
        added += 1
        if added >= n:
            break
    c.commit()
    return {'added': added, **counts(c, uid, now)}, 200


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

def _skip_below(book, skip_rank):
    """Frequency rank up to which a plan leaves a book's words out: the everyday words of the first frequency book;
    in exam and data books, the bands the vocabulary test showed as known (skip_rank); other frequency books are
    chosen by level and skip nothing."""
    if book == 'core':
        return CORE_SKIP
    return 0 if book in BOOKS else (skip_rank or 0)


def _skipped(book, skip_rank, force=False):
    """How many words a plan leaves out (see _skip_below)."""
    skip = _skip_below(book, skip_rank)
    return sum(1 for r, _ in book_words().get(book, ()) if r <= skip) if skip else 0


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
    skip_rank = (p.get('skip_rank') or 0) if p else 0
    if p and p['book'] in book_words():
        words = book_words()[p['book']]
        studied = {r['norm'] for r in rows if r['state'] != 'new' or r['known']}  # 已学: reviewed at least once, or marked known
        started = sum(1 for _, w in words if w in studied)
        skipped = _skipped(p['book'], skip_rank)
        left = max(0, len(words) - started - skipped)
        book = {'id': p['book'], 'title': book_title(p['book']), 'size': len(words), 'started': started, 'skipped': skipped,
                'finish': nx._day(now + math.ceil(left / max(1, p['daily_new'])) * fsrs.DAY) if left else None}
    books = registry()
    for b in books:  # how many words a plan would skip in each book, for the estimate on the plan page
        b['skippable'] = _skipped(b['id'], ((p.get('test_skip') or skip_rank) if p else 0) or 0, force=True)
    ids = {b['id'] for b in books}
    return {'plan': p, 'book': book, 'books': books, 'groups': book_groups(books), 'daily_new_options': list(DAILY_NEW), 'retention_options': list(RETENTION),
            'exam_goals': [{'title': t, 'book': b} for t, b in EXAM_GOALS if b in ids],
            'suggested_book': (p.get('suggest') if p and p.get('suggest') in book_words() else None) or LEVEL_BOOK.get(_level(c, uid), 'mid'), 'mastered': mastered, 'learning': learning, 'total': len(rows),
            'forecast': forecast, 'calendar': calendar, 'reminder': reminder(c, uid), **counts(c, uid, now)}


def save_plan(c, uid, data):
    book = data.get('book')
    if not isinstance(book, str) or book not in book_words():  # built-in books, and the data books that have words
        return {'error': '请选择词书'}, 400
    daily = data.get('daily_new', 10)
    retention = data.get('retention', 0.9)
    if type(daily) is not int or not 1 <= daily <= DAILY_MAX or retention not in RETENTION:
        return {'error': f'每天新词可以是 1–{DAILY_MAX} 个；记住率请从选项里选'}, 400
    now = time.time()
    old = plan(c, uid)
    if old and old['book'] != book:
        # Words the old book put into today's queue but that were never studied make way for the new book's words.
        gone = [r[0] for r in c.execute("SELECT id FROM next_cards WHERE user_id=? AND source='book' AND state='new' AND reps=0 AND known=0", (uid,))]
        for cid in gone:
            c.execute('UPDATE next_reviews SET card=-card WHERE card=? AND user_id=?', (cid, uid))
            c.execute('DELETE FROM next_cards WHERE id=?', (cid,))
    c.execute('''INSERT INTO next_vocab_plans(user_id,book,daily_new,retention,created,updated) VALUES(?,?,?,?,?,?)
                 ON CONFLICT(user_id) DO UPDATE SET book=excluded.book, daily_new=excluded.daily_new, retention=excluded.retention, updated=excluded.updated''',
              (uid, book, daily, retention, now, now))
    if data.get('skip_known') is False:
        c.execute('UPDATE next_vocab_plans SET skip_rank=0 WHERE user_id=?', (uid,))
    elif data.get('skip_known') is True:
        c.execute('UPDATE next_vocab_plans SET skip_rank=test_skip WHERE user_id=?', (uid,))
    c.commit()
    return overview(c, uid), 200


BEYOND = 20200  # the frequency books end here; the test's last band samples rarer exam words


def beyond_words():
    """GRE words rarer than the frequency books: the vocabulary test's hardest band."""
    return [w for r, w in book_words()['gre'] if r > BEYOND]


def test_items(seed=None):
    """About 46 words: 8 sampled from each book band plus 6 made-up words, shuffled."""
    rng = random.Random(seed)
    real = nx.dictionary()
    items = []
    for k in BOOKS:
        words = book_words()[k]
        items += [w for _, w in rng.sample(words, min(8, len(words)))]
    deep = beyond_words()
    items += rng.sample(deep, min(8, len(deep)))
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
    deep = beyond_words()
    band_of.update({w: 'beyond' for w in deep if w not in band_of})
    per = {k: [0, 0] for k in (*BOOKS, 'beyond')}
    fake = [0, 0]
    for w, yes in answers.items():
        w = str(w).lower()[:40]
        if w in PSEUDO and w not in real:
            fake[0] += bool(yes); fake[1] += 1
        elif w in band_of:
            per[band_of[w]][0] += bool(yes); per[band_of[w]][1] += 1
    fa = fake[0] / fake[1] if fake[1] else 0
    sizes = {**{k: len(book_words()[k]) for k in BOOKS}, 'beyond': len(deep)}
    known = {}
    for k, (y, n) in per.items():
        p = y / n if n else 0
        known[k] = max(0.0, (p - fa) / (1 - fa)) if fa < 1 else 0.0  # correct for guessing
    estimate = int(round(sum(known[k] * sizes[k] for k in sizes), -2))
    suggest = next((k for k in BOOKS if known[k] < 0.8), None)
    # Past the frequency books: GRE when the rare band is already half known, otherwise the last frequency book.
    ceiling = suggest is None and known['beyond'] >= 0.5
    suggest = suggest or ('gre' if ceiling else 'ext')
    skip_rank = 0
    for k, (_, lo, hi, _) in BOOKS.items():  # exam books skip every band below the first one not reliably known
        if known[k] < 0.85:
            break
        skip_rank = hi
    if uid:
        c.execute('UPDATE next_vocab_plans SET estimate=?, skip_rank=?, test_skip=?, suggest=?, updated=? WHERE user_id=?',
                  (estimate, skip_rank, skip_rank, suggest, time.time(), uid))
        c.commit()
        ar = __import__('ability_radar')  # the vocabulary test is the radar's vocabulary assessment
        ar.record(c, uid, 'vocab', ar.vocab_index(estimate), {'estimate': estimate})
    return {'estimate': estimate, 'suggest': suggest, 'bands': {k: round(v, 2) for k, v in known.items()}, 'ceiling': ceiling,
            'titles': {**{b['id']: b['title'] for b in registry()}, 'beyond': '超纲难词'},
            'guessing': fa > 0.2, 'skip_rank': skip_rank}, 200


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
    return {'card': card_out(r, level=_level(c, uid), rich=True, c=c), 'history': hist, 'retention': _retention(c, uid)}, 200


# ---------- reading: words before and after ----------

def preread(c, uid, hard, limit=5):
    """Words to glance at before reading: above the learner's level, most useful first, not already being learned."""
    have = {r[0] for r in c.execute('SELECT norm FROM next_cards WHERE user_id=?', (uid,))} if uid else set()
    d = nx.dictionary()
    out, seen = [], set()
    for form, info in sorted(hard.items(), key=lambda kv: kv[1]['rank']):
        hit = nx.lookup(form)
        if not hit or hit['lemma'] in seen or hit['lemma'] in have or not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', hit['lemma']):
            continue
        seen.add(hit['lemma'])
        e = d.get(hit['lemma']) or {}
        out.append({'word': hit['lemma'], 'form': form, 'phonetic': e.get('phonetic', ''), 'meaning': brief_meaning(e.get('meaning', '')),
                    'audio': word_audio(hit['lemma'])})
        if len(out) >= limit:
            break
    return out


def add_many(c, uid, data):
    """Add several words from one material at once (the pre-reading list, or the words looked up while reading)."""
    items = data.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        return {'error': '一次最多加 30 个词'}, 400
    pack = data.get('pack') if isinstance(data.get('pack'), str) and len(data['pack']) <= 80 else None
    min_rank = data.get('min_rank') if isinstance(data.get('min_rank'), int) else 0  # dictation: skip words everyone knows
    d = nx.dictionary()
    now = time.time()
    added = skipped = 0
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get('word'), str):
            continue
        word = it['word'].strip()[:40]
        hit = nx.lookup(word) if nx.WORD.fullmatch(word) else None
        if not hit:
            skipped += 1
            continue
        norm = hit['lemma']
        sentence = it.get('sentence') if isinstance(it.get('sentence'), str) else ''
        sentence = ' '.join(sentence.split())[:600]
        if c.execute('SELECT 1 FROM next_cards WHERE user_id=? AND norm=?', (uid, norm)).fetchone():
            skipped += 1
            continue
        e = d.get(norm) or {}
        if min_rank and (e.get('rank') or 99999) < min_rank:
            skipped += 1
            continue
        c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,rank) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid, e.get('word', norm), norm, (e.get('meaning') or '')[:300], sentence, pack, 'word', now, now, 'new', 'saved', e.get('rank')))
        added += 1
    c.commit()
    return {'added': added, 'skipped': skipped, **counts(c, uid, now)}, 200


def example_messages(words, level):
    """The chat messages that ask for one example sentence (and its translation) per word; shared by the learner's
    request (ai_examples) and the batch that writes them ahead of time (fill_examples.py)."""
    d = nx.dictionary()
    system = '你是英语词典编辑。为每个单词写一个自然、常用、贴近生活的英文例句（10–20 词，' + level + ' 学习者能读懂），并给出准确的中文翻译。只输出 JSON。'
    user = ('单词（附中文义项）：\n' + '\n'.join(f'{w}：{short_meaning(d[w]["meaning"])}' for w in words) +
            '\n\n输出 JSON：{"examples":[{"word":"单词原形","sentence":"英文例句（必须包含这个词或它的变形）","translation":"中文翻译"}]}')
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def example_results(raw, words):
    """{word: {sentence, translation}} from the model's JSON: only sentences that really use the word (or a form of it)."""
    from lab_service import text as clean_text
    out = {}
    for e in (raw.get('examples') if isinstance(raw, dict) else None) or []:
        if not isinstance(e, dict) or e.get('word') not in words or not isinstance(e.get('sentence'), str):
            continue
        sent = clean_text(e['sentence'], 8, 240)
        lemmas = {(nx.lookup(t) or {}).get('lemma') for t in nx.WORD.findall(sent)}
        if e['word'] in lemmas or e['word'] in sent.lower():
            out[e['word']] = {'sentence': sent, 'translation': clean_text(e.get('translation') or '', 0, 240)}
    return out


def save_examples(c, made, now=None):
    now = now or time.time()
    for w, e in made.items():
        c.execute('INSERT OR IGNORE INTO next_word_examples VALUES(?,?,?,?)', (w, e['sentence'], e['translation'], now))
    c.commit()


def needs_example(c, w):
    """No sentence from Flow's texts, no dictionary example and no AI example cached yet."""
    return not examples(w) and not extra_examples(c, w)


def ai_examples(c, uid, data):
    """One AI call writes example sentences for up to 8 words that no material uses; cached for everyone."""
    from lab_service import run_job
    from chat_service import request_model
    words = [w for w in (data.get('words') or []) if isinstance(w, str) and re.fullmatch(r'[a-z]+(?:-[a-z]+)*', w)][:8]
    d = nx.dictionary()
    words = [w for w in dict.fromkeys(words) if w in d and needs_example(c, w)]
    if not words:
        return {'examples': {}}, 200

    def convert(raw):
        out = example_results(raw, words)
        if not out:
            raise ValueError('no usable examples')
        return out

    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-examples', 'vocab', 'vocabulary', {'words': words},
                             lambda: request_model(example_messages(words, _level(c, uid))), convert)
    if status != 200:
        return result, status
    save_examples(c, result['result'])
    made = {w: [{'pack': None, 'i': None, 'text': e['sentence'], 'form': w, 'title': 'AI 例句', 'zh': e['translation'], 'audio': 0, 'ai': True}]
            for w, e in result['result'].items()}
    return {'examples': made, 'remaining': result.get('remaining')}, 200


def record_use(c, uid, uses, now=None):
    """A studied word used in writing: used correctly counts as a successful review, misused brings it back today."""
    now = now or time.time()
    for u in uses:
        r = c.execute("SELECT * FROM next_cards WHERE user_id=? AND norm=? AND kind='word'", (uid, u['word'])).fetchone()
        if not r:
            continue
        if u['ok']:
            if r['state'] == 'review' and now - (r['last'] or 0) > 12 * 3600:
                n = fsrs.review(dict(r), 'good', now, _retention(c, uid))
                c.execute('UPDATE next_cards SET state=?, step=?, stability=?, difficulty=?, last=?, due=?, lapses=?, interval=?, reps=reps+1 WHERE id=?',
                          (n['state'], n['step'], n['stability'], n['difficulty'], n['last'], n['due'], n['lapses'], n['interval'], r['id']))
            c.execute('INSERT INTO next_reviews(user_id,card,rating,created,mode) VALUES(?,?,?,?,?)', (uid, r['id'], 'used', now, 'writing'))
        else:
            if r['due'] > now:
                c.execute('UPDATE next_cards SET due=? WHERE id=?', (now, r['id']))
            c.execute('INSERT INTO next_reviews(user_id,card,rating,created,mode) VALUES(?,?,?,?,?)', (uid, r['id'], 'misused', now, 'writing'))
    c.commit()


# ---------- reminders ----------

def reminder(c, uid):
    r = c.execute('SELECT enabled, hour, last_sent FROM next_reminders WHERE user_id=?', (uid,)).fetchone()
    cols = {x[1] for x in c.execute('PRAGMA table_info(users)')}
    email = c.execute('SELECT email FROM users WHERE id=?', (uid,)).fetchone() if 'email' in cols else None
    return {'enabled': bool(r and r['enabled']), 'hour': r['hour'] if r else 20, 'has_email': bool(email and email[0])}


def set_reminder(c, uid, data):
    hour = data.get('hour', 20)
    if hour not in REMIND_HOURS:
        return {'error': '提醒时间不正确'}, 400
    enabled = bool(data.get('enabled'))
    if enabled and not reminder(c, uid)['has_email']:
        return {'error': '先在账号设置里绑定邮箱，才能收到提醒邮件；也可以用「加到手机日历」'}, 400
    c.execute('INSERT INTO next_reminders(user_id,enabled,hour,updated) VALUES(?,?,?,?) '
              'ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled, hour=excluded.hour, updated=excluded.updated',
              (uid, int(enabled), hour, time.time()))
    c.commit()
    return reminder(c, uid), 200


def send_reminders(c, now=None, send=None):
    """Called every few minutes: email learners whose reminder hour has come and who have reviews or new words waiting."""
    import os
    now = now or time.time()
    local = datetime.datetime.fromtimestamp(now, nx.TZ)
    today = local.date().isoformat()
    origin = os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').rstrip('/')
    if send is None:
        from account_service import mail as send
    if 'email' not in {x[1] for x in c.execute('PRAGMA table_info(users)')}:
        return 0
    rows = c.execute("SELECT r.user_id, u.email, u.username FROM next_reminders r JOIN users u ON u.id=r.user_id "
                     "WHERE r.enabled=1 AND r.hour=? AND (r.last_sent IS NULL OR r.last_sent<?) AND u.email IS NOT NULL AND u.email!=''",
                     (local.hour, today)).fetchall()
    sent = 0
    for r in rows:
        introduce(c, r['user_id'], now)
        n = counts(c, r['user_id'], now)
        c.execute('UPDATE next_reminders SET last_sent=? WHERE user_id=?', (today, r['user_id']))
        c.commit()
        if not n['due'] and not n['new']:
            continue
        text = (f"{r['username']}，你好：\n\n今天有 {n['due']} 个单词该复习了" + (f"，还有 {n['new']} 个新词" if n['new'] else '') +
                f"，大约 {n['minutes']} 分钟。\n记忆曲线到点了，现在复习效果最好：{origin}/#/review\n\n"
                "不想再收到提醒，可以在「单词 → 调整计划」里关掉。\n—— 语流 Flow")
        try:
            send(r['email'], f"语流 · 今天有 {n['due'] + n['new']} 个单词等你", text)
            sent += 1
        except Exception:
            pass  # a mail outage must not stop the loop; tomorrow is another try
    return sent


def ics(hour, kind='vocab', minutes=10):
    """A daily calendar event as a reminder that works on any phone, with no app or email needed.
    kind 'vocab' is the word review alone; 'plan' is the whole daily plan (words, today's material, grammar re-checks)."""
    import os
    hour = hour if hour in REMIND_HOURS else 20
    minutes = minutes if minutes in (5, 10, 15, 20, 30) else 10
    origin = os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').rstrip('/')
    start = datetime.datetime.now(nx.TZ).replace(hour=hour, minute=0, second=0, microsecond=0)
    utc = start.astimezone(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if kind == 'plan':
        uid, length, summary, url = f'flow-plan-{hour}', minutes, f'语流：今天的学习（约 {minutes} 分钟）', f'{origin}/#/'
        desc, alarm = f'打开今天的计划：到期的单词、今天这篇材料、该复习的语法点，按顺序做完就好。{url}', '语流：今天的学习'
    else:
        uid, length, summary, url = f'flow-vocab-{hour}', 10, '语流：背单词（约 10 分钟）', f'{origin}/#/review'
        desc, alarm = f'按遗忘曲线复习今天到期的单词：{url}', '语流：该复习单词了'
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Flow//daily reminder//ZH', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'BEGIN:VEVENT',
             f'UID:{uid}@flow', f'DTSTAMP:{stamp}', f'DTSTART:{utc}', f'DURATION:PT{length}M', 'RRULE:FREQ=DAILY',
             f'SUMMARY:{summary}', f'URL:{url}', f'DESCRIPTION:{desc}',
             'BEGIN:VALARM', 'ACTION:DISPLAY', f'DESCRIPTION:{alarm}', 'TRIGGER:PT0M', 'END:VALARM', 'END:VEVENT', 'END:VCALENDAR']
    return '\r\n'.join(_fold(x) for x in lines) + '\r\n'


def _fold(line, limit=75):
    """RFC 5545 line folding: at most 75 octets per line, continuation lines start with a space, never inside a character."""
    out, cur = [], ''
    for ch in line:
        if len((cur + ch).encode()) > (limit if not out else limit - 1):
            out.append(cur); cur = ''
        cur += ch
    out.append(cur)
    return '\r\n '.join(out)


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
    if path == '/api/next/vocab/add':
        return add_many(c, uid, data)
    if path == '/api/next/vocab/examples':
        return ai_examples(c, uid, data)
    if path == '/api/next/vocab/reminder':
        return set_reminder(c, uid, data)
    if path == '/api/next/vocab/import':
        return import_words(c, uid, data)
    if path == '/api/next/vocab/known':
        return set_known(c, uid, data)
    if path == '/api/next/vocab/more':
        return more_new(c, uid, data)
    if path == '/api/next/review':
        return rate(c, uid, data)
    if path == '/api/next/review/undo':
        return undo(c, uid, data)
    return None
