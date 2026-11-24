"""雅思口语练习: listing, Part 1 answers and feedback, Part 2 talk, bands and rounding, honest labels, logging."""
import base64, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ielts_speaking as ie, next_service as nx

AUDIO = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
FEEDBACK = {'bands': {'fc': 6, 'lr': 6.5, 'gra': 5.4, 'p': 6}, 'summary': '能一直说下去，连接词偏少。',
            'notes': {'fc': {'good': '能接着说', 'next': '多用 because / for example'}, 'lr': {'good': '用了 vivid', 'next': '换掉 good'},
                      'gra': {'good': '时态基本对', 'next': '过去时别漏 -ed'}, 'p': {'good': '清楚', 'next': 'th 别读成 s'}},
            'fixes': [{'from': 'I am more fresh', 'to': 'I feel fresher', 'why': '比较级', 'node': None}],
            'model': 'I would say I am a morning person, because my mind is clearest before breakfast.', 'model_q': 1}


class IeltsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'i.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        self.env = patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
                                           'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_AI_AUDIO': '1'}); self.env.start()

    def tearDown(self):
        self.env.stop(); self.c.close(); self.p.stop(); self.tmp.cleanup()

    def ai(self, reply):
        return patch('chat_service.request_model', return_value=(json.dumps(reply, ensure_ascii=False), 'stop'))

    def test_content_is_original_and_complete(self):
        self.assertEqual(len(ie.PART1), 8); self.assertEqual(len(ie.PART2), 8)
        for k, (zh, en, qs) in ie.PART1.items():
            self.assertEqual(len(qs), 4, k); self.assertTrue(all(q.endswith('?') for q in qs), k)
        for k, (zh, task, points, last) in ie.PART2.items():
            self.assertTrue(task.startswith('Describe '), k); self.assertEqual(len(points), 3, k); self.assertTrue(last.startswith('and explain'), k)
        self.assertIn('不是官方成绩', ie.NOTICE); self.assertIn('不是真题', ie.NOTICE)
        self.assertEqual((ie.PREP_SECONDS, ie.TALK_SECONDS), (60, 120))

    def test_bands_and_overall_rounding(self):
        self.assertEqual([ie.band(v) for v in (6, 6.4, 6.6, 0, 12, 'x', None, float('nan'))], [6.0, 6.5, 6.5, 1.0, 9.0, None, None, None])
        # IELTS rounds the mean of the four to the nearest half band, .25 and .75 upwards
        self.assertEqual(ie.overall({'fc': 6, 'lr': 6, 'gra': 6, 'p': 6.5}), 6.0)    # 6.125
        self.assertEqual(ie.overall({'fc': 6, 'lr': 6.5, 'gra': 6, 'p': 6.5}), 6.5)  # 6.25
        self.assertEqual(ie.overall({'fc': 6.5, 'lr': 7, 'gra': 7, 'p': 7}), 7.0)    # 6.875
        self.assertEqual(ie.overall({'fc': 6.5, 'lr': 7, 'gra': 6.5, 'p': 7}), 7.0)  # 6.75
        self.assertEqual(ie.overall({'fc': 6, 'lr': 6, 'gra': 5, 'p': None}), 5.5)   # typed: three criteria
        self.assertEqual([ie.cefr(b) for b in (3.5, 4, 5, 5.5, 6.5, 7, 8.5)], ['A2', 'B1', 'B1', 'B2', 'B2', 'C1', 'C1'])

    def test_listing_for_a_guest_and_after_practice(self):
        d = ie.listing(self.c, None)
        self.assertEqual([x['id'] for x in d['part1']][:2], ['study-work', 'hometown'])
        self.assertEqual(d['part2'][0]['points'][0], 'what the skill is'); self.assertIsNone(d['part2'][0]['last'])
        self.assertEqual([c['title'] for c in d['criteria']], ['流利与连贯', '词汇', '语法', '发音'])
        self.assertEqual(d['notice'], ie.NOTICE)
        out, s = nx.get(self.c, None, '/api/next/ielts', {})
        self.assertEqual((s, len(out['part1'])), (200, 8))

    def test_part1_answer_spoken_and_typed(self):
        reply = {'heard': 'I prefer morning because I am more fresh', 'better': {'text': 'Definitely a morning person: I feel much fresher then.', 'why': '比较级用 fresher'},
                 'note': '语速稳，fresh 的 /ʃ/ 清楚；比较级用错'}
        with self.ai(reply) as model:
            out, s = ie.post(self.c, 1, {'step': 'answer', 'topic': 'mornings', 'q': 0, 'audio': AUDIO, 'request_id': 'ielts-ans-00001'})
        self.assertEqual(s, 200); self.assertEqual(model.call_args.kwargs['audio'], AUDIO)
        self.assertIn(ie.PART1['mornings'][2][0], model.call_args[0][0][1]['content'])
        r = out['result']
        self.assertEqual((r['heard'], r['better']['why'], r['note'][:3]), (reply['heard'], '比较级用 fresher', '语速稳'))
        with self.ai({'better': None, 'note': '直接回答了'}) as model:
            out, s = ie.post(self.c, 1, {'step': 'answer', 'topic': 'mornings', 'q': 1, 'text': 'I check my phone and drink water.', 'request_id': 'ielts-ans-00002'})
        self.assertEqual(s, 200); self.assertNotIn('audio', model.call_args.kwargs)
        self.assertEqual((out['result']['heard'], out['result']['better']), ('I check my phone and drink water.', None))
        self.assertEqual(ie.post(self.c, 1, {'step': 'answer', 'topic': 'mornings', 'q': 4, 'text': 'x'})[1], 404)
        self.assertEqual(ie.post(self.c, 1, {'step': 'answer', 'topic': 'nope', 'q': 0, 'text': 'x'})[1], 404)
        self.assertEqual(ie.post(self.c, 1, {'step': 'what'})[1], 400)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_skill_events WHERE kind='ielts'").fetchone()[0], 0)  # answers log nothing

    def test_part1_feedback_scores_logs_and_honest_label(self):
        answers = [{'q': 0, 'text': 'I prefer morning because I am more fresh.', 'note': 'th 读成 s', 'spoken': True},
                   {'q': 1, 'text': 'I drink water.', 'note': '', 'spoken': False}]
        with self.ai(FEEDBACK) as model:
            out, s = ie.post(self.c, 1, {'step': 'part1', 'topic': 'mornings', 'answers': answers, 'request_id': 'ielts-p1-fb-001'})
        self.assertEqual(s, 200)
        prompt = model.call_args[0][0][1]['content']
        self.assertIn('录音的转写', prompt); self.assertIn('打字', prompt); self.assertIn('th 读成 s', prompt)
        self.assertIn('不要说这是官方成绩', model.call_args[0][0][0]['content'])
        r = out['result']
        self.assertEqual([c['band'] for c in r['criteria']], [6.0, 6.5, 5.5, 6.0]); self.assertEqual(r['overall'], 6.0)
        self.assertEqual((r['model_q'], r['answered'], r['spoken'], r['notice']), (ie.PART1['mornings'][2][0], 2, True, ie.NOTICE))
        ev = self.c.execute("SELECT skill, score, level, pack FROM next_skill_events WHERE kind='ielts'").fetchall()
        self.assertEqual([tuple(e) for e in ev], [('speaking', 6.0 / 9, 'B2', 'ielts-p1-mornings')])
        self.assertEqual(self.c.execute("SELECT text FROM next_cards WHERE source='mistake'").fetchone()[0], 'I feel fresher')
        self.assertEqual(ie.listing(self.c, 1)['part1'][2]['last'], 6.0)
        with self.ai(FEEDBACK):  # the same request again: replayed, logged once
            ie.post(self.c, 1, {'step': 'part1', 'topic': 'mornings', 'answers': answers, 'request_id': 'ielts-p1-fb-001'})
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_skill_events WHERE kind='ielts'").fetchone()[0], 1)

    def test_typed_only_has_no_pronunciation_band(self):
        answers = [{'q': 0, 'text': 'I am a student of chemistry.', 'note': '', 'spoken': False}]
        with self.ai(FEEDBACK) as model:
            out, s = ie.post(self.c, 1, {'step': 'part1', 'topic': 'study-work', 'answers': answers, 'request_id': 'ielts-p1-fb-002'})
        self.assertIn('p 填 null', model.call_args[0][0][0]['content'])
        r = out['result']
        self.assertIsNone(r['criteria'][3]['band']); self.assertEqual(r['overall'], 6.0)  # mean of 6, 6.5, 5.5
        self.assertEqual((r['criteria'][3]['good'], r['criteria'][3]['next']), ('', ''))  # no notes on sounds it never heard
        self.assertFalse(r['spoken'])

    def test_part1_feedback_rejects_bad_input_and_bad_replies(self):
        self.assertEqual(ie.post(self.c, 1, {'step': 'part1', 'topic': 'mornings', 'answers': []})[1], 400)
        self.assertEqual(ie.post(self.c, 1, {'step': 'part1', 'topic': 'mornings', 'answers': [{'q': 9, 'text': 'x'}]})[1], 400)
        with self.ai({'bands': {'fc': 6}}):  # fewer than three criteria: not saved, the page offers to try again
            out, s = ie.post(self.c, 1, {'step': 'part1', 'topic': 'mornings', 'answers': [{'q': 0, 'text': 'Yes I do.', 'spoken': False}], 'request_id': 'ielts-p1-fb-003'})
        self.assertEqual(s, 502); self.assertIn('error', out)

    def test_part2_talk_spoken(self):
        reply = {**FEEDBACK, 'transcript': 'I want to talk about cooking, which I learned from my grandmother.', 'covered': [True, True, False, True]}
        with self.ai(reply) as model:
            out, s = ie.post(self.c, 1, {'step': 'part2', 'card': 'skill', 'audio': AUDIO, 'seconds': 95, 'request_id': 'ielts-p2-00001'})
        self.assertEqual(s, 200); self.assertEqual(model.call_args.kwargs['audio'], AUDIO)
        prompt = model.call_args[0][0][1]['content']
        self.assertIn('Describe a skill you learned outside school or work.', prompt); self.assertIn('说了 95 秒', prompt)
        r = out['result']
        self.assertEqual((r['transcript'][:22], r['covered'], r['seconds'], r['overall']), ('I want to talk about c', [True, True, False, True], 95, 6.0))
        self.assertEqual(self.c.execute("SELECT pack FROM next_skill_events WHERE kind='ielts'").fetchone()[0], 'ielts-p2-skill')

    def test_part2_typed_and_limits(self):
        short = {'step': 'part2', 'card': 'skill', 'text': 'Cooking is my skill.', 'request_id': 'ielts-p2-00002'}
        out, s = ie.post(self.c, 1, short)
        self.assertEqual(s, 400); self.assertIn('20 个英文词', out['error'])
        text = 'I learned to cook from my grandmother when I was fifteen, and it took me about a year to cook well enough to make dinner for the family.'
        with self.ai({**FEEDBACK, 'covered': [True, True, True]}) as model:
            out, s = ie.post(self.c, 1, {'step': 'part2', 'card': 'skill', 'text': text, 'seconds': 999, 'request_id': 'ielts-p2-00003'})
        self.assertEqual(s, 200); self.assertIn(text, model.call_args[0][0][1]['content'])
        r = out['result']
        self.assertEqual((r['transcript'], r['spoken'], r['seconds'], r['covered']), (text, False, None, None))
        self.assertIsNone(r['criteria'][3]['band'])
        self.assertEqual(ie.post(self.c, 1, {'step': 'part2', 'card': 'nope', 'text': text})[1], 404)

    def test_routes(self):
        self.assertIn('/api/next/ielts', nx.AI_PATHS)
        with self.ai({'better': None, 'note': ''}):
            out, s = nx.post(self.c, 1, '/api/next/ielts', {'step': 'answer', 'topic': 'music', 'q': 0, 'text': 'Pop, mostly.', 'request_id': 'ielts-route-0001'})
        self.assertEqual(s, 200)
        import console_data, flow_admin
        self.assertEqual(console_data.KIND_LABEL['next-ielts'], '雅思口语')
        self.assertIn('speak-ielts', flow_admin.TAP_LABEL); self.assertIn('shadow-sound', flow_admin.TAP_LABEL)


    def test_heading_for_ielts_the_plan_speaks_part1_topic_by_topic(self):
        """r27: studying abroad, or preparing for IELTS, the plan's speaking step is the next Part 1 topic, never gone."""
        import skills_service as sk, vocab_service as vs
        now = __import__('time').time()
        speak = lambda: next((s for s in sk.daily_path(self.c, 1, nx.home(self.c, 1), now)['steps'] if s['key'] == 'speak'), None)
        with patch('ability_radar.weakest', return_value='writing'):  # today's output step is an essay, not a spoken retell
            nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'abroad', 'themes': [], 'minutes': 20})
            s = speak()
            self.assertEqual((s['title'], s['href'], s['done']), ('口语：雅思 Part 1 · 学习还是工作', '#/speak/ielts/p1-study-work', False))
            self.c.execute("INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(1,'speaking','ielts',?,'B2','ielts-p1-study-work',?)", (6 / 9, now - 2 * 86400))
            self.c.commit()
            self.assertEqual(speak()['href'], '#/speak/ielts/p1-hometown')
            for k, key in enumerate(list(ie.PART1)[1:]):  # every topic done, study-work longest ago
                self.c.execute("INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(1,'speaking','ielts',0.6,'B2',?,?)",
                               (ie.pack_id(1, key), now - 86400 * 1.5 + k * 60))
            self.c.commit()
            s = speak()
            self.assertEqual(s['href'], '#/speak/ielts/p1-study-work'); self.assertIn('再练一轮', s['sub'])
            self.c.execute("INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(1,'speaking','ielts',0.6,'B2','ielts-p1-music',?)", (now,))
            self.c.commit()
            s = speak()
            self.assertEqual((s['done'], s['sub']), (True, '今天说过了'))
            self.c.execute("DELETE FROM next_skill_events WHERE created>=?", (now - 60,)); self.c.commit()
            # preparing for an exam: IELTS (its word book) speaks Part 1; another exam keeps the role-play scenes
            nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'exam', 'themes': [], 'minutes': 20})
            vs.save_plan(self.c, 1, {'book': 'ielts', 'daily_new': 10, 'retention': 0.9})
            self.assertTrue(speak()['href'].startswith('#/speak/ielts/p1-'))
            self.assertTrue(ie.for_ielts(self.c, 1, {'goal': 'exam', 'exam': 'ielts'}))
            vs.save_plan(self.c, 1, {'book': 'cet6', 'daily_new': 10, 'retention': 0.9})
            self.assertIsNone(speak())  # an exam learner at 20 minutes: no speaking step, as before
            nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'work', 'themes': [], 'minutes': 20})
            self.assertTrue(speak()['href'].startswith('#/speak/') and 'ielts' not in speak()['href'])  # a role-play scene


if __name__ == '__main__':
    unittest.main()
