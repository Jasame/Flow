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

What the 隐私说明 says about where data is and which AI sees what is in public/guide/guide.md (# 隐私和数据).
"""
import time

AGES = {'u14': '不满 14 岁', '14-17': '14–17 岁', '18+': '18 岁及以上'}
WHY = '只问年龄段，不问生日：用来决定怎么保护未成年人的信息。'
NEED_GUARDIAN = '不满 14 岁需要先告诉家长（或监护人）并得到同意：你写的作文和说的录音会交给 AI 批改。'
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
    return {'ok': True, **info(c.execute('SELECT age_band, guardian_ok FROM users WHERE id=?', (uid,)).fetchone())}, 200


def info(u):
    """For the page (session_info): the band and whether a guardian's agreement is on record."""
    keys = u.keys() if u is not None and hasattr(u, 'keys') else ()
    band = u['age_band'] if 'age_band' in keys else None
    return {'age': band, 'guardian': bool(u['guardian_ok']) if 'guardian_ok' in keys else False}


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
