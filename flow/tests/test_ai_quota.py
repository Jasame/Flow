"""Each account's AI quota (ai_quota, 2026-11-26): an override (calls a day or a factor, a pause, an end date, a reason)
over the usual ceiling, in the one gate every AI call goes through (chat_service.reserve); the ¥10 stop and the site's
ceiling still come first; a pause stops AI only; what the learner reads is what the gate counts; the consoles see each
person's use. No AI is called."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_quota as q, ai_routes, chat_service as cs, lab_service as lab, next_service as nx  # noqa: E402

ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
       'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '5'}
PID = 'v5-science-b2-noise-cancelling'


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'q.db'), patch.dict(os.environ, ENV),
                  patch('console_ops.limit_override', lambda name: None), patch.object(ai_routes, 'day_full', lambda c=None, now=None: False)):
            p.start(); self.addCleanup(p.stop)
        app.init(); self.c = app.db(); self.addCleanup(self.c.close)
        for n, admin in (('learner', 0), ('other', 0), ('teacher', 1)):
            self.c.execute('INSERT INTO users(username,password,admin) VALUES(?,?,?)', (n, 'h', admin))
        self.c.commit()

    def use(self, uid, n, kind='next-rewrite'):
        out = []
        for _ in range(n):
            out.append(cs.reserve(self.c, uid, kind)); self.c.commit()
        return out

    # ---- the override ----
    def test_an_account_can_have_more_or_fewer_calls(self):
        self.assertEqual(cs.remaining(self.c, 1), 5)  # the usual ceiling
        q.set(self.c, 1, 'admin@flow', '期末前多练', limit=8); self.c.commit()
        self.assertEqual(self.use(1, 8), [None] * 8)
        self.assertIn('8 次', self.use(1, 1)[0])
        q.set(self.c, 2, 'admin@flow', '刷得太多', factor=0.4); self.c.commit()  # 5 × 0.4 = 2
        self.assertEqual(self.use(2, 3)[:2], [None, None]); self.assertIsNotNone(self.use(2, 1)[0])
        self.assertEqual(cs.remaining(self.c, 2), 0)

    def test_an_override_ends_on_its_date_and_the_usual_comes_back(self):
        now = time.time()
        q.set(self.c, 1, 'admin@flow', '一周', limit=50, until=now + 7 * 86400); self.c.commit()
        self.assertEqual(q.limit_for(self.c, 1, now), (50, 'override'))
        self.assertEqual(q.limit_for(self.c, 1, now + 8 * 86400), (5, 'usual'))  # ended: the usual ceiling
        self.c.execute('UPDATE ai_quota SET until=? WHERE user_id=1', (now - 1,)); self.c.commit()
        self.assertEqual(cs.remaining(self.c, 1), 5); self.assertFalse(q.get(self.c, 1)['active'])
        q.clear(self.c, 1, 'admin@flow'); self.c.commit()
        self.assertIsNone(q.get(self.c, 1))
        self.assertEqual([h['change'].get('cleared', False) for h in q.history(self.c, 1)], [True, False])  # set, then cleared

    def test_a_pause_stops_ai_only(self):
        q.set(self.c, 1, 'admin@flow', '违规使用', paused=True); self.c.commit()
        problem = self.use(1, 1)[0]
        self.assertEqual(problem, q.PAUSED)
        self.assertEqual(cs.refusal(problem, self.c, 1)['code'], 'ai_paused')
        self.assertEqual(q.used(self.c, 1), 0)  # nothing counted
        qn = json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (PID,)).fetchone()[0])['questions'][0]
        self.assertIn('correct', nx.check(self.c, 1, {'pack': PID, 'index': 0, 'choice': qn['answer']})[0])  # learning without AI goes on
        with self.assertRaises(PermissionError) as e:  # no AI voice either
            __import__('tts_service').ensure(self.c, 1, 'A sentence never read aloud before.', 'f1')
        self.assertEqual(e.exception.args[0], 'paused')
        self.assertIsNone(self.use(2, 1)[0])  # another account is not touched

    def test_the_hard_stop_and_the_site_ceiling_still_come_first(self):
        q.set(self.c, 1, 'admin@flow', '多给', limit=1000); self.c.commit()
        with patch.object(ai_routes, 'day_full', lambda c=None, now=None: True):
            self.assertEqual(self.use(1, 1)[0], cs.DAY_FULL)
        with patch.dict(os.environ, {'FLOW_AI_DAILY_LIMIT': '1'}):
            self.assertIsNone(self.use(2, 1)[0])
            self.assertEqual(self.use(1, 1)[0], q.SITE_FULL)  # 1000 of its own, but the site's 1 is used

    def test_admins_have_no_ceiling_but_can_be_paused(self):
        self.assertEqual(q.limit_for(self.c, 3), (None, 'admin'))
        self.assertEqual(self.use(3, 7), [None] * 7)
        q.set(self.c, 3, 'owner', '测试暂停', paused=True); self.c.commit()
        self.assertEqual(self.use(3, 1)[0], q.PAUSED)

    def test_what_a_console_may_set(self):
        for kw, word in (({'limit': 0}, '暂停'), ({'limit': 5000}, '1000'), ({'factor': 20}, '倍数'), ({'limit': 3, 'factor': 2}, '只能填一个'),
                         ({}, '至少要改一项'), ({'limit': 3, 'until': time.time() - 5}, '到期'), ({'limit': True}, '次数')):
            with self.assertRaises(ValueError) as e:
                q.set(self.c, 1, 'admin@flow', '原因', **kw)
            self.assertIn(word, str(e.exception), kw)
        with self.assertRaises(ValueError):
            q.set(self.c, 1, 'admin@flow', '', limit=3)  # a reason is needed
        with self.assertRaises(ValueError):
            q.set(self.c, 99, 'admin@flow', '原因', limit=3)  # no such account

    # ---- what is read ----
    def test_the_learner_reads_what_the_gate_counts_by_task(self):
        self.use(1, 2, 'next-rewrite'); self.use(1, 1, 'chat')
        t = q.today(self.c, 1)
        self.assertEqual((t['used'], t['limit'], t['remaining'], t['stopped']), (3, 5, 2, None))
        self.assertEqual([(k['kind'], k['count']) for k in t['by_kind']], [('next-rewrite', 2), ('chat', 1)])
        self.assertEqual(sum(k['count'] for k in t['by_kind']), t['used'])
        self.assertIn('还能用 2 次', t['note']); self.assertEqual(t['reset_at'] % 86400, 0)
        self.use(1, 2)
        t = q.today(self.c, 1)
        self.assertEqual((t['remaining'], t['stopped']), (0, 'user')); self.assertIn('用完了', t['note'])
        q.set(self.c, 1, 'admin@flow', '内部原因，不给学员看', paused=True, limit=9); self.c.commit()
        t = q.today(self.c, 1)
        self.assertEqual((t['stopped'], t['limit'], t['adjusted']), ('paused', 9, True)); self.assertNotIn('内部原因', json.dumps(t, ensure_ascii=False))

    def test_calls_from_before_tasks_were_counted_show_as_other(self):
        day = time.strftime('%Y-%m-%d', time.gmtime())
        self.c.execute('INSERT INTO ai_usage VALUES(1,?,4)', (day,)); self.c.commit()
        self.use(1, 1, 'next-essay')
        self.assertEqual([(k['kind'], k['count']) for k in q.today(self.c, 1)['by_kind']], [('next-essay', 1), ('other', 4)])

    def test_a_call_with_no_answer_is_given_back_in_both_counts(self):
        def invoke():
            raise OSError('gateway down')
        r, s = lab.run_job(self.c, 1, 'quota-test-000001', 'next-rewrite', PID, 'writing', {'x': 1}, invoke, lambda raw: raw)
        self.assertNotEqual(s, 200)
        self.assertEqual(q.used(self.c, 1), 0)
        self.assertEqual(q.today(self.c, 1)['by_kind'], [])

    def test_the_consoles_see_each_persons_use(self):
        self.use(1, 4); self.use(2, 1, 'chat')
        q.set(self.c, 3, 'owner', '观察', limit=2); self.c.commit()  # an account with an override is listed even unused
        with patch.object(q, '_unit_costs', lambda c: ({'next-rewrite': 0.004, 'chat': 0.002}, 0.003)):
            rows = q.report(self.c)
            one = q.report(self.c, uid=1)[0]
        self.assertEqual([r['user_id'] for r in rows], [1, 2, 3])
        self.assertEqual((one['today'], one['d7'], one['d30'], one['limit'], one['near_days_30']), (4, 4, 4, 5, 1))  # 4 of 5: near
        self.assertAlmostEqual(one['cost_est_30'], 0.016)
        self.assertEqual(set(one['by_kind']), {'today', 'd7', 'd30'})
        self.assertEqual(rows[2]['override']['daily'], 2)


if __name__ == '__main__':
    unittest.main()
