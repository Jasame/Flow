"""Problem reports from learners: what happened, the page they were on, and up to three screenshots.

Anyone may send one, signed in or not (a teacher trying the site inside WeChat often is not signed in):
- a signed-in learner's report names the account; a guest's keeps nothing that points to them. The guest limit uses a
  day-scoped hash of the address (survey_service.client_key) kept in its own table and deleted after two days, as the
  survey does;
- at most 5 a day as a guest, 20 a day per account, and 300 a day in all;
- screenshots are shrunk on the phone before they are sent (at most 1600 px, JPEG). Here they must be JPEG or PNG and
  at most 700 KB each (three, as base64, stay under nginx's 3 MB request limit). They are kept as files under
  <data>/feedback/<report id>/, never in the database.

Reports are read and marked handled in the operator console (flow_admin, administrators only). It is one-way: the
learner sees 「已收到」 and nothing is sent back.
"""
import base64, binascii, json, os, re, time
from pathlib import Path

KINDS = {'display': '页面显示不对', 'broken': '功能用不了', 'content': '内容有错', 'idea': '建议', 'other': '其他'}
STATUS = {'new': '待处理', 'done': '已处理'}
MIN_TEXT, MAX_TEXT = 4, 1000
MAX_IMAGES, MAX_IMAGE_BYTES = 3, 700_000  # three as base64 stay under nginx's 3 MB request limit
GUEST_DAILY, USER_DAILY, DAILY_TOTAL = 5, 20, 300
IMAGE_TYPES = {b'\xff\xd8\xff': 'jpg', b'\x89PNG\r\n\x1a\n': 'png'}
MIME = {'jpg': 'image/jpeg', 'png': 'image/png'}


def _data():
    """Flow's data folder (app.DATA: FLOW_DATA_DIR, or flow/data)."""
    try:
        import app
        return Path(app.DATA)
    except Exception:  # pragma: no cover - used without the app (a script)
        return Path(os.getenv('FLOW_DATA_DIR', Path(__file__).resolve().parent / 'data'))


def folder():
    return _data() / 'feedback'


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, created REAL NOT NULL, day TEXT NOT NULL, user_id INTEGER, '
              'kind TEXT NOT NULL, text TEXT NOT NULL, contact TEXT NOT NULL DEFAULT "", page TEXT NOT NULL DEFAULT "", '
              'release TEXT NOT NULL DEFAULT "", device TEXT NOT NULL DEFAULT "{}", images TEXT NOT NULL DEFAULT "[]", '
              'status TEXT NOT NULL DEFAULT "new", handled_by TEXT NOT NULL DEFAULT "", handled_at REAL)')
    c.execute('CREATE INDEX IF NOT EXISTS feedback_status ON feedback(status, created)')
    c.execute('CREATE TABLE IF NOT EXISTS feedback_limits(key TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(key, day))')


def _day(now):
    return time.strftime('%Y-%m-%d', time.localtime(now))


def _release():
    """The release this server runs (r20 …), from the deploy status the autodeploy writes."""
    try:
        d = json.loads((_data() / 'deploy-status.json').read_text())
        return str(d.get('tag') or '')[:20]
    except (OSError, ValueError, AttributeError):
        return ''


def _text(v, n):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(v if v is not None else '')).strip()[:n]


def _device(d):
    """What the page says about itself: browser, screen, theme, whether it runs from the home screen or inside
    WeChat, and the last few script errors. Only these keys, each cut short."""
    d = d if isinstance(d, dict) else {}
    out = {'ua': _text(d.get('ua'), 300), 'asset': _text(d.get('asset'), 20), 'theme': _text(d.get('theme'), 10), 'lang': _text(d.get('lang'), 20)}
    for k in ('w', 'h'):
        try:
            out[k] = max(0, min(10000, int(d.get(k) or 0)))
        except (TypeError, ValueError):
            out[k] = 0
    try:
        out['dpr'] = round(max(0.5, min(5.0, float(d.get('dpr') or 1))), 2)
    except (TypeError, ValueError):
        out['dpr'] = 1
    out['standalone'], out['wechat'] = bool(d.get('standalone')), bool(d.get('wechat'))
    errs = d.get('errors') if isinstance(d.get('errors'), list) else []
    out['errors'] = [_text(e, 200) for e in errs[:5] if _text(e, 200)]
    return out


def _images(raw):
    """[(bytes, ext)] from data: URLs, or an error for the learner."""
    raw = raw if isinstance(raw, list) else []
    if len(raw) > MAX_IMAGES:
        return None, f'最多 {MAX_IMAGES} 张截图'
    out = []
    for item in raw:
        m = re.fullmatch(r'data:image/(?:jpeg|png);base64,([A-Za-z0-9+/=\s]+)', item if isinstance(item, str) else '')
        if not m:
            return None, '截图只能是图片（JPEG 或 PNG）'
        try:
            data = base64.b64decode(m.group(1), validate=False)
        except (binascii.Error, ValueError):
            return None, '截图读不出来，请换一张'
        ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
        if not ext:
            return None, '截图只能是图片（JPEG 或 PNG）'
        if len(data) > MAX_IMAGE_BYTES:
            return None, '截图太大了，请换一张或裁小一点'
        out.append((data, ext))
    return out, None


def submit(c, data, address, user_id=None, now=None):
    """Store one report. user_id only when the request carried the session's CSRF token (see app.py)."""
    now = now or time.time()
    if data.get('website'):  # honeypot: a bot fills every field; pretend success, store nothing
        return {'ok': True}, 200
    kind = data.get('kind') if data.get('kind') in KINDS else 'other'
    text = _text(data.get('text'), MAX_TEXT + 1)
    if len(text) < MIN_TEXT:
        return {'error': f'请写几句发生了什么（至少 {MIN_TEXT} 个字）'}, 400
    if len(text) > MAX_TEXT:
        return {'error': f'说明请控制在 {MAX_TEXT} 字以内'}, 400
    images, problem = _images(data.get('images'))
    if problem:
        return {'error': problem}, 400
    page = _text(data.get('page'), 200)
    if page and not page.startswith(('#/', '/')):
        page = ''
    day = _day(now)
    c.execute('BEGIN IMMEDIATE')
    c.execute('DELETE FROM feedback_limits WHERE day<?', (_day(now - 2 * 86400),))
    if c.execute('SELECT COUNT(*) FROM feedback WHERE day=?', (day,)).fetchone()[0] >= DAILY_TOTAL:
        c.rollback()
        return {'error': '今天收到的反馈太多了，请明天再试'}, 429
    if user_id:
        if c.execute('SELECT COUNT(*) FROM feedback WHERE user_id=? AND day=?', (user_id, day)).fetchone()[0] >= USER_DAILY:
            c.rollback()
            return {'error': f'今天已经提交了 {USER_DAILY} 条，谢谢！明天再来吧'}, 429
    else:
        key = __import__('survey_service').client_key('feedback|' + str(address), day)
        used = c.execute('SELECT count FROM feedback_limits WHERE key=? AND day=?', (key, day)).fetchone()
        if used and used[0] >= GUEST_DAILY:
            c.rollback()
            return {'error': f'今天已经提交了 {GUEST_DAILY} 条，谢谢！登录后可以再提交'}, 429
        c.execute('INSERT INTO feedback_limits VALUES(?,?,1) ON CONFLICT(key,day) DO UPDATE SET count=count+1', (key, day))
    rid = c.execute('INSERT INTO feedback(created, day, user_id, kind, text, contact, page, release, device) VALUES(?,?,?,?,?,?,?,?,?)',
                    (now, day, user_id, kind, text, _text(data.get('contact'), 100), page, _release(),
                     json.dumps(_device(data.get('device')), ensure_ascii=False))).lastrowid
    c.commit()
    names = []
    if images:
        d = folder() / str(rid)
        try:
            d.mkdir(parents=True, exist_ok=True)
            for k, (blob, ext) in enumerate(images, 1):
                (d / f'{k}.{ext}').write_bytes(blob)
                names.append(f'{k}.{ext}')
        except OSError:
            pass  # the words still count; the console shows how many screenshots arrived
        c.execute('UPDATE feedback SET images=? WHERE id=?', (json.dumps(names), rid))
        c.commit()
    return {'ok': True, 'id': rid, 'images': len(names)}, 200


def listing(c, status='new', page=1, per_page=20):
    """Reports for the console, newest first, with who sent them (an account name, or 游客)."""
    where, args = ('WHERE f.status=?', [status]) if status in STATUS else ('', [])
    page = max(1, int(page or 1))
    rows = c.execute(f'SELECT f.*, u.username FROM feedback f LEFT JOIN users u ON u.id=f.user_id {where} ORDER BY f.id DESC LIMIT ? OFFSET ?',
                     args + [per_page, (page - 1) * per_page]).fetchall()
    counts = {k: c.execute('SELECT COUNT(*) FROM feedback WHERE status=?', (k,)).fetchone()[0] for k in STATUS}
    items = []
    for r in rows:
        r = dict(r)
        items.append({'id': r['id'], 'created': r['created'], 'kind': r['kind'], 'kind_label': KINDS.get(r['kind'], r['kind']),
                      'text': r['text'], 'contact': r['contact'], 'page': r['page'], 'release': r['release'],
                      'device': json.loads(r['device'] or '{}'), 'images': json.loads(r['images'] or '[]'),
                      'who': r['username'] or ('（账号已删除）' if r['user_id'] else '游客'), 'status': r['status'],
                      'status_label': STATUS.get(r['status'], r['status']), 'handled_by': r['handled_by'], 'handled_at': r['handled_at']})
    total = counts['new'] + counts['done'] if status not in STATUS else counts[status]
    return {'items': items, 'counts': counts, 'page': page, 'pages': max(1, -(-total // per_page))}


def image(rid, name):
    """(bytes, mime) of one screenshot, or None. The name must be one this module wrote (1.jpg … 3.png)."""
    m = re.fullmatch(r'([1-3])\.(jpg|png)', name or '')
    if not m or not str(rid).isdigit():
        return None
    f = folder() / str(int(rid)) / name
    try:
        return f.read_bytes(), MIME[m.group(2)]
    except OSError:
        return None


def set_status(c, rid, status, who):
    if status not in STATUS:
        return {'error': '状态不正确'}, 400
    n = c.execute('UPDATE feedback SET status=?, handled_by=?, handled_at=? WHERE id=?',
                  (status, who if status == 'done' else '', time.time() if status == 'done' else None, int(rid))).rowcount
    c.commit()
    return ({'ok': True}, 200) if n else ({'error': '没有这条反馈'}, 404)


def open_count(c):
    return c.execute("SELECT COUNT(*) FROM feedback WHERE status='new'").fetchone()[0]
