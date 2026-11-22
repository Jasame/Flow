import unittest, tempfile, sys, json, os, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, lab_service as lab

REWRITE = {'verdict': 'minor', 'summary': '意思清楚，时态需要统一。', 'corrected': 'If I had left earlier, I would have caught the bus.',
           'changes': [{'from': 'would catch', 'to': 'would have caught', 'why': '与过去事实相反要用 would have done'}],
           'versions': [{'label': '更自然', 'text': 'Had I left earlier, I would have made the bus.', 'why': '倒装更紧凑'},
                        {'label': '更正式', 'text': 'Had I departed earlier, I would have caught the bus.', 'why': '用词更正式'},
                        {'label': '更简洁', 'text': 'Leaving earlier would have got me the bus.', 'why': '更短'}],
           'keep': {'text': 'make the bus', 'meaning': '赶上公交'}}


class NextServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'next.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
                                           'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'): self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def pid(self, level='B2'):
        return nx.home(self.c, None, level)['today'][0]['id']

    def test_guest_home_uses_requested_level_and_profile_overrides(self):
        h = nx.home(self.c, None, 'A2')
        self.assertEqual(h['level'], 'A2'); self.assertEqual(len(h['today']), 3)
        self.assertTrue(all(x['level'] == 'A2' for x in h['today'])); self.assertIsNone(h['stats'])
        self.assertEqual(nx.save_profile(self.c, 1, {'level': 'C1', 'goal': 'work', 'themes': ['work', 'bogus'], 'minutes': 15})[1], 200)
        h = nx.home(self.c, 1, 'A2')
        self.assertEqual(h['level'], 'C1'); self.assertTrue(all(x['level'] == 'B2' for x in h['today']))
        self.assertEqual(h['profile']['themes'], ['work']); self.assertTrue(all(x['theme'] == 'work' for x in h['today']))
        self.assertEqual(nx.save_profile(self.c, 1, {'level': 'Z9'})[1], 400)

    def test_daily_picks_are_stable_within_a_day_and_skip_finished_material(self):
        a = [x['id'] for x in nx.home(self.c, 1, 'B1')['today']]
        self.assertEqual(a, [x['id'] for x in nx.home(self.c, 1, 'B1')['today']])
        nx.mark(self.c, 1, a[0], 'check')
        self.assertNotIn(a[0], [x['id'] for x in nx.home(self.c, 1, 'B1')['today']])

    def test_material_hides_answers_and_marks_words_above_level(self):
        pid = self.pid('B2')
        m, s = nx.material(self.c, None, pid, 'A2')
        self.assertEqual(s, 200); self.assertGreaterEqual(len(m['sentences']), 2)
        self.assertNotIn('answer', json.dumps(m['questions']))
        hard_a2 = set(m['hard'])
        m2, _ = nx.material(self.c, None, pid, 'C1')
        self.assertGreater(len(hard_a2), len(m2['hard']))
        self.assertTrue(m['can_variant']); self.assertIn('prompt', m['task'])
        self.assertEqual(nx.material(self.c, None, 'nope', 'B1')[1], 404)

    def test_lookup_handles_inflections(self):
        for w, lemma in [('decisions', 'decision'), ('stopped', 'stop'), ('arrived', 'arrive'), ('Cities', 'city'), ('news', 'news'),
                         ('hoping', 'hope'), ('biggest', 'big'), ('explained', 'explain')]:
            self.assertEqual(nx.lookup(w)['lemma'], lemma, w)
        self.assertIsNone(nx.lookup('qwzxv'))

    def test_check_records_evidence_only_for_members_and_marks_step(self):
        pid = self.pid()
        pack = json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (pid,)).fetchone()[0])
        last = len(pack['questions']) - 1
        out, s = nx.check(self.c, None, {'pack': pid, 'index': 0, 'choice': pack['questions'][0]['answer']})
        self.assertEqual((s, out['correct']), (200, True))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0], 0)
        nx.check(self.c, 1, {'pack': pid, 'index': last, 'choice': 0})
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM learning_events WHERE user_id=1 AND kind='next-check'").fetchone()[0], 1)
        self.assertIn('check', nx.material(self.c, 1, pid)[0]['steps'])
        self.assertEqual(nx.check(self.c, 1, {'pack': pid, 'index': 99, 'choice': 0})[1], 400)

    def test_cards_save_dedupe_scope_and_delete(self):
        out, s = nx.save_card(self.c, 1, {'text': 'decisions', 'context': 'We need to explain our decisions.', 'pack': 'x'})
        self.assertEqual(s, 200); self.assertEqual(out['card']['kind'], 'word'); self.assertIn('决定', out['card']['meaning'])
        again, _ = nx.save_card(self.c, 1, {'text': 'Decisions!', 'meaning': '决策'})
        self.assertTrue(again['existing']); self.assertEqual(again['card']['meaning'], '决策')
        self.assertEqual(nx.save_card(self.c, 1, {'text': 'a long way to go'})[0]['card']['kind'], 'phrase')
        self.assertEqual(nx.save_card(self.c, 1, {'text': '中文'})[1], 400)
        self.assertEqual(nx.cards(self.c, 2)['total'], 0); self.assertEqual(nx.cards(self.c, 1, 'way')['total'], 1)
        cid = out['card']['id']
        self.assertEqual(nx.delete_card(self.c, 2, {'id': cid})[1], 404)
        self.assertEqual(nx.delete_card(self.c, 1, {'id': cid})[1], 200)

    def test_review_schedule_grows_and_resets(self):
        cid = nx.save_card(self.c, 1, {'text': 'make the bus'})[0]['card']['id']
        self.assertEqual(nx.review_queue(self.c, 1)['due'], 1)
        d1 = nx.review(self.c, 1, {'id': cid, 'rating': 'good'})[0]['card']
        self.assertEqual(d1['interval'], 1); self.assertEqual(nx.review_queue(self.c, 1)['due'], 0)
        self.c.execute('UPDATE next_cards SET due=0 WHERE id=?', (cid,)); self.c.commit()
        self.assertEqual(nx.review(self.c, 1, {'id': cid, 'rating': 'good'})[0]['card']['interval'], 3)
        self.c.execute('UPDATE next_cards SET due=0 WHERE id=?', (cid,)); self.c.commit()
        self.assertGreater(nx.review(self.c, 1, {'id': cid, 'rating': 'easy'})[0]['card']['interval'], 7)
        again = nx.review(self.c, 1, {'id': cid, 'rating': 'again'})[0]['card']
        self.assertEqual((again['interval'], again['reps'], again['lapses']), (0, 0, 1))
        self.assertEqual(nx.review(self.c, 2, {'id': cid, 'rating': 'good'})[1], 404)
        self.assertEqual(nx.stats(self.c, 1)['reviews_week'], 4)

    def test_rewrite_is_validated_quota_counted_and_marks_output(self):
        pid = self.pid()
        with patch.dict(os.environ, {'FLOW_AI_USER_DAILY_LIMIT': '1'}), patch('chat_service.request_model', return_value=(json.dumps(REWRITE), 'stop')) as model:
            out, s = nx.rewrite(self.c, 1, {'pack': pid, 'text': 'If I left earlier I would catch the bus.', 'request_id': 'next-rw-0001'})
            self.assertEqual(s, 200); r = out['result']
            self.assertEqual(len(r['versions']), 3); self.assertEqual(r['keep']['text'], 'make the bus')
            self.assertIn('output', nx.material(self.c, 1, pid)[0]['steps'])
            self.assertEqual(nx.rewrite(self.c, 1, {'pack': pid, 'text': 'If I left earlier I would catch the bus.', 'request_id': 'next-rw-0001'})[1], 200)
            self.assertEqual(nx.rewrite(self.c, 1, {'pack': pid, 'text': 'Another try at the sentence.', 'request_id': 'next-rw-0002'})[1], 429)
            self.assertEqual(model.call_count, 1)
        self.assertEqual(nx.rewrite(self.c, 1, {'pack': pid, 'text': '只有中文', 'request_id': 'next-rw-0003'})[1], 400)
        with patch('chat_service.request_model', return_value=(json.dumps({'summary': 'x', 'corrected': 'y'}), 'stop')):
            self.assertEqual(nx.rewrite(self.c, 1, {'pack': pid, 'text': 'Valid english text here.', 'request_id': 'next-rw-0004'})[1], 502)

    def test_variant_generated_once_then_shared(self):
        pid = self.pid('B2')
        body = json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (pid,)).fetchone()[0])['body']
        simple = ' '.join(['I went to the hall late.'] * max(2, len(body.split()) // 7))
        with patch('chat_service.request_model', return_value=(json.dumps({'body': simple, 'notes': [{'text': 'go late', 'meaning': '晚到'}]}), 'stop')) as model:
            out, s = nx.variant(self.c, 1, {'pack': pid, 'level': 'A2', 'request_id': 'next-var-0001'})
            self.assertEqual((s, out['cached']), (200, False))
            out2, s2 = nx.variant(self.c, 2, {'pack': pid, 'level': 'A2', 'request_id': 'next-var-0002'})
            self.assertEqual((s2, out2['cached']), (200, True)); self.assertEqual(model.call_count, 1)
        nx.save_profile(self.c, 2, {'level': 'A2'})
        m = nx.material(self.c, 2, pid)[0]
        self.assertEqual(m['variant']['level'], 'A2'); self.assertEqual(' '.join(m['sentences']), simple)
        with patch('chat_service.request_model', return_value=(json.dumps({'body': 'Too short.'}), 'stop')):
            self.assertEqual(nx.variant(self.c, 1, {'pack': pid, 'level': 'C1', 'request_id': 'next-var-0003'})[1], 502)


class NextHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'h.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'}); self.env.start()
        app.SECURE = False
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', app.password('correct horse battery')))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cookie = ''

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def call(self, path, data=None, csrf=None):
        h = {'Content-Type': 'application/json', 'Cookie': self.cookie}
        if csrf: h['X-CSRF-Token'] = csrf
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.headers.get('Set-Cookie'): self.cookie = r.headers['Set-Cookie'].split(';')[0]
                return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()

    def test_page_guest_routes_and_member_routes(self):
        s, body = self.call('/next'); self.assertEqual(s, 200); self.assertIn(b'/next.js', body)
        for a in ('/next.js', '/next.css'): self.assertEqual(self.call(a)[0], 200)
        self.assertEqual(json.loads(self.call('/api/next/meta')[1])['levels'][0]['id'], 'A2')
        home = json.loads(self.call('/api/next/home?level=B1')[1]); pid = home['today'][0]['id']
        self.assertEqual(self.call('/api/next/material?id=' + pid)[0], 200)
        self.assertEqual(json.loads(self.call('/api/next/lookup?w=decisions')[1])['entry']['lemma'], 'decision')
        self.assertEqual(self.call('/api/next/check', {'pack': pid, 'index': 0, 'choice': 0})[0], 200)
        self.assertEqual(self.call('/api/next/cards')[0], 401)
        self.assertEqual(self.call('/api/next/cards', {'text': 'hello'})[0], 401)
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': 'correct horse battery'})[0], 200)
        csrf = json.loads(self.call('/api/session')[1])['user']['csrf']
        self.assertEqual(self.call('/api/next/cards', {'text': 'hello there'})[0], 403)
        self.assertEqual(self.call('/api/next/profile', {'level': 'B2', 'themes': ['science']}, csrf)[0], 200)
        self.assertEqual(self.call('/api/next/cards', {'text': 'hello there'}, csrf)[0], 200)
        self.assertEqual(json.loads(self.call('/api/next/review')[1])['due'], 1)
        self.assertEqual(json.loads(self.call('/api/next/home')[1])['level'], 'B2')
        self.assertEqual(self.call('/api/next/nothing')[0], 404)


if __name__ == '__main__':
    unittest.main()
