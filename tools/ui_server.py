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
# Data word books (专四、专八、中考、学术…): small fixtures instead of flow/corpus_data/wordbooks*.json, so the picker
# always shows the same groups and books whatever data files the checkout has.
os.environ['FLOW_WORDBOOKS'] = os.pathsep.join(str(ROOT.parent / 'tools' / 'ui-fixtures' / n) for n in ('wordbooks.json', 'wordbooks-open.json'))
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
    if '口语老师' in system:  # shadowing one sentence: one word left out, an estimate, one sound to practise
        sent = prompt.split('原句：', 1)[1].split('\n', 1)[0]
        ws = sent.split()
        heard = ' '.join(ws[:2] + ws[3:]) if len(ws) > 4 else sent
        th = next((w.strip('.,!?;:"\'').lower() for w in ws if 'th' in w.lower()), None)
        snd = {'sound': '/ð/' if th in ('the', 'this', 'that', 'there', 'they', 'then') else '/θ/', 'word': th, 'note': '舌尖放到上下齿之间，别读成 /z/ 或 /s/',
               'set': 'th-z' if th in ('the', 'this', 'that', 'there', 'they', 'then') else 'th-s'} if th else \
            {'sound': '/ɪ/', 'word': ws[-1].strip('.,!?;:"\'').lower(), 'note': '短而放松，不要拖长', 'set': 'i-long-short'}
        return J({'transcript': heard, 'accuracy': 78, 'fluency_score': 84, 'fluency': 'smooth', 'sounds': [snd],
                  'issues': [{'word': ws[2].strip('.,!?;:"\'') if len(ws) > 4 else ws[0], 'note': '这个词漏读了'}], 'tip': '节奏很好，重音再明显一点。'})
    if '练雅思口语 Part 1' in system:  # one Part 1 answer
        typed = prompt.split('学习者的回答：', 1)[1].split('\n\n输出', 1)[0] if '学习者的回答：' in prompt else 'I am more of a morning person, because I feel more fresh.'
        return J({'heard': typed, 'better': {'text': 'Definitely a morning person. I feel much fresher before breakfast, so I do my hardest work then.', 'why': '比较级用 fresher，再补一个理由'},
                  'note': '能直接回答；比较级用错；语速平稳。'})
    if '雅思口语考官' in system:  # Part 1 or Part 2 feedback on the four criteria
        fb = {'bands': {'fc': 6, 'lr': 6.5, 'gra': 5.5, 'p': 6 if 'p 填 null' not in system else None}, 'summary': '能一直说下去，回答切题；连接词偏少，过去时有时漏 -ed。',
              'notes': {'fc': {'good': '停顿不多，能接着往下说', 'next': '多用 because / for example 把理由说完整'},
                        'lr': {'good': '用了 rewarding、patient 这样的词', 'next': '把 very good 换成更具体的形容词'},
                        'gra': {'good': '简单句基本正确', 'next': '讲过去的事，动词别漏 -ed'}, 'p': {'good': '整体清楚，能听懂', 'next': 'think 的 th 别读成 s'}},
              'fixes': [{'from': 'I learn it last year', 'to': 'I learned it last year', 'why': '过去的事用过去时', 'node': None}],
              'model': 'I\'d like to talk about cooking, which I picked up from my grandmother. I started when I was fifteen, mostly by watching her and asking questions, and it took me about a year before I could make a proper meal on my own. These days it saves me money and, more importantly, it\'s how I relax after a long day.',
              'model_q': 1}
        if 'Part 2' in prompt:
            fb.update(transcript='I want to talk about cooking. I learn it last year from my grandmother. It is very good for me because I can save money.', covered=[True, True, False, True])
        return J(fb)
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
    yours = prompt.split('学习者写的英文：\n', 1)[1].split('\n\n', 1)[0] if '学习者写的英文：\n' in prompt else 'I like it.'
    return J({'verdict': 'minor', 'summary': '意思清楚。', 'corrected': yours, 'changes': [],
              'versions': [{'label': '更自然', 'text': yours, 'why': '—'}], 'used_well': [], 'keep': None})


chat_service.request_model = fake

PID = 'v5-science-b2-noise-cancelling'
LEARNERS = {'a2': ('A2', 'daily', ['life']), 'b1': ('B1', 'work', ['work', 'science']), 'exam': ('B2', 'exam', ['science']),
            # one learner per device in tools/ui_test.py, so each device starts from the same state
            **{d: ('B1', 'work', ['work', 'science']) for d in ('phone', 'phone-land', 'tablet', 'desktop', 'phone-360')},
            'guide': ('B1', 'work', ['work', 'science']),  # the 操作指南 screenshots (tools/guide_shots.py)
            'leaver': ('B1', 'work', ['work', 'science']),  # 注销账号 in tools/ui_test.py (learner_run)
            'a11y': ('B1', 'work', ['work', 'science']),  # the screen-reader and contrast audit (a11y_run)
            'sprint': ('B1', 'exam', ['campus']),  # 考试冲刺: 四级 in 19 days, four practice sets done (sprint_run; the guide's exam pictures)
            # swiping the review card from anywhere on the screen (swipe_run): one learner per screen size, each starting fresh
            **{f'swipe-{k}': ('B1', 'work', ['work', 'science']) for k in ('ipad-land', 'ipad-mini-land', 'phone')}}
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
        if name == 'sprint':  # preparing for 四级 in 19 days on its word book, four sets done over four weeks, getting better
            import exam_service as ex, exam_sprint as sp, datetime
            day = (datetime.datetime.now(nx.TZ).date() + datetime.timedelta(days=19)).isoformat()
            sp.set_goal(c, uid, {'exam': 'cet4', 'date': day})
            vs.save_plan(c, uid, {'book': 'cet4', 'daily_new': 10, 'retention': 0.9})
            for k, share in enumerate((0.4, 0.5, 0.6, 0.75)):
                p, _ = ex.paper(c, uid, 'cet4')
                paper = json.loads(c.execute('SELECT content FROM next_exam_papers WHERE id=?', (p['paper'],)).fetchone()[0])
                right = lambda xs, n: [a if i < round(share * len(xs)) else (a + 1) % n for i, a in enumerate(xs)]
                grammar = [c.execute('SELECT answer FROM questions WHERE id=?', (g['id'],)).fetchone()[0] for g in paper['grammar']]
                ex.submit(c, uid, {'paper': p['paper'], 'seconds': 840 - 40 * k, 'answers': {'vocab': right([v['answer'] for v in paper['vocab']], 4),
                          'grammar': right(grammar, 4), 'reading': right([r['answer'] for r in paper['reading']], 4)}})
                c.execute('UPDATE next_exam_results SET created=? WHERE paper=?', (time.time() - (4 - k) * 7 * 86400, p['paper']))
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
            # 这周进步 (r27): four weeks that reached the goal (4 days), last week 3 days, this week every day so far; words
            # remembered this week and last (added one day, still recalled the next), texts finished, questions answered,
            # and one sentence the AI corrected in this text (the grammar line after it).
            import progress_service as ps, event_service as ev, datetime as dt
            today, monday, lo, prev = ps._bounds(now)
            at = lambda d, h=9: min(ps._start(d) + h * 3600, now - 600)  # never later than now, whenever the tests run
            anchor = c.execute("SELECT id FROM next_cards WHERE user_id=? AND norm='commute'", (uid,)).fetchone()[0]
            for w in range(2, 6):
                for k in (0, 1, 3, 5):
                    c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (uid, anchor, 'good', at(monday - dt.timedelta(weeks=w, days=-k))))
            for k in (0, 2, 4):
                c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (uid, anchor, 'good', at(monday - dt.timedelta(weeks=1, days=-k))))
            days = [monday + dt.timedelta(days=k) for k in range((today - monday).days + 1)]
            words = {'this': ['negotiate', 'reliable', 'efficient', 'priority', 'estimate', 'colleague', 'maintain', 'evidence', 'budget', 'survey', 'resource', 'approach'],
                     'last': ['schedule', 'agenda', 'deliver', 'feedback', 'proposal', 'confirm', 'invoice', 'client']}
            for when, ws in words.items():
                for k, w in enumerate(ws):
                    day = days[k % len(days)] if when == 'this' else monday - dt.timedelta(days=1 + k % 6)
                    cid = c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due,state,source) VALUES(?,?,?,'word',?,?,'review','book')",
                                    (uid, w, w, at(day - dt.timedelta(days=1), 8), at(day) + 3 * 86400)).lastrowid
                    c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (uid, cid, 'good', at(day, 8)))
            packs = [r[0] for r in c.execute("SELECT id FROM lab_packs WHERE owner IS NULL AND origin!='daily' AND id!=? ORDER BY id LIMIT 5", (PID,))]
            for k, pk in enumerate(packs):
                c.execute('INSERT OR IGNORE INTO next_progress VALUES(?,?,?,?)', (uid, pk, 'check', at(days[-1] if k < 2 else monday - dt.timedelta(days=2 + k), 19)))
            for k in range(23):
                ev.record(c, uid, 'skill:reading', f'guide:{k}', 'choice', str(k), 'q', int(k % 9 not in (3, 6) and k != 22 and k != 21), 0, 'rule', created=at(days[k % len(days)], 10) + k)
            for k in range(30):
                ev.record(c, uid, 'skill:reading', f'guide-prev:{k}', 'choice', str(k), 'q', int(k % 10 not in (1, 4, 8)), 0, 'rule', created=at(monday - dt.timedelta(days=1 + k % 7), 10) + k)
            c.execute("INSERT INTO next_node_notes(user_id,node,pack,kind,detail,created) VALUES(?,?,?,?,?,?)", (uid, 'agreement-head', PID, 'flag', 'guide|it make → it makes', now - 7200))
            sk.log(c, uid, 'speaking', 'ielts', 6.0 / 9, 'B2', 'ielts-p1-mornings')  # 雅思口语: 「上次约 6.0」 on the list
        c.commit()
        out[name] = {'token': token, 'csrf': csrf, 'id': uid, **({'password': secret} if secret else {})}
# 今日热点 (r27: its own card under 今日好句): one news text of today, as the daily job would leave it, clearly a sample
with app.db() as c:
    base = json.loads(c.execute("SELECT content FROM lab_packs WHERE id=?", (PID,)).fetchone()[0])
    base.update(id='daily-ui-sample', title='示例热点：城市开通夜间公交线路', title_en='Sample news: night buses start running',
                source='示例来源（测试数据）', summary_zh='示例：这里是今日热点的一句话介绍，真正的热点每天由 AI 联网找新闻改写。', daily_day=time.strftime('%Y-%m-%d'))
    c.execute("INSERT OR REPLACE INTO lab_packs VALUES(?,NULL,'daily',?,?)", ('daily-ui-sample', json.dumps(base, ensure_ascii=False), time.time()))
    c.commit()
(STATE / 'sessions.json').write_text(json.dumps({'base': f'http://127.0.0.1:{PORT}', 'pid': PID, 'learners': out}))

from http.server import ThreadingHTTPServer  # noqa: E402


class Server(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


print(f'ui server on http://127.0.0.1:{PORT}/ (data {tmp})', flush=True)
Server(('127.0.0.1', PORT), app.Handler).serve_forever()
