"""r28 口语情景: scenes come back in rounds (a harder requirement, then the roles swapped), so speaking never drops out of
the plan; and the AI pitches each line by the learner's last answer (按回答调难度: length and mistakes, no emotion)."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, scenarios as SC, output_service as out, skills_service as sk

DAY = 86400
AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
          'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}


class RoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'r.db'); self.p.start()
        self.env = patch.dict(os.environ, AI_ENV); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 30})
        self.now = time.time()

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def did(self, sid, days_ago, score=0.7):
        self.c.execute("INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(1,'speaking','dialog',?,'B1',?,?)",
                       (score, 'scene-' + sid, self.now - days_ago * DAY)); self.c.commit()

    def test_content_covers_every_scene(self):
        self.assertEqual(set(SC.CHALLENGE), set(SC.SCENES)); self.assertEqual(set(SC.SWAP), set(SC.SCENES))
        for k, goals in SC.SWAP.items():
            self.assertEqual(len(goals), len(SC.SCENES[k][7]), k)  # as many goals as the usual part has
        self.assertEqual([SC.mode_of(n) for n in range(1, 7)], ['first', 'challenge', 'swap', 'challenge', 'swap', 'challenge'])

    def test_a_round_two_has_one_more_requirement_and_round_three_swaps_the_roles(self):
        ch = SC.pack('flat-viewing', 'challenge')
        self.assertIn(SC.CHALLENGE['flat-viewing'], ch['body']); self.assertIn(SC.CHALLENGE['flat-viewing'], ch['speaking'])
        self.assertEqual((ch['mode'], ch['challenge']), ('challenge', SC.CHALLENGE['flat-viewing']))
        sw = SC.pack('flat-viewing', 'swap')
        level, title, en, ai, me = SC.SCENES['flat-viewing'][:5]
        self.assertIn(f'The AI plays: {me}. The learner plays: {ai}.', sw['body'])
        self.assertIn(SC.SWAP['flat-viewing'][0], sw['body']); self.assertNotIn('Useful expressions', sw['body'])
        self.assertEqual((sw['mode'], sw['challenge']), ('swap', ''))
        self.assertEqual(SC.pack('flat-viewing')['mode'], 'first')

    def test_rounds_count_days_and_the_next_round_follows(self):
        self.assertEqual(SC.mode_for(self.c, 1, 'cafe-order'), 'first')
        self.did('cafe-order', 20); self.did('cafe-order', 20)  # twice the same day: one round
        it = next(x for x in SC.listing(self.c, 1, 'B1', self.now)['items'] if x['id'] == 'cafe-order')
        self.assertEqual((it['rounds'], it['round'], it['mode'], it['challenge']), (1, 2, 'challenge', SC.CHALLENGE['cafe-order']))
        self.did('cafe-order', 3)
        it = next(x for x in SC.listing(self.c, 1, 'B1', self.now)['items'] if x['id'] == 'cafe-order')
        self.assertEqual((it['round'], it['mode'], it['swap_goals']), (3, 'swap', SC.SWAP['cafe-order']))
        self.assertEqual(SC.mode_for(self.c, 1, 'cafe-order'), 'swap')

    def test_once_all_are_done_the_next_is_a_rested_scene_that_went_least_well(self):
        d = SC.listing(self.c, 1, 'B1', self.now)
        self.assertFalse(d['round_two'])
        for k, sid in enumerate(SC.SCENES):
            self.did(sid, 20 + k, 0.8)
        self.did('return-item', 16, 0.4)  # went least well, and rested
        self.did('job-interview', 3, 0.2)   # went worse, but practised 3 days ago
        d = SC.listing(self.c, 1, 'B1', self.now)
        self.assertTrue(d['round_two']); self.assertEqual(d['done'], d['total'])
        self.assertEqual(d['next'], 'return-item')
        for sid in SC.SCENES:  # everything practised in the last two weeks: the one practised longest ago
            self.did(sid, 1)
        self.did('ask-way', 0.1)
        oldest = min(SC.SCENES, key=lambda s: max(t for (t,) in self.c.execute("SELECT created FROM next_skill_events WHERE pack=?", ('scene-' + s,))))
        self.assertEqual(SC.listing(self.c, 1, 'B1', self.now)['next'], oldest)

    def test_the_plan_keeps_a_speaking_step_after_all_twelve(self):
        for k, sid in enumerate(SC.SCENES):
            self.did(sid, 20 + k, 0.3 if sid == 'flat-viewing' else 0.8)  # one round each; 看房租房 went least well
        with patch('ability_radar.weakest', return_value='writing'):  # today's output step is an essay, not a spoken retell
            st = {s['key']: s for s in sk.daily_path(self.c, 1, nx.home(self.c, 1), self.now)['steps']}
        s = st['speak']
        self.assertEqual((s['title'], s['href'], s['done']), ('口语：看房租房 · 第 2 轮', '#/speak/flat-viewing', False))
        self.assertEqual(s['sub'], '这次多一条：' + SC.CHALLENGE['flat-viewing'])

    def test_pace_follows_the_answer(self):
        self.assertEqual(SC.pace('yes', False), 'easier')
        self.assertEqual(SC.pace('I want buy a ticket', True), 'easier')  # short with a mistake
        self.assertEqual(SC.pace('I would like a large latte with oat milk', True), 'same')
        self.assertEqual(SC.pace('I would like a large latte please', False), 'same')
        self.assertEqual(SC.pace('It is about ten minutes on foot and there is a bus stop outside', False), 'harder')
        self.assertEqual(SC.pace('It is about ten minutes on foot and there is a bus stop outside', True), 'same')

    def test_the_dialogue_pitches_its_lines_and_says_so(self):
        replies = [{'scene': '你在看房。', 'role': '房东', 'reply': 'Hi! Come in. What would you like to know?'},
                   {'reply': 'OK. Is it near your school?', 'correction': None, 'hint': '说说离学校多远', 'say': "It's about ten minutes on foot."},
                   {'reply': 'Nice. How do you feel about sharing a kitchen with two others?', 'correction': None, 'hint': '', 'say': 'Not needed.'},
                   {'summary': '敢开口。', 'good': [], 'fixes': [], 'expressions': [], 'score': 0.6, 'challenge_met': True}]
        calls = []
        def fake(msgs, audio=None):
            calls.append(msgs); return json.dumps(replies[len(calls) - 1], ensure_ascii=False), 'stop'
        self.did('flat-viewing', 20)  # round 2: the challenge
        with patch('chat_service.request_model', side_effect=fake):
            r, code = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': [], 'request_id': 'rounds-req-0001'})
            self.assertEqual((code, r['result']['mode'], r['result']['challenge']), (200, 'challenge', SC.CHALLENGE['flat-viewing']))
            self.assertIn('不到 4 个词', calls[0][0]['content']); self.assertIn(SC.CHALLENGE['flat-viewing'], calls[0][1]['content'])
            hist = [{'role': 'ai', 'text': replies[0]['reply']}]
            r, _ = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': hist, 'text': 'yes', 'request_id': 'rounds-req-0002'})
            self.assertEqual((r['result']['pace'], r['result']['say']), ('easier', "It's about ten minutes on foot."))
            self.assertIn('"say"', calls[1][1]['content'])
            hist += [{'role': 'me', 'text': 'yes'}, {'role': 'ai', 'text': replies[1]['reply']}]
            long = "It's ten minutes on foot, and there's a bus stop right outside the building."
            r, _ = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': hist, 'text': long, 'request_id': 'rounds-req-0003'})
            self.assertEqual((r['result']['pace'], r['result']['say']), ('harder', ''))  # a sentence to use only when slowing down
            hist += [{'role': 'me', 'text': long}, {'role': 'ai', 'text': replies[2]['reply']}]
            r, _ = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': hist, 'end': True, 'request_id': 'rounds-req-0004'})
            self.assertEqual((r['result']['challenge'], r['result']['challenge_met']), (SC.CHALLENGE['flat-viewing'], True))
            self.assertIn('challenge_met', calls[3][1]['content'])
        self.assertEqual(SC.mode_for(self.c, 1, 'flat-viewing'), 'swap')  # round 2 finished today: the next one swaps the roles

    def test_material_dialogues_are_unchanged(self):
        pid = 'v5-science-b2-noise-cancelling'
        reply = {'heard': 'yes', 'reply': 'Why?', 'correction': None, 'hint': ''}
        with patch('chat_service.request_model', return_value=(json.dumps(reply), 'stop')) as m:
            r, code = out.dialog(self.c, 1, {'pack': pid, 'history': [{'role': 'ai', 'text': 'Do you like them?'}], 'text': 'yes', 'request_id': 'material-req-01'})
        self.assertEqual(code, 200); self.assertNotIn('pace', r['result']); self.assertNotIn('不到 4 个词', m.call_args[0][0][0]['content'])


if __name__ == '__main__':
    unittest.main()
