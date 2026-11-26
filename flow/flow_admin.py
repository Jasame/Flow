"""Operator API for xmc.hk/flow/. Reads: the numbers (概览, 学习, 留存漏斗, 发版对比, 打开速度, 问卷, 材料, 词书和考试, AI),
and for 管理员 the people (学员 one by one, answers, feedback, error traces, the operator log, CSV files). Writes
(管理员 only): accounts (reset link, stop / restore, sign out everywhere, level, daily new words, 员工账号), materials
(off the lists and back), today's news, the AI limits, 例句预生成, 公告, survey answers and feedback status. The data
is in console_data.py, the changes in console_ops.py (r26).

Listens only on 127.0.0.1:FLOW_ADMIN_PORT. The sole route in is the xmc.hk
nginx location /flow/api/, which sits behind Cloudflare Access; flow.jasa.hk
never proxies here. Mutations additionally require the X-Requested-With: xmc
header, which a cross-site form or image cannot send.

r20: this console is the only place for operator functions (the learner site has none). Two roles, by the email
Cloudflare Access signed in: FLOW_ADMIN_EMAILS (comma-separated) are 管理员; anyone else who gets through Access may
only look at the numbers (只看数据). Without FLOW_ADMIN_EMAILS everyone is 管理员, as before. What a 管理员 changes or
exports is written to the operator log.
"""
import datetime, json, os, re, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

import survey_service as survey

PREFIX = '/flow/api'
# One console page and one API for both sites (2026-11-26, the owner: 「内测后台和正式版后台都要完善，要区分开」): 语流's
# console is xmc.hk/flow/, the 内测版's xmc.hk/flow-beta/ (each nginx location reaches its own site's loopback admin
# port). The API answers under either prefix; which site it is comes from FLOW_CHANNEL (/me: env), never from the path.
PREFIXES = (PREFIX, '/flow-beta/api')


def site():
    """Which site this console runs for: env 'beta' (the 内测版, FLOW_CHANNEL=beta) or 'prod' (语流), and its address, so
    the page can say so on every tab and ask before a change on 语流's (xmc-admin/admin.js)."""
    import app
    host = os.getenv('FLOW_PUBLIC_URL', '').strip().rstrip('/').split('//')[-1] or ('flow.jasa.hk' if app.CHANNEL == 'beta' else 'flowlang.cn')
    return {'env': app.CHANNEL, 'site': host}


def server_label():
    """Which server this Flow runs on, shown in the xmc.hk console (FLOW_SERVER_LABEL, e.g. 香港服务器; else the host name)."""
    return os.getenv('FLOW_SERVER_LABEL', '').strip() or __import__('socket').gethostname()


# 只看数据 sees the numbers; 管理员 also sees people (accounts, answers in full, error traces) and may change things.
VIEWER_GET = {'/me', '/overview', '/learning', '/survey/definition', '/survey/summary', '/releases', '/compare', '/speed',
              '/funnel', '/cohorts', '/content', '/books', '/ai', '/ai/samples', '/tasks', '/announcements'}
ADMIN_GET = {'/users', '/survey/responses', '/survey/export.csv', '/errors', '/log', '/feedback', '/feedback/image',
             '/learners', '/learner', '/export/learners.csv', '/export/materials.csv', '/export/ai.csv',
             '/classes', '/class', '/export/classes.csv', '/teacher-links', '/beta-invites', '/beta-tests', '/ai-people', '/word-extras'}
CSV_EXPORTS = {'/export/learners.csv': ('learners', '学员'), '/export/materials.csv': ('materials', '材料'), '/export/ai.csv': ('ai', 'AI 用量'),
               '/export/classes.csv': ('classes', '班级试用人次')}
ROLE_LABEL = {'admin': '管理员', 'viewer': '只看数据', 'system': '自动'}  # system: the site itself (privacy_service.purge_paused)


def operator(headers):
    """Who is asking (the email Cloudflare Access signed in) and the role that email has. With FLOW_ACCESS_AUD and
    FLOW_ACCESS_TEAM set, the email comes from Access's signed token (access_check.py) and a request without a valid
    one gets None (403); without them, the header is read as before."""
    email = (headers.get('Cf-Access-Authenticated-User-Email') or '').strip().lower()[:200]
    check = __import__('access_check').settings()
    if check:
        email = __import__('access_check').verify(headers.get('Cf-Access-Jwt-Assertion'), *check)
        if not email:
            return None
    admins = {e.strip().lower() for e in os.getenv('FLOW_ADMIN_EMAILS', '').split(',') if e.strip()}
    role = 'admin' if not admins or email in admins else 'viewer'
    return {'email': email, 'role': role, 'label': ROLE_LABEL[role], 'roles_set': bool(admins)}


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS flow_admin_log(id INTEGER PRIMARY KEY, created REAL NOT NULL, email TEXT NOT NULL, '
              'role TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL DEFAULT "", detail TEXT NOT NULL DEFAULT "")')
    c.execute('CREATE TABLE IF NOT EXISTS flow_releases(tag TEXT PRIMARY KEY, commit_sha TEXT NOT NULL DEFAULT "", at REAL NOT NULL)')
    # Taps on a few entry points of the learning site, counted per day: no account, no address, only how many.
    c.execute('CREATE TABLE IF NOT EXISTS ui_taps(day TEXT NOT NULL, key TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, key))')
    __import__('feedback_service').schema(c)  # problem reports from the learning site (问题反馈)
    __import__('field_service').schema(c)  # page errors and opening times the browsers report
    __import__('console_ops').schema(c)  # materials off the lists, 公告 (r26)
    __import__('class_service').schema(c)  # 班级试用: classes, who is in which (2026-11-24)
    __import__('teacher_service').schema(c)  # 老师账号 and the one-use 老师注册链接 (2026-11-26)
    __import__('beta_invites').schema(c)  # 内测版邀请码 (2026-11-26)
    __import__('beta_tools').schema(c)  # 内测版的测试账号 (2026-11-26)


WX_KIND = {'colloc': '常用搭配', 'near': '近义、易混词'}


def word_extras_list(c, days):
    """GET /word-extras?days=7|30|0 (管理员 only): the AI 常用搭配和近义、易混词 learners marked 「这条不对」, most learners
    first, no names (word_extras.reported); the ones taken down here say so and can go back."""
    import word_extras as wx
    days = 30 if str(days) == '30' else 0 if str(days) == '0' else 7
    rows = wx.reported(c, time.time() - days * 86400 if days else None)
    for r in rows:
        r['kind_label'] = WX_KIND.get(r['kind'], r['kind'])
    return {'days': days, 'items': rows}


def word_extras_post(c, path, data, op, who):
    """POST /word-extras/take-down {id, why} and /word-extras/put-back {id}, in the operator log."""
    import word_extras as wx
    try:
        xid = int(data.get('id'))
    except (TypeError, ValueError):
        return {'error': '参数不正确'}, 400
    row = c.execute('SELECT norm, kind, en, zh, hidden FROM vocab_extras WHERE id=?', (xid,)).fetchone() if \
        c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vocab_extras'").fetchone() else None
    if not row:
        return {'error': '没有找到这一条'}, 404
    target = f"{row[0]} · {WX_KIND.get(row[1], row[1])}：{row[2]} {row[3] or ''}".strip() + f' #{xid}'
    if path.endswith('take-down'):
        if row[4]:  # hidden already (taken down here, or by the AI review): nothing to take down, and the review's own
            # reason is never replaced by a console one (put_back would then show it again; B7 #443 guards the same)
            return {'error': '这一条已经藏起来了（审稿时就藏了，或者之前下架过），不用再下架'}, 409
        why = re.sub(r'\s+', ' ', str(data.get('why') or '')).strip()
        if not why or len(why) > 120:
            return {'error': '写一句为什么下架（120 字以内）', 'field': 'why'}, 400
        changed = wx.take_down(c, xid, why, who)
        c.commit()
        if changed:
            log_action(c, op, 'extra-down', target, why)
        return {'ok': True, 'changed': bool(changed)}, 200
    changed = wx.put_back(c, xid, who)
    c.commit()
    if not changed:
        return {'error': '这一条不是在后台下架的（是审稿时就藏起来的），不能在这里放回'}, 409
    log_action(c, op, 'extra-up', target)
    return {'ok': True, 'changed': True}, 200


def harmony_link(c, admin):
    """The 内测版's 鸿蒙内测链接 for the console: the link, its domain, and when it was last saved (the operator log: the
    settings file's own time is for all its keys)."""
    co = __import__('console_ops')
    last = c.execute("SELECT created, email FROM flow_admin_log WHERE action='harmony-link' ORDER BY id DESC LIMIT 1").fetchone()
    return {'url': co.harmony_test_url(), 'host': co.harmony_test_host(),
            'saved': ({'at': last[0], **({'by': last[1]} if admin else {})} if last else None)}


QUOTA_DAYS = (0, 1, 7, 30, 90)  # how long a quota of its own lasts; 0: until changed


def quota_text(o):
    """An override in a few words, for the operator log."""
    what = '暂停 AI' if o['paused'] else f"每天 {o['daily']} 次" if o['daily'] else f"普通上限的 {o['factor']:g} 倍"
    until = datetime.datetime.fromtimestamp(o['until'], __import__('next_service').TZ).strftime('%Y-%m-%d %H:%M') if o['until'] else '一直有效'
    return f"{what}，{until}；原因：{o['reason']}"


def ai_quota_post(c, path, data, op, who):
    """POST /learner/ai-quota {id, mode: daily | factor | pause, value, days, reason} and /learner/ai-quota/clear {id}:
    an account's AI quota of its own (ai_quota, B7 #405), in the operator log. The reason is facts only: the learner's
    export shows it (the page does not)."""
    import ai_quota, console_data as cd, console_ops as co
    try:
        u = c.execute('SELECT * FROM users WHERE id=?', (int(data.get('id')),)).fetchone()
    except (TypeError, ValueError):
        u = None
    if not u:
        return {'error': '没有找到这个学员'}, 404
    if path.endswith('/clear'):
        if ai_quota.clear(c, u['id'], who):
            c.commit()
            log_action(c, op, 'ai-quota-clear', co.target(u))
        return {'ok': True, 'quota': cd.ai_quota_view(c, u['id'])}, 200
    mode, raw = data.get('mode'), data.get('value')
    try:
        days = int(data.get('days') or 0)
    except (TypeError, ValueError):
        days = -1
    if days not in QUOTA_DAYS:
        return {'error': '到期时间请从选项里选', 'field': 'days'}, 400
    try:
        kw = ({'limit': int(raw)} if mode == 'daily' else {'factor': float(raw)} if mode == 'factor' else {'paused': True} if mode == 'pause' else None)
    except (TypeError, ValueError):
        return {'error': '每天次数或倍数要填数字', 'field': 'value'}, 400
    if kw is None:
        return {'error': '选一种：每天次数、倍数或暂停 AI', 'field': 'mode'}, 400
    try:
        o = ai_quota.set(c, u['id'], who, data.get('reason'), until=time.time() + days * 86400 if days else None, **kw)
    except ValueError as e:
        c.rollback()
        return {'error': str(e), 'field': 'reason' if '原因' in str(e) else 'value'}, 400
    c.commit()
    log_action(c, op, 'ai-quota', co.target(u), quota_text(o))
    return {'ok': True, 'quota': cd.ai_quota_view(c, u['id'])}, 200


def log_action(c, op, action, target='', detail=''):
    c.execute('INSERT INTO flow_admin_log(created, email, role, action, target, detail) VALUES(?,?,?,?,?,?)',
              (time.time(), op['email'] or '（未知）', op['role'], action, str(target)[:200], str(detail)[:300]))
    c.commit()


ACTION_LABEL = {'reset-link': '生成重设密码链接', 'survey-hide': '隐藏问卷回答', 'survey-show': '恢复问卷回答',
                'survey-export': '导出问卷 CSV', 'daily-run': '生成今日一读', 'feedback-done': '标记反馈已处理',
                'feedback-reopen': '重新打开反馈',
                # r26
                'account-disable': '停用账号', 'account-enable': '恢复账号', 'account-signout': '退出所有设备',
                'account-staff-on': '设为员工账号', 'account-staff-off': '取消员工账号',
                'account-teacher-on': '设为老师账号', 'account-teacher-off': '取消老师账号', 'account-level': '改水平',
                'account-daily-new': '改每日新词', 'material-hide': '下架材料', 'material-show': '恢复材料',
                'daily-again': '重新生成今日一读', 'ai-limits': '改 AI 额度', 'examples-start': '开始例句预生成',
                'examples-stop': '停止例句预生成', 'announce': '发布公告', 'announce-end': '结束公告', 'export': '导出 CSV',
                # 班级试用
                'class-create': '新建班级', 'class-rename': '班级改名', 'class-teacher': '换班级老师', 'class-code': '换邀请码',
                'class-stop': '停用班级', 'class-start': '重新启用班级',
                'teacher-link': '生成老师注册链接', 'teacher-link-revoke': '作废老师注册链接',
                'invite-create': '生成内测版邀请码', 'harmony-link': '改鸿蒙内测链接', 'ai-quota': '调整 AI 额度', 'extra-down': '下架单词搭配', 'extra-up': '放回单词搭配', 'ai-quota-clear': '恢复普通 AI 额度', 'invite-revoke': '作废内测版邀请码',
                'test-account': '造测试账号', 'test-reset': '重置测试数据（删掉全部测试账号）',
                'ai-routes': '改任务用的模型', 'ai-budget': '改 AI 预算和评测', 'ai-redo': '让 AI 重写一条内容',
                'account-purge': '删除暂停满 30 天的账号', 'account-purge-report': '暂停满 30 天的账号（只报告，没删）',
                'account-purge-held': '暂停满 30 天的账号（备份不在，没删）'}


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
    'home-sprint': '今日 · 考试倒计时', 'home-remind-once': '今日 · 计划完成后约复习时间', 'me-exam': '我的 · 我的考试', 'exam-goal': '考试练习 · 设定考试', 'exam-pace': '考试练习 · 按倒计时改每天新词',
    'exam-type': '考试练习 · 题型专练',
    'notice-login': '今日 · 提醒：登录', 'notice-level': '今日 · 提醒：换水平', 'notice-mail': '今日 · 提醒：绑定邮箱', 'notice-guide': '今日 · 提醒：看指南',
    'home-resume': '今日 · 继续上次', 'home-news': '今日 · 今日一读', 'home-mine': '今日 · 我的材料', 'home-start': '今日 · 开始今天的练习', 'today-view-list': '今日 · 换成列表', 'today-view-cards': '今日 · 换成卡片', 'today-edit': '今日 · 调整顺序', 'today-edit-done': '今日 · 调整顺序 · 完成', 'home-pick': '今日 · 也可以读', 'home-more': '今日 · 更多材料',
    'practice-tip': '练习 · 今天建议',
    'practice-review-other': '练习 · 错题和句型复习',  # 练习 → 复习 (49-practice.js)
    'words-plan': '单词 · 词书计划', 'words-confuse': '单词 · 辨析', 'words-mistake': '单词 · 错题本', 'words-test': '单词 · 测词汇量', 'words-import': '单词 · 导入',
    'words-stats': '单词 · 展开统计', 'confuse-how': '词汇辨析 · 展开怎么区分', 'read-gains': '读 · 展开这篇的收获', 'listen-preread': '听 · 展开读前生词',
    'study-origin': '学习页 · 看来源', 'notice-install': '今日 · 提醒：放到桌面',
    'me-growth': '我的 · 我的进步', 'me-report': '我的 · 这周的报告', 'me-mistake': '我的 · 错题本',
    'me-level': '我的 · 学习目标和水平', 'me-voice': '我的 · 朗读声音', 'me-habits': '我的 · 使用习惯', 'me-remind': '我的 · 提醒和每周邮件', 'me-install': '我的 · 添加到桌面',
    'trial-level': '试读之后 · 选学习目标',
    'welcome-start': '第一次打开 · 选好方向和目标，开始学习', 'welcome-login': '第一次打开 · 已有账号，登录', 'notice-test': '今日 · 提醒：去能力里测一下',
    'notice-week': '今日 · 提醒：上周小结', 'notice-goal-lower': '今日 · 提醒：建议调低每周目标', 'me-habit': '我的 · 每周目标',
    'study-keep': '学习页 · 存到手机',
    'share-material': '学一篇 · 分享学会的一句', 'share-week': '这周报告 · 分享', 'week-try': '这周报告 · 现在用它写一句',
    'me-data': '我的 · 导出我的数据', 'me-delete': '我的 · 注销账号', 'me-info-list': '我的 · 个人信息收集清单（安卓 App）',
    'me-sharing-list': '我的 · 第三方信息共享清单（安卓 App）', 'me-withdraw': '我的 · 撤回同意（安卓 App）', 'me-permissions': '我的 · 系统权限（安卓 App）', 'words-export': '单词 · 导出单词本',
    'export-csv': '导出 · Excel 表格', 'export-anki': '导出 · Anki', 'export-json': '导出 · 全部学习记录',
    'trial-survey': '今日 · 试用问卷', 'me-guide': '我的 · 操作指南', 'me-feedback': '我的 · 问题反馈', 'me-survey': '我的 · 匿名问卷',
    'beta-main': '内测版 · 去正式版',
    'me-about': '我的 · 认识语流', 'welcome-about': '第一次打开 · 认识语流',
    'about-start': '认识语流 · 开始学', 'about-join': '认识语流 · 注册账号', 'about-guide': '认识语流 · 操作指南', 'about-vocab-test': '认识语流 · 测词汇量',
    'about-dl-android': '认识语流 · 下载安卓 App', 'about-dl-windows': '认识语流 · 下载 Windows 版', 'about-dl-mac': '认识语流 · 下载 Mac 版', 'about-dl-linux-appimage': '认识语流 · 下载 Linux 测试版（AppImage）', 'about-dl-linux-deb': '认识语流 · 下载 Linux 测试版（deb）',
    'about-harmony-apply': '认识语流 · 鸿蒙申请内测（去问题反馈）', 'about-harmony-join': '认识语流 · 鸿蒙加入内测（AppTest，仅内测版）',
    'announce-open': '今日 · 公告：去看看',
    'home-week': '今日 · 这周进步', 'me-weekly-mail': '我的 · 每周进度邮件',
    'finish-expr': '学完一篇 · 小结：表达', 'finish-words': '学完一篇 · 小结：新词', 'finish-grammar': '学完一篇 · 小结：语法点',
    'home-more-one': '今日 · 计划完成后再学一篇', 'home-more-grammar': '今日 · 计划完成后做 4 道语法题',
    'home-extra': '今日 · 还有时间的话', 'home-week-task': '今日 · 本周任务',
    'line-say': '今日好句 · 听一遍', 'line-shadow': '今日好句 · 跟读', 'line-keep': '今日好句 · 收藏', 'line-read': '今日好句 · 读原文',
    'shadow-sound': '跟读 · 去练要练的音', 'speak-ielts': '口语路线 · 雅思口语',
    'two-play': '听两句、答一句 · 听这两句', 'two-hint': '听两句、答一句 · 给我一点提示', 'two-next': '听两句、答一句 · 下一步',
    # 从提醒点进来 (r29): counted per day and kind, no account (99-boot.js remindOpen)
    'remind-review': '从复习提醒邮件点进来', 'remind-once': '从「这次什么时候复习」的提醒点进来', 'remind-weekly': '从周报邮件点进来', 'remind-other': '从其他提醒链接点进来',
}


ACTIVE_SINCE = ('SELECT COUNT(DISTINCT user_id) FROM (SELECT user_id FROM learning_events WHERE created>? UNION '
                'SELECT user_id FROM next_progress WHERE created>? UNION SELECT user_id FROM next_reviews WHERE created>?)')


def overview(c):
    import chat_service
    now = time.time()
    day = time.strftime('%Y-%m-%d', time.gmtime(now))
    week = [time.strftime('%Y-%m-%d', time.gmtime(now - i * 86400)) for i in range(7)]
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    return {
        'feedback_open': __import__('feedback_service').open_count(c),
        'users': q('SELECT COUNT(*) FROM users'),
        'admins': q('SELECT COUNT(*) FROM users WHERE admin=1'),
        # r26: a material step or a review counts too (as in 学习数据), not only the older learning events
        'active_7d': q(ACTIVE_SINCE, *[now - 7 * 86400] * 3),
        'active_1d': q(ACTIVE_SINCE, *[now - 86400] * 3),
        'events_7d': q('SELECT COUNT(*) FROM learning_events WHERE created>?', now - 7 * 86400),
        'ai': {
            'today': q('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', day),
            'week': [{'day': d, 'count': q('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', d)} for d in reversed(week)],
            'site_limit': chat_service.site_limit(c),  # today's, grown with the learners (chat_service.site_limit)
            'limits': __import__('console_ops').limits(),
            'user_limit': chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'),
            'users_at_limit': (q('SELECT COUNT(*) FROM ai_usage WHERE day=? AND user_id>0 AND count>=?', day, chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'))
                               if chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT') else 0),
            'model': ai_model_text(),
        },
        'survey_responses': q('SELECT COUNT(*) FROM survey_responses WHERE survey=? AND hidden=0', survey.SURVEY_ID),
        'trial_responses': q('SELECT COUNT(*) FROM survey_responses WHERE survey=? AND hidden=0', survey.TRIAL_ID),
        'profiles': q('SELECT COUNT(*) FROM next_profiles'),
        'never_started': q("SELECT COUNT(*) FROM users WHERE admin=0 AND COALESCE(role, '')<>'teacher' AND id NOT IN (SELECT user_id FROM next_progress UNION SELECT user_id FROM next_reviews)"),
        'disabled': q('SELECT COUNT(*) FROM users WHERE disabled=1'),
        'hidden_materials': q('SELECT COUNT(*) FROM material_hidden'),
        'errors_24h': __import__('ops_errors').count_since(c, 86400),
        'announce': __import__('console_ops').current_announcement(c),
        'classes': _class_numbers(c),
        'task': __import__('console_ops').task_status()['state'],
        'backup': backup_status(), 'daily': __import__('daily_service').status(c),
        'paused': __import__('privacy_service').paused_report(c),  # 数据存放在香港: paused, run out, deleted or not
        'server': server_label(),
        'generated_at': now,
    }


def ai_model_text():
    """The models the tasks use, for the overview (B7's routes, ai_routes.routes: console over server over the default;
    FLOW_AI_MODEL is gone from both sites since 2026-11-26): the one most tasks use, and how many use another."""
    try:
        import ai_routes
        names = [v.get('route') or ai_routes.default_model() for v in ai_routes.routes().values()]
    except Exception:  # noqa: BLE001 - the overview shows the rest without it
        names = []
    names = [x for x in names if x] or [x for x in [os.getenv('FLOW_AI_MODEL', '').strip()] if x]
    if not names:
        return ''
    top = max(sorted(set(names)), key=names.count)
    others = len(set(names)) - 1
    return top + (f'（另有 {others} 种模型用在个别任务上，见「AI 用量、费用和质量」）' if others else '（各项任务都用它）')


def _class_numbers(c):
    """班级试用 in the overview: how many classes, members, 试用人数 and 试用人次 (numbers only, so 只看数据 sees them too)."""
    got = __import__('class_service').console_list(c)
    return {'count': sum(1 for x in got['items'] if x['active']), 'members': got['members'], 'trial_people': got['trial_people'],
            'trial_days': got['trial_days']}


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


def console_get(c, path, one, op):
    """The r26 views (console_data.py); the learner pages and the people in the AI view only for 管理员."""
    import console_data as cd, console_ops as co
    days = lambda d: int(one('days', d) or d)
    if path == '/funnel':
        return cd.funnel(c, days('0') if one('days') in ('7', '30', '90') else 0)
    if path == '/cohorts':
        return cd.cohorts(c)
    if path == '/content':
        return cd.content(c, days('0') if one('days') in ('7', '30', '90') else 0)
    if path == '/books':
        return {'books': cd.books(c), 'exams': cd.exams(c)}
    admin = op['role'] == 'admin'
    if path == '/ai':
        out = cd.ai(c, days('14'), people=admin)
        if not admin:
            out['limits'].pop('by', None)  # 只看数据 sees the numbers, not which operator changed them
        return out
    if path == '/tasks':
        ex = co.task_status()
        if not admin:
            ex['task'].pop('by', None)
        return {'examples': ex, 'daily': __import__('daily_service').status(c), 'backup': backup_status(),
                'paused': __import__('privacy_service').paused_report(c),
                'books': [{'id': b['id'], 'title': b['title'], 'group': b['group']} for b in __import__('vocab_service').registry()]}
    if path == '/announcements':
        out = co.announcements(c)
        if not admin:
            for x in out['items']:
                x.pop('by', None)
        if __import__('app').CHANNEL == 'beta':
            out['harmony'] = harmony_link(c, admin)
        return out
    if path == '/learners':
        return cd.learner_list(c, one('q')[:60], one('filter', 'all'), one('sort', 'recent'), int(one('page', '1') or 1))
    if path == '/classes':
        return __import__('class_service').console_list(c)
    if path == '/teacher-links':
        return __import__('teacher_service').links(c)
    if path == '/beta-invites':
        return __import__('beta_invites').listing(c)
    if path == '/beta-tests':
        return __import__('beta_tools').listing(c)
    if path == '/ai-people':
        return cd.ai_people(c)
    if path == '/word-extras':
        return word_extras_list(c, one('days', '7'))


ACCOUNT_POSTS = {'/learner/disable', '/learner/signout', '/learner/staff', '/learner/teacher', '/learner/level', '/learner/daily-new'}


def console_post(c, path, data, op):
    """The r26 changes (console_ops.py), each written to the operator log. Returns (body, status) or None."""
    import console_ops as co
    who = op['email'] or op['label']
    if path in ('/learner/ai-quota', '/learner/ai-quota/clear'):
        return ai_quota_post(c, path, data, op, who)
    if path in ACCOUNT_POSTS:
        uid = data.get('id')
        if path == '/learner/disable':
            on = bool(data.get('disabled', True))
            body, status, u = co.set_disabled(c, uid, on)
            action, detail = ('account-disable' if on else 'account-enable'), (f"结束了 {body.get('sessions_ended', 0)} 个登录" if on and status == 200 else '')
        elif path == '/learner/signout':
            body, status, u = co.sign_out(c, uid)
            action, detail = 'account-signout', (f"结束了 {body.get('sessions_ended', 0)} 个登录" if status == 200 else '')
        elif path == '/learner/staff':
            on = bool(data.get('staff'))
            body, status, u = co.set_staff(c, uid, on)
            action, detail = ('account-staff-on' if on else 'account-staff-off'), ''
        elif path == '/learner/teacher':
            on = bool(data.get('teacher'))
            body, status, u = __import__('teacher_service').set_teacher(c, uid, on)
            action, detail = ('account-teacher-on' if on else 'account-teacher-off'), ''
        elif path == '/learner/level':
            body, status, u = co.set_level(c, uid, data.get('level'))
            action, detail = 'account-level', str(data.get('level'))[:10]
        else:
            body, status, u = co.set_daily_new(c, uid, data.get('daily_new'))
            action, detail = 'account-daily-new', f"每天 {data.get('daily_new')} 个"
        if u is not None:
            log_action(c, op, action, co.target(u), detail if status == 200 else body.get('error', status))
        return body, status
    if path == '/material/hide':
        hidden = bool(data.get('hidden', True))
        body, status, title = co.set_hidden(c, data.get('pack'), hidden, data.get('reason', ''), who)
        if status == 200:
            log_action(c, op, 'material-hide' if hidden else 'material-show', f"{title} ({body['pack']})", str(data.get('reason') or '')[:120] if hidden else '')
        return body, status
    if path == '/settings/ai-limits':
        body, status = co.set_limits(data, who)
        if status == 200:
            log_action(c, op, 'ai-limits', 'AI 额度', co.limits_text(body))
        return body, status
    if path == '/settings/ai-routes':
        import ai_routes
        body, status, changes = ai_routes.set_routes(data, who)
        if status == 200 and changes:
            log_action(c, op, 'ai-routes', 'AI 模型', ai_routes.changes_text(changes)[:300])
        return body, status
    if path == '/settings/ai-budget':
        body, status = co.set_ai_budget(data, who)
        if status == 200:
            log_action(c, op, 'ai-budget', 'AI 预算', co.ai_budget_text(body))
        return body, status
    if path == '/ai/samples/redo':
        body, status = co.redo_sample(c, data.get('kind'), data.get('key'))
        if status == 200:
            log_action(c, op, 'ai-redo', __import__('console_data').KIND_LABEL.get(data['kind'], data['kind']), ' / '.join(data['key'])[:160])
        return body, status
    if path == '/tasks/examples/start':
        body, status = co.start_examples(data, who)
        if status == 202:
            books = data.get('books') or []
            log_action(c, op, 'examples-start', '例句预生成', ('词书 ' + ','.join(books) if books else '全部词书') + (f"，最多 {data['max_calls']} 次请求" if data.get('max_calls') else ''))
        return body, status
    if path == '/tasks/examples/stop':
        body, status = co.stop_examples()
        if status == 200:
            log_action(c, op, 'examples-stop', '例句预生成')
        return body, status
    if path == '/announcements/create':
        body, status = co.announce(c, data, who)
        if status == 200:
            log_action(c, op, 'announce', f"#{body['id']}", body['text'][:120])
        return body, status
    if path == '/announcements/end':
        body, status = co.end_announcement(c, data.get('id'))
        if status == 200:
            log_action(c, op, 'announce-end', f"#{body['id']}")
        return body, status
    if path == '/class/create':
        body, status, tgt = __import__('class_service').create(c, data, who)
        if status == 200:
            log_action(c, op, 'class-create', tgt)
        return body, status
    if path == '/teacher-link/create':
        body, status, tgt = __import__('teacher_service').make_link(c, data, who)
        if status == 200:
            log_action(c, op, 'teacher-link', tgt, f"有效 {body['days']} 天，到 {body['expires']}")
        return body, status
    if path == '/teacher-link/revoke':
        body, status, tgt = __import__('teacher_service').revoke(c, data)
        if status == 200:
            log_action(c, op, 'teacher-link-revoke', tgt)
        return body, status
    # 内测版的测试账号 (beta_tools): made and all deleted only on the 内测版's console (FLOW_CHANNEL=beta)
    if path in ('/beta-test/create', '/beta-test/reset'):
        bt = __import__('beta_tools')
        if not bt.beta():
            return {'error': '测试账号只在内测版的后台里造和删'}, 409
        if path == '/beta-test/create':
            body, status, tgt = bt.make(c, data.get('kind'), who)
            if status == 200:
                log_action(c, op, 'test-account', tgt, body['label'])
            return body, status
        body, status, tgt = bt.reset(c, data)
        if status == 200:
            log_action(c, op, 'test-reset', tgt)
        return body, status
    # 鸿蒙内测链接 (console_ops, D3 #415): the 内测版's download page shows 「加入内测」 with it, 「即将开放」 without
    # 单词搭配反馈 (word_extras, B7; B2's 「这条不对」): a row learners marked is taken down for everyone, or put back
    if path in ('/word-extras/take-down', '/word-extras/put-back'):
        return word_extras_post(c, path, data, op, who)
    if path == '/settings/harmony-link':
        import app
        if app.CHANNEL != 'beta':
            return {'error': '鸿蒙内测链接只在内测版的后台里填'}, 409
        try:
            co.set_harmony_test_url(str(data.get('url') or '')[:2000], who)
        except ValueError as e:
            return {'error': str(e), 'field': 'url'}, 400
        host = co.harmony_test_host()
        log_action(c, op, 'harmony-link', '鸿蒙内测链接', host or '清空')
        return {'ok': True, **harmony_link(c, True)}, 200
    # 内测版邀请码 (beta_invites): made and revoked only on the 内测版's console (FLOW_CHANNEL=beta)
    if path in ('/beta-invite/create', '/beta-invite/revoke'):
        import app
        if app.CHANNEL != 'beta':
            return {'error': '邀请码只在内测版的后台里发'}, 409
        bi = __import__('beta_invites')
        if path == '/beta-invite/create':
            body, status, tgt = bi.make(c, data, who)
            if status == 200:
                log_action(c, op, 'invite-create', tgt, f"能用 {body['uses']} 次，到 {body['expires']}")
            return body, status
        body, status, tgt = bi.revoke(c, data)
        if status == 200:
            log_action(c, op, 'invite-revoke', tgt)
        return body, status
    if path in CLASS_POSTS:
        what = path.rsplit('/', 1)[1]
        body, status, tgt, detail = __import__('class_service').change(c, {**data, '_what': what})
        if status == 200:
            action = 'class-' + (what if what != 'active' else 'start' if data.get('active') else 'stop')
            log_action(c, op, action, tgt, detail)
        return body, status
    return None


CLASS_POSTS = {'/class/rename', '/class/teacher', '/class/code', '/class/active'}


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
        base = next((x for x in PREFIXES if path.startswith(x + '/')), None)
        if base is None:
            return self._send({'error': '接口不存在'}, 404)
        path = path[len(base):]
        op = operator(self.headers)
        if op is None:
            return self._send({'error': '没有通过 Cloudflare Access 的登录核对，请重新打开后台'}, 403)
        with app.db() as c:
            schema(c)
            if method == 'GET':
                if path not in VIEWER_GET | ADMIN_GET:
                    return self._send({'error': '接口不存在'}, 404)
                if path in ADMIN_GET and op['role'] != 'admin':
                    return self._send({'error': '需要管理员权限：你现在的身份是「只看数据」'}, 403)
                if path == '/me':
                    return self._send({**op, 'server': server_label(), **site()})
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
                    # the server's own errors, and what learners' browsers reported (页面报错)
                    return self._send({**__import__('ops_errors').recent(c), 'client': __import__('field_service').recent_issues(c)})
                if path == '/speed':
                    return self._send(__import__('field_service').speed(c, 30 if one('days') == '30' else 7))
                if path == '/users':
                    return self._send(__import__('account_service').admin_users(c, one('q')))
                if path == '/log':
                    return self._send(operator_log(c))
                if path == '/feedback':
                    return self._send(__import__('feedback_service').listing(c, one('status', 'new'), int(one('page', '1') or 1)))
                if path == '/feedback/image':
                    # a screenshot learners sent with a report: administrators only, never cached
                    got = __import__('feedback_service').image(one('id'), one('n'))
                    if not got:
                        return self._send({'error': '没有这张截图'}, 404)
                    return self._send(None, body=got[0], mime=got[1])
                if path == '/learner':
                    got = __import__('console_data').learner(c, int(one('id')))
                    return self._send(got) if got else self._send({'error': '没有找到这个学员'}, 404)
                if path == '/class':
                    got = __import__('class_service').console_detail(c, one('id'))
                    if not got:
                        return self._send({'error': '没有找到这个班级'}, 404)
                    for r in got['log']:
                        r['action_label'] = ACTION_LABEL.get(r['action'], r['action'])
                    return self._send(got)
                if path == '/ai/samples':
                    return self._send(*__import__('console_data').ai_samples(c, one('kind'), int(one('n', '5') or 5)))
                if path in ('/funnel', '/cohorts', '/content', '/books', '/ai', '/tasks', '/announcements', '/learners', '/classes', '/teacher-links', '/beta-invites', '/beta-tests', '/ai-people', '/word-extras'):
                    return self._send(console_get(c, path, one, op))
                if path in CSV_EXPORTS:
                    import console_data as cd
                    kind, label = CSV_EXPORTS[path]
                    name = f"flow-{kind}-{time.strftime('%Y%m%d')}.csv"
                    body = {'learners': cd.learners_csv, 'materials': cd.materials_csv, 'ai': cd.ai_csv,
                            'classes': __import__('class_service').classes_csv}[kind](c)
                    log_action(c, op, 'export', name, label)
                    return self._send(None, body=body, mime='text/csv; charset=utf-8', extra={'Content-Disposition': f'attachment; filename="{name}"'})
                # ?s= picks the survey (survey_service.SURVEYS: the needs survey by default, s=trial the class trial one)
                sid = survey.pick(one('s'))
                if path == '/survey/definition':
                    return self._send(survey.definition(sid))
                if path == '/survey/summary':
                    filters = {k: one(k) for k in ('role', 'level', 'flow')} if sid == survey.SURVEY_ID else {}
                    return self._send(survey.summary(c, filters, sid))
                if path == '/survey/responses':
                    return self._send(survey.responses(c, int(one('page', '1') or 1), 20, one('q')[:100], sid))
                if path == '/survey/export.csv':
                    name = f"flow-survey-{'trial-' if sid == survey.TRIAL_ID else ''}{time.strftime('%Y%m%d')}.csv"
                    log_action(c, op, 'survey-export', name)
                    return self._send(None, body=survey.export_csv(c, sid), mime='text/csv; charset=utf-8',
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
                if path == '/feedback/status':
                    status = 'done' if data.get('status') == 'done' else 'new'
                    body, code = __import__('feedback_service').set_status(c, int(data['id']), status, op['email'] or op['label'])
                    if code == 200:
                        log_action(c, op, 'feedback-done' if status == 'done' else 'feedback-reopen', f"#{int(data['id'])}")
                    return self._send(body, code)
                if path == '/daily/run':
                    # Today's 今日一读 (今日热点 until 2026-11-25), made now instead of waiting for the timer.
                    if __import__('daily_service').PAUSED:  # off until the samples are read (daily_service.samples)
                        return self._send({'ok': False, 'message': '今日一读还没打开：先在内测版写几篇样稿看过（daily_service.py samples），确认不碰新闻再打开。'}, 409)
                    # again: today's failed (or cut off) — allow one more round of two tries (r26).
                    again = bool(data.get('again')) and __import__('console_ops').daily_again(c)
                    def run():
                        with app.db() as conn:
                            __import__('daily_service').run(conn)
                    threading.Thread(target=run, daemon=True).start()
                    log_action(c, op, 'daily-again' if again else 'daily-run', time.strftime('%Y-%m-%d'))
                    return self._send({'ok': True, 'message': '已开始生成，几分钟后刷新查看；今天已经成功生成过的不会重做。'}, 202)
                got = console_post(c, path, data, op)
                if got is not None:
                    return self._send(*got)
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
