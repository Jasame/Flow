"""年龄段和监护人同意 (2026-11-24): the minimum for learners under 18, as little information as possible.

- The age is asked as a band, never a birthday: 不满 14 岁 / 14–17 岁 / 18 岁及以上 (users.age_band 'u14' / '14-17' /
  '18+'). Asked at sign-up (the form always sends it); an account without one is asked once the next time it opens the
  site (POST /api/account/age), and before joining a class (class_service.join).
- 不满 14 岁 needs the learner to tick 「已经告诉家长（或监护人），他们同意我用语流」 (users.guardian_ok: when). Without
  it, sign-up with that band is refused; an existing account that says 不满 14 岁 without it keeps everything except the
  features that hand what the learner wrote or said to an AI model (GUARDED): those answer 403 code 'guardian' until it
  is ticked. Shared material (a sentence explained, examples, the 今日热点 search) is not the learner's own and stays.
- The band shows in the xmc.hk console (管理员). Nothing public or shared carries a learner's name (the share pictures
  and the class summary have none); 导出我的数据 has the band; 注销账号 deletes it with the account.

数据存放在香港的单独同意 (2026-11-25; the user, with 语流 23's advice that storing learners' data in Hong Kong is very
likely 个人信息出境): a separate tick, never bundled with anything else.
- Sign-up (learner or teacher) needs it (data.storage is True): users.storage_ok, when. Without it no account is made,
  since the account itself is stored there.
- An account from before has none: it is asked once, on a page of its own, before anything else (the page, 81-privacy.js).
- 不同意 or 撤回同意 (我的 → 账号 → 数据存放): users.storage_no, when (the user's choices 2026-11-25: 暂停这个账号, and after
  PAUSE_DAYS the account and its data are deleted: 个保法第四十七条, 语流 23). A paused or
  not-yet-asked account gets nothing of its learning: every signed-in request answers 403 code 'storage' except
  STORAGE_OPEN (agree again, export, delete the account, sign out, change the password), and /api/next/home is a
  guest's. A paused account (storage_no) gets no mail (weekly progress, review reminders) and is out of every class
  number (class_service). Its data is kept PAUSE_DAYS for agreeing again or exporting, then deleted (the deletion job is
  a follow-up, due before the first pause reaches PAUSE_DAYS).
- Every answer is kept in consent_events (when, agree or not, which wording: STORAGE_VERSION), for the console.

What the 隐私说明 says about where data is and which AI sees what is in public/guide/guide.md (# 隐私和数据).
"""
import time

AGES = {'u14': '不满 14 岁', '14-17': '14–17 岁', '18+': '18 岁及以上'}
WHY = '只问年龄段，不问生日：用来决定怎么保护未成年人的信息。'
NEED_GUARDIAN = '不满 14 岁需要先告诉家长（或监护人）并得到同意：你的账号和学习数据存放在香港的服务器上，你写的作文和说的录音会交给 AI 批改（录音不保存）。'
# what a learner wrote or said, handed to an AI model (next_service.AI_PATHS minus shared material, and the older
# AI pages, ai_stream.PATHS, which all carry the learner's own words)
GUARDED = {'/api/next/assess/speaking', '/api/next/assess/writing', '/api/next/rewrite', '/api/next/shadow', '/api/next/retell',
           '/api/next/dialog', '/api/next/essay', '/api/next/translate', '/api/next/say', '/api/next/ielts', '/api/next/import/enrich',
           '/api/ai/help', '/api/chat', '/api/coach/chat', '/api/lab/feedback', '/api/lab/audio', '/api/vocab/feedback'}


def schema(c):
    cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
    if 'age_band' not in cols:
        c.execute('ALTER TABLE users ADD COLUMN age_band TEXT')
    if 'guardian_ok' not in cols:
        c.execute('ALTER TABLE users ADD COLUMN guardian_ok REAL')
    if 'age_set' not in cols:
        c.execute('ALTER TABLE users ADD COLUMN age_set REAL')
    for col in ('storage_ok', 'storage_no'):  # 数据存放在香港: when agreed / when declined or withdrawn
        if col not in cols:
            c.execute(f'ALTER TABLE users ADD COLUMN {col} REAL')
    c.execute('CREATE TABLE IF NOT EXISTS consent_events(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), '
              'kind TEXT NOT NULL, agree INTEGER NOT NULL, version TEXT NOT NULL, created REAL NOT NULL)')


def _parse(data, required, strict=True):
    """(band, guardian, error). band None when not given and not required. strict: 不满 14 岁 must come with the
    guardian's agreement ticked (sign-up); not strict, it is kept without (the account then waits on GUARDED)."""
    band = str(data.get('age') or '').strip()
    if not band:
        if required:
            return None, None, ({'error': '请选一个年龄段', 'field': 'age', 'code': 'age'}, 400)
        return None, False, None
    if band not in AGES:
        return None, None, ({'error': '请选一个年龄段', 'field': 'age', 'code': 'age'}, 400)
    guardian = data.get('guardian') is True
    if band == 'u14' and not guardian and strict:
        return None, None, ({'error': NEED_GUARDIAN + '勾选后才能继续。', 'field': 'guardian', 'code': 'guardian'}, 400)
    return band, guardian, None


def check_signup(data):
    """Before an account is made: an error answer, or None. The sign-up form always sends the band; an older page or
    another client that sends none still signs up and is asked when it next opens the site."""
    return _parse(data, False)[2]


def store(c, uid, data, now=None):
    """After sign-up (data already checked): keep the band and, under 14, when the guardian's agreement was ticked."""
    band, guardian, err = _parse(data, False)
    if err or not band:
        return
    now = now or time.time()
    c.execute('UPDATE users SET age_band=?, age_set=?, guardian_ok=? WHERE id=?', (band, now, now if band == 'u14' and guardian else None, uid))
    c.commit()


def set_age(c, uid, data):
    """POST /api/account/age {age, guardian}: the band asked later (an older account, or changed in 我的), or the
    guardian's agreement ticked when a GUARDED feature asked for it. Under 14 without it is kept too: everything but
    GUARDED goes on, and those ask again."""
    band, guardian, err = _parse(data, True, strict=False)
    if err:
        return err
    now = time.time()
    row = c.execute('SELECT guardian_ok FROM users WHERE id=?', (uid,)).fetchone()
    kept = row['guardian_ok'] if row else None
    c.execute('UPDATE users SET age_band=?, age_set=?, guardian_ok=? WHERE id=?',
              (band, now, (kept or now) if band == 'u14' and guardian else None, uid))
    c.commit()
    return {'ok': True, **info(c.execute('SELECT age_band, guardian_ok, storage_ok, storage_no FROM users WHERE id=?', (uid,)).fetchone())}, 200


def info(u):
    """For the page (session_info): the band, whether a guardian's agreement is on record, and the answer about
    storage in Hong Kong ('ok', 'no', or None: not asked yet)."""
    keys = u.keys() if u is not None and hasattr(u, 'keys') else ()
    band = u['age_band'] if 'age_band' in keys else None
    out = {'age': band, 'guardian': bool(u['guardian_ok']) if 'guardian_ok' in keys else False}
    if 'storage_ok' in keys:  # a row read without the columns says nothing about it (the page keeps what it knows)
        out['storage'] = storage(u)
        if out['storage'] == 'no':  # the day the paused account goes (Beijing date)
            import datetime
            out['storage_until'] = datetime.datetime.fromtimestamp(u['storage_no'] + PAUSE_DAYS * 86400, datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
    return out


# ---------------------------------------------------------------- 数据存放在香港 (the separate consent)

STORAGE_TEXT = '我同意语流在香港的服务器上存放和处理我的账号和学习数据'
STORAGE_VERSION = '2026-11-25'  # the wording agreed to (STORAGE_TEXT and its note in 81-privacy.js); a new wording, a new version
PAUSE_DAYS = 30
STORAGE_OPEN = {'/api/account/storage', '/api/account/delete', '/api/logout', '/api/password'}
STORAGE_HELD = ({'error': '这个账号还没有同意把数据存放在香港的服务器上，学习暂停了。同意以后就能继续；也可以导出数据或注销账号。',
                 'code': 'storage'}, 403)


def storage(u):
    """'ok' (agreed), 'no' (declined or withdrawn: the account is paused) or None (an older account, not asked yet)."""
    keys = u.keys() if u is not None and hasattr(u, 'keys') else ()
    if 'storage_ok' in keys and u['storage_ok']:
        return 'ok'
    return 'no' if 'storage_no' in keys and u['storage_no'] else None


def check_storage(data):
    """Before an account is made: the separate tick is required (an error answer, or None)."""
    if data.get('storage') is True:
        return None
    return {'error': '注册前，请先勾选同意把账号和学习数据存放在香港的服务器上', 'field': 'storage', 'code': 'storage'}, 400


def _event(c, uid, agree, now):
    c.execute("INSERT INTO consent_events(user_id, kind, agree, version, created) VALUES(?, 'storage', ?, ?, ?)", (uid, int(agree), STORAGE_VERSION, now))


def agreed(c, uid, now=None):
    """The account just made agreed (sign-up, in its transaction: no commit here)."""
    now = now or time.time()
    c.execute('UPDATE users SET storage_ok=?, storage_no=NULL WHERE id=?', (now, uid))
    _event(c, uid, True, now)


def set_storage(c, uid, data):
    """POST /api/account/storage {agree}: agree (again), or decline / withdraw: the account is paused."""
    now, agree = time.time(), data.get('agree') is True
    c.execute('UPDATE users SET storage_ok=?, storage_no=? WHERE id=?', (now if agree else None, None if agree else now, uid))
    _event(c, uid, agree, now)
    c.commit()
    return {'ok': True, **info(c.execute('SELECT age_band, guardian_ok, storage_ok, storage_no FROM users WHERE id=?', (uid,)).fetchone())}, 200


def storage_held(u, path):
    """403 for any signed-in request but STORAGE_OPEN while the account has not agreed; else None."""
    if storage(u) != 'ok' and path not in STORAGE_OPEN:
        return STORAGE_HELD
    return None


def needs_guardian(u):
    i = info(u)
    return i['age'] == 'u14' and not i['guardian']


def gate(u, path):
    """403 for a feature that hands the learner's own words or voice to an AI model, while an account under 14 has
    no guardian's agreement on record; else None."""
    if path in GUARDED and needs_guardian(u):
        return {'error': '这一步会把你写的或说的交给 AI 处理。不满 14 岁需要先告诉家长（或监护人）并得到同意，在弹出的窗口里勾选后就能用。',
                'code': 'guardian'}, 403
    return None


def label(band):
    return AGES.get(band or '', '没填')
