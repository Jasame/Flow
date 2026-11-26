"""单词搭配反馈 in the console (2026-11-26; B7's word_extras, B2's 「这条不对」): a 管理员 sees the AI 常用搭配和近义、易混词
learners marked, most learners first, with their notes and no names; takes one down for everyone with a reason, or puts
back one taken down here (never one the AI review hid); each in the operator log. 只看数据 sees none of it."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, flow_admin  # noqa: E402

BOSS, PEEK = 'boss@example.com', 'peek@example.com'


class ConsoleWordExtras(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                  patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': BOSS, 'FLOW_DATA_DIR': self.tmp.name})):
            p.start(); self.addCleanup(p.stop)
        app.init()
        now = time.time()
        with app.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS vocab_extras_flags(user_id INTEGER NOT NULL REFERENCES users(id), extra_id INTEGER NOT NULL, '
                      "created REAL NOT NULL, note TEXT NOT NULL DEFAULT '', PRIMARY KEY(user_id, extra_id))")  # B2's (#429)
            ins = "INSERT INTO vocab_extras(norm, kind, en, zh, diff, created, hidden, flagged) VALUES(?,?,?,?,?,?,?,?)"
            self.bad = c.execute(ins, ('decision', 'colloc', 'do a decision', '做决定', '', now, 0, '')).lastrowid
            self.ok = c.execute(ins, ('wonder', 'near', 'wander', '闲逛', '拼写相近', now, 0, '')).lastrowid
            self.review = c.execute(ins, ('choice', 'near', 'chose', '选择（过去式）', '', now, 1, json.dumps({'model': 'qwen-plus'}))).lastrowid
            users = [c.execute('INSERT INTO users(username,password) VALUES(?,?)', (f'u{i}', 'x')).lastrowid for i in range(3)]
            for u, x, note in ((users[0], self.bad, '应该是 make a decision'), (users[1], self.bad, ''), (users[2], self.ok, ''),
                               (users[2], self.review, '')):
                c.execute('INSERT INTO vocab_extras_flags(user_id, extra_id, created, note) VALUES(?,?,?,?)', (u, x, now, note))
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

    def test_the_marked_rows_most_learners_first_without_names(self):
        st, d = self.call('/word-extras')
        self.assertEqual(st, 200, d)
        first = d['items'][0]
        self.assertEqual((first['extra_id'], first['users'], first['notes'], first['kind_label']), (self.bad, 2, ['应该是 make a decision'], '常用搭配'))
        self.assertNotIn('username', json.dumps(d, ensure_ascii=False))
        self.assertNotIn('user_id', json.dumps(d))
        self.assertEqual(self.call('/word-extras', who=PEEK)[0], 403)  # 只看数据: no learners' notes

    def test_take_down_with_a_reason_then_put_back(self):
        self.assertEqual(self.call('/word-extras/take-down', {'id': self.bad, 'why': ' '})[1].get('field'), 'why')
        st, body = self.call('/word-extras/take-down', {'id': self.bad, 'why': '搭配错了，应为 make a decision'})
        self.assertEqual((st, body['changed']), (200, True))
        row = next(x for x in self.call('/word-extras')[1]['items'] if x['extra_id'] == self.bad)
        self.assertEqual((row['hidden'], row['by_admin']), (True, True))
        log = self.call('/log')[1]['items'][0]
        self.assertEqual((log['action'], log['detail']), ('extra-down', '搭配错了，应为 make a decision'))
        self.assertIn('decision', log['target']); self.assertIn(f'#{self.bad}', log['target'])
        self.assertEqual(self.call('/word-extras/put-back', {'id': self.bad})[0], 200)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT hidden FROM vocab_extras WHERE id=?', (self.bad,)).fetchone()[0], 0)
        self.assertEqual(self.call('/log')[1]['items'][0]['action'], 'extra-up')

    def test_what_the_review_hid_stays_hidden_and_others_cannot(self):
        st, body = self.call('/word-extras/put-back', {'id': self.review})
        self.assertEqual(st, 409); self.assertIn('审稿', body['error'])
        self.assertEqual(self.call('/word-extras/take-down', {'id': 99999, 'why': 'x'})[0], 404)
        self.assertEqual(self.call('/word-extras/take-down', {'id': self.ok, 'why': 'x'}, who=PEEK)[0], 403)
        js = (Path(app.ROOT).parent / 'xmc-admin' / 'admin.js').read_text(encoding='utf-8')
        self.assertIn("'/word-extras/take-down': '下架这一条单词搭配'", js)  # 正式版 asks first


if __name__ == '__main__':
    unittest.main()
