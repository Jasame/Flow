"""考试冲刺 (r27): the exam a learner is preparing for and its date, a countdown word plan, the score trend of
考试练习, and practice on single question types (exam_types.py: original items, never past papers).

The exam and its date live in next_profiles (columns exam, exam_date; next_service.schema). The countdown takes the
words not yet studied in that exam's word book and the days left, keeps the last week for review, and says how many
new words a day finish the book in time and whether the learner's plan does. More than EASY_MAX new words a day are
not remembered (a month later the reviews come to four or five times that), so past it the plan says so and suggests
the most common words first (every word book is ordered most common first). In the last SPRINT_DAYS days 今日's plan
adds the weekly practice set and a round on that exam's grammar points (skills_service.daily_path).
"""
import datetime, json, math, random, re, time

import next_service as nx
import exam_service as ES

SPRINT_DAYS = 28
REVIEW_DAYS = 7
EASY_MAX = 40
TREND_N = 12
TYPES_NOTE = '题型专练的题目是原创题，由 AI 辅助编写，按这个考试的题型和难度出，不是真题，也不取自任何真题或教辅。'


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS next_exam_type_results(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      exam TEXT NOT NULL, type TEXT NOT NULL, set_id TEXT NOT NULL, right INTEGER NOT NULL, total INTEGER NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS next_exam_type_results_user ON next_exam_type_results(user_id, exam, type, created);''')


def short(exam):
    import vocab_service as vs
    return {b: t for t, b in vs.EXAM_GOALS}.get(exam) or ES.EXAMS[exam]['title']


def available():
    """The exams a learner can choose: the ones whose word book is there (中考、高考、专四、专八 are data books)."""
    import vocab_service as vs
    books = vs.book_words()
    return [k for k, e in ES.EXAMS.items() if e['book'] in books]


def _today(now=None):
    return datetime.datetime.fromtimestamp(now or time.time(), nx.TZ).date()


def goal(c, uid):
    if not uid:
        return None
    r = c.execute('SELECT exam, exam_date FROM next_profiles WHERE user_id=?', (uid,)).fetchone()
    if not r or r['exam'] not in ES.EXAMS:
        return None
    return {'exam': r['exam'], 'date': r['exam_date'] or None, 'title': ES.EXAMS[r['exam']]['title'], 'short': short(r['exam'])}


def set_goal(c, uid, data, now=None):
    exam = data.get('exam') or ''
    if exam and exam not in available():
        return {'error': '没有这个考试'}, 400
    date = data.get('date') or ''
    if exam and date:
        try:
            d = datetime.date.fromisoformat(str(date)[:10])
        except ValueError:
            return {'error': '考试日期的格式不对'}, 400
        today = _today(now)
        if not today <= d <= today + datetime.timedelta(days=3 * 366):
            return {'error': '考试日期要在今天以后、三年以内'}, 400
        date = d.isoformat()
    else:
        date = ''
    if not c.execute('UPDATE next_profiles SET exam=?, exam_date=?, updated=? WHERE user_id=?', (exam or None, date or None, time.time(), uid)).rowcount:
        return {'error': '请先回答几个问题，设好学习目标和水平'}, 400
    c.commit()
    return {'goal': goal(c, uid), 'countdown': countdown(c, uid, now)}, 200


def countdown(c, uid, now=None, g=None):
    """Words left in the exam's book against the days left: {status, days, left, need, daily, suggest, …}.
    status: done (every word studied), no_date, past, today, no_plan / other_book (the plan is on another book),
    on_time, behind."""
    import vocab_service as vs
    g = g or goal(c, uid)
    if not g:
        return None
    now = now or time.time()
    book = ES.EXAMS[g['exam']]['book']
    words = vs.book_words().get(book, [])
    p = vs.plan(c, uid)
    studied = {r[0] for r in c.execute("SELECT norm FROM next_cards WHERE user_id=? AND (state!='new' OR known=1)", (uid,))}
    started = sum(1 for _, w in words if w in studied)
    skipped = vs._skipped(book, (p.get('skip_rank') or 0) if p else 0)
    left = max(0, len(words) - started - skipped)
    on_book = bool(p and p['book'] == book)
    daily = p['daily_new'] if on_book else 0
    # what was really learned: words of this book first studied in the last seven days
    inbook = {w for _, w in words}
    recent = sum(1 for (w,) in c.execute("SELECT norm FROM next_cards WHERE user_id=? AND source='book' AND state!='new' AND created>=?",
                                         (uid, now - 7 * 86400)) if w in inbook)
    out = {**g, 'book': book, 'book_title': vs.book_title(book), 'size': len(words), 'started': started, 'skipped': skipped, 'left': left,
           'daily': daily, 'week_avg': round(recent / 7, 1), 'plan_book': p['book'] if p else None,
           'plan_book_title': vs.book_title(p['book']) if p else None, 'retention': p['retention'] if p else 0.9,
           'plan_days': int((now - p['updated']) // 86400) if p else 0,  # a plan changed this week: its pace cannot be judged yet
           'days': None, 'sprint': False, 'need': None, 'suggest': None, 'reach': None, 'too_many': False}
    today = _today(now)
    if g['date']:
        out['days'] = (datetime.date.fromisoformat(g['date']) - today).days
        out['sprint'] = 0 <= out['days'] <= SPRINT_DAYS
    days = out['days']
    if days is not None and days < 0:
        out['status'] = 'past'
    elif days == 0:
        out['status'] = 'today'
    elif not left:
        out['status'] = 'done'
    elif days is None:
        out['status'] = 'no_date'
        if daily:
            out['finish'] = (today + datetime.timedelta(days=math.ceil(left / daily))).isoformat()
    else:
        study = max(1, days - min(REVIEW_DAYS, days // 3))  # the last week (a third of a short run-up) is for review only
        need = math.ceil(left / study)
        out.update(study_days=study, review_days=days - study, need=need,
                   last_new=(today + datetime.timedelta(days=study)).isoformat(), reach=min(left, daily * study))
        out['status'] = 'no_plan' if not p else 'other_book' if not on_book else 'on_time' if daily >= need else 'behind'
        if out['status'] != 'on_time':
            out['too_many'] = need > EASY_MAX
            out['suggest'] = EASY_MAX if need > EASY_MAX else min(EASY_MAX, max(5, math.ceil(need / 5) * 5))
            out['suggest_reach'] = min(left, out['suggest'] * study)
    return out


def brief(c, uid, now=None):
    """One line for 今日's plan header: the exam, the days left and whether the word plan keeps up."""
    cd = countdown(c, uid, now)
    if not cd:
        return None
    return {k: cd[k] for k in ('exam', 'short', 'days', 'status', 'sprint')}


# ---------- 成绩走势 ----------

def trend(c, uid, exam, limit=TREND_N):
    """The latest practice sets of an exam, oldest first: total and each part (词汇/语法/阅读) as percentages."""
    if not uid:
        return []
    rows = c.execute('SELECT score, total, parts, created FROM next_exam_results WHERE user_id=? AND exam=? ORDER BY created DESC LIMIT ?',
                     (uid, exam, limit)).fetchall()
    out = []
    for r in rows[::-1]:
        parts = {p['key']: round(100 * p['right'] / p['of']) for p in json.loads(r['parts']) if p.get('of')}
        out.append({'pct': round(100 * r['score'] / r['total']) if r['total'] else 0, 'parts': parts,
                    'day': nx._day(r['created'])})
    return out


# ---------- 题型专练 ----------

def _types(exam):
    import exam_types
    return exam_types.TYPES.get(exam, [])


def _type(exam, tid):
    return next((t for t in _types(exam) if t['id'] == tid), None)


def type_list(c, uid, exam):
    last = {}
    if uid:
        for r in c.execute('SELECT type, right, total, set_id FROM next_exam_type_results WHERE user_id=? AND exam=? ORDER BY created', (uid, exam)):
            last.setdefault(r['type'], {'done': set()})
            last[r['type']].update(right=r['right'], total=r['total'])
            last[r['type']]['done'].add(r['set_id'])
    out = []
    for t in _types(exam):
        l = last.get(t['id'])
        out.append({'id': t['id'], 'title': t['title'], 'how': t['how'], 'sets': len(t['sets']), 'items': sum(len(s['items']) for s in t['sets']),
                    'last': {'right': l['right'], 'of': l['total']} if l else None, 'done': len(l['done']) if l else 0})
    return out


def _public_set(t, s):
    """A set as the learner sees it: no answers, no explanations."""
    k = t['kind']
    out = {'id': s['id'], 'title': s.get('title', ''), 'kind': k}
    if k in ('cloze', 'bank'):
        out['text'] = s['text']
    if k in ('tfng',):
        out['text'] = s['text']
    if k in ('match', 'headings'):
        out['paras'] = s['paras']
    if k == 'proof':
        out['lines'] = s['lines']
    if k in ('bank', 'headings'):
        out['bank'] = s['bank']
    if k in ('cloze', 'choice'):
        out['items'] = [{'prompt': it.get('prompt', ''), 'options': it['options']} for it in s['items']]
    elif k == 'tfng':
        out['items'] = [{'prompt': it['prompt'], 'options': ['TRUE', 'FALSE', 'NOT GIVEN']} for it in s['items']]
    elif k == 'match':
        out['items'] = [{'prompt': it['prompt']} for it in s['items']]
    elif k == 'proof':
        out['items'] = [{'line': it['line']} for it in s['items']]
    else:
        out['items'] = [{} for _ in s['items']]
    return out


def type_set(c, uid, exam, tid, want=None):
    """The next set of a type: the one done least often (a set asked for by id when given)."""
    if _reading_tid(tid):
        return reading_set(c, uid, exam, tid, want)
    t = _type(exam, tid)
    if not t or exam not in available():
        return {'error': '没有这个题型'}, 404
    sets = t['sets']
    if want:
        s = next((x for x in sets if x['id'] == want), None)
        if not s:
            return {'error': '没有这一组'}, 404
    else:
        done = {}
        if uid:
            for (sid,) in c.execute('SELECT set_id FROM next_exam_type_results WHERE user_id=? AND exam=? AND type=?', (uid, exam, tid)):
                done[sid] = done.get(sid, 0) + 1
        s = min(sets, key=lambda x: (done.get(x['id'], 0), sets.index(x)))
    return {'exam': exam, 'exam_title': ES.EXAMS[exam]['title'], 'type': tid, 'title': t['title'], 'how': t['how'], 'note': TYPES_NOTE,
            'set': _public_set(t, s), 'index': sets.index(s) + 1, 'of': len(sets)}, 200


def _norm(w):
    return ''.join(ch for ch in str(w).lower() if ch.isalpha() or ch in "'-")


def type_submit(c, uid, data):
    exam, tid, sid = data.get('exam'), data.get('type'), data.get('set')
    if isinstance(exam, str) and _reading_tid(tid):
        return reading_submit(c, uid, data)
    t = _type(exam, tid) if isinstance(exam, str) and isinstance(tid, str) else None
    s = next((x for x in t['sets'] if x['id'] == sid), None) if t else None
    if not s:
        return {'error': '没有这一组'}, 404
    answers = data.get('answers') if isinstance(data.get('answers'), list) else []
    get = lambda i: answers[i] if i < len(answers) else None
    k, items = t['kind'], []
    for i, it in enumerate(s['items']):
        a = get(i)
        if k == 'proof':
            ok = isinstance(a, str) and _norm(a) == _norm(it['wrong'])
            items.append({'correct': ok, 'choice': a if isinstance(a, str) else None, 'wrong': it['wrong'], 'fix': it['fix'], 'why': it['why']})
            continue
        n = len(s['bank']) if k in ('bank', 'headings') else len(s['paras']) if k == 'match' else 3 if k == 'tfng' else len(it['options'])
        pick = a if type(a) is int and 0 <= a < n else None
        items.append({'correct': pick == it['answer'], 'choice': pick, 'answer': it['answer'], 'why': it['why'], 'evidence': it.get('evidence', '')})
    right = sum(x['correct'] for x in items)
    if uid:
        c.execute('INSERT INTO next_exam_type_results(user_id,exam,type,set_id,right,total,created) VALUES(?,?,?,?,?,?,?)',
                  (uid, exam, tid, sid, right, len(items), time.time()))
        c.commit()
    nxt = t['sets'][(t['sets'].index(s) + 1) % len(t['sets'])]['id']
    return {'right': right, 'of': len(items), 'items': items, 'saved': bool(uid), 'next': nxt}, 200


# ---------- 考试小练 (r28 第 4 段): a few minutes of the exam every day, sized to the minutes 今日's plan gives it ----------
# Today's piece is one passage at the exam's reading level (阅读一篇, 2 or 4 questions) or one set of its two question
# types, whichever fits the minutes: the weakest part of the last full set first when that was reading, else the three
# in turn, day by day. Time: the text once at 130 words a minute, then each item (21–36 s by kind).
WPM = 130
ITEM_SECS = {'cloze': 21, 'bank': 24, 'choice': 24, 'tfng': 30, 'match': 30, 'headings': 36, 'proof': 36, 'reading': 30}
READING = 'reading'  # 阅读一篇; 'reading-2' asks only the first two questions (a short budget)


def _reading_tid(tid):
    return isinstance(tid, str) and tid in (READING, READING + '-2')


def est_minutes(kind, words, items):
    return max(2, math.ceil(words / WPM + items * ITEM_SECS[kind] / 60))


def _set_words(s):
    text = s.get('text') or ' '.join(s.get('paras') or []) or ' '.join(s.get('lines') or []) or ' '.join(it.get('prompt', '') for it in s['items'])
    return len(re.sub(r'\{\d+\}', ' ', text).split())


def _next_set(c, uid, exam, t):
    done = {}
    if uid:
        for (sid,) in c.execute('SELECT set_id FROM next_exam_type_results WHERE user_id=? AND exam=? AND type=?', (uid, exam, t['id'])):
            done[sid] = done.get(sid, 0) + 1
    return min(t['sets'], key=lambda x: (done.get(x['id'], 0), t['sets'].index(x)))


def _reading_packs(c, exam):
    level = ES.EXAMS[exam]['reading']
    return sorted((p for _, p in nx._public_packs(c) if nx.cefr(p) == level and str(p['id']).startswith('v5-') and len(p.get('questions') or []) >= 2
                   and not p.get('series')), key=lambda p: p['id'])


def _reading_pack(c, uid, exam, now=None):
    """Today's passage: one the learner has not answered here nor checked in 学一篇, the same all day."""
    packs = _reading_packs(c, exam)
    seen = set()
    if uid:
        seen = {r[0] for r in c.execute("SELECT set_id FROM next_exam_type_results WHERE user_id=? AND exam=? AND type=?", (uid, exam, READING))}
        seen |= {pid for pid, steps in nx._done(c, uid).items() if 'check' in steps}
    pool = [p for p in packs if p['id'] not in seen] or packs
    return random.Random(f'{uid}|{nx._day(now)}|{exam}|{READING}').choice(pool) if pool else None


def reading_set(c, uid, exam, tid, want=None):
    """阅读一篇 as a set of the 题型专练 page: an original passage at the exam's level, its questions without answers."""
    if exam not in available():
        return {'error': '没有这个题型'}, 404
    p = next((x for x in _reading_packs(c, exam) if x['id'] == want), None) if want else _reading_pack(c, uid, exam)
    if not p:
        return {'error': '没有这一组'}, 404
    qs = p['questions'][:2 if tid.endswith('-2') else 4]
    level = ES.EXAMS[exam]['reading']
    return {'exam': exam, 'exam_title': ES.EXAMS[exam]['title'], 'type': tid, 'title': '阅读一篇',
            'how': f'读一篇 {level} 难度的原创短文，回答 {len(qs)} 道题。每题的依据都在文章里。', 'note': TYPES_NOTE,
            'set': {'id': p['id'], 'title': p.get('title_en') or p['title'], 'kind': READING, 'text': p['body'],
                    'items': [{'prompt': q['prompt'], 'options': q['options']} for q in qs]},
            'index': 1, 'of': 1}, 200


def reading_submit(c, uid, data):
    exam, tid, sid = data.get('exam'), data.get('type'), data.get('set')
    p = next((x for x in _reading_packs(c, exam) if x['id'] == sid), None) if exam in available() and isinstance(sid, str) else None
    if not p:
        return {'error': '没有这一组'}, 404
    qs = p['questions'][:2 if tid.endswith('-2') else 4]
    answers = data.get('answers') if isinstance(data.get('answers'), list) else []
    items = []
    for i, q in enumerate(qs):
        a = answers[i] if i < len(answers) else None
        pick = a if type(a) is int and 0 <= a < len(q['options']) else None
        items.append({'correct': pick == q['answer'], 'choice': pick, 'answer': q['answer'], 'why': q.get('evidence') or '', 'evidence': q.get('evidence') or ''})
    right = sum(x['correct'] for x in items)
    if uid:
        c.execute('INSERT INTO next_exam_type_results(user_id,exam,type,set_id,right,total,created) VALUES(?,?,?,?,?,?,?)',
                  (uid, exam, READING, p['id'], right, len(items), time.time()))
        c.commit()
    nxt = _reading_pack(c, uid, exam)
    return {'right': right, 'of': len(items), 'items': items, 'saved': bool(uid), 'next': nxt['id'] if nxt and nxt['id'] != p['id'] else None}, 200


def _day_start(now=None):
    return datetime.datetime.combine(_today(now), datetime.time(), nx.TZ).timestamp()


def drill_pick(c, uid, exam, minutes, now=None):
    """What today's 考试小练 is: {'tid', 'title', 'items', 'minutes'} — the piece that fits `minutes` (a minute over is
    fine), the weakest part first, else in turn by day. 阅读一篇 is always there: two questions when four do not fit."""
    out = []
    p = _reading_pack(c, uid, exam, now)
    if p:
        words, nq = len(p['body'].split()), min(4, len(p['questions']))
        q = nq if est_minutes(READING, words, nq) <= minutes + 1 else 2
        out.append({'tid': READING if q > 2 else READING + '-2', 'title': '阅读一篇', 'items': q, 'minutes': est_minutes(READING, words, q)})
    for t in _types(exam):
        st = _next_set(c, uid, exam, t)
        m = est_minutes(t['kind'], _set_words(st), len(st['items']))
        if m <= minutes + 1:
            out.append({'tid': t['id'], 'title': t['title'], 'items': len(st['items']), 'minutes': m})
    if not out:
        return None
    tr = trend(c, uid, exam, 1)
    parts = tr[-1]['parts'] if tr else {}
    if parts.get('reading') is not None and parts['reading'] < min(v for k, v in parts.items() if k != 'reading') and out[0]['tid'].startswith(READING):
        return out[0]  # the last full set's reading was its weakest part
    return out[_today(now).toordinal() % len(out)]


def drill_step(c, uid, minutes, now=None):
    if not uid or not minutes or minutes <= 0:
        return None
    g = goal(c, uid)
    exam = g and g.get('exam')
    if not exam or exam not in available():
        return None
    short_ = short(exam)
    # done today: any 题型专练 set or passage of this exam, or a full set
    last = c.execute('SELECT type, right, total FROM next_exam_type_results WHERE user_id=? AND exam=? AND created>=? ORDER BY created DESC LIMIT 1',
                     (uid, exam, _day_start(now))).fetchone()
    full = c.execute('SELECT score, total FROM next_exam_results WHERE user_id=? AND exam=? AND created>=? ORDER BY created DESC LIMIT 1',
                     (uid, exam, _day_start(now))).fetchone()
    if last or full:
        r = last or full
        title = '阅读一篇' if last and last['type'] == READING else (_type(exam, last['type']) or {}).get('title', '一套练习') if last else '一套练习'
        return {'key': 'exam-drill', 'title': f'考试小练：{short_}{title}', 'sub': f"今天做过了：{r['total']} 题对 {r['right' if last else 'score']} 题",
                'href': f'#/exam/{exam}', 'done': True, 'minutes': 0}
    pick = drill_pick(c, uid, exam, minutes, now)
    if not pick:
        return None
    what = f"{ES.EXAMS[exam]['reading']} 难度的原创短文，{pick['items']} 题" if pick['tid'].startswith(READING) else f"一组 {pick['items']} 题，原创，不是真题"
    # the minutes are said by 今日's plan row from 'minutes' (10-welcome-today.js planRowHTML), as for every step: not
    # here too (B8, 2026-11-25: 「约 4 分钟 · 约 4 分钟」)
    return {'key': 'exam-drill', 'title': f"考试小练：{short_}{pick['title']}", 'sub': what,
            'href': f"#/exam/{exam}/{pick['tid']}", 'done': False, 'minutes': pick['minutes']}


# ---------- 考点语法: the exam's grammar points in one mixed round ----------

def grammar_nodes(c, uid, exam, now=None):
    """The exam's grammar points to practise: flagged first, then those due, then the ones not yet verified;
    points already verified only when nothing else is left."""
    e = ES.EXAMS.get(exam)
    if not e:
        return []
    meta = nx.nodes_meta(c)
    nodes = [n for n in meta if nx.node_level(n) in e['levels']]
    states = nx.graph_states(c, uid) if uid else {}
    due = set(nx.GB.due(c, uid, now)) if uid else set()
    st = lambda n: states.get(n, {}).get('status', 'untouched')
    order = {'watch': 0, 'met': 2, 'used': 2, 'untouched': 3, 'solid': 5}
    rnd = random.Random(f'{uid}|{nx._day(now)}|{exam}')  # the same round all day, a different one tomorrow
    keyed = [((1 if n in due and st(n) != 'watch' else order.get(st(n), 3)), rnd.random(), n) for n in nodes]
    return [n for _, _, n in sorted(keyed)]


def grammar_today(c, uid, now=None):
    """Answers given today in 考点语法 rounds (node_answer with from='exam')."""
    start = datetime.datetime.combine(_today(now), datetime.time(), nx.TZ).timestamp()
    return c.execute("SELECT COUNT(*) FROM learning_events WHERE user_id=? AND source LIKE 'next-node:%' AND created>=? AND details LIKE '%\"from\": \"exam\"%'",
                     (uid, start)).fetchone()[0]


# ---------- routes ----------

def get(c, uid, path, q):
    one = lambda k: (q.get(k) or [''])[0]
    if path == '/api/next/exam/type':
        return type_set(c, uid, one('exam'), one('type'), one('set') or None)
    if path == '/api/next/exam/goal':
        if not uid:
            return {'error': '请先登录'}, 401
        return {'goal': goal(c, uid), 'countdown': countdown(c, uid), 'exams': [{'id': k, 'title': ES.EXAMS[k]['title'], 'short': short(k)} for k in available()]}, 200
    return None


def post_public(c, uid, path, data):
    if path == '/api/next/exam/type':
        return type_submit(c, uid, data)
    return None


def post(c, uid, path, data):
    if path == '/api/next/exam/goal':
        return set_goal(c, uid, data)
    return None
