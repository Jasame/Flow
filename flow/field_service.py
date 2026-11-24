"""What learners' browsers tell us about the site itself, so a problem shows up before anyone writes in.

- Page errors: a script that broke, a promise nobody caught, a picture or sound that did not load, a request that
  failed, a sound the browser would not play. Counted per day by kind, page, message, release and platform (an
  iPhone's Safari, WeChat on Android …). Each browser sends each problem once per visit, at most 20.
- Opening times: once per visit, how long until the first page was on screen and where the time went (DNS,
  connecting, the server, the download, the scripts, the home data), with the domain, the platform, the network type
  when the browser tells it, the time zone, and whether it was a repeat visit (served by the service worker). A visit
  that left before anything showed is kept too: that is the slowest kind.

Neither keeps an account or an address: the platform is worked out from the User-Agent and only its family is kept.
Both are capped per day and kept 30 days. The console shows the errors under 错误 (administrators) and the times
under 打开速度 (everyone who can open the console).
"""
import re, sqlite3, time
from datetime import datetime, timedelta

KINDS = {'js': '脚本出错', 'promise': '未处理的异步错误', 'resource': '资源没加载出来', 'api': '请求失败', 'audio': '声音放不出来'}
STEPS = {'listen', 'read', 'check', 'output', 'retell', 'dialog', 'translate', 'essay', 'plan', 'test', 'mistake', 'goals', 'reading',
         'writing', 'speaking', 'listening', 'pair', 'topic', 'edit', 'confuse', 'paper'}
DOMAINS = {'flow.jasa.hk', 'flowlang.cn', 'www.flowlang.cn'}
NETS = {'slow-2g', '2g', '3g', '4g'}
PHASES = ('dns', 'connect', 'tls', 'ttfb', 'html', 'scripts', 'home_api', 'render')
MAX_ISSUE_ROWS, MAX_ISSUE_COUNT, MAX_BATCH = 1000, 100000, 20
MAX_OPENS = 5000
KEEP_DAYS = 30


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS client_issues(day TEXT NOT NULL, kind TEXT NOT NULL, page TEXT NOT NULL, message TEXT NOT NULL, '
              'source TEXT NOT NULL, release TEXT NOT NULL, platform TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, first REAL NOT NULL, last REAL NOT NULL, '
              'PRIMARY KEY(day, kind, page, message, source, release, platform))')
    c.execute('CREATE TABLE IF NOT EXISTS open_times(id INTEGER PRIMARY KEY, created REAL NOT NULL, day TEXT NOT NULL, domain TEXT NOT NULL, '
              'platform TEXT NOT NULL, browser TEXT NOT NULL, net TEXT NOT NULL, tz TEXT NOT NULL, repeat INTEGER NOT NULL, standalone INTEGER NOT NULL, '
              'first_view INTEGER, waited INTEGER NOT NULL DEFAULT 0, dns INTEGER, connect INTEGER, tls INTEGER, ttfb INTEGER, html INTEGER, '
              'scripts INTEGER, home_api INTEGER, render INTEGER, snap INTEGER NOT NULL DEFAULT 0)')
    try:  # a table made before the page could draw from its kept copy (r21) gets the column
        c.execute('ALTER TABLE open_times ADD COLUMN snap INTEGER NOT NULL DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    c.execute('CREATE INDEX IF NOT EXISTS open_times_day ON open_times(day)')


def _today():
    return datetime.now(__import__('next_service').TZ).date().isoformat()


def _release():
    return __import__('feedback_service')._release()


def platform(ua):
    """(system, browser) families from a User-Agent; the string itself is not kept."""
    ua = ua or ''
    system = ('iPad' if 'iPad' in ua or ('Macintosh' in ua and 'Mobile/' in ua) else 'iPhone' if 'iPhone' in ua or 'iPod' in ua
              else 'Android' if 'Android' in ua else 'Mac' if 'Macintosh' in ua else 'Windows' if 'Windows' in ua else '其他')
    browser = ('微信' if 'MicroMessenger' in ua else 'QQ' if 'MQQBrowser' in ua or ' QQ/' in ua else 'Edge' if 'Edg' in ua
               else 'Chrome' if 'Chrome/' in ua or 'CriOS' in ua else 'Firefox' if 'Firefox' in ua or 'FxiOS' in ua
               else 'Safari' if 'Safari' in ua else '其他')
    return system, browser


def page_of(p):
    """'#/m/v5-x/read' -> '#/m/*/read': the kind of page, not which material or node."""
    p = str(p or '').split('?')[0][:120]
    if not p.startswith('#/'):
        return '#/'
    parts = [x for x in p[2:].split('/') if x][:3]
    if not parts:
        return '#/'
    return '#/' + '/'.join([parts[0] if re.fullmatch(r'[a-z]{1,12}', parts[0]) else '*'] + [x if x in STEPS else '*' for x in parts[1:]])


def clean_message(m):
    """No addresses, query strings or long numbers (they make one problem look like many, or could carry a person)."""
    m = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '<email>', str(m or ''))
    m = re.sub(r'https?://[^/\s]+', '', m)
    m = re.sub(r'\?[^\s)"\']*', '', m)
    m = re.sub(r'\d{4,}', '#', m)
    return re.sub(r'\s+', ' ', m).strip()[:200]


def _old(c):
    cut = (datetime.now(__import__('next_service').TZ).date() - timedelta(days=KEEP_DAYS)).isoformat()
    c.execute('DELETE FROM client_issues WHERE day<?', (cut,))
    c.execute('DELETE FROM open_times WHERE day<?', (cut,))


def issues(c, data, ua):
    items = data.get('items') if isinstance(data.get('items'), list) else []
    if not items or len(items) > MAX_BATCH:
        return {'error': '报错条数不对'}, 400
    system, browser = platform(ua)
    plat = f'{system} · {browser}' + (' · 桌面' if data.get('standalone') else '')
    day, now, release = _today(), time.time(), _release() or str(data.get('asset') or '')[:20]
    rows = c.execute('SELECT COUNT(*) FROM client_issues WHERE day=?', (day,)).fetchone()[0]
    kept = 0
    for it in items:
        if not isinstance(it, dict) or it.get('kind') not in KINDS:
            continue
        msg = clean_message(it.get('message'))
        if not msg:
            continue
        key = (day, it['kind'], page_of(it.get('page')), msg, clean_message(it.get('source'))[:120], release, plat)
        hit = c.execute('UPDATE client_issues SET n=n+1, last=? WHERE day=? AND kind=? AND page=? AND message=? AND source=? AND release=? AND platform=? AND n<?',
                        (now, *key, MAX_ISSUE_COUNT)).rowcount
        if not hit and rows < MAX_ISSUE_ROWS:  # a new problem today (one already at its cap stays as it is)
            rows += c.execute('INSERT OR IGNORE INTO client_issues VALUES(?,?,?,?,?,?,?,1,?,?)', (*key, now, now)).rowcount
        kept += 1
    if day != getattr(issues, 'cleaned', ''):
        _old(c); issues.cleaned = day
    c.commit()
    return {'ok': True, 'kept': kept}, 200


def _ms(v, top=120000):
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= top else None


def open_time(c, data, ua):
    day = _today()
    if c.execute('SELECT COUNT(*) FROM open_times WHERE day=?', (day,)).fetchone()[0] >= MAX_OPENS:
        return {'ok': True}, 200  # enough for today: the numbers would not change
    system, browser = platform(ua)
    domain = str(data.get('domain') or '').lower()
    first = _ms(data.get('first_view'))
    c.execute('INSERT INTO open_times(created, day, domain, platform, browser, net, tz, repeat, standalone, snap, first_view, waited, '
              + ', '.join(PHASES) + ') VALUES(' + ','.join('?' * (12 + len(PHASES))) + ')',
              (time.time(), day, domain if domain in DOMAINS else '其他', system, browser, data.get('net') if data.get('net') in NETS else '',
               str(data.get('tz') or '')[:40], int(bool(data.get('repeat'))), int(bool(data.get('standalone'))), int(bool(data.get('snap'))), first,
               _ms(data.get('waited')) or 0, *[_ms(data.get(k)) for k in PHASES]))
    c.commit()
    return {'ok': True}, 200


# ---------- console ----------
def recent_issues(c, days=7):
    since = (datetime.now(__import__('next_service').TZ).date() - timedelta(days=days - 1)).isoformat()
    rows = c.execute('SELECT kind, page, message, source, release, platform, SUM(n) n, COUNT(DISTINCT day) days, MAX(last) last '
                     'FROM client_issues WHERE day>=? GROUP BY kind, page, message, source, release, platform', (since,)).fetchall()
    groups = {}
    for r in rows:
        g = groups.setdefault((r['kind'], r['page'], r['message'], r['source']), {
            'kind': r['kind'], 'kind_label': KINDS.get(r['kind'], r['kind']), 'page': r['page'], 'message': r['message'], 'source': r['source'],
            'count': 0, 'days': 0, 'last': 0, 'releases': {}, 'platforms': {}})
        g['count'] += r['n']; g['days'] = max(g['days'], r['days']); g['last'] = max(g['last'], r['last'])
        g['releases'][r['release'] or '—'] = g['releases'].get(r['release'] or '—', 0) + r['n']
        g['platforms'][r['platform']] = g['platforms'].get(r['platform'], 0) + r['n']
    out = sorted(groups.values(), key=lambda g: -g['count'])[:100]
    for g in out:
        g['platforms'] = sorted(g['platforms'].items(), key=lambda x: -x[1])[:4]
        g['releases'] = sorted(g['releases'].items(), key=lambda x: -x[1])[:4]
    return {'days': days, 'groups': out, 'total': sum(g['count'] for g in groups.values())}


def _pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]


def _summary(rows):
    seen = [r['first_view'] for r in rows if r['first_view'] is not None]
    left = sum(1 for r in rows if r['first_view'] is None)
    return {'visits': len(rows), 'p50': _pct(seen, 50), 'p75': _pct(seen, 75), 'p90': _pct(seen, 90),
            'left': left, 'left_pct': round(100 * left / len(rows), 1) if rows else 0}


def speed(c, days=7):
    """Opening times for the console: overall, where the time goes (medians), and by domain, platform, browser,
    network, first or repeat visit, and day."""
    since = (datetime.now(__import__('next_service').TZ).date() - timedelta(days=days - 1)).isoformat()
    rows = [dict(r) for r in c.execute('SELECT * FROM open_times WHERE day>=?', (since,)).fetchall()]
    label = {'repeat': lambda r: '再次打开（有缓存）' if r['repeat'] else '第一次打开', 'net': lambda r: r['net'] or '浏览器没有告诉',
             'platform': lambda r: r['platform'], 'browser': lambda r: r['browser'], 'domain': lambda r: r['domain'],
             'standalone': lambda r: '从桌面打开' if r['standalone'] else '在浏览器里',
             'snap': lambda r: '先显示上次的内容' if r.get('snap') else '等服务器的回答'}
    by = {}
    for name, f in label.items():
        groups = {}
        for r in rows:
            groups.setdefault(f(r), []).append(r)
        by[name] = sorted(({'group': k, **_summary(v)} for k, v in groups.items()), key=lambda x: -x['visits'])
    daily = {}
    for r in rows:
        daily.setdefault(r['day'], []).append(r)
    return {'days': days, 'overall': _summary(rows),
            'phases': {k: _pct([r[k] for r in rows if r[k] is not None], 50) for k in PHASES},
            'by': by, 'daily': [{'day': d, **_summary(v)} for d, v in sorted(daily.items())]}
