"""班级试用 (2026-11-24): a class a learner joins of their own accord with an invite code, and leaves whenever they like.

- 运营后台 (flow_admin.py, 管理员 only, every change in the operator log): a class is made with a name and a teacher (one
  语流 account) and gets a 6-character invite code. The console lists every class with its members, how many of them
  studied in the last 7 days, its 试用人数 and 试用人次; an operator renames it, changes its teacher or code, stops or
  restarts it.
- 学员 (我的 → 班级): find a class by its code, read what the teacher sees and what not, join; leave at any time. One class
  at a time. Leaving keeps only when they joined and left (for 试用人数 and 人次 below); 注销账号 deletes that too (the table has
  user_id, account_data.erase), and 导出我的数据 has it (account_data.records).
- 老师 (我的 → 我的班级): the teacher's own account sees, per class, numbers for the whole class only: how many of its
  members studied in the last 7 days and in each of the 4 weeks up to now, and the 5 grammar points most of them got
  wrong in the last 7 days. No names, no ids, nothing about one learner. A class with fewer than 5 members shows none
  of it. A member who leaves is out of every number from that moment; the teacher and 员工 accounts are never counted.

学过一步 (studied a step): a row in any of progress_service.DAY_TABLES — the tables 「我的进步」 counts study days from:
a step of a material, a word reviewed, 复听, 轻松读, a practice score, a question answered — made while a member: after
joining, before leaving.
做错一个语法点: a rule-checked answer on it that was wrong (learning_events.correct = 0), or a change the AI feedback on
writing made because of it (next_node_notes kind 'flag').
试用人数 and 试用人次 (for 春萌结项, the console only): RULE_PEOPLE and RULE_DAYS below. 人次 counts study days with
progress_service.study_days, so a day is the same day as in 「我的进步」.
"""
import datetime, re, secrets, time

MIN = 5                         # a class shows its teacher nothing until it has this many members
CODE_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # no I, L, O, 0 or 1: read aloud or copied by hand without mistakes
CODE_LEN = 6
TRIES, WINDOW = 10, 900         # wrong invite codes: 10 in 15 minutes pause looking up codes for 15 minutes
DAY, WEEK = 86400, 7 * 86400
TZ = datetime.timezone(datetime.timedelta(hours=8))
STEP = '学材料的任一步、复习单词、复听、轻松读、做题或其他练习，和「我的进步」算学习天数的口径一样'
RULE_PEOPLE = ('试用人数：加入班级以后、退出之前，在语流里至少学过一步（' + STEP + '）的不同学员。员工账号、这个班的老师和暂停的账号（没同意数据存放在香港）不算；'
               '同一个人在一个班里只算一个，全部班级合计时也只算一个。退出班级的人，在班里时学过就仍然算。')
RULE_DAYS = ('试用人次：这些学员在班里期间学习的天数加起来，同一学员同一天算 1 次（按北京时间算天，和「我的进步」里的学习天数一致）。'
             '全部班级合计时，同一学员同一天也只算 1 次。')
STUDY_RULE = '在学：这 7 天（按北京时间，含今天）里在语流里学过至少一步（' + STEP + '）。'


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
      teacher INTEGER REFERENCES users(id), active INTEGER NOT NULL DEFAULT 1, by TEXT NOT NULL DEFAULT '', created REAL NOT NULL,
      updated REAL);
    CREATE TABLE IF NOT EXISTS class_members(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      class_id INTEGER NOT NULL REFERENCES classes(id), joined_at REAL NOT NULL, left_at REAL);
    CREATE UNIQUE INDEX IF NOT EXISTS class_members_now ON class_members(user_id) WHERE left_at IS NULL;
    CREATE INDEX IF NOT EXISTS class_members_class ON class_members(class_id, left_at);''')


def _day(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%Y-%m-%d') if t else ''


def _md(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%m-%d')


def _end(now):
    """Weeks are 7 Beijing calendar days ending today: the next midnight is where the last one ends."""
    d = datetime.datetime.fromtimestamp(now, TZ).date() + datetime.timedelta(days=1)
    return datetime.datetime(d.year, d.month, d.day, tzinfo=TZ).timestamp()


def _norm(code):
    return re.sub(r'[\s-]', '', str(code or '')).upper()[:16]


def new_code(c):
    while True:
        code = ''.join(secrets.choice(CODE_CHARS) for _ in range(CODE_LEN))
        if not c.execute('SELECT 1 FROM classes WHERE code=?', (code,)).fetchone():
            return code


def target(k):
    """How a class is named in the operator log (its number stays when the name changes)."""
    return f"班级 {k['name']} #c{k['id']}"


def _class(c, cid):
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return None
    return c.execute('SELECT * FROM classes WHERE id=?', (cid,)).fetchone()


def _username(c, uid):
    r = c.execute('SELECT username FROM users WHERE id=?', (uid,)).fetchone() if uid else None
    return r['username'] if r else ''


# ---------------------------------------------------------------- who studied, as a member

def _tables(c):
    import progress_service as ps  # the same tables as 「我的进步」's study days
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return [t for t in ps.DAY_TABLES if t in have]


def _base(t, cid, current):
    """FROM … WHERE for the study rows of table t made by members inside their membership (the teacher and 员工 left out)."""
    sql = (f'FROM class_members m JOIN users u ON u.id=m.user_id JOIN classes k ON k.id=m.class_id JOIN "{t}" s ON s.user_id=m.user_id '
           'WHERE COALESCE(u.admin,0)=0 AND u.storage_no IS NULL AND m.user_id IS NOT k.teacher AND s.created>=m.joined_at AND (m.left_at IS NULL OR s.created<m.left_at)')
    args = []
    if cid is not None:
        sql += ' AND m.class_id=?'
        args.append(cid)
    if current:
        sql += ' AND m.left_at IS NULL'
    return sql, args


def _weeks(c, cid, now, weeks, current):
    """[set of members who studied in each week], the last 7 days (today and the 6 before) last."""
    out = [set() for _ in range(weeks)]
    end = _end(now)
    since = end - weeks * WEEK
    for t in _tables(c):
        sql, args = _base(t, cid, current)
        for r in c.execute(f'SELECT DISTINCT m.user_id, CAST((? - s.created) / {WEEK} AS INTEGER) w {sql} AND s.created>=?', [end, *args, since]):
            if 0 <= r['w'] < weeks:
                out[weeks - 1 - r['w']].add(r['user_id'])
    return out


def _trial(c, cid=None):
    """{(user_id, class_id): the Beijing dates they studied on as members of that class (progress_service.study_days, from
    joining to leaving)} — only learners who studied, so the keys are 试用人数 and the dates add up to 试用人次."""
    import progress_service as ps
    sql = ('SELECT m.user_id, m.class_id, m.joined_at, m.left_at FROM class_members m JOIN users u ON u.id=m.user_id '
           'JOIN classes k ON k.id=m.class_id WHERE COALESCE(u.admin,0)=0 AND u.storage_no IS NULL AND m.user_id IS NOT k.teacher')
    out = {}
    for r in c.execute(sql + (' AND m.class_id=?' if cid is not None else ''), (cid,) if cid is not None else ()).fetchall():
        days = ps.study_days(c, r['user_id'], r['joined_at'], r['left_at'])
        if days:
            out.setdefault((r['user_id'], r['class_id']), set()).update(days)
    return out


def _totals(trial):
    """(试用人数, 试用人次) over all classes: a learner once, and a learner's day once."""
    per = {}
    for (u, _), days in trial.items():
        per.setdefault(u, set()).update(days)
    return len(per), sum(len(d) for d in per.values())


def _members(c, k):
    """The class's members now: [(user_id, joined_at)], the teacher and 员工 left out."""
    return [(r['user_id'], r['joined_at']) for r in c.execute(
        'SELECT m.user_id, m.joined_at FROM class_members m JOIN users u ON u.id=m.user_id '
        'WHERE m.class_id=? AND m.left_at IS NULL AND COALESCE(u.admin,0)=0 AND u.storage_no IS NULL AND m.user_id IS NOT ?', (k['id'], k['teacher']))]


def _points(c, members, now, n=5):
    """The grammar points most members got wrong in the last 7 days (after they joined): [{node, title, learners}]."""
    joined = dict(members)
    if not joined:
        return []
    since, who = _end(now) - WEEK, {}
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    ids = list(joined)
    marks = ','.join('?' * len(ids))
    rows = []
    if 'learning_events' in have:
        rows += c.execute(f"SELECT user_id, node, created FROM learning_events WHERE correct=0 AND node NOT LIKE 'skill:%' AND created>? AND user_id IN ({marks})", [since, *ids]).fetchall()
    if 'next_node_notes' in have:
        rows += c.execute(f"SELECT user_id, node, created FROM next_node_notes WHERE kind='flag' AND created>? AND user_id IN ({marks})", [since, *ids]).fetchall()
    for r in rows:
        if r['created'] >= joined[r['user_id']]:
            who.setdefault(r['node'], set()).add(r['user_id'])
    titles = {r['id']: r['title'] for r in c.execute('SELECT id, title FROM subskills')} if 'subskills' in have else {}
    ranked = sorted(((nd, len(us)) for nd, us in who.items() if nd in titles), key=lambda x: (-x[1], titles[x[0]]))
    return [{'node': nd, 'title': titles[nd], 'learners': k} for nd, k in ranked[:n]]


def _week_labels(now, weeks):
    end = _end(now)
    return [f'{_md(end - (weeks - i) * WEEK)}–{_md(end - (weeks - 1 - i) * WEEK - DAY)}' for i in range(weeks)]


# ---------------------------------------------------------------- 学员: 我的 → 班级

def mine(c, uid):
    """GET /api/next/class: the class this learner is in (or None), and the classes they teach."""
    r = c.execute('SELECT k.*, m.joined_at FROM class_members m JOIN classes k ON k.id=m.class_id WHERE m.user_id=? AND m.left_at IS NULL', (uid,)).fetchone()
    member = {'name': r['name'], 'teacher': _username(c, r['teacher']), 'joined': _day(r['joined_at']), 'active': bool(r['active'])} if r else None
    # ready: whether the class has MIN members (never how many fewer: with 2 or 3 the teacher could tell who joined)
    teaching = [{'id': k['id'], 'name': k['name'], 'active': bool(k['active']), 'code': k['code'], 'ready': len(_members(c, k)) >= MIN} for k in
                c.execute('SELECT * FROM classes WHERE teacher=? ORDER BY active DESC, created DESC', (uid,))]
    return {'member': member, 'teaching': teaching, 'min': MIN}, 200


def _locked(c, uid, now):
    r = c.execute('SELECT * FROM login_failures WHERE key=?', ('class:%d' % uid,)).fetchone()
    return r if r and r['until'] > now else None


def _wrong(c, uid, now):
    key = 'class:%d' % uid
    r = c.execute('SELECT * FROM login_failures WHERE key=?', (key,)).fetchone()
    if r and r['first'] > now - WINDOW:
        n = r['count'] + 1
        c.execute('UPDATE login_failures SET count=?, until=? WHERE key=?', (n, now + WINDOW if n >= TRIES else 0, key))
    else:
        c.execute('INSERT OR REPLACE INTO login_failures(key, count, first, until) VALUES(?, 1, ?, 0)', (key, now))
    c.commit()


def _by_code(c, uid, code):
    """(class row, None) or (None, (error, status)); a wrong code counts toward the pause."""
    now = time.time()
    lock = _locked(c, uid, now)
    if lock:
        return None, ({'error': '邀请码输错太多次了，请 %d 分钟后再试' % max(1, round((lock['until'] - now) / 60)), 'field': 'code'}, 429)
    code = _norm(code)
    if not re.fullmatch(r'[A-Z0-9]{4,16}', code):
        return None, ({'error': '请输入老师给你的 6 位邀请码', 'field': 'code'}, 400)
    k = c.execute('SELECT * FROM classes WHERE code=?', (code,)).fetchone()
    if not k:
        _wrong(c, uid, now)
        return None, ({'error': '没有找到这个邀请码，请核对后再输入', 'field': 'code'}, 404)
    if not k['active']:
        return None, ({'error': '这个班级已经停用，不能再加入', 'field': 'code'}, 409)
    return k, None


def find(c, uid, data):
    """POST /api/next/class/find {code}: the class's name and teacher, before joining."""
    k, err = _by_code(c, uid, data.get('code'))
    if err:
        return err
    return {'name': k['name'], 'teacher': _username(c, k['teacher']) or '还没有指定', 'teaching': k['teacher'] == uid}, 200


def join(c, uid, data):
    """POST /api/next/class/join {code}: join of the learner's own accord; one class at a time."""
    k, err = _by_code(c, uid, data.get('code'))
    if err:
        return err
    if k['teacher'] == uid:
        return {'error': '你是这个班的老师，不用加入；在首页「我的班级」里看全班汇总', 'field': 'code'}, 409
    if __import__('teacher_service').is_teacher(c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()):
        return {'error': '老师账号不能加入班级。想以学生身份体验，请另外注册一个学生账号', 'field': 'code'}, 409
    import privacy_service as pv  # the 年龄段 first (asked in the same sheet), and under 14 a guardian's agreement
    if data.get('age'):
        got = pv.set_age(c, uid, data)
        if got[1] != 200:
            return got
    u = c.execute('SELECT age_band, guardian_ok FROM users WHERE id=?', (uid,)).fetchone()
    if not pv.info(u)['age']:
        return {'error': '加入班级前，先选一下你的年龄段', 'field': 'age', 'code': 'age'}, 409
    if pv.needs_guardian(u):
        return {'error': pv.NEED_GUARDIAN + '勾选后才能加入班级。', 'field': 'guardian', 'code': 'guardian'}, 409
    now_in = c.execute('SELECT k.id, k.name FROM class_members m JOIN classes k ON k.id=m.class_id WHERE m.user_id=? AND m.left_at IS NULL', (uid,)).fetchone()
    if now_in:
        if now_in['id'] == k['id']:
            return mine(c, uid)
        return {'error': f'你已经在「{now_in["name"]}」里了。一次只能在一个班级，先退出再加入新的', 'field': 'code'}, 409
    c.execute('INSERT INTO class_members(user_id, class_id, joined_at) VALUES(?,?,?)', (uid, k['id'], time.time()))
    c.commit()
    return mine(c, uid)


def leave(c, uid):
    """POST /api/next/class/leave: out of the class at once; only when they joined and left is kept."""
    n = c.execute('UPDATE class_members SET left_at=? WHERE user_id=? AND left_at IS NULL', (time.time(), uid)).rowcount
    c.commit()
    if not n:
        return {'error': '你现在没有加入班级'}, 409
    return mine(c, uid)


# ---------------------------------------------------------------- 老师: 我的 → 我的班级

def teach(c, uid, cid, now=None):
    """GET /api/next/class/teach?id=: the class summary for its teacher. Only numbers for the whole class: no names, no
    ids, nothing about one learner; under MIN members, none of them."""
    k = _class(c, cid)
    if not k or k['teacher'] != uid:
        return {'error': '没有找到这个班级'}, 404
    now = now or time.time()
    out = {'id': k['id'], 'name': k['name'], 'code': k['code'], 'active': bool(k['active']), 'min': MIN, 'rule': STUDY_RULE}
    members = _members(c, k)
    if not k['active'] or len(members) < MIN:
        out['ready'] = False
        return out, 200
    weeks = _weeks(c, k['id'], now, 4, True)
    out.update(ready=True, members=len(members), active_7d=len(weeks[-1]),
               weeks=[{'label': l, 'studied': len(w)} for l, w in zip(_week_labels(now, 4), weeks)],
               points=_points(c, members, now))
    return out, 200


# ---------------------------------------------------------------- 运营后台 (flow_admin.py: 管理员 only)

def console_list(c, now=None):
    """GET /classes: every class with its members now, how many studied in the last 7 days, its 试用人数 and 试用人次."""
    now = now or time.time()
    trial = _trial(c)
    items = []
    for k in c.execute('SELECT * FROM classes ORDER BY active DESC, created DESC').fetchall():
        members = _members(c, k)
        items.append({'id': k['id'], 'name': k['name'], 'code': k['code'], 'active': bool(k['active']),
                      'teacher': {'id': k['teacher'], 'username': _username(c, k['teacher'])} if k['teacher'] else None,
                      'members': len(members), 'ready': len(members) >= MIN,
                      'active_7d': len(_weeks(c, k['id'], now, 1, True)[0]),
                      'trial_people': sum(1 for (_, cid) in trial if cid == k['id']),
                      'trial_days': sum(len(d) for (_, cid), d in trial.items() if cid == k['id']),
                      'created': _day(k['created']), 'by': k['by']})
    people, days = _totals(trial)
    return {'items': items, 'trial_people': people, 'trial_days': days, 'members': sum(x['members'] for x in items),
            'rule_people': RULE_PEOPLE, 'rule_days': RULE_DAYS, 'study_rule': STUDY_RULE, 'min': MIN}


def console_detail(c, cid, now=None):
    """GET /class?id=: one class for an operator: who teaches it, its code, and 8 weeks of 在学, new 试用人数 and 试用人次."""
    k = _class(c, cid)
    if not k:
        return None
    now = now or time.time()
    weeks = _weeks(c, k['id'], now, 8, False)
    trial = [d for (_, cl), d in _trial(c, k['id']).items() if cl == k['id']]
    today = datetime.datetime.fromtimestamp(now, TZ).date()
    slot = lambda d: 7 - (today - d).days // 7  # the same 8 weeks as _weeks: 7 = today and the 6 days before
    new, visits = [0] * 8, [0] * 8
    for days in trial:
        if 0 <= slot(min(days)) <= 7:
            new[slot(min(days))] += 1
        for d in days:
            if 0 <= slot(d) <= 7:
                visits[slot(d)] += 1
    joined = c.execute('SELECT COUNT(DISTINCT user_id) FROM class_members WHERE class_id=?', (k['id'],)).fetchone()[0]
    left = c.execute('SELECT COUNT(DISTINCT user_id) FROM class_members WHERE class_id=? AND left_at IS NOT NULL AND user_id NOT IN '
                     '(SELECT user_id FROM class_members WHERE class_id=? AND left_at IS NULL)', (k['id'], k['id'])).fetchone()[0]
    tag = f'% #c{k["id"]}'
    log = [dict(r) for r in c.execute('SELECT created, email, action, detail FROM flow_admin_log WHERE target LIKE ? OR target LIKE ? ORDER BY id DESC LIMIT 30',
                                      (tag, tag + ' ·%'))] if c.execute("SELECT 1 FROM sqlite_master WHERE name='flow_admin_log'").fetchone() else []
    return {'id': k['id'], 'name': k['name'], 'code': k['code'], 'active': bool(k['active']),
            'teacher': {'id': k['teacher'], 'username': _username(c, k['teacher'])} if k['teacher'] else None,
            'created': _day(k['created']), 'by': k['by'], 'members': len(_members(c, k)), 'joined': joined or 0, 'left': left or 0,
            'trial_people': len(trial), 'trial_days': sum(len(d) for d in trial), 'min': MIN,
            'rule_people': RULE_PEOPLE, 'rule_days': RULE_DAYS, 'study_rule': STUDY_RULE,
            'weeks': [{'label': l, 'studied': len(w), 'new_people': n, 'days': v} for l, w, n, v in zip(_week_labels(now, 8), weeks, new, visits)], 'log': log}


def _teacher(c, name):
    name = str(name or '').strip()
    if not name:
        return None, ({'error': '请填老师的语流账号（用户名）', 'field': 'teacher'}, 400)
    r = c.execute('SELECT id, username, COALESCE(disabled,0) disabled FROM users WHERE username=? COLLATE NOCASE', (name[:60],)).fetchone()
    if not r:
        return None, ({'error': f'没有叫「{name[:30]}」的语流账号。请老师先在语流注册，再把用户名填在这里', 'field': 'teacher'}, 404)
    if r['disabled']:
        return None, ({'error': '这个账号已停用，不能当老师', 'field': 'teacher'}, 409)
    return r, None


def _name(v):
    v = re.sub(r'\s+', ' ', str(v or '')).strip()
    if not 2 <= len(v) <= 30:
        return None, ({'error': '班级名写 2–30 个字', 'field': 'name'}, 400)
    return v, None


def create(c, data, by):
    """POST /class/create {name, teacher}: (body, status, log target)."""
    name, err = _name(data.get('name'))
    if err:
        return (*err, '')
    t, err = _teacher(c, data.get('teacher'))
    if err:
        return (*err, '')
    now = time.time()
    cid = c.execute('INSERT INTO classes(name, code, teacher, by, created, updated) VALUES(?,?,?,?,?,?)',
                    (name, new_code(c), t['id'], by, now, now)).lastrowid
    c.commit()
    k = _class(c, cid)
    return {'ok': True, 'id': cid, 'code': k['code']}, 200, f"{target(k)} · 老师 {t['username']} #{t['id']}"


def change(c, data):
    """POST /class/rename {id, name} · /class/teacher {id, teacher} · /class/code {id} · /class/active {id, active}:
    the path's last part says which. (body, status, log target, detail)."""
    k = _class(c, data.get('id'))
    if not k:
        return {'error': '没有找到这个班级'}, 404, '', ''
    what, now = data.get('_what'), time.time()
    if what == 'rename':
        name, err = _name(data.get('name'))
        if err:
            return (*err, '', '')
        c.execute('UPDATE classes SET name=?, updated=? WHERE id=?', (name, now, k['id']))
        detail = f"{k['name']} → {name}"
    elif what == 'teacher':
        t, err = _teacher(c, data.get('teacher'))
        if err:
            return (*err, '', '')
        c.execute('UPDATE classes SET teacher=?, updated=? WHERE id=?', (t['id'], now, k['id']))
        c.commit()
        return {'ok': True}, 200, f"{target(k)} · 老师 {t['username']} #{t['id']}", f"原来的老师：{_username(c, k['teacher']) or '没有'}"
    elif what == 'code':
        c.execute('UPDATE classes SET code=?, updated=? WHERE id=?', (new_code(c), now, k['id']))
        detail = '旧邀请码作废'
    elif what == 'active':
        on = bool(data.get('active'))
        c.execute('UPDATE classes SET active=?, updated=? WHERE id=?', (int(on), now, k['id']))
        detail = '重新启用' if on else '停用（不能再加入，老师看不到汇总；已在班里的人不受影响，可以随时退出）'
    else:
        return {'error': '接口不存在'}, 404, '', ''
    c.commit()
    return {'ok': True, 'code': _class(c, k['id'])['code']}, 200, target(_class(c, k['id'])), detail


SURVEY_AFTER = 21 * DAY  # the trial survey is offered on 今日 three weeks after joining (survey_service.TRIAL)


def survey_due(c, uid, now=None):
    """Whether 今日 offers the anonymous trial survey: in a class now, joined at least three weeks ago. Whether it was
    answered or closed is kept on the phone only, so nothing links an account to an answer."""
    r = c.execute('SELECT m.joined_at FROM class_members m JOIN classes k ON k.id=m.class_id WHERE m.user_id=? AND m.left_at IS NULL AND k.active=1',
                  (uid,)).fetchone()
    return bool(r) and (now or time.time()) - r['joined_at'] >= SURVEY_AFTER


def membership(c, uid):
    """For the console's learner drawer: the class they are in now, and the classes they teach."""
    r = c.execute('SELECT k.id, k.name, m.joined_at FROM class_members m JOIN classes k ON k.id=m.class_id WHERE m.user_id=? AND m.left_at IS NULL', (uid,)).fetchone()
    return {'member': {'id': r['id'], 'name': r['name'], 'joined': _day(r['joined_at'])} if r else None,
            'teaching': [{'id': k['id'], 'name': k['name']} for k in c.execute('SELECT id, name FROM classes WHERE teacher=?', (uid,))]}


def classes_csv(c, now=None):
    """试用人数 and 试用人次 for 春萌结项: one row a class and a total, with both rules on top."""
    import csv, io
    out = console_list(c, now)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([RULE_PEOPLE])
    w.writerow([RULE_DAYS])
    w.writerow(['班级', '老师', '创建日期', '现在人数', '近 7 天在学', '试用人数', '试用人次', '状态'])
    for x in out['items']:
        w.writerow([x['name'], (x['teacher'] or {}).get('username', ''), x['created'], x['members'], x['active_7d'], x['trial_people'], x['trial_days'],
                    '使用中' if x['active'] else '已停用'])
    w.writerow(['合计（同一人、同一人同一天只算一次）', '', '', out['members'], '', out['trial_people'], out['trial_days'], ''])
    return ('﻿' + buf.getvalue()).encode('utf-8')


def export_rows(c, uid):
    """For 导出我的数据: the classes the account was in (with when it joined and left) and the ones it teaches."""
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'class_members' not in have:
        return {}
    out = {}
    rows = c.execute('SELECT k.name, m.joined_at, m.left_at FROM class_members m JOIN classes k ON k.id=m.class_id WHERE m.user_id=? ORDER BY m.joined_at', (uid,)).fetchall()
    if rows:
        out['班级'] = [{'班级': r['name'], '加入': _day(r['joined_at']), '退出': _day(r['left_at']) or '还在班里'} for r in rows]
    teach_rows = c.execute('SELECT name FROM classes WHERE teacher=?', (uid,)).fetchall()
    if teach_rows:
        out['我当老师的班级'] = [r['name'] for r in teach_rows]
    return out
