"""Data for the xmc.hk console (r26), read only: learners one by one, the onboarding funnel and weekly cohorts, how each
material and word book does, exam practice, AI use, and CSV files of the tables.

Days are Asia/Shanghai calendar days. A learner studies on a day with a step of a material or a word review. What a
learner wrote (answers, essays, chats) never leaves here; only counts, levels, words and titles do. Emails are masked.
"""
import csv, datetime, io, json, os, time

DAY = 86400
KIND_LABEL = {'next-rewrite': '仿写改写', 'next-explain': '句子讲解', 'next-variant': '难度改写', 'next-shadow': '跟读点评',
              'next-examples': 'AI 例句', 'next-retell': '复述', 'next-dialog': '情景对话', 'next-essay': '短文批改',
              'next-translate': '翻译批改', 'next-transsrc': '翻译原句', 'next-say': '发音检查', 'next-enrich': '导入文章出题'}
RATE_LABEL = {'again': '忘了', 'hard': '模糊', 'good': '记得', 'easy': '很熟', 'known': '标为熟知', 'used': '写作用对',
              'misused': '写作用错', 'lookup': '阅读时查词'}
SOURCE_LABEL = {'book': '词书每日新词', 'saved': '读文章时收藏', 'import': '自己导入', 'mistake': '错题加入'}
GOAL_LABEL = {'daily': '日常交流', 'work': '工作沟通', 'exam': '考试', 'abroad': '留学和海外生活', 'media': '看懂影视、新闻', 'interest': '兴趣'}


def _tz():
    return __import__('next_service').TZ


def day_of(t):
    return datetime.datetime.fromtimestamp(t, _tz()).date()


def today():
    return day_of(time.time())


def _q(c, sql, *a):
    return c.execute(sql, a).fetchone()[0]


def activity(c, uid=None):
    """uid -> {date: [material steps, reviews]} over all time (or one learner)."""
    out = {}
    where, args = ('WHERE user_id=?', (uid,)) if uid else ('', ())
    for table, k in (('next_progress', 0), ('next_reviews', 1)):
        for u, t in c.execute(f'SELECT user_id, created FROM {table} {where}', args):
            cell = out.setdefault(u, {}).setdefault(day_of(t), [0, 0])
            cell[k] += 1
    return out


def _titles(c):
    """material id -> (title, level, theme label, origin) for every public material, the hidden ones too."""
    import next_service as nx
    out = {}
    for row, p in nx._public_packs(c, with_hidden=True):
        out[p['id']] = (p.get('title') or p['id'], nx.cefr(p), nx.THEMES.get(p.get('theme'), p.get('theme') or ''), row['origin'])
    return out


def _title(c, titles, pid):
    if pid in titles:
        return titles[pid][0]
    row = c.execute('SELECT content FROM lab_packs WHERE id=?', (pid,)).fetchone()
    try:
        return json.loads(row[0]).get('title') or pid if row else pid
    except ValueError:
        return pid


def _session_seen(c):
    """uid -> the last time the account opened the site signed in (sessions slide by a day at most, app.SESSION_DAYS)."""
    days = getattr(__import__('sys').modules.get('app'), 'SESSION_DAYS', 30)
    return {u: t - days * DAY for u, t in c.execute('SELECT user_id, MAX(expires) FROM sessions WHERE expires>? GROUP BY user_id', (time.time(),))}


def _joined(u, prof_created, first_day):
    """When an account began: the sign-up time (kept since r26), else its learning profile, else its first study day."""
    if u['created']:
        return u['created']
    if prof_created:
        return prof_created
    if first_day:
        return datetime.datetime.combine(first_day, datetime.time(12), _tz()).timestamp()
    return None


# ---------- learners ----------

def learners(c):
    """One row per account, for the 学员 table (newest first). Everything here is counts and dates."""
    import auth_service
    now, td = time.time(), today()
    act = activity(c)
    prof = {r['user_id']: r for r in c.execute('SELECT user_id, level, goal, created FROM next_profiles')}
    plans = {r['user_id']: r for r in c.execute('SELECT user_id, book, daily_new FROM next_vocab_plans')}
    cards = {u: (n, b) for u, n, b in c.execute("SELECT user_id, COUNT(*), SUM(source='book') FROM next_cards GROUP BY user_id")}
    rev7 = dict(c.execute('SELECT user_id, COUNT(*) FROM next_reviews WHERE created>? GROUP BY user_id', (now - 7 * DAY,)).fetchall())
    mats = dict(c.execute('SELECT user_id, COUNT(DISTINCT pack) FROM next_progress GROUP BY user_id').fetchall())
    done = dict(c.execute("SELECT user_id, COUNT(DISTINCT pack) FROM next_progress WHERE step='output' GROUP BY user_id").fetchall())
    since = (td - datetime.timedelta(days=6)).isoformat()
    ai7 = dict(c.execute('SELECT user_id, SUM(count) FROM ai_usage WHERE day>=? GROUP BY user_id', (since,)).fetchall())
    exams = dict(c.execute('SELECT user_id, COUNT(*) FROM next_exam_results GROUP BY user_id').fetchall())
    fb = dict(c.execute('SELECT user_id, COUNT(*) FROM feedback WHERE user_id IS NOT NULL GROUP BY user_id').fetchall())
    seen = _session_seen(c)
    last_job = dict(c.execute('SELECT user_id, MAX(created) FROM lab_jobs GROUP BY user_id').fetchall())
    import vocab_service as vs
    out = []
    for u in c.execute('SELECT id, username, email, admin, disabled, created FROM users ORDER BY id DESC'):
        uid = u['id']
        days = act.get(uid, {})
        first = min(days) if days else None
        last_study = max(days) if days else None
        p = prof.get(uid)
        joined = _joined(u, p['created'] if p else None, first)
        last_seen = max([t for t in (seen.get(uid), last_job.get(uid)) if t] +
                        ([datetime.datetime.combine(last_study, datetime.time(12), _tz()).timestamp()] if last_study else []), default=None)
        plan = plans.get(uid)
        out.append({
            'id': uid, 'username': u['username'], 'email': auth_service.mask(u['email']) if u['email'] else '', 'has_email': bool(u['email']),
            'staff': bool(u['admin']), 'disabled': bool(u['disabled']), 'joined': joined, 'joined_known': bool(u['created']),
            'level': p['level'] if p else None, 'goal': GOAL_LABEL.get(p['goal'], p['goal']) if p else None,
            'last_study': last_study.isoformat() if last_study else None, 'last_seen': last_seen,
            'days_total': len(days), 'days_7d': sum(1 for d in days if (td - d).days < 7), 'days_30d': sum(1 for d in days if (td - d).days < 30),
            'materials': mats.get(uid, 0), 'materials_done': done.get(uid, 0),
            'book': vs.book_title(plan['book']) if plan else None, 'daily_new': plan['daily_new'] if plan else None,
            'cards': (cards.get(uid) or (0, 0))[0], 'book_words': (cards.get(uid) or (0, 0))[1] or 0,
            'reviews_7d': rev7.get(uid, 0), 'ai_7d': ai7.get(uid, 0), 'exams': exams.get(uid, 0), 'feedback': fb.get(uid, 0),
        })
    return out


FILTERS = {
    'all': ('全部', lambda r, td: True),
    'active7': ('近 7 天学过', lambda r, td: r['days_7d'] > 0),
    'lapsed': ('学过、超过 7 天没学', lambda r, td: r['days_total'] > 0 and not r['days_7d']),
    'never': ('注册了还没开始学', lambda r, td: not r['days_total']),
    'staff': ('员工账号', lambda r, td: r['staff']),
    'disabled': ('已停用', lambda r, td: r['disabled']),
}
SORTS = {
    'recent': lambda r: (r['last_seen'] or 0, r['id']),
    'days': lambda r: (r['days_total'], r['last_seen'] or 0),
    'joined': lambda r: (r['joined'] or 0, r['id']),
    'ai': lambda r: (r['ai_7d'], r['last_seen'] or 0),
}


def learner_list(c, q='', flt='all', sort='recent', page=1, per=50):
    rows = learners(c)
    td = today()
    counts = {k: sum(1 for r in rows if f(r, td)) for k, (_, f) in FILTERS.items()}
    q = str(q or '').strip().lower()[:60]
    if q:
        rows = [r for r in rows if q in r['username'].lower() or (q.isdigit() and int(q) == r['id'])]
    flt = flt if flt in FILTERS else 'all'
    rows = [r for r in rows if FILTERS[flt][1](r, td)]
    rows.sort(key=SORTS.get(sort, SORTS['recent']), reverse=True)
    page = max(1, int(page or 1))
    return {'items': rows[(page - 1) * per: page * per], 'total': len(rows), 'page': page, 'per_page': per,
            'filters': [{'key': k, 'label': v[0], 'count': counts[k]} for k, v in FILTERS.items()]}


def learner(c, uid):
    """Everything an operator needs to help one learner: account, profile, study days, word plan, mistakes, materials,
    exam practice, AI use, feedback and what operators did to the account. Never the password, a session or what the
    learner wrote."""
    import auth_service, vocab_service as vs, exam_service as ex, chat_service, feedback_service
    uid = int(uid)
    u = c.execute('SELECT id, username, email, admin, disabled, created FROM users WHERE id=?', (uid,)).fetchone()
    if not u:
        return None
    now, td = time.time(), today()
    p = c.execute('SELECT * FROM next_profiles WHERE user_id=?', (uid,)).fetchone()
    days = activity(c, uid).get(uid, {})
    first = min(days) if days else None
    # 12 weeks, Monday first, ending this week
    start = td - datetime.timedelta(days=td.weekday() + 7 * 11)
    calendar = [{'day': (start + datetime.timedelta(days=i)).isoformat(), 'steps': days.get(start + datetime.timedelta(days=i), [0, 0])[0],
                 'reviews': days.get(start + datetime.timedelta(days=i), [0, 0])[1], 'future': start + datetime.timedelta(days=i) > td}
                for i in range(84)]
    titles = _titles(c)
    mats = []
    for pid, steps, last in c.execute('SELECT pack, GROUP_CONCAT(step), MAX(created) FROM next_progress WHERE user_id=? GROUP BY pack ORDER BY MAX(created) DESC LIMIT 20', (uid,)):
        t = titles.get(pid)
        mats.append({'id': pid, 'title': _title(c, titles, pid), 'level': t[1] if t else '', 'steps': (steps or '').split(','), 'last': last})
    vo = None
    if c.execute('SELECT 1 FROM next_vocab_plans WHERE user_id=?', (uid,)).fetchone() or c.execute('SELECT 1 FROM next_cards WHERE user_id=?', (uid,)).fetchone():
        o = vs.overview(c, uid)
        vo = {'plan': {k: o['plan'][k] for k in ('book', 'daily_new', 'retention', 'estimate')} if o['plan'] else None,
              'book': o['book'], 'mastered': o['mastered'], 'learning': o['learning'], 'total': o['total'],
              'due': o.get('due'), 'new': o.get('new')}
        if vo['plan']:
            vo['plan']['title'] = vs.book_title(vo['plan']['book'])
    sources = {SOURCE_LABEL.get(k, k): n for k, n in c.execute('SELECT source, COUNT(*) FROM next_cards WHERE user_id=? GROUP BY source', (uid,))}
    mistakes = [dict(r) for r in c.execute('SELECT text, meaning, lapses, reps FROM next_cards WHERE user_id=? AND lapses>0 ORDER BY lapses DESC, last DESC LIMIT 12', (uid,))]
    ratings = {RATE_LABEL.get(k, k): n for k, n in c.execute('SELECT rating, COUNT(*) FROM next_reviews WHERE user_id=? AND created>? GROUP BY rating', (uid, now - 30 * DAY))}
    mature = c.execute("SELECT COUNT(*), SUM(rating!='again') FROM next_reviews WHERE user_id=? AND created>? AND elapsed>=1 AND rating IN ('again','hard','good','easy')",
                       (uid, now - 30 * DAY)).fetchone()
    exams = [{'exam': r['exam'], 'title': ex.EXAMS.get(r['exam'], {}).get('title', r['exam']), 'score': r['score'], 'total': r['total'],
              'pct': round(100 * r['score'] / r['total']) if r['total'] else None, 'seconds': r['seconds'], 'created': r['created'],
              'parts': json.loads(r['parts'] or '[]')}
             for r in c.execute('SELECT exam, score, total, parts, seconds, created FROM next_exam_results WHERE user_id=? ORDER BY created DESC LIMIT 12', (uid,))]
    ai = {}
    for kind, status, n in c.execute('SELECT kind, status, COUNT(*) FROM lab_jobs WHERE user_id=? AND created>? GROUP BY kind, status', (uid, now - 30 * DAY)):
        k = ai.setdefault(kind, {'kind': kind, 'label': KIND_LABEL.get(kind, kind), 'complete': 0, 'failed': 0, 'other': 0})
        k['complete' if status == 'complete' else 'failed' if status == 'failed' else 'other'] += n
    ai_days = dict(c.execute('SELECT day, count FROM ai_usage WHERE user_id=? AND day>=?', (uid, (td - datetime.timedelta(days=13)).isoformat())).fetchall())
    fb = [{'id': r['id'], 'created': r['created'], 'kind': feedback_service.KINDS.get(r['kind'], r['kind']), 'status': r['status'], 'text': r['text'][:80]}
          for r in c.execute('SELECT id, created, kind, status, text FROM feedback WHERE user_id=? ORDER BY id DESC LIMIT 8', (uid,))]
    log = [dict(r) for r in c.execute('SELECT created, email, action, detail FROM flow_admin_log WHERE target LIKE ? ORDER BY id DESC LIMIT 20', (f'% #{uid}',))]
    lab = __import__('flow_admin').ACTION_LABEL
    for r in log:
        r['action_label'] = lab.get(r['action'], r['action'])
    lock = c.execute('SELECT until FROM login_failures WHERE key=?', ('u:%d' % uid,)).fetchone()
    sessions = _q(c, 'SELECT COUNT(*) FROM sessions WHERE user_id=? AND expires>?', uid, now)
    seen = _session_seen(c).get(uid)
    return {
        'account': {'id': uid, 'username': u['username'], 'email': auth_service.mask(u['email']) if u['email'] else '', 'has_email': bool(u['email']),
                    'staff': bool(u['admin']), 'disabled': bool(u['disabled']), 'joined': _joined(u, p['created'] if p else None, first),
                    'joined_known': bool(u['created']), 'sessions': sessions, 'last_open': seen,
                    'locked_until': lock['until'] if lock and lock['until'] > now else None},
        'profile': {'level': p['level'], 'goal': GOAL_LABEL.get(p['goal'], p['goal']), 'minutes': p['minutes'], 'weekly_goal': p['weekly_goal'],
                    'themes': [__import__('next_service').THEMES.get(t, t) for t in json.loads(p['themes'] or '[]')], 'created': p['created']} if p else None,
        'study': {'days_total': len(days), 'days_7d': sum(1 for d in days if (td - d).days < 7), 'days_30d': sum(1 for d in days if (td - d).days < 30),
                  'first': first.isoformat() if first else None, 'last': max(days).isoformat() if days else None,
                  'steps': sum(v[0] for v in days.values()), 'reviews': sum(v[1] for v in days.values()), 'calendar': calendar},
        'vocab': vo, 'card_sources': sources, 'mistakes': mistakes, 'ratings_30d': ratings,
        'retention_30d': round(mature[1] / mature[0], 3) if mature and mature[0] else None,
        'materials': mats, 'exams': exams,
        'ai': {'kinds': sorted(ai.values(), key=lambda k: -(k['complete'] + k['failed'])),
               'days': [{'day': (td - datetime.timedelta(days=i)).isoformat(), 'count': ai_days.get((td - datetime.timedelta(days=i)).isoformat(), 0)} for i in range(13, -1, -1)],
               'remaining': chat_service.remaining(c, uid)},
        'feedback': fb, 'log': log,
    }


# ---------- onboarding funnel and weekly cohorts ----------

def funnel(c, days=0):
    """Accounts that began in the window (all of them for 0), and how far they got, each step within the previous one."""
    now, td = time.time(), today()
    act = activity(c)
    prof = {r[0]: r[1] for r in c.execute('SELECT user_id, created FROM next_profiles')}
    started = {r[0] for r in c.execute('SELECT DISTINCT user_id FROM next_progress')}
    finished = {r[0] for r in c.execute("SELECT DISTINCT user_id FROM next_progress WHERE step='output'")}
    planned = {r[0] for r in c.execute('SELECT user_id FROM next_vocab_plans')}
    steps = [['注册', 0], ['填了水平和目标', 0], ['学了第一篇', 0], ['学完一篇（用出来）', 0], ['一周内又来学', 0], ['第二周还在学', 0]]
    waiting = [0, 0]
    unknown = 0
    side = {'plan': 0, 'next_day': 0, 'next_day_of': 0}
    for u in c.execute('SELECT id, created FROM users WHERE admin=0'):
        uid = u['id']
        ds = act.get(uid, {})
        first = min(ds) if ds else None
        joined = _joined(u, prof.get(uid), first)
        if days:
            if joined is None:
                unknown += 1
                continue
            if joined < now - days * DAY:
                continue
        reach = [True, uid in prof, uid in started, uid in finished]
        k = 0
        while k < len(reach) and reach[k]:
            steps[k][1] += 1
            k += 1
        side['plan'] += uid in planned
        if not first:
            continue
        if (td - first).days >= 1:
            side['next_day_of'] += 1
            side['next_day'] += (first + datetime.timedelta(days=1)) in ds
        if k < 4:
            continue
        for i, (lo, hi) in enumerate(((1, 7), (8, 14))):
            if any(lo <= (d - first).days <= hi for d in ds):
                steps[4 + i][1] += 1
                continue
            if (td - first).days < hi:
                waiting[i] += 1  # that week is not over yet: not lost
            break
    return {'days': days, 'steps': [{'label': s[0], 'count': s[1]} for s in steps], 'waiting': {'week1': waiting[0], 'week2': waiting[1]},
            'unknown_joined': unknown, 'planned': side['plan'], 'next_day': side['next_day'], 'next_day_of': side['next_day_of'],
            'note': '员工账号不算。r26 之前注册的账号没有注册时间，按开始学习的时间算。'}


def cohorts(c, weeks=12):
    """Learners by the week they first studied (Monday first): how many studied again in week 1, 2, 3 and 4 after."""
    td = today()
    act = activity(c)
    staff = {r[0] for r in c.execute('SELECT id FROM users WHERE admin=1')}
    monday = td - datetime.timedelta(days=td.weekday())
    rows = {}
    for uid, ds in act.items():
        if uid in staff or not ds:
            continue
        first = min(ds)
        wk = first - datetime.timedelta(days=first.weekday())
        if (monday - wk).days // 7 >= weeks:
            continue
        r = rows.setdefault(wk, {'n': 0, 'cells': [[0, 0] for _ in range(4)]})
        r['n'] += 1
        for k in range(4):
            lo, hi = 7 * k + 1, 7 * k + 7
            if (td - first).days < hi:
                continue  # this week after the start is not over yet for this learner
            r['cells'][k][1] += 1
            r['cells'][k][0] += any(lo <= (d - first).days <= hi for d in ds)
    out = []
    for i in range(weeks):
        wk = monday - datetime.timedelta(days=7 * i)
        r = rows.get(wk, {'n': 0, 'cells': [[0, 0] for _ in range(4)]})
        out.append({'week': wk.isoformat(), 'n': r['n'],
                    'cells': [{'back': b, 'of': o, 'pct': round(100 * b / o) if o else None} for b, o in r['cells']]})
    return {'weeks': out, 'note': '按第一次学习的那一周分组；「第 1 周」是开始后第 1–7 天又学过的比例，还没过完的周不算。员工账号不算。'}


# ---------- materials, word books, exam practice ----------

def content(c, days=0):
    import next_service as nx
    now = time.time()
    since = now - days * DAY if days else 0
    per = {}
    for pid, step, n in c.execute('SELECT pack, step, COUNT(DISTINCT user_id) FROM next_progress WHERE created>=? GROUP BY pack, step', (since,)):
        per.setdefault(pid, {})[step] = n
    learners = dict(c.execute('SELECT pack, COUNT(DISTINCT user_id) FROM next_progress WHERE created>=? GROUP BY pack', (since,)).fetchall())
    last = dict(c.execute('SELECT pack, MAX(created) FROM next_progress GROUP BY pack').fetchall())
    easy = {}
    for pid, rating, n in c.execute('SELECT pack, rating, COUNT(*) FROM next_easy_reads WHERE created>=? GROUP BY pack, rating', (since,)):
        easy.setdefault(pid, {})[rating] = n
    hidden = {r['pack']: dict(r) for r in c.execute('SELECT pack, reason, by, at FROM material_hidden')}
    items = []
    for row, p in nx._public_packs(c, with_hidden=True):
        pid = p['id']
        n = learners.get(pid, 0)
        s = per.get(pid, {})
        items.append({'id': pid, 'title': p.get('title') or pid, 'level': nx.cefr(p), 'theme': nx.THEMES.get(p.get('theme'), p.get('theme') or ''),
                      'origin': '热点' if row['origin'] == 'daily' else '系列' if p.get('series') else '精选' if nx.featured(p) else '材料',
                      'learners': n, 'steps': {k: s.get(k, 0) for k in nx.STEPS}, 'completion': round(100 * s.get('output', 0) / n) if n else None,
                      'easy_read': easy.get(pid, {}), 'last': last.get(pid), 'hidden': pid in hidden, 'hidden_info': hidden.get(pid)})
    items.sort(key=lambda m: (-m['learners'], -(m['last'] or 0), m['title']))
    levels = {}
    for m in items:
        levels[m['level']] = levels.get(m['level'], 0) + 1
    return {'days': days, 'items': items, 'total': len(items), 'used': sum(1 for m in items if m['learners']),
            'hidden': len(hidden), 'levels': levels}


def books(c):
    import vocab_service as vs
    bw = vs.book_words()
    sets = {k: {w for _, w in v} for k, v in bw.items()}
    studied = {}
    for uid, norm in c.execute("SELECT user_id, norm FROM next_cards WHERE state!='new' OR known=1"):
        studied.setdefault(uid, set()).add(norm)
    plans = c.execute('SELECT p.user_id, p.book, p.daily_new FROM next_vocab_plans p JOIN users u ON u.id=p.user_id WHERE u.admin=0').fetchall()
    per = {}
    for r in plans:
        size = len(sets.get(r['book'], ()))
        got = len(studied.get(r['user_id'], set()) & sets.get(r['book'], set()))
        per.setdefault(r['book'], []).append((got, size, r['daily_new']))
    items = []
    for b in vs.registry():
        xs = per.get(b['id'], [])
        items.append({'id': b['id'], 'title': b['title'], 'group': b['group'], 'size': b['size'], 'learners': len(xs),
                      'avg_words': round(sum(x[0] for x in xs) / len(xs)) if xs else None,
                      'avg_pct': round(sum(100 * x[0] / x[1] for x in xs if x[1]) / len(xs), 1) if xs else None,
                      'best_pct': round(max(100 * x[0] / x[1] for x in xs if x[1]), 1) if xs and any(x[1] for x in xs) else None,
                      'avg_daily_new': round(sum(x[2] for x in xs) / len(xs)) if xs else None})
    return {'items': items, 'learners': len(plans)}


def exams(c):
    import exam_service as ex
    out = []
    for exam, n, people, avg, best, secs, last in c.execute(
            'SELECT exam, COUNT(*), COUNT(DISTINCT user_id), AVG(100.0*score/total), MAX(100.0*score/total), AVG(seconds), MAX(created) '
            'FROM next_exam_results WHERE total>0 GROUP BY exam ORDER BY COUNT(*) DESC'):
        parts = {}
        for (raw,) in c.execute('SELECT parts FROM next_exam_results WHERE exam=? AND total>0', (exam,)):
            for part in json.loads(raw or '[]'):
                a = parts.setdefault(part.get('title') or part.get('key'), [0, 0])
                a[0] += part.get('right', 0)
                a[1] += part.get('of', 0)
        out.append({'exam': exam, 'title': ex.EXAMS.get(exam, {}).get('title', exam), 'papers': n, 'learners': people, 'avg_pct': round(avg),
                    'best_pct': round(best), 'avg_minutes': round(secs / 60, 1), 'last': last,
                    'parts': [{'title': k, 'pct': round(100 * v[0] / v[1]) if v[1] else None} for k, v in parts.items()]})
    return {'items': out, 'note': ex.NOTE}


# ---------- AI ----------

def ai(c, days=14, people=False):
    import console_ops
    days = 30 if int(days or 14) >= 30 else 14
    now, td = time.time(), today()
    utc_today = datetime.datetime.utcfromtimestamp(now).date()
    by_day = dict(c.execute('SELECT day, SUM(count) FROM ai_usage WHERE day>=? GROUP BY day', ((utc_today - datetime.timedelta(days=days - 1)).isoformat(),)).fetchall())
    kinds = {}
    for kind, status, n, wait in c.execute('SELECT kind, status, COUNT(*), AVG(updated-created) FROM lab_jobs WHERE created>? GROUP BY kind, status', (now - days * DAY,)):
        k = kinds.setdefault(kind, {'kind': kind, 'label': KIND_LABEL.get(kind, kind), 'complete': 0, 'failed': 0, 'other': 0, 'seconds': None})
        if status == 'complete':
            k['complete'] += n
            k['seconds'] = round(wait or 0, 1)
        elif status == 'failed':
            k['failed'] += n
        else:
            k['other'] += n
    for k in kinds.values():
        tot = k['complete'] + k['failed']
        k['fail_pct'] = round(100 * k['failed'] / tot) if tot else None
    lim = console_ops.limits()
    day = utc_today.isoformat()
    out = {
        'days': days, 'today': by_day.get(day, 0),
        'by_day': [{'day': (utc_today - datetime.timedelta(days=i)).isoformat(), 'count': by_day.get((utc_today - datetime.timedelta(days=i)).isoformat(), 0)}
                   for i in range(days - 1, -1, -1)],
        'kinds': sorted(kinds.values(), key=lambda k: -(k['complete'] + k['failed'] + k['other'])),
        'limits': lim, 'users_at_limit': _q(c, 'SELECT COUNT(*) FROM ai_usage a JOIN users u ON u.id=a.user_id WHERE a.day=? AND u.admin=0 AND a.count>=?', day, lim['user_limit']) if lim['user_limit'] else 0,
        'models': {'main': os.getenv('FLOW_AI_MODEL', ''), 'text': os.getenv('FLOW_TEXT_AI_MODEL', '')},
        'note': '次数按 UTC 日计（北京时间早上 8 点换日），和额度重置一致；按功能的统计来自学习页面的 AI 请求。',
    }
    if people:
        out['top'] = [{'id': r[0], 'username': r[1], 'staff': bool(r[2]), 'count': r[3]} for r in c.execute(
            'SELECT u.id, u.username, u.admin, SUM(a.count) n FROM ai_usage a JOIN users u ON u.id=a.user_id WHERE a.day>=? GROUP BY u.id ORDER BY n DESC LIMIT 15',
            ((utc_today - datetime.timedelta(days=days - 1)).isoformat(),))]
        out['failures'] = [{'kind': KIND_LABEL.get(r[0], r[0]), 'error': (r[1] or '')[:160], 'created': r[2]} for r in c.execute(
            "SELECT kind, error, created FROM lab_jobs WHERE status='failed' AND created>? ORDER BY id DESC LIMIT 8", (now - days * DAY,))]
    return out


# ---------- CSV ----------

def _csv(head, rows):
    buf = io.StringIO()
    buf.write('﻿')  # Excel opens UTF-8 correctly with a BOM
    w = csv.writer(buf)
    w.writerow(head)
    for r in rows:
        w.writerow(['' if v is None else v for v in r])
    return buf.getvalue().encode('utf-8')


def _date(t):
    return datetime.datetime.fromtimestamp(t, _tz()).strftime('%Y-%m-%d %H:%M') if t else ''


def learners_csv(c):
    head = ['编号', '用户名', '邮箱（打码）', '员工账号', '已停用', '注册', '水平', '目标', '最近来', '最近学习日', '学习天数', '近7天学习天数', '近30天学习天数',
            '学过的材料', '学完的材料', '词书', '每日新词', '单词卡', '近7天复习', '近7天AI次数', '考试练习次数', '反馈条数']
    rows = [[r['id'], r['username'], r['email'], '是' if r['staff'] else '', '是' if r['disabled'] else '', _date(r['joined']), r['level'], r['goal'],
             _date(r['last_seen']), r['last_study'], r['days_total'], r['days_7d'], r['days_30d'], r['materials'], r['materials_done'], r['book'],
             r['daily_new'], r['cards'], r['reviews_7d'], r['ai_7d'], r['exams'], r['feedback']] for r in learners(c)]
    return _csv(head, rows)


def materials_csv(c):
    d = content(c)
    head = ['编号', '标题', '级别', '话题', '类型', '学过的人', '听', '读', '理解题', '用出来', '学完的比例%', '轻松读：容易', '轻松读：正好', '轻松读：难', '已下架']
    rows = [[m['id'], m['title'], m['level'], m['theme'], m['origin'], m['learners'], m['steps']['listen'], m['steps']['read'], m['steps']['check'],
             m['steps']['output'], m['completion'], m['easy_read'].get('easy', 0), m['easy_read'].get('ok', 0), m['easy_read'].get('hard', 0),
             '是' if m['hidden'] else ''] for m in d['items']]
    return _csv(head, rows)


def ai_csv(c, days=30):
    now = time.time()
    rows = []
    for day, kind, status, n in c.execute(
            "SELECT date(created, 'unixepoch', '+8 hours'), kind, status, COUNT(*) FROM lab_jobs WHERE created>? GROUP BY 1, 2, 3 ORDER BY 1, 2, 3", (now - days * DAY,)):
        rows.append([day, KIND_LABEL.get(kind, kind), kind, {'complete': '成功', 'failed': '失败'}.get(status, status), n])
    return _csv(['日期（北京时间）', '功能', '代码', '结果', '次数'], rows)
