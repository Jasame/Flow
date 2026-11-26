"""新手引导 (the owner, 2026-11-25: 「加入首次使用引导」): a few steps that point at the real buttons of 今日 (or, for a
老师账号, of 我的班级) the first time a new account opens it. Once per account, kept here so another phone or computer
does not show it again; 我的 → 帮助 → 「再看一遍新手引导」 plays it again without counting.

What is counted is the whole only: how many finished it, how many skipped it and at which step. The table of counts
has no account in it; next_tours only says, per account, that its tour is behind it.
"""
import datetime, os, time

TOURS = {'learner': 13, 'teacher': 3}  # name: steps (新手引导 v2: up to 13 for a new learner, 08-intro.js)
# Accounts made before the tour existed never see it (they know the pages); FLOW_TOUR_FROM moves the date (the UI tests
# set it far ahead and give the tour to their own learner only).
TOUR_FROM = float(os.getenv('FLOW_TOUR_FROM') or datetime.datetime(2026, 11, 25, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp())


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS next_tours(user_id INTEGER NOT NULL, tour TEXT NOT NULL, result TEXT NOT NULL,
      created REAL NOT NULL, PRIMARY KEY(user_id, tour));
    CREATE TABLE IF NOT EXISTS next_tour_stats(tour TEXT NOT NULL, result TEXT NOT NULL, step INTEGER NOT NULL, n INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(tour, result, step));''')


def _account(c, uid):
    r = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not r:
        return None, None
    keys = r.keys()
    return (r['created'] if 'created' in keys else None), (r['role'] if 'role' in keys else None)


def due(c, uid):
    """{learner: bool, teacher: bool}: the tour this account has not seen yet. A guest has none (a tour is per account:
    after signing up, 今日 shows it)."""
    out = {k: False for k in TOURS}
    if not uid:
        return out
    created, role = _account(c, uid)
    seen = {r['tour']: r['result'] for r in c.execute('SELECT tour, result FROM next_tours WHERE user_id=?', (uid,))}
    pending = {t for t, res in seen.items() if res == 'pending'}  # given on purpose (the UI tests' learner)
    new = created is not None and created >= TOUR_FROM
    out['teacher'] = role == 'teacher' and ('teacher' in pending or (new and 'teacher' not in seen))
    out['learner'] = role != 'teacher' and ('learner' in pending or (new and 'learner' not in seen))
    return out


def record(c, uid, data):
    """The tour's end: {tour, result: 'done' | 'skip', step (1-based, where it ended), again: true for 再看一遍}. The
    first end marks the account and counts once; 再看一遍 is neither marked nor counted."""
    tour, result = data.get('tour'), data.get('result')
    if tour not in TOURS or result not in ('done', 'skip'):
        return {'error': '参数不对'}, 400
    step = data.get('step') if type(data.get('step')) is int and 1 <= data.get('step') <= TOURS[tour] else 1
    if not uid or data.get('again'):
        return {'ok': True, 'counted': False}, 200
    row = c.execute('SELECT result FROM next_tours WHERE user_id=? AND tour=?', (uid, tour)).fetchone()
    if row and row['result'] != 'pending':
        return {'ok': True, 'counted': False}, 200
    c.execute('INSERT INTO next_tours(user_id, tour, result, created) VALUES(?,?,?,?) ON CONFLICT(user_id, tour) DO UPDATE SET result=excluded.result, created=excluded.created',
              (uid, tour, result, time.time()))
    c.execute('INSERT INTO next_tour_stats(tour, result, step, n) VALUES(?,?,?,1) ON CONFLICT(tour, result, step) DO UPDATE SET n=n+1',
              (tour, result, step if result == 'skip' else TOURS[tour]))
    c.commit()
    return {'ok': True, 'counted': True}, 200


# 使用提示 (the user, 2026-11-25: 「第一次用时提示，记在账号上，换设备不再重复出；我的 → 帮助里能重看」): a line said the
# first time a page is used, where an instruction used to stay for good (「点词查词…」 on 读), put away with 知道了 and not
# said again on any phone or computer. 我的 → 帮助 → 更多 →「重新显示使用提示」 brings them all back. Kept in next_tours as
# 'tip:<name>' rows (no counts: a tip is not a tour); due() and the stats look at TOURS only.
# 一次性入口 (the user, 2026-11-26: 「第一次用才需要的按钮，点过一次就不要再出现」) are kept the same way: guide (「第一次用？看
# 操作指南」 on 今日 and 练习), review-zones / review-zones-back (the review card's left, middle and right, front and back),
# swipe-tip (「右滑认识」 on the first review), know-side (「『认识』换到右边了」), beta-note / beta-hello (the 内测版's line
# and its once-only sheet).
TIPS = ('read', 'listen', 'guide', 'review-zones', 'review-zones-back', 'swipe-tip', 'know-side', 'beta-note', 'beta-hello')


def tips(c, uid):
    """{seen: [name]}: the tips this account has put away. A guest: none (its browser keeps them)."""
    if not uid:
        return {'seen': []}
    return {'seen': sorted(r['tour'][4:] for r in c.execute("SELECT tour FROM next_tours WHERE user_id=? AND tour LIKE 'tip:%'", (uid,)))}


def tip(c, uid, data):
    """{tip: name} puts one away; {tip: name, seen: false} brings that one back (「下次复习时再看一次」); {reset: true}
    brings them all back."""
    if data.get('reset') is True:
        if uid:
            c.execute("DELETE FROM next_tours WHERE user_id=? AND tour LIKE 'tip:%'", (uid,)); c.commit()
        return {'seen': []}, 200
    name = data.get('tip')
    if name not in TIPS:
        return {'error': '参数不对'}, 400
    if uid and data.get('seen') is False:
        c.execute('DELETE FROM next_tours WHERE user_id=? AND tour=?', (uid, 'tip:' + name)); c.commit()
    elif uid:
        c.execute('INSERT OR IGNORE INTO next_tours(user_id, tour, result, created) VALUES(?,?,?,?)', (uid, 'tip:' + name, 'seen', time.time())); c.commit()
    return tips(c, uid), 200


def stats(c):
    """The counts, for 后台: {tour: {done, skipped, skipped_at: {step: n}}}."""
    out = {t: {'done': 0, 'skipped': 0, 'skipped_at': {}} for t in TOURS}
    for r in c.execute('SELECT tour, result, step, n FROM next_tour_stats'):
        o = out.setdefault(r['tour'], {'done': 0, 'skipped': 0, 'skipped_at': {}})
        if r['result'] == 'done':
            o['done'] += r['n']
        else:
            o['skipped'] += r['n']; o['skipped_at'][r['step']] = o['skipped_at'].get(r['step'], 0) + r['n']
    return out
