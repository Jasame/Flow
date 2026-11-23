"""Operator API for xmc.hk/flow/ (read-mostly; the writes: a one-time password-reset link, hiding a survey answer,
generating today's news material).

Listens only on 127.0.0.1:FLOW_ADMIN_PORT. The sole route in is the xmc.hk
nginx location /flow/api/, which sits behind Cloudflare Access; flow.jasa.hk
never proxies here. Mutations additionally require the X-Requested-With: xmc
header, which a cross-site form or image cannot send.

r20: this console is the only place for operator functions (the learner site has none). Two roles, by the email
Cloudflare Access signed in: FLOW_ADMIN_EMAILS (comma-separated) are 管理员; anyone else who gets through Access may
only look at the numbers (只看数据). Without FLOW_ADMIN_EMAILS everyone is 管理员, as before. What a 管理员 changes or
exports is written to the operator log.
"""
import datetime, json, os, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

import survey_service as survey

PREFIX = '/flow/api'


def server_label():
    """Which server this Flow runs on, shown in the xmc.hk console (FLOW_SERVER_LABEL, e.g. 香港服务器; else the host name)."""
    return os.getenv('FLOW_SERVER_LABEL', '').strip() or __import__('socket').gethostname()


# 只看数据 sees the numbers; 管理员 also sees people (accounts, answers in full, error traces) and may change things.
VIEWER_GET = {'/me', '/overview', '/learning', '/survey/definition', '/survey/summary', '/releases', '/compare'}
ADMIN_GET = {'/users', '/survey/responses', '/survey/export.csv', '/errors', '/log'}
ROLE_LABEL = {'admin': '管理员', 'viewer': '只看数据'}


def operator(headers):
    """Who is asking (the email Cloudflare Access signed in) and the role that email has."""
    email = (headers.get('Cf-Access-Authenticated-User-Email') or '').strip().lower()[:200]
    admins = {e.strip().lower() for e in os.getenv('FLOW_ADMIN_EMAILS', '').split(',') if e.strip()}
    role = 'admin' if not admins or email in admins else 'viewer'
    return {'email': email, 'role': role, 'label': ROLE_LABEL[role], 'roles_set': bool(admins)}


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS flow_admin_log(id INTEGER PRIMARY KEY, created REAL NOT NULL, email TEXT NOT NULL, '
              'role TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL DEFAULT "", detail TEXT NOT NULL DEFAULT "")')
    c.execute('CREATE TABLE IF NOT EXISTS flow_releases(tag TEXT PRIMARY KEY, commit_sha TEXT NOT NULL DEFAULT "", at REAL NOT NULL)')
    # Taps on a few entry points of the learning site, counted per day: no account, no address, only how many.
    c.execute('CREATE TABLE IF NOT EXISTS ui_taps(day TEXT NOT NULL, key TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, key))')


def log_action(c, op, action, target='', detail=''):
    c.execute('INSERT INTO flow_admin_log(created, email, role, action, target, detail) VALUES(?,?,?,?,?,?)',
              (time.time(), op['email'] or '（未知）', op['role'], action, str(target)[:200], str(detail)[:300]))
    c.commit()


ACTION_LABEL = {'reset-link': '生成重设密码链接', 'survey-hide': '隐藏问卷回答', 'survey-show': '恢复问卷回答',
                'survey-export': '导出问卷 CSV', 'daily-run': '生成今日热点'}


def operator_log(c, limit=200):
    rows = c.execute('SELECT created, email, role, action, target, detail FROM flow_admin_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    return {'items': [{**dict(r), 'action_label': ACTION_LABEL.get(r['action'], r['action']), 'role_label': ROLE_LABEL.get(r['role'], r['role'])}
                      for r in rows]}


def note_release(c, st):
    """Remember a release the first time its deploy status says it is live (the before/after view needs the dates)."""
    if not isinstance(st, dict) or st.get('result') not in ('DEPLOYED', 'NOTHING_TO_DO') or not st.get('tag'):
        return
    try:
        at = datetime.datetime.fromisoformat(str(st.get('finished') or st.get('started'))).timestamp()
    except ValueError:
        return
    c.execute('INSERT OR IGNORE INTO flow_releases(tag, commit_sha, at) VALUES(?,?,?)', (str(st['tag'])[:40], str(st.get('commit', ''))[:40], at))
    c.commit()


def releases(c):
    try:
        import app
        note_release(c, json.loads((app.DATA / 'deploy-status.json').read_text()))
    except (OSError, ValueError):
        pass
    return {'items': [dict(r) for r in c.execute('SELECT tag, commit_sha, at FROM flow_releases ORDER BY at DESC LIMIT 30')]}


def compare(c, at, days=14):
    """The days before a release against the days after it, as daily averages (the after side may still be short)."""
    import next_service as nx
    now = time.time()
    days = max(3, min(60, int(days)))
    after_end = min(now, at + days * 86400)
    sides = {'before': (at - days * 86400, at), 'after': (at, after_end)}
    out = {'at': at, 'days': days, 'after_days': round(max(0, after_end - at) / 86400, 1), 'metrics': [], 'taps': []}
    day_of = lambda t: datetime.datetime.fromtimestamp(t, nx.TZ).date()

    def per_day(sql, a, b):
        return c.execute(sql, (a, b)).fetchone()[0] / max(1, (b - a) / 86400)

    def active(a, b):
        days_seen = {}
        for uid, t in c.execute('SELECT user_id, created FROM next_progress WHERE created>=? AND created<? UNION ALL '
                                'SELECT user_id, created FROM next_reviews WHERE created>=? AND created<?', (a, b, a, b)):
            days_seen.setdefault(day_of(t), set()).add(uid)
        return sum(len(v) for v in days_seen.values()) / max(1, (b - a) / 86400)

    def came_back(a, b):
        # Of those who started in this window, the share who came back on another day within a week.
        joined = back = 0
        for uid, created in c.execute('SELECT user_id, created FROM next_profiles WHERE created>=? AND created<?', (a, b)).fetchall():
            joined += 1
            start = day_of(created)
            back += any(1 <= (day_of(t) - start).days <= 7 for (t,) in c.execute(
                'SELECT created FROM next_progress WHERE user_id=? AND created>? UNION ALL SELECT created FROM next_reviews WHERE user_id=? AND created>?',
                (uid, created, uid, created)))
        return round(100 * back / joined) if joined else None

    rows = [('active', '日均学习人数', lambda a, b: active(a, b)),
            ('joined', '日均新学员', lambda a, b: per_day('SELECT COUNT(*) FROM next_profiles WHERE created>=? AND created<?', a, b)),
            ('reviews', '日均复习次数', lambda a, b: per_day('SELECT COUNT(*) FROM next_reviews WHERE created>=? AND created<?', a, b)),
            ('back7', '新学员一周内回来的比例（%）', came_back)]
    rows += [(f'step-{s}', f'日均完成「{l}」', (lambda s: lambda a, b: per_day(f"SELECT COUNT(*) FROM next_progress WHERE step='{s}' AND created>=? AND created<?", a, b))(s))
             for s, l in (('listen', '听'), ('read', '读'), ('check', '理解'), ('output', '用出来'))]
    for key, label, f in rows:
        v = {side: f(a, b) if b > a else None for side, (a, b) in sides.items()}
        v = {k: (round(x, 1) if isinstance(x, float) else x) for k, x in v.items()}
        out['metrics'].append({'key': key, 'label': label, **v})
    # Taps are kept per day, so the release day itself would fall on both sides: it is left out of both.
    one_day = datetime.timedelta(days=1)
    span = {'before': (day_of(at - days * 86400).isoformat(), (day_of(at) - one_day).isoformat()),
            'after': ((day_of(at) + one_day).isoformat(), day_of(after_end).isoformat())}
    for key, n_before, n_after in c.execute(
            'SELECT key, SUM(CASE WHEN day BETWEEN ? AND ? THEN n ELSE 0 END), SUM(CASE WHEN day BETWEEN ? AND ? THEN n ELSE 0 END) '
            'FROM ui_taps GROUP BY key ORDER BY 3 DESC', (*span['before'], *span['after'])):
        out['taps'].append({'key': key, 'label': TAP_LABEL.get(key, key), 'before': n_before or 0, 'after': n_after or 0})
    return out


# The entry points the learning site counts (next_service.tap accepts only these), and what each one is.
TAP_LABEL = {
    'notice-login': '今日 · 提醒：登录', 'notice-level': '今日 · 提醒：换水平', 'notice-mail': '今日 · 提醒：绑定邮箱', 'notice-guide': '今日 · 提醒：看指南',
    'home-resume': '今日 · 继续上次', 'home-news': '今日 · 热点', 'home-pick': '今日 · 也可以读', 'home-more': '今日 · 更多材料',
    'practice-map': '练习 · 知识图谱大卡', 'practice-tip': '练习 · 今天建议',
    'words-plan': '单词 · 词书计划', 'words-confuse': '单词 · 辨析', 'words-mistake': '单词 · 错题本', 'words-test': '单词 · 测词汇量', 'words-import': '单词 · 导入',
    'words-stats': '单词 · 展开统计', 'read-gains': '读 · 展开这篇的收获', 'listen-preread': '听 · 展开读前生词',
    'study-origin': '学习页 · 看来源', 'notice-install': '今日 · 提醒：放到桌面',
    'me-radar': '我的 · 能力雷达', 'me-growth': '我的 · 我的进步', 'me-report': '我的 · 这周的报告', 'me-mistake': '我的 · 错题本',
    'me-level': '我的 · 学习目标和水平', 'me-voice': '我的 · 朗读声音', 'me-remind': '我的 · 每天提醒', 'me-install': '我的 · 添加到桌面',
    'me-guide': '我的 · 操作指南', 'me-survey': '我的 · 匿名问卷',
    'beta-main': '内测版 · 去正式版',
}


def overview(c):
    import chat_service
    now = time.time()
    day = time.strftime('%Y-%m-%d', time.gmtime(now))
    week = [time.strftime('%Y-%m-%d', time.gmtime(now - i * 86400)) for i in range(7)]
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    return {
        'users': q('SELECT COUNT(*) FROM users'),
        'admins': q('SELECT COUNT(*) FROM users WHERE admin=1'),
        'active_7d': q('SELECT COUNT(DISTINCT user_id) FROM learning_events WHERE created>?', now - 7 * 86400),
        'active_1d': q('SELECT COUNT(DISTINCT user_id) FROM learning_events WHERE created>?', now - 86400),
        'events_7d': q('SELECT COUNT(*) FROM learning_events WHERE created>?', now - 7 * 86400),
        'ai': {
            'today': q('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', day),
            'week': [{'day': d, 'count': q('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', d)} for d in reversed(week)],
            'site_limit': chat_service.daily_limit('FLOW_AI_DAILY_LIMIT'),
            'user_limit': chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'),
            'users_at_limit': (q('SELECT COUNT(*) FROM ai_usage WHERE day=? AND user_id>0 AND count>=?', day, chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'))
                               if chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT') else 0),
            'model': os.getenv('FLOW_AI_MODEL', ''),
        },
        'survey_responses': q('SELECT COUNT(*) FROM survey_responses WHERE survey=? AND hidden=0', survey.SURVEY_ID),
        'backup': backup_status(), 'daily': __import__('daily_service').status(c),
        'server': server_label(),
        'generated_at': now,
    }


def backup_status():
    """The last database backup (ops.py writes data/backup-status.json); it used to be on the classic site."""
    try:
        import app
        return json.loads((app.DATA / 'backup-status.json').read_text())
    except (OSError, ValueError):
        return None


def learning(c):
    """Flow learning data for the operator dashboard: activity, retention, the study funnel, vocabulary and AI use.

    Days are Asia/Shanghai calendar days. A learner is "active" on a day with any study step or review."""
    import datetime
    import next_service as nx
    now = time.time()
    tz = nx.TZ
    day_of = lambda t: datetime.datetime.fromtimestamp(t, tz).date()
    today = day_of(now)
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    since = now - 45 * 86400
    acts = {}
    for uid, t in c.execute('SELECT user_id, created FROM next_progress WHERE created>? UNION ALL '
                            'SELECT user_id, created FROM next_reviews WHERE created>?', (since, since)):
        acts.setdefault(uid, set()).add(day_of(t))
    days14 = [today - datetime.timedelta(days=i) for i in range(13, -1, -1)]
    active = [{'day': d.isoformat(), 'count': sum(1 for ds in acts.values() if d in ds)} for d in days14]
    within = lambda n: sum(1 for ds in acts.values() if any((today - d).days < n for d in ds))
    # Retention by onboarding day (Flow profile created): came back the next day / within the first week.
    cohort = {'joined': 0, 'd1': 0, 'week': 0}
    for uid, created in c.execute('SELECT user_id, created FROM next_profiles WHERE created BETWEEN ? AND ?', (now - 30 * 86400, now - 86400)):
        start = day_of(created or now)
        ds = acts.get(uid, set())
        cohort['joined'] += 1
        cohort['d1'] += (start + datetime.timedelta(days=1)) in ds
        cohort['week'] += any(1 <= (d - start).days <= 7 for d in ds)
    week_ago = now - 7 * 86400
    funnel = {s: q('SELECT COUNT(*) FROM next_progress WHERE step=? AND created>?', s, week_ago) for s in nx.STEPS}
    ratings = dict(c.execute('SELECT rating, COUNT(*) FROM next_reviews WHERE created>? GROUP BY rating', (week_ago,)).fetchall())
    mature = c.execute("SELECT COUNT(*), SUM(rating!='again') FROM next_reviews WHERE created>? AND elapsed>=1 AND rating IN ('again','hard','good','easy')",
                       (week_ago,)).fetchone()
    books = dict(c.execute('SELECT book, COUNT(*) FROM next_vocab_plans GROUP BY book').fetchall())
    added = dict(c.execute('SELECT source, COUNT(*) FROM next_cards WHERE created>? GROUP BY source', (week_ago,)).fetchall())
    ai = dict(c.execute("SELECT kind, COUNT(*) FROM lab_jobs WHERE status='complete' AND updated>? AND kind LIKE 'next-%' GROUP BY kind", (week_ago,)).fetchall())
    top = [{'id': pid, 'learners': n} for pid, n in c.execute(
        'SELECT pack, COUNT(DISTINCT user_id) n FROM next_progress WHERE created>? GROUP BY pack ORDER BY n DESC LIMIT 8', (week_ago,))]
    titles = {p['id']: p['title'] for p in __import__('content_v50').v5_materials()}
    for t in top:
        t['title'] = titles.get(t['id'], t['id'])
    return {
        'active_today': active[-1]['count'], 'active_7d': within(7), 'active_30d': within(30), 'active_days': active,
        'profiles': q('SELECT COUNT(*) FROM next_profiles'), 'cohort': cohort,
        'funnel_7d': funnel, 'materials': len(titles),
        'reviews_7d': sum(v for k, v in ratings.items() if k in ('again', 'hard', 'good', 'easy')), 'ratings_7d': ratings,
        'true_retention': round(mature[1] / mature[0], 3) if mature and mature[0] else None, 'mature_reviews_7d': mature[0] if mature else 0,
        'vocab_plans': books, 'words_added_7d': added, 'reminders_on': q('SELECT COUNT(*) FROM next_reminders WHERE enabled=1'),
        'cards_total': q('SELECT COUNT(*) FROM next_cards'), 'ai_7d': ai, 'top_materials_7d': top, 'generated_at': now,
    }


class AdminHandler(BaseHTTPRequestHandler):
    server_version = 'FlowAdmin'

    def log_message(self, *args):
        pass

    def _send(self, obj, status=200, body=None, mime='application/json; charset=utf-8', extra=None):
        body = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        import app
        url = urlsplit(self.path)
        path, qs = url.path, parse_qs(url.query)
        one = lambda k, d='': (qs.get(k) or [d])[0]
        if not path.startswith(PREFIX + '/'):
            return self._send({'error': '接口不存在'}, 404)
        path = path[len(PREFIX):]
        op = operator(self.headers)
        with app.db() as c:
            schema(c)
            if method == 'GET':
                if path not in VIEWER_GET | ADMIN_GET:
                    return self._send({'error': '接口不存在'}, 404)
                if path in ADMIN_GET and op['role'] != 'admin':
                    return self._send({'error': '需要管理员权限：你现在的身份是「只看数据」'}, 403)
                if path == '/me':
                    return self._send({**op, 'server': server_label()})
                if path == '/overview':
                    return self._send(overview(c))
                if path == '/learning':
                    return self._send(learning(c))
                if path == '/releases':
                    return self._send(releases(c))
                if path == '/compare':
                    at = one('at')
                    when = float(at) if at.replace('.', '', 1).isdigit() else datetime.datetime.fromisoformat(at).replace(tzinfo=__import__('next_service').TZ).timestamp()
                    return self._send(compare(c, when, int(one('days', '14') or 14)))
                if path == '/errors':
                    return self._send(__import__('ops_errors').recent(c))
                if path == '/users':
                    return self._send(__import__('account_service').admin_users(c, one('q')))
                if path == '/log':
                    return self._send(operator_log(c))
                if path == '/survey/definition':
                    return self._send(survey.SURVEY)
                if path == '/survey/summary':
                    filters = {k: one(k) for k in ('role', 'level', 'flow')}
                    return self._send(survey.summary(c, filters))
                if path == '/survey/responses':
                    return self._send(survey.responses(c, int(one('page', '1') or 1), 20, one('q')[:100]))
                if path == '/survey/export.csv':
                    name = f"flow-survey-{time.strftime('%Y%m%d')}.csv"
                    log_action(c, op, 'survey-export', name)
                    return self._send(None, body=survey.export_csv(c), mime='text/csv; charset=utf-8',
                                      extra={'Content-Disposition': f'attachment; filename="{name}"'})
            elif method == 'POST':
                if self.headers.get('X-Requested-With') != 'xmc':
                    return self._send({'error': '缺少请求标记'}, 403)
                if op['role'] != 'admin':
                    return self._send({'error': '需要管理员权限：你现在的身份是「只看数据」'}, 403)
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 2000:
                    return self._send({'error': '请求大小不正确'}, 400)
                data = json.loads(self.rfile.read(length))
                if path == '/users/reset-link':
                    # A one-time link for a learner who forgot the password and has no email bound. The log keeps who
                    # asked for which account, never the link.
                    body, status = __import__('account_service').admin_link(c, data.get('user'))
                    log_action(c, op, 'reset-link', data.get('user', ''), '已生成' if status == 200 else body.get('error', status))
                    return self._send(body, status)
                if path == '/survey/hide':
                    hidden = bool(data.get('hidden', True))
                    body, status = survey.set_hidden(c, int(data['id']), hidden)
                    if status == 200:
                        log_action(c, op, 'survey-hide' if hidden else 'survey-show', f"#{int(data['id'])}")
                    return self._send(body, status)
                if path == '/daily/run':
                    # Today's news material, made now instead of waiting for the timer (it used to be on the classic site).
                    def run():
                        with app.db() as conn:
                            __import__('daily_service').run(conn)
                    threading.Thread(target=run, daemon=True).start()
                    log_action(c, op, 'daily-run', time.strftime('%Y-%m-%d'))
                    return self._send({'ok': True, 'message': '已开始生成，几分钟后刷新查看；今天已经成功生成过的不会重做。'}, 202)
        return self._send({'error': '接口不存在'}, 404)

    def do_GET(self):
        try:
            self._route('GET')
        except (ValueError, KeyError, TypeError):
            self._send({'error': '参数不正确'}, 400)
        except Exception:
            self._send({'error': '服务暂时异常'}, 500)

    def do_POST(self):
        try:
            self._route('POST')
        except (ValueError, KeyError, TypeError):
            self._send({'error': '参数不正确'}, 400)
        except Exception:
            self._send({'error': '服务暂时异常'}, 500)


def start():
    """Start the operator API when FLOW_ADMIN_PORT is set. Always loopback-only."""
    port = int(os.getenv('FLOW_ADMIN_PORT', '0') or 0)
    if not port:
        return None
    server = ThreadingHTTPServer(('127.0.0.1', port), AdminHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name='flow-admin', daemon=True).start()
    print('Flow admin listening', server.server_address, flush=True)
    return server
