"""Each account's AI quota (2026-11-26, the owner in A0: a learner sees their own AI use of the day in 「我的 → 设置」,
and both consoles can change an account's quota and see each person's use, to manage it and stop abuse). B6 builds the
pages; this is the layer every AI call goes through (chat_service.reserve: the tutor, every run_job task, 发音).

The gates, in order (reserve): the day's ¥10 stop, the site's ceiling of the day, then this account: paused, then its
own ceiling. An account's ceiling: an override in force (a number of calls a day, or a factor on the usual one) over
FLOW_AI_USER_DAILY_LIMIT (the console's value over /etc/flow.env). Admins have no ceiling of their own but can be
paused. Paused also stops AI voice (the page reads with the browser's voice); learning without AI goes on.
Counting: ai_usage (a UTC day, reset at 08:00 Beijing), and per task in ai_usage_kind beside it, written and given
back in the same places, so the parts always add up to the number the gates use.
"""
import datetime, json, time

DAILY_MAX, FACTOR_MIN, FACTOR_MAX, REASON_MAX, UNTIL_MAX_DAYS = 1000, 0.1, 10.0, 120, 366
PAUSED = '你的 AI 功能暂停中；学材料、背单词和做题照常可以用。有疑问请联系老师或管理员。'
SITE_FULL = '本站今日 AI 调用额度已用完，请明天再来。'
RESET_TEXT = '北京时间早上 8 点'


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS ai_quota(user_id INTEGER PRIMARY KEY REFERENCES users(id), daily INTEGER, factor REAL,
 paused INTEGER NOT NULL DEFAULT 0, until REAL, reason TEXT NOT NULL DEFAULT '', changed_by TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ai_quota_log(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), at REAL NOT NULL,
 changed_by TEXT NOT NULL, change TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ai_quota_log_user ON ai_quota_log(user_id, id);
CREATE TABLE IF NOT EXISTS ai_usage_kind(user_id INTEGER NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(user_id, day, kind));''')


def _today(now=None):
    return time.strftime('%Y-%m-%d', time.gmtime(now or time.time()))


def _days_back(n, now=None):
    t = now or time.time()
    return [time.strftime('%Y-%m-%d', time.gmtime(t - i * 86400)) for i in range(n)]


# ---------- the override ----------

def get(c, uid, now=None):
    """The account's override, or None: {daily, factor, paused, until, reason, by, updated, active}."""
    r = c.execute('SELECT daily, factor, paused, until, reason, changed_by, updated FROM ai_quota WHERE user_id=?', (uid,)).fetchone()
    if not r:
        return None
    now = now or time.time()
    return {'daily': r[0], 'factor': r[1], 'paused': bool(r[2]), 'until': r[3], 'reason': r[4], 'by': r[5], 'updated': r[6],
            'active': r[3] is None or r[3] > now}


def active(c, uid, now=None):
    o = get(c, uid, now)
    return o if o and o['active'] else None


def _log(c, uid, by, change, now):
    c.execute('INSERT INTO ai_quota_log(user_id, at, changed_by, change) VALUES(?,?,?,?)', (uid, now, by, json.dumps(change, ensure_ascii=False)))


def set(c, uid, by, reason, limit=None, factor=None, paused=False, until=None, now=None):  # noqa: A001 - the console's word
    """Give an account its own quota (the caller commits and keeps its admin log). limit: calls a day (1–DAILY_MAX);
    factor: times the usual ceiling (FACTOR_MIN–FACTOR_MAX); one of the two at most; paused: no AI for this account;
    until: when it ends (epoch, later than now, within a year), None = until changed. ValueError with the reason in
    Chinese when something is not right."""
    now = now or time.time()
    if not c.execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
        raise ValueError('账号不存在')
    by, reason = str(by or '').strip()[:40], str(reason or '').strip()
    if not by:
        raise ValueError('要写明是谁改的')
    if not reason or len(reason) > REASON_MAX:
        raise ValueError(f'要写原因（{REASON_MAX} 字以内）')
    if limit is not None and factor is not None:
        raise ValueError('每天次数和倍数只能填一个')
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= DAILY_MAX:
            raise ValueError(f'每天次数要在 1 到 {DAILY_MAX} 之间；要停用 AI 请选「暂停」')
    if factor is not None:
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not FACTOR_MIN <= factor <= FACTOR_MAX:
            raise ValueError(f'倍数要在 {FACTOR_MIN} 到 {FACTOR_MAX:g} 之间')
        factor = float(factor)
    if not isinstance(paused, bool):
        raise ValueError('暂停要填是或否')
    if limit is None and factor is None and not paused:
        raise ValueError('至少要改一项：每天次数、倍数或暂停')
    if until is not None:
        if isinstance(until, bool) or not isinstance(until, (int, float)) or not now < until <= now + UNTIL_MAX_DAYS * 86400:
            raise ValueError('到期时间要在今后一年以内')
        until = float(until)
    c.execute('INSERT INTO ai_quota(user_id, daily, factor, paused, until, reason, changed_by, updated) VALUES(?,?,?,?,?,?,?,?) '
              'ON CONFLICT(user_id) DO UPDATE SET daily=excluded.daily, factor=excluded.factor, paused=excluded.paused, until=excluded.until, '
              'reason=excluded.reason, changed_by=excluded.changed_by, updated=excluded.updated',
              (uid, limit, factor, int(paused), until, reason, by, now))
    _log(c, uid, by, {'daily': limit, 'factor': factor, 'paused': paused, 'until': until, 'reason': reason}, now)
    return get(c, uid, now)


def clear(c, uid, by, now=None):
    """Back to the usual quota (the caller commits). Returns whether there was an override."""
    now = now or time.time()
    n = c.execute('DELETE FROM ai_quota WHERE user_id=?', (uid,)).rowcount
    if n:
        _log(c, uid, str(by or '').strip()[:40] or '?', {'cleared': True}, now)
    return bool(n)


def history(c, uid, limit=20):
    return [{'at': r[0], 'by': r[1], 'change': json.loads(r[2])} for r in
            c.execute('SELECT at, changed_by, change FROM ai_quota_log WHERE user_id=? ORDER BY id DESC LIMIT ?', (uid, int(limit)))]


# ---------- the gates ----------

def _admin(c, uid):
    r = c.execute('SELECT admin FROM users WHERE id=?', (uid,)).fetchone()
    return bool(r and r[0])


def usual_limit():
    return __import__('chat_service').daily_limit('FLOW_AI_USER_DAILY_LIMIT')


def limit_for(c, uid, now=None):
    """(calls a day or None for no ceiling, where it comes from: 'admin' | 'override' | 'usual' | 'none')."""
    if _admin(c, uid):
        return None, 'admin'
    base, o = usual_limit(), active(c, uid, now)
    if o and o['daily']:
        return int(o['daily']), 'override'
    if o and o['factor']:
        return (max(1, round(base * o['factor'])), 'override') if base else (None, 'none')
    return (base, 'usual') if base else (None, 'none')


def paused(c, uid, now=None):
    o = active(c, uid, now)
    return bool(o and o['paused'])


def used(c, uid, day=None):
    r = c.execute('SELECT count FROM ai_usage WHERE user_id=? AND day=?', (uid, day or _today())).fetchone()
    return r[0] if r else 0


def note(c, uid, day, kind):
    """One call counted (in reserve, beside ai_usage), by task."""
    c.execute('INSERT INTO ai_usage_kind(user_id, day, kind, count) VALUES(?,?,?,1) ON CONFLICT(user_id, day, kind) DO UPDATE SET count=count+1',
              (uid, day, kind or 'other'))


def give_back(c, uid, kind, day=None):
    """A call that got no answer is not charged (run_job): both counts go down by one."""
    day = day or _today()
    c.execute('UPDATE ai_usage SET count=MAX(0, count-1) WHERE user_id=? AND day=?', (uid, day))
    c.execute('UPDATE ai_usage_kind SET count=MAX(0, count-1) WHERE user_id=? AND day=? AND kind=?', (uid, day, kind or 'other'))


# ---------- what learners and the consoles read ----------

LOW = 0.2  # under a fifth of the day's calls left: 'low' (B6: the page says so once, not in the way)


def _level(left, limit, stopped):
    if stopped:
        return 'out'
    return 'low' if limit and left is not None and left < LOW * limit else 'ok'


def brief(c, uid, now=None):
    """The cheap reading for every AI response (B6's X-Flow-AI-Quota header): {remaining, limit, level}, level 'ok',
    'low' (under LOW of the day's calls left) or 'out' (paused, or none left). The site's ceiling and the ¥10 stop are
    not looked at here (today() does): they are one sentence on the refused call itself."""
    limit, _ = limit_for(c, uid, now)
    left = None if limit is None else max(0, limit - used(c, uid, _today(now)))
    stopped = 'paused' if paused(c, uid, now) else 'user' if left == 0 else None
    return {'remaining': left, 'limit': limit, 'level': _level(left, limit, stopped)}


def header(c, uid, now=None):
    """X-Flow-AI-Quota: <remaining>/<limit>/<level>, empty numbers when there is no ceiling."""
    b = brief(c, uid, now)
    return f"{'' if b['remaining'] is None else b['remaining']}/{b['limit'] or ''}/{b['level']}"

def _label(kind):
    import ai_routes
    if kind == 'other':
        return '其他'
    return ai_routes.LABEL.get(kind) or (ai_routes.EXTRA.get(kind) or (kind,))[0]


def _by_kind(c, uid, days, total):
    rows = c.execute('SELECT kind, SUM(count) FROM ai_usage_kind WHERE user_id=? AND day IN (%s) GROUP BY kind HAVING SUM(count) > 0'
                     % ','.join('?' * len(days)), (uid, *days)).fetchall()
    out = sorted(({'kind': k, 'label': _label(k), 'count': n} for k, n in rows if k != 'other'), key=lambda x: -x['count'])
    rest = total - sum(x['count'] for x in out)
    if rest > 0:  # calls counted before tasks were (2026-11-26) and those marked other
        out.append({'kind': 'other', 'label': '其他', 'count': rest})
    return out


def today(c, uid, now=None):
    """For the learner (「我的 → 设置」): the numbers the gates use. limit None = no ceiling. stopped: why the next call
    would be refused (None, 'paused', 'user', 'site', 'day_full'); note: one line to show. The reason of a pause is not
    shown to the learner."""
    import ai_routes, chat_service as cs
    now = now or time.time()
    day = _today(now)
    n = used(c, uid, day)
    limit, source = limit_for(c, uid, now)
    left = None if limit is None else max(0, limit - n)
    o = active(c, uid, now)
    is_paused = bool(o and o['paused'])
    site = cs.site_limit(c)
    stopped = ('day_full' if ai_routes.day_full(c) else
               'site' if site and c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', (day,)).fetchone()[0] >= site else
               'paused' if is_paused else 'user' if left == 0 else None)
    line = {'day_full': cs.DAY_FULL, 'site': SITE_FULL, 'paused': PAUSED,
            'user': f'今天的 {limit} 次 AI 用完了，{RESET_TEXT}重置。'}.get(stopped) or (
        f'今天还能用 {left} 次 AI，{RESET_TEXT}重置。' if left is not None else '今天的 AI 不限次数。')
    reset = (int(now // 86400) + 1) * 86400
    return {'used': n, 'limit': limit, 'remaining': left, 'level': _level(left, limit, stopped), 'adjusted': source == 'override', 'paused': is_paused,
            'paused_until': o['until'] if is_paused else None, 'reset_at': reset, 'reset_text': RESET_TEXT,
            'by_kind': _by_kind(c, uid, [day], n), 'stopped': stopped, 'note': line}


def _unit_costs(c):
    """Average yuan a call, per task, over 30 days (ai_calls has no learner: an account's cost is its calls × these)."""
    import ai_routes
    s = ai_routes.summary(c, 30)
    per = {k['kind']: k['cost'] / k['calls'] for k in s['kinds'] if k['calls']}
    t = s['total']
    return per, (t['cost'] / t['calls'] if t['calls'] else 0.0)


def _sum(c, uid, days):
    return c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE user_id=? AND day IN (%s)' % ','.join('?' * len(days)), (uid, *days)).fetchone()[0]


def report(c, uid=None, limit=200, now=None):
    """For the consoles: one row a person, most used in 30 days first (accounts with an override always listed):
    {user_id, today, d7, d30, limit, source, paused, override, override_until, by_kind_30, cost_est_30, near_days_30,
    full_days_30, near_streak (days in a row up to today at LOW's other side, 80% of the ceiling or more; today short of it: 0)};
    with uid, that one person and by_kind for today, 7 and 30 days. cost_est is an estimate (calls × the task's average)."""
    now = now or time.time()
    d1, d7, d30 = _days_back(1, now), _days_back(7, now), _days_back(30, now)
    if uid is not None:
        ids = [uid]
    else:
        ids = [r[0] for r in c.execute('SELECT user_id FROM ai_usage WHERE user_id > 0 AND day IN (%s) GROUP BY user_id ORDER BY SUM(count) DESC LIMIT ?'
                                       % ','.join('?' * len(d30)), (*d30, int(limit)))]
        ids += [r[0] for r in c.execute('SELECT user_id FROM ai_quota') if r[0] not in ids]
    per, avg = _unit_costs(c)
    out = []
    for u in ids:
        t30 = _sum(c, u, d30)
        lim, source = limit_for(c, u, now)
        kinds30 = _by_kind(c, u, d30, t30)
        by_day = dict(c.execute('SELECT day, count FROM ai_usage WHERE user_id=? AND day IN (%s)' % ','.join('?' * len(d30)), (u, *d30)).fetchall())
        daily = list(by_day.values())
        streak = 0
        for d in d30:  # today first
            if not lim or by_day.get(d, 0) < 0.8 * lim:
                break
            streak += 1
        o = get(c, u, now)
        row = {'user_id': u, 'today': _sum(c, u, d1), 'd7': _sum(c, u, d7), 'd30': t30, 'limit': lim, 'source': source,
               'paused': paused(c, u, now), 'override': o, 'override_until': o['until'] if o else None, 'by_kind_30': kinds30,
               'cost_est_30': round(sum(k['count'] * per.get(k['kind'], avg) for k in kinds30), 4),
               'near_days_30': sum(1 for n in daily if lim and 0.8 * lim <= n < lim), 'full_days_30': sum(1 for n in daily if lim and n >= lim),
               'near_streak': streak}
        if uid is not None:
            row['by_kind'] = {'today': _by_kind(c, u, d1, row['today']), 'd7': _by_kind(c, u, d7, row['d7']), 'd30': kinds30}
        out.append(row)
    return out
