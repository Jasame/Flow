"""Exam practice: a timed mixed set at the difficulty of 中考, 高考, CET-4, CET-6, 考研, 专四, 专八 or IELTS, built only from
Flow's own content (an exam shows only when its word book is there: 中考、高考、专四、专八 are data books).

Three parts: words from that exam's list (ECDICT tags), grammar points of that exam's levels (the 44-point bank), and
one original reading passage at the exam's level with its questions. It is practice at the right difficulty, not a past
paper, and the score is not converted to an exam score. Grammar answers are evidence like any other check (a miss goes
to the mistake book and the point to fix); missed words can be added to the word cards in one tap.
"""
import json, random, secrets, time

import next_service as nx
import grammar_bank as GB

EXAMS = {  # id -> title, word book (ECDICT tag or data book), grammar levels, reading level, suggested minutes, blurb
    'zk': {'title': '中考英语', 'book': 'zk', 'levels': ('A2',), 'reading': 'A2', 'minutes': 12,
           'blurb': '中考大纲词汇、基础语法、一篇 A2 阅读'},
    'gk': {'title': '高考英语', 'book': 'gk', 'levels': ('A2', 'B1'), 'reading': 'B1', 'minutes': 15,
           'blurb': '高考大纲词汇、基础到中级语法、一篇 B1 阅读'},
    'cet4': {'title': '大学英语四级', 'book': 'cet4', 'levels': ('A2', 'B1'), 'reading': 'B1', 'minutes': 15,
             'blurb': '四级大纲词汇、基础到中级语法、一篇 B1 阅读'},
    'cet6': {'title': '大学英语六级', 'book': 'cet6', 'levels': ('B1', 'B2'), 'reading': 'B2', 'minutes': 18,
             'blurb': '六级大纲词汇、中级到中高级语法、一篇 B2 阅读'},
    'ky': {'title': '考研英语', 'book': 'ky', 'levels': ('B2', 'C1'), 'reading': 'C1', 'minutes': 20,
           'blurb': '考研大纲词汇、中高级到高级语法、一篇 C1 阅读'},
    'tem4': {'title': '英语专业四级', 'book': 'tem4', 'levels': ('B1', 'B2'), 'reading': 'B2', 'minutes': 18,
             'blurb': '专四词汇（按考纲词汇量编，不是官方词表）、中级到中高级语法、一篇 B2 阅读'},
    'tem8': {'title': '英语专业八级', 'book': 'tem8', 'levels': ('B2', 'C1'), 'reading': 'C1', 'minutes': 20,
             'blurb': '专八词汇（按考纲词汇量编，不是官方词表）、中高级到高级语法、一篇 C1 阅读'},
    'ielts': {'title': '雅思', 'book': 'ielts', 'levels': ('B1', 'B2', 'C1'), 'reading': 'B2', 'minutes': 18,
              'blurb': '雅思常考词汇、中级到高级语法、一篇 B2 阅读'},
}
VOCAB_N, GRAMMAR_N = 10, 8
# Reading: two passages, the first two questions of each (the paper is 「阅读 2 篇短文，4 题」 and timed for that).
# Materials now carry up to four questions (r27 content line); the first two are the original ones and never move.
READING_Q = 2
SKIP_COMMON = 300  # the most frequent words of every list ("about", "use"): knowing them says nothing about the exam
PAPER_TTL = 2 * 86400
NOTE = '按考试难度出的练习题，全部是原创内容，不是真题；分数只用来看自己的变化，不能换算成考试分数。'


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS next_exam_papers(id TEXT PRIMARY KEY, user_id INTEGER, exam TEXT NOT NULL,
      content TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS next_exam_results(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), exam TEXT NOT NULL,
      paper TEXT NOT NULL UNIQUE, score INTEGER NOT NULL, total INTEGER NOT NULL, parts TEXT NOT NULL, seconds INTEGER NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS next_exam_results_user ON next_exam_results(user_id, exam, created);''')


def history(c, uid, exam, limit=8):
    if not uid:
        return []
    rows = c.execute('SELECT score, total, parts, seconds, created FROM next_exam_results WHERE user_id=? AND exam=? ORDER BY created DESC LIMIT ?',
                     (uid, exam, limit)).fetchall()
    return [{'score': r['score'], 'total': r['total'], 'pct': round(100 * r['score'] / r['total']) if r['total'] else 0,
             'parts': json.loads(r['parts']), 'seconds': r['seconds'], 'created': r['created']} for r in rows][::-1]


def overview(c, uid):
    import vocab_service as vs
    books = vs.book_words()
    plan = vs.plan(c, uid) if uid else None
    import exam_sprint as sp  # 考试冲刺: the learner's exam on top, with its countdown, score trend and question types
    g = sp.goal(c, uid)
    return {'note': NOTE, 'types_note': sp.TYPES_NOTE, 'plan': {k: plan[k] for k in ('book', 'daily_new', 'retention')} if plan else None,
            'goal': g, 'countdown': sp.countdown(c, uid, g=g) if g else None, 'signed_in': bool(uid),
            'exams': [{'id': k, 'title': e['title'], 'short': sp.short(k), 'blurb': e['blurb'], 'minutes': e['minutes'], 'words': len(books.get(e['book'], [])),
                       'book': e['book'], 'book_title': vs.book_title(e['book']), 'history': history(c, uid, k), 'trend': sp.trend(c, uid, k),
                       'types': sp.type_list(c, uid, k)} for k, e in EXAMS.items() if e['book'] in books]}, 200


def _vocab(rnd, book, n):
    import vocab_service as vs
    d = nx.dictionary()
    words = [w for _, w in vs.book_words().get(book, [])][SKIP_COMMON:]
    if len(words) < n * 4:
        return []
    picked, seen = [], set()
    for w in rnd.sample(words, min(len(words), n * 6)):
        m = vs.brief_meaning(d[w]['meaning'], 2)
        if not m or m in seen:
            continue
        picked.append((w, m)); seen.add(m)
        if len(picked) == n:
            break
    pos = lambda m: m.split('. ')[0] if '. ' in m else ''
    items = []
    for w, m in picked:
        # Wrong options of the same part of speech, so "the only adjective" never gives the answer away.
        wrong, other = [], []
        for x in rnd.sample(words, 120):
            mx = vs.brief_meaning(d[x]['meaning'], 2)
            if x == w or not mx or mx == m or mx in wrong or mx in other:
                continue
            (wrong if pos(mx) == pos(m) else other).append(mx)
            if len(wrong) == 3:
                break
        wrong = (wrong + other)[:3]
        options = wrong + [m]
        rnd.shuffle(options)
        items.append({'word': d[w]['word'], 'phonetic': d[w].get('phonetic') or '', 'options': options, 'answer': options.index(m)})
    return items


def _grammar(c, rnd, levels, n):
    nodes = [x for x in nx.nodes_meta(c) if nx.node_level(x) in levels]
    rnd.shuffle(nodes)
    out = []
    for node in nodes[:n]:
        out.extend(GB.draw(c, node, 1, rnd.random()))
    return out


def _reading(c, uid, rnd, level, n=2):
    """Two passages at the exam's level from different themes, preferring ones the learner has not checked yet."""
    done = nx._done(c, uid)
    packs = [p for _, p in nx._public_packs(c) if nx.cefr(p) == level and str(p['id']).startswith('v5-') and p.get('questions') and not p.get('series')]
    fresh = [p for p in packs if 'check' not in done.get(p['id'], set())]
    pool = fresh if len({p['theme'] for p in fresh}) >= n else packs
    rnd.shuffle(pool)
    out, themes = [], set()
    for p in pool:
        if p['theme'] not in themes:
            out.append(p); themes.add(p['theme'])
        if len(out) == n:
            break
    return out


def paper(c, uid, exam):
    """A new practice set. The answers stay on the server with the paper; it can be handed in once."""
    import vocab_service as vs
    e = EXAMS.get(exam)
    if not e or e['book'] not in vs.book_words():  # 中考、高考、专四、专八 need their data books
        return {'error': '没有这个考试'}, 400
    now = time.time()
    c.execute('DELETE FROM next_exam_papers WHERE created<?', (now - PAPER_TTL,))
    # Unfinished papers are kept only a few at a time: five per learner, three hundred for all guests together.
    if uid:
        c.execute('DELETE FROM next_exam_papers WHERE user_id=? AND id NOT IN (SELECT id FROM next_exam_papers WHERE user_id=? ORDER BY created DESC LIMIT 4)', (uid, uid))
    else:
        c.execute('DELETE FROM next_exam_papers WHERE user_id IS NULL AND id NOT IN (SELECT id FROM next_exam_papers WHERE user_id IS NULL ORDER BY created DESC LIMIT 299)')
    rnd = random.Random()
    vocab, grammar, reading = _vocab(rnd, e['book'], VOCAB_N), _grammar(c, rnd, e['levels'], GRAMMAR_N), _reading(c, uid, rnd, e['reading'])
    pid = secrets.token_urlsafe(12)
    content = {'vocab': vocab, 'grammar': [{'id': q['id']} for q in grammar],
               'reading': [{'pack': p['id'], 'answer': q['answer'], 'evidence': q.get('evidence', '')} for p in reading for q in p['questions'][:READING_Q]]}
    c.execute('INSERT INTO next_exam_papers(id,user_id,exam,content,created) VALUES(?,?,?,?,?)', (pid, uid, exam, json.dumps(content, ensure_ascii=False), now))
    c.commit()
    parts = [{'key': 'vocab', 'title': '词汇', 'hint': '选出单词的中文意思', 'items': [{k: v[k] for k in ('word', 'phonetic', 'options')} for v in vocab]},
             {'key': 'grammar', 'title': '语法', 'hint': '选出最合适的一项', 'items': grammar}]
    if reading:
        parts.append({'key': 'reading', 'title': '阅读', 'hint': '读短文，回答问题',
                      'passages': [{'pack': p['id'], 'title': p.get('title_en') or p['title'], 'body': p['body'],
                                    'items': [{'prompt': q['prompt'], 'options': q['options']} for q in p['questions'][:READING_Q]]} for p in reading]})
    return {'paper': pid, 'exam': exam, 'title': e['title'], 'minutes': e['minutes'], 'note': NOTE, 'parts': parts}, 200


def _choice(x, n):
    return x if type(x) is int and 0 <= x < n else None


def submit(c, uid, data):
    pid = data.get('paper')
    row = c.execute('SELECT * FROM next_exam_papers WHERE id=?', (pid if isinstance(pid, str) else '',)).fetchone()
    if not row or row['user_id'] != uid:
        return {'error': '这份练习已经交过或已过期，重新开始一份吧'}, 404
    exam, content = row['exam'], json.loads(row['content'])
    answers = data.get('answers') if isinstance(data.get('answers'), dict) else {}
    seconds = data.get('seconds') if type(data.get('seconds')) is int and 0 <= data.get('seconds') <= 6 * 3600 else 0
    def get(key, i):
        xs = answers.get(key)
        return xs[i] if isinstance(xs, list) and i < len(xs) else None
    vocab = [{'word': v['word'], 'correct': _choice(get('vocab', i), 4) == v['answer'], 'answer': v['options'][v['answer']]} for i, v in enumerate(content['vocab'])]
    grammar = []
    for i, g in enumerate(content['grammar']):
        q = c.execute('SELECT id, node, prompt, options, answer, explanation FROM questions WHERE id=?', (g['id'],)).fetchone()
        if not q:
            continue
        opts = json.loads(q['options'])
        pick = _choice(get('grammar', i), len(opts))
        grammar.append({'id': q['id'], 'node': q['node'], 'prompt': q['prompt'], 'options': opts, 'correct': pick == q['answer'], 'choice': pick,
                        'answer': q['answer'], 'explanation': q['explanation'] or ''})
    reading = [{'correct': _choice(get('reading', i), 4) == r['answer'], 'answer': r['answer'], 'evidence': r['evidence'], 'pack': r['pack']}
               for i, r in enumerate(content.get('reading') or [])]
    parts = [{'key': k, 'title': t, 'right': sum(x['correct'] for x in xs), 'of': len(xs)}
             for k, t, xs in (('vocab', '词汇', vocab), ('grammar', '语法', grammar), ('reading', '阅读', reading)) if xs]
    score, total = sum(p['right'] for p in parts), sum(p['of'] for p in parts)
    c.execute('DELETE FROM next_exam_papers WHERE id=?', (pid,))
    if uid:
        now = time.time()
        c.execute('INSERT INTO next_exam_results(user_id,exam,paper,score,total,parts,seconds,created) VALUES(?,?,?,?,?,?,?,?)',
                  (uid, exam, pid, score, total, json.dumps(parts, ensure_ascii=False), seconds, now))
        ev, sk = __import__('event_service'), __import__('skills_service')
        day = int(now // 86400)
        for g in grammar:
            if g['choice'] is None:
                continue  # left blank under time pressure: no evidence either way
            ev.record(c, uid, g['node'], f"next-exam:{g['id']}:{day}", 'choice', str(g['id']), 'exam:' + exam, int(g['correct']), 0, 'rule', {'choice': g['choice'], 'from': 'exam'})
            GB.schedule(c, uid, g['node'], g['correct'], now)
            if not g['correct']:
                sk.add_mistake(c, uid, 'question', g['prompt'], f"gq:{g['id']}", '', '', 'grammar', node=g['node'],
                               extra={'options': g['options'], 'answer': g['answer'], 'evidence': g['explanation']}, commit=False)
    c.commit()
    titles = {k: v['title'] for k, v in nx.nodes_meta(c).items()}
    return {'exam': exam, 'title': EXAMS[exam]['title'], 'score': score, 'total': total, 'pct': round(100 * score / total) if total else 0,
            'seconds': seconds, 'minutes': EXAMS[exam]['minutes'], 'parts': parts, 'saved': bool(uid),
            'vocab': vocab, 'grammar': [{'id': g['id'], 'correct': g['correct'], 'answer': g['answer'], 'explanation': g['explanation'],
                                         'node': g['node'], 'node_title': titles.get(g['node'], '')} for g in grammar],
            'reading': reading, 'history': history(c, uid, exam)}, 200
