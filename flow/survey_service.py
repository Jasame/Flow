"""Anonymous learner-needs survey.

Privacy: responses carry no account, cookie, IP or user agent. Abuse control keeps
an HMAC of (client address, UTC day) in a separate table for two days only, keyed
by FLOW_SURVEY_SALT or a random secret file in the data dir. Nothing links a stored
response to that key, so a response cannot be traced back to an address.
"""
import csv, hashlib, hmac, io, json, os, secrets, time
from pathlib import Path

SURVEY_ID = 'needs-2026-11'
DAILY_PER_CLIENT = 3
DAILY_TOTAL = 1000
MIN_SECONDS = 20
TEXT_MAX = 1000

SURVEY = {
    'id': SURVEY_ID,
    'title': '你理想中的英语学习网站是什么样？',
    'intro': '这是一份匿名问卷，大约 4 分钟。不需要登录，不收集姓名、邮箱、手机号或 IP 地址。你的回答只用于决定语流 Flow 接下来做什么。',
    'sections': [
        {'title': '关于你', 'questions': [
            {'id': 'role', 'type': 'single', 'required': True, 'label': '你现在的身份',
             'options': ['中学生', '大学生（英语专业）', '大学生（非英语专业）', '研究生', '在职', '其他']},
            {'id': 'level', 'type': 'single', 'required': True, 'label': '你觉得自己的英语大概在什么水平？',
             'options': ['入门：简单句子也吃力', '基础：能应付日常简单交流', '中级：能读懂工作或学习材料', '中高级：能比较自如地讨论话题', '高级：接近母语者']},
            {'id': 'goals', 'type': 'multi', 'max': 3, 'required': True, 'label': '你学英语最主要的目标（最多选 3 项）',
             'options': ['应试（四六级、考研、专四专八等）', '出国考试（雅思、托福等）', '工作沟通', '留学或海外生活', '看懂影视、播客、新闻', '专业学习与研究', '兴趣，没有具体目标']},
            {'id': 'hours', 'type': 'single', 'required': True, 'label': '你平均每周花多少时间学英语？',
             'options': ['不到 1 小时', '1–3 小时', '3–7 小时', '7 小时以上']},
        ]},
        {'title': '你现在怎么学', 'questions': [
            {'id': 'tools', 'type': 'multi', 'required': True, 'label': '你现在用哪些方式学英语？（可多选）',
             'options': ['背单词 App', '多邻国这类闯关 App', 'AI 聊天工具（ChatGPT、豆包等）', '美剧、电影、YouTube、播客', '网课或培训班', '真人外教或语伴', '纸质书或课本', '最近几乎没在学']},
            {'id': 'quit', 'type': 'multi', 'max': 3, 'required': True, 'label': '你放弃一个英语 App 或学习计划，最常见的原因（最多选 3 项）',
             'options': ['太枯燥', '看不到自己在进步', '内容太难或太简单', '内容和我的需要无关', '不知道下一步该学什么', '没时间', '没人督促', '平时没有用英语的场景', '收费太贵']},
            {'id': 'skills', 'type': 'multi', 'max': 2, 'required': True, 'label': '你最想提高的两项能力',
             'options': ['听力', '口语', '阅读', '写作', '词汇', '语法', '发音']},
        ]},
        {'title': '理想的英语学习网站', 'questions': [
            {'id': 'materials', 'type': 'multi', 'max': 3, 'required': True, 'label': '你最想用什么材料来学？（最多选 3 项）',
             'options': ['真实的新闻和文章', '影视片段', '播客和演讲', '自己专业或工作领域的材料', '考试真题', 'AI 按我的水平和兴趣生成的材料', '我自己导入的文章或视频']},
            {'id': 'ai', 'type': 'multi', 'max': 3, 'required': True, 'label': '你最希望 AI 帮你做什么？（最多选 3 项）',
             'options': ['批改写作，并给出更地道的改写', '陪我练口语对话', '纠正发音', '讲解语法', '结合语境讲生词', '根据我的情况定制学习计划', '模拟面试、会议等真实场景']},
            {'id': 'features', 'type': 'matrix', 'required': True, 'label': '下面这些功能对你有多重要？（1 = 不需要，5 = 非常需要）',
             'rows': ['每天 10 分钟的小任务', '看得见的进步记录', '按遗忘规律安排复习', '打卡、连续天数', '排行榜或和朋友比较', '学习社区、找语伴'],
             'scale': 5},
            {'id': 'session', 'type': 'single', 'required': True, 'label': '每次打开，你愿意学多久？',
             'options': ['5 分钟以内', '10–15 分钟', '30 分钟左右', '1 小时以上']},
            {'id': 'pay', 'type': 'single', 'required': True, 'label': '如果真的好用，你愿意每月付多少钱？',
             'options': ['只用免费的', '每月 20 元以内', '20–50 元', '50–100 元', '100 元以上']},
        ]},
        {'title': '说说你的想法', 'questions': [
            {'id': 'dislike', 'type': 'text', 'required': False, 'label': '你用过的英语学习产品里，最让你不想再用的一点是什么？',
             'placeholder': '比如：广告太多、只会背单词、AI 改得不自然……'},
            {'id': 'ideal', 'type': 'text', 'required': False, 'label': '如果有一个理想的英语学习网站，它应该是什么样？',
             'placeholder': '想到什么写什么，一句话也可以'},
            {'id': 'flow', 'type': 'single', 'required': True, 'label': '你用过语流 Flow 吗？',
             'options': ['没用过', '打开看过', '用过几次', '经常用']},
            {'id': 'flow_note', 'type': 'text', 'required': False, 'label': '如果用过，对 Flow 有什么评价或建议？',
             'placeholder': '选填'},
        ]},
    ],
}


def questions():
    for section in SURVEY['sections']:
        yield from section['questions']


def schema(c):
    c.executescript('''
CREATE TABLE IF NOT EXISTS survey_responses(
 id INTEGER PRIMARY KEY, survey TEXT NOT NULL, created REAL NOT NULL, day TEXT NOT NULL,
 answers TEXT NOT NULL, seconds INTEGER, hidden INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS survey_responses_day ON survey_responses(survey, day);
CREATE TABLE IF NOT EXISTS survey_limits(key TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL,
 PRIMARY KEY(key, day));''')


def _day(now=None):
    return time.strftime('%Y-%m-%d', time.gmtime(now or time.time()))


def _salt():
    env = os.getenv('FLOW_SURVEY_SALT')
    if env:
        return env.encode()
    path = Path(os.getenv('FLOW_DATA_DIR', Path(__file__).resolve().parent / 'data')) / 'survey-salt'
    try:
        return path.read_bytes()
    except FileNotFoundError:
        value = secrets.token_bytes(32)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(value)
            return value
        except FileExistsError:
            return path.read_bytes()


def client_key(address, day):
    return hmac.new(_salt(), f'{address}|{day}'.encode(), hashlib.sha256).hexdigest()


def clean(data):
    """Validate a submission against SURVEY. Returns (answers, error)."""
    raw = data.get('answers')
    if not isinstance(raw, dict):
        return None, '请完成问卷后再提交'
    known = {q['id'] for q in questions()}
    if set(raw) - known:
        return None, '问卷内容已更新，请刷新页面后重新填写'
    out = {}
    for q in questions():
        value = raw.get(q['id'])
        empty = value in (None, '', [], {})
        if empty:
            if q['required']:
                return None, f"请回答：{q['label']}"
            continue
        if q['type'] == 'single':
            if value not in q['options']:
                return None, f"选项无效：{q['label']}"
        elif q['type'] == 'multi':
            if not isinstance(value, list) or len(set(value)) != len(value) or any(v not in q['options'] for v in value):
                return None, f"选项无效：{q['label']}"
            if q.get('max') and len(value) > q['max']:
                return None, f"最多选 {q['max']} 项：{q['label']}"
        elif q['type'] == 'matrix':
            if not isinstance(value, dict) or set(value) != set(q['rows']):
                return None, f"请给每一项打分：{q['label']}"
            if any(type(v) is not int or not 1 <= v <= q['scale'] for v in value.values()):
                return None, f"分数无效：{q['label']}"
        elif q['type'] == 'text':
            if not isinstance(value, str):
                return None, f"内容无效：{q['label']}"
            value = value.strip()[:TEXT_MAX]
            if not value:
                continue
        out[q['id']] = value
    return out, None


def submit(c, data, address, now=None):
    now = now or time.time()
    # Honeypot: bots fill every field. Pretend success, store nothing.
    if data.get('website'):
        return {'ok': True}, 200
    try:
        seconds = int(data.get('seconds', 0))
    except (TypeError, ValueError):
        seconds = 0
    if seconds < MIN_SECONDS:
        return {'error': '填得有点快，请再看一遍题目后提交'}, 400
    answers, problem = clean(data)
    if problem:
        return {'error': problem}, 400
    day = _day(now)
    key = client_key(address, day)
    c.execute('BEGIN IMMEDIATE')
    c.execute('DELETE FROM survey_limits WHERE day<?', (_day(now - 2 * 86400),))
    used = c.execute('SELECT count FROM survey_limits WHERE key=? AND day=?', (key, day)).fetchone()
    if used and used[0] >= DAILY_PER_CLIENT:
        c.rollback()
        return {'error': '今天已经收到你的回答了，谢谢！'}, 429
    if c.execute('SELECT COUNT(*) FROM survey_responses WHERE survey=? AND day=?', (SURVEY_ID, day)).fetchone()[0] >= DAILY_TOTAL:
        c.rollback()
        return {'error': '今天的问卷收集已满，请明天再来'}, 429
    c.execute('INSERT INTO survey_limits VALUES(?,?,1) ON CONFLICT(key,day) DO UPDATE SET count=count+1', (key, day))
    c.execute('INSERT INTO survey_responses(survey,created,day,answers,seconds) VALUES(?,?,?,?,?)',
              (SURVEY_ID, now, day, json.dumps(answers, ensure_ascii=False), min(seconds, 86400)))
    c.commit()
    return {'ok': True}, 200


def _rows(c, include_hidden=False):
    sql = 'SELECT id,created,day,answers,seconds,hidden FROM survey_responses WHERE survey=?'
    if not include_hidden:
        sql += ' AND hidden=0'
    return [dict(id=r[0], created=r[1], day=r[2], answers=json.loads(r[3]), seconds=r[4], hidden=bool(r[5]))
            for r in c.execute(sql + ' ORDER BY id DESC', (SURVEY_ID,))]


def summary(c, filters=None):
    filters = {k: v for k, v in (filters or {}).items() if v}
    rows = [r for r in _rows(c) if all(r['answers'].get(k) == v for k, v in filters.items())]
    total = len(rows)
    out = []
    for q in questions():
        item = {'id': q['id'], 'type': q['type'], 'label': q['label']}
        answered = [r['answers'][q['id']] for r in rows if q['id'] in r['answers']]
        item['answered'] = len(answered)
        if q['type'] in ('single', 'multi'):
            counts = {o: 0 for o in q['options']}
            for a in answered:
                for v in (a if isinstance(a, list) else [a]):
                    counts[v] = counts.get(v, 0) + 1
            item['options'] = [{'label': o, 'count': n} for o, n in counts.items()]
        elif q['type'] == 'matrix':
            item['rows'] = []
            for row in q['rows']:
                scores = [a[row] for a in answered if row in a]
                dist = [scores.count(s) for s in range(1, q['scale'] + 1)]
                item['rows'].append({'label': row, 'average': round(sum(scores) / len(scores), 2) if scores else None, 'distribution': dist})
        else:
            item['samples'] = [{'id': r['id'], 'day': r['day'], 'text': r['answers'][q['id']]} for r in rows if q['id'] in r['answers']][:50]
        out.append(item)
    days = {}
    for r in rows:
        days[r['day']] = days.get(r['day'], 0) + 1
    secs = sorted(r['seconds'] for r in rows if r['seconds'])
    return {'survey': {'id': SURVEY_ID, 'title': SURVEY['title']}, 'total': total, 'filters': filters,
            'by_day': [{'day': d, 'count': n} for d, n in sorted(days.items())],
            'median_seconds': secs[len(secs) // 2] if secs else None,
            'hidden': c.execute('SELECT COUNT(*) FROM survey_responses WHERE survey=? AND hidden=1', (SURVEY_ID,)).fetchone()[0],
            'questions': out}


def responses(c, page=1, per_page=20, query=''):
    rows = _rows(c, include_hidden=True)
    if query:
        q = query.lower()
        rows = [r for r in rows if q in json.dumps(r['answers'], ensure_ascii=False).lower()]
    page = max(1, page)
    return {'total': len(rows), 'page': page, 'per_page': per_page, 'items': rows[(page - 1) * per_page: page * per_page]}


def set_hidden(c, rid, hidden):
    cur = c.execute('UPDATE survey_responses SET hidden=? WHERE id=? AND survey=?', (1 if hidden else 0, rid, SURVEY_ID))
    c.commit()
    return ({'ok': True}, 200) if cur.rowcount else ({'error': '记录不存在'}, 404)


def _cell(v):
    # Free text must not run as a spreadsheet formula when the CSV is opened.
    return "'" + v if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r') else v


def export_csv(c):
    qs = list(questions())
    buf = io.StringIO()
    buf.write('﻿')  # Excel opens UTF-8 correctly with a BOM.
    w = csv.writer(buf)
    head = ['id', 'date_utc', 'seconds']
    for q in qs:
        head += [f"{q['id']}:{row}" for row in q['rows']] if q['type'] == 'matrix' else [q['id']]
    w.writerow(head)
    for r in reversed(_rows(c)):
        line = [r['id'], r['day'], r['seconds']]
        for q in qs:
            v = r['answers'].get(q['id'])
            if q['type'] == 'matrix':
                line += [(v or {}).get(row, '') for row in q['rows']]
            elif isinstance(v, list):
                line.append('；'.join(v))
            else:
                line.append(_cell(v or ''))
        w.writerow(line)
    return buf.getvalue().encode('utf-8')
