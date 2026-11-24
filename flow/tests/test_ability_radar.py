"""r17: the ability radar — goals, assessments, practice evidence, history, and the plan weighted by the gap."""
import unittest, tempfile, sys, json, time, os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, ability_radar as AR, grammar_bank as GB, vocab_service as vs

DAY = 86400


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'radar.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
                                           'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_AI_AUDIO': '1'}); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'abroad', 'themes': [], 'minutes': 20})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def test_scale_and_ladder(self):
        self.assertEqual([AR.level_of(x) for x in (5, 20, 39.9, 40, 79, 80, 100)], ['A1', 'A2', 'A2', 'B1', 'B2', 'C1', 'C1'])
        self.assertEqual(AR.goal_index('B1'), 55)
        self.assertEqual(AR.ladder_index({'A2': 1, 'B1': 1, 'B2': 0}), 58)  # cannot manage B2 yet: stays in B1
        self.assertEqual(AR.ladder_index({'A2': 1, 'B1': 0.5, 'B2': 0.5}), 60)
        self.assertEqual(AR.ladder_index({'A2': 0}), 18)
        self.assertEqual(AR.vocab_index(3000), 50); self.assertEqual(AR.vocab_index(20000), 100); self.assertIsNone(AR.vocab_index(0))

    def test_no_evidence_means_no_number_and_goals_default_one_level_up(self):
        r = AR.radar(self.c, 1)
        self.assertTrue(all(d['score'] is None and d['confidence'] is None for d in r['dims']))
        self.assertEqual(set(r['goals'].values()), {'B2'}); self.assertFalse(r['goals_chosen'])
        self.assertIsNone(AR.due_today(self.c, 1))  # no test step until the learner has chosen goals
        r, code = AR.set_goals(self.c, 1, {'goals': {'speaking': 'B1'}})
        self.assertEqual((code, r['goals']['speaking'], r['goals']['reading'], r['goals_chosen']), (200, 'B1', 'B2', True))
        for bad in ({'goals': {'speaking': 'Z9'}}, {'goals': {'singing': 'B1'}}, {'goals': {}}, {}):
            self.assertEqual(AR.set_goals(self.c, 1, bad)[1], 400)
        self.assertEqual(set(AR.due_today(self.c, 1)), {'listening', 'reading', 'vocab', 'grammar', 'speaking', 'writing'})

    def test_a_reading_check_scores_against_the_goal_and_shows_the_change_next_time(self):
        AR.set_goals(self.c, 1, {'goals': {'reading': 'B1'}})
        t, _ = AR.comprehension_test(self.c, 1, 'reading', seed=3)
        self.assertEqual([p['level'] for p in t['passages']], ['A2', 'B1', 'B2'])
        self.assertTrue(all(len(p['questions']) == 2 and all(set(q) == {'i', 'prompt', 'options'} for q in p['questions']) for p in t['passages']))
        key = lambda p, q: json.loads(nx._pack_row(self.c, 1, p['pack'])['content'])['questions'][q['i']]['answer']
        answers = [{'pack': p['pack'], 'i': q['i'], 'choice': key(p, q) if p['level'] == 'A2' else (key(p, q) + 1) % 4} for p in t['passages'] for q in p['questions']]
        r, code = AR.comprehension_score(self.c, 1, {'kind': 'reading', 'answers': answers})
        self.assertEqual((code, r['index'], r['level']), (200, 38, 'A2'))
        self.assertEqual(r['recorded']['score'], round(38 / 55 * 100))
        reading = next(d for d in AR.radar(self.c, 1)['dims'] if d['id'] == 'reading')
        self.assertEqual((reading['source'], reading['confidence'], reading['due']), ('assessment', 'high', False))
        # A month later, a better check: the radar compares with the earlier snapshot.
        self.c.execute('UPDATE next_assess SET created=created-30*86400'); self.c.execute('UPDATE next_radar SET created=created-30*86400'); self.c.commit()
        answers = [{'pack': p['pack'], 'i': q['i'], 'choice': key(p, q) if p['level'] != 'B2' else (key(p, q) + 1) % 4} for p in t['passages'] for q in p['questions']]
        AR.comprehension_score(self.c, 1, {'kind': 'reading', 'answers': answers})
        reading = next(d for d in AR.radar(self.c, 1)['dims'] if d['id'] == 'reading')
        self.assertGreater(reading['score'], reading['prev_score'])
        self.assertEqual(AR.comprehension_score(self.c, 1, {'kind': 'reading', 'answers': [{'pack': 'nope', 'i': 0, 'choice': 0}]})[1], 404)
        self.assertEqual(AR.comprehension_score(self.c, 1, {'kind': 'singing', 'answers': []})[1], 400)

    def test_vocabulary_test_and_starting_check_feed_the_radar(self):
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 10, 'retention': 0.9})
        items = vs.test_items(seed=1)['items']
        r, code = vs.score_test(self.c, 1, {'answers': {w: w not in vs.PSEUDO for w in items}})  # knows the real words, rejects the made-up ones
        self.assertEqual(code, 200, r)
        t = GB.placement_items(self.c, seed=2)['items']
        right = lambda i: self.c.execute('SELECT answer FROM questions WHERE id=?', (i['id'],)).fetchone()[0]
        GB.placement_score(self.c, 1, {'answers': [{'question': i['id'], 'choice': right(i)} for i in t[:4]] + [{'question': i['id'], 'choice': None} for i in t[4:8]]})
        dims = {d['id']: d for d in AR.radar(self.c, 1)['dims']}
        self.assertEqual(dims['vocab']['source'], 'assessment'); self.assertIsNotNone(dims['vocab']['score'])
        self.assertEqual((dims['grammar']['source'], dims['grammar']['level']), ('assessment', 'A2'))  # A2 all right, B1 none: top of A2

    def test_writing_and_speaking_are_judged_by_the_ai_and_recorded(self):
        reply = {'level': 'B1', 'position': 0.5, 'scores': {'content': 4, 'organization': 3, 'accuracy': 3, 'range': 3}, 'strength': '例子具体。', 'next': ['多用连接词']}
        q = AR.task(self.c, 1, 'writing', seed=1)[0]['question']
        text = 'I would like to learn to cook because I live alone now. ' * 6
        with patch('chat_service.request_model', return_value=(json.dumps(reply), 'stop')):
            r, code = AR.judged(self.c, 1, 'writing', {'question': q, 'text': text, 'request_id': 'assess-writing-0001'})
        self.assertEqual(code, 200); self.assertEqual(r['result']['index'], 50); self.assertEqual(r['result']['recorded']['level'], 'B1')
        self.assertEqual(AR.judged(self.c, 1, 'writing', {'question': 'Something else?', 'text': text, 'request_id': 'assess-writing-0002'})[1], 400)
        self.assertEqual(AR.judged(self.c, 1, 'writing', {'question': q, 'text': 'Too short.', 'request_id': 'assess-writing-0003'})[1], 400)
        sq = AR.task(self.c, 1, 'speaking', seed=1)[0]['question']
        spoken = {**reply, 'scores': {'fluency': 3, 'accuracy': 3, 'range': 3, 'pronunciation': 4}, 'transcript': 'I went to Xi\'an.', 'level': 'A2', 'position': 0.9}
        audio = {'mime_type': 'audio/webm', 'data': __import__('base64').b64encode(b'\x1aE\xdf\xa3' + b'0' * 4000).decode()}
        with patch('chat_service.request_model', return_value=(json.dumps(spoken), 'stop')):
            r, code = AR.judged(self.c, 1, 'speaking', {'question': sq, 'audio': audio, 'request_id': 'assess-speaking-0001'})
        self.assertEqual(code, 200, r); self.assertEqual(r['result']['index'], 38)
        dims = {d['id']: d for d in AR.radar(self.c, 1)['dims']}
        self.assertEqual((dims['writing']['level'], dims['speaking']['level']), ('B1', 'A2'))

    def test_the_plan_works_on_the_widest_gap_and_asks_for_a_test_every_few_days(self):
        AR.set_goals(self.c, 1, {'goals': {k: 'B2' for k in ('listening', 'reading', 'speaking', 'writing')}})
        AR.record(self.c, 1, 'reading', 58); AR.record(self.c, 1, 'writing', 30)
        self.assertEqual(AR.weakest(self.c, 1), 'writing')
        steps = {s['key']: s for s in nx.home(self.c, 1)['path']['steps']}
        self.assertIn('essay', steps)  # the output step practises writing, the widest gap
        self.assertTrue(steps['assess']['done'])  # tested today
        self.c.execute('UPDATE next_assess SET created=created-86400'); self.c.commit()
        self.assertNotIn('assess', [s['key'] for s in nx.home(self.c, 1)['path']['steps']])  # not again the next day
        self.c.execute('UPDATE next_assess SET created=created-3*86400'); self.c.commit()
        self.assertFalse(next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'assess')['done'])

    def test_snapshots_are_kept_weekly_between_assessments(self):
        AR.record(self.c, 1, 'reading', 50)
        n = lambda: self.c.execute('SELECT COUNT(*) FROM next_radar WHERE user_id=1').fetchone()[0]
        self.assertEqual(n(), 1)
        AR.radar(self.c, 1); self.assertEqual(n(), 1)  # an assessment snapshot is recent: no automatic one
        self.c.execute('UPDATE next_radar SET created=created-8*86400'); self.c.commit()
        AR.radar(self.c, 1); self.assertEqual(n(), 2)
        self.assertEqual(len(AR.radar(self.c, 1)['history']), 2)


if __name__ == '__main__':
    unittest.main()
