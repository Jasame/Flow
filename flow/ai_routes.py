"""Which model answers each AI task, what every call cost, and the daily AI budget (xmc.hk console).

Routes. A text task goes to one of two model names on the xmc-api gateway, with the same address and key as now:
- gemini: FLOW_TEXT_AI_MODEL (flow-text: Gemini 3.8 Flash first);
- deepseek: FLOW_DEEPSEEK_AI_MODEL, default flow-deepseek (DeepSeek first, Gemini as the gateway's backup line).
A task's route is set in the console (console-settings.json 'ai_routes': {kind: route, '*': route}); FLOW_AI_ROUTES
(JSON of the same shape) is the server's default; with neither, every task stays on gemini, as before. Audio and web
search never take a route: they go to the main model. When a route's lines all fail, Flow still falls back to the main
model (chat_service.request_model).

DeepSeek thinks before it answers unless told not to; every text request says "no thinking" (the Gemini relay ignores
the field), and the deepseek route also asks for a JSON object on tasks whose answer is JSON.

Every model call (each attempt, a fallback included) is a row in ai_calls: the task, route, which service, the model
that answered, tokens (DeepSeek reports the input that hit its prompt cache), milliseconds and the outcome. The Gemini
relay reports no usage: those rows are estimated from the text (its thinking tokens are not known) and marked so.
Costs are worked out when read, from PRICES (the console may override them), by the time of each call: DeepSeek's
off-peak half price, Gemini's price after 2026-12-31.
"""
import contextlib, datetime, json, math, os, re, sqlite3, sys, threading, time

DAY = 86400
TASKS = [  # kind, label, group (grading: marks what a learner wrote or said; content: shared material; chat: free answers)
    ('next-rewrite', '仿写批改', 'grading'), ('next-essay', '写作批改', 'grading'), ('next-translate', '翻译批改', 'grading'),
    ('next-retell', '复述点评', 'grading'), ('next-dialog', '情景对话', 'grading'), ('next-ielts', '雅思口语点评', 'grading'),
    ('next-explain', '句子讲解', 'content'), ('next-variant', '难度改写', 'content'), ('next-examples', 'AI 例句', 'content'),
    ('next-transsrc', '翻译原句', 'content'), ('next-enrich', '导入文章出题', 'content'), ('daily-news', '今日热点改写', 'content'),
    ('context-help', '随堂提示', 'chat'), ('chat', '导师问答', 'chat'),
]
LABEL = {k: l for k, l, _ in TASKS}
GROUP = {k: g for k, _, g in TASKS}
# calls that are not learner tasks of their own: in the cost tables under their own name, on another task's route
EXTRA = {'fill-examples': ('例句预生成（批量）', 'next-examples'), 'daily-search': ('今日热点联网检索', None),
         'ai-check': ('部署自检', None), 'ai-check-json': ('部署自检', None)}
LABEL.update({k: v[0] for k, v in EXTRA.items()})
FREE_TEXT = {'chat', 'ai-check'}  # answers in prose, not JSON
ROUTES = {'gemini': 'Gemini', 'deepseek': 'DeepSeek'}
DEFAULT_ROUTE = 'gemini'

# Yuan per million tokens (DeepSeek's own CNY prices; Gemini's USD prices at 7.1). Read from the vendors' pages 2026-11-24:
# api-docs.deepseek.com/zh-cn/quick_start/pricing (deepseek-flash = DeepSeek-V4.1-Flash-1017) and
# cloud.google.com/vertex-ai/generative-ai/pricing (Gemini 3.8 Flash, global endpoint; output includes thinking).
PRICES = {
    'deepseek': {'label': 'DeepSeek V4.1 Flash', 'in': 2.0, 'cached': 0.04, 'out': 8.0, 'offpeak': 0.5,
                 'note': '高峰（北京时间工作日 9–12、14–18 点）原价，其余时段半价；法定节假日按高峰估，略偏高'},
    'gemini': {'label': 'Gemini 3.8 Flash', 'in': 5.33, 'cached': 0.53, 'out': 26.63, 'offpeak': 1.0,
               'after': {'2027-01-01': {'in': 10.65, 'cached': 1.07, 'out': 53.25}},
               'note': '按 1 美元 = 7.1 元；2026-12-31 前是推广价，2027-01-01 起翻倍；思考 token 也按输出计费，但中转站不回报，算不进来'},
}
TZ = datetime.timezone(datetime.timedelta(hours=8))
CTX = threading.local()


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS ai_calls(id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,
      route TEXT NOT NULL DEFAULT '', service TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', served TEXT NOT NULL DEFAULT '',
      ok INTEGER NOT NULL, status INTEGER, prompt INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
      completion INTEGER NOT NULL DEFAULT 0, reasoning INTEGER NOT NULL DEFAULT 0, estimated INTEGER NOT NULL DEFAULT 0,
      ms INTEGER NOT NULL DEFAULT 0, fallback INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
    CREATE INDEX IF NOT EXISTS ai_calls_ts ON ai_calls(ts);''')


# ---------- which task is calling ----------

@contextlib.contextmanager
def task(kind):
    """Mark the model calls made inside as this task's (thread-local: the site answers each request on its own thread)."""
    old = getattr(CTX, 'kind', None)
    CTX.kind = kind
    try:
        yield
    finally:
        CTX.kind = old


def current():
    return getattr(CTX, 'kind', None) or 'other'


# ---------- routes ----------

def _settings():
    try:
        return __import__('console_ops').settings()
    except Exception:  # noqa: BLE001 - no console settings: the server's defaults
        return {}


def _env_routes():
    try:
        v = json.loads(os.getenv('FLOW_AI_ROUTES', '') or '{}')
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def routes():
    """{kind: route} for every task, and where each comes from (console / server / default)."""
    console, server = _settings().get('ai_routes') or {}, _env_routes()
    out = {}
    for kind, _, _ in TASKS:
        for src, table in (('console', console), ('server', server)):
            r = table.get(kind) or table.get('*')
            if r in ROUTES:
                out[kind] = {'route': r, 'source': src}
                break
        else:
            out[kind] = {'route': DEFAULT_ROUTE, 'source': 'default'}
    return out


def route(kind=None):
    kind = kind or current()
    kind = EXTRA[kind][1] or kind if kind in EXTRA else kind
    console, server = _settings().get('ai_routes') or {}, _env_routes()
    for table in (console, server):
        r = table.get(kind) or table.get('*')
        if r in ROUTES:
            return r
    return DEFAULT_ROUTE


def model_name(r):
    """The gateway model name of a route ('' when the route is not set up on this server)."""
    if r == 'deepseek':
        return os.getenv('FLOW_DEEPSEEK_AI_MODEL', 'flow-deepseek').strip()
    return os.getenv('FLOW_TEXT_AI_MODEL', '').strip()


def extra_body(r, kind=None):
    """Request fields for the text service: no thinking (DeepSeek thinks by default; the Gemini relay drops unknown
    fields), and on the deepseek route a JSON object for tasks that answer in JSON."""
    kind = kind or current()
    out = {'thinking': {'type': 'disabled'}}
    if r == 'deepseek' and kind not in FREE_TEXT:
        out['response_format'] = {'type': 'json_object'}
    return out


def set_routes(data, by):
    """Console change: data = {'routes': {kind: 'deepseek'|'gemini'|None}} (None = back to the server's default).
    Returns (body, status, changes) with changes = [(kind, before, after)]."""
    import console_ops as co
    want = data.get('routes')
    if not isinstance(want, dict) or not want:
        return {'error': '请选择要改的任务'}, 400, []
    before = {k: v['route'] for k, v in routes().items()}
    cur = dict(co.settings().get('ai_routes') or {})
    for kind, r in want.items():
        if kind not in LABEL and kind != '*':
            return {'error': f'没有这个任务：{kind}'}, 400, []
        if r is None or r == '':
            cur.pop(kind, None)
        elif r in ROUTES:
            cur[kind] = r
        else:
            return {'error': '模型只能选 DeepSeek 或 Gemini'}, 400, []
    if '*' in want:  # "all tasks": one value for every task, no per-task exceptions left behind
        cur = {'*': cur['*']} if '*' in cur else {}
    co.save_settings({'ai_routes': cur}, by)
    after = {k: v['route'] for k, v in routes().items()}
    changes = [(k, before[k], after[k]) for k in after if before[k] != after[k]]
    return {'ok': True, 'routes': routes()}, 200, changes


def changes_text(changes):
    return '；'.join(f"{LABEL.get(k, k)}：{ROUTES[a]} → {ROUTES[b]}" for k, a, b in changes) or '没有变化'


# ---------- one call ----------

def estimate(text):
    """Tokens of a text, roughly (Chinese characters about 0.6 each, other text about 3.5 characters a token)."""
    text = text or ''
    han = len(re.findall(r'[㐀-鿿豈-﫿]', text))
    return int(math.ceil(han * 0.6 + (len(text) - han) / 3.5))


def usage_of(d):
    """(prompt, cached, completion, reasoning) from an OpenAI-style usage object, or None."""
    u = d.get('usage') if isinstance(d, dict) else None
    if not isinstance(u, dict):
        return None
    num = lambda v: v if type(v) is int and 0 <= v < 10**9 else 0
    prompt, completion = num(u.get('prompt_tokens')), num(u.get('completion_tokens'))
    if not prompt and not completion:
        return None
    cached = num(u.get('prompt_cache_hit_tokens')) or num((u.get('prompt_tokens_details') or {}).get('cached_tokens'))
    reasoning = num((u.get('completion_tokens_details') or {}).get('reasoning_tokens'))
    return prompt, min(cached, prompt), completion, reasoning


def family(served, model=''):
    """Which vendor answered: by the model the answer names (served), else by the name asked for. A gateway alias
    such as flow-text says nothing on its own: then the route tells (flow-text is Gemini first)."""
    s = (served or model or '').lower()
    if not served and model and model == os.getenv('FLOW_TEXT_AI_MODEL', '').strip():
        return 'gemini'
    return 'deepseek' if 'deepseek' in s else 'gemini' if 'gemini' in s or 'google' in s else 'other'


def _db():
    """The site's database: the running site's (app.db), else, in a script run for a site (fill_examples.py with
    FLOW_DATA_DIR), that site's flow.sqlite3."""
    app = sys.modules.get('app')
    try:
        if app is not None and hasattr(app, 'db'):
            return app.db()
        if os.environ.get('FLOW_DATA_DIR'):
            p = os.path.join(os.environ['FLOW_DATA_DIR'], 'flow.sqlite3')
            if os.path.isfile(p):
                c = sqlite3.connect(p, timeout=15)
                schema(c)
                return c
    except sqlite3.Error:
        pass
    return None


def record(service, model, started, messages, reply=None, info=None, exc=None, fallback=False):
    """One attempt, into ai_calls. Never raises: the learner's answer matters more than the bookkeeping."""
    info = info or {}
    try:
        status = getattr(exc, 'code', None) if exc is not None else 200
        use = info.get('usage')
        estimated = 0
        if use is None:
            prompt = sum(estimate(m.get('content') if isinstance(m.get('content'), str) else '') for m in messages if isinstance(m, dict))
            use, estimated = (prompt, 0, estimate(reply) if reply else 0, 0), 1
        err = '' if exc is None else (type(exc).__name__ + (f' {status}' if status else '') + ': ' + str(exc)[:120])
        row = (time.time(), current(), getattr(CTX, 'route', '') or '', service, model or '', (info.get('served') or '')[:80],
               int(exc is None), status, *use, estimated, int((time.monotonic() - started) * 1000), int(fallback), err[:200])
        c = _db()
        if c is None:
            return
        with c:
            c.execute('INSERT INTO ai_calls(ts,kind,route,service,model,served,ok,status,prompt,cached,completion,reasoning,estimated,ms,fallback,error) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', row)
        c.close()
    except Exception:  # noqa: BLE001
        pass


# ---------- cost ----------

def prices():
    """The price table in force: PRICES with the console's overrides."""
    out = json.loads(json.dumps(PRICES))
    for fam, v in (_settings().get('ai_prices') or {}).items():
        if fam in out and isinstance(v, dict):
            for k in ('in', 'cached', 'out'):
                if isinstance(v.get(k), (int, float)) and 0 <= v[k] <= 10000:
                    out[fam][k] = float(v[k])
                    out[fam].pop('after', None)  # a price set by hand replaces the scheduled change
            out[fam]['custom'] = True
    return out


def peak(ts):
    """DeepSeek's peak hours: Beijing time, Monday to Friday, 9–12 and 14–18 (public holidays not known: counted as peak)."""
    t = datetime.datetime.fromtimestamp(ts, TZ)
    return t.weekday() < 5 and (9 <= t.hour < 12 or 14 <= t.hour < 18)


def next_offpeak(ts):
    """The first moment at or after ts outside DeepSeek's peak hours."""
    t = datetime.datetime.fromtimestamp(ts, TZ)
    if not peak(ts):
        return ts
    end = t.replace(hour=12 if t.hour < 12 else 18, minute=0, second=0, microsecond=0)
    return end.timestamp()


def cost(fam, ts, prompt, cached, completion, table=None):
    """Yuan for one call."""
    p = (table or prices()).get(fam)
    if not p:
        return 0.0
    day = datetime.datetime.fromtimestamp(ts, TZ).date().isoformat()
    for start, later in sorted((p.get('after') or {}).items()):
        if day >= start:
            p = {**p, **later}
    k = p.get('offpeak', 1.0) if not peak(ts) else 1.0
    return ((prompt - cached) * p['in'] + cached * p['cached'] + completion * p['out']) * k / 1e6


def beijing_day(ts=None):
    return datetime.datetime.fromtimestamp(ts or time.time(), TZ).date()


def _day_start(d):
    return datetime.datetime.combine(d, datetime.time(), TZ).timestamp()


def spent(c, day=None):
    """Yuan spent on a Beijing day (today by default)."""
    d = day or beijing_day()
    start = _day_start(d)
    table = prices()
    try:
        rows = c.execute('SELECT ts, model, served, prompt, cached, completion FROM ai_calls WHERE ts>=? AND ts<? AND ok=1',
                         (start, start + DAY)).fetchall()
    except sqlite3.OperationalError:
        return 0.0
    return sum(cost(family(r[2], r[1]), r[0], r[3], r[4], r[5], table) for r in rows)


def summary(c, days=14):
    """The console's AI cost view: by task (with its route), by model, by day; failures and fallbacks."""
    table, now = prices(), time.time()
    start = _day_start(beijing_day(now) - datetime.timedelta(days=days - 1))
    try:
        rows = c.execute('SELECT ts, kind, route, service, model, served, ok, prompt, cached, completion, reasoning, estimated, ms, fallback '
                         'FROM ai_calls WHERE ts>=?', (start,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    rt = routes()
    blank = lambda: {'calls': 0, 'ok': 0, 'failed': 0, 'fallback': 0, 'backup': 0, 'prompt': 0, 'cached': 0, 'completion': 0, 'reasoning': 0,
                     'estimated': 0, 'cost': 0.0, 'ms': 0}
    kinds, models, by_day = {}, {}, {}
    total = blank()
    for r in rows:
        ts, kind, rte, service, model, served, ok, prompt, cached, completion, reasoning, est, ms, fb = tuple(r)
        fam = family(served, model) if ok else ''
        yuan = cost(fam, ts, prompt, cached, completion, table) if ok else 0.0
        day = beijing_day(ts).isoformat()
        name = served or model or '—'
        for bucket in (kinds.setdefault(kind, blank()), models.setdefault(name if ok else '（失败）', {**blank(), 'family': fam}),
                       by_day.setdefault(day, blank()), total):
            bucket['calls'] += 1
            bucket['ok' if ok else 'failed'] += 1
            bucket['fallback'] += fb
            # the gateway's own backup line answered: the model is not the route's (DeepSeek route answered by Gemini…)
            bucket['backup'] += int(bool(ok and service == 'text' and rte in ROUTES and fam in ROUTES and fam != rte))
            if ok:
                bucket['prompt'] += prompt
                bucket['cached'] += cached
                bucket['completion'] += completion
                bucket['reasoning'] += reasoning
                bucket['estimated'] += est
                bucket['ms'] += ms
            bucket['cost'] += yuan
    def finish(b):
        b['cost'] = round(b['cost'], 4)
        b['seconds'] = round(b.pop('ms') / b['ok'] / 1000, 1) if b['ok'] else None
        b['cache_pct'] = round(100 * b['cached'] / b['prompt']) if b['prompt'] else None
        return b
    out_kinds = []
    for kind, label, group in TASKS + [(k, LABEL.get(k, k), 'other') for k in sorted(kinds) if k not in GROUP]:
        b = finish(kinds.get(kind, blank()))
        if kind in GROUP or b['calls']:
            out_kinds.append({'kind': kind, 'label': LABEL.get(kind, kind), 'group': group, **rt.get(kind, {'route': None, 'source': None}), **b})
    days_list = []
    for i in range(days - 1, -1, -1):
        d = (beijing_day(now) - datetime.timedelta(days=i)).isoformat()
        b = finish(by_day.get(d, blank()))
        days_list.append({'day': d, 'calls': b['calls'], 'cost': b['cost'], 'failed': b['failed']})
    return {'days': days, 'kinds': out_kinds, 'models': sorted(({'name': k, **finish(v)} for k, v in models.items()), key=lambda m: -m['calls']),
            'by_day': days_list, 'total': finish(total), 'today': round(spent(c), 4), 'budget': budget_state(c),
            'prices': table, 'routes': ROUTES, 'deepseek_model': model_name('deepseek'), 'gemini_model': model_name('gemini'),
            'note': '费用按每次调用的实际 token 和上面的单价估算（北京时间）。Gemini 走自己的中转站，不回报用量：这部分 token 按文字长度估算（标「估算」），'
                    '它的思考 token 也收费但算不进来，所以 Gemini 的实际费用会比这里高。'}


# ---------- daily budget ----------

def budget():
    v = _settings().get('ai_budget')
    return float(v) if isinstance(v, (int, float)) and v > 0 else 0.0


def budget_state(c):
    b, s = budget(), spent(c)
    level = None
    if b:
        level = 'over' if s >= b else 'warn' if s >= 0.8 * b else None
    return {'daily': b, 'spent': round(s, 4), 'pct': round(100 * s / b) if b else None, 'level': level}


def over_budget(c=None):
    """Today's spend has reached the daily budget: batch work (例句预生成, the nightly check) waits for tomorrow.
    Learners are never stopped by the budget; their daily call limits stay as they are."""
    if not budget():
        return False
    own = c is None
    c = c or _db()
    if c is None:
        return False
    try:
        return spent(c) >= budget()
    finally:
        if own:
            c.close()


def _alerts_path():
    return __import__('console_ops').data_dir() / 'ai-budget-alerts.json'


def check_budget(c, now=None):
    """Run every few minutes: at 80% and at 100% of the day's budget, one mail to the console's 管理员 (once a day each).
    Returns the levels mailed this time."""
    st = budget_state(c)
    if not st['level']:
        return []
    day = beijing_day(now).isoformat()
    p = _alerts_path()
    try:
        sent = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        sent = {}
    if sent.get('day') != day:
        sent = {'day': day, 'sent': []}
    todo = [lv for lv in ('warn', 'over') if lv not in sent['sent'] and (lv == 'warn' or st['level'] == 'over')]
    if not todo:
        return []
    to = [e.strip() for e in os.getenv('FLOW_ADMIN_EMAILS', '').split(',') if e.strip()]
    mailed = []
    if to and (os.getenv('FLOW_SMTP_HOST') or os.getenv('FLOW_MAIL_OUTBOX')):
        import account_service
        lv = todo[-1]
        subject = ('语流 AI 费用已超过今日预算' if lv == 'over' else '语流 AI 费用已到今日预算的 80%')
        text = (f"今天（北京时间 {day}）AI 估算费用 ¥{st['spent']:.2f}，每日预算 ¥{st['daily']:.2f}（{st['pct']}%）。\n\n"
                + ('已暂停例句预生成等批量任务，明天自动恢复；学员的请求不受影响（每人每天、全站每天的次数上限照旧）。\n' if lv == 'over' else
                   '到 100% 时会暂停例句预生成等批量任务；学员的请求不受影响。\n')
                + '\n明细：xmc.hk/flow → 运维 → AI 用量和费用。')
        for addr in to:
            try:
                account_service.mail(addr, subject, text)
            except Exception:  # noqa: BLE001 - a mail failure must not stop the loop
                continue
        mailed = todo
    sent['sent'] = sorted(set(sent['sent']) | set(todo))  # mailed or not (no mail set up), not asked again today
    try:
        p.write_text(json.dumps(sent), encoding='utf-8')
    except OSError:
        pass
    return mailed


def prune(c, keep_days=180):
    try:
        c.execute('DELETE FROM ai_calls WHERE ts<?', (time.time() - keep_days * DAY,))
        c.commit()
    except sqlite3.Error:
        pass


# ---------- the nightly marking check ----------

NIGHT = (2, 5)  # Beijing hours: off-peak for DeepSeek, and nobody is studying


def eval_dir():
    return __import__('console_ops').data_dir() / 'ai-eval'


def nightly_on():
    return _settings().get('nightly_eval', True) is not False and os.getenv('FLOW_CHANNEL', '').strip().lower() != 'beta'


def nightly(c, now=None):
    """Once a night (02:00–05:00 Beijing), the quick marking check (ai_eval.py --quick, about 17 calls, a throwaway
    database, the site's routes) as a child process; its report is <data>/ai-eval/<day>.json for the console.
    Not on the 内测版, not when turned off in the console, not once the day's budget is spent. Returns True if started."""
    now = now or time.time()
    t = datetime.datetime.fromtimestamp(now, TZ)
    if not nightly_on() or not NIGHT[0] <= t.hour < NIGHT[1]:
        return False
    from vertex_auth import ai_enabled
    if not ai_enabled() or over_budget(c):
        return False
    d = eval_dir()
    day = t.date().isoformat()
    out, mark = d / f'{day}.json', d / 'running.json'
    if out.exists():
        return False
    try:
        if now - json.loads(mark.read_text()).get('started', 0) < 3600:
            return False
    except (OSError, ValueError):
        pass
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    d.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, os.path.join(here, 'ai_eval.py'), '--quick', '--env-file', os.devnull, '--output', str(out),
           '--site-settings', str(__import__('console_ops').data_dir() / 'console-settings.json')]
    with open(d / f'{day}.log', 'w', encoding='utf-8') as log:
        subprocess.Popen(cmd, cwd=here, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env={**os.environ, 'PYTHONUNBUFFERED': '1'})
    mark.write_text(json.dumps({'started': now, 'day': day}))
    return True


def eval_reports(days=14):
    """The last nights' checks, newest first: day, passed/total, per kind, routes, cost."""
    out = []
    d = eval_dir()
    try:
        files = sorted((p for p in d.glob('20*.json')), reverse=True)[:days]
    except OSError:
        files = []
    for p in files:
        try:
            r = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        s = r.get('summary') or {}
        out.append({'day': p.stem, 'when': r.get('when'), 'passed': s.get('passed'), 'total': s.get('total'), 'quick': r.get('quick', False),
                    'parts': {k: s.get(k) for k in ('rewrite_fix', 'rewrite_keep', 'essay', 'translate', 'content')},
                    'routes': r.get('routes'), 'cost': (r.get('usage') or {}).get('cost'), 'calls': (r.get('usage') or {}).get('calls'),
                    'failed': [{'kind': x['kind'], 'id': x['id'], 'why': x['why'][:2]} for x in r.get('items', []) if not x.get('ok')][:8]})
    return out


def tick(c, now=None):
    """Every few minutes from the site's loop: budget mails, the nightly check, and once a day old rows pruned."""
    check_budget(c, now)
    nightly(c, now)
    t = now or time.time()
    if int(t // 300) % 288 == 0:  # about once a day
        prune(c)
