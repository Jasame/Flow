"""「我的 → 设置 → AI 用量」 (2026-11-26, the owner in A0: a learner sees their own AI use of the day): /api/account/ai
is ai_quota.today for the signed-in account; every AI route's answer carries X-Flow-AI-Quota
("<remaining>/<limit>/<level>", ai_quota.header) for the page's once-a-day line, and no other route does; a paused
account reads 「暂停中」 and its AI answers say 'out'. No AI is called."""
import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_quota as q, ai_routes, chat_service as cs, next_service as nx  # noqa: E402

PW = 'a long password here'
ENV = {'FLOW_COOKIE_SECURE': '0', 'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '10'}


class AiUsagePage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.dict(os.environ, ENV),
                  patch('console_ops.limit_override', lambda name: None), patch.object(ai_routes, 'day_full', lambda c=None, now=None: False)):
            p.start(); self.addCleanup(p.stop)
        app.SECURE = False
        app.RATE.clear()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,storage_ok,terms_ok,terms_version) VALUES(?,?,1,1,?)',
                      ('lin', app.password(PW), __import__('privacy_service').CONSENT_VERSION))
            self.uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]
            c.commit()
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.site.shutdown(), self.site.server_close()))
        self.addCleanup(self.tmp.cleanup)

    def call(self, path, data=None, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}'), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}'), dict(e.headers)

    def sign_in(self):
        st, body, h = self.call('/api/login', {'username': 'lin', 'password': PW})
        self.assertEqual(st, 200, body)
        cookie = h['Set-Cookie'].split(';')[0]
        return {'Cookie': cookie, 'X-CSRF-Token': self.call('/api/session', headers={'Cookie': cookie})[1]['user']['csrf']}

    def use(self, n, kind='next-essay'):
        with app.db() as c:
            for _ in range(n):
                self.assertIsNone(cs.reserve(c, self.uid, kind)); c.commit()

    def test_the_learner_reads_the_day_by_task(self):
        self.assertEqual(self.call('/api/account/ai')[0], 401)
        h = self.sign_in()
        self.use(6); self.use(3, 'chat')
        st, a, _ = self.call('/api/account/ai', headers=h)
        self.assertEqual(st, 200, a)
        self.assertEqual((a['used'], a['limit'], a['remaining'], a['level'], a['stopped'], a['adjusted']), (9, 10, 1, 'low', None, False))
        self.assertEqual([(k['label'], k['count']) for k in a['by_kind']], [('写作批改', 6), ('导师问答', 3)])
        self.assertIn('今天还能用 1 次', a['note'])

    def test_an_ai_answer_says_what_is_left_and_no_other_does(self):
        h = self.sign_in()
        self.use(2)
        with patch.object(nx, 'post', lambda c, uid, path, data: ({'ok': True}, 200)):
            st, _, hd = self.call('/api/next/rewrite', {'pack': 'x', 'text': 'y'}, h)
            self.assertEqual((st, hd.get('X-Flow-AI-Quota')), (200, '8/10/ok'))
            st, _, hd = self.call('/api/next/check', {'pack': 'x'}, h)  # learning without AI: no header
            self.assertNotIn('X-Flow-AI-Quota', hd)
        self.assertNotIn('X-Flow-AI-Quota', self.call('/api/account/ai', headers=h)[2])

    def test_a_paused_account_reads_paused_and_its_ai_answers_say_out(self):
        h = self.sign_in()
        with app.db() as c:
            q.set(c, self.uid, 'admin@example.com', '测试暂停', paused=True); c.commit()
        a = self.call('/api/account/ai', headers=h)[1]
        self.assertEqual((a['stopped'], a['paused'], a['level'], a['note'], a['adjusted']), ('paused', True, 'out', q.PAUSED, False))  # a pause alone leaves the ceiling: not 「调整过」
        with patch.object(nx, 'post', lambda c, uid, path, data: ({'error': q.PAUSED, 'code': 'ai_paused'}, 429)):
            st, body, hd = self.call('/api/next/rewrite', {'pack': 'x', 'text': 'y'}, h)
        self.assertEqual((st, body['code'], hd.get('X-Flow-AI-Quota')), (429, 'ai_paused', '10/10/out'))

    def test_the_page_has_the_row_and_reads_the_header(self):
        src = Path(app.ROOT) / 'public' / 'src' / 'next'
        me, head = (src / '81-me.js').read_text(encoding='utf-8'), (src / '00-head.js').read_text(encoding='utf-8')
        self.assertIn("grow('meAi', 'AI 用量'", me)
        self.assertIn("'/api/account/ai'", me)
        self.assertIn("r.headers.get('X-Flow-AI-Quota')", head)
        self.assertIn('ai_paused', (src / '01-audio-offline.js').read_text(encoding='utf-8'))  # AI voice paused: its own words


if __name__ == '__main__':
    unittest.main()
