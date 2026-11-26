"""每次用 AI 的结果 (lab_jobs.result: the marking, and in 口语练习 what the AI heard; the 隐私说明 since 2026-11-27):
the learner's own, so 导出我的数据 carries every row and 注销账号 deletes them with the corrections hung on them
(feedback_disputes); the console sees them as numbers only: no page or CSV of xmc.hk/flow shows any word of a result
(console_data.ai_quality reads a score or a verdict out of it, never the text, and no average from fewer than 5), and
a teacher's class page shows none either (B9)."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import account_data, app, flow_admin  # noqa: E402

BOSS = 'boss@example.com'
MARK = 'ZQX-HEARD-7731'  # what a learner said, as the AI wrote it down: must never reach the console


class LabJobsPrivacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                  patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': BOSS, 'FLOW_DATA_DIR': self.tmp.name})):
            p.start(); self.addCleanup(p.stop)
        app.init()
        now = time.time()
        results = {'next-retell': {'points': [{'covered': True}, {'covered': False}], 'transcript': MARK + ' retell'},
                   'next-dialog': {'score': 0.7, 'heard': MARK + ' dialog', 'summary': MARK},
                   'next-ielts': {'band': 6, 'transcript': MARK + ' ielts'},
                   'next-essay': {'scores': {'task': 5, 'grammar': 4}, 'comment': MARK + ' essay'},
                   'next-rewrite': {'verdict': 'minor', 'changes': [{'from': MARK, 'to': 'x'}]},
                   'next-translate': {'score': 0.8, 'comment': MARK},
                   'feedback': {'summary': MARK + ' feedback'}, 'audio': {'transcript': MARK + ' audio'}}
        with app.db() as c:
            self.uid = c.execute("INSERT INTO users(username,password,email,admin,created) VALUES('lj-learner','x','lj@example.com',0,?)",
                                 (now,)).lastrowid
            for i, (kind, r) in enumerate(results.items()):
                job = c.execute('INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,fingerprint,status,result,error,created,updated) '
                                "VALUES(?,?,?,'p1','speaking','fp','complete',?,'',?,?)",
                                (self.uid, f'rid-{i}', kind, json.dumps(r, ensure_ascii=False), now - 3600, now - 3500)).lastrowid
            c.execute('INSERT INTO feedback_disputes(user_id,job,correction,created) VALUES(?,?,?,?)', (self.uid, job, MARK + ' dispute', now))
            for i in range(4):  # 复述 five times in all: enough for its average (QUALITY_MIN)
                c.execute('INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,fingerprint,status,result,error,created,updated) '
                          "VALUES(?,?,'next-retell','p1','speaking','fp','complete',?,'',?,?)",
                          (self.uid, f'retell-{i}', json.dumps(results['next-retell']), now - 3600, now - 3500))
            # a 老师账号 with a class of five, this learner in it
            self.teacher = c.execute("INSERT INTO users(username,password,email,admin,role,created) VALUES('lj-teacher','x','t@example.com',0,'teacher',?)",
                                     (now,)).lastrowid
            __import__('class_service').schema(c)
            self.cid = c.execute("INSERT INTO classes(name,code,teacher,created) VALUES('三班','LJCLS1',?,?)", (self.teacher, now)).lastrowid
            members = [self.uid] + [c.execute("INSERT INTO users(username,password,created) VALUES(?,'x',?)", (f'lj-m{i}', now)).lastrowid for i in range(4)]
            for m in members:
                c.execute('INSERT INTO class_members(user_id,class_id,joined_at) VALUES(?,?,?)', (m, self.cid, now - 86400))
            c.commit()

    def test_the_console_never_shows_a_word_of_a_result(self):
        site = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        threading.Thread(target=site.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (site.shutdown(), site.server_close()))
        paths = sorted((flow_admin.VIEWER_GET | flow_admin.ADMIN_GET) - {'/feedback/image'}) + [f'/learner?id={self.uid}', '/ai?days=30']
        seen = 0
        for path in paths:
            req = urllib.request.Request(f'http://127.0.0.1:{site.server_address[1]}/flow/api{path}', headers={'Cf-Access-Authenticated-User-Email': BOSS})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    body, st = r.read().decode('utf-8', 'replace'), r.status
            except urllib.error.HTTPError as e:
                body, st = e.read().decode('utf-8', 'replace'), e.code
            self.assertNotIn(MARK, body, path)
            seen += st == 200
        self.assertGreater(seen, 20)  # the pages did answer (an empty run would prove nothing)
        with app.db() as c:  # the quality numbers still come from the results, from five or more only
            q = {x['kind']: x for x in __import__('console_data').ai_quality(c, 30)}
        self.assertIn('平均讲到 50% 的要点', q['next-retell']['notes'])
        self.assertEqual((q['next-essay']['done'], q['next-essay']['notes']), (1, []))  # one essay: counted, no average

    def test_the_teacher_sees_no_word_of_a_result(self):
        cs = __import__('class_service')
        with app.db() as c:
            mine, st = cs.mine(c, self.teacher)
            page, st2 = cs.teach(c, self.teacher, self.cid)
        self.assertEqual((st, st2), (200, 200))
        self.assertTrue(page.get('ready', True))  # five members: the page has its numbers
        self.assertNotIn(MARK, json.dumps([mine, page], ensure_ascii=False))

    def test_export_carries_them_and_deleting_the_account_removes_them(self):
        with app.db() as c:
            u = c.execute('SELECT * FROM users WHERE id=?', (self.uid,)).fetchone()
            out = json.loads(account_data.records(c, u))
            self.assertEqual(len(out['tables']['lab_jobs']), 12)  # 8 kinds + 4 more 复述
            self.assertIn(MARK, json.dumps(out['tables']['lab_jobs'], ensure_ascii=False))
            self.assertIn('lab_jobs', out['目录']); self.assertIn('feedback_disputes', out['tables'])
            account_data.forget(c, self.uid, Path(self.tmp.name)); c.commit()
            for t in ('lab_jobs', 'feedback_disputes'):
                self.assertEqual(c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0], 0, t)


if __name__ == '__main__':
    unittest.main()
