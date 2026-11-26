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
        # a few words answered yesterday: an ordinary day, not the short day back after days away (r28 回归模式)
        self.c.execute("INSERT INTO next_reviews(user_id,card,rating,created) VALUES(1,0,'good',?)", (self.now - 86400,)); self.c.commit()
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

    def test_a_full_round_of_eight_lines_still_ends_with_its_feedback(self):
        # the owner, 2026-11-26: after 8 lines 「对话太长了，先结束这一轮吧」, and 结束并看反馈 was refused by the same limit
        hist = [{'role': 'ai', 'text': 'Hi! Come in. What would you like to know?'}]
        for k in range(out.DIALOG_LINES):
            hist += [{'role': 'me', 'text': f'Line number {k + 1} from me.'}, {'role': 'ai', 'text': f'Answer {k + 1}.'}]
        self.assertEqual(len(hist), 17)
        summary = {'summary': '说满了一轮。', 'good': ['Line number 1 from me.'], 'fixes': [], 'expressions': [], 'score': 0.7}
        with patch('chat_service.request_model', return_value=(json.dumps(summary, ensure_ascii=False), 'stop')) as m:
            r, code = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': hist, 'text': 'one more', 'request_id': 'full-round-09'})
            self.assertEqual((code, r['error']), (400, '对话太长了，先结束这一轮吧'))  # a 9th line: no
            m.assert_not_called()
            r, code = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': hist, 'end': True, 'request_id': 'full-round-end'})
            self.assertEqual((code, r['result']['summary']), (200, '说满了一轮。'))  # 结束并看反馈: yes
            self.assertIn('Line number 8 from me.', m.call_args[0][0][1]['content'])  # every line in the feedback
            r, code = out.dialog(self.c, 1, {'pack': 'v5-science-b2-noise-cancelling', 'history': hist, 'end': True, 'request_id': 'full-round-pk'})
            self.assertEqual(code, 200)  # 读后对话's 结束并总结 too
        r, code = out.dialog(self.c, 1, {'scenario': 'flat-viewing', 'history': hist * 3, 'end': True, 'request_id': 'full-round-big'})
        self.assertEqual(code, 400)  # still a limit (40)

    def test_material_dialogues_are_unchanged(self):
        pid = 'v5-science-b2-noise-cancelling'
        reply = {'heard': 'yes', 'reply': 'Why?', 'correction': None, 'hint': ''}
        with patch('chat_service.request_model', return_value=(json.dumps(reply), 'stop')) as m, patch('tts_service.start') as soon:
            r, code = out.dialog(self.c, 1, {'pack': pid, 'history': [{'role': 'ai', 'text': 'Do you like them?'}], 'text': 'yes', 'request_id': 'material-req-01'})
        self.assertEqual(code, 200); self.assertNotIn('pace', r['result']); self.assertNotIn('不到 4 个词', m.call_args[0][0][0]['content'])
        self.assertNotIn('voice', r['result']); soon.assert_called_once_with(1, 'Why?', 'us-f')  # the partner speaks in the learner's voice


class HumanTests(RoundTests):
    """像真人 and the voice (owner, 2026-11-24: 「语音比较僵硬，回复速度比较慢，不像真人」): short spoken turns in character,
    each role its own voice, and the server starts making that voice while the reply travels (声音接力)."""

    def test_every_scene_has_a_way_of_talking_and_a_voice(self):
        self.assertEqual(set(SC.PERSONA), set(SC.SCENES))
        self.assertTrue(all(len(p) > 20 and g in ('f', 'm') for p, g in SC.PERSONA.values()))
        self.assertEqual({g for _, g in SC.PERSONA.values()}, {'f', 'm'})  # not one voice for everyone

    def test_the_role_sets_the_voice_and_the_learner_the_accent(self):
        g = SC.PERSONA['see-doctor'][1]
        self.assertEqual(SC.voice_for('see-doctor', 'first', 'uk-f'), 'uk-' + g)
        self.assertEqual(SC.voice_for('see-doctor', 'challenge', 'us-f'), 'us-' + g)
        self.assertEqual(SC.voice_for('see-doctor', 'swap', 'us-f'), 'us-' + ('m' if g == 'f' else 'f'))  # the AI plays the patient
        self.assertEqual(SC.voice_for('see-doctor', 'first', None), 'us-' + g)

    def test_short_spoken_turns_in_character_and_the_voice_starts_at_once(self):
        replies = [{'scene': '你在咖啡店。', 'role': '店员', 'reply': "Hi there! What can I get you?"},
                   {'reply': "Sure thing. Hot or iced?", 'correction': None, 'hint': '', 'say': ''}]
        calls = []
        def fake(msgs, audio=None):
            calls.append(msgs); return json.dumps(replies[len(calls) - 1], ensure_ascii=False), 'stop'
        with patch('chat_service.request_model', side_effect=fake), patch('tts_service.start') as soon:
            r, _ = out.dialog(self.c, 1, {'scenario': 'cafe-order', 'history': [], 'request_id': 'human-req-0001'})
            voice = SC.voice_for('cafe-order', 'first', 'us-f')
            self.assertEqual(r['result']['voice'], voice); soon.assert_called_with(1, replies[0]['reply'], voice)
            system = calls[0][0]['content']
            for rule in ('1–2 句', '不超过 25 个英文词', '先接住对方刚说的内容', '一次只问一个问题', '不纠错', SC.PERSONA['cafe-order'][0]):
                self.assertIn(rule, system)
            r, _ = out.dialog(self.c, 1, {'scenario': 'cafe-order', 'history': [{'role': 'ai', 'text': replies[0]['reply']}], 'text': 'A latte, please.',
                                          'request_id': 'human-req-0002'})
            self.assertEqual(r['result']['voice'], voice); soon.assert_called_with(1, replies[1]['reply'], voice)
            # a second learner gets the kept opening, and its voice, without asking the AI
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('second', 'h')); self.c.commit()
            nx.save_profile(self.c, 2, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})  # the same level: the same opening
            r, _ = out.dialog(self.c, 2, {'scenario': 'cafe-order', 'history': [], 'request_id': 'human-req-0003'})
            self.assertEqual((r.get('cached'), r['result']['reply'], r['result']['voice'], len(calls)), (True, replies[0]['reply'], voice, 2))

    def test_openings_kept_before_the_personas_are_not_used(self):
        old = {'scene': '旧的开场', 'role': '店员', 'reply': 'Welcome to our café, what would you like to order today from our menu?'}
        self.c.execute('INSERT INTO next_dialog_openers VALUES(?,?,?,?)', ('scene-cafe-order', 'B1', json.dumps(old), time.time())); self.c.commit()
        new = {'scene': '你在咖啡店。', 'role': '店员', 'reply': 'Hi! What can I get you?'}
        with patch('chat_service.request_model', return_value=(json.dumps(new, ensure_ascii=False), 'stop')), patch('tts_service.start'):
            r, _ = out.dialog(self.c, 1, {'scenario': 'cafe-order', 'history': [], 'request_id': 'human-req-0004'})
        self.assertEqual(r['result']['reply'], new['reply'])

    def test_a_swapped_round_plays_the_learners_usual_part(self):
        self.did('see-doctor', 40); self.did('see-doctor', 20)  # two days done: round 3 swaps
        reply = {'scene': '你是医生。', 'role': '病人', 'reply': "Hi, doctor. I've had a sore throat for three days."}
        with patch('chat_service.request_model', return_value=(json.dumps(reply, ensure_ascii=False), 'stop')) as m, patch('tts_service.start'):
            r, _ = out.dialog(self.c, 1, {'scenario': 'see-doctor', 'history': [], 'request_id': 'human-req-0005'})
        self.assertEqual((r['result']['mode'], r['result']['voice']), ('swap', SC.voice_for('see-doctor', 'swap', 'us-f')))
        self.assertIn('an ordinary person in this part (病人)', m.call_args[0][0][0]['content'])


if __name__ == '__main__':
    unittest.main()
