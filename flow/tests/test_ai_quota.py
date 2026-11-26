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

    def test_one_level_for_the_page_and_a_cheap_header(self):  # B6: the page reads level, both sides one threshold
        q.set(self.c, 1, 'admin@flow', '多练', limit=10); self.c.commit()
        self.assertEqual((q.today(self.c, 1)['level'], q.header(self.c, 1)), ('ok', '10/10/ok'))
        self.use(1, 8)
        self.assertEqual(q.header(self.c, 1), '2/10/ok')  # a fifth left exactly: not yet low
        self.use(1, 1)
        self.assertEqual((q.today(self.c, 1)['level'], q.header(self.c, 1)), ('low', '1/10/low'))  # under a fifth
        self.use(1, 1)
        self.assertEqual((q.today(self.c, 1)['level'], q.header(self.c, 1)), ('out', '0/10/out'))
        q.set(self.c, 2, 'admin@flow', '暂停', paused=True); self.c.commit()
        self.assertEqual(q.brief(self.c, 2)['level'], 'out')
        self.assertEqual(q.header(self.c, 3), '//ok')  # an admin: no ceiling

    def test_days_in_a_row_near_the_ceiling(self):
        now = time.time()
        for back, n in ((0, 4), (1, 5), (2, 4), (3, 1), (4, 5)):  # today 4 of 5, then 5, 4, a quiet day, 5
            self.c.execute('INSERT INTO ai_usage VALUES(1,?,?)', (time.strftime('%Y-%m-%d', time.gmtime(now - back * 86400)), n))
        self.c.execute('INSERT INTO ai_usage VALUES(2,?,1)', (time.strftime('%Y-%m-%d', time.gmtime(now)),))
        self.c.commit()
        with patch.object(q, '_unit_costs', lambda c: ({}, 0.0)):
            rows = {r['user_id']: r for r in q.report(self.c, now=now)}
        self.assertEqual((rows[1]['near_streak'], rows[1]['near_days_30'], rows[1]['full_days_30']), (3, 2, 2))
        self.assertEqual(rows[2]['near_streak'], 0)  # today short of it: no streak
        q.set(self.c, 1, 'admin@flow', '一周', limit=8, until=now + 86400); self.c.commit()
        with patch.object(q, '_unit_costs', lambda c: ({}, 0.0)):
            one = q.report(self.c, uid=1, now=now)[0]
        self.assertEqual(one['override_until'], now + 86400)

    def test_the_export_keeps_the_reason_but_not_who_set_it(self):  # B6: who is a staff member's mail
        q.set(self.c, 1, 'staff@school.example', '期末前多练', limit=8); self.c.commit()
        self.use(1, 1)
        out = __import__('account_data').records(self.c, {'id': 1}).decode('utf-8')
        self.assertNotIn('staff@school.example', out)
        self.assertIn('期末前多练', out)
        data = json.loads(out)['tables']
        self.assertIn('ai_quota', data); self.assertIn('ai_usage_kind', data)
        self.assertNotIn('changed_by', data['ai_quota'][0])

    def test_a_persons_counts_go_after_90_days_and_the_days_total_stays(self):  # D2: 「保存多久」
        now = time.time()
        old, kept = (time.strftime('%Y-%m-%d', time.gmtime(now - d * 86400)) for d in (95, 30))
        self.c.executemany('INSERT INTO ai_usage VALUES(?,?,?)', [(1, old, 4), (2, old, 3), (0, old, 2), (1, kept, 5)])
        self.c.executemany('INSERT INTO ai_usage_kind VALUES(?,?,?,?)', [(1, old, 'chat', 4), (2, old, 'chat', 1), (2, old, 'next-essay', 2), (1, kept, 'chat', 5)])
        q.set(self.c, 1, 'admin@flow', '一直留', limit=8); self.c.commit()
        self.assertEqual(q.prune(self.c, now), 2)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT user_id, count FROM ai_usage WHERE day=? ORDER BY user_id', (old,)).fetchall()], [(-1, 7), (0, 2)])
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT kind, count FROM ai_usage_kind WHERE day=? ORDER BY kind', (old,)).fetchall()], [('chat', 5), ('next-essay', 2)])
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT user_id FROM ai_usage_kind WHERE day=? GROUP BY user_id', (old,)).fetchall()], [(-1,)])
        self.assertEqual(q.used(self.c, 1, kept), 5)  # 30 days back: kept
        self.assertIsNotNone(q.get(self.c, 1)); self.assertTrue(q.history(self.c, 1))  # the quota and its log stay
        self.assertEqual(q.prune(self.c, now), 0)  # once is enough
        self.assertNotIn(-1, [r['user_id'] for r in q.report(self.c, now=now)])
        self.assertIn('「我的 → 帮助 → 问题反馈」', q.PAUSED)  # #464: 问题反馈 sits under 我的 → 帮助

    def test_an_ai_result_goes_after_180_days_with_its_dispute(self):  # the owner 2026-11-27, via D2
        now = time.time()
        rows = [(1, 'old-job-00001', 'next-rewrite', now - 181 * 86400), (1, 'new-job-00001', 'next-rewrite', now - 179 * 86400),
                (2, 'old-job-00002', 'next-shadow', now - 200 * 86400)]
        for uid, rid, kind, at in rows:
            self.c.execute("INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,fingerprint,status,result,created,updated) "
                           "VALUES(?,?,?,'p','writing','f','complete','{\"summary\": \"x\"}',?,?)", (uid, rid, kind, at, at))
        ids = {r['request_id']: r['id'] for r in self.c.execute('SELECT id, request_id FROM lab_jobs')}
        self.c.executemany('INSERT INTO feedback_disputes VALUES(?,?,?,?)', [(1, ids['old-job-00001'], '我觉得没错', now - 180 * 86400),
                                                                           (1, ids['new-job-00001'], '这里不对', now)])
        self.c.commit()
        self.assertEqual(self.c.execute('PRAGMA foreign_keys').fetchone()[0], 1)  # as the site runs: the dispute must go first
        self.assertEqual(q.prune(self.c, now), 3)  # two results, one dispute
        self.assertEqual([r[0] for r in self.c.execute('SELECT request_id FROM lab_jobs')], ['new-job-00001'])
        self.assertEqual([r[0] for r in self.c.execute('SELECT correction FROM feedback_disputes')], ['这里不对'])
        self.assertEqual(q.prune(self.c, now), 0)

    def test_read_aloud_characters_go_after_90_days_with_the_account_and_into_the_export(self):  # B6, D2
        import account_data
        now = time.time()
        old, kept = (time.strftime('%Y-%m-%d', time.gmtime(now - d * 86400)) for d in (95, 30))
        self.c.executemany('INSERT INTO tts_usage(day, who, chars, files) VALUES(?,?,?,?)',
                           [(old, 1, 300, 2), (old, 0, 500, 3), (old, -1, 900, 9), (kept, 1, 120, 1), (kept, 0, 120, 1), (kept, 2, 40, 1)])
        self.c.execute('INSERT INTO tts_import(day, who, chars) VALUES(?,?,?)', (old, 1, 200)); self.c.commit()
        q.prune(self.c, now)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT who, chars FROM tts_usage WHERE day=? ORDER BY who', (old,))], [(-1, 900), (0, 500)])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM tts_import').fetchone()[0], 0)
        out = json.loads(account_data.records(self.c, {'id': 1}).decode('utf-8'))
        self.assertEqual([r['chars'] for r in out['tables']['tts_usage']], [120])  # the learner's own row, 30 days back
        self.assertIn('tts_usage', out['目录'])
        account_data.forget(self.c, 2)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM tts_usage WHERE who=2').fetchone()[0], 0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM tts_usage WHERE who=0').fetchone()[0], 2)  # the site's rows stay

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


class NameTests(unittest.TestCase):
    """「我的 → 设置 → AI 用量」 (the owner, 2026-11-26 22:1x: 「汉化不完全」): every task a learner's AI use is counted under
    has a name a learner reads, Chinese on a Chinese page and English on an English one; an unknown kind is 「其他」."""

    def kinds_in_code(self):
        import re
        flow = Path(__file__).resolve().parents[1]
        pat = re.compile(r"(?:run_job\(\s*c\s*,\s*uid\s*,[^,]+,|_ai\(\s*c\s*,\s*uid\s*,\s*data\s*,|reserve\(\s*c\s*,\s*uid\s*,)\s*'([a-z0-9-]+)'")
        found = set()
        for f in flow.glob('*.py'):
            found |= {k for k in pat.findall(f.read_text(encoding='utf-8')) if not k.endswith('-')}  # 'next-assess-' + kind: below
        import two_lines, ai_routes
        found |= {two_lines.ASK, two_lines.CHECK, 'next-assess-speaking', 'next-assess-writing', 'audio', 'feedback'}
        found |= {k for k, _, _ in ai_routes.TASKS}
        return found

    def test_every_counted_task_has_a_learners_name(self):
        import ui_lang
        kinds = self.kinds_in_code()
        self.assertGreater(len(kinds), 20)
        self.assertEqual(sorted(kinds - set(q.NAMES)), [], 'give these a name in ai_quota.NAMES')
        for k, (zh, en) in q.NAMES.items():
            self.assertTrue(ui_lang.HAN.search(zh), k); self.assertFalse(ui_lang.HAN.search(en), k)
            self.assertNotIn('-', zh, k)  # no keys, no model names
        self.addCleanup(ui_lang.use, None)
        ui_lang.use(None)
        self.assertEqual((q._label('next-shadow'), q._label('next-two-check'), q._label('a-new-kind'), q._label('other')),
                         ('跟读', '听两句、答一句：批改', '其他', '其他'))
        ui_lang.use('en')
        self.assertEqual((q._label('next-shadow'), q._label('a-new-kind')), ('Shadowing', 'Other'))


if __name__ == '__main__':
    unittest.main()
