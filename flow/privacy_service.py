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
  number (class_service). Its data is kept PAUSE_DAYS for agreeing again or exporting, then deleted: purge_paused, from
  the reminder loop in app.py, once the day the page names (storage_until) is over. It only reports until the user has
  seen the numbers and FLOW_PURGE_PAUSED=on is set, and it deletes only while the daily backup is fresh.
- Every answer is kept in consent_events (when, agree or not, which wording: STORAGE_VERSION), for the console.

What the 隐私说明 says about where data is and which AI sees what is in public/guide/guide.md (# 隐私和数据).
"""
import os
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
    for col in ('storage_ok', 'storage_no', 'terms_ok'):  # 数据存放在香港: when agreed / declined or withdrawn; 用户协议: when agreed
        if col not in cols:
            c.execute(f'ALTER TABLE users ADD COLUMN {col} REAL')
    if 'terms_version' not in cols:  # which 用户协议 and 隐私和数据 (CONSENT_VERSION) were agreed to
        c.execute('ALTER TABLE users ADD COLUMN terms_version TEXT')
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
    if 'terms_version' in keys:
        out['terms'] = terms(u)
    return out


# ---------------------------------------------------------------- 数据存放在香港 (the separate consent)

STORAGE_TEXT = '我同意语流在香港的服务器上存放和处理我的账号和学习数据'
STORAGE_VERSION = '2026-11-26'  # the wording agreed to (81-privacy.js: CONSENT_LEAD at sign-up and on the asked page, STORAGE_TEXT
# alone where only the storage is missing); a new wording, a new version. Older answers keep theirs: nobody is asked again.
PAUSE_DAYS = 30
STORAGE_OPEN = {'/api/account/storage', '/api/account/terms', '/api/account/delete', '/api/logout', '/api/password'}
STORAGE_HELD = ({'error': '这个账号还没有同意把数据存放在香港的服务器上，学习暂停了。同意以后就能继续；也可以导出数据或注销账号。',
                 'code': 'storage', 'need': 'storage'}, 403)


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


def _event(c, uid, agree, now, kind='storage', version=STORAGE_VERSION):
    c.execute('INSERT INTO consent_events(user_id, kind, agree, version, created) VALUES(?, ?, ?, ?, ?)', (uid, kind, int(agree), version, now))


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
    return {'ok': True, **info(c.execute('SELECT age_band, guardian_ok, storage_ok, storage_no, terms_version FROM users WHERE id=?', (uid,)).fetchone())}, 200


def gone_at(paused):
    """When a paused account goes: the end of the Beijing day PAUSE_DAYS after it was paused (the day the page names,
    「……以前」, is the learner's whole)."""
    import datetime
    bj = datetime.timezone(datetime.timedelta(hours=8))
    day = datetime.datetime.fromtimestamp(paused + PAUSE_DAYS * 86400, bj).date() + datetime.timedelta(days=1)
    return datetime.datetime(day.year, day.month, day.day, tzinfo=bj).timestamp()


PURGE_SWITCH = 'FLOW_PURGE_PAUSED'  # 'on': delete for real; anything else (the default): report only
BACKUP_FRESH_HOURS = 36  # the daily backup runs at 03:15: the last good one is never older than this on a normal day


def purge_on():
    """Whether paused accounts are really deleted. Off by default: the job only reports. The user turns it on (A1 sets
    FLOW_PURGE_PAUSED=on in the site's environment) after seeing the report's numbers (A0, 2026-11-26)."""
    return os.getenv(PURGE_SWITCH, '').strip().lower() in ('on', '1', 'yes')


def _bj_day(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')


def paused_due(c, now=None):
    """[(id, storage_no)] of the accounts whose pause has run out (gone_at passed), oldest first; never a staff account."""
    now = time.time() if now is None else now
    if 'storage_no' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
        return []
    return [(r['id'], r['storage_no']) for r in c.execute(
        'SELECT id, storage_no FROM users WHERE storage_no IS NOT NULL AND storage_ok IS NULL AND COALESCE(admin, 0)=0 '
        'ORDER BY storage_no').fetchall() if gone_at(r['storage_no']) <= now]


def backup_fresh(now=None):
    """The daily backup is there to fall back on: its last run succeeded within BACKUP_FRESH_HOURS (data/backup-status.json,
    written by ops.py backup). A deletion waits while it is not."""
    now = time.time() if now is None else now
    st = __import__('flow_admin').backup_status()
    return bool(st and st.get('ok') and now - float(st.get('created') or 0) <= BACKUP_FRESH_HOURS * 3600)


def paused_report(c, now=None):
    """For the console (运维 → 任务): how many accounts are paused, how many have run out and when they were paused (Beijing
    dates, never names), whether deletion is switched on, and whether the backup is fresh."""
    now = time.time() if now is None else now
    if 'storage_no' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
        return {'paused': 0, 'due': 0, 'due_days': [], 'on': purge_on(), 'backup_ok': backup_fresh(now)}
    paused = c.execute('SELECT COUNT(*) FROM users WHERE storage_no IS NOT NULL AND storage_ok IS NULL AND COALESCE(admin, 0)=0').fetchone()[0]
    due = paused_due(c, now)
    return {'paused': paused, 'due': len(due), 'due_days': sorted({_bj_day(t) for _, t in due}), 'on': purge_on(),
            'backup_ok': backup_fresh(now)}


def _log_once_today(c, action, detail, now):
    """One line a Beijing day for the same report (the loop runs every 5 minutes)."""
    import datetime
    bj = datetime.timezone(datetime.timedelta(hours=8))
    d = datetime.datetime.fromtimestamp(now, bj).date()
    start = datetime.datetime(d.year, d.month, d.day, tzinfo=bj).timestamp()
    if c.execute('SELECT 1 FROM flow_admin_log WHERE action=? AND detail=? AND created>=?', (action, detail[:300], start)).fetchone():
        return
    c.execute('INSERT INTO flow_admin_log(created, email, role, action, target, detail) VALUES(?,?,?,?,?,?)',
              (now, '语流（自动）', 'system', action, '', detail[:300]))  # as flow_admin.log_action, dated by the same clock
    c.commit()


def purge_paused(c, now=None, data_dir=None):
    """隐私和数据: 30 天后还没有重新同意，语流会删除这个账号和数据. The accounts paused_due finds (declined or withdrawn,
    not agreed since, the day the page names over; never staff):
    - switch off (the default, purge_on): nothing is deleted; once a day the console's log says how many and when they
      were paused (account-purge-report), and 运维 → 任务 shows the same (paused_report);
    - switch on, but the daily backup not fresh (backup_fresh): nothing is deleted; once a day the log says why
      (account-purge-held);
    - switch on and the backup fresh: each is deleted as 注销账号 deletes one (account_data.forget); the backups lose
      their copy within their 14 days. One log line each (account-purge), with the account's number only.
    Returns how many were deleted."""
    now = time.time() if now is None else now
    due = paused_due(c, now)
    if not due:
        return 0
    days = '、'.join(sorted({_bj_day(t) for _, t in due}))
    if not purge_on():
        _log_once_today(c, 'account-purge-report', f'{len(due)} 个账号暂停满 30 天，等待删除（暂停日期：{days}）；自动删除没有打开，没有删', now)
        return 0
    if not backup_fresh(now):
        _log_once_today(c, 'account-purge-held', f'{len(due)} 个账号暂停满 30 天，但最近一次数据库备份不在或失败，今天没有删', now)
        return 0
    import account_data, flow_admin
    for uid, _ in due:
        account_data.forget(c, uid, data_dir)
        flow_admin.log_action(c, {'email': '语流（自动）', 'role': 'system'}, 'account-purge', f'账号 #{uid}',
                              '不同意或撤回「数据存放在香港」满 30 天，没有重新同意')
    return len(due)


def storage_held(u, path):
    """403 for any signed-in request but STORAGE_OPEN while the account has not agreed (to the storage in Hong Kong or
    to the current 用户协议 and 隐私和数据); else None."""
    if path in STORAGE_OPEN:
        return None
    if storage(u) != 'ok':
        return STORAGE_HELD
    return TERMS_HELD if terms(u) != 'ok' else None


def consented(u):
    """Both answers on record: the account's learning may be processed."""
    return storage(u) == 'ok' and terms(u) == 'ok'


# ---------------------------------------------------------------- 用户协议和隐私说明 (the basic agreement, 2026-11-25)
# The user's choice (A0, card): a short 用户协议, agreed together with 隐私和数据 in one tick at sign-up, next to (never
# merged with) the separate 数据存放在香港 tick. An older account, or one that agreed to an earlier version, is asked
# once on the same page as the storage question. A new version of either text (its 生效日期, guide.md) asks everyone
# again: tests/test_privacy.py keeps TERMS_VERSION and PRIVACY_VERSION equal to the two chapters' 生效日期.

TERMS_DRAFT = '0-draft'          # the 用户协议 text is not approved yet: this version is never shipped (test_privacy)
TERMS_VERSION = '2026-11-25'     # # 语流用户协议 {#terms}: its 生效日期 (the owner approved the text, 「可以上线」, 2026-11-25)
PRIVACY_VERSION = '2026-11-25'   # # 隐私和数据 {#privacy}: its 生效日期
CONSENT_VERSION = f'{TERMS_VERSION}/{PRIVACY_VERSION}'
TERMS_TEXT = '我已阅读并同意《用户协议》和《隐私和数据》'
# code 'storage' for both holds, 'need' says which answer is missing: the Android App 1.0.1 and 1.0.2 out there pause
# their reminders on code 'storage' only (C2), so a new code would leave them reminding from stale numbers.
TERMS_HELD = ({'error': '请先阅读并同意《用户协议》和《隐私和数据》，同意以后就能继续；也可以导出数据或注销账号。', 'code': 'storage', 'need': 'terms'}, 403)


def terms(u):
    """'ok' when the account agreed to the current CONSENT_VERSION, else None (never asked, or an earlier version)."""
    keys = u.keys() if u is not None and hasattr(u, 'keys') else ()
    return 'ok' if 'terms_version' in keys and u['terms_version'] == CONSENT_VERSION else None


def check_terms(data):
    """Before an account is made: the 用户协议 and 隐私和数据 tick is required (an error answer, or None)."""
    if data.get('terms') is True:
        return None
    return {'error': '注册前，请先阅读并勾选同意《用户协议》和《隐私和数据》', 'field': 'terms', 'code': 'terms'}, 400


def agreed_terms(c, uid, now=None):
    """The account (just made, or asked again) agreed to CONSENT_VERSION. No commit here."""
    now = now or time.time()
    c.execute('UPDATE users SET terms_ok=?, terms_version=? WHERE id=?', (now, CONSENT_VERSION, uid))
    _event(c, uid, True, now, 'terms', CONSENT_VERSION)


def set_terms(c, uid, data):
    """POST /api/account/terms {agree: true}: the current version agreed. There is nothing to decline: without it the
    account stays held (only export, delete, sign out, the password)."""
    if data.get('agree') is not True:
        return {'error': '勾选同意以后才能继续', 'field': 'terms', 'code': 'terms'}, 400
    agreed_terms(c, uid)
    c.commit()
    return {'ok': True, **info(c.execute('SELECT age_band, guardian_ok, storage_ok, storage_no, terms_version FROM users WHERE id=?', (uid,)).fetchone())}, 200


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
