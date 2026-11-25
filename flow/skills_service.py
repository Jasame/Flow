"""Flow's learner model: one ability profile, one mistake book, a daily path and a weekly report.

Every practice the learner does leaves a skill event (0..1 score, the material's level): comprehension
questions, dictation, shadowing, AI-checked writing, retelling, dialogue, essays, translation and
pronunciation. From these the profile estimates a CEFR level per skill and the home page adapts:
which level to read at, which output task to do today, and which grammar to meet next.

Mistakes (a wrong answer, a corrected phrase in writing, a sound the AI flagged) become cards in the
same FSRS queue as words (next_cards, source='mistake'), so errors come back on the forgetting curve too.
"""
import datetime
import json
import time

import next_service as nx

SKILLS = {'vocab': '词汇', 'grammar': '语法', 'listening': '听力', 'reading': '阅读', 'speaking': '口语', 'writing': '写作',
          'translation': '翻译', 'pronunciation': '发音'}
EVENT_SKILLS = ('listening', 'reading', 'speaking', 'writing', 'translation', 'pronunciation')
LEVELS = ('A2', 'B1', 'B2', 'C1')
PASS = 0.75  # average score at a level that counts as "can do this level"
MISTAKE_KINDS = ('fix', 'question', 'sound')


def schema(c):
    c.executescript('''
CREATE TABLE IF NOT EXISTS next_skill_events(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), skill TEXT NOT NULL,
 kind TEXT NOT NULL, score REAL NOT NULL, level TEXT, pack TEXT, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS next_skill_events_user ON next_skill_events(user_id, skill, created);
CREATE TABLE IF NOT EXISTS next_weekly(user_id INTEGER PRIMARY KEY REFERENCES users(id), last_sent TEXT);''')
    cols = {r[1] for r in c.execute('PRAGMA table_info(next_cards)')}
    for name, decl in (('skill', 'TEXT'), ('node', 'TEXT'), ('extra', 'TEXT')):
        if name not in cols:
            c.execute(f'ALTER TABLE next_cards ADD COLUMN {name} {decl}')
    c.commit()


def _day_start(now=None):
    d = datetime.datetime.fromtimestamp(now or time.time(), nx.TZ)
    return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


# ---------- recording ----------

def log(c, uid, skill, kind, score, level=None, pack=None, commit=True):
    if not uid or skill not in EVENT_SKILLS:
        return
    score = max(0.0, min(1.0, float(score)))
    c.execute('INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(?,?,?,?,?,?,?)',
              (uid, skill, kind, score, level if level in LEVELS else None, pack, time.time()))
    if commit:
        c.commit()


def add_mistake(c, uid, kind, text, norm, meaning='', context='', skill=None, node=None, pack=None, extra=None, commit=True):
    """A mistake becomes a card on the forgetting curve. The same mistake again just brings it back to today."""
    if not uid or kind not in MISTAKE_KINDS or not text:
        return None
    now = time.time()
    norm = norm[:300]
    # One statement, so two requests at once (a double tap) cannot both find nothing and both insert: the second one
    # meets UNIQUE(user_id, norm) and brings the card back to today instead (b38 self-check, 500 under 60 at once).
    c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,skill,node,extra) '
              'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id, norm) DO UPDATE SET due=MIN(due, excluded.due), known=0',
              (uid, text[:300], norm, (meaning or '')[:300], (context or '')[:600], pack, kind, now, now, 'new', 'mistake',
               skill, node, json.dumps(extra or {}, ensure_ascii=False)))
    cid = c.execute('SELECT id FROM next_cards WHERE user_id=? AND norm=?', (uid, norm)).fetchone()['id']  # lastrowid is not the row after an update
    if commit:
        c.commit()
    return cid


def mistakes_from_changes(c, uid, changes, sentence, skill, pack=None, limit=3):
    """Corrections from AI feedback ({from, to, why, node}) become fix cards."""
    for ch in (changes or [])[:limit]:
        frm, to = (ch.get('from') or '').strip(), (ch.get('to') or '').strip()
        if not to or frm in ('', '—') or frm.lower() == to.lower() or len(frm) > 160:
            continue
        # keep the sentence the mistake was in, not the whole essay or retelling
        ctx = next((x for x in nx.sentences(sentence or '') if frm.lower() in x.lower()), sentence or '')[:600]
        add_mistake(c, uid, 'fix', to, 'fix:' + nx._norm(frm + ' > ' + to), ch.get('why') or '', ctx, skill,
                    ch.get('node'), pack, {'from': frm}, commit=False)
    c.commit()


# ---------- the profile ----------

def _events(c, uid, since):
    return c.execute('SELECT skill, kind, score, level, created FROM next_skill_events WHERE user_id=? AND created>?', (uid, since)).fetchall()


def _estimate(evts, home='B1'):
    """Highest level with at least two attempts averaging PASS. Without a pass: the easiest level tried when the
    learner is getting about half of it (still working at that level), one below only when clearly struggling.
    Fewer than three attempts in all is not enough to say anything."""
    if len(evts) < 3:
        return None
    by = {}
    for e in evts:
        by.setdefault(e['level'] or home, []).append(e['score'])
    best = None
    for lv in LEVELS:
        s = by.get(lv)
        if s and len(s) >= 2 and sum(s) / len(s) >= PASS:
            best = lv
    if best:
        return best
    tried = [lv for lv in LEVELS if by.get(lv)]
    lowest = LEVELS.index(tried[0])
    s = by[tried[0]]
    return LEVELS[lowest] if sum(s) / len(s) >= 0.5 else LEVELS[max(0, lowest - 1)]


def _vocab_level(size):
    if not size:
        return None
    return 'A2' if size < 2000 else 'B1' if size < 4000 else 'B2' if size < 7000 else 'C1'


def ability(c, uid, now=None):
    """Per-skill CEFR estimate with the evidence behind it and an 8-week trend of average scores."""
    now = now or time.time()
    evts = _events(c, uid, now - 56 * 86400)
    recent = [e for e in evts if e['created'] > now - 45 * 86400]
    home = (nx.profile(c, uid) or {}).get('level') or 'B1'
    out = {}
    for sk in EVENT_SKILLS:
        es = [e for e in recent if e['skill'] == sk]
        weeks = []
        for w in range(7, -1, -1):
            lo, hi = now - (w + 1) * 7 * 86400, now - w * 7 * 86400
            s = [e['score'] for e in evts if e['skill'] == sk and lo < e['created'] <= hi]
            weeks.append(round(sum(s) / len(s), 2) if s else None)
        out[sk] = {'label': SKILLS[sk], 'level': _estimate(es, home), 'count': len(es),
                   'avg': round(sum(e['score'] for e in es) / len(es), 2) if es else None, 'weeks': weeks}
    plan = c.execute('SELECT estimate FROM next_vocab_plans WHERE user_id=?', (uid,)).fetchone()
    mastered = c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND kind='word' AND (known=1 OR stability>=21)", (uid,)).fetchone()[0]
    size = (plan['estimate'] if plan and plan['estimate'] else 0) or 0
    out['vocab'] = {'label': SKILLS['vocab'], 'level': _vocab_level(size), 'count': mastered, 'size': size, 'avg': None, 'weeks': []}
    states = nx.graph_states(c, uid)
    touched = [s for s in states.values() if s['status'] != 'untouched']
    good = sum(1 for s in states.values() if s['status'] in ('solid', 'used'))
    watch = sum(1 for s in states.values() if s['status'] == 'watch')
    # Judged on the points the learner has actually written with: how many came out right rather than flagged.
    shown = good + watch
    ratio = good / max(1, shown)
    out['grammar'] = {'label': SKILLS['grammar'], 'count': good, 'avg': None, 'weeks': [], 'watch': watch,
                      'level': None if shown < 4 else 'A2' if ratio < 0.35 else 'B1' if ratio < 0.6 else 'B2' if ratio < 0.85 else 'C1'}
    known = [sk for sk in ('listening', 'reading', 'speaking', 'writing') if out[sk]['level']]
    weakest = min(known, key=lambda sk: (LEVELS.index(out[sk]['level']), out[sk]['avg'] or 0)) if known else None
    order = ['vocab', 'grammar', 'listening', 'reading', 'speaking', 'writing', 'translation', 'pronunciation']
    return {'skills': [{'id': k, **out[k]} for k in order], 'weakest': weakest}


def suggest_level(c, uid, now=None):
    """Adaptive difficulty: after enough comprehension and dictation at the learner's level, suggest moving up or down.
    None with 按我的学习记录推荐 switched off (next_service.follows_records)."""
    prof = nx.profile(c, uid)
    if not prof or not nx.follows_records(prof):
        return None
    now = now or time.time()
    cur = 'C1' if prof['level'] == 'C1' else prof['level']
    es = [e for e in _events(c, uid, now - 21 * 86400) if e['skill'] in ('reading', 'listening') and e['level'] == cur]
    if len(es) < 6:
        return None
    avg = sum(e['score'] for e in es) / len(es)
    i = LEVELS.index(cur)
    if avg >= 0.85 and i < len(LEVELS) - 1:
        return {'direction': 'up', 'to': LEVELS[i + 1], 'reason': f'最近 {len(es)} 次 {cur} 的理解题和听写平均 {round(avg * 100)}%，可以试试更难一点的材料。'}
    if avg < 0.5 and i > 0:
        return {'direction': 'down', 'to': LEVELS[i - 1], 'reason': f'最近 {len(es)} 次 {cur} 的理解题和听写平均只有 {round(avg * 100)}%，先降一级打牢基础会更顺。'}
    return None


# ---------- the daily path ----------

OUTPUTS = {  # what to practise when this skill is the weak spot; href is completed by the front end with today's material
    'speaking': ('retell', '复述今天这篇', '用自己的话讲一遍，AI 看你讲到了哪些要点'),
    'writing': ('essay', '写一段短文', '按评分维度批改，错误进错题本'),
    'translation': ('translate', '翻译练习', '汉译英，对照原文找差距'),
    'listening': ('dictate', '逐句听写', '听错的词直接进复习'),
    'reading': ('retell', '复述今天这篇', '先读懂，再讲出来'),
}


# Minutes of each output task, and the one that fits two minutes (r28: 15 and 20 minutes a day give output two).
OUT_MIN = {'model': 2, 'sounds': 3, 'dictate': 3, 'retell': 4, 'translate': 5, 'essay': 8}
MODEL = ('model', '仿写一句', '照今天这篇里的一句话，换成你自己的内容，AI 帮你改')
EXTRA = 4  # 「还有时间的话」 shows at most this many
# 回归模式 (r28 第 2 段): after this many days or more without study, the day back is short.
BACK_DAYS = 3
BACK_WORDS = 40  # the words most due first, one round (vocab_service.BATCH); the rest over the next days
BACK_KEEP = ('review', 'relisten', 'read')


def _easier(c, uid, level, now):
    """A featured text one level below, not learned yet, the same one all day; None at A2 or when there is none."""
    import hashlib
    order = list(nx.LEVELS)
    if level not in order or not order.index(level):
        return None
    down, done = order[order.index(level) - 1], nx._done(c, uid)
    rows = [p for r, p in nx._public_packs(c, down) if r['origin'] != 'daily' and nx.featured(p) and not p.get('series')
            and 'check' not in done.get(p['id'], set())]
    if not rows:
        return None
    day, goal = nx._day(now), (nx.profile(c, uid) or {}).get('goal')
    suits = getattr(nx, 'suits_goal', None)
    p = min(rows, key=lambda p: (not (suits and suits(p, goal)), hashlib.sha256(f"{day}|{p['id']}".encode()).hexdigest()))
    return {**nx._card(p, done.get(p['id'])), 'easier': down}
READ_SUB = {'glance': '只听一遍，或只读一段', 'listen-read': '听一遍，再读一遍', 'core': '听、读、做理解题'}


def daily_path(c, uid, home, now=None):
    """Today's plan packed into the learner's minutes (time_budget, r28 第 1 段). Every step says about how long it takes
    ('minutes') and which part of the day's budget it uses ('part'). 必做 ('group': 'must') holds the words, today's text
    and whatever fits its part; the rest is 「还有时间的话」 ('extra', not counted in done / total); the week's exam set
    is 本周任务 ('week'). 'studied' is today's minutes from the learner's own records; 'over' once they pass the
    minutes chosen by a fifth with 必做 not done."""
    import inspect
    import progress_service as ps
    import time_budget as tb
    import vocab_service as vs
    now = now or time.time()
    start = _day_start(now)
    prof = nx.profile(c, uid) or {}
    minutes = prof.get('minutes') or 10
    # 考试冲刺 (exam_sprint): in the last four weeks before the learner's exam, the weekly set of that exam and a round
    # on its grammar points join the plan, whatever the goal.
    sprint = home.get('sprint') if 'sprint' in home else __import__('exam_sprint').brief(c, uid, now)
    sprinting = bool(sprint and sprint['sprint'])
    exams = __import__('exam_service')
    drill = getattr(exams, 'drill_step', None)  # 考试小练 (r28 第 4 段); until it exists exam learners keep the usual day
    b = tb.budget(minutes, exam=bool(drill) and (prof.get('goal') == 'exam' or sprinting))
    # The words step is capped (r28 第 3 段): vocab_service sizes the day's share once it takes the cap.
    n = vs.counts(c, uid, now, cap=b['words']) if 'cap' in inspect.signature(vs.counts).parameters else vs.counts(c, uid, now)
    pick = (home.get('today') or [None])[0]
    # The material studied today stays "today's" even after it is finished (the recommendations move on).
    # Today's steps, a text studied again included (progress_service.steps_since: next_progress keeps the first time only).
    today_steps = ps.steps_since(c, uid, start)

    def material(pid):
        pr = nx._pack_row(c, uid, pid)
        if not pr:
            return None
        d = json.loads(pr['content'])
        return {'id': pid, 'title': d['title'], 'words': len((d.get('body') or '').split())}
    row = max(today_steps, key=lambda r: (r['step'] in ('check', 'output'), r['created']), default=None)
    if row:
        pick = material(row['pack']) or pick
    done_steps = {r['step'] for r in today_steps if pick and r['pack'] == pick['id']}
    kind_n = {r['kind']: r['n'] for r in c.execute('SELECT kind, COUNT(*) n FROM next_skill_events WHERE user_id=? AND created>=? GROUP BY kind', (uid, start))}
    today_kinds = set(kind_n)
    # 回归模式 (r28 第 2 段): BACK_DAYS or more days without study before today make today the day back, all day long:
    # the words most due first (one round of BACK_WORDS), a text half read before or one a level easier, and nothing
    # else; the next day is an ordinary one again.
    back = None
    before = ps.study_days(c, uid, now - 400 * 86400, start)
    if before:
        missed = (ps._local(now).date() - max(before)).days - 1
        if missed >= getattr(vs, 'BACK_DAYS', BACK_DAYS):
            back = {'days': missed, 'left': 0}
            if not row and nx.follows_records(prof):  # off (我的 → 设置): no easier text picked from the records
                half = home.get('resume') if home.get('resume') and 'check' not in (home['resume'].get('steps') or []) else None
                pick = half or _easier(c, uid, prof.get('level') or 'B1', now) or pick
                done_steps = set()
    steps = []

    def add(step, mins, parts, rank, must=None):
        """rank: the order in which 必做 is filled part by part, and 「还有时间的话」 is listed; must: always 必做."""
        steps.append({**step, 'minutes': max(0, int(mins)), '_parts': parts, '_rank': rank, '_must': must})
    todo = n['due'] + n['new']
    if not todo and not vs.plan(c, uid):
        # No word book yet: 「单词」 would only tick itself, and a newcomer (one preparing for an exam above all) would not
        # know a book is waiting to be chosen. Ask for one; 背词计划 opens with the exam's book (or the level's) chosen.
        exam = prof.get('exam') if prof.get('exam') in vs.book_words() else None
        book = exam or vs.LEVEL_BOOK.get(prof.get('level') or 'B1', 'mid')
        add({'key': 'review', 'title': '选一本词书', 'href': '#/vocab/plan', 'done': False,
             'sub': f"按你的考试先选好了《{vs.book_title(book)}》，确认一下就能每天背" if exam else f"先给你挑了《{vs.book_title(book)}》，每天背几个新词"},
            1, ('words',), 0, must=True)
    elif back and n['due'] and 'catch_up' not in n:  # before vocab_service sizes the day's share (r28 第 3 段)
        # the day back: one round of the words most due (the ones answered today count towards it); the rest come over
        # the next days
        answered = c.execute('SELECT COUNT(DISTINCT card) FROM next_reviews WHERE user_id=? AND created>=?', (uid, start)).fetchone()[0]
        first = min(n['due'] + answered, BACK_WORDS)
        left = max(0, first - answered)
        back['left'] = max(0, n['due'] - left)
        add({'key': 'review', 'title': f'单词：先复习最该复习的 {first} 个' if n['due'] + answered > first else f'单词：复习 {first} 个',
             'sub': '今天复习完这一轮就好' if left else '这一轮复习完了', 'href': '#/review', 'done': not left},
            vs.minutes_for(left, 0, vs.answer_seconds(c, uid, now)) if left else 0, ('words',), 0, must=True)
    else:
        title = '单词：' + ' · '.join(x for x in (f"复习 {n['due']}" if n['due'] else '', f"新词 {n['new']}" if n['new'] else '') if x) if todo else '单词'
        cu = n.get('catch_up')  # 补积压 (r28 第 3 段): after days away, the backlog over the next days, no new words meanwhile
        if back and 'catch_up' in n:
            back.update(left=cu['left'] if cu else n.get('later') or 0, catch_days=cu['days'] if cu else None)
        later = [f"还有 {n['later']} 个复习留到之后几天" if n.get('later') else '',
                 ('新词明天继续' if n.get('later') else '今天先复习，新词明天继续') if n.get('new_paused') else '']
        sub = ((f"补积压：还剩 {cu['left']} 个，大约 {cu['days']} 天补完" if cu else ' · '.join(x for x in later if x)
                or ('复习到期的词，再学新词' if n['new'] and n['due'] else '')) if todo else '今天的都完成了')
        if back and cu and todo:
            title = f"单词：先复习最容易忘的 {n['due']} 个"  # the first day's share of the backlog
        add({'key': 'review', 'title': title, 'sub': sub, 'href': '#/review', 'done': not todo}, n['minutes'] if todo else 0, ('words',), 0, must=True)
    if minutes >= 10:
        # 复听 (relisten_service): a text from a few days ago heard again without the words, before today's new one
        import relisten_service as rl
        heard, waiting = rl.today(c, uid, start), None
        if not heard:
            waiting = next(iter(rl.due(c, uid, now, exclude={pick['id']} if pick else set())), None)
        it = {'pack': heard[-1]['pack']} if heard else waiting
        m3 = it and material(it['pack'])
        if m3:
            ago = max(1, round((now - waiting['first']) / 86400)) if waiting else 0
            add({'key': 'relisten', 'title': '复听：' + m3['title'], 'href': f"#/m/{it['pack']}/listen/again", 'done': bool(heard),
                 'sub': f"今天复听过了：听懂了{rl.LABELS[heard[-1]['understood']]}" if heard else f'{ago} 天前学过 · 先不看原文听一遍'},
                3, ('relisten',), 2)
    if pick:
        # Today's text, in the day's mode: at 5 minutes one listen or one paragraph; with 考试小练 at 10, heard and read.
        mode = b['read_mode']
        did = done_steps if mode == 'glance' else done_steps & {'read', 'check', 'output'} if mode == 'listen-read' else done_steps & {'check', 'output'}
        easier = back and pick.get('easier')
        add({'key': 'read', 'title': '今天这篇', 'sub': pick['title'] + (f" · 低一级（{easier}），先找回状态" if easier else ''), 'href': f"#/m/{pick['id']}",
             'done': bool(did), 'mode': mode, 'mode_label': READ_SUB[mode]},
            tb.read_minutes(pick.get('words'), mode), ('read',), 1, must=True)
    if minutes >= 45 and pick:
        # A longer day gets a second material: the next recommendation, or the one already started today.
        other = next((m for m in (home.get('today') or []) if m and m['id'] != pick['id']), None)
        row2 = next((r for r in reversed(today_steps) if r['pack'] != pick['id']), None)
        if row2 and material(row2['pack']):
            other = material(row2['pack'])
        if other:
            st2 = {r['step'] for r in today_steps if r['pack'] == other['id']}
            add({'key': 'read2', 'title': '再读一篇', 'sub': other['title'], 'href': f"#/m/{other['id']}", 'done': 'check' in st2 or 'output' in st2},
                tb.read_minutes(other.get('words'), 'core'), ('read', 'other'), 8)
    # With goals set, the output step works on the skill furthest from its goal on the radar; otherwise the weakest estimate.
    # 按我的学习记录推荐 switched off: the skill goes round by the day instead (speaking, writing, listening, reading)
    weakest = (__import__('ability_radar').weakest(c, uid, now) or ability(c, uid, now)['weakest']) if nx.follows_records(prof) else \
        ('speaking', 'writing', 'listening', 'reading')[datetime.date.fromisoformat(nx._day(now)).toordinal() % 4]
    level = prof.get('level') or 'B1'
    if level == 'A2' and minutes <= 10 and 'say' not in today_kinds:
        key, title, sub = 'sounds', '发音入门', '容易混的音，听辨 + 跟读'
        href = '#/sounds'
    else:
        goal = prof.get('goal')
        skill = 'translation' if goal == 'exam' and level != 'A2' and weakest in (None, 'writing') else (weakest or 'speaking')
        key, title, sub = OUTPUTS.get(skill, OUTPUTS['speaking'])
        if minutes <= 5 and key == 'essay':
            key, title, sub = OUTPUTS['speaking']
        href = f"#/m/{pick['id']}/output/{key}" if pick and key != 'dictate' else (f"#/m/{pick['id']}/listen" if pick else '#/library')
    kinds = {'retell': {'retell'}, 'essay': {'essay'}, 'translate': {'translate'}, 'dictate': {'dictation'}, 'sounds': {'say', 'discriminate'}, 'model': {'rewrite'}}
    out_step = {'key': key, 'title': title, 'sub': sub, 'href': href, 'done': bool(kinds.get(key, set()) & today_kinds)}
    if b['output'] + 1 < OUT_MIN[key] and pick and b['output'] >= OUT_MIN['model']:
        # Too little time for the weak skill's task: one sentence modelled on today's text is 必做, the task waits below.
        mk, mt, ms = MODEL
        add({'key': mk, 'title': mt, 'sub': ms, 'href': f"#/m/{pick['id']}/output", 'done': bool(kinds[mk] & today_kinds)}, OUT_MIN[mk], ('output',), 3)
        add(out_step, OUT_MIN[key], ('output', 'other'), 4)
    else:
        add(out_step, OUT_MIN[key], ('output',), 3)
    # Grammar: one mixed review a day of the points flagged in writing or practice and those whose re-check has come
    # (several points interleaved, one or two questions each). The step is done once a round's worth is answered today;
    # whatever was missed comes back tomorrow on a different question, so the day always ends.
    practised = c.execute("SELECT COUNT(*) FROM learning_events WHERE user_id=? AND source LIKE 'next-node:%' AND created>=?", (uid, start)).fetchone()[0]
    nodes = nx.GB.mix_nodes(c, uid, now)
    if nodes or practised:
        titles = nx.nodes_meta(c)
        size = min(8, max(4, min(len(nodes), 6))) if nodes else 4
        if practised >= min(4, size):
            left = len(nodes)
            add({'key': 'grammar', 'title': '语法复习', 'href': '#/mix',
                 'sub': f'今天做了 {practised} 题' + (f' · 还有 {left} 个点明天接着练' if left else ' · 都练到了'), 'done': True}, max(1, practised // 2), ('grammar',), 7)
        else:
            names = '、'.join(titles.get(n, {}).get('title', n) for n in nodes[:2]) + (f' 等 {len(nodes)} 个点' if len(nodes) > 2 else '')
            add({'key': 'grammar', 'title': '语法混合复习：' + names, 'href': '#/mix', 'sub': f'{size} 道题混着做', 'done': False},
                max(2, size // 2), ('grammar',), 7)
    if drill and b['exam']:
        st = drill(c, uid, b['exam'], now)
        if st:
            add(st, st.get('minutes') or b['exam'], ('exam',), 5)
    week = []
    if (prof.get('goal') == 'exam' and minutes >= 10) or sprinting:
        # 本周任务: the week's timed set, any day of the week (Monday on), outside the daily budget. A newcomer's first
        # week calls it a first look that can be skipped.
        ex = sprint['exam'] if sprint else ''
        monday = ps._bounds(now)[2]
        last = c.execute('SELECT MAX(created) t FROM next_exam_results WHERE user_id=?' + (' AND exam=?' if ex else ''), (uid, ex) if ex else (uid,)).fetchone()['t']
        made = c.execute('SELECT created FROM next_profiles WHERE user_id=?', (uid,)).fetchone()
        first = not last and not sprinting and bool(made and made['created'] and made['created'] > now - 7 * 86400)
        set_minutes = getattr(exams, 'set_minutes', None)
        mins = set_minutes(ex, minutes, sprinting) if set_minutes and ex else exams.EXAMS[ex]['minutes'] if ex in exams.EXAMS else 15
        title, href = ('考试练习：' + sprint['short'], '#/exam/' + ex) if ex else ('考试练习', '#/exam')
        done = bool(last and last >= monday)
        week.append({'key': 'exam', 'title': title, 'href': href, 'done': done, 'minutes': mins, 'part': 'week', 'group': 'week', 'first': first,
                     'sub': '这周的一套做完了' if done else (f"考前 {sprint['days']} 天 · " if sprinting else '摸底，可以跳过 · ' if first else '')
                     + '词汇、语法、阅读限时一套，这周哪天做都行'})
    if sprinting:
        import exam_sprint as sp
        answered = sp.grammar_today(c, uid, now)
        pts = sp.grammar_nodes(c, uid, sprint['exam'], now)[:6]
        if pts:
            titles = nx.nodes_meta(c)
            names = '、'.join(titles.get(n, {}).get('title', n) for n in pts[:2]) + (f' 等 {len(pts)} 个点' if len(pts) > 2 else '')
            add({'key': 'exam-grammar', 'title': f"考点语法：{names}", 'href': '#/mix/exam/' + sprint['exam'], 'done': answered >= 4,
                 'sub': f'今天做了 {answered} 题' if answered >= 4 else f"{sprint['short']}常考的语法点混着练，8 道题"}, 4, ('grammar', 'exam'), 6)
    stale = __import__('ability_radar').due_today(c, uid, now)
    last_test = c.execute('SELECT MAX(created) FROM next_assess WHERE user_id=?', (uid,)).fetchone()[0]
    if stale and not (last_test and start - 2 * 86400 <= last_test < start):  # a test every few days, not every day
        tested = c.execute('SELECT COUNT(*) FROM next_assess WHERE user_id=? AND created>=?', (uid, start)).fetchone()[0]
        names = '、'.join(dict(__import__('ability_radar').DIMS)[k] for k in stale[:3])
        add({'key': 'assess', 'title': '能力测评', 'href': '#/radar/test', 'done': bool(tested),
             'sub': '今天测过了，雷达图已更新' if tested else f'{names}{"等" if len(stale) > 3 else ""}该测一测了，选一项就行'}, 5, ('other',), 11)
    if minutes >= 30:
        # Easy reading: a lot of easy text builds fluency; one short text a day on longer days.
        n_easy = __import__('easy_reading').read_today(c, uid, start)
        add({'key': 'easy', 'title': '轻松读一篇', 'href': '#/easy', 'done': bool(n_easy),
             'sub': f'今天读了 {n_easy} 篇' if n_easy else '比你的水平低一点，只读不做题'}, 3, ('other',), 10)
    ielts = __import__('ielts_speaking')
    to_ielts = ielts.for_ielts(c, uid, prof)
    if key != 'retell' and (minutes >= 30 or ((prof.get('goal') in ('abroad', 'daily', 'work') or to_ielts) and minutes >= 20)):
        # The speaking route: one role-play scene, unless today's output step is already spoken. Heading for IELTS
        # (abroad, or the IELTS exam): the next 雅思口语 Part 1 topic instead, round after round.
        spoke = c.execute("SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND skill='speaking' AND created>=?", (uid, start)).fetchone()[0]
        if to_ielts:
            t = ielts.next_part1(c, uid)
            add({'key': 'speak', 'title': '口语：' + ('雅思 Part 1 · ' + t['title'] if not spoke else '雅思口语'), 'done': bool(spoke),
                 'href': f"#/speak/ielts/p1-{t['id']}",
                 'sub': '今天说过了' if spoke else '考官问 4 个问题，说完看四项估计分' + ('（再练一轮）' if t['round'] else '')}, 5, ('other',), 9)
        sp = None if to_ielts else __import__('scenarios').listing(c, uid, level)
        if sp and (sp['next'] or spoke):
            nxt = next((x for x in sp['items'] if x['id'] == sp['next']), None)
            # a scene done before comes back as round 2, 3…: one more requirement, or the roles swapped (scenarios.mode_of)
            again = nxt and nxt['rounds'] > 0
            sub = ('今天说过了' if spoke else f"这次多一条：{nxt['challenge']}" if again and nxt['mode'] == 'challenge'
                   else f"换角色：你演{nxt['ai']}，AI 演{nxt['me']}" if again else '和 AI 演一个情景，说四五句')
            add({'key': 'speak', 'title': '口语：' + (nxt['title'] + (f" · 第 {nxt['round']} 轮" if again else '') if nxt and not spoke else '情景对话'),
                 'done': bool(spoke), 'href': '#/speak/' + nxt['id'] if nxt else '#/speak', 'sub': sub}, 5, ('other',), 9)
    if minutes >= 15 and key != 'dictate' and pick:
        add({'key': 'dictate', 'title': '听写三句', 'sub': f"练耳朵，也练拼写 · 今天 {min(3, kind_n.get('dictation', 0))}/3", 'href': f"#/m/{pick['id']}/listen",
             'done': kind_n.get('dictation', 0) >= 3}, 3, ('other',), 12)
    if back:  # the day back: words, 复听 when it fits, a text; output, grammar and the rest from tomorrow
        steps = [s for s in steps if s['key'] in BACK_KEEP]
    # Packing: part by part in rank order, a step is 必做 if its part has its minutes left (a minute over is fine).
    room = {p: b[p] for p in tb.PARTS}
    for s in sorted(steps, key=lambda s: s['_rank']):
        part = s['_parts'][0] if s['_must'] else next((p for p in s['_parts'] if s['minutes'] <= room[p] + 1), None)
        s['group'], s['part'] = ('must', part) if part else ('extra', s['_parts'][0])
        if part:
            room[part] -= s['minutes']
    must = [s for s in steps if s['group'] == 'must']
    extra = [] if back else sorted((s for s in steps if s['group'] == 'extra'), key=lambda s: s['_rank'])[:EXTRA]
    for s in must + extra:
        for k in ('_parts', '_rank', '_must'):
            s.pop(k)
    done = sum(1 for s in must if s['done'])
    studied = ps.active_minutes(c, uid, start, now + 1)
    return {'minutes': minutes, 'budget': b, 'steps': must + extra + week, 'done': done, 'total': len(must),
            'must_minutes': sum(s['minutes'] for s in must), 'left_minutes': sum(s['minutes'] for s in must if not s['done']),
            'studied': studied, 'over': studied >= tb.over_at(minutes) and done < len(must), 'back': back}


# ---------- weekly report ----------

def report(c, uid, now=None):
    now = now or time.time()
    # The last 7 calendar days, today included (the page shows 「from – to」 and says 这 7 天): from midnight 6 days ago,
    # so every count covers exactly those dates (7×24 hours back reached into an 8th date: 学习天数 8 for a 7-day range).
    # The 7 days before them are the comparison.
    week = (datetime.datetime.fromtimestamp(now, nx.TZ).replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=6)).timestamp()
    prev = week - 7 * 86400
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    days = set()
    for (t,) in c.execute('SELECT created FROM next_progress WHERE user_id=? AND created>? UNION ALL SELECT created FROM next_reviews WHERE user_id=? AND created>? '
                          'UNION ALL SELECT created FROM next_skill_events WHERE user_id=? AND created>? UNION ALL SELECT created FROM next_relisten WHERE user_id=? AND created>?',
                          (uid, week, uid, week, uid, week, uid, week)):
        days.add(nx._day(t))
    evts = _events(c, uid, prev)
    def avg(sk, lo, hi):
        s = [e['score'] for e in evts if e['skill'] == sk and lo < e['created'] <= hi]
        return round(sum(s) / len(s), 2) if s else None
    skills = [{'id': sk, 'label': SKILLS[sk], 'now': avg(sk, week, now), 'before': avg(sk, prev, week),
               'count': sum(1 for e in evts if e['skill'] == sk and e['created'] > week)} for sk in EVENT_SKILLS]
    reviews = q("SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND created>? AND rating IN ('again','hard','good','easy')", uid, week)
    import progress_service as ps
    learned = ps.new_words(c, uid, week, now + 1)  # first answered this week, not just put into the queue
    mastered = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND kind='word' AND stability>=21 AND last>?", uid, week)
    fixed = q("SELECT COUNT(DISTINCT r.card) FROM next_reviews r JOIN next_cards k ON k.id=r.card WHERE r.user_id=? AND r.created>? AND k.source='mistake' AND r.rating IN ('good','easy')", uid, week)
    new_mistakes = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND source='mistake' AND created>?", uid, week)
    materials = len(ps._finished(c, uid, week, now + 1))  # a text studied again this week counts too
    outputs = q("SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND created>? AND kind IN ('rewrite','retell','dialog','essay','translate')", uid, week)
    minutes = round(reviews * 0.15 + materials * 9 + outputs * 4 + q('SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND created>?', uid, week) * 0.5)
    meta = nx.nodes_meta(c)
    watch = [{'id': n, 'title': meta.get(n, {}).get('title', n)} for n, s in nx.graph_states(c, uid).items() if s['status'] == 'watch'][:3]
    ab = ability(c, uid, now)
    focus = None
    backlog = __import__('vocab_service').counts(c, uid, now)['due']
    if backlog > 100:  # a pile of words due comes first: it only grows while other things are practised
        focus = f'先把单词积压清掉：现在有 {backlog} 个单词到了复习时间。接下来几天，每天先复习一轮，再学新的内容。'
    elif ab['weakest'] and nx.follows_records(nx.profile(c, uid)):  # 按我的学习记录推荐 off: no advice picked from the records
        name = SKILLS[ab['weakest']]
        what = {'speaking': '每天复述一篇或和 AI 对话一轮', 'writing': '写一段短文让 AI 批改', 'listening': '每天听写三句', 'reading': '先读懂再做理解题'}
        focus = f"{name}是现在最弱的一项，接下来几天{what.get(ab['weakest'], '多练这一项')}。"
    elif not days:
        focus = '这 7 天还没学：每天 10 分钟，先从今天这篇开始。'
    return {'from': nx._day(week), 'to': nx._day(now), 'days': len(days), 'minutes': minutes, 'materials': materials, 'outputs': outputs,
            'reviews': reviews, 'learned': learned, 'mastered': mastered, 'mistakes_new': new_mistakes, 'mistakes_fixed': fixed,
            'skills': skills, 'watch': watch, 'focus': focus, 'ability': ab['skills'], 'relisten': __import__('relisten_service').week(c, uid, week),
            **_week_more(c, uid, now, week, prev)}


def _week_more(c, uid, now, week, prev):
    """The rest of the week: easy reading (texts, words, speed), speaking scenes, and how the ability radar moved."""
    import ability_radar as ar, scenarios
    n, words, wpm = c.execute('SELECT COUNT(*), COALESCE(SUM(words),0), AVG(wpm) FROM next_easy_reads WHERE user_id=? AND created>?', (uid, week)).fetchone()
    wpm0 = c.execute('SELECT AVG(wpm) FROM next_easy_reads WHERE user_id=? AND created>? AND created<=?', (uid, prev, week)).fetchone()[0]
    scene = lambda since: {r[0][6:] for r in c.execute("SELECT DISTINCT pack FROM next_skill_events WHERE user_id=? AND kind='dialog' AND pack LIKE 'scene-%' AND created>?", (uid, since))} & set(scenarios.SCENES)
    g, chosen = ar.goals(c, uid)
    snaps = [(r[0], json.loads(r[1]), r[2]) for r in c.execute('SELECT created, scores, source FROM next_radar WHERE user_id=? ORDER BY created', (uid,))]
    last = lambda k, until: next((s[1][k] for s in reversed(snaps) if s[0] <= until and s[1].get(k) is not None), None)
    moves = []
    for k, label in ar.DIMS:  # each skill's latest measure, against its latest one from before this week
        now_s = ar._score(last(k, now), g[k])
        if now_s is not None:
            moves.append({'id': k, 'label': label, 'now': now_s, 'before': ar._score(last(k, week), g[k])})
    return {'easy': {'texts': n, 'words': words, 'wpm': round(wpm) if wpm else None, 'wpm_before': round(wpm0) if wpm0 else None},
            'speaking': {'scenes_week': len(scene(week)), 'scenes_done': len(scene(0)), 'scenes_total': len(scenarios.SCENES)},
            'radar': {'moves': moves, 'tests_week': sum(1 for s in snaps if s[0] > week and s[2] != 'auto'), 'goals_chosen': chosen}}


def send_weekly(c, now=None, send=None):
    """The Sunday mail (r27: progress_service.send_weekly): every learner with a bound email, with a link to stop it."""
    return __import__('progress_service').send_weekly(c, now, send)


# ---------- routes ----------

def post_skill(c, uid, data):
    """Client-scored practice (dictation, sound discrimination) reports its score here."""
    kind = data.get('kind')
    allowed = {'dictation': 'listening', 'discriminate': 'pronunciation'}
    if kind not in allowed or not isinstance(data.get('score'), (int, float)):
        return {'error': '记录格式不正确'}, 400
    pack = data.get('pack') if isinstance(data.get('pack'), str) and len(data['pack']) <= 80 else None
    level = None
    if pack:
        row = nx._pack_row(c, uid, pack)
        level = nx.cefr(json.loads(row['content'])) if row else None
    log(c, uid, allowed[kind], kind, data['score'], level, pack)
    return {'ok': True}, 200


def get(c, uid, path, q):
    if path == '/api/next/ability':
        return {**ability(c, uid), 'suggest': suggest_level(c, uid)}, 200
    if path == '/api/next/report':
        return report(c, uid), 200
    return None


def post(c, uid, path, data):
    if path == '/api/next/skill':
        return post_skill(c, uid, data)
    return None
