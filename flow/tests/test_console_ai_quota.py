"""AI 额度 in the consoles (2026-11-26, the owner in A0: both consoles change an account's quota and see each person's
use; read-only accounts see the totals only): a 管理员 sets an account's calls a day, a factor or a pause, for a time or
until changed, always with a reason, and puts it back; each change is in the operator log and in the learner drawer;
「AI 额度」 lists one row a person; 只看数据 sees none of it. No AI is called."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_quota as q, ai_routes, chat_service as cs, flow_admin  # noqa: E402

BOSS, PEEK = 'boss@example.com', 'peek@example.com'


class ConsoleAiQuota(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                  patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': BOSS, 'FLOW_DATA_DIR': self.tmp.name, 'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '10'}),
                  patch('console_ops.limit_override', lambda name: None), patch.object(ai_routes, 'day_full', lambda c=None, now=None: False)):
            p.start(); self.addCleanup(p.stop)
        app.init()
        with app.db() as c:
            self.lin = c.execute("INSERT INTO users(username,password) VALUES('lin','x')").lastrowid
            self.ma = c.execute("INSERT INTO users(username,password) VALUES('ma','x')").lastrowid
            for _ in range(8):
                cs.reserve(c, self.lin, 'next-essay')
            cs.reserve(c, self.ma, 'chat')
            c.commit()
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        threading.Thread(target=self.admin.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.admin.shutdown(), self.admin.server_close()))

    def call(self, path, data=None, who=BOSS):
        h = {'Content-Type': 'application/json', 'Cf-Access-Authenticated-User-Email': who}
        if data is not None:
            h['X-Requested-With'] = 'xmc'
        req = urllib.request.Request(f'http://127.0.0.1:{self.admin.server_address[1]}/flow/api{path}',
                                     data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_an_account_gets_its_own_calls_a_day_then_the_usual_again(self):
        st, body = self.call('/learner/ai-quota', {'id': self.lin, 'mode': 'daily', 'value': 30, 'days': 7, 'reason': '期末前多练'})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['quota']['limit'], body['quota']['source'], body['quota']['today']), (30, 'override', 8))
        with app.db() as c:
            o = q.get(c, self.lin)
            self.assertEqual((o['daily'], o['reason'], o['by']), (30, '期末前多练', BOSS))
            self.assertAlmostEqual(o['until'], time.time() + 7 * 86400, delta=60)
        drawer = self.call(f'/learner?id={self.lin}')[1]['ai']['quota']
        self.assertEqual((drawer['override']['daily'], drawer['history'][0]['change']['reason'], drawer['usual']), (30, '期末前多练', 10))
        self.assertEqual([k['label'] for k in drawer['by_kind']['d30']], ['作文批改'])
        log = self.call('/log')[1]['items'][0]
        self.assertEqual((log['action'], log['target']), ('ai-quota', f'lin #{self.lin}'))
        self.assertIn('每天 30 次', log['detail']); self.assertIn('期末前多练', log['detail'])
        st, body = self.call('/learner/ai-quota/clear', {'id': self.lin})
        self.assertEqual((st, body['quota']['source'], body['quota']['override']), (200, 'usual', None))
        self.assertEqual(self.call('/log')[1]['items'][0]['action'], 'ai-quota-clear')
        self.assertIn('调整 AI 额度', [r['action_label'] for r in self.call(f'/learner?id={self.lin}')[1]['log']])

    def test_a_pause_and_a_factor_and_what_is_refused(self):
        self.assertEqual(self.call('/learner/ai-quota', {'id': self.ma, 'mode': 'pause', 'days': 0, 'reason': '一天内调用 300 次，疑似脚本'})[0], 200)
        with app.db() as c:
            self.assertTrue(q.paused(c, self.ma)); self.assertIsNone(q.get(c, self.ma)['until'])
        self.assertEqual(self.call('/learner/ai-quota', {'id': self.ma, 'mode': 'factor', 'value': 0.5, 'days': 30, 'reason': '用得太多'})[1]['quota']['limit'], 5)
        bad = [({'mode': 'daily', 'value': 30, 'days': 7, 'reason': ''}, 'reason'),
               ({'mode': 'daily', 'value': 'abc', 'days': 7, 'reason': 'x'}, 'value'),
               ({'mode': 'daily', 'value': 5000, 'days': 7, 'reason': 'x'}, 'value'),
               ({'mode': 'daily', 'value': 30, 'days': 5, 'reason': 'x'}, 'days'),
               ({'mode': 'other', 'value': 30, 'days': 7, 'reason': 'x'}, 'mode')]
        for data, field in bad:
            st, body = self.call('/learner/ai-quota', {'id': self.ma, **data})
            self.assertEqual((st, body.get('field')), (400, field), data)
        self.assertEqual(self.call('/learner/ai-quota', {'id': 99999, 'mode': 'pause', 'reason': 'x'})[0], 404)

    def test_one_row_a_person_for_administrators_only(self):
        self.call('/learner/ai-quota', {'id': self.ma, 'mode': 'pause', 'days': 7, 'reason': '测试'})
        d = self.call('/ai-people')[1]
        rows = {r['username']: r for r in d['items']}
        self.assertEqual([r['username'] for r in d['items']][:2], ['lin', 'ma'])  # most used first
        self.assertEqual((rows['lin']['d30'], rows['lin']['limit'], rows['ma']['paused']), (8, 10, True))
        self.assertEqual(d['usual'], 10)
        self.assertEqual(self.call('/ai-people', who=PEEK)[0], 403)  # 只看数据: the totals on the AI page only
        self.assertEqual(self.call(f'/learner?id={self.lin}', who=PEEK)[0], 403)
        self.assertEqual(self.call('/learner/ai-quota', {'id': self.lin, 'mode': 'pause', 'reason': 'x'}, who=PEEK)[0], 403)
        self.assertNotIn('top', self.call('/ai', who=PEEK)[1])

    def test_the_page_asks_on_the_prod_console_and_says_facts_only(self):
        js = (Path(app.ROOT).parent / 'xmc-admin' / 'admin.js').read_text(encoding='utf-8')
        self.assertIn("'/learner/ai-quota': '改这个学员的 AI 额度'", js)
        self.assertIn("'/learner/ai-quota/clear'", js)
        self.assertIn('只写事实，不写对人的评价', js)
        self.assertIn('href="#aiquota"', (Path(app.ROOT).parent / 'xmc-admin' / 'index.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
