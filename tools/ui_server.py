#!/usr/bin/env python3
"""Local Flow server for UI tests: a throwaway database, a simulated AI, and signed-in test learners.

    python3 tools/ui_server.py <port> <state dir>

Writes <state dir>/sessions.json: {learner: {"token", "csrf", "id"}} for a2, b1, exam and one per test device. The UI tests put the
token in the browser's cookie, so no password is typed, except for "leaver": 注销账号 asks for the password, so that one
learner gets a password made for this run (in sessions.json) and the test deletes it. Learners come with a profile, a word
plan, saved words, a mistake card of each kind and a few practice results, so every page has something on it.
Nothing here talks to a real AI or to production.
"""
import json, os, re, secrets, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'flow'
PORT, STATE = int(sys.argv[1]), Path(sys.argv[2])
STATE.mkdir(parents=True, exist_ok=True)
tmp = tempfile.mkdtemp(prefix='flow-ui-')
# Mail is on, as in production (sign-up, code login and a forgotten password then use emailed codes): messages are
# written to <data>/outbox as files, never sent.
os.environ.update({'FLOW_DATA_DIR': tmp, 'FLOW_COOKIE_SECURE': '0', 'FLOW_MAIL_OUTBOX': os.path.join(tmp, 'outbox'), 'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'ui-test', 'FLOW_AI_MODEL': 'ui-test',
                   'FLOW_AI_URL': 'https://ai.invalid/v1/chat/completions', 'FLOW_AI_USER_DAILY_LIMIT': '500', 'FLOW_AI_DAILY_LIMIT': '5000', 'FLOW_AI_AUDIO': '1'})
sys.path.insert(0, str(ROOT))
import app, chat_service, next_service as nx, vocab_service as vs, skills_service as sk  # noqa: E402

app.DB = Path(tmp) / 'flow.sqlite3'
# Audio in R2 (flow/media.py): one serial episode is listed as having narration while neither this server nor the
# media origin can send it (port 9 refuses at once), so tools/ui_test.py can check that the page asks the media
# domain itself; the test intercepts that address. Other materials have narration only as before (audio/index.json).
MEDIA_PID = 'v5-culture-c1-lighthouse-ledger-3'
os.environ['FLOW_MEDIA_BASE'] = 'http://127.0.0.1:9'
import media  # noqa: E402
media.MANIFEST = Path(tmp) / 'media-manifest.json'
# Narration this server has (the WeChat run's FLOW_AUDIO_DIR=tools/ui-fixtures/audio) stays listed, sent from here.
try:
    HERE = json.loads((media.DIR / 'index.json').read_text())
except (OSError, ValueError):
    HERE = {}
media.MANIFEST.write_text(json.dumps({'v': 1, 'version': 'uitest000001', 'narration': {**HERE, MEDIA_PID: ['us-f', 'us-m', 'uk-f', 'uk-m']},
                                      'files': {f'{v}/{MEDIA_PID}.{x}': ['0' * 64, 10] for v in ('us-f', 'us-m', 'uk-f', 'uk-m') for x in ('m4a', 'json')}}))
app.SECURE = False
app.init()


def fake(messages, audio=None, grounding=False):
    """Plausible answers for every prompt Flow sends, keyed on the prompt's role line."""
    system, prompt = messages[0]['content'], messages[-1]['content']
    J = lambda o: (json.dumps(o, ensure_ascii=False), 'stop')
    if '评估老师' in system:  # the radar's speaking and writing assessments
        dims = ('fluency', 'accuracy', 'range', 'pronunciation') if '口语' in system else ('content', 'organization', 'accuracy', 'range')
        return J({'transcript': 'I went to Hangzhou last spring with my parents.' if '口语' in system else '', 'level': 'B1', 'position': 0.6,
                  'scores': {k: 3 for k in dims}, 'strength': '意思表达清楚，有具体的例子。', 'next': ['多用连接词把句子连起来', '注意过去时的动词变化']})
    if '口语老师' in system:  # shadowing one sentence
        sent = prompt.split('原句：', 1)[1].split('\n', 1)[0]
        return J({'transcript': sent, 'issues': [], 'fluency': 'smooth', 'tip': '节奏很好，重音再明显一点。'})
    if '复述' in system:
        return J({'transcript': 'The headphones make an opposite sound wave so the noise is cancelled.',
                  'points': [{'point': '降噪耳机用反相声波抵消噪音', 'covered': True}, {'point': '对低频持续的噪音最有效', 'covered': False}],
                  'used': [], 'fixes': [{'from': 'it make', 'to': 'it makes', 'why': '主语是 it，动词要加 s', 'node': 'agreement-head'}],
                  'comment': '要点抓得准。', 'model': 'Noise-cancelling headphones create an opposite wave, so the two cancel out.'})
    if '情景对话' in system:
        if '对话结束' in prompt or '总结' in prompt:
            return J({'summary': '敢开口，回答也切题。', 'good': ['I take the train every day.'], 'fixes': [{'from': 'I want buy', 'to': 'I want to buy', 'why': 'want to do'}],
                      'expressions': [{'text': 'shop around', 'meaning': '货比三家'}], 'score': 0.72})
        if '学习者：' not in prompt:
            return J({'scene': '你在一家耳机店。', 'role': '店员', 'reply': 'Hi there! Are you looking for anything in particular today?'})
        return J({'heard': 'I want buy headphones for the train.', 'reply': 'Great. Do you prefer over-ear or in-ear ones?',
                  'correction': {'original': 'I want buy', 'better': 'I want to buy', 'why': 'want to do'}, 'hint': '说说你在意音质还是价格'})
    if '写作老师' in system:
        return J({'scores': {'content': 4, 'organization': 3, 'accuracy': 3, 'range': 3}, 'level': 'B1', 'comment': '观点清楚。',
                  'paragraphs': [{'para': 1, 'note': '开头直接给观点。'}], 'fixes': [{'from': 'more quieter', 'to': 'quieter', 'why': '比较级不要重复'}],
                  'better': [], 'model': 'On a crowded train, ...'})
    if '专业翻译' in system:
        return J({'zh': '降噪耳机会制造相反的声波来抵消噪音。'})
    if '翻译老师' in system:
        return J({'score': 0.78, 'accuracy': '意思基本准确。', 'fluency': '读起来自然。', 'fixes': [], 'reference': '耳机会产生相反的声波。', 'original': 'x'})
    if '语音老师' in system:
        return J({'heard': prompt.split('目标词：', 1)[1].split('\n', 1)[0], 'ok': True, 'note': '目标音清楚。', 'tip': ''})
    if '阅读老师' in system:  # questions and expressions for an imported article, quoting it word for word
        body = prompt.split('文章：\n', 1)[1].split('\n\n输出', 1)[0]
        first = re.split(r'(?<=[.!?])\s+', body)[0]
        words = re.findall(r'[A-Za-z]{6,}', body)
        return J({'summary_zh': '一篇导入的文章。', 'level': 'B1',
                  'questions': [{'prompt': 'What is the article mainly about?', 'options': ['The topic of the first sentence', 'Cooking', 'Football', 'Music'], 'answer': 0, 'evidence': first}],
                  'expressions': [], 'vocabulary': [{'term': words[0], 'meaning': '（演示）'}] if words else []})
    if '词典编辑' in system:
        words = re.findall(r'^([a-z-]+)：', prompt.split('单词（附中文义项）：\n', 1)[-1], re.M)
        return J({'examples': [{'word': w, 'sentence': f'We talked about the word {w} in class today.', 'translation': '（演示）'} for w in words]})
    if '改写成 CEFR' in prompt:  # keep the length (the server checks it); a real model simplifies the wording
        orig = prompt.split('原文：\n', 1)[1].split('\n\n输出', 1)[0]
        return J({'body': orig, 'notes': [{'text': 'on time', 'meaning': '准时'}]})
    if '要讲解的句子：' in prompt:
        return J({'translation': '（演示）这句话的中文。', 'structure': '主干 + 从句。', 'points': [{'text': 'The', 'note': '开头先交代主语。', 'node': None}],
                  'pattern': {'frame': 'not A so much as B', 'example': 'It is not talent so much as practice.'}})
    yours = prompt.split('学习者写的英文：\n', 1)[1].split('\n\n输出', 1)[0] if '学习者写的英文：\n' in prompt else 'I like it.'
    return J({'verdict': 'minor', 'summary': '意思清楚。', 'corrected': yours, 'changes': [],
              'versions': [{'label': '更自然', 'text': yours, 'why': '—'}], 'used_well': [], 'keep': None})


chat_service.request_model = fake

PID = 'v5-science-b2-noise-cancelling'
LEARNERS = {'a2': ('A2', 'daily', ['life']), 'b1': ('B1', 'work', ['work', 'science']), 'exam': ('B2', 'exam', ['science']),
            # one learner per device in tools/ui_test.py, so each device starts from the same state
            **{d: ('B1', 'work', ['work', 'science']) for d in ('phone', 'phone-land', 'tablet', 'desktop')},
            'guide': ('B1', 'work', ['work', 'science']),  # the 操作指南 screenshots (tools/guide_shots.py)
            'leaver': ('B1', 'work', ['work', 'science']),  # 注销账号 in tools/ui_test.py (learner_run)
            'a11y': ('B1', 'work', ['work', 'science'])}  # the screen-reader and contrast audit (a11y_run)
out = {}
with app.db() as c:
    for name, (level, goal, themes) in LEARNERS.items():
        uname = '小林' if name == 'guide' else f'ui-{name}'
        secret = 'ui-leaver-' + secrets.token_hex(8) if name == 'leaver' else ''
        c.execute('INSERT INTO users(username,password) VALUES(?,?)', (uname, app.password(secret) if secret else 'ui-no-login:' + secrets.token_hex(8)))
        uid = c.execute('SELECT id FROM users WHERE username=?', (uname,)).fetchone()[0]
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, uid, csrf, time.time() + 86400))
        c.commit()
        nx.save_profile(c, uid, {'level': level, 'goal': goal if goal in nx.GOALS else next(iter(nx.GOALS)), 'themes': [t for t in themes if t in nx.THEMES], 'minutes': 15})
        vs.save_plan(c, uid, {'book': 'core' if level == 'A2' else 'mid', 'daily_new': 10, 'retention': 0.9})
        for w, ctx in (('commute', 'I commute to work by train.'), ('deadline', 'The deadline is on Friday.'), ('make ends meet', 'It is hard to make ends meet.')):
            nx.save_card(c, uid, {'text': w, 'context': ctx, 'pack': PID})
        nx.save_card(c, uid, {'text': 'not A so much as B', 'meaning': '句型｜例：It is not talent so much as practice.', 'context': 'It is not talent so much as practice.'})
        sk.add_mistake(c, uid, 'fix', 'would have arrived', 'fix:would arrive > would have arrived', '说过去没发生的事', 'If I had left earlier, I would arrive on time. Then I went home.',
                       'writing', None, PID, {'from': 'would arrive'})
        q = json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?', (PID,)).fetchone()[0])['questions'][0]
        sk.add_mistake(c, uid, 'question', q['prompt'], f'q:{PID}:0', q.get('evidence', ''), '', 'reading', pack=PID,
                       extra={'options': q['options'], 'answer': q['answer'], 'evidence': q.get('evidence', '')})
        for _ in range(3):
            sk.log(c, uid, 'reading', 'question', 0.8, level, PID); sk.log(c, uid, 'writing', 'rewrite', 0.7, level, PID)
        if name == 'guide':  # a learner a few weeks in, so the guide's pictures show a lived-in page
            import ability_radar as ar
            now = time.time()
            for k, (words, wpm) in enumerate(((420, 118), (380, 126), (450, 131))):
                c.execute("INSERT INTO next_easy_reads(user_id,pack,words,seconds,wpm,rating,created) VALUES(?,?,?,?,?,'ok',?)", (uid, PID, words, round(words / wpm * 60), wpm, now - k * 86400))
            ar.set_goals(c, uid, {'goals': {'listening': 'B2', 'reading': 'B2', 'vocab': 'B2', 'grammar': 'B2', 'speaking': 'B1', 'writing': 'B1'}})
            for dim, idx in (('vocab', 52), ('grammar', 49), ('reading', 58), ('listening', 44), ('speaking', 38), ('writing', 41)):
                ar.record(c, uid, dim, idx, now=now - 9 * 86400)
            for dim, idx in (('reading', 63), ('listening', 50), ('speaking', 45)):
                ar.record(c, uid, dim, idx, now=now - 3600)
        c.commit()
        out[name] = {'token': token, 'csrf': csrf, 'id': uid, **({'password': secret} if secret else {})}
(STATE / 'sessions.json').write_text(json.dumps({'base': f'http://127.0.0.1:{PORT}', 'pid': PID, 'learners': out}))

from http.server import ThreadingHTTPServer  # noqa: E402


class Server(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


print(f'ui server on http://127.0.0.1:{PORT}/ (data {tmp})', flush=True)
Server(('127.0.0.1', PORT), app.Handler).serve_forever()
