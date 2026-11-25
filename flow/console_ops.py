"""What a 管理员 can change from the xmc.hk console (r26). flow_admin.py routes every one of these: 管理员 only, checked
on the server, with the X-Requested-With header, and written to the operator log there.

- accounts: stop an account (signed out everywhere at once, cannot sign in again) and restore it; sign an account out
  everywhere; a learner's level and daily new words; 员工账号 (users.admin: no daily AI limit) on or off;
- materials: take a material off the lists (书库, 今日, 练习…) and put it back; whoever has it open or in the history
  still reads it, and nothing learned is lost;
- the daily AI limits, set here instead of /etc/flow.env (console-settings.json in the data folder; empty = the
  server's value), in force at once;
- 例句预生成 (fill_examples.py) started, followed and stopped from the console;
- 公告: one line learners see at the top of 今日 until it ends or an operator ends it.
"""
import json, os, re, signal, sqlite3, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def data_dir():
    """The site's data folder (app.DATA when the site runs; FLOW_DATA_DIR otherwise)."""
    app = sys.modules.get('app')
    return Path(app.DATA) if app is not None and hasattr(app, 'DATA') else Path(os.environ.get('FLOW_DATA_DIR') or HERE / 'data')


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS material_hidden(pack TEXT PRIMARY KEY, reason TEXT NOT NULL DEFAULT "", '
              'by TEXT NOT NULL DEFAULT "", at REAL NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, text TEXT NOT NULL, link TEXT NOT NULL DEFAULT "", '
              'starts REAL NOT NULL, ends REAL NOT NULL, ended REAL, by TEXT NOT NULL DEFAULT "", created REAL NOT NULL)')


def target(u):
    """How an account is named in the operator log: name and number (the number stays when a name is reused)."""
    return f"{u['username']} #{u['id']}"


def _user(c, uid):
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None
    return c.execute('SELECT id, username, admin, disabled FROM users WHERE id=?', (uid,)).fetchone()


MISSING = ({'error': '没有找到这个账号'}, 404)


# ---------- accounts ----------

def set_disabled(c, uid, disabled):
    u = _user(c, uid)
    if not u:
        return (*MISSING, None)
    ended = 0
    c.execute('UPDATE users SET disabled=? WHERE id=?', (1 if disabled else 0, u['id']))
    if disabled:
        ended = c.execute('DELETE FROM sessions WHERE user_id=?', (u['id'],)).rowcount
    c.commit()
    return {'ok': True, 'username': u['username'], 'disabled': bool(disabled), 'sessions_ended': ended}, 200, u


def sign_out(c, uid):
    u = _user(c, uid)
    if not u:
        return (*MISSING, None)
    ended = c.execute('DELETE FROM sessions WHERE user_id=?', (u['id'],)).rowcount
    c.commit()
    return {'ok': True, 'username': u['username'], 'sessions_ended': ended}, 200, u


def set_staff(c, uid, on):
    u = _user(c, uid)
    if not u:
        return (*MISSING, None)
    c.execute('UPDATE users SET admin=? WHERE id=?', (1 if on else 0, u['id']))
    c.commit()
    return {'ok': True, 'username': u['username'], 'staff': bool(on)}, 200, u


def set_level(c, uid, level):
    import next_service as nx
    u = _user(c, uid)
    if not u:
        return (*MISSING, None)
    if level not in nx.LEVELS:
        return {'error': '水平只能是 ' + '、'.join(nx.LEVELS)}, 400, u
    if not c.execute('UPDATE next_profiles SET level=?, updated=? WHERE user_id=?', (level, time.time(), u['id'])).rowcount:
        return {'error': '这个学员还没有填学习档案，没有水平可改'}, 409, u
    c.commit()
    return {'ok': True, 'username': u['username'], 'level': level}, 200, u


def set_daily_new(c, uid, n):
    import vocab_service as vs
    u = _user(c, uid)
    if not u:
        return (*MISSING, None)
    if type(n) is not int or not 1 <= n <= vs.DAILY_MAX:
        return {'error': f'每天新词可以是 1–{vs.DAILY_MAX} 个'}, 400, u
    if not c.execute('UPDATE next_vocab_plans SET daily_new=?, updated=? WHERE user_id=?', (n, time.time(), u['id'])).rowcount:
        return {'error': '这个学员还没有开背词计划'}, 409, u
    c.commit()
    return {'ok': True, 'username': u['username'], 'daily_new': n}, 200, u


# ---------- materials ----------

def hidden_packs(c):
    """Materials taken off the lists (an older database without the table: none)."""
    try:
        return {r[0] for r in c.execute('SELECT pack FROM material_hidden')}
    except sqlite3.OperationalError:
        return set()


def set_hidden(c, pack, hidden, reason, by):
    pack = str(pack or '')[:160]
    row = c.execute('SELECT content FROM lab_packs WHERE id=? AND owner IS NULL', (pack,)).fetchone()
    if not row:
        return {'error': '没有这篇材料'}, 404, ''
    title = json.loads(row[0]).get('title') or pack
    if hidden:
        reason = ' '.join(str(reason or '').split())[:200]
        c.execute('INSERT OR REPLACE INTO material_hidden(pack, reason, by, at) VALUES(?,?,?,?)', (pack, reason, by, time.time()))
    else:
        c.execute('DELETE FROM material_hidden WHERE pack=?', (pack,))
    c.commit()
    return {'ok': True, 'pack': pack, 'title': title, 'hidden': bool(hidden)}, 200, title


def daily_again(c):
    """Today's news failed (or was cut off): allow it one more round of two tries. Returns True if it was reset."""
    import daily_service
    st = daily_service.status(c)
    if st['status'] not in ('failed', 'interrupted'):
        return False
    c.execute("UPDATE daily_runs SET attempts=0, status='failed' WHERE day=?", (st['day'],))
    c.commit()
    return True


# ---------- AI limits ----------

SETTINGS = 'console-settings.json'
LIMIT_KEYS = {'FLOW_AI_USER_DAILY_LIMIT': 'user_limit', 'FLOW_AI_DAILY_LIMIT': 'site_limit'}
_CACHE = {'path': None, 'mtime': None, 'data': {}}


def settings():
    p = data_dir() / SETTINGS
    try:
        m = p.stat().st_mtime_ns
    except OSError:
        return {}
    if _CACHE['path'] != p or _CACHE['mtime'] != m:
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            d = {}
        _CACHE.update(path=p, mtime=m, data=d if isinstance(d, dict) else {})
    return _CACHE['data']


def limit_override(name):
    """The console's value for FLOW_AI_DAILY_LIMIT / FLOW_AI_USER_DAILY_LIMIT, or None (use the server's)."""
    v = settings().get(name)
    return v if type(v) is int and v >= 0 else None


def server_limit(name):
    try:
        return max(0, int(os.getenv(name, '0') or 0))
    except ValueError:
        return 0


def limits():
    """The AI limits in force, and where each one comes from: console (后台设置) or server (服务器配置)."""
    import chat_service
    s = settings()
    out = {'updated': s.get('updated'), 'by': s.get('by')}
    for env, key in LIMIT_KEYS.items():
        out[key] = chat_service.daily_limit(env)
        out[key + '_source'] = 'console' if limit_override(env) is not None else 'server'
        out[key + '_server'] = server_limit(env)
    out['tts'] = tts_limits()
    return out


TTS_KEYS = {'FLOW_TTS_USER_CHARS': 'tts_user_chars', 'FLOW_TTS_DAILY_CHARS': 'tts_site_chars', 'FLOW_TTS_IMPORT_CHARS': 'tts_import_chars',
            'FLOW_TTS_IMPORT_PERCENT': 'tts_import_percent', 'FLOW_TTS_PREWARM_CHARS': 'tts_prewarm_chars'}


def tts_limits():
    """AI 朗读 (CosyVoice) caps in characters a day, and the share of the site's day imports may use (tts_service.CAPS)."""
    import tts_service
    out = {}
    for env, key in TTS_KEYS.items():
        out[key] = tts_service.cap(env)
        out[key + '_source'] = 'console' if limit_override(env) is not None else 'server'
    return out


def set_limits(data, by):
    new = {k: v for k, v in settings().items()}
    for env, key in TTS_KEYS.items():
        if key not in data:
            continue
        v, top = data[key], 100 if env == 'FLOW_TTS_IMPORT_PERCENT' else 10_000_000
        if v is None or v == '':
            new.pop(env, None)
        elif type(v) is int and 0 <= v <= top:
            new[env] = v
        else:
            return {'error': f'AI 朗读额度请填 0–{top} 的整数（留空表示用服务器配置）'}, 400
    for env, key in LIMIT_KEYS.items():
        if key not in data:
            continue
        v = data[key]
        if v is None or v == '':
            new.pop(env, None)
        elif type(v) is int and 0 <= v <= 1_000_000:
            new[env] = v
        else:
            return {'error': '额度请填 0–1000000 的整数（0 表示不限，留空表示用服务器配置）'}, 400
    save_settings({k: new.get(k) for k in (*LIMIT_KEYS, *TTS_KEYS)}, by, drop_none=True)
    return {'ok': True, **limits()}, 200


def save_settings(update, by, drop_none=False):
    """Write some keys of console-settings.json (the rest kept), with who and when. drop_none: a None value removes the key."""
    new = dict(settings())
    for k, v in update.items():
        if v is None and drop_none:
            new.pop(k, None)
        else:
            new[k] = v
    new.update(updated=time.time(), by=by)
    p = data_dir() / SETTINGS
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(new, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)
    _CACHE.update(path=None)  # read again at once (two writes within one mtime tick)


def set_ai_budget(data, by):
    """The daily AI budget in yuan (0 or empty: none), the nightly marking check on or off, platform discounts
    ({'bailian': 0.65}: the share of the list price actually paid) and prices set by hand ({model: {in, cached, out,
    platform}} yuan per million tokens at list price; a new model name adds a row; null: back to the built-in table)."""
    import ai_routes
    update = {}
    if 'daily' in data:
        v = data['daily']
        if v in (None, '', 0):
            update['ai_budget'] = None
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 100000:
            update['ai_budget'] = round(float(v), 2)
        else:
            return {'error': '每日预算请填 0–100000 元（0 或留空表示不设）'}, 400
    if 'nightly' in data:
        if type(data['nightly']) is not bool:
            return {'error': '参数不正确'}, 400
        update['nightly_eval'] = None if data['nightly'] else False
    if 'discounts' in data:
        cur = dict(settings().get('ai_discounts') or {})
        if not isinstance(data['discounts'], dict):
            return {'error': '折扣格式不正确'}, 400
        for k, v in data['discounts'].items():
            if k not in ai_routes.PLATFORMS:
                return {'error': f'没有这个平台：{k}'}, 400
            if v is None:
                cur.pop(k, None)
            elif isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 1:
                cur[k] = round(float(v), 3)
            else:
                return {'error': '折扣请填 0–1 之间的小数，比如 0.65 表示六五折'}, 400
        update['ai_discounts'] = cur or None
    if 'prices' in data:
        cur = dict(settings().get('ai_prices') or {})
        if not isinstance(data['prices'], dict):
            return {'error': '单价格式不正确'}, 400
        for key, v in data['prices'].items():
            if not isinstance(key, str) or not ai_routes.NAME.fullmatch(key):
                return {'error': '模型名不正确'}, 400
            if v is None:
                cur.pop(key, None)
                continue
            if not isinstance(v, dict) or any(not isinstance(v.get(k), (int, float)) or isinstance(v.get(k), bool) or not 0 <= v[k] <= 10000 for k in ('in', 'cached', 'out')):
                return {'error': '单价请填 0–10000 元 / 百万 token'}, 400
            row = {k: float(v[k]) for k in ('in', 'cached', 'out')}
            if v.get('platform') in ai_routes.PLATFORMS:
                row['platform'] = v['platform']
            cur[key] = row
        update['ai_prices'] = cur or None
    if not update:
        return {'error': '没有要改的'}, 400
    save_settings(update, by, drop_none=True)
    return {'ok': True, 'daily': ai_routes.budget(), 'nightly': ai_routes.nightly_on(), 'discounts': ai_routes.discounts(), 'prices': ai_routes.prices()}, 200


def ai_budget_text(body):
    return ((f"每日预算 ¥{body['daily']:g}" if body['daily'] else '不设每日预算') + ('，每晚小评测开' if body['nightly'] else '，每晚小评测关')
            + '，百炼折扣 ' + f"{body['discounts'].get('bailian', 1):g}")


REDO = {'next-explain': ('DELETE FROM next_explains WHERE pack=? AND sentence=? AND level=?', 3),
        'next-variant': ('DELETE FROM next_variants WHERE pack=? AND level=?', 2),
        'next-examples': ('DELETE FROM next_word_examples WHERE norm=?', 1),
        'next-transsrc': ('DELETE FROM next_translations WHERE pack=? AND sentence=?', 2),
        'next-dialog': ('DELETE FROM next_dialog_openers WHERE pack=? AND level=?', 2)}


def redo_sample(c, kind, key):
    """Throw away one cached piece of shared AI content an operator found wrong: the next learner who needs it gets a
    freshly written one (one AI call then)."""
    if kind not in REDO or not isinstance(key, list) or len(key) != REDO[kind][1] or not all(isinstance(k, str) and len(k) <= 2000 for k in key):
        return {'error': '参数不正确'}, 400
    if not c.execute(REDO[kind][0], key).rowcount:
        return {'error': '这一条已经不在了'}, 404
    c.commit()
    return {'ok': True}, 200


def limits_text(lim):
    show = lambda v: '不限' if not v else f'{v} 次'
    t = lim.get('tts') or {}
    voice = (f" · AI 朗读每账号 {t['tts_user_chars']} 字符、全站 {t['tts_site_chars']}、导入每账号 {t['tts_import_chars']}、"
             f"导入最多用到全站 {t['tts_import_percent']}%") if t else ''
    return f"每账号 {show(lim['user_limit'])} · 全站 {show(lim['site_limit'])}" + voice


# ---------- 例句预生成 (fill_examples.py) ----------

_PROC = {'p': None}


def _paths():
    d = data_dir()
    return d / 'fill-examples-task.json', d / 'fill-examples-status.json', d / 'fill-examples.log'


def _read(p):
    try:
        v = json.loads(p.read_text(encoding='utf-8'))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _running(task):
    p = _PROC['p']
    if p is not None and task.get('pid') == p.pid:
        return p.poll() is None
    pid = task.get('pid')
    if not pid or task.get('finished'):
        return False
    # A run started before a restart of this process: still there, and still writing progress (the script writes
    # after every call; a number that has been quiet for 15 minutes is another process by now)?
    last = _read(_paths()[1]).get('updated') or task.get('started') or 0
    if time.time() - last > 900:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def task_status():
    task_p, status_p, log_p = _paths()
    task, st = _read(task_p), _read(status_p)
    running = bool(task) and _running(task)
    if not task:
        state = 'idle'
    elif running:
        state = 'waiting' if st.get('state') == 'waiting' else 'running'
    elif task.get('stop_requested'):
        state = 'stopped'
    else:
        state = st.get('state') if st.get('state') in ('done', 'left', 'no-model', 'failed', 'budget') else 'ended'
    try:
        log = log_p.read_text(encoding='utf-8', errors='replace').splitlines()[-12:]
    except OSError:
        log = []
    return {'state': state, 'task': {k: task.get(k) for k in ('started', 'by', 'books', 'max_calls', 'stopped', 'offpeak')},
            'progress': {k: st.get(k) for k in ('total', 'looked', 'calls', 'made', 'left', 'updated', 'books', 'until')}, 'log': log}


def start_examples(data, by):
    import vocab_service as vs
    task_p, status_p, log_p = _paths()
    if task_status()['state'] == 'running':
        return {'error': '例句预生成已经在运行，等它结束或先停止'}, 409
    books = data.get('books') or []
    if isinstance(books, str):
        books = [b for b in books.split(',') if b]
    known = set(vs.book_words())
    if not isinstance(books, list) or len(books) > 30 or any(b not in known for b in books):
        return {'error': '词书不正确'}, 400
    max_calls = data.get('max_calls') or 0
    if type(max_calls) is not int or not 0 <= max_calls <= 100000:
        return {'error': '最多请求次数请填 0–100000（0 表示不限）'}, 400
    cmd = [sys.executable, str(HERE / 'fill_examples.py'), '--env-file', os.devnull, '--status', str(status_p)]
    if books:
        cmd += ['--books', ','.join(books)]
    if max_calls:
        cmd += ['--max-calls', str(max_calls)]
    offpeak = data.get('offpeak', True) is not False
    if offpeak:
        cmd += ['--offpeak']
    for p in (status_p,):
        try:
            p.unlink()
        except OSError:
            pass
    env = {**os.environ, 'FLOW_DATA_DIR': str(data_dir()), 'PYTHONUNBUFFERED': '1'}
    with open(log_p, 'w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, cwd=str(HERE), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
    _PROC['p'] = proc
    task = {'pid': proc.pid, 'started': time.time(), 'by': by, 'books': books, 'max_calls': max_calls, 'offpeak': offpeak}
    task_p.write_text(json.dumps(task, ensure_ascii=False), encoding='utf-8')
    return {'ok': True, **task_status()}, 202


def stop_examples():
    task_p = _paths()[0]
    task = _read(task_p)
    if not task or not _running(task):
        return {'error': '例句预生成没有在运行'}, 409
    try:
        if _PROC['p'] is not None and _PROC['p'].pid == task.get('pid'):
            _PROC['p'].terminate()
        else:
            os.kill(int(task['pid']), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    task.update(stop_requested=True, stopped=time.time())
    task_p.write_text(json.dumps(task, ensure_ascii=False), encoding='utf-8')
    return {'ok': True, 'message': '已让它停下；已经写好的例句都保留，下次从没写的词接着做。'}, 200


# ---------- 公告 ----------

LINK = re.compile(r'#/[A-Za-z0-9/_\-.%]{0,120}')


def current_announcement(c, now=None):
    """The one notice learners see at the top of 今日 now, or None."""
    now = now or time.time()
    try:
        r = c.execute('SELECT id, text, link FROM announcements WHERE ended IS NULL AND starts<=? AND ends>? ORDER BY id DESC LIMIT 1',
                      (now, now)).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(r) if r else None


def announcements(c):
    now = time.time()
    cur = current_announcement(c, now)
    rows = c.execute('SELECT id, text, link, starts, ends, ended, by, created FROM announcements ORDER BY id DESC LIMIT 30').fetchall()
    return {'current': cur, 'items': [{**dict(r), 'active': bool(cur and cur['id'] == r['id'])} for r in rows]}


def announce(c, data, by):
    text = ' '.join(str(data.get('text') or '').split())
    if not 4 <= len(text) <= 120:
        return {'error': '公告请写 4–120 个字，一句话说清楚'}, 400
    link = str(data.get('link') or '').strip()
    if link and not LINK.fullmatch(link):
        return {'error': '链接只能是网站里的页面，例如 #/guide 或 #/library'}, 400
    days = data.get('days', 7)
    if type(days) is not int or not 1 <= days <= 60:
        return {'error': '有效天数请填 1–60'}, 400
    now = time.time()
    c.execute('UPDATE announcements SET ended=? WHERE ended IS NULL AND ends>?', (now, now))  # one at a time: the new one replaces it
    aid = c.execute('INSERT INTO announcements(text, link, starts, ends, by, created) VALUES(?,?,?,?,?,?)',
                    (text, link, now, now + days * 86400, by, now)).lastrowid
    c.commit()
    return {'ok': True, 'id': aid, 'text': text}, 200


def end_announcement(c, aid):
    try:
        aid = int(aid)
    except (TypeError, ValueError):
        return {'error': '参数不正确'}, 400
    if not c.execute('UPDATE announcements SET ended=? WHERE id=? AND ended IS NULL', (time.time(), aid)).rowcount:
        return {'error': '这条公告已经结束了'}, 409
    c.commit()
    return {'ok': True, 'id': aid}, 200
