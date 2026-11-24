#!/usr/bin/env python3
"""Flow production end-to-end check with internal test accounts.

- Accounts qa-e2e-* get ids from 990001 up, so an id is never handed to a real learner later, and sessions are
  written straight into the database: no password is typed anywhere and the accounts cannot be signed into.
- Four learners run at the same time against the live app on 127.0.0.1:8090, with the real model and real
  (synthesized) speech: an A2 beginner, a B1 worker, an exam candidate and a "guard" that probes limits.
- Test accounts have no email address, so reminder and weekly-report mail can never go out.
- Afterwards it checks database invariants, deletes every row that belongs to the test accounts, verifies that none
  is left, and writes report.json next to this script. Leftovers of an interrupted run are removed before starting.
- Run after each deploy by tools/flow-autodeploy.py; the clips in qa-audio/ come from tools/qa_clips.py (Kokoro).
  Local dry run: QA_DB=<sqlite> QA_BASE=http://127.0.0.1:<port> python3 -I tools/qa_e2e.py
- Light run (QA_LIGHT=1: every automatic 内测版 release, .github/workflows/beta.yml): no check that sends a recording
  to the AI (pronunciation, shadowing, a dialogue turn by voice, a spoken retell). Those go through the Gemini relay,
  which has two places that learners on 语流 share; text AI on the 内测版 goes elsewhere. The full run is what 语流's
  releases and the daily run do.
- At most QA_AI_SLOTS (default 1) AI requests of this test are in flight at once, so the test never takes all of a
  model's places from learners while it runs (2026-11-24: three release tests in half an hour slowed 语流 down).
"""
import base64, concurrent.futures as cf, contextlib, datetime, json, os, re, secrets, sqlite3, statistics, sys, threading, time, traceback
import urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = os.getenv('QA_DB', '/www/wwwroot/flow/data/flow.sqlite3')
BASE = os.getenv('QA_BASE', 'http://127.0.0.1:8090')
AUD = Path(os.getenv('QA_AUDIO', HERE / 'qa-audio'))
PID = 'v5-science-b2-noise-cancelling'
IDS = {'a2': 990001, 'b1': 990002, 'exam': 990003, 'guard': 990004}
LOCK = threading.Lock()
LIGHT = os.getenv('QA_LIGHT') == '1'
AI_SLOT_COUNT = max(1, int(os.getenv('QA_AI_SLOTS', '1')))
AI_SLOTS = threading.BoundedSemaphore(AI_SLOT_COUNT)
CALLS, CHECKS, NOTES = [], [], []
T0 = time.time()


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def note(who, msg):
    with LOCK:
        NOTES.append({'t': round(time.time() - T0, 1), 'who': who, 'msg': msg})
    print(f'[{time.time() - T0:7.1f}] {who}: {msg}', flush=True)



def spoken(who, what):
    """Whether to run a check that sends a recording to the AI: a light run (QA_LIGHT=1) notes that it skipped it."""
    if LIGHT:
        note(who, f'light run: no recording sent to the AI ({what})')
    return not LIGHT

def check(who, name, ok, detail=''):
    with LOCK:
        CHECKS.append({'who': who, 'name': name, 'ok': bool(ok), 'detail': str(detail)[:600]})
    print(f'[{time.time() - T0:7.1f}] {who}: {"PASS" if ok else "FAIL"} {name} {"" if ok else str(detail)[:300]}', flush=True)
    return ok


def audio(name):
    return {'mime_type': 'audio/mp4', 'data': base64.b64encode((AUD / f'{name}.m4a').read_bytes()).decode()}


def rid(tag):
    return f'qae2e-{tag}-{secrets.token_hex(6)}'


class Client:
    def __init__(self, who, token=None, csrf=None):
        self.who, self.token, self.csrf = who, token, csrf

    def call(self, method, path, data=None, headers=None, raw=None, timeout=200, expect=None):
        h = {'Accept': 'application/json'}
        if self.token:
            h['Cookie'] = 'flow_session=' + self.token
        body = None
        if method == 'POST':
            body = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode()
            h['Content-Type'] = 'application/json'
            if self.csrf:
                h['X-CSRF-Token'] = self.csrf
        h.update(headers or {})
        req = urllib.request.Request(BASE + path, data=body, method=method, headers=h)
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, payload, ctype = r.status, r.read(), r.headers.get('Content-Type', '')
        except urllib.error.HTTPError as e:
            status, payload, ctype = e.code, e.read(), e.headers.get('Content-Type', '')
        except Exception as e:
            status, payload, ctype = 0, repr(e).encode(), ''
        ms = int((time.time() - t) * 1000)
        try:
            js = json.loads(payload) if 'json' in ctype else None
        except ValueError:
            js = None
        rec = {'who': self.who, 'method': method, 'path': path.split('?')[0], 'q': path[len(path.split('?')[0]):][:80], 'status': status,
               'ms': ms, 'bytes': len(payload)}
        if status >= 400 or status == 0:
            rec['error'] = (js or {}).get('error') if isinstance(js, dict) else payload[:200].decode('utf-8', 'replace')
        if expect is not None:
            rec['expected'] = expect
        with LOCK:
            CALLS.append(rec)
        if status >= 500 and expect != status:
            note(self.who, f'server error {status} on {method} {path}: {rec.get("error")}')
        return status, (js if js is not None else payload)

    def get(self, path, **kw):
        return self.call('GET', path, **kw)

    def post(self, path, data=None, **kw):
        return self.call('POST', path, data, **kw)

    def ai(self, path, data, tag, slot=True):
        """An AI request, waiting for one of the test's AI_SLOTS (slot=False: the caller already holds one)."""
        data = dict(data, request_id=rid(tag))
        with AI_SLOTS if slot else contextlib.nullcontext():
            s, j = self.post(path, data)
        res = j.get('result') if isinstance(j, dict) else None
        if s != 200:
            note(self.who, f'AI {path} -> {s} {j.get("error") if isinstance(j, dict) else j!r}'[:300])
        return s, j, res


# ---------- setup ----------

def setup():
    c = db()
    if c.execute('SELECT 1 FROM users WHERE id IN (%s) LIMIT 1' % ','.join('?' * len(IDS)), list(IDS.values())).fetchone():
        c.close()
        removed, _ = cleanup(record=False)
        note('setup', f'removed leftovers of an earlier run: {sum(removed.values())} rows')
        c = db()
    c.execute("DELETE FROM sessions WHERE user_id IN (%s)" % ','.join('?' * len(IDS)), list(IDS.values()))
    out = {}
    for name, uid in IDS.items():
        c.execute('INSERT INTO users(id,username,password,admin) VALUES(?,?,?,0)', (uid, f'qa-e2e-{name}', 'qa-e2e-no-login:' + secrets.token_hex(16)))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, uid, csrf, time.time() + 3 * 3600))
        out[name] = Client(name, token, csrf)
    c.commit()
    c.close()
    return out


def usage():
    c = db()
    day = time.strftime('%Y-%m-%d', time.gmtime())
    site = c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', (day,)).fetchone()[0]
    mine = {n: (c.execute('SELECT count FROM ai_usage WHERE user_id=? AND day=?', (u, day)).fetchone() or [0])[0] for n, u in IDS.items()}
    c.close()
    return {'day': day, 'site_today': site, 'test_accounts': mine}


def limits():
    def n(k):
        try:
            return int(os.getenv(k, '0'))
        except ValueError:
            return 0
    return {'site': n('FLOW_AI_DAILY_LIMIT'), 'user': n('FLOW_AI_USER_DAILY_LIMIT'), 'audio': os.getenv('FLOW_AI_AUDIO', '') not in ('', '0')}


def sentences(body):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', body or '') if s.strip()]


# ---------- personas ----------

def persona_a2(cl):
    who = 'a2'
    s, meta = cl.get('/api/next/meta')
    check(who, 'meta', s == 200 and meta.get('levels'), s)
    goal = meta['goals'][0]['id']
    themes = [t['id'] for t in meta['themes'][:2]]
    s, j = cl.post('/api/next/profile', {'level': 'A2', 'goal': goal, 'themes': themes, 'minutes': 10})
    check(who, 'save profile A2', s == 200 and j['profile']['level'] == 'A2', j)
    s, h = cl.get('/api/next/home')
    check(who, 'home has a daily path', s == 200 and isinstance(h.get('path'), dict) and h['path'].get('steps'), list(h)[:20] if isinstance(h, dict) else h)
    s, lib = cl.get('/api/next/library?level=A2')
    check(who, 'A2 library has materials', s == 200 and lib['total'] > 0 and lib['items'], lib.get('total') if isinstance(lib, dict) else lib)
    pid = lib['items'][0]['id']
    s, m = cl.get('/api/next/material?id=' + pid)
    check(who, 'open A2 material', s == 200 and m.get('id') == pid and m.get('questions'), s)
    for step in ('listen', 'read'):
        s, _ = cl.post('/api/next/progress', {'pack': pid, 'step': step})
        check(who, f'progress {step}', s == 200, s)
    s, bad = cl.post('/api/next/progress', {'pack': pid, 'step': 'nonsense'})
    check(who, 'bad step rejected', s == 400, s)
    # comprehension: make sure one answer is wrong, so a mistake card appears
    s, r0 = cl.post('/api/next/check', {'pack': pid, 'index': 0, 'choice': 0})
    check(who, 'check answer', s == 200 and 'correct' in r0, r0)
    if r0['correct']:
        s, r0 = cl.post('/api/next/check', {'pack': pid, 'index': 0, 'choice': 1})
    for i in range(1, len(m['questions'])):
        s, ri = cl.post('/api/next/check', {'pack': pid, 'index': i, 'choice': 0})
        if not ri.get('correct'):
            cl.post('/api/next/check', {'pack': pid, 'index': i, 'choice': ri['answer']})
    s, mc = cl.get('/api/next/cards?f=mistake')
    check(who, 'wrong answer became a mistake card', s == 200 and any(x.get('kind') == 'question' for x in mc.get('items', [])), mc.get('items', [])[:2] if isinstance(mc, dict) else mc)
    # dictionary + saving a word met in reading
    s, lk = cl.get('/api/next/lookup?w=weather')
    check(who, 'lookup weather', s == 200 and lk.get('entry'), lk)
    s, lk2 = cl.get('/api/next/lookup?w=went')
    check(who, 'lookup inflection went -> go', s == 200 and (lk2.get('entry') or {}).get('lemma') == 'go', (lk2.get('entry') or {}).get('lemma'))
    s, met = cl.post('/api/next/vocab/met', {'word': 'weather'})
    check(who, 'vocab/met', s == 200, met)
    s, sc = cl.post('/api/next/cards', {'text': 'weather', 'meaning': '天气', 'context': 'The weather is nice today.', 'pack': pid})
    check(who, 'save a word card', s == 200, sc)
    s, sc2 = cl.post('/api/next/cards', {'text': 'weather', 'meaning': '天气', 'context': 'The weather is nice today.', 'pack': pid})
    check(who, 'saving it again does not duplicate', s == 200, sc2)
    # plan + review session
    s, pl = cl.post('/api/next/vocab/plan', {'book': 'core', 'daily_new': 10, 'retention': 0.9})
    check(who, 'plan core book', s == 200, pl)
    s, q = cl.get('/api/next/review')
    check(who, 'review queue has items', s == 200 and len(q.get('items', [])) >= 5, (q.get('due'), q.get('new'), len(q.get('items', []))) if isinstance(q, dict) else q)
    grades = ['good', 'again', 'hard', 'easy', 'good', 'good', 'again']
    modes = ['recognize', 'recall', 'spell', 'cloze', 'recognize', 'recall', 'spell']
    rated = 0
    for k, it in enumerate(q.get('items', [])[:7]):
        body = {'id': it['id'], 'rating': grades[k], 'ms': 2500 + k * 300}
        if it.get('mode') not in ('fix', 'question', 'sound'):
            body['mode'] = modes[k]
        s, rr = cl.post('/api/next/review', body)
        rated += s == 200
        if s == 200 and k == 0:
            check(who, 'rated card is scheduled in the future', rr['card'].get('due', 0) > time.time() - 5 if isinstance(rr.get('card'), dict) and 'due' in rr['card'] else True, rr.get('card'))
    check(who, 'rate 7 cards', rated == min(7, len(q.get('items', []))), rated)
    s, bad = cl.post('/api/next/review', {'id': q['items'][0]['id'], 'rating': 'perfect'})
    check(who, 'invalid rating rejected', s == 400, s)
    # offline review synced later with its own timestamp
    if len(q.get('items', [])) > 8:
        s, off = cl.post('/api/next/review', {'id': q['items'][8]['id'], 'rating': 'good', 'at': time.time() - 600, 'mode': 'recall'})
        check(who, 'offline review with timestamp', s == 200, off)
    # sounds
    s, so = cl.get('/api/next/sounds')
    check(who, 'sounds listing', s == 200 and len(so.get('sets', so.get('items', []))) >= 10 if isinstance(so, dict) else False, list(so)[:5] if isinstance(so, dict) else so)
    if spoken(who, 'pronunciation, the sound card after two misses'):
        s, j, r = cl.ai('/api/next/say', {'text': 'think', 'audio': audio('think_ok')}, 'say')
        check(who, 'pronunciation check answers (think)', s == 200 and isinstance((r or {}).get('ok'), bool), r)
        note(who, f"AI verdict on a synthetic 'think': {r}")  # a model's judgement of one synthetic word: information, not a test
        first_ok = bool(r and r.get('ok'))
        s, j, r = cl.ai('/api/next/say', {'text': 'think', 'audio': audio('think_as_sink')}, 'say')
        check(who, 'pronunciation check answers (sink for think)', s == 200 and isinstance((r or {}).get('ok'), bool), r)
        note(who, f"AI verdict on 'sink' said for 'think': {r}")
        second_miss = bool(r and r.get('ok') is False)
        s, mc = cl.get('/api/next/cards?f=mistake')
        has_card = any(x.get('kind') == 'sound' for x in mc.get('items', []))
        check(who, 'a sound card only after two misses in a row', has_card == (second_miss and not first_ok), (first_ok, second_miss, has_card))
    s, _ = cl.post('/api/next/skill', {'kind': 'discriminate', 'score': 0.7})
    check(who, 'log discrimination score', s == 200, s)
    s, _ = cl.post('/api/next/skill', {'kind': 'dictation', 'score': 0.8, 'pack': pid})
    check(who, 'log dictation score', s == 200, s)
    s, _ = cl.post('/api/next/skill', {'kind': 'grammar', 'score': 0.8})
    check(who, 'unknown skill kind rejected', s == 400, s)
    # writing with the model
    s, j, r = cl.ai('/api/next/rewrite', {'pack': pid, 'text': 'I like go to the park with my friend in weekend, we play football very happy.'}, 'rw')
    check(who, 'AI rewrite of an A2 sentence', s == 200 and isinstance(r, dict), r if s == 200 else j)
    sent = (m.get('sentences') or ['I like it.'])[0]
    s, j, r = cl.ai('/api/next/explain', {'pack': pid, 'sentence': sent}, 'ex')
    check(who, 'AI explains a sentence', s == 200 and isinstance(r, dict), j if s != 200 else list(r)[:6])
    s, ab = cl.get('/api/next/ability')
    check(who, 'ability profile', s == 200 and len(ab.get('skills', [])) >= 5, ab)
    s, rp = cl.get('/api/next/report')
    check(who, 'weekly report', s == 200 and isinstance(rp, dict), list(rp)[:10] if isinstance(rp, dict) else rp)
    s, st = cl.get('/api/next/stats')
    check(who, 'stats', s == 200, st)
    s, v = cl.get('/api/next/vocab')
    check(who, 'vocab overview', s == 200, list(v)[:10] if isinstance(v, dict) else v)


def persona_b1(cl):
    who = 'b1'
    s, meta = cl.get('/api/next/meta')
    goal = next((g['id'] for g in meta['goals'] if g['id'] == 'work'), meta['goals'][0]['id'])
    s, j = cl.post('/api/next/profile', {'level': 'B1', 'goal': goal, 'themes': [t['id'] for t in meta['themes'][:3]], 'minutes': 15})
    check(who, 'save profile B1', s == 200, j)
    s, m = cl.get('/api/next/material?id=' + PID)
    check(who, 'open science material', s == 200 and m.get('id') == PID, s)
    sents = m.get('sentences') or []
    if spoken(who, 'shadowing'):
        s, j, r = cl.ai('/api/next/shadow', {'pack': PID, 'i': 0, 'audio': audio('shadow_s0')}, 'sh')
        check(who, 'AI scores shadowing (native-like clip)', s == 200 and isinstance(r, dict), j if s != 200 else {k: r.get(k) for k in list(r)[:6]})
        if s == 200:
            sc = r.get('score', r.get('accuracy'))
            if isinstance(sc, dict):  # since r27 (#41): {accuracy, fluency, complete, total}, 0–100 each
                sc = sc.get('total')
            check(who, 'shadow of a clean reading scores well', sc is None or (isinstance(sc, (int, float)) and sc >= (0.6 if sc <= 1 else 60)), r.get('score', sc))
    s, j, r = cl.ai('/api/next/variant', {'pack': PID, 'level': 'B1'}, 'nv')
    check(who, 'AI makes a B1 version', s == 200, j if s != 200 else (r or j).get('level') if isinstance(r or j, dict) else j)
    s, j, r = cl.ai('/api/next/explain', {'pack': PID, 'sentence': sents[1] if len(sents) > 1 else sents[0]}, 'ex')
    check(who, 'AI explains a B2 sentence', s == 200, j if s != 200 else '')
    # role-play
    s, j, r = cl.ai('/api/next/dialog', {'pack': PID, 'history': []}, 'dg')
    opening = (r or {}).get('reply') or (r or {}).get('text') or ''
    check(who, 'dialog opens with an AI line', s == 200 and len(opening) > 5, r if s == 200 else j)
    hist = [{'role': 'ai', 'text': opening[:480] or 'Hello! How can I help you?'}]
    if spoken(who, 'a dialogue turn by voice'):
        s, j, r = cl.ai('/api/next/dialog', {'pack': PID, 'history': hist, 'audio': audio('dialog')}, 'dg')
        check(who, 'dialog turn by voice (transcribed + reply)', s == 200 and isinstance(r, dict) and (r.get('reply') or r.get('text')), r if s == 200 else j)
        if s == 200:
            tr = (r.get('heard') or '').lower()
            check(who, 'dialog transcript matches what was said', 'headphones' in tr or 'train' in tr, tr)
            hist += [{'role': 'me', 'text': (r.get('heard') or 'I would like some headphones.')[:480]}, {'role': 'ai', 'text': (r.get('reply') or r.get('text') or 'Sure.')[:480]}]
    else:  # typed instead, so the round still has a learner turn to give feedback on
        said = 'I would like some headphones for the train, please.'
        s, j, r = cl.ai('/api/next/dialog', {'pack': PID, 'history': hist, 'text': said}, 'dg')
        check(who, 'dialog turn by text (reply)', s == 200 and isinstance(r, dict) and (r.get('reply') or r.get('text')), r if s == 200 else j)
        if s == 200:
            hist += [{'role': 'me', 'text': said}, {'role': 'ai', 'text': (r.get('reply') or r.get('text') or 'Sure.')[:480]}]
    s, j, r = cl.ai('/api/next/dialog', {'pack': PID, 'history': hist, 'end': True}, 'dg')
    check(who, 'dialog end gives feedback', s == 200 and isinstance(r, dict), r if s == 200 else j)
    s, j = cl.post('/api/next/dialog', {'pack': PID, 'history': [{'role': 'x', 'text': 'hi'}], 'text': 'hello there', 'request_id': rid('dg')})
    check(who, 'bad dialog history rejected', s == 400, j)
    # translation both ways
    s, j, r = cl.ai('/api/next/translate/source', {'pack': PID, 'i': 1}, 'ts')
    zh = (j or {}).get('zh') or '' if isinstance(j, dict) else ''
    check(who, 'AI gives the Chinese of sentence 2', s == 200 and len(zh) >= 4, j)
    s, j, r = cl.ai('/api/next/translate', {'pack': PID, 'i': 1, 'direction': 'zh2en', 'text': 'The headphone listen the noise around and make a opposite wave to cancel it.'}, 'tr')
    check(who, 'AI checks a zh->en translation', s == 200 and isinstance(r, dict), r if s == 200 else j)
    s, j, r = cl.ai('/api/next/translate', {'pack': PID, 'i': 2, 'direction': 'en2zh', 'text': '耳机会产生相反的声波来抵消噪音。'}, 'tr')
    check(who, 'AI checks an en->zh translation', s == 200 and isinstance(r, dict), r if s == 200 else j)
    # own word list + AI examples for words no material uses
    s, j = cl.post('/api/next/vocab/import', {'text': 'deadline\nnegotiate\ncommute\nquarterly\nreimburse\nxqzvbn'})
    check(who, 'import a word list (one bogus word)', s == 200, j)
    s, j = cl.post('/api/next/vocab/examples', {'words': ['reimburse', 'quarterly', 'wobble', 'zesty'], 'request_id': rid('ve')})
    check(who, 'AI examples for words without material examples', s == 200, j)
    s, q = cl.get('/api/next/review')
    check(who, 'review queue', s == 200, s)
    for it in q.get('items', [])[:5]:
        cl.post('/api/next/review', {'id': it['id'], 'rating': 'good', 'mode': 'recall', 'ms': 3000})
    s, ab = cl.get('/api/next/ability')
    check(who, 'ability after speaking/writing', s == 200, ab.get('weakest') if isinstance(ab, dict) else ab)
    s, h = cl.get('/api/next/home')
    check(who, 'home', s == 200, s)
    check(who, 'home says how many featured texts are left and marks each card\'s kind (精选/重学/简版)',
          isinstance(h.get('featured_left'), int) and all(isinstance(m.get('brief'), bool) for m in h.get('today') or []),
          {'featured_left': h.get('featured_left'), 'brief': [m.get('brief') for m in h.get('today') or []]})


ESSAY = ('Many people think noise cancelling headphones is only for rich travellers, but I disagree. In my opinion they are useful for '
         'everyone who work in a busy office. When the air conditioner and the printers make a constant low noise, it is hard to focus '
         'for long time. With these headphones the steady sound almost disappear, so I can concentrate on my report. However, they can '
         'not block voices very well, so you still hear your colleagues. Overall, I believe they are a good investment for students and workers.')
ARTICLE = ('Scientists have long wondered why some birds migrate at night. One idea is that the cooler air saves energy on long flights. '
           'Another is that darkness protects small birds from predators that hunt by sight. Recent observations suggest both reasons matter, '
           'and that the stars may help the birds keep their direction when the sky is clear. On cloudy nights, they seem to rely on other cues, '
           'such as the earth\'s magnetic field and familiar landmarks below.')


def persona_exam(cl):
    who = 'exam'
    s, t = cl.get('/api/next/vocab/test')
    check(who, 'vocab size test items', s == 200 and len(t.get('items', [])) >= 30, len(t.get('items', [])) if isinstance(t, dict) else t)
    items = t['items']
    # an advanced learner: knows nearly every real word, rejects the made-up ones (we cannot tell which are fake here,
    # so the scorer's guessing correction is tested with "yes" to everything except a handful)
    answers = {w: (k % 9 != 0) for k, w in enumerate(items)}
    s, sc = cl.post('/api/next/vocab/test', {'answers': answers})
    check(who, 'vocab test scored', s == 200 and isinstance(sc.get('estimate'), int), sc)
    s, pl = cl.post('/api/next/vocab/plan', {'book': 'ielts', 'daily_new': 15, 'retention': 0.95})
    check(who, 'plan IELTS book (skipping known words)', s == 200, pl)
    s, v = cl.get('/api/next/vocab')
    check(who, 'vocab overview shows the IELTS plan', s == 200 and 'ielts' in json.dumps(v), (v.get('plan') if isinstance(v, dict) else v))
    s, j = cl.post('/api/next/profile', {'level': 'B2', 'goal': 'exam', 'themes': ['science'], 'minutes': 30})
    check(who, 'save profile B2 exam', s == 200, j)
    # r13: the starting check, a CET-6 practice set handed in blank (no evidence either way), the serial, the re-check ladder
    s, t = cl.get('/api/next/placement')
    check(who, 'starting check: 16 questions, no answers sent', s == 200 and len(t.get('items', [])) == 16 and not any('answer' in i for i in t['items']), s)
    if s == 200:
        s, r = cl.post('/api/next/placement', {'answers': [{'question': i['id'], 'choice': None} for i in t['items'][:4]]})
        check(who, 'starting check: decided after a band answered "不会"', s == 200 and r.get('done') and r.get('level') == 'A2', r)
    s, pp = cl.post('/api/next/exam/paper', {'exam': 'cet6'})
    check(who, 'exam practice: a CET-6 paper of 22 questions', s == 200 and sum(len(x.get('items') or [q for ps in x['passages'] for q in ps['items']]) for x in pp['parts']) == 22, s)
    if s == 200:
        s, r = cl.post('/api/next/exam/submit', {'paper': pp['paper'], 'answers': {}, 'seconds': 60})
        check(who, 'exam practice: handed in and saved', s == 200 and r.get('total') == 22 and r.get('saved') and len(r.get('history', [])) >= 1, r if s != 200 else r.get('parts'))
        s, again = cl.post('/api/next/exam/submit', {'paper': pp['paper'], 'answers': {}})
        check(who, 'exam practice: a paper is handed in once', s == 404, s)
    s, se = cl.get('/api/next/series?id=lighthouse-ledger')
    check(who, 'serial: six episodes in order', s == 200 and [e.get('part') for e in se.get('episodes', [])] == [1, 2, 3, 4, 5, 6], s)
    s, nd = cl.get('/api/next/node?id=modal-past')
    check(who, 'point page: a round of 4 drawn from the bank, options mapped', s == 200 and len(nd.get('practice', [])) == 4 and all(sorted(q['map']) == [0, 1, 2, 3] for q in nd['practice']), s)
    # r14: the learning route, a point's trap and links, an interleaved pair round, and extra new words on request
    s, g = cl.get('/api/next/graph')
    check(who, 'graph: a learning route through all 44 points', s == 200 and sum(len(b['nodes']) for b in g.get('route', [])) == 44 and len(g['links']['confusable']) >= 30, s)
    check(who, 'point page: Chinese-speaker trap and confusable points', s == 200 and nd.get('l1') and nd.get('related', {}).get('confusable'), list(nd.get('related', {})) if isinstance(nd, dict) else nd)
    s, mx = cl.get('/api/next/mix?pair=tense-past,tense-perfect')
    check(who, 'mixed round: a confusable pair interleaved', s == 200 and len(mx.get('items', [])) == 6 and all(a['node'] != b['node'] for a, b in zip(mx['items'], mx['items'][1:])), s)
    s, mo = cl.post('/api/next/vocab/more', {'n': 5})
    check(who, 'words: five more new words on request', s == 200 and mo.get('added') == 5, mo)
    # r15: easy reading, a word group in the look-up, the speaking route, the B1 serial, my progress
    s, ez = cl.get('/api/next/easy')
    check(who, 'easy reading: texts a level below', s == 200 and ez.get('target') == 'B1' and ez.get('items'), s)
    if s == 200 and ez.get('items'):
        s, ed = cl.post('/api/next/easy/done', {'pack': ez['items'][0]['id'], 'seconds': 80, 'rating': 'ok'})
        check(who, 'easy reading: words and speed recorded', s == 200 and ed.get('saved') and ed.get('words', 0) > 0, ed)
    s, lk = cl.get('/api/next/lookup?w=lent')
    check(who, 'look-up names the confusable group', s == 200 and (lk.get('entry') or {}).get('confusable', [{}])[0].get('id') == 'borrow-lend', s)
    s, sp = cl.get('/api/next/speak')
    check(who, 'speaking route: twelve scenes', s == 200 and sp.get('total') == 12 and sp.get('next'), s)
    s, se = cl.get('/api/next/series?id=a-new-term')
    check(who, 'B1 serial: six episodes', s == 200 and se.get('of') == 6, s)
    s, gw = cl.get('/api/next/growth')
    check(who, 'my progress: this month and milestones', s == 200 and gw.get('now', {}).get('words_read', 0) > 0 and len(gw.get('milestones', [])) >= 10, s)
    # r17: the ability radar: goals, a reading check, the radar with the measured skill
    s, rg = cl.post('/api/next/radar/goals', {'goals': {'reading': 'B2', 'speaking': 'B1'}})
    check(who, 'radar: goals saved', s == 200 and rg.get('goals', {}).get('speaking') == 'B1', s)
    s, at = cl.get('/api/next/assess/test?kind=reading')
    check(who, 'radar: a reading check of 2–3 texts around the level', s == 200 and 2 <= len(at.get('passages', [])) <= 3, s)
    if s == 200:
        ans = [{'pack': p['pack'], 'i': q['i'], 'choice': 0} for p in at['passages'] for q in p['questions']]
        s, sc = cl.post('/api/next/assess/comprehension', {'kind': 'reading', 'answers': ans})
        check(who, 'radar: the check is scored and recorded', s == 200 and sc.get('recorded', {}).get('skill') == 'reading', s)
    s, rr = cl.get('/api/next/radar')
    check(who, 'radar: reading measured against its goal', s == 200 and next(d for d in rr['dims'] if d['id'] == 'reading')['source'] == 'assessment', s)
    s, m = cl.get('/api/next/material?id=' + PID)
    check(who, 'material has a speaking and writing task', s == 200 and (m.get('speaking_task') or m.get('writing_task')), [k for k in m if 'task' in k] if isinstance(m, dict) else m)
    s, j, r = cl.ai('/api/next/retell', {'pack': PID, 'text': 'The article say noise cancelling headphones listen to the outside noise and make a opposite sound wave. '
                                         'So the engine noise become very quiet, but they are not good for voices.'}, 'rt')
    check(who, 'AI scores a written retell', s == 200 and isinstance(r, dict) and r.get('points'), r if s == 200 else j)
    if s == 200:
        check(who, 'retell score in [0,1]', 0 <= r.get('score', -1) <= 1, r.get('score'))
    if spoken(who, 'a spoken retell'):
        s, j, r = cl.ai('/api/next/retell', {'pack': PID, 'audio': audio('retell')}, 'rt')
        check(who, 'AI scores a spoken retell (transcribes it)', s == 200 and isinstance(r, dict) and len(r.get('transcript', '')) > 40, (r or {}).get('transcript', '')[:200] if s == 200 else j)
    s, j, r = cl.ai('/api/next/essay', {'pack': PID, 'text': ESSAY}, 'es')
    check(who, 'AI marks an essay', s == 200 and isinstance(r, dict), r if s == 200 else j)
    if s == 200:
        sc = r.get('scores') or {}
        check(who, 'essay has 4 sub-scores', isinstance(sc, dict) and len(sc) >= 4 or isinstance(sc, list) and len(sc) >= 4, sc)
    s, j = cl.post('/api/next/essay', {'pack': PID, 'text': 'Too short.', 'request_id': rid('es')})
    check(who, 'too-short essay rejected without a model call', s == 400, j)
    # import an article, enrich it with AI, study it, delete it
    s, im = cl.post('/api/next/import', {'title': 'Night migration', 'text': ARTICLE})
    check(who, 'import an article', s == 200 and im.get('id', '').startswith('imp-'), im)
    iid = im.get('id', '')
    s, im2 = cl.post('/api/next/import', {'title': 'Night migration', 'text': ARTICLE})
    check(who, 're-import is recognised', s == 200 and im2.get('existing') is True, im2)
    s, lst = cl.get('/api/next/import')
    check(who, 'my articles lists it', s == 200 and any(x.get('id') == iid for x in lst.get('items', [])), lst)
    s, j, r = cl.ai('/api/next/import/enrich', {'id': iid}, 'ie')
    check(who, 'AI adds questions/expressions to the import', s == 200, j if s != 200 else '')
    s, im_m = cl.get('/api/next/material?id=' + iid)
    check(who, 'imported article opens as material', s == 200 and im_m.get('imported'), {k: im_m.get(k) for k in ('id', 'imported', 'level')} if isinstance(im_m, dict) else im_m)
    if s == 200 and im_m.get('questions'):
        s, ck = cl.post('/api/next/check', {'pack': iid, 'index': 0, 'choice': 0})
        check(who, 'check a question on the imported article', s == 200, ck)
    s, bad = cl.post('/api/next/import', {'title': 'x', 'text': '这是一篇中文文章。' * 40})
    check(who, 'non-English import rejected', s == 400, bad)
    with LOCK:
        SHARED['exam_import'] = iid
    # reminders: switch on for an hour that is not now, read the calendar file, switch off
    hour_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).hour
    hr = next(h for h in range(6, 24) if abs(h - hour_now) >= 2)
    s, j = cl.post('/api/next/vocab/reminder', {'enabled': True, 'hour': hr})
    check(who, 'email reminder needs a bound address (test accounts have none)', s == 400 and '邮箱' in (j.get('error') or ''), (s, j))
    s, ics = cl.get(f'/api/next/vocab/reminder.ics?hour={hr}')
    check(who, 'calendar reminder file', s == 200 and b'BEGIN:VCALENDAR' in (ics if isinstance(ics, bytes) else b''), ics[:80] if isinstance(ics, bytes) else ics)
    s, j = cl.post('/api/next/vocab/reminder', {'enabled': False, 'hour': hr})
    check(who, 'turn reminder off', s == 200, j)
    # mistakes from writing come back in review as "fix" cards
    s, mc = cl.get('/api/next/cards?f=mistake')
    kinds = [x.get('kind') for x in mc.get('items', [])] if isinstance(mc, dict) else []
    check(who, 'writing mistakes became fix cards', 'fix' in kinds, kinds)
    s, q = cl.get('/api/next/review')
    fixes = [x for x in q.get('items', []) if x.get('mode') == 'fix']
    check(who, 'fix cards are in today\'s review', bool(fixes) or 'fix' not in kinds, [x.get('mode') for x in q.get('items', [])][:12])
    for it in fixes[:3]:
        s, _ = cl.post('/api/next/review', {'id': it['id'], 'rating': 'good', 'ms': 6000})
        check(who, 'review a fix card', s == 200, s)
    words = [x for x in q.get('items', []) if x.get('mode') not in ('fix', 'question', 'sound')]
    if words:
        s, j = cl.post('/api/next/vocab/known', {'id': words[0]['id'], 'known': True})
        check(who, 'mark a word as already known', s == 200, j)
    s, rp = cl.get('/api/next/report')
    check(who, 'weekly report', s == 200, s)
    s, ab = cl.get('/api/next/ability')
    check(who, 'ability profile', s == 200, s)


SHARED = {}


def persona_guard(cl, others):
    who = 'guard'
    anon = Client('anon')
    s, _ = anon.get('/api/next/cards')
    check(who, 'cards need sign-in', s == 401, s)
    s, _ = anon.post('/api/next/review', {'id': 1, 'rating': 'good'})
    check(who, 'review needs sign-in', s == 401, s)
    s, _ = anon.post('/api/next/say', {'text': 'think', 'audio': audio('think_ok'), 'request_id': rid('sy')})
    check(who, 'AI endpoints need sign-in', s == 401, s)
    s, h = anon.get('/api/next/home')
    check(who, 'guest home works', s == 200, s)
    nocsrf = Client('guard', cl.token, None)
    s, _ = nocsrf.post('/api/next/profile', {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 10})
    check(who, 'POST without CSRF token refused', s == 403, s)
    badcsrf = Client('guard', cl.token, 'x' * 32)
    s, _ = badcsrf.post('/api/next/profile', {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 10})
    check(who, 'POST with wrong CSRF token refused', s == 403, s)
    s, _ = cl.post('/api/next/profile', {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 10}, headers={'Sec-Fetch-Site': 'cross-site'})
    check(who, 'cross-site POST refused', s == 403, s)
    s, j = cl.post('/api/next/profile', {'level': 'B1', 'goal': 'work', 'themes': ['science'], 'minutes': 10})
    check(who, 'save profile', s == 200, j)
    s, _ = cl.post('/api/next/essay', None, raw=json.dumps({'pack': PID, 'text': 'word ' * 12000}).encode())
    check(who, 'oversized essay body refused', s == 400, s)
    s, _ = cl.post('/api/next/profile', None, raw=b'{not json')
    check(who, 'malformed JSON -> 400', s == 400, s)
    s, _ = cl.post('/api/next/profile', None, raw=b'[1,2]')
    check(who, 'non-object JSON -> 400', s == 400, s)
    webm_as_mp4 = {'mime_type': 'audio/mp4', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
    s, _ = cl.post('/api/next/say', {'text': 'think', 'audio': webm_as_mp4, 'request_id': rid('sy')})
    check(who, 'audio whose bytes do not match its type refused', s == 400, s)
    s, _ = cl.post('/api/next/say', {'text': 'think', 'audio': audio('think_ok'), 'request_id': 'short'})
    check(who, 'malformed request id refused', s == 400, s)
    s, _ = cl.post('/api/next/say', {'text': 'zzqxv', 'audio': audio('think_ok'), 'request_id': rid('sy')})
    check(who, 'say: non-word target refused', s == 400, s)
    s, _ = cl.get('/api/next/material?id=does-not-exist')
    check(who, 'unknown material 404', s == 404, s)
    s, _ = cl.get('/api/next/lookup?w=' + 'a' * 60)
    check(who, 'over-long lookup handled', s in (200, 400), s)
    # three AI requests at once from one learner: queued one after another, all succeed, none is lost
    t = time.time()
    # the server runs one learner's AI requests one after another, so the three hold one of the test's slots together
    with AI_SLOTS, cf.ThreadPoolExecutor(3) as ex:
        texts = ['I am agree that the noise is a big problem in city.', 'Yesterday I buy a new headphone for my journey.',
                 'The machine make sound that cancel other sound.']
        res = list(ex.map(lambda x: cl.ai('/api/next/rewrite', {'pack': PID, 'text': x}, 'cc', slot=False), texts))
    check(who, '3 simultaneous AI requests all complete (queued per learner)', all(r[0] == 200 for r in res), [r[0] for r in res])
    note(who, f'3 queued AI calls took {time.time() - t:.1f}s')
    # same request id again: the stored result comes back, no second model call
    before = usage()['test_accounts']['guard']
    r_id = rid('idem')
    body = {'pack': PID, 'text': 'She have been living here since five years.', 'request_id': r_id}
    s1, j1 = cl.post('/api/next/rewrite', body)
    s2, j2 = cl.post('/api/next/rewrite', body)
    after = usage()['test_accounts']['guard']
    same = s1 == 200 and s2 == 200 and j1['result'].get('corrected') == j2['result'].get('corrected')
    check(who, 'retry with the same request id returns the saved result', same, (s1, s2))
    check(who, 'retry returns the same display fields', same and j1['result'] == j2['result'],
          {k: (j1['result'].get(k), j2['result'].get(k)) for k in ('used_well', 'changes')} if same else '')
    check(who, 'the retry did not use another AI call', after - before == 1, (before, after))
    s3, j3 = cl.post('/api/next/rewrite', dict(body, text='Something completely different here.'))
    check(who, 'same request id with different content refused', s3 == 409, (s3, j3))
    # isolation between learners
    while 'exam_import' not in SHARED and time.time() - T0 < 900:
        time.sleep(2)
    iid = SHARED.get('exam_import')
    if iid:
        s, _ = cl.get('/api/next/material?id=' + iid)
        check(who, "another learner's imported article is private", s == 404, s)
        s, _ = cl.post('/api/next/import/delete', {'id': iid})
        check(who, "cannot delete another learner's article", s == 404, s)
    c = db()
    other_card = c.execute('SELECT id FROM next_cards WHERE user_id=? LIMIT 1', (IDS['a2'],)).fetchone()
    c.close()
    if other_card:
        s, _ = cl.post('/api/next/review', {'id': other_card[0], 'rating': 'easy'})
        check(who, "cannot review another learner's card", s == 404, s)
        s, _ = cl.post('/api/next/vocab/known', {'id': other_card[0], 'known': True})
        check(who, "cannot change another learner's card", s in (404, 200), s)
        c = db()
        k = c.execute('SELECT known FROM next_cards WHERE id=?', (other_card[0],)).fetchone()[0]
        c.close()
        check(who, "other learner's card unchanged", k == 0, k)
        s, _ = cl.post('/api/next/cards/delete', {'id': other_card[0]})
        c = db()
        still = c.execute('SELECT 1 FROM next_cards WHERE id=?', (other_card[0],)).fetchone()
        c.close()
        check(who, "cannot delete another learner's card", still is not None, s)
    # quota: at the per-learner ceiling the model is not called
    lim = limits()['user']
    if lim:
        c = db()
        day = time.strftime('%Y-%m-%d', time.gmtime())
        old = (c.execute('SELECT count FROM ai_usage WHERE user_id=? AND day=?', (IDS['guard'], day)).fetchone() or [0])[0]
        c.execute('INSERT INTO ai_usage VALUES(?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET count=excluded.count', (IDS['guard'], day, lim))
        c.commit()
        s, j = cl.post('/api/next/rewrite', {'pack': PID, 'text': 'This should not reach the model at all.', 'request_id': rid('q')})
        cnt = c.execute('SELECT count FROM ai_usage WHERE user_id=? AND day=?', (IDS['guard'], day)).fetchone()[0]
        check(who, 'at the daily ceiling: 429, no model call', s == 429 and cnt == lim, (s, j, cnt))
        check(who, 'ceiling message tells when it resets', '8 点' in (j.get('error') or ''), j.get('error'))
        c.execute('UPDATE ai_usage SET count=? WHERE user_id=? AND day=?', (old, IDS['guard'], day))
        c.commit()
        c.close()
    else:
        note(who, 'no per-learner AI ceiling configured; quota check skipped')
    # one card rated twice at the same moment (double tap, or offline queue + live)
    s, pl = cl.post('/api/next/vocab/plan', {'book': 'core', 'daily_new': 5, 'retention': 0.9})
    s, q = cl.get('/api/next/review')
    if q.get('items'):
        cid = q['items'][0]['id']
        with cf.ThreadPoolExecutor(2) as ex:
            rs = list(ex.map(lambda g: cl.post('/api/next/review', {'id': cid, 'rating': g, 'mode': 'recall'}), ['good', 'good']))
        c = db()
        reps = c.execute('SELECT reps FROM next_cards WHERE id=?', (cid,)).fetchone()[0]
        nrev = c.execute('SELECT COUNT(*) FROM next_reviews WHERE card=?', (cid,)).fetchone()[0]
        c.close()
        check(who, 'double-tapped rating keeps reps and review log consistent', reps == nrev, (reps, nrev, [r[0] for r in rs]))
    # load: 60 reads at once across all learners
    paths = ['/api/next/home', '/api/next/library?page=1', '/api/next/material?id=' + PID, '/api/next/vocab', '/api/next/review',
             '/api/next/ability', '/api/next/cards?page=1', '/api/next/report', '/api/next/graph', '/api/next/sounds']
    jobs = [(cli, p) for p in paths for cli in [cl] + others][:60]
    t = time.time()
    with cf.ThreadPoolExecutor(20) as ex:
        rs = list(ex.map(lambda a: (a[1], a[0].get(a[1]), ), jobs))
    took = time.time() - t
    sts = [r[1][0] for r in rs]
    check(who, f'60 concurrent reads all 200 ({took:.1f}s)', all(x == 200 for x in sts), [p for p, (s, _) in rs if s != 200][:10])
    # static files and audio through the app (the CDN layer is checked separately from outside)
    raw = Client('guard')
    for p, want in (('/', 200), ('/sw.js', 200), ('/manifest.webmanifest', 200), ('/next.js?v=11', 200), ('/icon-192.png', 200)):
        s, _ = raw.get(p)
        check(who, f'static {p}', s == want, s)
    # the 操作指南 PDF is printed when a commit is released (tools/build_release.py): the site offers it, and it downloads
    s, g = raw.get('/api/next/guide')
    check(who, 'the guide offers its PDF', s == 200 and isinstance(g, dict) and g.get('pdf') == '/guide.pdf', (s, g.get('pdf') if isinstance(g, dict) else str(g)[:100]))
    try:
        with urllib.request.urlopen(BASE + '/guide.pdf', timeout=30) as r:
            head = r.read(5)
            check(who, 'the guide PDF downloads', r.status == 200 and head == b'%PDF-' and r.headers.get('Content-Type') == 'application/pdf', (r.status, head))
    except urllib.error.HTTPError as e:
        check(who, 'the guide PDF downloads', False, e.code)
    s, wi = cl.get('/api/next/material?id=' + PID)
    au = (wi.get('audio') or {}) if isinstance(wi, dict) else {}
    src = f"/audio/{au['voices'][0]}/{PID}.mp4" if au.get('voices') else None
    if src:
        rq = urllib.request.Request(BASE + src, headers={'Range': 'bytes=0-99'})
        try:
            with urllib.request.urlopen(rq, timeout=20) as r:
                check(who, 'narration audio byte range', r.status == 206 and len(r.read()) == 100, r.status)
        except urllib.error.HTTPError as e:
            check(who, 'narration audio byte range', False, e.code)
    else:
        note(who, f'material audio field: {json.dumps(au)[:200]}')


# ---------- invariants + cleanup ----------

def user_columns(c):
    out = []
    for (tb,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = {r[1] for r in c.execute(f'PRAGMA table_info("{tb}")')}
        refs = {r[3] for r in c.execute(f'PRAGMA foreign_key_list("{tb}")') if r[2] == 'users'}
        for col in sorted((refs | (cols & {'user_id', 'owner', 'actor'})) - ({'id'} if tb == 'users' else set())):
            out.append((tb, col))
    return out


def invariants():
    who = 'db'
    c = db()
    ids = list(IDS.values())
    ph = ','.join('?' * len(ids))
    pend = c.execute(f"SELECT COUNT(*) FROM lab_jobs WHERE user_id IN ({ph}) AND status='pending'", ids).fetchone()[0]
    check(who, 'no AI job left pending', pend == 0, pend)
    jobs = c.execute(f"SELECT status, COUNT(*) FROM lab_jobs WHERE user_id IN ({ph}) GROUP BY status", ids).fetchall()
    note(who, 'AI jobs by status: ' + json.dumps({r[0]: r[1] for r in jobs}))
    fails = c.execute(f"SELECT kind, error FROM lab_jobs WHERE user_id IN ({ph}) AND status='failed'", ids).fetchall()
    check(who, 'no AI job failed', not fails, [dict(r) for r in fails])
    bad = c.execute(f"SELECT COUNT(*) FROM next_cards WHERE user_id IN ({ph}) AND state!='new' AND (stability IS NULL OR stability<=0 OR difficulty<1 OR difficulty>10 OR due IS NULL OR last IS NULL)", ids).fetchone()[0]
    check(who, 'reviewed cards have valid FSRS state', bad == 0, bad)
    graded = "r.card=c.id AND r.rating IN ('again','hard','good','easy')"  # 'used', 'lookup', 'known' are evidence, not reviews
    mism = c.execute(f"SELECT c.id, c.reps, (SELECT COUNT(*) FROM next_reviews r WHERE {graded}) n FROM next_cards c WHERE c.user_id IN ({ph}) AND c.reps != (SELECT COUNT(*) FROM next_reviews r WHERE {graded})", ids).fetchall()
    check(who, 'card reps match the review log', not mism, [tuple(r) for r in mism][:10])
    dup = c.execute(f"SELECT user_id, norm, COUNT(*) n FROM next_cards WHERE user_id IN ({ph}) GROUP BY user_id, norm HAVING n>1", ids).fetchall()
    check(who, 'no duplicate cards', not dup, [tuple(r) for r in dup])
    mk = c.execute(f"SELECT kind, skill, COUNT(*) FROM next_cards WHERE user_id IN ({ph}) AND source='mistake' GROUP BY kind, skill", ids).fetchall()
    note(who, 'mistake cards: ' + json.dumps([tuple(r) for r in mk]))
    check(who, 'mistake cards have kind and skill', all(r[0] in ('fix', 'question', 'sound') and r[1] for r in mk), [tuple(r) for r in mk])
    ev = c.execute(f"SELECT COUNT(*) FROM next_skill_events WHERE user_id IN ({ph}) AND (score<0 OR score>1)", ids).fetchone()[0]
    check(who, 'skill scores within 0..1', ev == 0, ev)
    evs = c.execute(f"SELECT user_id, skill, COUNT(*) FROM next_skill_events WHERE user_id IN ({ph}) GROUP BY user_id, skill", ids).fetchall()
    note(who, 'skill events: ' + json.dumps([tuple(r) for r in evs]))
    rem = c.execute(f"SELECT COUNT(*) FROM next_reminders WHERE user_id IN ({ph}) AND enabled=1", ids).fetchone()[0]
    check(who, 'reminders switched off again', rem == 0, rem)
    sent = c.execute(f"SELECT COUNT(*) FROM next_reminders WHERE user_id IN ({ph}) AND last_sent IS NOT NULL", ids).fetchone()[0]
    check(who, 'no reminder was sent', sent == 0, sent)
    imp = c.execute(f"SELECT id, owner, origin FROM lab_packs WHERE owner IN ({ph})", ids).fetchall()
    check(who, 'imported packs are private and marked import', all(r['origin'] == 'import' for r in imp), [tuple(r) for r in imp])
    c.close()


def cleanup(record=True):
    c = db()
    ids = list(IDS.values())
    ph = ','.join('?' * len(ids))
    removed = {}
    cols = user_columns(c)
    for tb, col in cols:
        n = c.execute(f'DELETE FROM "{tb}" WHERE "{col}" IN ({ph})', ids).rowcount
        if n:
            removed[f'{tb}.{col}'] = n
    n = c.execute(f'DELETE FROM users WHERE id IN ({ph})', ids).rowcount
    removed['users.id'] = n
    c.commit()
    left = {f'{tb}.{col}': c.execute(f'SELECT COUNT(*) FROM "{tb}" WHERE "{col}" IN ({ph})', ids).fetchone()[0] for tb, col in cols}
    left['users.id'] = c.execute(f'SELECT COUNT(*) FROM users WHERE id IN ({ph})', ids).fetchone()[0]
    left['users.name'] = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE 'qa-e2e-%'").fetchone()[0]
    c.close()
    left = {k: v for k, v in left.items() if v}
    if record:
        check('cleanup', 'no row of the test accounts is left', not left, left)
    return removed, len(cols)


def main():
    lim = limits()
    u0 = usage()
    print('limits', lim, 'usage', u0, flush=True)
    if lim['site'] and lim['site'] - u0['site_today'] < 80:
        raise SystemExit('not enough site AI quota left today for a full run')
    clients = setup()
    note('setup', 'test accounts ' + ', '.join(f'qa-e2e-{k}={v}' for k, v in IDS.items()))
    errors = {}
    try:
        with cf.ThreadPoolExecutor(4) as ex:
            futs = {ex.submit(persona_a2, clients['a2']): 'a2', ex.submit(persona_b1, clients['b1']): 'b1',
                    ex.submit(persona_exam, clients['exam']): 'exam',
                    ex.submit(persona_guard, clients['guard'], [clients['a2'], clients['b1'], clients['exam']]): 'guard'}
            for f in cf.as_completed(futs):
                try:
                    f.result()
                except Exception:
                    errors[futs[f]] = traceback.format_exc()[-2500:]
                    check(futs[f], 'persona finished without crashing', False, errors[futs[f]][-500:])
        invariants()
    finally:
        u1 = usage()
        removed, ncols = cleanup()
    by_path = {}
    for r in CALLS:
        by_path.setdefault(r['method'] + ' ' + r['path'], []).append(r['ms'])
    lat = {k: {'n': len(v), 'p50': int(statistics.median(v)), 'max': max(v)} for k, v in sorted(by_path.items())}
    report = {'started': datetime.datetime.fromtimestamp(T0).isoformat(timespec='seconds'), 'seconds': round(time.time() - T0, 1),
              'light': LIGHT, 'ai_slots': AI_SLOT_COUNT,
              'limits': lim, 'usage_before': u0, 'usage_after': u1,
              'ai_calls_used': sum(u1['test_accounts'].values()),
              'checks': {'total': len(CHECKS), 'failed': sum(not x['ok'] for x in CHECKS)},
              'failed': [x for x in CHECKS if not x['ok']], 'crashes': errors,
              'server_errors': [r for r in CALLS if r['status'] >= 500 or r['status'] == 0],
              'latency_ms': lat, 'removed': removed, 'user_columns_scanned': ncols,
              'notes': NOTES, 'all_checks': CHECKS, 'calls': CALLS}
    (HERE / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print('RESULT', json.dumps({k: report[k] for k in ('seconds', 'ai_calls_used', 'checks')}), flush=True)


if __name__ == '__main__':
    main()
