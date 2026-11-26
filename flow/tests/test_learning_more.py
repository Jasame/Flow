"""r15: easy reading, word confusables, the speaking route, the B1 serial, and my progress."""
import unittest, tempfile, sys, json, time, os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, easy_reading as er, word_links as WL, scenarios as SC, growth_report as gr, vocab_service as vs

DAY = 86400


class MoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'more.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
                                           'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'abroad', 'themes': [], 'minutes': 30})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    # ---------------- easy reading ----------------

    def test_easy_reading_is_a_level_below_counts_words_and_speed_and_adapts(self):
        l, _ = er.listing(self.c, 1)
        self.assertEqual((l['level'], l['target']), ('B2', 'B1'))
        self.assertEqual(len(l['items']), 6); self.assertTrue(all(x['level'] == 'B1' for x in l['items']))
        first = l['items'][0]['id']
        r, code = er.done(self.c, 1, {'pack': first, 'seconds': 90, 'rating': 'easy'})
        self.assertEqual(code, 200); self.assertEqual(r['wpm'], round(r['words'] / 1.5))
        self.assertEqual(r['stats']['week_words'], r['words'])
        self.assertEqual(er.listing(self.c, 1)[0]['target'], 'B2')  # "too easy": up to the learner's own level, no further
        er.done(self.c, 1, {'pack': er.listing(self.c, 1)[0]['items'][0]['id'], 'seconds': 120, 'rating': 'easy'})
        self.assertEqual(er.listing(self.c, 1)[0]['target'], 'B2')
        for _ in range(3):
            er.done(self.c, 1, {'pack': er.listing(self.c, 1)[0]['items'][0]['id'], 'seconds': 120, 'rating': 'hard'})
        self.assertEqual(er.listing(self.c, 1)[0]['target'], 'A2')  # at most two levels down
        self.assertNotIn(first, [x['id'] for x in er.listing(self.c, 1)[0]['items']])  # a text read is not offered again
        # It counts as reading for the graph, but it is not a material in progress on the home page.
        p = json.loads(nx._pack_row(self.c, 1, first)['content'])
        if nx.pack_grammar(p):
            self.assertGreater(nx.graph_states(self.c, 1)[nx.pack_grammar(p)[0]]['met'], 0)
        self.assertIsNone(nx.home(self.c, 1)['resume'])
        self.assertEqual(er.done(self.c, 1, {'pack': first, 'seconds': 2, 'rating': 'ok'})[1], 400)  # under five seconds is not a read
        self.assertEqual(er.done(self.c, 1, {'pack': first, 'seconds': 60, 'rating': 'meh'})[1], 400)
        g, _ = er.done(self.c, None, {'pack': first, 'seconds': 60, 'rating': 'ok'})
        self.assertFalse(g['saved'])

    def test_a_speed_that_cannot_be_reading_is_not_stored_as_a_speed(self):
        pid = er.listing(self.c, 1)[0]['items'][0]['id']
        r, _ = er.done(self.c, 1, {'pack': pid, 'seconds': 6, 'rating': 'ok'})
        self.assertIsNone(r['wpm']); self.assertGreater(r['words'], 0)

    # ---------------- word confusables ----------------

    def test_word_groups_are_well_formed_and_a_lookup_names_the_group(self):
        self.assertGreaterEqual(len(WL.GROUPS), 50)
        for gid, (level, words, how, items) in WL.GROUPS.items():
            self.assertIn(level, ('A2', 'B1', 'B2', 'C1')); self.assertEqual(len(items), 3, gid)
            for sent, opts, ans, why in items:
                self.assertIn('____', sent); self.assertEqual(len(set(opts)), len(opts)); self.assertTrue(0 <= ans < len(opts) and why)
        hit, _ = nx.get(self.c, 1, '/api/next/lookup', {'w': ['lent']})
        self.assertEqual(hit['entry']['confusable'][0]['id'], 'borrow-lend')
        self.assertNotIn('confusable', nx.lookup('lent'))  # the cached dictionary entry is left alone
        for form, gid in (('borrowed', 'borrow-lend'), ('said', 'say-tell'), ('rose', 'raise-rise'), ('robbed', 'steal-rob'), ('watching', 'look-see-watch')):
            hit, _ = nx.get(self.c, 1, '/api/next/lookup', {'w': [form]})  # the form a reader taps, not only the base word
            self.assertIn(gid, [g['id'] for g in hit['entry']['confusable']], form)

    def test_a_missed_word_question_comes_back_on_another_question_until_right_twice(self):
        r = WL.round_of(['borrow-lend', 'make-do'], seed=2, per=2)
        self.assertEqual(len(r), 4); self.assertEqual({x['group'] for x in r}, {'borrow-lend', 'make-do'})
        WL.answer(self.c, 1, {'item': 'make-do:1', 'correct': False})
        card = self.c.execute("SELECT * FROM next_cards WHERE user_id=1 AND norm='wq:make-do'").fetchone()
        self.assertEqual((card['kind'], card['source']), ('question', 'mistake'))
        item = next(x for x in vs.queue(self.c, 1, part='other')['items'] if x['id'] == card['id'])
        self.assertEqual(item['variant']['kind'], 'word'); self.assertNotEqual(item['variant']['id'], 'make-do:1')  # never the missed one first
        self.assertEqual(vs.rate(self.c, 1, {'id': card['id'], 'rating': 'good'})[0]['outcome'], 'once-more')
        self.assertEqual(vs.rate(self.c, 1, {'id': card['id'], 'rating': 'good'})[0]['outcome'], 'passed')
        # Answers from review are recorded for progress, but make no new card.
        WL.answer(self.c, 1, {'item': 'borrow-lend:0', 'correct': False, 'from': 'review'})
        self.assertIsNone(self.c.execute("SELECT 1 FROM next_cards WHERE norm='wq:borrow-lend'").fetchone())
        self.assertEqual(WL.progress(self.c, 1)['make-do'], {'right': 0, 'tries': 1})
        for bad in ({'item': 'nope:0', 'correct': True}, {'item': 'make-do:9', 'correct': True}, {'item': 'make-do:0', 'correct': 'yes'}):
            self.assertEqual(WL.answer(self.c, 1, bad)[1], 400)

    # ---------------- speaking route ----------------

    def test_the_speaking_route_lists_twelve_scenes_and_a_scene_is_played_through_the_dialogue(self):
        l = SC.listing(self.c, 1, 'B2')
        self.assertEqual(l['total'], 12); self.assertEqual(SC.SCENES[l['next']][0], 'B2')
        calls = []

        def fake(messages, audio=None, grounding=False):
            calls.append(messages)
            user = messages[-1]['content']
            if '对话结束' in user:
                return json.dumps({'summary': '说得清楚。', 'good': ['Is that OK?'], 'fixes': [], 'expressions': [], 'score': 0.8}), 'stop'
            if '开始对话' in user:
                return json.dumps({'scene': '面试开始。', 'role': '面试官', 'reply': 'Tell me about yourself.'}), 'stop'
            return json.dumps({'reply': 'Great.', 'correction': None, 'hint': ''}), 'stop'
        with patch('chat_service.request_model', fake):
            out = __import__('output_service')
            r, code = out.dialog(self.c, 1, {'scenario': 'job-interview', 'history': [], 'request_id': 'scene-request-0001'})
            self.assertEqual(code, 200); self.assertIn('情景：求职面试', calls[0][-1]['content'])
            hist = [{'role': 'ai', 'text': 'Tell me about yourself.'}, {'role': 'me', 'text': 'I studied marketing.'}]
            r, code = out.dialog(self.c, 1, {'scenario': 'job-interview', 'history': hist, 'end': True, 'request_id': 'scene-request-0002'})
            self.assertEqual(code, 200)
        after = SC.listing(self.c, 1, 'B2')
        self.assertTrue(next(x for x in after['items'] if x['id'] == 'job-interview')['done']); self.assertEqual(after['done'], 1)
        self.assertNotEqual(after['next'], 'job-interview')
        self.assertIsNone(SC.pack('nope'))

    def test_longer_days_get_easy_reading_and_a_speaking_scene(self):
        steps = {s['key']: s for s in nx.home(self.c, 1)['path']['steps']}
        self.assertIn('easy', steps)
        if 'retell' not in steps:
            self.assertTrue(steps['speak']['href'].startswith('#/speak/'))
        nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'exam', 'themes': [], 'minutes': 15})
        keys = [s['key'] for s in nx.home(self.c, 1)['path']['steps']]
        self.assertNotIn('easy', keys); self.assertNotIn('speak', keys)

    # ---------------- serial and progress ----------------

    def test_the_b1_serial_is_in_order_and_recommended_one_episode_at_a_time(self):
        s, _ = nx.series(self.c, 1, 'a-new-term')
        self.assertEqual((s['of'], s['level']), (6, 'B1'))
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'abroad', 'themes': ['campus'], 'minutes': 15})
        ids = [e['id'] for e in s['episodes']]
        self.assertFalse({x['id'] for x in nx.home(self.c, 1)['today']} & set(ids[1:]))

    def test_my_progress_compares_months_and_milestones_only_count_up(self):
        pid = er.listing(self.c, 1)[0]['items'][0]['id']
        er.done(self.c, 1, {'pack': pid, 'seconds': 90, 'rating': 'ok'})
        m, code = gr.month(self.c, 1)
        self.assertEqual(code, 200)
        self.assertGreater(m['now']['words_read'], 0); self.assertEqual(m['now']['days'], 1); self.assertEqual(m['before']['days'], 0)
        keys = {x['key'] for x in m['milestones']}
        self.assertTrue({'read-10000', 'words-100', 'grammar-A2', 'series-lighthouse-ledger', 'series-a-new-term', 'scenes-5', 'days-30'} <= keys)
        self.assertTrue(all(0 <= x['have'] <= x['need'] for x in m['milestones']))
        last, _ = gr.month(self.c, 1, m['prev'])
        self.assertEqual(last['now']['days'], 0); self.assertEqual(last['month'], m['prev'])
        self.assertEqual(gr.month(self.c, 1, 'garbage')[0]['month'], m['month'])


if __name__ == '__main__':
    unittest.main()
