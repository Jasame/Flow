"""今日热点 search check: the site's own news-search request (daily_service.search_messages) for a few topics, once per
search route, then what a reader would check:
- are the cited source links real and do they open (followed from this server, public addresses only);
- is the story within 48 hours (dates in the brief; publish dates the source pages state);
- does the brief say anything its sources do not (numbers and names in the brief looked up in the opened pages);
- time and cost of the search call (ai_calls; 百炼's search fee added).
Routes: 'gemini' = Gemini's own search on the main service (as today); any other name = FLOW_SEARCH_AI_MODEL, a 百炼
search name on the gateway (flow-search-ds-flash …). When 百炼 fails the site falls back to Gemini; here that counts
as a failure of the 百炼 route and is reported.

    python3 search_eval.py [--env-file /etc/flow.env] [--routes gemini,flow-search-ds-flash] [--topics tech,sport]
                           [--strategy turbo|max] [--output report.json]
A throwaway database; the site's own data is never touched. About ¥0.01–0.06 per route and topic."""
import argparse, datetime, html, ipaddress, json, os, re, socket, statistics, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TZ = datetime.timezone(datetime.timedelta(hours=8))
DEFAULT_TOPICS = ('tech', 'society', 'sport', 'science', 'screen')
# 百炼's own search fee per search, yuan (help.aliyun.com/zh/model-studio/web-search, read 2026-11-25: per 1,000 calls
# turbo ¥3, max ¥4); Gemini's search fee on Vertex is not counted here (it is not in the token price).
SEARCH_FEE = {'turbo': 0.003, 'max': 0.004}
MONTHS = {m: i for i, m in enumerate(('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
                                      'october', 'november', 'december'), 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS['sept'] = 9
MON = '(' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?'
DATE_PATTERNS = (re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+' + MON + r'(?:,?\s+(\d{4}))?', re.I),
                 re.compile(r'\b' + MON + r'\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?', re.I),
                 re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'))
COMMON = set('The A An In On At Of For And But Or By With From To As It Its This That These Those He She They We You I His Her Their Our '
             'Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September '
             'October November December According Officials Some Many Most Others After Before During While When Where What Who '
             'However Meanwhile Also Several Experts Researchers Scientists People Residents Students Fans Critics'.split())


# ---------- fetching a source, safely ----------

def public_host(host):
    """Only public addresses: a search result must not make this server open its own or a private network's pages."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


class CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlsplit(newurl)
        if u.scheme not in ('http', 'https') or not u.hostname or not public_host(u.hostname):
            raise urllib.error.URLError('redirect to a non-public address')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(CheckedRedirects)


def fetch(url, timeout=12, limit=2_000_000):
    """{status, open, final_host, published, text} for one source link."""
    out = {'url': url, 'status': None, 'open': False, 'final_host': '', 'published': None, 'text': ''}
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or not public_host(u.hostname):
        out['error'] = 'not a public http(s) address'
        return out
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; jasa-flow-search-check/1.0)', 'Accept': 'text/html,*/*;q=0.5'})
    try:
        with OPENER.open(req, timeout=timeout) as r:
            out['status'] = r.status
            out['final_host'] = urllib.parse.urlsplit(r.geturl()).hostname or ''
            raw = r.read(limit).decode(r.headers.get_content_charset() or 'utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        out['status'] = exc.code
        out['error'] = f'HTTP {exc.code}'
        return out
    except Exception as exc:  # noqa: BLE001 - a link that does not open is the finding
        out['error'] = type(exc).__name__ + ': ' + str(exc)[:120]
        return out
    out['open'] = 200 <= (out['status'] or 0) < 400
    out['published'] = published(raw)
    body = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', raw)
    out['text'] = re.sub(r'\s+', ' ', html.unescape(re.sub(r'(?s)<[^>]+>', ' ', body)))[:400_000]
    return out


def published(raw):
    """The publish date a page states (meta tags, JSON-LD, <time>), as an ISO date, or None."""
    for pat in (r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|og:published_time|datePublished|pubdate|publishdate|date)["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\'](?:article:published_time|og:published_time|datePublished|pubdate|publishdate)',
                r'"datePublished"\s*:\s*"([^"]+)"', r'<time[^>]+datetime=["\']([^"\']+)'):
        m = re.search(pat, raw, re.I)
        if m:
            d = re.match(r'(\d{4})-(\d{2})-(\d{2})', m.group(1).strip())
            if d:
                return '-'.join(d.groups())
    return None


# ---------- reading the brief ----------

def dates_in(text, today):
    """Calendar dates the brief names (a date without a year takes the run's year, or last year if that is ahead)."""
    found = set()
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text):
            g = m.groups()
            try:
                if pat is DATE_PATTERNS[2]:
                    d = datetime.date(int(g[0]), int(g[1]), int(g[2]))
                elif pat is DATE_PATTERNS[0]:
                    d = datetime.date(int(g[2]) if g[2] else today.year, MONTHS[g[1].lower().rstrip('.')], int(g[0]))
                else:
                    d = datetime.date(int(g[2]) if g[2] else today.year, MONTHS[g[0].lower().rstrip('.')], int(g[1]))
            except (ValueError, KeyError):
                continue
            if not g[-1] and pat is not DATE_PATTERNS[2] and d > today + datetime.timedelta(days=1):
                d = d.replace(year=d.year - 1)
            found.add(d)
    return sorted(found)


def facts(text):
    """What can be looked up: numbers (12, 3.5%, 1,200) and names (capitalised words not opening a sentence)."""
    nums = {n.replace(',', '').rstrip('.') for n in re.findall(r'\b\d[\d,]*(?:\.\d+)?%?', text)}
    nums = {n for n in nums if not re.fullmatch(r'(19|20)\d\d', n) and n not in {'1', '2', '0'}}
    names = set()
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        words = re.findall(r"[A-Za-z][A-Za-z'’-]*", sentence)
        for w in words[1:]:
            if w[0].isupper() and w not in COMMON and len(w) > 2:
                names.add(w.strip("'’"))
    return sorted(nums), sorted(names)


def found_in(fact, pages):
    f = fact.lower()
    return any(f in p for p in pages) or (fact.replace('%', '') != fact and any(fact.replace('%', ' percent').lower() in p for p in pages))


# ---------- one route, one topic ----------

def ask(route, topic, day, strategy):
    import ai_routes, chat_service as cs, daily_service as daily
    if route == 'gemini':
        os.environ.pop('FLOW_SEARCH_AI_MODEL', None)
    else:
        os.environ['FLOW_SEARCH_AI_MODEL'] = route
    os.environ['FLOW_SEARCH_STRATEGY'] = strategy
    item = {'route': route, 'topic': topic[0], 'ok': False}
    started = time.time()
    try:
        with ai_routes.task('daily-search'):
            brief, reason, meta = cs.request_model(daily.search_messages(day, topic, []), grounding=True)
    except Exception as exc:  # noqa: BLE001
        item['error'] = type(exc).__name__ + ': ' + str(exc)[:200]
        brief, reason, meta = '', None, None
    item['seconds'] = round(time.time() - started, 1)
    rows = calls_since(started)
    item['answered_by'] = rows[-1]['service'] if rows else ''
    item['fell_back'] = route != 'gemini' and bool(rows) and rows[-1]['service'] == 'main'
    if item['fell_back']:
        item['error'] = 'bailian failed, Gemini answered: ' + (rows[0]['error'] or '?')
    item['calls'] = [{k: r[k] for k in ('service', 'served', 'ok', 'ms', 'prompt', 'completion', 'error')} for r in rows]
    item['cost'] = round(sum(ai_routes.cost(r['served'] or r['model'], r['ts'], r['prompt'], r['cached'], r['completion']) or 0 for r in rows)
                         + sum(SEARCH_FEE.get(strategy, 0.003) for r in rows if r['service'] == 'search' and r['ok']), 4)
    if not brief:
        return item
    item['brief_raw'] = brief[:3000]
    if 'NO_RECENT_STORY' in brief or reason != 'stop':
        item['error'] = 'no story' if 'NO_RECENT_STORY' in brief else f'finish {reason}'
        return item
    try:
        prov = daily.provenance(brief, meta)
    except ValueError as exc:
        item['error'] = 'provenance: ' + str(exc)
        return item
    item['ok'] = not item['fell_back']
    item['brief'] = prov['brief']
    item['supports'] = len(prov['supports'])
    pages = [fetch(s['url']) for s in prov['sources'][:8]]
    item['sources'] = [{k: p[k] for k in ('url', 'status', 'open', 'final_host', 'published')} | ({'error': p['error']} if p.get('error') else {}) for p in pages]
    item['links_open'] = [sum(p['open'] for p in pages), len(pages)]
    today = datetime.date.fromisoformat(day)
    window = (today - datetime.timedelta(days=2), today)
    named = dates_in(prov['brief'], today)
    item['dates_in_brief'] = [d.isoformat() for d in named]
    item['fresh'] = any(window[0] <= d <= window[1] for d in named) if named else None
    pub = [datetime.date.fromisoformat(p['published']) for p in pages if p['published']]
    item['source_dates'] = sorted({d.isoformat() for d in pub})
    item['source_fresh'] = any(today - datetime.timedelta(days=3) <= d <= today + datetime.timedelta(days=1) for d in pub) if pub else None
    texts = [p['text'].lower() for p in pages if p['open'] and p['text']]
    nums, names = facts(prov['brief'])
    missing = [f for f in nums + names if not found_in(f, texts)] if texts else nums + names
    item['facts'] = [len(nums) + len(names) - len(missing), len(nums) + len(names)]
    item['not_in_sources'] = missing[:15]
    item['numbers_not_in_sources'] = [n for n in nums if n in missing]
    return item


def calls_since(ts):
    import app
    c = app.db()
    try:
        return [dict(r) for r in c.execute("SELECT * FROM ai_calls WHERE kind='daily-search' AND ts>=? ORDER BY id", (ts - 0.5,))]
    finally:
        c.close()


def summarize(items):
    out = {}
    for route in dict.fromkeys(i['route'] for i in items):
        rows = [i for i in items if i['route'] == route]
        good = [i for i in rows if i['ok']]
        links = [sum(x) for x in zip(*[i['links_open'] for i in good])] if good else [0, 0]
        fct = [sum(x) for x in zip(*[i['facts'] for i in good])] if good else [0, 0]
        out[route] = {'ok': [len(good), len(rows)], 'links_open': links, 'fresh': [sum(1 for i in good if i['fresh']), sum(1 for i in good if i['fresh'] is not None)],
                      'source_fresh': [sum(1 for i in good if i['source_fresh']), sum(1 for i in good if i['source_fresh'] is not None)],
                      'facts_found': fct, 'numbers_not_in_sources': sum(len(i['numbers_not_in_sources']) for i in good),
                      'seconds_p50': statistics.median([i['seconds'] for i in rows]) if rows else None,
                      'seconds_max': max([i['seconds'] for i in rows], default=None), 'cost': round(sum(i['cost'] for i in rows), 4),
                      'fell_back': sum(1 for i in rows if i.get('fell_back')), 'failures': [f"{i['topic']}: {i.get('error')}" for i in rows if not i['ok']]}
    return out


def describe(summary):
    lines = []
    for route, s in summary.items():
        pct = lambda a: f'{a[0]}/{a[1]}'
        lines.append(f"== {route}: 成功 {pct(s['ok'])} | 来源能打开 {pct(s['links_open'])} | 简报里有 48 小时内的日期 {pct(s['fresh'])} | "
                     f"来源页标的发布日期在 3 天内 {pct(s['source_fresh'])} | 简报里的数字和名字在来源里找到 {pct(s['facts_found'])}"
                     f"（来源里没有的数字 {s['numbers_not_in_sources']} 个）| 中位 {s['seconds_p50']} 秒、最长 {s['seconds_max']} 秒 | ¥{s['cost']}")
        for f in s['failures']:
            lines.append('   ✗ ' + f)
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='今日热点联网检索评测：来源是否真实可开、是否 48 小时内、有没有来源里没有的内容、用时和费用')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--routes', default='gemini,flow-search-ds-flash', help="逗号分隔；gemini = 现在的 Gemini 检索，其余是网关里的百炼检索名")
    ap.add_argument('--topics', default=','.join(DEFAULT_TOPICS), help='daily_service.TOPICS 里的 key，逗号分隔')
    ap.add_argument('--strategy', choices=('turbo', 'max'), default='turbo')
    ap.add_argument('--day', help='按哪一天问（默认今天，北京时间）')
    ap.add_argument('--output', help='详细结果写进这个 JSON 文件')
    args = ap.parse_args(argv)
    if Path(args.env_file).is_file():
        from studio_setup import read_env
        for k, v in read_env(Path(args.env_file).read_text()).items():
            if k.startswith(('FLOW_', 'GOOGLE_')):
                os.environ[k] = v
    tmp = Path(tempfile.mkdtemp(prefix='flow-search-eval-'))
    os.environ['FLOW_DATA_DIR'] = str(tmp)
    sys.path.insert(0, str(HERE))
    import app, daily_service as daily
    app.DB, app.DATA = tmp / 'eval.sqlite3', tmp
    app.init()
    day = args.day or datetime.datetime.now(TZ).date().isoformat()
    topics = {t[0]: t for t in daily.TOPICS}
    picked = [topics[k] for k in args.topics.split(',') if k in topics]
    items = []
    for topic in picked:
        for route in [r.strip() for r in args.routes.split(',') if r.strip()]:
            item = ask(route, topic, day, args.strategy)
            items.append(item)
            print(f"{route:>22} {topic[0]:<8} {'ok' if item['ok'] else '✗'} {item['seconds']}s ¥{item['cost']} "
                  f"links {item.get('links_open')} fresh {item.get('fresh')} facts {item.get('facts')} {item.get('error', '')}", flush=True)
    report = {'day': day, 'strategy': args.strategy, 'run_at': time.time(), 'summary': summarize(items), 'items': items}
    print(describe(report['summary']))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
