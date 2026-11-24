"""复听: a text learned a few days ago, heard again without the words, then rated by how much was understood.

Spaced like the word reviews, but for whole texts. The first time 3 days after the text was studied (its first step
of 读, 理解 or 用出来); then 7 and 21 days after the last listen that was mostly understood. A listen where half or
less was understood brings the text back after 3 days, without moving on. After three good listens the text is
known and is not brought back. Texts studied more than 60 days ago (counting the last listen) are left alone.

One text a day, in 今日 (skills_service.daily_path): the one waiting longest. The listen page (#/m/<id>/listen/again)
starts with the text hidden, asks how much was understood, then shows the text for the sentences that were missed.
A listen counts as a study day for 每周目标 (next_service.habit) and in the weekly report (skills_service.report).
"""
import time

STEPS = (3, 7, 21)  # days to the next listen after 0, 1 and 2 good listens
AGAIN = 3           # days to the next listen after one where half or less was understood
LOOKBACK = 60       # days: texts studied longer ago are not brought back
LABELS = ('很少', '一半左右', '大部分', '几乎都懂')  # understood: 0..3; 2 and 3 are good listens
SAME_VISIT = 600    # seconds: a second rating of the same text this soon replaces the first


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS next_relisten(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), '
              'pack TEXT NOT NULL, understood INTEGER NOT NULL, created REAL NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS next_relisten_user ON next_relisten(user_id, pack, created)')


def next_time(first, listens):
    """When this text should be heard again (None: known, no more), from when it was first studied and its listens
    [(understood, created)] in order; and how many good listens it has had."""
    good, last, missed = 0, first, False
    for understood, created in listens:
        last, missed = created, understood < 2
        if not missed:
            good += 1
    if good >= len(STEPS):
        return None, good
    return last + (AGAIN if missed else STEPS[good]) * 86400, good


def _studied(c, uid):
    """{pack: when it was first studied}: the texts read, checked or used, with any step."""
    return {r[0]: r[1] for r in c.execute("SELECT pack, MIN(created) FROM next_progress WHERE user_id=? AND step IN ('read','check','output') GROUP BY pack", (uid,))}


def _listens(c, uid, pack=None):
    out = {}
    q = 'SELECT pack, understood, created FROM next_relisten WHERE user_id=?' + (' AND pack=?' if pack else '') + ' ORDER BY created, id'
    for p, u, t in c.execute(q, (uid, pack) if pack else (uid,)):
        out.setdefault(p, []).append((u, t))
    return out


def due(c, uid, now=None, exclude=()):
    """The texts waiting to be heard again, the longest waiting first: [{'pack', 'first', 'due', 'times', 'good'}]."""
    import next_service as nx
    now = now or time.time()
    listens = _listens(c, uid)
    out = []
    for pack, first in _studied(c, uid).items():
        ls = listens.get(pack, [])
        if pack in exclude or max([first] + [t for _, t in ls]) < now - LOOKBACK * 86400:
            continue
        when, good = next_time(first, ls)
        if when is not None and when <= now and nx._pack_row(c, uid, pack):
            out.append({'pack': pack, 'first': first, 'due': when, 'times': len(ls), 'good': good})
    return sorted(out, key=lambda x: x['due'])


def today(c, uid, start):
    """This day's listens, latest last: [{'pack', 'understood', 'created'}]."""
    return [dict(r) for r in c.execute('SELECT pack, understood, created FROM next_relisten WHERE user_id=? AND created>=? ORDER BY created, id', (uid, start))]


def record(c, uid, data, now=None):
    """POST /api/next/relisten {pack, understood 0–3}: one listen, and when the text comes back."""
    import next_service as nx
    now = now or time.time()
    pack, understood = str(data.get('pack', ''))[:120], data.get('understood')
    if type(understood) is not int or not 0 <= understood <= 3:
        return {'error': '听懂了多少？选一项就好'}, 400
    if not nx._pack_row(c, uid, pack):
        return {'error': '材料不存在'}, 404
    again = c.execute('SELECT id FROM next_relisten WHERE user_id=? AND pack=? AND created>? ORDER BY created DESC LIMIT 1', (uid, pack, now - SAME_VISIT)).fetchone()
    if again:  # changed their mind on the same visit: the latest answer stands
        c.execute('UPDATE next_relisten SET understood=? WHERE id=?', (understood, again[0]))
    else:
        c.execute('INSERT INTO next_relisten(user_id, pack, understood, created) VALUES(?,?,?,?)', (uid, pack, understood, now))
    c.commit()
    first = _studied(c, uid).get(pack, now)
    when, good = next_time(first, _listens(c, uid, pack).get(pack, []))
    return {'ok': True, 'label': LABELS[understood], 'known': when is None, 'good': good,
            'next_days': None if when is None else max(1, round((when - now) / 86400))}, 200


def week(c, uid, since):
    """For the weekly report: how many listens since then, and how much was understood on average (0–3)."""
    rows = [r[0] for r in c.execute('SELECT understood FROM next_relisten WHERE user_id=? AND created>?', (uid, since))]
    avg = sum(rows) / len(rows) if rows else None
    return {'count': len(rows), 'avg': None if avg is None else round(avg, 2), 'label': None if avg is None else LABELS[min(3, round(avg))]}
