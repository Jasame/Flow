"""「听两句、答一句」(B1's next three, item 2; the owner's picks 2026-11-26): two neighbouring lines of today's text, a
question about the learner's own life that grows out of them, and a one-sentence answer the learner types or says.

- ask(c, uid, data): the question (next-two-ask): one English sentence, one Chinese line, and an opener for 「给我一点提示」.
  It comes from the text alone, so it is shared: the same two lines at the same level get the same question all day
  (two_questions), and only the first learner's call reaches a model.
- check(c, uid, data): the answer (next-two-check): did the meaning come across (met / not_yet), one Chinese line on what
  came across or what is missing, a more natural sentence with the expression to learn in [[ ]], and that expression for
  the word book. `assisted` comes from the page and goes back as it came: the model never judges it. A spoken answer is
  written down first (chat_service.write_down: Omni told only to write it down) and the text model judges the words;
  what was heard is not kept, not even in the result.
Both are the learner's own calls (run_job: the daily count and the ¥10 stop), and AI-made (the page labels them).
The two lines (data['lines']) must be two neighbouring sentences of the text or of one of its level versions.
"""
import datetime, hashlib, json, re, time

import ai_lang  # 全英文界面: on an English page the note is in English (ai_lang.py)
import next_service as nx
from lab_service import Shape, mtext

PROMPT = 'v1-2026-11-26'
ASK, CHECK = 'next-two-ask', 'next-two-check'
TZ = datetime.timezone(datetime.timedelta(hours=8))
CJK = re.compile(r'[㐀-鿿]')
MARK = re.compile(r'\[\[([^\[\]]{1,60})\]\]')
LEVEL_NOTE = {'A2': '入门水平：用最常见的词和短句。', 'B1': '中级水平：词句清楚自然。', 'B2': '中高级水平：可以用常见搭配和稍长的句子。',
              'C1': '高级水平：措辞可以更地道、更精确。'}
SAFE = '不问真实姓名、住址、学校、电话这类个人信息；不涉及政治、宗教、时事、暴力、疾病和家庭隐私。'
NOTHING_HEARD = '没听清你说的，可以再说一遍，或者打字回答。'
NOTHING_HEARD_EN = "I didn't catch that. Say it again, or type your answer."


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS two_questions(pack TEXT NOT NULL, i INTEGER NOT NULL, level TEXT NOT NULL, day TEXT NOT NULL, '
              'lines TEXT NOT NULL, question TEXT NOT NULL, zh TEXT NOT NULL, hint TEXT NOT NULL DEFAULT \'\', prompt TEXT NOT NULL, '
              'created REAL NOT NULL, PRIMARY KEY(pack, i, level, day, lines))')


def _sha(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def _norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def _texts(c, pid, p):
    """The text and every level version of it, as the learner may have read it."""
    yield p.get('body') or ''
    for r in c.execute('SELECT body FROM next_variants WHERE pack=?', (pid,)):
        yield r['body'] if hasattr(r, 'keys') else r[0]


def _lines(c, uid, data):
    """(pack, level, [line 1, line 2]) or (None, None, (error, status)): the two lines must be neighbours in one text."""
    pid = str(data.get('pack', ''))
    lines = data.get('lines')
    if not isinstance(lines, list) or len(lines) != 2 or not all(isinstance(x, str) and 0 < len(x.strip()) <= 400 for x in lines):
        return None, None, ({'error': '要带上这两句'}, 400)
    row = nx._pack_row(c, uid, pid)
    if not row:
        return None, None, ({'error': '材料不存在'}, 404)
    p = json.loads(row['content'])
    a, b = _norm(lines[0]), _norm(lines[1])
    for text in _texts(c, pid, p):
        sents = [_norm(s) for s in nx.sentences(text)]
        if any(sents[j] == a and sents[j + 1] == b for j in range(len(sents) - 1)):
            level = (nx.profile(c, uid) or {}).get('level') or nx.cefr(p)
            return p, level, [a, b]
    return None, None, ({'error': '这两句不在这篇材料里'}, 400)


def _today():
    return datetime.datetime.now(TZ).date().isoformat()


def _run(c, uid, data, kind, pid, skill, spec, invoke, convert):
    from lab_service import run_job
    return run_job(c, uid, str(data.get('request_id', '')), kind, pid, skill, spec, invoke, convert, mark_replay=True)


# ---------- the question ----------

def ask_messages(lines, level):
    return [{'role': 'system', 'content': '你是给中国学习者出口语题的英语老师。只输出 JSON。'}, {'role': 'user', 'content':
        f'学习者是 {level}，{LEVEL_NOTE.get(level, LEVEL_NOTE["B1"])}\n今天这篇短文里相邻的两句：\n1. {lines[0]}\n2. {lines[1]}\n\n'
        '根据这两句，出一个和学习者自己的生活有关的问题，让他用一两句英语回答：\n'
        '- 问题从这两句的内容自然引出（比如两句讲排队买咖啡，就问他平时早上喝什么），不考这两句的细节；\n'
        '- 开放的问题，不能只用 yes 或 no 答完；\n'
        '- question：英文一句，以问号结尾，不超过 20 个词，用这个级别能听懂的词；\n'
        '- zh：问题的中文意思，一句，不超过 30 个字；\n'
        '- hint：一个回答的开头，3–8 个英文词，最好用上这两句里的一个表达，以 … 结尾；\n'
        f'- {SAFE}\n\n'
        '输出 JSON：{"question":"…","zh":"…","hint":"…"}'}]


def convert_ask(raw, guard=None):
    if not isinstance(raw, dict):
        raise Shape('json_shape')
    q = mtext(raw.get('question'), 3, 200, 'question_empty')
    if CJK.search(q) or not 3 <= len(nx.WORD.findall(q)) <= 25:
        raise Shape('question_shape')
    q = q if q.endswith('?') else q.rstrip('.!。') + '?'
    zh = mtext(raw.get('zh'), 1, 60, 'zh_empty')
    if not CJK.search(zh):
        raise Shape('zh_shape')
    hint = mtext(raw.get('hint') or '', 0, 80, default='')
    if CJK.search(hint) or len(nx.WORD.findall(hint)) > 10:
        hint = ''
    if hint and not hint.endswith(('…', '...')):
        hint = hint.rstrip('.') + '…'
    if (guard or _guard)({'body': q, 'summary_zh': zh}):
        raise Shape('topic')
    return {'question': q, 'zh': zh, 'hint': hint}


def _guard(p):
    return __import__('topic_guard').hits(p, dated=False)


def ask(c, uid, data):
    """POST /api/next/two/ask {pack, i, lines, request_id} -> ({result: {question, zh, hint}, request_id, remaining}, status)."""
    p, level, lines = _lines(c, uid, data)
    if not p:
        return lines
    try:
        i = int(data.get('i'))
    except (TypeError, ValueError):
        return {'error': '句子序号不正确'}, 400
    key = (p['id'], i, level, _today(), _sha(lines))
    row = c.execute('SELECT question, zh, hint FROM two_questions WHERE pack=? AND i=? AND level=? AND day=? AND lines=? AND prompt=?',
                    (*key, PROMPT)).fetchone()
    if row:
        from chat_service import remaining
        return {'result': {'question': row[0], 'zh': row[1], 'hint': row[2]}, 'request_id': str(data.get('request_id', '')),
                'remaining': remaining(c, uid), 'cached': True}, 200
    from chat_service import request_model
    msgs = ask_messages(lines, level)
    result, status = _run(c, uid, data, ASK, p['id'], 'speaking', {'pack': p['id'], 'i': i, 'level': level, 'lines': _sha(lines), 'prompt': PROMPT},
                          lambda: request_model(msgs), convert_ask)
    if status == 200 and not result.get('replayed'):
        r = result['result']
        c.execute('INSERT OR IGNORE INTO two_questions(pack,i,level,day,lines,question,zh,hint,prompt,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (*key, r['question'], r['zh'], r['hint'], PROMPT, time.time()))
        c.commit()
    return result, status


# ---------- the answer ----------

def check_messages(lines, question, answer, level, spoken):
    said = ('学习者说的话（语音转写，可能有转写误差，不要因为转写里的小错扣分）' if spoken else '学习者写的回答')
    return [{'role': 'system', 'content': '你是耐心的英语口语老师，看一位中国学习者的一句回答。只输出 JSON。' + ai_lang.tail()}, {'role': 'user', 'content':
        f'学习者是 {level}，{LEVEL_NOTE.get(level, LEVEL_NOTE["B1"])}\n短文里的两句：\n1. {lines[0]}\n2. {lines[1]}\n'
        f'问题：{question}\n{said}：{answer}\n\n'
        '- met：回答回应了这个问题、别人能听懂他的意思，就是 "met"；语法小错不影响。答非所问、太短说不清、或者只是照抄原文，才是 "not_yet"；\n'
        '- note：' + ai_lang.word() + '一句，不超过 40 个字。met 时说他说清楚了什么；not_yet 时说差在哪、下一次可以怎么说。不说「很好」这类空话；\n'
        '- better：一句更自然的英文，保留他想说的意思（not_yet 时给一句示范回答），不超过 25 个词；用 [[ ]] 标出一个值得学的表达，'
        '最好来自上面两句，整句只标一处；\n'
        '- save：[[ ]] 里的那个表达，原样照写；\n'
        f'- 不评价学习者本人；{SAFE}\n\n'
        '输出 JSON：{"met":"met 或 not_yet","note":"…","better":"…","save":"…"}'}]


def convert_check(raw, assisted=None):
    if not isinstance(raw, dict):
        raise Shape('json_shape')
    if raw.get('nothing_heard') is True:
        return {'met': 'not_yet', 'note': NOTHING_HEARD_EN if ai_lang.en() else NOTHING_HEARD, 'better': '', 'save': '', 'heard_nothing': True, 'assisted': assisted}
    m = raw.get('met')
    m = {'met': 'met', 'not_yet': 'not_yet', 'not yet': 'not_yet', 'notyet': 'not_yet', True: 'met', False: 'not_yet'}.get(
        m.strip().lower() if isinstance(m, str) else m)
    if not m:
        raise Shape('met_missing')
    if ai_lang.en():  # an English page's note: in English, a few words at least (40 字 ≈ 20 words)
        note = mtext(raw.get('note'), 1, 200, 'note_empty')
        if CJK.search(note) or len(nx.WORD.findall(note)) < 3:
            raise Shape('note_shape')
    else:
        note = mtext(raw.get('note'), 1, 80, 'note_empty')
        if not CJK.search(note):
            raise Shape('note_shape')
    better = mtext(raw.get('better'), 3, 300, 'better_empty')
    if CJK.search(better):
        raise Shape('better_shape')
    save = mtext(raw.get('save') or '', 0, 60, default='').strip('[] ')
    marks = MARK.findall(better)
    if not marks and save and save.lower() in better.lower():
        k = better.lower().index(save.lower())
        better = better[:k] + '[[' + better[k:k + len(save)] + ']]' + better[k + len(save):]
        marks = MARK.findall(better)
    if not marks:
        raise Shape('mark_missing')
    first = marks[0]
    head, _, tail = better.partition('[[' + first + ']]')
    better = head + '[[' + first + ']]' + MARK.sub(lambda x: x.group(1), tail)  # one mark only
    return {'met': m, 'note': note, 'better': better, 'save': first.strip(), 'assisted': assisted}


def check(c, uid, data):
    """POST /api/next/two/check {pack, i, lines, question, text | audio, assisted, request_id}
    -> ({result: {met, note, better, save, assisted}, request_id, remaining}, status)."""
    p, level, lines = _lines(c, uid, data)
    if not p:
        return lines
    question = data.get('question')
    if not isinstance(question, str) or not 3 <= len(question.strip()) <= 300 or CJK.search(question):
        return {'error': '问题不正确'}, 400
    question = _norm(question)
    from output_service import _audio_or_text
    text, audio, err = _audio_or_text(data, 2, 400)
    if err:
        return err
    assisted = data.get('assisted') if isinstance(data.get('assisted'), bool) else None
    spoken = audio is not None
    answer_sha = _sha(audio if spoken else text)
    import chat_service as cs
    heard = {}

    def invoke():
        said = text
        if spoken:
            if 'text' not in heard:  # once per request: run_job may ask the model again, the recording is not written down again
                heard['text'] = cs.write_down(audio)
            said = heard['text']
            if not said.strip():
                return json.dumps({'nothing_heard': True}), 'stop'
        return cs.request_model(check_messages(lines, question, said, level, spoken))
    spec = {'pack': p['id'], 'lines': _sha(lines), 'question': _sha(question), 'answer': answer_sha, 'spoken': spoken,
            'assisted': assisted, 'prompt': PROMPT}
    return _run(c, uid, data, CHECK, p['id'], 'speaking' if spoken else 'writing', spec, invoke, lambda raw: convert_check(raw, assisted))
