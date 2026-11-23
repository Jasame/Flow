"""Easy reading (轻松读): a lot of easy text, read fast, no tasks.

Why: the most reliable finding on reading is that large amounts of easy, comprehensible text build fluency, while
the four-step material is intensive study. Here the learner reads one level below their own (adjusted by "too easy /
just right / too hard"), a timer gives the reading speed, and the words read add up week by week. A text read here
also counts as "met" for its grammar points, without showing up as a material in progress.
"""
import json, random, time

import next_service as nx

ORDER = ('A2', 'B1', 'B2', 'C1')
WPM_MAX = 600  # faster than this is skimming or a timer left running the other way: not stored as a speed


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS next_easy_reads(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), pack TEXT NOT NULL,
      words INTEGER NOT NULL, seconds INTEGER NOT NULL, wpm INTEGER, rating TEXT NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS next_easy_reads_user ON next_easy_reads(user_id, created);
    CREATE TABLE IF NOT EXISTS next_easy_pref(user_id INTEGER PRIMARY KEY REFERENCES users(id), offset INTEGER NOT NULL DEFAULT -1, updated REAL NOT NULL);''')


def _offset(c, uid):
    r = c.execute('SELECT offset FROM next_easy_pref WHERE user_id=?', (uid,)).fetchone() if uid else None
    return r[0] if r else -1


def _target(level, offset):
    i = ORDER.index(level if level in ORDER else 'B1')
    return ORDER[max(0, min(len(ORDER) - 1, i + offset))]


def stats(c, uid, now=None):
    if not uid:
        return None
    now = now or time.time()
    week = now - 7 * 86400
    rows = c.execute('SELECT words, wpm, created FROM next_easy_reads WHERE user_id=? ORDER BY created', (uid,)).fetchall()
    speeds = [r['wpm'] for r in rows if r['wpm']]
    return {'week_words': sum(r['words'] for r in rows if r['created'] >= week), 'week_reads': sum(1 for r in rows if r['created'] >= week),
            'total_words': sum(r['words'] for r in rows), 'reads': len(rows), 'last_wpm': speeds[-1] if speeds else None,
            'avg_wpm': round(sum(speeds[-5:]) / len(speeds[-5:])) if speeds else None,
            'first_wpm': round(sum(speeds[:3]) / len(speeds[:3])) if len(speeds) >= 6 else None}


def listing(c, uid, level=None):
    prof = nx.profile(c, uid) or {}
    lv = prof.get('level') or (level if level in ORDER else 'B1')
    off = _offset(c, uid)
    target = _target(lv, off)
    done = nx._done(c, uid)
    read = {r[0] for r in c.execute('SELECT pack FROM next_easy_reads WHERE user_id=?', (uid,))} if uid else set()
    pool = [p for _, p in nx._public_packs(c) if nx.cefr(p) == target and not p.get('series') and p['id'] not in read
            and 'check' not in done.get(p['id'], set())]
    rnd = random.Random(f"{uid}:{nx._day()}")  # the same suggestions all day, new ones tomorrow
    rnd.shuffle(pool)
    pool.sort(key=lambda p: not nx.featured(p))
    return {'level': lv, 'target': target, 'offset': off, 'items': [nx._card(p) for p in pool[:6]], 'stats': stats(c, uid),
            'note': f'比你现在的水平（{lv}）低一点的材料，读起来几乎不用查词。只读不做题，读完说一下难不难，系统会自动调整。' if off < 0 else
                    f'和你现在的水平（{lv}）一样的材料，只读不做题。'}, 200


def done(c, uid, data, now=None):
    """One easy read finished: words, seconds, and how it felt. 'too easy' moves the next ones one level up (at most to
    the learner's own level); 'too hard' one level down."""
    now = now or time.time()
    row = nx._pack_row(c, uid, str(data.get('pack', '')))
    if not row:
        return {'error': '材料不存在'}, 404
    rating = data.get('rating')
    if rating not in ('easy', 'ok', 'hard'):
        return {'error': '请选择难度感受'}, 400
    seconds = data.get('seconds')
    if type(seconds) is not int or not 5 <= seconds <= 3 * 3600:
        return {'error': '阅读时间不正确'}, 400
    p = json.loads(row['content'])
    words = len(nx.WORD.findall(p.get('body', '')))
    wpm = round(words / (seconds / 60))
    wpm = wpm if 30 <= wpm <= WPM_MAX else None
    if not uid:
        return {'words': words, 'wpm': wpm, 'saved': False}, 200
    c.execute('INSERT INTO next_easy_reads(user_id,pack,words,seconds,wpm,rating,created) VALUES(?,?,?,?,?,?,?)',
              (uid, p['id'], words, seconds, wpm, rating, now))
    off = _offset(c, uid)
    off = min(0, off + 1) if rating == 'easy' else max(-2, off - 1) if rating == 'hard' else off
    c.execute('INSERT INTO next_easy_pref(user_id,offset,updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET offset=excluded.offset, updated=excluded.updated',
              (uid, off, now))
    c.commit()  # its grammar points count as met (graph_states reads this table); it is not a started material
    return {'words': words, 'wpm': wpm, 'saved': True, 'stats': stats(c, uid, now), 'offset': off}, 200


def read_today(c, uid, start):
    return c.execute('SELECT COUNT(*) FROM next_easy_reads WHERE user_id=? AND created>=?', (uid, start)).fetchone()[0]
