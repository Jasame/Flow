import unittest, tempfile, sys, os, time, json, base64, datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, vocab_service as vs, skills_service as sk, output_service as out, import_service as imp, sounds

AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
          'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_AI_AUDIO': '1'}
PID = 'v5-science-b2-noise-cancelling'
AUDIO = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
ARTICLE = ('Scientists have long wondered why some birds migrate at night. One idea is that the cooler air saves energy on long flights. '
           'Another is that darkness protects small birds from predators that hunt by sight. Recent observations suggest both reasons matter, '
           'and that the stars may help the birds keep their direction when the sky is clear. On cloudy nights, they seem to rely on other cues.')


def ai(obj):
    return patch('chat_service.request_model', return_value=(json.dumps(obj, ensure_ascii=False), 'stop'))


class LearnerModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'l.db'); self.p.start()
        self.env = patch.dict(os.environ, AI_ENV); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'): self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'exam', 'themes': ['science'], 'minutes': 15})
        self.n = 0

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def rid(self):
        self.n += 1
        return f'next-test-{self.n:06d}'

    def test_wrong_answers_become_question_cards_and_reading_evidence(self):
        q = json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (PID,)).fetchone()[0])['questions'][0]
        wrong = (q['answer'] + 1) % 4
        self.assertFalse(nx.check(self.c, 1, {'pack': PID, 'index': 0, 'choice': wrong})[0]['correct'])
        card = self.c.execute("SELECT * FROM next_cards WHERE user_id=1 AND source='mistake'").fetchone()
        self.assertEqual((card['kind'], card['skill']), ('question', 'reading'))
        item = vs.queue(self.c, 1)['items'][0]
        self.assertEqual(item['mode'], 'question'); self.assertEqual(item['extra']['answer'], q['answer'])
        nx.check(self.c, 1, {'pack': PID, 'index': 0, 'choice': wrong})  # the same mistake again: still one card
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE source='mistake'").fetchone()[0], 1)
        self.assertEqual(sk.ability(self.c, 1)['skills'][3]['count'], 2)

    def test_profile_estimates_levels_and_suggests_moving_up(self):
        for _ in range(4):
            sk.log(self.c, 1, 'listening', 'dictation', 0.95, 'B2'); sk.log(self.c, 1, 'reading', 'question', 1.0, 'B2')
        sk.log(self.c, 1, 'speaking', 'shadow', 0.4, 'B2'); sk.log(self.c, 1, 'speaking', 'shadow', 0.45, 'B2'); sk.log(self.c, 1, 'speaking', 'shadow', 0.4, 'B2')
        ab = sk.ability(self.c, 1)
        lv = {s['id']: s['level'] for s in ab['skills']}
        self.assertEqual((lv['listening'], lv['reading'], lv['speaking']), ('B2', 'B2', 'B1'))
        self.assertEqual(ab['weakest'], 'speaking')
        self.assertEqual(sk.suggest_level(self.c, 1)['to'], 'C1')
        self.assertIsNone(sk.suggest_level(self.c, 2))
        sk.log(self.c, 1, 'grammar', 'x', 1.0)  # not an event skill: ignored
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_skill_events WHERE skill='grammar'").fetchone()[0], 0)

    def test_daily_path_follows_the_weak_skill(self):
        for _ in range(3):
            sk.log(self.c, 1, 'speaking', 'shadow', 0.3, 'B2'); sk.log(self.c, 1, 'reading', 'question', 1.0, 'B2')
        home = nx.home(self.c, 1)
        keys = [s['key'] for s in home['path']['steps']]
        self.assertEqual(keys[:2], ['review', 'read']); self.assertIn('retell', keys); self.assertIn('dictate', keys)
        sk.log(self.c, 1, 'writing', 'retell', 0.8, 'B2')
        retell = next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'retell')
        self.assertTrue(retell['done']); self.assertIn('/output/retell', retell['href'])

    def test_rewrite_corrections_become_fix_cards(self):
        reply = {'verdict': 'minor', 'summary': '不错。', 'corrected': 'If I had left earlier, I would have caught the bus.',
                 'changes': [{'from': 'would catch', 'to': 'would have caught', 'why': '与过去事实相反', 'node': 'subjunctive-past'}],
                 'versions': [{'label': '更自然', 'text': 'Had I left earlier, I would have made the bus.', 'why': '倒装'}], 'used_well': []}
        with ai(reply):
            self.assertEqual(nx.rewrite(self.c, 1, {'pack': PID, 'text': 'If I left earlier I would catch the bus.', 'request_id': self.rid()})[1], 200)
        card = self.c.execute("SELECT * FROM next_cards WHERE source='mistake'").fetchone()
        self.assertEqual((card['kind'], card['text'], card['node']), ('fix', 'would have caught', 'subjunctive-past'))
        item = next(i for i in vs.queue(self.c, 1)['items'] if i['id'] == card['id'])
        self.assertEqual(item['mode'], 'fix'); self.assertEqual(item['extra']['from'], 'would catch'); self.assertEqual(item['node']['id'], 'subjunctive-past')
        self.assertEqual(self.c.execute("SELECT skill, kind FROM next_skill_events").fetchone()[:], ('writing', 'rewrite'))

    def test_retell_dialogue_essay_translation(self):
        with ai({'points': [{'point': '降噪靠反相声波', 'covered': True}, {'point': '对低频最有效', 'covered': False}], 'used': ['fight fire with fire'],
                 'fixes': [{'from': 'it make', 'to': 'it makes', 'why': '三单', 'node': 'agreement-head'}], 'comment': '要点清楚', 'model': 'Noise-cancelling headphones...'}):
            r, s = out.retell(self.c, 1, {'pack': PID, 'text': 'The headphones listen to the noise and it make an opposite wave so we hear less.', 'request_id': self.rid()})
        self.assertEqual(s, 200); self.assertAlmostEqual(r['result']['score'], 0.47, places=2)
        self.assertEqual(out.retell(self.c, 1, {'pack': PID, 'text': 'too short'})[1], 400)
        with ai({'scene': '你在耳机店', 'role': '店员', 'reply': 'Hi! Looking for headphones?'}):
            first = out.dialog(self.c, 1, {'pack': PID, 'history': [], 'request_id': self.rid()})[0]['result']
        self.assertEqual(first['role'], '店员')
        hist = [{'role': 'ai', 'text': first['reply']}]
        with ai({'reply': 'Great choice.', 'correction': {'original': 'I want buy', 'better': 'I want to buy', 'why': 'want to do'}, 'hint': '问问价格'}):
            turn = out.dialog(self.c, 1, {'pack': PID, 'history': hist, 'text': 'I want buy quiet ones.', 'request_id': self.rid()})[0]['result']
        self.assertEqual(turn['correction']['better'], 'I want to buy')
        hist += [{'role': 'me', 'text': 'I want buy quiet ones.'}, {'role': 'ai', 'text': turn['reply']}]
        with ai({'summary': '敢说', 'good': ['Looking for quiet ones.'], 'fixes': [{'from': 'want buy', 'to': 'want to buy', 'why': 'want to do'}],
                 'expressions': [{'text': 'shop around', 'meaning': '货比三家'}], 'score': 0.7}):
            end = out.dialog(self.c, 1, {'pack': PID, 'history': hist, 'end': True, 'request_id': self.rid()})[0]['result']
        self.assertEqual(end['score'], 0.7)
        self.assertEqual(out.dialog(self.c, 1, {'pack': PID, 'history': [{'role': 'x', 'text': 'y'}]})[1], 400)
        essay = ' '.join(['I think noise cancelling headphones are useful for students who study in busy places.'] * 5)
        with ai({'scores': {'content': 4, 'organization': 3, 'accuracy': 3, 'range': 2}, 'level': 'B1', 'comment': '观点清楚',
                 'paragraphs': [{'para': 1, 'note': '重复较多'}], 'fixes': [], 'better': [], 'model': 'Model.'}):
            e = out.essay(self.c, 1, {'pack': PID, 'text': essay, 'request_id': self.rid()})[0]['result']
        self.assertEqual(e['score'], 0.6); self.assertEqual(out.essay(self.c, 1, {'pack': PID, 'text': 'Too short.'})[1], 400)
        with ai({'zh': '你第一次在火车上戴上降噪耳机时，效果几乎像魔法。'}):
            src = out.translate_source(self.c, 1, {'pack': PID, 'i': 0, 'request_id': self.rid()})[0]
        self.assertFalse(src['cached']); self.assertTrue(out.translate_source(self.c, 1, {'pack': PID, 'i': 0})[0]['cached'])
        with ai({'score': 0.8, 'accuracy': '基本准确', 'fluency': '自然', 'fixes': [], 'reference': 'The first time...'}):
            t = out.translate(self.c, 1, {'pack': PID, 'i': 0, 'direction': 'zh2en', 'text': 'When you first wear them on a train it feels like magic.',
                                          'request_id': self.rid()})[0]['result']
        self.assertEqual(t['score'], 0.8)
        skills = {r[0] for r in self.c.execute('SELECT DISTINCT skill FROM next_skill_events')}
        self.assertEqual(skills, {'writing', 'speaking', 'translation'})
        self.assertGreaterEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE source='mistake' AND kind='fix'").fetchone()[0], 2)

    def test_pronunciation_sets_and_say(self):
        self.assertGreaterEqual(len(sounds.listing()['sets']), 10)
        self.assertIn('/θ/', sounds.focus_of('think'))
        miss = {'heard': 'sink', 'ok': False, 'note': '/θ/ 读成了 /s/', 'tip': '舌尖放在上下齿之间'}
        with ai(miss):
            r = out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})[0]['result']
        self.assertFalse(r['ok']); self.assertFalse(r['confirmed'])  # one verdict on one short word: just try again
        self.assertIsNone(self.c.execute("SELECT 1 FROM next_cards WHERE source='mistake'").fetchone())
        with ai({**miss, 'ok': True}):
            out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})
        with ai(miss):
            self.assertFalse(out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})[0]['result']['confirmed'])  # after a success
            r = out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})[0]['result']
        self.assertTrue(r['confirmed'])  # two misses in a row: now it is a pronunciation card
        card = self.c.execute("SELECT kind, text FROM next_cards WHERE source='mistake'").fetchone()
        self.assertEqual(tuple(card), ('sound', 'think'))
        self.assertEqual(out.say(self.c, 1, {'text': 'zzzqqq', 'audio': AUDIO})[1], 400)

    def test_a_word_judged_by_qwen_omni_is_a_reference_only(self):
        # owner 2026-11-25: 跟读 and 发音 off Gemini (「延迟太高了」); Omni once heard a correct "think" as "zink" 3 times in 3,
        # so its verdict on one word is shown as maybe wrong, counted as practice and never filed as a mistake
        import ai_routes
        miss = {'heard': 'zink', 'ok': False, 'note': '/θ/ 读成了 /z/', 'tip': '舌尖放在上下齿之间'}

        def answered_by(service, reply):
            def fake(msgs, audio=None):
                ai_routes.CTX.last_service = service  # as ai_routes.record notes it for the call that answered
                return json.dumps(reply, ensure_ascii=False), 'stop'
            return patch('chat_service.request_model', side_effect=fake)
        for _ in range(3):
            with answered_by('audio', miss):
                r = out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})[0]['result']
            self.assertEqual((r['ok'], r['tentative'], r['confirmed']), (False, True, False))
        self.assertIsNone(self.c.execute("SELECT 1 FROM next_cards WHERE source='mistake'").fetchone())
        self.assertEqual({x[0] for x in self.c.execute("SELECT score FROM next_skill_events WHERE kind='say'")}, {0.5})  # practice, not judged
        with answered_by('main', miss):  # Gemini answered (the backup): judged as before
            r = out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})[0]['result']
        self.assertEqual((r['tentative'], r['confirmed']), (False, False))  # the Omni misses before it were not misses
        with answered_by('main', miss):
            self.assertTrue(out.say(self.c, 1, {'text': 'think', 'audio': AUDIO, 'request_id': self.rid()})[0]['result']['confirmed'])

    def test_a_16k_wav_from_the_page_reaches_the_ai_as_wav(self):
        # the 发音 check can record 16 kHz mono 16-bit WAV (70-learner.js WAV16) for a pronunciation scorer, which 语流 12
        # is trying on Aliyun; the page does it only when the server says say_wav (FLOW_SAY_WAV=1), off by default
        import io, wave
        b = io.BytesIO()
        with wave.open(b, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0' * 16000)
        wav = {'mime_type': 'audio/wav', 'data': base64.b64encode(b.getvalue()).decode()}
        with ai({'heard': 'think', 'ok': True, 'note': '', 'tip': ''}) as m:
            r, st = out.say(self.c, 1, {'text': 'think', 'audio': wav, 'request_id': self.rid()})
        self.assertEqual((st, r['result']['ok']), (200, True))
        self.assertEqual(m.call_args.kwargs['audio'], wav)  # as recorded, not converted on the way
        self.assertFalse(app.session_info(None)['say_wav'])
        with patch.dict(os.environ, {'FLOW_SAY_WAV': '1'}):
            self.assertTrue(app.session_info(None)['say_wav'])

    def test_import_article_study_and_enrich(self):
        r = imp.save(self.c, 1, {'title': 'Night migration', 'text': ARTICLE})[0]
        pid = r['id']; self.assertTrue(pid.startswith('imp-'))
        self.assertTrue(imp.save(self.c, 1, {'text': ARTICLE})[0]['existing'])
        self.assertEqual(imp.save(self.c, 1, {'text': '这不是英文。' * 50})[1], 400)
        m, s = nx.material(self.c, 1, pid)
        self.assertEqual(s, 200); self.assertTrue(m['imported']); self.assertGreaterEqual(len(m['sentences']), 4)
        self.assertEqual(nx.material(self.c, 2, pid)[1], 404)  # private
        self.assertNotIn(pid, [x['id'] for x in nx.library(self.c, 1)['items']])
        with ai({'summary_zh': '候鸟为什么夜里迁徙', 'level': 'B2',
                 'questions': [{'prompt': 'Why might birds fly at night?', 'options': ['To save energy', 'To sing', 'To sleep', 'To eat'], 'answer': 0,
                                'evidence': 'the cooler air saves energy on long flights'},
                               {'prompt': 'Bad?', 'options': ['a', 'b', 'c', 'd'], 'answer': 1, 'evidence': 'not in the text'}],
                 'expressions': [{'text': 'keep their direction', 'meaning': '保持方向'}, {'text': 'made up', 'meaning': 'x'}],
                 'vocabulary': [{'term': 'predators', 'meaning': '捕食者'}]}):
            self.assertEqual(imp.enrich(self.c, 1, {'id': pid, 'request_id': self.rid()})[1], 200)
        m = nx.material(self.c, 1, pid)[0]
        self.assertEqual(len(m['questions']), 1); self.assertEqual([e['text'] for e in m['expressions']], ['keep their direction'])
        self.assertEqual(imp.articles(self.c, 1)['items'][0]['enriched'], True)
        self.assertEqual(imp.delete(self.c, 2, {'id': pid})[1], 404)
        self.assertEqual(imp.delete(self.c, 1, {'id': pid})[1], 200)

    def test_weekly_report_and_email(self):
        nx.mark(self.c, 1, PID, 'check')
        sk.log(self.c, 1, 'listening', 'dictation', 0.9, 'B2')
        cid = nx.save_card(self.c, 1, {'text': 'serendipity'})[0]['card']['id']
        vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})
        rp = sk.report(self.c, 1)
        self.assertEqual((rp['days'], rp['materials'], rp['reviews']), (1, 1, 1))
        self.assertTrue(any(s['id'] == 'listening' and s['now'] == 0.9 for s in rp['skills']))
        self.c.execute("UPDATE users SET email='l@example.test' WHERE id=1"); self.c.commit()
        vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})
        now = datetime.datetime.now(nx.TZ)
        sunday = (now + datetime.timedelta(days=(6 - now.weekday()) % 7)).replace(hour=20, minute=3).timestamp()
        sent = []
        self.assertEqual(sk.send_weekly(self.c, sunday, lambda *a: sent.append(a)), 1)
        self.assertIn('这周', sent[0][1]); self.assertEqual(sk.send_weekly(self.c, sunday + 60, lambda *a: sent.append(a)), 0)
        self.assertEqual(sk.send_weekly(self.c, sunday - 86400, lambda *a: sent.append(a)), 0)  # Saturday

    def test_client_scored_practice(self):
        self.assertEqual(sk.post_skill(self.c, 1, {'kind': 'dictation', 'score': 0.8, 'pack': PID})[1], 200)
        self.assertEqual(sk.post_skill(self.c, 1, {'kind': 'essay', 'score': 1})[1], 400)
        self.assertEqual(self.c.execute('SELECT skill, level FROM next_skill_events').fetchone()[:], ('listening', 'B2'))


class QARoundTests(LearnerModelTests):
    """Behaviour fixed after the QA round (walkthroughs at three levels and the production end-to-end run)."""

    def test_retried_request_returns_the_same_result_and_counts_once(self):
        reply = {'points': [{'point': '要点', 'covered': True}], 'used': [], 'fixes': [{'from': 'it make', 'to': 'it makes', 'why': '三单'}],
                 'comment': '好。', 'model': 'x'}
        body = {'pack': PID, 'text': 'The article says it make an opposite wave so the noise goes away quickly.', 'request_id': self.rid()}
        with ai(reply) as model:
            a = out.retell(self.c, 1, dict(body)); b = out.retell(self.c, 1, dict(body))
        self.assertEqual(model.call_count, 1); self.assertTrue(b[0].get('replayed'))
        self.assertEqual(a[0]['result'], b[0]['result'])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_skill_events WHERE kind='retell'").fetchone()[0], 1)
        card = self.c.execute("SELECT context FROM next_cards WHERE source='mistake'").fetchone()
        self.assertEqual(card['context'], body['text'])  # the sentence with the mistake

    def test_rewrite_retry_has_the_same_display_fields(self):
        reply = {'verdict': 'minor', 'summary': '好。', 'corrected': 'If I had left earlier, I would have caught it.', 'changes': [{'from': 'would catch', 'to': 'would have caught', 'why': '虚拟', 'node': 'subjunctive-past'}],
                 'versions': [{'label': '更自然', 'text': 'x', 'why': 'y'}], 'used_well': ['clause-adverb']}
        body = {'pack': PID, 'text': 'If I left earlier, I would catch it.', 'request_id': self.rid()}
        with ai(reply):
            a = nx.rewrite(self.c, 1, dict(body))[0]['result']; b = nx.rewrite(self.c, 1, dict(body))[0]['result']
        self.assertEqual(a, b); self.assertEqual(a['used_well'][0]['id'], 'clause-adverb'); self.assertTrue(a['changes'][0]['node_title'])

    def test_failed_call_gives_the_quota_back(self):
        import socket, chat_service
        with patch('chat_service.request_model', side_effect=socket.timeout('slow')):
            r, st = out.retell(self.c, 1, {'pack': PID, 'text': 'The headphones make an opposite sound wave to cancel the noise.', 'request_id': self.rid()})
        self.assertEqual(st, 504); self.assertNotIn('Gemini', r['error'])
        self.assertEqual(self.c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE user_id=1').fetchone()[0], 0)
        with ai({'nonsense': True}):  # the model answered (and cost a call), only the format was wrong: it counts
            out.retell(self.c, 1, {'pack': PID, 'text': 'The headphones make an opposite sound wave to cancel the noise.', 'request_id': self.rid()})
        self.assertEqual(self.c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE user_id=1').fetchone()[0], 1)

    def test_deleted_card_history_is_unlinked(self):
        cid = nx.save_card(self.c, 1, {'text': 'devise'})[0]['card']['id']
        vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})
        nx.delete_card(self.c, 1, {'id': cid})
        self.assertEqual(self.c.execute('SELECT card FROM next_reviews WHERE user_id=1').fetchone()[0], -cid)
        new = nx.save_card(self.c, 1, {'text': 'contrive'})[0]['card']['id']  # SQLite may hand out the same id again
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM next_reviews WHERE card=?', (new,)).fetchone()[0], 0)

    def test_switching_books_replaces_unstudied_words(self):
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9}); vs.queue(self.c, 1)
        core = {r[0]: r[1] for r in self.c.execute("SELECT id, norm FROM next_cards WHERE source='book'")}
        self.assertNotIn('the', core.values())  # the everyday words of 基础词汇 are skipped
        vs.save_plan(self.c, 1, {'book': 'gre', 'daily_new': 5, 'retention': 0.9}); vs.queue(self.c, 1)
        now = {r[0]: r[1] for r in self.c.execute("SELECT id, norm FROM next_cards WHERE source='book'")}
        gre = {w for _, w in vs.book_words()['gre']}
        self.assertEqual(len(now), 5); self.assertTrue(set(now.values()) <= gre)  # the old book's unstudied words made way
        self.assertFalse({w for w in core.values() if w not in gre} & set(now.values()))

    def test_daily_plan_keeps_todays_article_and_counts_three_dictations(self):
        first = nx.home(self.c, 1)['today'][0]['id']
        for step in ('listen', 'read', 'check'):
            nx.mark(self.c, 1, first, step)
        for k in range(2):
            sk.log(self.c, 1, 'listening', 'dictation', 0.9, 'B2', first)
        path = nx.home(self.c, 1)['path']
        read = next(s for s in path['steps'] if s['key'] == 'read')
        self.assertTrue(read['done']); self.assertIn(first, read['href'])
        dic = next((s for s in path['steps'] if s['key'] == 'dictate'), None)
        if dic:
            self.assertFalse(dic['done'])
            sk.log(self.c, 1, 'listening', 'dictation', 0.9, 'B2', first)
            self.assertTrue(next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'dictate')['done'])

    def test_report_covers_seven_days(self):
        r = sk.report(self.c, 1)
        d = lambda s: datetime.date.fromisoformat(s)
        self.assertEqual((d(r['to']) - d(r['from'])).days, 6)

    def test_sounds_know_the_contrast_word(self):
        self.assertEqual(sounds.partner_of('think'), 'sink'); self.assertEqual(sounds.partner_of('Sink'), 'think')
        s = sounds.listing()['sets'][0]
        self.assertTrue(s['listen']); self.assertTrue(s['pairs'][0][0]['phonetic'].startswith('['))
        self.assertNotIn("'", nx.lookup('ticket')['phonetic'])  # one phonetic style: ˈ not '


class QARound2Tests(LearnerModelTests):
    """Second round: dictionary senses, roots in Chinese, a harder test band, the skip toggle, import topics."""

    def test_reviewed_senses_and_chinese_roots(self):
        self.assertTrue(nx.lookup('mean')['meaning'].startswith('v. 意思是'))
        self.assertIn('利益相关者', nx.lookup('stakeholder')['meaning'])
        r = vs.roots('abbreviate')
        self.assertTrue(r and all(not any(ch.isdigit() for ch in x['part']) for x in r))
        self.assertTrue(any('一' <= ch <= '鿿' for ch in r[0]['meaning'])); self.assertIn(r[0]['kind'], ('动词后缀', '前缀', '词根'))

    def test_vocabulary_test_reaches_past_twenty_thousand(self):
        items = vs.test_items(7)['items']
        deep = set(vs.beyond_words())
        self.assertGreaterEqual(sum(w in deep for w in items), 6)
        answers = {w: w not in vs.PSEUDO for w in items}  # knows every real word, rejects the made-up ones
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9})
        r = vs.score_test(self.c, 1, {'answers': answers})[0]
        self.assertTrue(r['ceiling']); self.assertEqual(r['suggest'], 'gre')
        self.assertGreater(r['estimate'], sum(len(vs.book_words()[k]) for k in vs.BOOKS))  # past the old cap of the frequency books
        self.assertIn('beyond', r['bands'])
        # skipping known words can be switched off and on again
        vs.save_plan(self.c, 1, {'book': 'ielts', 'daily_new': 10, 'retention': 0.9, 'skip_known': False})
        self.assertEqual(vs.plan(self.c, 1)['skip_rank'], 0)
        vs.save_plan(self.c, 1, {'book': 'ielts', 'daily_new': 10, 'retention': 0.9, 'skip_known': True})
        self.assertEqual(vs.plan(self.c, 1)['skip_rank'], vs.plan(self.c, 1)['test_skip']); self.assertGreater(vs.plan(self.c, 1)['skip_rank'], 0)

    def test_import_topic_is_guessed_or_chosen(self):
        work = ('Our team meeting with the client moved to Monday. The manager said the project deadline is Friday, so every colleague '
                'must send an email update today. The company wants the customer to see progress before the next business review.')
        self.assertEqual(imp.save(self.c, 1, {'title': 'Work', 'text': work})[1], 200)
        self.assertEqual(json.loads(self.c.execute("SELECT content FROM lab_packs WHERE origin='import'").fetchone()[0])['theme'], 'work')
        self.assertEqual(imp.guess_theme(ARTICLE), 'science')
        pid = imp.save(self.c, 1, {'title': 'Birds', 'text': ARTICLE, 'theme': 'culture'})[0]['id']
        self.assertEqual(json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (pid,)).fetchone()[0])['theme'], 'culture')

    def test_beginner_hard_words_and_stable_picks(self):
        self.assertNotIn('forty', nx.material(self.c, None, PID, 'A2')[0]['hard'])
        guest = nx.home(self.c, None, 'B2', ['science'])['today'][0]['id']
        self.assertEqual(nx.home(self.c, 1)['today'][0]['id'], guest)  # same level and topics: signing in keeps today's pick
