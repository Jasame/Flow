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
    row = c.execute('SELECT id FROM next_cards WHERE user_id=? AND norm=?', (uid, norm)).fetchone()
    if row:
        c.execute('UPDATE next_cards SET due=MIN(due, ?), known=0 WHERE id=?', (now, row['id']))
        cid = row['id']
    else:
        cur = c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,skill,node,extra) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (uid, text[:300], norm, (meaning or '')[:300], (context or '')[:600], pack, kind, now, now, 'new', 'mistake',
                         skill, node, json.dumps(extra or {}, ensure_ascii=False)))
        cid = cur.lastrowid
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
    """Adaptive difficulty: after enough comprehension and dictation at the learner's level, suggest moving up or down."""
    prof = nx.profile(c, uid)
    if not prof:
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


def daily_path(c, uid, home, now=None):
    """Today's plan sized to the learner's minutes: review, today's material, one output task matched to the weak skill."""
    import vocab_service as vs
    now = now or time.time()
    start = _day_start(now)
    prof = nx.profile(c, uid) or {}
    minutes = prof.get('minutes') or 10
    n = vs.counts(c, uid, now)
    pick = (home.get('today') or [None])[0]
    # The material studied today stays "today's" even after it is finished (the recommendations move on).
    row = c.execute("SELECT pack FROM next_progress WHERE user_id=? AND created>=? ORDER BY (step IN ('check','output')) DESC, created DESC LIMIT 1",
                    (uid, start)).fetchone()
    if row:
        pr = nx._pack_row(c, uid, row['pack'])
        if pr:
            pick = {'id': row['pack'], 'title': json.loads(pr['content'])['title']}
    done_steps = {r['step'] for r in c.execute('SELECT step FROM next_progress WHERE user_id=? AND pack=? AND created>=?',
                                                (uid, pick['id'] if pick else '', start))}
    kind_n = {r['kind']: r['n'] for r in c.execute('SELECT kind, COUNT(*) n FROM next_skill_events WHERE user_id=? AND created>=? GROUP BY kind', (uid, start))}
    today_kinds = set(kind_n)
    steps = []
    todo = n['due'] + n['new']
    title = '单词：' + ' · '.join(x for x in (f"复习 {n['due']}" if n['due'] else '', f"新词 {n['new']}" if n['new'] else '') if x) if todo else '单词'
    steps.append({'key': 'review', 'title': title, 'sub': f"约 {n['minutes']} 分钟" if todo else '今天的都完成了',
                  'href': '#/review', 'done': not todo})
    if pick:
        steps.append({'key': 'read', 'title': '今天这篇', 'sub': pick['title'], 'href': f"#/m/{pick['id']}",
                      'done': 'check' in done_steps or 'output' in done_steps})
    if minutes >= 45 and pick:
        # A longer day gets a second material: the next recommendation, or the one already started today.
        other = next((m for m in (home.get('today') or []) if m and m['id'] != pick['id']), None)
        row2 = c.execute("SELECT pack FROM next_progress WHERE user_id=? AND created>=? AND pack!=? ORDER BY created DESC LIMIT 1",
                         (uid, start, pick['id'])).fetchone()
        if row2 and nx._pack_row(c, uid, row2['pack']):
            other = {'id': row2['pack'], 'title': json.loads(nx._pack_row(c, uid, row2['pack'])['content'])['title']}
        if other:
            st2 = {r['step'] for r in c.execute('SELECT step FROM next_progress WHERE user_id=? AND pack=? AND created>=?', (uid, other['id'], start))}
            steps.append({'key': 'read2', 'title': '再读一篇', 'sub': other['title'], 'href': f"#/m/{other['id']}", 'done': 'check' in st2 or 'output' in st2})
    # With goals set, the output step works on the skill furthest from its goal on the radar; otherwise the weakest estimate.
    weakest = __import__('ability_radar').weakest(c, uid, now) or ability(c, uid, now)['weakest']
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
    kinds = {'retell': {'retell'}, 'essay': {'essay'}, 'translate': {'translate'}, 'dictate': {'dictation'}, 'sounds': {'say', 'discriminate'}}
    steps.append({'key': key, 'title': title, 'sub': sub, 'href': href, 'done': bool(kinds.get(key, set()) & today_kinds)})
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
            steps.append({'key': 'grammar', 'title': '语法复习', 'href': '#/mix',
                          'sub': f'今天做了 {practised} 题' + (f' · 还有 {left} 个点明天接着练' if left else ' · 都练到了'), 'done': True})
        else:
            names = '、'.join(titles.get(n, {}).get('title', n) for n in nodes[:2]) + (f' 等 {len(nodes)} 个点' if len(nodes) > 2 else '')
            steps.append({'key': 'grammar', 'title': '语法混合复习：' + names, 'href': '#/mix',
                          'sub': f'{size} 道题混着做，约 {max(2, size // 2)} 分钟', 'done': False})
    if prof.get('goal') == 'exam' and minutes >= 10:
        # One practice set a week: shown when the last one is a week old (or none yet), ticked on the day it is done.
        last = c.execute('SELECT MAX(created) t FROM next_exam_results WHERE user_id=?', (uid,)).fetchone()['t']
        if last and last >= start:
            steps.append({'key': 'exam', 'title': '考试练习', 'sub': '这周的一套做完了', 'href': '#/exam', 'done': True})
        elif not last or last < now - 6 * 86400:
            steps.append({'key': 'exam', 'title': '考试练习', 'sub': '每周一套：词汇、语法、阅读，约 15–20 分钟', 'href': '#/exam', 'done': False})
    stale = __import__('ability_radar').due_today(c, uid, now)
    last_test = c.execute('SELECT MAX(created) FROM next_assess WHERE user_id=?', (uid,)).fetchone()[0]
    if stale and not (last_test and start - 2 * 86400 <= last_test < start):  # a test every few days, not every day
        tested = c.execute('SELECT COUNT(*) FROM next_assess WHERE user_id=? AND created>=?', (uid, start)).fetchone()[0]
        names = '、'.join(dict(__import__('ability_radar').DIMS)[k] for k in stale[:3])
        steps.append({'key': 'assess', 'title': '能力测评', 'href': '#/radar/test', 'done': bool(tested),
                      'sub': '今天测过了，雷达图已更新' if tested else f'{names}{"等" if len(stale) > 3 else ""}该测一测了，选一项就行，约 5 分钟'})
    if minutes >= 30:
        # Easy reading: a lot of easy text builds fluency; one short text a day on longer days.
        n_easy = __import__('easy_reading').read_today(c, uid, start)
        steps.append({'key': 'easy', 'title': '轻松读一篇', 'href': '#/easy', 'done': bool(n_easy),
                      'sub': f'今天读了 {n_easy} 篇' if n_easy else '比你的水平低一点，只读不做题，约 3 分钟'})
    if key != 'retell' and (minutes >= 30 or (prof.get('goal') in ('abroad', 'daily', 'work') and minutes >= 20)):
        # The speaking route: one role-play scene, unless today's output step is already spoken.
        sp = __import__('scenarios').listing(c, uid, level)
        spoke = c.execute("SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND skill='speaking' AND created>=?", (uid, start)).fetchone()[0]
        if sp['next'] or spoke:
            nxt = next((x for x in sp['items'] if x['id'] == sp['next']), None)
            steps.append({'key': 'speak', 'title': '口语：' + (nxt['title'] if nxt and not spoke else '情景对话'), 'done': bool(spoke),
                          'href': '#/speak/' + nxt['id'] if nxt else '#/speak',
                          'sub': '今天说过了' if spoke else '和 AI 演一个情景，说四五句，约 5 分钟'})
    if minutes >= 15 and key != 'dictate' and pick:
        steps.append({'key': 'dictate', 'title': '听写三句', 'sub': f"练耳朵，也练拼写 · 今天 {min(3, kind_n.get('dictation', 0))}/3", 'href': f"#/m/{pick['id']}/listen",
                      'done': kind_n.get('dictation', 0) >= 3})
    return {'minutes': minutes, 'steps': steps, 'done': sum(1 for s in steps if s['done']), 'total': len(steps)}


# ---------- weekly report ----------

def report(c, uid, now=None):
    now = now or time.time()
    week = now - 7 * 86400
    prev = now - 14 * 86400
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    days = set()
    for (t,) in c.execute('SELECT created FROM next_progress WHERE user_id=? AND created>? UNION ALL SELECT created FROM next_reviews WHERE user_id=? AND created>? '
                          'UNION ALL SELECT created FROM next_skill_events WHERE user_id=? AND created>?', (uid, week, uid, week, uid, week)):
        days.add(nx._day(t))
    evts = _events(c, uid, prev)
    def avg(sk, lo, hi):
        s = [e['score'] for e in evts if e['skill'] == sk and lo < e['created'] <= hi]
        return round(sum(s) / len(s), 2) if s else None
    skills = [{'id': sk, 'label': SKILLS[sk], 'now': avg(sk, week, now), 'before': avg(sk, prev, week),
               'count': sum(1 for e in evts if e['skill'] == sk and e['created'] > week)} for sk in EVENT_SKILLS]
    reviews = q("SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND created>? AND rating IN ('again','hard','good','easy')", uid, week)
    learned = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND kind='word' AND created>?", uid, week)
    mastered = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND kind='word' AND stability>=21 AND last>?", uid, week)
    fixed = q("SELECT COUNT(DISTINCT r.card) FROM next_reviews r JOIN next_cards k ON k.id=r.card WHERE r.user_id=? AND r.created>? AND k.source='mistake' AND r.rating IN ('good','easy')", uid, week)
    new_mistakes = q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND source='mistake' AND created>?", uid, week)
    materials = q("SELECT COUNT(DISTINCT pack) FROM next_progress WHERE user_id=? AND step='check' AND created>?", uid, week)
    outputs = q("SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND created>? AND kind IN ('rewrite','retell','dialog','essay','translate')", uid, week)
    minutes = round(reviews * 0.15 + materials * 9 + outputs * 4 + q('SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND created>?', uid, week) * 0.5)
    meta = nx.nodes_meta(c)
    watch = [{'id': n, 'title': meta.get(n, {}).get('title', n)} for n, s in nx.graph_states(c, uid).items() if s['status'] == 'watch'][:3]
    ab = ability(c, uid, now)
    focus = None
    if ab['weakest']:
        name = SKILLS[ab['weakest']]
        what = {'speaking': '每天复述一篇或和 AI 对话一轮', 'writing': '写一段短文让 AI 批改', 'listening': '每天听写三句', 'reading': '先读懂再做理解题'}
        focus = f"{name}是现在最弱的一项，下周{what.get(ab['weakest'], '多练这一项')}。"
    elif not days:
        focus = '这周还没开始：每天 10 分钟，先从今天这篇开始。'
    return {'from': nx._day(now - 6 * 86400), 'to': nx._day(now), 'days': len(days), 'minutes': minutes, 'materials': materials, 'outputs': outputs,
            'reviews': reviews, 'learned': learned, 'mastered': mastered, 'mistakes_new': new_mistakes, 'mistakes_fixed': fixed,
            'skills': skills, 'watch': watch, 'focus': focus, 'ability': ab['skills'], **_week_more(c, uid, now, week, prev)}


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
    """Sunday, at the learner's reminder hour: the weekly report by email (learners who turned reminders on)."""
    import os
    now = now or time.time()
    local = datetime.datetime.fromtimestamp(now, nx.TZ)
    if local.weekday() != 6 or 'email' not in {x[1] for x in c.execute('PRAGMA table_info(users)')}:
        return 0
    if send is None:
        from account_service import mail as send
    today = local.date().isoformat()
    origin = os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').rstrip('/')
    sent = 0
    rows = c.execute("SELECT r.user_id, u.email, u.username FROM next_reminders r JOIN users u ON u.id=r.user_id LEFT JOIN next_weekly w ON w.user_id=r.user_id "
                     "WHERE r.enabled=1 AND r.hour=? AND u.email IS NOT NULL AND u.email!='' AND (w.last_sent IS NULL OR w.last_sent<?)",
                     (local.hour, today)).fetchall()
    for r in rows:
        c.execute('INSERT INTO next_weekly(user_id,last_sent) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_sent=excluded.last_sent', (r['user_id'], today))
        c.commit()
        rp = report(c, r['user_id'], now)
        if not rp['days']:
            continue
        lines = [f"{r['username']}，这是你这周（{rp['from']} – {rp['to']}）的学习小结：", '',
                 f"· 学了 {rp['days']} 天，约 {rp['minutes']} 分钟", f"· 学完 {rp['materials']} 篇材料，做了 {rp['outputs']} 次输出练习",
                 f"· 复习 {rp['reviews']} 次，新学 {rp['learned']} 个词，{rp['mastered']} 个词进入长期记忆",
                 f"· 新错题 {rp['mistakes_new']} 个，改对 {rp['mistakes_fixed']} 个"]
        if rp['easy']['texts']:
            lines.append(f"· 轻松读 {rp['easy']['texts']} 篇，共 {rp['easy']['words']} 个词" + (f"，每分钟 {rp['easy']['wpm']} 词" if rp['easy']['wpm'] else ''))
        if rp['speaking']['scenes_week']:
            lines.append(f"· 口语情景练了 {rp['speaking']['scenes_week']} 个（一共完成 {rp['speaking']['scenes_done']} / {rp['speaking']['scenes_total']}）")
        up = [m for m in rp['radar']['moves'] if m['before'] is not None and m['now'] > m['before']]
        if up:
            lines.append('· 能力雷达上涨：' + '、'.join(f"{m['label']} {m['before']}→{m['now']}" for m in up))
        if rp['focus']:
            lines += ['', '下周重点：' + rp['focus']]
        lines += ['', f'完整周报：{origin}/#/report', '—— 语流 Flow']
        try:
            send(r['email'], f"语流 · 你这周学了 {rp['days']} 天", '\n'.join(lines))
            sent += 1
        except Exception:
            pass
    return sent


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
