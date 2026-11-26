"""看得见的进步，有人督促 (r27, direction B).

- 这周进步 at the top of 今日: words remembered for the first time, texts finished, the share of questions answered
  right against last week, and the weekly goal (每周目标). Weeks run Monday to Sunday in China time, as 每周目标 does.
- 学完一篇的小结: what this text gave the learner (expressions and words saved from it) and one grammar point to work on.
- Weeks at the weekly goal are counted up, in total: a missed day or a missed week never takes one away. A new goal
  counts from its own week on; the weeks before keep the goal they had (next_goal_weeks).
- 每周进度邮件: on Sunday from 20:00 China time, to learners with a bound email who studied in the last few weeks,
  with a link to stop it (and List-Unsubscribe for mail apps). Learners can also turn it off in 我的.

Every number comes from the learner's own records. Where there is too little to say anything (a few questions only),
it says how many there were instead of a percentage.
"""
import datetime, json, os, re, secrets, time, uuid
from collections import Counter

import next_service as nx

D = datetime.timedelta
EPOCH = datetime.date(1970, 1, 1)
CN = 8 * 3600  # China time, as next_service.TZ (no summer time)
PASS = ('hard', 'good', 'easy', 'used')  # a review that recalled the word (used: written correctly in 用出来)
MIN_ANSWERS = 5  # fewer answers in a week than this: no percentage, only how many
MAIL_HOUR = 20  # Sunday evening
# The mail's links say they come from a reminder (B1's count of who comes back with or without one: per day and kind,
# never who; the page drops the query once read): ?from=remind&k=weekly, before the #.
FROM_MAIL = '?from=remind&k=weekly'
NUDGE_WEEKS = 3  # a week without study still gets the mail for this many weeks after the last study day, then it stops
WEEKDAY = '一二三四五六日'


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS next_goal_weeks(user_id INTEGER NOT NULL REFERENCES users(id), monday TEXT NOT NULL, '
              'goal INTEGER NOT NULL, PRIMARY KEY(user_id, monday))')
    cols = {r[1] for r in c.execute('PRAGMA table_info(next_weekly)')}  # skills_service: the Sunday mail's last day
    for name, decl in (('off', 'INTEGER NOT NULL DEFAULT 0'), ('token', 'TEXT'), ('mailed', 'TEXT')):
        if name not in cols:
            c.execute(f'ALTER TABLE next_weekly ADD COLUMN {name} {decl}')
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS next_weekly_token ON next_weekly(token) WHERE token IS NOT NULL')
    # every day a step of a material was done, a second time included (next_progress keeps only the first time, which
    # 复听 and 这周进步 read as "first studied"): so redoing a text the plan offers still ticks it
    c.execute('CREATE TABLE IF NOT EXISTS next_step_log(user_id INTEGER NOT NULL REFERENCES users(id), pack TEXT NOT NULL, step TEXT NOT NULL, '
              'day TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(user_id, pack, step, day))')
    c.execute('CREATE INDEX IF NOT EXISTS next_step_log_time ON next_step_log(user_id, created)')
    # 周报「这周的一次进步」(r29): a sentence the learner wrote later that uses a form AI once corrected for them (card:
    # the fix card), right and not corrected this time. Written only: spoken words are never kept. At most EVIDENCE_KEEP
    # a grammar point, EVIDENCE_DAYS at most; only the learner sees them.
    c.execute('CREATE TABLE IF NOT EXISTS next_evidence(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), node TEXT NOT NULL, '
              'card INTEGER NOT NULL, kind TEXT NOT NULL, sentence TEXT NOT NULL, source TEXT NOT NULL, assisted INTEGER, created REAL NOT NULL, '
              'UNIQUE(user_id, card, source))')
    c.execute('CREATE INDEX IF NOT EXISTS next_evidence_user ON next_evidence(user_id, node, created)')


# ---------- days and weeks ----------

def _local(now):
    return datetime.datetime.fromtimestamp(now, nx.TZ)


def _start(day):
    return datetime.datetime.combine(day, datetime.time(), nx.TZ).timestamp()


def _bounds(now):
    """(today, this Monday, the time this week began, the time last week began)."""
    today = _local(now).date()
    monday = today - D(days=today.weekday())
    return today, monday, _start(monday), _start(monday - D(weeks=1))


# What makes a study day, for 每周目标 and for 我的进步's 学习天数 alike: anything learned. A step of a material (the
# first time or again), a review, a relisten, easy reading, a scored practice (dictation, speaking, writing ...) or an answered question.
DAY_TABLES = ('next_progress', 'next_step_log', 'next_reviews', 'next_relisten', 'next_easy_reads', 'next_skill_events', 'learning_events')


def study_days(c, uid, since=0, until=None):
    """China-time dates in [since, until) on which the learner studied anything (DAY_TABLES)."""
    out = set()
    for t in DAY_TABLES:
        sql = f'SELECT DISTINCT CAST((created+{CN})/86400 AS INTEGER) FROM {t} WHERE user_id=? AND created>=?' + (' AND created<?' if until else '')
        for (d,) in c.execute(sql, (uid, since, until) if until else (uid, since)):
            out.add(EPOCH + D(days=d))
    return out


def _history(c, uid):
    return c.execute('SELECT monday, goal FROM next_goal_weeks WHERE user_id=? ORDER BY monday', (uid,)).fetchall()


def _goal_for(history, monday, current):
    goal = None
    for m, g in history:
        if m > monday:
            break
        goal = g
    return current if goal is None else goal


def goal_changed(c, uid, old, new, now=None):
    """A new weekly goal counts from this week on; the weeks before keep the goal they had (the first change also
    writes down the old one, for every week before it). The caller commits."""
    monday = _bounds(now or time.time())[1].isoformat()
    if old and not c.execute('SELECT 1 FROM next_goal_weeks WHERE user_id=?', (uid,)).fetchone():
        c.execute('INSERT INTO next_goal_weeks VALUES(?,?,?)', (uid, '0000-00-00', old))
    c.execute('INSERT INTO next_goal_weeks VALUES(?,?,?) ON CONFLICT(user_id, monday) DO UPDATE SET goal=excluded.goal', (uid, monday, new))


def weeks_reached(c, uid, goal, days, monday):
    """Weeks (Monday to Sunday) that reached the weekly goal, this one included once it does. Only counts up."""
    history, per = _history(c, uid), Counter(d - D(days=d.weekday()) for d in days)
    return sum(1 for mon, n in per.items() if mon <= monday and n >= (goal if mon == monday else _goal_for(history, mon.isoformat(), goal)))


# ---------- 这周的一次进步 (r29): written evidence and points that keep coming back ----------

EVIDENCE_KEEP, EVIDENCE_DAYS = 2, 90
# 反复出现 (the user's rule, 2026-11-26, with B7): the same grammar point corrected in at least RECUR_OUTPUTS different
# outputs on at least RECUR_DAYS days within RECUR_WINDOW days. Once or twice is pointed out there and then, and stops.
RECUR_WINDOW, RECUR_DAYS, RECUR_OUTPUTS = 14, 2, 3


def note_evidence(c, uid, text, changes, kind, request_id='', assisted=None, now=None):
    """After a written output is marked: for each fix card on a grammar point whose corrected form (to) the learner now
    wrote, and that point not corrected this time, keep that sentence (next_evidence). Forms too short to mean anything
    (a, the, in…) are left out. Returns how many were kept. The caller commits."""
    if not uid or not (text or '').strip():
        return 0
    now = now or time.time()
    fixed = {ch.get('node') for ch in (changes or []) if ch.get('node')}
    source, low, kept = 'ev:' + (str(request_id or '') or uuid.uuid4().hex), text.lower(), 0
    for r in c.execute("SELECT id, text, node FROM next_cards WHERE user_id=? AND kind='fix' AND source='mistake' AND node IS NOT NULL AND created<?",
                       (uid, now)).fetchall():
        to = (r['text'] or '').strip()
        if r['node'] in fixed or not to or len(to) > 60 or (len(to) < 4 and ' ' not in to):
            continue
        if not re.search(r'(?<![a-z])' + re.escape(to.lower()) + r'(?![a-z])', low):
            continue
        sent = next((s for s in nx.sentences(text) if to.lower() in s.lower()), '')[:300]
        if not sent:
            continue
        c.execute('INSERT OR IGNORE INTO next_evidence(user_id,node,card,kind,sentence,source,assisted,created) VALUES(?,?,?,?,?,?,?,?)',
                  (uid, r['node'], r['id'], kind, sent, source, None if assisted is None else int(bool(assisted)), now))
        c.execute('DELETE FROM next_evidence WHERE user_id=? AND node=? AND id NOT IN '
                  '(SELECT id FROM next_evidence WHERE user_id=? AND node=? ORDER BY created DESC, id DESC LIMIT ?)', (uid, r['node'], uid, r['node'], EVIDENCE_KEEP))
        kept += 1
    c.execute('DELETE FROM next_evidence WHERE user_id=? AND created<?', (uid, now - EVIDENCE_DAYS * 86400))
    return kept


def recurring(c, uid, now=None):
    """Grammar points that keep coming back (RECUR_*), most outputs first: [{node, outputs, days, last}]. A point the
    learner has since answered right without help in a rule-marked question no longer counts (B7)."""
    now = now or time.time()
    by = {}
    for r in c.execute('SELECT node, source, created FROM next_corrections WHERE user_id=? AND created>=?', (uid, now - RECUR_WINDOW * 86400)):
        d = by.setdefault(r['node'], {'outputs': set(), 'days': set(), 'last': 0})
        d['outputs'].add(r['source']); d['days'].add(_local(r['created']).date()); d['last'] = max(d['last'], r['created'])
    out = []
    for node, d in by.items():
        if len(d['outputs']) < RECUR_OUTPUTS or len(d['days']) < RECUR_DAYS:
            continue
        if c.execute("SELECT 1 FROM learning_events WHERE user_id=? AND node=? AND evaluator='rule' AND correct=1 AND assisted=0 AND created>? LIMIT 1",
                     (uid, node, d['last'])).fetchone():
            continue
        out.append({'node': node, 'outputs': len(d['outputs']), 'days': len(d['days']), 'last': d['last']})
    return sorted(out, key=lambda x: (-x['outputs'], -x['last']))


def pairs(c, uid, now=None, days=7):
    """「之前 / 这周」 for the weekly report, newest first, one a grammar point: before = the fix card (the learner's own
    sentence, from → to, when, which practice); after = the sentence they wrote right later (when, which practice,
    assisted: 1 with help, 0 without, None not known)."""
    now = now or time.time()
    out, seen = [], set()
    for e in c.execute('SELECT e.node, e.kind, e.sentence, e.assisted, e.created, k.text AS fix_to, k.context, k.extra, k.created AS before_at, k.skill '
                       'FROM next_evidence e JOIN next_cards k ON k.id=e.card AND k.user_id=e.user_id WHERE e.user_id=? AND e.created>=? '
                       'ORDER BY e.created DESC, e.id DESC', (uid, now - days * 86400)):
        if e['node'] in seen:
            continue
        seen.add(e['node'])
        extra = json.loads(e['extra'] or '{}')
        out.append({'node': e['node'],
                    'before': {'sentence': e['context'], 'from': extra.get('from', ''), 'to': e['fix_to'], 'at': e['before_at'], 'kind': extra.get('kind') or e['skill'] or ''},
                    'after': {'sentence': e['sentence'], 'at': e['created'], 'kind': e['kind'], 'assisted': e['assisted']}})
    return out


# ---------- this week ----------

def _remembered(c, uid, since):
    """(card id, word, when) for words remembered for the first time since `since`: a word card (not one marked as
    already known) recalled in a review on a later day than the one it was added on. Each word counts once."""
    later = f'CAST((r.created+{CN})/86400 AS INTEGER) > CAST((k.created+{CN})/86400 AS INTEGER)'
    return c.execute(f"""SELECT k.id, k.text, MIN(r.created) t FROM next_cards k JOIN next_reviews r ON r.card=k.id AND r.user_id=k.user_id
        WHERE k.user_id=? AND k.kind='word' AND k.known=0 AND r.rating IN ({','.join('?' * len(PASS))}) AND {later}
        GROUP BY k.id HAVING t>=? ORDER BY t""", (uid, *PASS, since)).fetchall()


def _answers(c, uid, lo, hi):
    """Questions answered without a hint in [lo, hi): comprehension, grammar points, mixed rounds, exam practice.
    The placement test is left out (it climbs until the learner misses, so about half is wrong by design)."""
    right, total = c.execute("SELECT COALESCE(SUM(correct),0), COUNT(*) FROM learning_events WHERE user_id=? AND correct IS NOT NULL "
                             "AND evaluator='rule' AND assisted=0 AND COALESCE(context,'')!='placement' AND COALESCE(source,'') NOT LIKE 'placement:%' "
                             'AND created>=? AND created<?', (uid, lo, hi)).fetchone()
    return {'right': right, 'total': total, 'rate': round(right / total * 100) if total >= MIN_ANSWERS else None}


# 今天学了几分钟 (r28 按时间打包今日计划): from the learner's own records, never a timer. Records less than ACTIVE_GAP
# apart are one sitting and the time between them counts; a sitting's first record counts a minute before it (the
# answer or step it records took that long at least); an exam set counts its own seconds.
ACTIVE_GAP = 600


def active_minutes(c, uid, since, until=None):
    """Minutes studied in [since, until)."""
    until = until or time.time() + 1
    spans = []
    for t in DAY_TABLES + ('next_assess',):
        try:
            spans += [(r[0] - 60, r[0]) for r in c.execute(f'SELECT created FROM {t} WHERE user_id=? AND created>=? AND created<?', (uid, since, until))]
        except Exception:  # a table a fresh database has not made yet
            pass
    try:
        spans += [(r[0] - min(r[1], 3 * 3600), r[0]) for r in
                  c.execute('SELECT created, seconds FROM next_exam_results WHERE user_id=? AND created>=? AND created<?', (uid, since, until))]
    except Exception:
        pass
    total, cur = 0, None
    for a, z in sorted(spans):
        a = max(a, since)
        if cur and a <= cur[1] + ACTIVE_GAP:
            cur[1] = max(cur[1], z)
        else:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, z]
    if cur:
        total += cur[1] - cur[0]
    return round(total / 60)


def log_step(c, uid, pid, step, now=None):
    """A step of a material done today (next_service.mark): kept once a day, the first time and every time after."""
    now = now or time.time()
    c.execute('INSERT OR IGNORE INTO next_step_log VALUES(?,?,?,?,?)', (uid, pid, step, _local(now).date().isoformat(), now))


def steps_since(c, uid, since, until=None, pack=None):
    """(pack, step, time) of every step done in [since, until): the first time (next_progress) or again (next_step_log)."""
    until = until or time.time() + 1
    extra, args = (' AND pack=?', (pack,)) if pack else ('', ())
    rows = c.execute('SELECT pack, step, created FROM next_progress WHERE user_id=? AND created>=? AND created<?' + extra + ' UNION '
                     'SELECT pack, step, created FROM next_step_log WHERE user_id=? AND created>=? AND created<?' + extra + ' ORDER BY created',
                     (uid, since, until, *args, uid, since, until, *args)).fetchall()
    return rows


def _finished(c, uid, lo, hi, steps=('check',)):
    """Texts finished in [lo, hi): materials whose comprehension questions were done then, the first time or again
    (学完的文章 here, 学完的材料 in the weekly report and 我的进步). Ordered by when."""
    return list(dict.fromkeys(r['pack'] for r in steps_since(c, uid, lo, hi) if r['step'] in steps))


def new_words(c, uid, lo, hi):
    """新学的词 in [lo, hi): word cards answered for the first time then (a review's first rating), not cards merely put
    into the queue (今日 brings in the day's new words when it opens) nor words marked as already known."""
    return c.execute("""SELECT COUNT(*) FROM (SELECT MIN(r.created) t FROM next_reviews r JOIN next_cards k ON k.id=r.card AND k.user_id=r.user_id
        WHERE r.user_id=? AND k.kind='word' AND k.known=0 AND r.rating IN ('again','hard','good','easy') GROUP BY r.card) WHERE t>=? AND t<?""",
                     (uid, lo, hi)).fetchone()[0]


def _titles(c, uid, packs):
    out = []
    for pid in packs:
        row = nx._pack_row(c, uid, pid)
        if row:
            p = json.loads(row['content'])
            out.append({'id': pid, 'title': p.get('title') or pid})
    return out


def mail_state(c, uid):
    has = 'email' in {x[1] for x in c.execute('PRAGMA table_info(users)')}
    row = c.execute('SELECT email FROM users WHERE id=?', (uid,)).fetchone() if has else None
    off = c.execute('SELECT off FROM next_weekly WHERE user_id=?', (uid,)).fetchone()
    return {'on': not (off and off[0]), 'email': bool(row and row['email']), 'hour': MAIL_HOUR}


def week(c, uid, now=None, detail=False):
    """这周进步: this week so far against the whole of last week. With detail, the words and titles behind the numbers."""
    now = now or time.time()
    today, monday, lo, prev = _bounds(now)
    words = _remembered(c, uid, prev)
    mine = [w for w in words if w['t'] >= lo]
    done, before = _finished(c, uid, lo, now + 1), _finished(c, uid, prev, lo)
    out = {'monday': monday.isoformat(), 'from': monday.isoformat(), 'to': (monday + D(days=6)).isoformat(),
           'remembered': {'now': len(mine), 'before': len(words) - len(mine)},
           'finished': {'now': len(set(done)), 'before': len(set(before))},
           'accuracy': {'now': _answers(c, uid, lo, now + 1), 'before': _answers(c, uid, prev, lo), 'min': MIN_ANSWERS},
           'mail': mail_state(c, uid)}
    if detail:
        out['remembered']['words'] = [w['text'] for w in reversed(mine)][:40]
        out['finished']['titles'] = _titles(c, uid, list(dict.fromkeys(reversed(done))))[:12]
        out['easy'] = c.execute('SELECT COUNT(*), COALESCE(SUM(words),0) FROM next_easy_reads WHERE user_id=? AND created>=?', (uid, lo)).fetchone()[:]
        prof = nx.profile(c, uid) or {}
        out['habit'] = nx.habit(c, uid, prof.get('weekly_goal') or 4, now)
    return out


# ---------- after a text ----------

def text_summary(c, uid, pid):
    """学完一篇的小结: the expressions and words saved from this text, and one grammar point to work on next."""
    row = nx._pack_row(c, uid, pid)
    if not row:
        return {'error': '材料不存在'}, 404
    p = json.loads(row['content'])
    cards = c.execute("SELECT text, meaning, kind FROM next_cards WHERE user_id=? AND pack=? AND source='saved' ORDER BY created", (uid, pid)).fetchall()
    saved = [{'text': r['text'], 'meaning': r['meaning']} for r in cards if r['kind'] != 'word']
    words = [{'text': r['text'], 'meaning': r['meaning']} for r in cards if r['kind'] == 'word']
    key = [x.get('text') for x in p.get('expressions', []) if x.get('text')][:3]
    mine = []
    if not words:  # nothing saved: the words of the learner's own word book this text went over
        mine = list(dict.fromkeys(x['form'] for x in __import__('vocab_service').mine_in_text(c, uid, p.get('body', ''))))[:5]
    return {'pack': pid, 'expressions': {'saved': saved[:8], 'count': len(saved), 'key': key},
            'words': {'saved': words[:8], 'count': len(words), 'mine': mine},
            'grammar': grammar_next(c, uid, p)}, 200


def grammar_next(c, uid, p):
    """One grammar point to work on after this text, the most pressing first: one the AI corrected in what the
    learner wrote for it; one of its points that needs attention; one of its points not yet checked with questions.
    None when it has no points; {'all_solid': True} when all of them have been checked."""
    meta = nx.nodes_meta(c)
    fix = c.execute("SELECT node, detail FROM next_node_notes WHERE user_id=? AND pack=? AND kind='flag' ORDER BY created DESC LIMIT 1", (uid, p['id'])).fetchone()
    if fix and fix['node'] in meta:
        n = c.execute("SELECT COUNT(*) FROM next_node_notes WHERE user_id=? AND pack=? AND kind='flag' AND node=?", (uid, p['id'], fix['node'])).fetchone()[0]
        return {'id': fix['node'], 'title': meta[fix['node']]['title'], 'why': 'flag', 'times': n, 'change': fix['detail'].split('|', 1)[-1]}
    fix = c.execute("SELECT node, extra, text FROM next_cards WHERE user_id=? AND pack=? AND source='mistake' AND kind='fix' AND node IS NOT NULL "
                    'ORDER BY created DESC LIMIT 1', (uid, p['id'])).fetchone()
    if fix and fix['node'] in meta:
        frm = (json.loads(fix['extra'] or '{}') or {}).get('from', '')
        return {'id': fix['node'], 'title': meta[fix['node']]['title'], 'why': 'flag', 'times': 1, 'change': f"{frm} → {fix['text']}" if frm else ''}
    points = [n for n in nx.pack_grammar(p) if n in meta]
    if not points:
        return None
    states = nx.graph_states(c, uid)
    for status, why in (('watch', 'watch'), ('used', 'check'), ('met', 'check'), ('untouched', 'check')):
        hit = next((n for n in points if states[n]['status'] == status), None)
        if hit:
            return {'id': hit, 'title': meta[hit]['title'], 'why': why}
    return {'all_solid': True, 'count': len(points)}


# ---------- the Sunday mail ----------

def _token(c, uid):
    row = c.execute('SELECT token FROM next_weekly WHERE user_id=?', (uid,)).fetchone()
    if row and row[0]:
        return row[0]
    token = secrets.token_urlsafe(24)
    c.execute('INSERT INTO next_weekly(user_id, token) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET token=excluded.token', (uid, token))
    return token


def set_mail(c, uid, data):
    if type(data.get('on')) is not bool:
        return {'error': '设置不正确'}, 400
    c.execute('INSERT INTO next_weekly(user_id, off) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET off=excluded.off', (uid, int(not data['on'])))
    c.commit()
    return mail_state(c, uid), 200


def unsubscribe(c, token, on=False):
    """The link in the mail (no sign-in): the token stands for the account. on=True takes it back."""
    if not isinstance(token, str) or not 20 <= len(token) <= 64:
        return {'error': '这个退订链接不完整，请从邮件里重新打开'}, 400
    row = c.execute('SELECT user_id FROM next_weekly WHERE token=?', (token,)).fetchone()
    if not row:
        return {'error': '这个退订链接已经失效（账号可能已经注销）'}, 404
    c.execute('UPDATE next_weekly SET off=? WHERE user_id=?', (int(not on), row[0]))
    c.commit()
    return {'ok': True, 'on': bool(on)}, 200


def _date(d):
    return f'{d.month} 月 {d.day} 日'


def compose(c, uid, name, now, origin):
    """(subject, text, html, unsubscribe token) of the Sunday mail in the one look of 语流's mails (mail_layout, the
    owner's 「A 简洁卡片」): a greeting, then one row per fact (heading, detail), a button back to 语流, and the link to
    stop the mail in the footer. None when there is nothing to send (no study for a while)."""
    import mail_layout
    today, monday, lo, prev = _bounds(now)
    days = study_days(c, uid, _start(monday - D(weeks=NUDGE_WEEKS)))
    if not days:
        return None
    prof = nx.profile(c, uid) or {}
    hb = nx.habit(c, uid, prof.get('weekly_goal') or 4, now)
    w = week(c, uid, now, detail=True)
    import vocab_service as vs
    due = vs.counts(c, uid, now)['due']
    span = f'{_date(monday)} – {_date(monday + D(days=6))}'
    words_due = ('单词复习', f'现在有 {due} 个单词到了复习时间，复习一轮大约 {max(1, round(due * 0.15))} 分钟。') if due else None
    rows = []
    if not hb['done']:
        last = max(days)
        subject = '语流 · 这周还没学，下周一起开个头'
        paragraphs = [f'{name}，你好：', f'这周（{span}）你还没有打开语流学习。上次学习是 {_date(last)}（周{WEEKDAY[last.weekday()]}）。',
                      f"你的每周目标是 {hb['goal']} 天。没学的周不会把以前的记录清零" + (f"，你已经有 {hb['weeks']} 周达成了目标。" if hb['weeks'] else '。'),
                      '下周从周一开始：学一步材料或复习几个词，就算学了一天。']
    else:
        rem, fin, acc = w['remembered'], w['finished'], w['accuracy']
        if hb['met']:
            subject = f"语流 · 这周目标达成，一共 {hb['weeks']} 周了" if hb['weeks'] > 1 else '语流 · 这周目标达成了'
        elif rem['now'] or fin['now']:
            subject = '语流 · 这周进步：' + '，'.join(x for x in (f"记住 {rem['now']} 个新词" if rem['now'] else '', f"学完 {fin['now']} 篇" if fin['now'] else '') if x)
        else:
            subject = f"语流 · 你这周学了 {hb['done']} 天"
        paragraphs = [f'{name}，你好：', f'这是你这周（{span}）的进步，数字都来自你自己的学习记录。']
        rows.append(('每周目标', f"学了 {hb['done']} 天，目标 {hb['goal']} 天，达成了！一共达成 {hb['weeks']} 周。" if hb['met'] else
                     f"学了 {hb['done']} 天，目标 {hb['goal']} 天，这周差 {hb['goal'] - hb['done']} 天。" + (f"已经达成过 {hb['weeks']} 周，不会因为这周清零。" if hb['weeks'] else '')))
        if rem['now']:
            shown = '、'.join(rem['words'][:8]) + ('等' if rem['now'] > 8 else '')
            rows.append((f"记住了 {rem['now']} 个新词", f'隔天复习还记得的：{shown}。' + (f"上周 {rem['before']} 个。" if rem['before'] else '')))
        elif rem['before']:
            rows.append(('记住的新词', f"这周还没有（上周 {rem['before']} 个）。新词要隔天复习还记得才算。"))
        if fin['now']:
            rows.append((f"学完 {fin['now']} 篇", '、'.join(f"《{t['title']}》" for t in fin['titles'][:4]) + (f"。上周 {fin['before']} 篇。" if fin['before'] else '')))
        a, b = acc['now'], acc['before']
        if a['rate'] is not None:
            rows.append((f"做题正确率 {a['rate']}%", f"{a['total']} 题对 {a['right']} 题" + (f"，上周 {b['rate']}%。" if b['rate'] is not None else '。')))
        elif a['total']:
            rows.append((f"做了 {a['total']} 题", f"对了 {a['right']} 题，满 {MIN_ANSWERS} 题才算正确率。"))
        import skills_service as sk
        more = sk._week_more(c, uid, now, lo, prev)
        e, sp = more['easy'], more['speaking']
        if e['texts']:
            rows.append(('轻松读', f"{e['texts']} 篇，共 {e['words']} 个词" + (f"，每分钟 {e['wpm']} 词。" if e['wpm'] else '。')))
        if sp['scenes_week']:
            rows.append(('口语情景', f"练了 {sp['scenes_week']} 个，一共完成 {sp['scenes_done']} / {sp['scenes_total']}。"))
        up = [m for m in more['radar']['moves'] if m['before'] is not None and m['now'] > m['before']]
        if up:
            rows.append(('能力雷达上涨', '、'.join(f"{m['label']} {m['before']}→{m['now']}" for m in up) + '。'))
    if words_due:
        rows.append(words_due)
    token = _token(c, uid)
    text, page = mail_layout.message(paragraphs, rows=rows, button=('打开语流接着学', f'{origin}/{FROM_MAIL}#/'),
                                     foot=[('这周的完整报告', f'{origin}/{FROM_MAIL}#/report'), ('不想再收到每周进度邮件，点这里退订', f'{origin}/#/weekly-off/{token}'),
                                           ('也可以在「我的 → 每周进度邮件」里关掉。', None)])
    return subject, text, page, token


def send_weekly(c, now=None, send=None):
    """Sunday from 20:00 China time: the week's progress to every learner with a bound email who has not turned it
    off and studied in the last few weeks (this week, or a nudge after a week without). Once per Sunday."""
    now = now or time.time()
    local = _local(now)
    cols = {x[1] for x in c.execute('PRAGMA table_info(users)')}
    if local.weekday() != 6 or local.hour < MAIL_HOUR or 'email' not in cols:
        return 0
    import account_service as account
    if send is None and not account.configured():
        return 0
    today, origin, sent = local.date().isoformat(), os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').rstrip('/'), 0
    rows = c.execute("SELECT u.id, u.email, u.username FROM users u LEFT JOIN next_weekly w ON w.user_id=u.id WHERE u.email IS NOT NULL AND u.email!='' "
                     "AND COALESCE(w.off,0)=0 AND (w.last_sent IS NULL OR w.last_sent<?)" + (' AND COALESCE(u.disabled,0)=0' if 'disabled' in cols else '')
                     + (' AND u.storage_no IS NULL' if 'storage_no' in cols else ''),  # a paused account (privacy_service) gets no mail
                     (today,)).fetchall()
    for r in rows:
        c.execute('INSERT INTO next_weekly(user_id,last_sent) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_sent=excluded.last_sent', (r['id'], today))
        c.commit()
        mail = compose(c, r['id'], r['username'], now, origin)
        if not mail:
            continue
        subject, text, page, token = mail
        try:
            if send is None:
                link = f'{origin}/api/next/weekly-mail/off?t={token}'
                account.mail(r['email'], subject, text, headers={'List-Unsubscribe': f'<{link}>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}, html=page)
            else:
                send(r['email'], subject, text)
            sent += 1
        except Exception:
            continue  # a mail outage must not stop the loop
        # mailed: the day a mail really went (last_sent above is the day it was tried, so a learner is tried once a
        # Sunday); the day's reminder skips after it, and the count of who came back unreminded reads it (only the date)
        c.execute('UPDATE next_weekly SET mailed=? WHERE user_id=?', (today, r['id']))
        c.commit()
    return sent


def mailed_today(c, uid, now=None):
    """The Sunday mail went to this learner today: it already says how many words are due (the daily reminder skips)."""
    local = _local(now or time.time())
    if local.weekday() != 6:
        return False
    row = c.execute('SELECT mailed FROM next_weekly WHERE user_id=?', (uid,)).fetchone()
    return bool(row and row[0] == local.date().isoformat())


# ---------- routes ----------

def get(c, uid, path, q):
    if path == '/api/next/week':  # brief=1: what the 这周进步 card shows (the numbers and the weekly goal), wherever it is
        if (q.get('brief') or [''])[0] == '1':
            prof = nx.profile(c, uid) or {}
            return {**week(c, uid), 'habit': nx.habit(c, uid, prof.get('weekly_goal') or 4)}, 200
        return week(c, uid, detail=True), 200
    if path == '/api/next/text-summary':
        return text_summary(c, uid, (q.get('pack') or [''])[0][:80])
    if path == '/api/next/weekly-mail':
        return mail_state(c, uid), 200
    return None


def post_public(c, path, data):
    if path == '/api/next/weekly-mail/off':
        return unsubscribe(c, data.get('token'), on=data.get('on') is True)
    return None


def post(c, uid, path, data):
    if path == '/api/next/weekly-mail':
        return set_mail(c, uid, data)
    return None
