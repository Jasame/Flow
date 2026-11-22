"""Account-scoped progress for Flow's workplace English path."""
import datetime as dt
import difflib
import json
import re
import time

import adaptive_service
from meeting_path import CRITERIA, DAYS, FRAMES, TITLE, task

TZ = dt.timezone(dt.timedelta(hours=8))
MAX_ATTEMPTS = 3
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
FIRST_TASK = '/api/meeting/preview'


def schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS meeting_starts(
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, day TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS meeting_hints(
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      task INTEGER NOT NULL, PRIMARY KEY(user_id,task));
    CREATE TABLE IF NOT EXISTS meeting_attempts(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      task INTEGER NOT NULL, request_id TEXT NOT NULL, answer TEXT NOT NULL,
      assisted INTEGER NOT NULL, feedback TEXT NOT NULL, day TEXT NOT NULL,
      UNIQUE(user_id,request_id));
    CREATE INDEX IF NOT EXISTS meeting_attempts_user_task ON meeting_attempts(user_id,task,id);
    CREATE TABLE IF NOT EXISTS meeting_samples(
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      request_id TEXT NOT NULL, task INTEGER NOT NULL, answer TEXT NOT NULL, day TEXT NOT NULL,
      feedback TEXT NOT NULL, joined INTEGER NOT NULL, PRIMARY KEY(user_id,request_id));
    CREATE TABLE IF NOT EXISTS meeting_visits(
      visitor TEXT PRIMARY KEY, day TEXT NOT NULL,
      submitted INTEGER NOT NULL DEFAULT 0, revised INTEGER NOT NULL DEFAULT 0,
      saved INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS meeting_visits_day ON meeting_visits(day);
    """)


def today(now=None):
    return dt.datetime.fromtimestamp(time.time() if now is None else now, TZ).date()


def day_number(value):
    if type(value) is not int or not 1 <= value <= len(DAYS):
        raise ValueError('invalid task')
    return value


def answer_text(value):
    if not isinstance(value, str):
        raise ValueError('invalid answer')
    value = value.strip()
    if len(value) > 1200 or len(re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", value)) < 2:
        return None
    return value


# 4.5.0: a sense check before the rule matching, so a random or copied answer is told so instead of getting the
# usual "check whether the listener can hear ..." tip. Plain heuristics, no AI: real sentences almost always contain
# a few of these very common words; keyboard mashing and word lists do not.
COMMON = frozenset("""a an the and but or so because if when then than that this these those it its it's i i'm i'll i've
me my we we're we'll we've us our you your he she they them their there here is are was were be been being am do does did
done have has had will would can could should may might must shall not no yes to of in on at for with from by about into
over after before until up out off as just still also all some any more most very much many what which who whom how why
where tomorrow today yesterday afternoon morning week friday monday wednesday thursday tuesday please let get got""".split())
WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")


def sense(number, answer):
    """None, or a tip explaining why the answer cannot really be checked."""
    words = [w.lower().replace('’', "'") for w in WORD.findall(answer)]
    cjk = len(re.findall(r'[\u3400-\u9fff]', answer))
    if cjk > sum(len(w) for w in words):
        return '这里要用英文写。先用中文想好要说的三点，再把它们写成一到三句英文。'
    if len(words) >= 3:
        common = sum(w in COMMON for w in words) / len(words)
        if common < .15 or len(set(words)) / len(words) < .4:
            return '这段文字看起来不像完整的英文句子，规则没法判断。用一到三句话写给同事看，比如先说已经做完了什么。'
    example = DAYS[number - 1]['example'].lower().replace('’', "'")
    if difflib.SequenceMatcher(None, ' '.join(words), ' '.join(WORD.findall(example.lower()))).ratio() > .9:
        return '这几乎就是示例原句。换成自己的情况再写一遍，比如换一个时间、人名或者原因。'
    if len(words) < 4:
        return '再多写一点：用一到三句完整的话，把场景里要说的几点都说到。'
    return None


def feedback(number, answer):
    item = DAYS[number - 1]
    clauses = re.split(r'[.!?]+(?=\s|$)|[;\n]+|\s+(?:but|while)\s+', answer, flags=re.I)
    checks = []
    for label, (detail, expression, blocked) in zip(item['checks'], CRITERIA[number - 1]):
        quote = ''
        for clause in clauses:
            normalized = clause.replace('’', "'")
            if (re.search(detail, normalized, re.I) and re.search(expression, normalized, re.I)
                    and not (blocked and re.search(blocked, normalized, re.I))):
                quote = clause.strip()[:180]
                break
        checks.append({'label': label, 'found': bool(quote), 'quote': quote})

    wait_pattern = re.compile(r"\b(wait(?:ing|s|ed)?)\s+(?=(?:the|a|an|some|their|photos?|approval|final)\b)", re.I)
    correction = next(((match, clause) for clause in clauses if (match := wait_pattern.search(clause))), None)
    unresolved = next((check for check in checks if not check['found']), None)
    notice = sense(number, answer)
    if notice and (not correction or not any(check['found'] for check in checks)):
        tip = {'quote': '', 'text': notice}
    elif correction:
        match, clause = correction
        tip = {'quote': clause.strip()[:180], 'text': '说「等待某物」时用 wait for。试着在 ' + match.group(1) + ' 后面加上 for，再检查一次。'}
    elif unresolved:
        tip = {'quote': '', 'text': f'检查听众能否从你的回答里听出「{unresolved["label"]}」。卡住时先看句型，补一句自己的话。'}
    else:
        tip = {'quote': checks[0]['quote'], 'text': '读一遍这段话，检查同事是否能听清关键细节。也可以换一种说法再练一次。'}
    return {
        'version': 2, 'checks': checks, 'tip': tip, 'next': tip['text'],
        'method': '这里标出规则匹配到的片段。请结合原句确认意思与场景是否一致。',
    }


def hint(number, data):
    if data.get('level') == 'frame':
        return {'frame': FRAMES[number - 1]}, 200
    return {'example': DAYS[number - 1]['example']}, 200


def valid_id(value):
    return isinstance(value, str) and bool(UUID.fullmatch(value))


def record_visit(c, visitor, date, *, submitted=False, revised=False, saved=False):
    if not valid_id(visitor):
        return
    if not (submitted or revised or saved):
        c.execute('DELETE FROM meeting_visits WHERE day < ?', ((date - dt.timedelta(days=29)).isoformat(),))
    c.execute("""INSERT INTO meeting_visits(visitor,day,submitted,revised,saved) VALUES (?,?,?,?,?)
      ON CONFLICT(visitor) DO UPDATE SET submitted=max(submitted,excluded.submitted),
      revised=max(revised,excluded.revised),saved=max(saved,excluded.saved)""",
              (visitor, date.isoformat(), int(submitted or revised or saved), int(revised), int(saved)))


def attempts(c, uid):
    return c.execute(
        'SELECT * FROM meeting_attempts WHERE user_id=? ORDER BY task,id', (uid,)
    ).fetchall()


def first_attempts(rows):
    first = {}
    for row in rows:
        first.setdefault(row['task'], row)
    return first


def next_task(first, date):
    number = len(first) + 1
    if number > len(DAYS):
        return None, None
    unlock = dt.date.fromisoformat(first[number - 1]['day']) + dt.timedelta(days=1) if first else date
    return number, unlock


def recorded(row):
    return {
        'answer': row['answer'], 'assisted': bool(row['assisted']), 'day': row['day'],
        'feedback': json.loads(row['feedback']),
    }


def state(c, uid, date=None, include_samples=True):
    date = date or today()
    rows = attempts(c, uid)
    first = first_attempts(rows)
    number, unlock = next_task(first, date)
    return {
        'title': TITLE, 'completed': len(first), 'next': task(number) if number and unlock <= date else None,
        'next_title': DAYS[number - 1]['title'] if number else None,
        'unlock': unlock.isoformat() if number and unlock > date else None,
        'days': [{'day': i, 'title': item['title'], 'completed': i in first} for i, item in enumerate(DAYS, 1)],
        'last': task(rows[-1]['task']) if rows and rows[-1]['day'] == date.isoformat()
                and sum(r['task'] == rows[-1]['task'] for r in rows) < MAX_ATTEMPTS else None,
        'recent': recorded(rows[-1]) if rows else None,
        'first': recorded(first[1]) if 1 in first else None,
        'retest': recorded(first[len(DAYS)]) if len(DAYS) in first else None,
        'samples': [
            {'title': DAYS[row['task'] - 1]['title'], **recorded(row)}
            for row in c.execute('SELECT *,1 AS assisted FROM meeting_samples WHERE user_id=? AND joined=0 ORDER BY rowid DESC', (uid,))
        ] if include_samples else [],
    }


def overview(c, uid):
    from coach_service import mission_list
    from loop_service import overview as learning_loop

    has_profile = c.execute('SELECT 1 FROM coach_profiles WHERE user_id=?', (uid,)).fetchone() is not None
    loop = learning_loop(c, uid, mission_list(c, uid)) if has_profile else {}
    review = adaptive_service.review_status(c, uid)
    return {
        'meeting': state(c, uid, include_samples=False), 'profile': has_profile,
        'recommendation': loop.get('next_action'),
        'mission': (loop.get('unit') or {}).get('tasks', [None])[0],
        'review_due': review['due_words'] + review['due_grammar'],
    }


def stats(c, date=None):
    date = date or today()
    rows = c.execute("""
        WITH cohort AS (
          SELECT s.user_id, s.day AS started, MIN(a.day) AS first_day
          FROM meeting_starts s LEFT JOIN meeting_attempts a ON a.user_id=s.user_id AND a.task=1
          GROUP BY s.user_id,s.day
        )
        SELECT COUNT(*) AS started, COUNT(first_day) AS completed_first,
          COUNT(CASE WHEN first_day < ? THEN 1 END) AS next_day_eligible,
          COUNT(CASE WHEN first_day < ? AND EXISTS(
            SELECT 1 FROM meeting_attempts a WHERE a.user_id=cohort.user_id
            AND a.task=2 AND a.day=date(first_day,'+1 day')) THEN 1 END) AS next_day_returned,
          COUNT(CASE WHEN date(first_day,'+6 days') <= ? THEN 1 END) AS retest_eligible,
          COUNT(CASE WHEN date(first_day,'+6 days') <= ? AND EXISTS(
            SELECT 1 FROM meeting_attempts a WHERE a.user_id=cohort.user_id AND a.task=7
          ) THEN 1 END) AS completed_retest
        FROM cohort
    """, (date.isoformat(),)*4).fetchone()
    results = [json.loads(row['feedback']) for row in c.execute("""
        SELECT a.feedback FROM meeting_attempts a
        WHERE a.task=7 AND a.assisted=0 AND a.id=(
          SELECT MIN(b.id) FROM meeting_attempts b WHERE b.user_id=a.user_id AND b.task=7)
    """)]
    results = [result for result in results if result.get('version') == 2]
    visits = c.execute('''SELECT COUNT(*) AS opened, COALESCE(SUM(submitted),0) AS submitted,
        COALESCE(SUM(revised),0) AS revised, COALESCE(SUM(saved),0) AS saved FROM meeting_visits
        WHERE day BETWEEN ? AND ?''', ((date - dt.timedelta(days=29)).isoformat(), date.isoformat())).fetchone()
    return dict(rows) | {
        'guest': dict(visits), 'unassisted_retests': len(results),
        'all_cues_found': sum(all(check['found'] for check in result['checks']) for result in results),
    }


def allowed(c, uid, number, date):
    rows = attempts(c, uid)
    first = first_attempts(rows)
    current, unlock = next_task(first, date)
    existing = [row for row in rows if row['task'] == number]
    revision = (existing and number == len(first) and len(existing) < MAX_ATTEMPTS
                and existing[0]['day'] == date.isoformat())
    return number == current and date >= unlock or bool(revision)


def submit(c, uid, data, date=None):
    date = date or today()
    number = day_number(data.get('day'))
    answer = answer_text(data.get('answer'))
    request_id = data.get('request_id')
    if not answer:
        return {'error': '先写一句英文再提交，例如 Photos pending. 最多可输入 1200 个字符。'}, 400
    if not valid_id(request_id):
        return {'error': '请刷新页面后重试。'}, 400

    c.execute('BEGIN IMMEDIATE')
    existing = c.execute('SELECT * FROM meeting_attempts WHERE user_id=? AND request_id=?', (uid, request_id)).fetchone()
    if existing:
        if (existing['task'], existing['answer']) != (number, answer):
            return {'error': '这次请求已保存，请刷新后再提交新答案。'}, 409
        return {'attempt': recorded(existing), 'progress': state(c, uid, date)}, 200
    if not allowed(c, uid, number, date):
        return {'error': '这个任务目前无法提交，请打开今日学习查看下一步。'}, 409
    assisted = bool(c.execute(
        'SELECT 1 FROM meeting_hints WHERE user_id=? AND task=? UNION ALL '
        'SELECT 1 FROM meeting_attempts WHERE user_id=? AND task=? LIMIT 1',
        (uid, number, uid, number),
    ).fetchone()) or data.get('preview') is True
    result = feedback(number, answer)
    write_attempt(c, uid, number, request_id, answer, assisted, result, date)
    return {'attempt': {'answer': answer, 'assisted': assisted, 'day': date.isoformat(), 'feedback': result},
            'progress': state(c, uid, date)}, 200


def write_attempt(c, uid, number, request_id, answer, assisted, result, date):
    if number == 1:
        c.execute('INSERT OR IGNORE INTO meeting_starts VALUES (?,?)', (uid, date.isoformat()))
    c.execute('INSERT INTO meeting_attempts(user_id,task,request_id,answer,assisted,feedback,day) VALUES (?,?,?,?,?,?,?)',
              (uid, number, request_id, answer, int(assisted), json.dumps(result, ensure_ascii=False), date.isoformat()))


def save_preview(c, uid, data, date=None):
    date = date or today()
    number = day_number(data.get('day'))
    answer = answer_text(data.get('answer'))
    request_id = data.get('request_id')
    if not DAYS[number - 1]['slug'] or not answer or not valid_id(request_id):
        return {'error': '练习记录不完整，请返回答案页再试一次。'}, 400

    c.execute('BEGIN IMMEDIATE')
    previous = c.execute('SELECT * FROM meeting_samples WHERE user_id=? AND request_id=?', (uid, request_id)).fetchone()
    if previous:
        if (previous['task'], previous['answer']) != (number, answer):
            return {'error': '此练习已保存，请返回答案页。'}, 409
        return {'joined': bool(previous['joined']), 'progress': state(c, uid, date)}, 200
    joined = number == 1 and not c.execute('SELECT 1 FROM meeting_attempts WHERE user_id=? AND task=1', (uid,)).fetchone()
    result = feedback(number, answer)
    c.execute('INSERT INTO meeting_samples VALUES (?,?,?,?,?,?,?)',
              (uid, request_id, number, answer, date.isoformat(), json.dumps(result, ensure_ascii=False), int(joined)))
    if joined:
        write_attempt(c, uid, number, request_id, answer, True, result, date)
    record_visit(c, data.get('visitor'), date, saved=True)
    return {'joined': joined, 'progress': state(c, uid, date)}, 200


def get(c, uid, admin, path):
    if path == '/api/meeting':
        return state(c, uid), 200
    if path == '/api/meeting/today':
        return overview(c, uid), 200
    if path == '/api/meeting/stats':
        return (stats(c), 200) if admin else ({'error': '需要管理员权限'}, 403)


def post(c, uid, path, data):
    if path == '/api/meeting/start':
        c.execute('INSERT OR IGNORE INTO meeting_starts VALUES (?,?)', (uid, today().isoformat()))
        return {'ok': True}, 200
    if path == '/api/meeting/hint':
        number = day_number(data.get('day'))
        c.execute('BEGIN IMMEDIATE')
        if not allowed(c, uid, number, today()):
            return {'error': '请按今日学习里的安排完成这项练习。'}, 409
        c.execute('INSERT OR IGNORE INTO meeting_hints VALUES (?,?)', (uid, number))
        return hint(number, data)
    if path == '/api/meeting/save-preview':
        return save_preview(c, uid, data)
    if path == '/api/meeting/submit':
        return submit(c, uid, data)


def preview(data, c=None):
    number = day_number(data.get('day'))
    if not DAYS[number - 1]['slug']:
        return {'error': '该练习需要登录。'}, 401
    if data.get('action') == 'hint':
        return hint(number, data)
    if data.get('action') == 'open':
        if c is not None:
            record_visit(c, data.get('visitor'), today())
        return {'ok': True}, 200
    answer = answer_text(data.get('answer'))
    if not answer:
        return {'error': '先写一句英文再提交，例如 Photos pending. 最多可输入 1200 个字符。'}, 400
    if c is not None:
        record_visit(c, data.get('visitor'), today(), submitted=True, revised=data.get('revision') is True)
    return {'feedback': feedback(number, answer)}, 200
