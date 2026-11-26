"""Ability radar (能力雷达): where the learner stands in six skills, against goals they set, and how that changes.

- Scale: one ability index 0-100 for every skill, CEFR bands of 20 (A1 0-20, A2 20-40, B1 40-60, B2 60-80, C1 80-100).
- Goal: a level per skill; "reached" is 15 points into that band (steadily at that level), which is 100 on the radar.
- Evidence: short assessments (vocabulary size, grammar starting check, reading, listening, a spoken answer, a short
  text) weigh most while recent; practice (the existing per-skill estimate) fills in between them and alone gives a
  low-confidence value. With neither, the skill says "not enough evidence" instead of a made-up number.
- History: a snapshot after each assessment and at most weekly otherwise, so the radar can show what moved.
This is an estimate to steer practice, not a certificate; it is never converted to an exam score.
"""
import json, random, time

import next_service as nx

DIMS = (('listening', '听力'), ('reading', '阅读'), ('vocab', '词汇'), ('grammar', '语法'), ('speaking', '口语'), ('writing', '写作'))
LABEL = dict(DIMS)
BANDS = ('A1', 'A2', 'B1', 'B2', 'C1')
START = {'A1': 0, 'A2': 20, 'B1': 40, 'B2': 60, 'C1': 80}
GOALS = ('A2', 'B1', 'B2', 'C1')
INTO_BAND = 15          # points into the goal band that count as having reached it
FRESH, KEEP = 45, 120   # days an assessment counts fully / at all
RETEST = 28             # days after which a skill is due to be measured again
DAY = 86400


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS next_goals(user_id INTEGER PRIMARY KEY REFERENCES users(id), goals TEXT NOT NULL, updated REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS next_assess(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), skill TEXT NOT NULL,
      idx REAL NOT NULL, level TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS next_assess_user ON next_assess(user_id, skill, created);
    CREATE TABLE IF NOT EXISTS next_radar(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), scores TEXT NOT NULL,
      source TEXT NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS next_radar_user ON next_radar(user_id, created);''')


def level_of(idx):
    return next((b for b in reversed(BANDS) if idx >= START[b]), 'A1') if idx is not None else None


def goal_index(level):
    return START[level] + INTO_BAND


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- goals

def goals(c, uid):
    r = c.execute('SELECT goals FROM next_goals WHERE user_id=?', (uid,)).fetchone() if uid else None
    if r:
        g = json.loads(r[0])
        return {k: g.get(k) for k, _ in DIMS}, True
    lv = (nx.profile(c, uid) or {}).get('level') or 'B1'
    nxt = GOALS[min(len(GOALS) - 1, GOALS.index(lv) + 1)] if lv in GOALS else 'B2'
    return {k: nxt for k, _ in DIMS}, False  # a default one level up, until the learner chooses


def set_goals(c, uid, data):
    g = data.get('goals')
    if not isinstance(g, dict) or set(g) - set(LABEL) or not all(v in GOALS for v in g.values()) or not g:
        return {'error': '目标等级不正确'}, 400
    cur, _ = goals(c, uid)
    cur.update(g)
    c.execute('INSERT INTO next_goals(user_id,goals,updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET goals=excluded.goals, updated=excluded.updated',
              (uid, json.dumps(cur), time.time()))
    c.commit()
    return radar(c, uid), 200


# ---------------------------------------------------------------- evidence

def vocab_index(size):
    """Vocabulary size to the index, on the same lines as the word-book levels (2000 B1, 4000 B2, 7000 C1)."""
    if not size:
        return None
    pts = ((0, 0), (1000, 20), (2000, 40), (4000, 60), (7000, 80), (10000, 100))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if size <= x1:
            return round(y0 + (y1 - y0) * (size - x0) / (x1 - x0), 1)
    return 100.0


def ladder_index(accuracy):
    """Accuracy per level, easiest first -> index: each level adds up to 20 points; a level below half right stops the climb."""
    levels = [lv for lv in BANDS if lv in accuracy]
    if not levels:
        return None
    idx = START[levels[0]]
    for lv in levels:
        idx += 20 * accuracy[lv]
        if accuracy[lv] < 0.5:  # this level is not managed yet: the learner stays below it, however well the easier ones went
            idx = min(idx, START[lv] - 2)
            break
    return round(clamp(idx), 1)


def _practice(c, uid, now):
    """Index and evidence count per skill from practice alone (the existing CEFR estimate, refined by the average score)."""
    ab = {s['id']: s for s in __import__('skills_service').ability(c, uid, now)['skills']}
    out = {}
    for k in ('listening', 'reading', 'speaking', 'writing'):
        s = ab.get(k) or {}
        if s.get('level'):
            out[k] = (round(START[s['level']] + 20 * (0.3 + 0.6 * (s.get('avg') or 0.5)), 1), s.get('count') or 0)
    v = ab.get('vocab') or {}
    if v.get('size'):
        out['vocab'] = (vocab_index(v['size']), 5)
    states = nx.graph_states(c, uid)
    checked = [n for n, s in states.items() if s['evidence']]
    if len(checked) >= 4:
        acc = {}
        for band in GOALS:
            nodes = [n for n in states if nx.node_level(n) == band]
            if nodes:
                acc[band] = sum(1 for n in nodes if states[n]['status'] == 'solid') / len(nodes)
        idx = START['A2'] + sum(20 * acc[b] for b in GOALS if b in acc)
        out['grammar'] = (round(clamp(idx), 1), len(checked))
    return out


def _assessed(c, uid, now):
    out = {}
    for r in c.execute('SELECT skill, idx, created, detail FROM next_assess WHERE user_id=? AND created>=? ORDER BY created', (uid, now - KEEP * DAY)):
        out[r['skill']] = (r['idx'], r['created'], json.loads(r['detail']))
    return out


def current(c, uid, now=None):
    """skill -> {index, confidence, source, assessed} combining assessment and practice."""
    now = now or time.time()
    prac, test = _practice(c, uid, now), _assessed(c, uid, now)
    out = {}
    for k, _ in DIMS:
        p, t = prac.get(k), test.get(k)
        if t:
            age = (now - t[1]) / DAY
            w = 0.75 if age <= FRESH else 0.5
            idx = t[0] if not p else w * t[0] + (1 - w) * p[0]
            conf = 'high' if age <= FRESH else 'medium'
            out[k] = {'index': round(idx, 1), 'confidence': conf, 'source': 'assessment', 'assessed': t[1]}
        elif p:
            out[k] = {'index': p[0], 'confidence': 'medium' if p[1] >= 8 else 'low', 'source': 'practice', 'assessed': None}
        else:
            out[k] = {'index': None, 'confidence': None, 'source': None, 'assessed': None}
    return out


def _score(idx, goal):
    return None if idx is None else int(round(clamp(idx / goal_index(goal) * 100)))


def _snapshot(c, uid, scores, source, now):
    c.execute('INSERT INTO next_radar(user_id,scores,source,created) VALUES(?,?,?,?)', (uid, json.dumps(scores), source, now))


def record(c, uid, skill, idx, detail=None, now=None):
    """One assessment result; the radar is snapshotted right after it."""
    if not uid or skill not in LABEL or idx is None:
        return None
    now = now or time.time()
    idx = round(clamp(idx), 1)
    c.execute('INSERT INTO next_assess(user_id,skill,idx,level,detail,created) VALUES(?,?,?,?,?,?)',
              (uid, skill, idx, level_of(idx), json.dumps(detail or {}, ensure_ascii=False), now))
    g, _ = goals(c, uid)
    _snapshot(c, uid, {k: v['index'] for k, v in current(c, uid, now).items()}, 'assessment:' + skill, now)
    c.commit()
    return {'skill': skill, 'index': idx, 'level': level_of(idx), 'score': _score(idx, g[skill]), 'goal': g[skill]}


# ---------------------------------------------------------------- the radar

TIPS = {'listening': ('逐句听写和精听', '#/library'), 'reading': ('轻松读，读得多一点', '#/easy'), 'vocab': ('提高每天新词数', '#/vocab/plan'),
        'grammar': ('语法混合复习', '#/mix'), 'speaking': ('口语路线的情景对话', '#/speak'), 'writing': ('写一段短文，让 AI 批改', '#/')}


def radar(c, uid, now=None):
    now = now or time.time()
    g, chosen = goals(c, uid)
    cur = current(c, uid, now)
    # at most one automatic snapshot a week, so the change view has points between assessments
    last = c.execute('SELECT created FROM next_radar WHERE user_id=? ORDER BY created DESC LIMIT 1', (uid,)).fetchone()
    if any(v['index'] is not None for v in cur.values()) and (not last or last[0] < now - 7 * DAY):
        _snapshot(c, uid, {k: v['index'] for k, v in cur.items()}, 'auto', now)
        c.commit()
    snaps = [{'created': r['created'], 'source': r['source'], 'scores': json.loads(r['scores'])}
             for r in c.execute('SELECT * FROM next_radar WHERE user_id=? ORDER BY created DESC LIMIT 12', (uid,))][::-1]
    before = next((s for s in reversed(snaps) if s['created'] < now - DAY), None)  # the latest one at least a day old
    dims = []
    for k, label in DIMS:
        v = cur[k]
        prev = (before or {}).get('scores', {}).get(k) if before else None
        dims.append({'id': k, 'label': label, 'index': v['index'], 'level': level_of(v['index']), 'goal': g[k], 'score': _score(v['index'], g[k]),
                     'prev_score': _score(prev, g[k]) if prev is not None else None, 'confidence': v['confidence'], 'source': v['source'],
                     'assessed': v['assessed'], 'due': not v['assessed'] or v['assessed'] < now - RETEST * DAY,
                     'tip': TIPS[k][0], 'href': TIPS[k][1]})
    known = [d for d in dims if d['score'] is not None]
    gap = min(known, key=lambda d: d['score'])['id'] if known else None
    history = [{'created': s['created'], 'source': s['source'], 'scores': {k: _score(v, g[k]) if v is not None else None for k, v in s['scores'].items()}} for s in snaps]
    return {'dims': dims, 'goals': g, 'goals_chosen': chosen, 'gap': gap, 'history': history, 'before': before['created'] if before else None,
            'due': [d['id'] for d in dims if d['due']], 'goal_levels': list(GOALS),
            'note': '雷达图上 100 分 = 稳定达到你设定的目标等级。分数是根据测评和平时练习做出的估计，用来安排学习，不是考试成绩。'}


def due_today(c, uid, now=None):
    """A re-test step for today's plan: only for learners who have set goals, when a skill is unmeasured or a month old."""
    now = now or time.time()
    if not c.execute('SELECT 1 FROM next_goals WHERE user_id=?', (uid,)).fetchone():
        return None
    test = _assessed(c, uid, now)
    stale = [k for k, _ in DIMS if k not in test or test[k][1] < now - RETEST * DAY]
    return stale or None


def weakest(c, uid, now=None):
    """The four-skill dimension furthest from its goal, for the plan's output step (only once goals are set)."""
    if not c.execute('SELECT 1 FROM next_goals WHERE user_id=?', (uid,)).fetchone():
        return None
    g, _ = goals(c, uid)
    cur = current(c, uid, now)
    known = [(k, _score(cur[k]['index'], g[k])) for k in ('listening', 'reading', 'speaking', 'writing') if cur[k]['index'] is not None]
    return min(known, key=lambda x: x[1])[0] if known else None


# ---------------------------------------------------------------- reading and listening checks

def comprehension_test(c, uid, kind, seed=None):
    """Two or three short texts around the learner's level (one below, at, one above), two questions each.
    Listening sends the text too, for the browser voice when no recording exists; the page does not show it."""
    if kind not in ('reading', 'listening'):
        return {'error': '没有这项测评'}, 400
    cur = current(c, uid)[kind]['index']
    lv = level_of(cur) if cur is not None else ((nx.profile(c, uid) or {}).get('level') or 'B1')
    lv = lv if lv in GOALS else 'A2'
    i = GOALS.index(lv)
    levels = sorted({GOALS[max(0, i - 1)], lv, GOALS[min(len(GOALS) - 1, i + 1)]}, key=GOALS.index)
    rnd = random.Random(seed)
    seen = {json.loads(r[0]).get('pack') for r in c.execute("SELECT detail FROM next_assess WHERE user_id=? AND skill=?", (uid, kind))} if uid else set()
    voices, version = nx.audio_index()
    out = []
    for level in levels:
        pool = [p for _, p in nx._public_packs(c) if nx.cefr(p) == level and str(p['id']).startswith('v5-') and not p.get('series')
                and len(p.get('questions') or []) >= 2 and (kind == 'reading' or voices.get(p['id']))]
        if not pool:
            pool = [p for _, p in nx._public_packs(c) if nx.cefr(p) == level and str(p['id']).startswith('v5-') and not p.get('series') and len(p.get('questions') or []) >= 2]
        fresh = [p for p in pool if p['id'] not in seen] or pool
        if not fresh:
            continue
        p = rnd.choice(fresh)
        out.append({'pack': p['id'], 'level': level, 'title': p.get('title_en') or p['title'], 'body': p['body'],
                    'audio': {'voices': voices.get(p['id'], []), 'version': version},
                    'questions': [{'i': k, 'prompt': q['prompt'], 'options': q['options']} for k, q in enumerate(p['questions'][:2])]})
    return {'kind': kind, 'passages': out, 'minutes': 6 if kind == 'reading' else 8}, 200


def comprehension_score(c, uid, data):
    kind = data.get('kind')
    answers = data.get('answers')
    if kind not in ('reading', 'listening') or not isinstance(answers, list) or not 1 <= len(answers) <= 12:
        return {'error': '答案格式不正确'}, 400
    per, packs = {}, {}
    for a in answers:
        if not isinstance(a, dict) or type(a.get('i')) is not int or not (a.get('choice') is None or type(a.get('choice')) is int):
            return {'error': '答案格式不正确'}, 400
        row = nx._pack_row(c, uid, str(a.get('pack', '')))
        if not row:
            return {'error': '材料不存在'}, 404
        p = packs.setdefault(row['id'], json.loads(row['content']))
        qs = p.get('questions') or []
        if not 0 <= a['i'] < len(qs):
            return {'error': '题目不存在'}, 400
        lv = nx.cefr(p)
        r = per.setdefault(lv, [0, 0])
        r[0] += int(a['choice'] == qs[a['i']]['answer']); r[1] += 1
    acc = {lv: r[0] / r[1] for lv, r in per.items()}
    idx = ladder_index(acc)
    out = {'index': idx, 'level': level_of(idx), 'levels': {lv: {'right': r[0], 'of': r[1]} for lv, r in per.items()},
           'results': [{'pack': a['pack'], 'i': a['i'], 'answer': packs[a['pack']]['questions'][a['i']]['answer']} for a in answers]}
    if uid:
        out['recorded'] = record(c, uid, kind, idx, {'levels': out['levels'], 'pack': answers[0]['pack']})
    return out, 200


# ---------------------------------------------------------------- speaking and writing, judged by the AI

TASKS = {
    'speaking': {
        'A2': [('介绍一下你的家乡：在哪里、有什么好吃的、你最喜欢那里的什么。', 'Tell me about your hometown.'),
               ('说说你平常的一个周末：做什么、和谁、为什么喜欢。', 'What do you usually do at the weekend?')],
        'B1': [('讲一次让你印象深刻的旅行：去了哪里、发生了什么、学到了什么。', 'Tell me about a trip you remember well.'),
               ('你觉得网上学习和在教室上课，哪种更适合你？说说理由。', 'Do you prefer learning online or in a classroom? Why?')],
        'B2': [('有人说年轻人应该先工作几年再读研究生。你同意吗？给出理由和例子。', 'Should young people work for a few years before doing a master\'s degree?'),
               ('描述一个你改变过看法的问题：以前怎么想、为什么改变。', 'Describe something you changed your mind about.')],
        'C1': [('城市应该限制私家车进入市中心吗？权衡利弊，给出你的立场。', 'Should cities ban private cars from their centres?'),
               ('谈谈人工智能会怎样改变语言学习，有哪些机会和风险。', 'How will AI change the way people learn languages?')],
    },
    'writing': {
        'A2': [('给朋友写一条消息，邀请他周末来你家吃饭，说清时间、地点和要带什么。', 'Write a message inviting a friend to dinner.')],
        'B1': [('给你的老师写一封邮件，说明你下周的课不能参加，解释原因，并问怎么补上。', 'Write an email to your teacher about missing a class.'),
               ('写一段话：你最想学会的一项技能是什么，为什么，打算怎么学。', 'What skill would you most like to learn, and how?')],
        'B2': [('写一段短文：远程办公对员工利大于弊吗？给出你的观点和两条理由。', 'Does working from home do employees more good than harm?')],
        'C1': [('写一段评论：大学应不应该取消期末考试？考虑不同立场，给出有条件的结论。', 'Should universities abolish final exams?')],
    },
}
RUBRIC = {'speaking': (('fluency', '流利度'), ('accuracy', '准确度'), ('range', '词汇句式'), ('pronunciation', '发音清晰度')),
          'writing': (('content', '内容切题'), ('organization', '结构衔接'), ('accuracy', '语言准确'), ('range', '词汇句式'))}


def task(c, uid, kind, seed=None):
    if kind not in TASKS:
        return {'error': '没有这项测评'}, 400
    cur = current(c, uid)[kind]['index']
    lv = level_of(cur) if cur is not None else ((nx.profile(c, uid) or {}).get('level') or 'B1')
    lv = lv if lv in TASKS[kind] else 'A2'
    zh, en = random.Random(seed).choice(TASKS[kind][lv])
    return {'kind': kind, 'level': lv, 'task': zh, 'question': en,
            'limit': '60 秒以内，至少说 30 秒' if kind == 'speaking' else '80–180 个英文词', 'minutes': 3 if kind == 'speaking' else 10}, 200


def judged(c, uid, kind, data):
    """A spoken answer or a short text, judged against CEFR descriptors by the AI: level, position within it, four rubric scores."""
    out = __import__('output_service')
    if kind not in TASKS:
        return {'error': '没有这项测评'}, 400
    question = data.get('question') if isinstance(data.get('question'), str) else ''
    if not any(question == q for lv in TASKS[kind].values() for _, q in lv):
        return {'error': '题目不正确'}, 400
    audio, text = None, ''
    if kind == 'speaking':
        from lab_service import audio_enabled
        from audio_validation import validate_audio
        if not audio_enabled():
            return {'error': 'AI 听录音暂未开启，口语测评暂时做不了'}, 503
        validate_audio(data.get('audio'))
        audio = data.get('audio')
    else:
        text = data.get('text') if isinstance(data.get('text'), str) else ''
        if not 40 <= len(nx.WORD.findall(text)) <= 260:
            return {'error': '写 40–260 个英文词'}, 400
    dims = RUBRIC[kind]
    system = ('你是英语' + ('口语' if kind == 'speaking' else '写作') + '评估老师，按 CEFR 能力描述评估一位中国学习者这一次表现出的水平。'
              '只评估这段' + ('录音' if kind == 'speaking' else '文字') + '本身，不要因为话题难易加减分；口音不算错，只看别人能不能听懂。'
              '给出等级（A1/A2/B1/B2/C1）和在这个等级里的位置（0 到 1，0.5 是典型水平），四个维度各 1–5 分。'
              '最后写一个做得好的地方和两条最重要的改进建议，都用' + __import__('ai_lang').word() + '、具体到能马上练。只输出 JSON。' + __import__('ai_lang').tail())
    user = (f'题目：{question}\n' + ('学习者的回答是一段录音，请先忠实转写。' if audio else '学习者写的：\n' + text) +
            '\n\n输出 JSON：{' + ('"transcript":"转写",' if audio else '') + '"level":"A1|A2|B1|B2|C1","position":0到1的数字,'
            '"scores":{' + ','.join(f'"{k}":1-5' for k, _ in dims) + '},"strength":"' + __import__('ai_lang').word() + '：做得好的地方","next":["' + __import__('ai_lang').word() + '改进建议1","' + __import__('ai_lang').word() + '改进建议2"]}')

    def convert(raw):
        if not isinstance(raw, dict) or raw.get('level') not in BANDS or not isinstance(raw.get('scores'), dict):
            raise ValueError('bad')
        pos = raw.get('position')
        pos = max(0.0, min(1.0, float(pos))) if isinstance(pos, (int, float)) and not isinstance(pos, bool) else 0.5
        return {'level': raw['level'], 'position': pos, 'transcript': out._clean(raw.get('transcript') or '', 0, 2000) if audio else '',
                'scores': {k: max(1, min(5, int(raw['scores'].get(k) or 1))) for k, _ in dims},
                'strength': out._clean(raw.get('strength') or '', 0, 300),
                'next': [out._clean(x, 1, 300) for x in (raw.get('next') or [])[:2] if isinstance(x, str) and x.strip()]}

    import hashlib
    spec = {'question': question, 'text': text, 'audio_sha256': hashlib.sha256(json.dumps(audio, sort_keys=True).encode()).hexdigest() if audio else ''}
    result, status = out._ai(c, uid, data, 'next-assess-' + kind, 'assess', kind, spec, system, user, convert, audio)
    if status == 200 and not result.get('replayed'):
        r = result['result']
        idx = START[r['level']] + 20 * r['position']
        result['result']['index'] = round(idx, 1)
        result['result']['recorded'] = record(c, uid, kind, idx, {'question': question, 'scores': r['scores'], 'level': r['level']})
    return result, status
