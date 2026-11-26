import datetime, unittest, tempfile, sys, json, os, threading, time, urllib.request, urllib.error
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
        self.assertEqual(h['level'], 'C1'); self.assertTrue(all(x['level'] in ('C1', 'B2') for x in h['today']))
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

    def test_lookup_handles_irregular_forms(self):
        for w, lemma in (('went', 'go'), ('bought', 'buy'), ('mice', 'mouse'), ('taught', 'teach'), ('were', 'be'), ('are', 'be'), ('geese', 'goose')):
            self.assertEqual(nx.lookup(w)['lemma'], lemma, w)
        for w in ('left', 'found', 'saw'):  # also words of their own: they keep their own entries
            self.assertEqual(nx.lookup(w)['lemma'], w)
        self.assertEqual(nx.easiest_rank('went'), nx.easiest_rank('go'))

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

    def test_a_word_saved_today_is_first_reviewed_tomorrow(self):
        # the owner, 2026-11-26 (语流 B1): from tomorrow 00:00 Beijing time; saving it again keeps the card's schedule
        at = datetime.datetime(2026, 11, 26, 23, 30, tzinfo=nx.TZ).timestamp()
        with patch('next_service.time.time', return_value=at):
            card = nx.save_card(self.c, 1, {'text': 'ponder'})[0]['card']
        due = self.c.execute('SELECT due FROM next_cards WHERE id=?', (card['id'],)).fetchone()[0]
        self.assertEqual(due, datetime.datetime(2026, 11, 27, tzinfo=nx.TZ).timestamp())
        self.c.execute('UPDATE next_cards SET due=? WHERE id=?', (at - 60, card['id'])); self.c.commit()  # due again later on
        with patch('next_service.time.time', return_value=at + 3600):
            nx.save_card(self.c, 1, {'text': 'Ponder', 'meaning': '沉思'})
        self.assertEqual(self.c.execute('SELECT due FROM next_cards WHERE id=?', (card['id'],)).fetchone()[0], at - 60)

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
            c.execute('INSERT INTO users(username,password,storage_ok,terms_version) VALUES(?,?,1,?)', ('learner', app.password('correct horse battery'), __import__('privacy_service').CONSENT_VERSION))  # agreed to 数据存放在香港
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
        q = json.loads(self.call('/api/next/review')[1]); self.assertEqual((q['due'], q['new'], len(q['items'])), (0, 0, 0))  # saved today, reviewed from tomorrow
        self.assertEqual(json.loads(self.call('/api/next/home')[1])['level'], 'B2')
        self.assertEqual(self.call('/api/next/nothing')[0], 404)

    def test_the_word_index_for_the_phones_search_is_the_learners_own_words_in_one_go(self):
        # 语流 C1 (iOS 专属 7): the whole list at once, versioned; not the mistakes, saved sentences or sentence patterns
        self.assertEqual(self.call('/api/next/cards/index')[0], 401)
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': 'correct horse battery'})[0], 200)
        csrf = json.loads(self.call('/api/session')[1])['user']['csrf']
        self.assertEqual(self.call('/api/next/profile', {'level': 'B2', 'themes': ['science']}, csrf)[0], 200)
        long = '确认' * 30
        with app.db() as c:
            uid = c.execute("SELECT id FROM users WHERE username='learner'").fetchone()[0]
            for k, (text, kind, meaning, source) in enumerate([('confirm', 'word', 'v. 确认, 证实；批准', 'book'), ('make up for', 'phrase', '弥补', ''),
                                                               ('lengthy', 'word', long, 'book'), ('q:1', 'word', '阅读理解错题', 'mistake'),
                                                               ('I wish I could go.', 'sentence', '我希望我能去。', ''), ('so … that', 'phrase', '句型｜例：so tired that…', '')]):
                c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,kind,source,created,due) VALUES(?,?,?,?,?,?,?,?)',
                          (uid, text, text.lower(), meaning, kind, source, 1000 + k, 0))
            c.commit()
        st, body = self.call('/api/next/cards/index'); got = json.loads(body)
        self.assertEqual(st, 200)
        self.assertEqual([(w['text'], w['zh']) for w in got['words']], [('lengthy', '确认' * 19 + '确…'), ('make up for', '弥补'), ('confirm', 'v. 确认, 证实')])
        self.assertTrue(all(isinstance(w['id'], int) for w in got['words']))
        self.assertEqual(json.loads(self.call('/api/next/cards/index?v=' + got['v'])[1]), {'v': got['v'], 'same': True})  # unchanged: no list
        self.assertEqual(self.call('/api/next/cards', {'text': 'ponder'}, csrf)[0], 200)
        again = json.loads(self.call('/api/next/cards/index?v=' + got['v'])[1])
        self.assertNotEqual(again['v'], got['v']); self.assertEqual(again['words'][0]['text'], 'ponder')

    def test_home_carries_the_session_so_the_page_starts_with_one_request(self):
        guest = json.loads(self.call('/api/next/home?level=A2')[1])
        self.assertEqual(guest['session']['user'], None); self.assertEqual(guest['level'], 'A2')
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': 'correct horse battery'})[0], 200)
        # The page asks before it knows who is signed in, so it sends the guest's level: signed in, that is ignored.
        member = json.loads(self.call('/api/next/home?level=A2&themes=science')[1])
        session = json.loads(self.call('/api/session')[1])
        self.assertEqual(member['session'], session); self.assertEqual(member['session']['user']['username'], 'learner')
        self.assertEqual(member['level'], json.loads(self.call('/api/next/home')[1])['level'])
        self.assertEqual(self.call('/api/next/profile', {'level': 'C1', 'themes': ['work']}, session['user']['csrf'])[0], 200)
        member = json.loads(self.call('/api/next/home?level=A2&themes=science')[1])
        self.assertEqual((member['level'], member['profile']['themes']), ('C1', ['work']))

    def test_versioned_script_and_styles_are_cached_for_a_year_everything_else_is_checked(self):
        def cache(path):
            with urllib.request.urlopen(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', timeout=10) as r:
                return r.headers['Cache-Control']
        v = app.asset_version()
        self.assertIn(f'/next.js?v={v}'.encode(), self.call('/')[1])
        for name in ('next.js', 'next.css'):
            self.assertEqual(cache(f'/{name}?v={v}'), 'public, max-age=31536000, immutable', name)
            self.assertEqual(cache(f'/{name}?v=0000000000'), 'no-cache', name)  # an old page's version: today's file, checked again
            self.assertEqual(cache(f'/{name}'), 'no-cache', name)
        # the page itself opens from the browser's copy at once and is fetched again in the background (iPhone WeChat
        # has no service worker); the service worker and the manifest are checked every time
        self.assertEqual(cache('/'), app.PAGE_CACHE)
        self.assertIn('stale-while-revalidate', app.PAGE_CACHE)
        for path in ('/sw.js', '/manifest.webmanifest'):
            self.assertEqual(cache(path), 'no-cache', path)

    def test_app_files_calendar_and_audio_aliases(self):
        for path in ('/sw.js', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png'):
            self.assertEqual(self.call(path)[0], 200, path)
        self.assertIn(b'"start_url": "/"', self.call('/manifest.webmanifest')[1])
        s, body = self.call('/api/next/vocab/reminder.ics?hour=7')
        self.assertEqual(s, 200); self.assertIn(b'RRULE:FREQ=DAILY', body)
        self.assertEqual(self.call('/api/next/vocab/reminder.ics?hour=x')[0], 200)  # falls back to 20:00
        self.assertEqual(self.call('/audio/words/us/../index.json')[0], 404)
        self.assertEqual(self.call('/audio/words/zz/w000.mp4')[0], 404)
        self.assertEqual(self.call('/api/next/shadow', {'pack': 'x'})[0], 401)


class NextGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'g.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
                                           'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'): self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def pack_with(self, node):
        for r in self.c.execute('SELECT id, content FROM lab_packs WHERE owner IS NULL'):
            p = json.loads(r['content'])
            if node in p.get('grammar', []) and p.get('knowledge'):
                return p
        self.skipTest('no material for ' + node)

    def test_new_grammar_points_have_a_page_four_questions_and_real_sentences(self):
        import grammar_more as gm, content_subskills as cs
        self.assertEqual(len(gm.NODES_MORE), 26)
        self.assertEqual([a for a in cs.audit(self.c) if a['issues']], [])  # every page, guided item and question bank checks out
        with_sentences = 0
        for n in gm.NODES_MORE:
            page, code = nx.node(self.c, None, n['id'], 'B1')
            self.assertEqual(code, 200)
            self.assertEqual(page['page']['status'], 'ready', n['id']); self.assertEqual(len(page['practice']), 4, n['id'])
            self.assertTrue(all('answer' not in q for q in page['practice']))  # answers stay on the server
            with_sentences += bool(page['examples'])
        self.assertGreaterEqual(with_sentences, 22)  # found in the materials' own text

    def test_finder_tags_clear_forms_and_leaves_lookalikes_alone(self):
        import grammar_more as gm
        cases = {
            'The letter was written by a student.': 'voice-basic', 'The road is being repaired this week.': 'voice-tenses',
            'By the time we arrived, the film had already started.': 'tense-past-perfect', 'My sister, who lives in Hangzhou, is a nurse.': 'clause-nondefining',
            'Never have I seen such a beautiful sunset.': 'emph-inversion', 'It was in 2019 that we first met.': 'emph-cleft',
            'It was so cold that the lake froze.': 'link-purpose', 'She must have missed the train.': 'modal-past',
            'Having finished the report, he went for lunch.': 'nonfinite-clause', 'I wish I knew the answer to that.': 'subjunctive-wish',
            'She is interested in starting a business.': 'prep-pattern', 'We had our kitchen painted last spring.': 'voice-causative'}
        for sentence, point in cases.items():
            self.assertIn(point, gm.find(sentence), sentence)
        not_cases = {'She is interested in art and music.': 'voice-basic', 'We used to live near the sea.': 'prep-pattern',
                     'During the long winter, we read a lot.': 'nonfinite-clause', 'It is important that you rest.': 'emph-cleft',
                     'She had a long day at work.': 'tense-past-perfect', 'This is rather than a guess.': 'compare-basic'}
        for sentence, point in not_cases.items():
            self.assertNotIn(point, gm.find(sentence), sentence)

    def test_practice_on_a_point_page_is_evidence_and_wrong_answers_go_to_the_mistake_book(self):
        qs = nx.practice(self.c, 'voice-basic')
        right = {r['id']: r['answer'] for r in self.c.execute("SELECT id, answer FROM questions WHERE node='voice-basic'")}
        guest, code = nx.node_answer(self.c, None, {'question': qs[0]['id'], 'choice': right[qs[0]['id']]})
        self.assertEqual(code, 200); self.assertTrue(guest['correct']); self.assertNotIn('status', guest)  # a guest is told, nothing stored
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events WHERE node=?', ('voice-basic',)).fetchone()[0], 0)
        wrong = (right[qs[0]['id']] + 1) % len(qs[0]['options'])
        r, _ = nx.node_answer(self.c, 1, {'question': qs[0]['id'], 'choice': wrong})
        self.assertFalse(r['correct']); self.assertEqual(r['status'], 'watch')
        card = self.c.execute("SELECT kind, node, source FROM next_cards WHERE user_id=1 AND norm=?", (f"gq:{qs[0]['id']}",)).fetchone()
        self.assertEqual((card['kind'], card['node'], card['source']), ('question', 'voice-basic', 'mistake'))
        r, _ = nx.node_answer(self.c, 1, {'question': qs[1]['id'], 'choice': right[qs[1]['id']]})
        self.assertTrue(r['correct']); self.assertEqual(r['status'], 'solid')
        self.assertEqual(nx.node_answer(self.c, 1, {'question': 999999, 'choice': 0})[1], 404)
        self.assertEqual(nx.node_answer(self.c, 1, {'question': qs[1]['id'], 'choice': 9})[1], 400)

    def test_a_point_got_wrong_becomes_a_short_step_in_todays_plan_and_stays_ticked(self):
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': ['work'], 'minutes': 15})
        self.assertNotIn('grammar', [s['key'] for s in nx.home(self.c, 1)['path']['steps']])
        qs = nx.practice(self.c, 'modal-obligation')
        answers = {r['id']: r['answer'] for r in self.c.execute("SELECT id, answer FROM questions WHERE node='modal-obligation'")}
        nx.node_answer(self.c, 1, {'question': qs[0]['id'], 'choice': (answers[qs[0]['id']] + 1) % 4})
        step = next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'grammar')
        self.assertEqual((step['href'], step['done']), ('#/mix', False)); self.assertIn('必须、禁止', step['title'])
        for q in qs[1:4]:  # a round's worth answered today: the step is done, whatever the score
            nx.node_answer(self.c, 1, {'question': q['id'], 'choice': answers[q['id']]})
        step = next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'grammar')
        self.assertEqual((step['href'], step['done']), ('#/mix', True))

    def test_read_step_shows_points_found_in_the_text(self):
        p = next(p for _, p in nx._public_packs(self.c) if 'voice-basic' in nx._found(p))
        m, code = nx.material(self.c, None, p['id'])
        self.assertEqual(code, 200)
        found = [k for k in m['notes'] if k['node'] in __import__('grammar_more').BY_ID]
        self.assertTrue(1 <= len(found) <= 2)
        self.assertTrue(all(k['quote'] in p['body'] for k in found))

    def test_graph_has_44_points_in_13_topics_and_reading_lights_nodes(self):
        g = nx.graph(self.c, 1)
        self.assertEqual(len(g['topics']), 13); self.assertEqual(sum(len(t['nodes']) for t in g['topics']), 44)
        self.assertEqual(g['summary']['untouched'], 44)
        self.assertTrue(all(n['level'] in ('A2', 'B1', 'B2', 'C1') for t in g['topics'] for n in t['nodes']))
        p = self.pack_with('tense-past')
        nx.mark(self.c, 1, p['id'], 'read')
        st = nx.graph_states(self.c, 1)
        self.assertEqual(st['tense-past']['status'], 'met')
        nx.mark(self.c, 1, p['id'], 'output')
        self.assertEqual(nx.graph_states(self.c, 1)['tense-past']['status'], 'used')
        self.assertEqual(nx.graph_states(self.c, 2)['tense-past']['status'], 'untouched')

    def test_node_detail_lists_examples_materials_and_neighbours(self):
        out, s = nx.node(self.c, None, 'subjunctive-past', 'B2')
        self.assertEqual(s, 200); self.assertTrue(out['examples']); self.assertTrue(out['materials'])
        self.assertTrue(all(e['quote'] for e in out['examples']))
        self.assertEqual(nx.node(self.c, None, 'nope')[1], 404)

    def test_rewrite_flags_map_to_graph_and_steer_recommendations(self):
        p = self.pack_with('subjunctive-past')
        nx.save_profile(self.c, 1, {'level': 'B2'})
        reply = dict(REWRITE); reply['changes'] = [dict(REWRITE['changes'][0], node='subjunctive-past')]; reply['used_well'] = ['clause-relative', 'bogus']
        with patch('chat_service.request_model', return_value=(json.dumps(reply), 'stop')):
            out, s = nx.rewrite(self.c, 1, {'pack': p['id'], 'text': 'If I left earlier I would catch the bus.', 'request_id': 'next-rw-g001'})
            self.assertEqual(s, 200)
            self.assertEqual(out['result']['changes'][0]['node'], 'subjunctive-past')
            self.assertEqual([n['id'] for n in out['result']['used_well']], ['clause-relative'])
            nx.rewrite(self.c, 1, {'pack': p['id'], 'text': 'If I left earlier I would catch the bus.', 'request_id': 'next-rw-g001'})
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_node_notes WHERE user_id=1 AND kind='flag'").fetchone()[0], 1)
        self.assertEqual(nx.graph_states(self.c, 1)['subjunctive-past']['status'], 'watch')
        h = nx.home(self.c, 1)
        self.assertIn('subjunctive-past', [w['id'] for w in h['graph']['watch']])
        self.assertTrue(any('虚拟' in r or '过去事实' in r for x in h['today'] for r in x.get('reasons', [])) or
                        any('subjunctive-past' in x['grammar'] for x in h['today']))

    def test_saved_expression_reappearing_is_a_recommendation_reason(self):
        nx.save_profile(self.c, 1, {'level': 'B1'})
        first = nx.home(self.c, 1)['today'][2]
        body = json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (first['id'],)).fetchone()[0])['body']
        word = max(nx.WORD.findall(body), key=len)
        nx.save_card(self.c, 1, {'text': word})
        top = nx.home(self.c, 1)['today']
        self.assertTrue(any(word in r for x in top for r in x['reasons']))

    def test_explain_is_grounded_cached_and_limited_to_material_sentences(self):
        p = self.pack_with('clause-relative')
        sentence = nx.sentences(p['body'])[0]
        good = {'translation': '中文', 'structure': '主干', 'points': [{'text': sentence.split()[0], 'note': '讲解', 'node': 'clause-relative'}, {'text': 'x', 'note': 'y', 'node': 'bad-node'}],
                'pattern': {'frame': 'A so much as B', 'example': 'Not luck so much as practice.'}}
        with patch('chat_service.request_model', return_value=(json.dumps(good), 'stop')) as model:
            out, s = nx.explain(self.c, 1, {'pack': p['id'], 'sentence': sentence, 'request_id': 'next-ex-0001'})
            self.assertEqual(s, 200); self.assertFalse(out['cached'])
            self.assertEqual(out['result']['points'][0]['node_title'], nx.nodes_meta(self.c)['clause-relative']['title'])
            self.assertIsNone(out['result']['points'][1]['node'])
            again, _ = nx.explain(self.c, 2, {'pack': p['id'], 'sentence': sentence, 'request_id': 'next-ex-0002'})
            self.assertTrue(again['cached']); self.assertEqual(model.call_count, 1)
        self.assertEqual(nx.explain(self.c, 1, {'pack': p['id'], 'sentence': 'Not in the text at all.', 'request_id': 'next-ex-0003'})[1], 400)


class NextAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'); self.p.start()
        self.audio = Path(self.tmp.name) / 'audio'
        self.a = patch.object(nx, 'AUDIO_DIR', self.audio); self.a.start()
        nx._AUDIO.update(mtime=None, index={})
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,storage_ok,terms_version) VALUES(?,?,1,?)', ('learner', app.password('correct horse battery'), __import__('privacy_service').CONSENT_VERSION))  # agreed to 数据存放在香港
        self.pid = 'v5-science-b2-noise-cancelling'
        (self.audio / 'uk-m').mkdir(parents=True)
        (self.audio / 'uk-m' / (self.pid + '.m4a')).write_bytes(bytes(range(256)) * 4)
        (self.audio / 'uk-m' / (self.pid + '.json')).write_text('{"v":1,"sentences":[]}')
        (self.audio / 'index.json').write_text(json.dumps({self.pid: ['uk-m', 'bogus']}))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.a.stop(); self.p.stop(); self.tmp.cleanup()

    def get(self, path, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r: return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)

    def test_material_lists_available_voices_and_meta_lists_all(self):
        with app.db() as c:
            m, _ = nx.material(c, None, self.pid, 'B2')
            self.assertEqual(m['audio']['voices'], ['uk-m']); self.assertGreater(m['audio']['version'], 0)
            other = nx.home(c, None, 'A2')['today'][0]['id']
            self.assertEqual(nx.material(c, None, other, 'A2')[0]['audio']['voices'], [])
        self.assertEqual([v['id'] for v in nx.meta()['voices']], ['us-f', 'us-m', 'uk-f', 'uk-m'])

    def test_audio_is_served_with_ranges_and_paths_are_validated(self):
        s, body, h = self.get(f'/audio/uk-m/{self.pid}.m4a')
        self.assertEqual((s, len(body), h['Accept-Ranges'], h['Content-Type']), (200, 1024, 'bytes', 'audio/mp4'))
        s, body, h = self.get(f'/audio/uk-m/{self.pid}.m4a', {'Range': 'bytes=100-199'})
        self.assertEqual((s, len(body), h['Content-Range']), (206, 100, 'bytes 100-199/1024')); self.assertEqual(body[0], 100)
        s, body, h = self.get(f'/audio/uk-m/{self.pid}.m4a', {'Range': 'bytes=-24'})
        self.assertEqual((s, len(body)), (206, 24))
        self.assertEqual(self.get(f'/audio/uk-m/{self.pid}.m4a', {'Range': 'bytes=5000-'})[0], 416)
        self.assertEqual(self.get(f'/audio/uk-m/{self.pid}.json')[0], 200)
        for bad in (f'/audio/us-f/{self.pid}.m4a', '/audio/uk-m/../app.py', '/audio/uk-m/x.py', '/audio/evil/a.m4a', f'/audio/uk-m/{self.pid}.wav'):
            self.assertEqual(self.get(bad)[0], 404, bad)

    def test_voice_preference_is_saved_with_profile(self):
        with app.db() as c:
            self.assertEqual(nx.set_voice(c, 1, {'voice': 'xx'})[1], 400)
            nx.save_profile(c, 1, {'level': 'B1'})
            self.assertEqual(nx.profile(c, 1)['voice'], 'us-f')
            self.assertEqual(nx.set_voice(c, 1, {'voice': 'uk-f'})[1], 200)
            self.assertEqual(nx.profile(c, 1)['voice'], 'uk-f')
            nx.save_profile(c, 1, {'level': 'B2'})
            self.assertEqual(nx.profile(c, 1)['voice'], 'uk-f')

    def test_the_look_of_today_is_kept_with_the_account(self):
        with app.db() as c:
            self.assertEqual(nx.set_today_view(c, 1, {'view': 'cards'})[1], 400)  # no profile yet: nothing to keep it on
            nx.save_profile(c, 1, {'level': 'B1'})
            self.assertEqual(nx.profile(c, 1)['today_view'], 'list')  # 列表 by default (the user, 2026-11-26)
            self.assertEqual(nx.set_today_view(c, 1, {'view': 'grid'})[1], 400)
            st = nx.post(c, 1, '/api/next/today-view', {'view': 'cards'})
            self.assertEqual((st[1], st[0]['today_view']), (200, 'cards'))
            nx.save_profile(c, 1, {'level': 'B2'})  # other settings saved later keep it
            self.assertEqual(nx.profile(c, 1)['today_view'], 'cards')
            # 调整顺序: 今天的计划 first by default; the learner's order kept, every block once
            self.assertEqual(nx.profile(c, 1)['today_order'], ['plan', 'week', 'line', 'mine', 'news', 'extra'])
            order = ['week', 'line', 'plan', 'mine', 'extra', 'news']
            self.assertEqual(nx.set_today_view(c, 1, {'order': order})[0]['today_order'], order)
            self.assertEqual(nx.profile(c, 1)['today_view'], 'cards')  # the look stays
            for bad in (['plan', 'plan', 'line', 'mine', 'news', 'extra'], ['plan', 'week'], 'plan', ['plan', 'week', 'line', 'mine', 'news', 'radar']):
                self.assertEqual(nx.set_today_view(c, 1, {'order': bad})[1], 400, bad)
            self.assertEqual(nx.profile(c, 1)['today_order'], order)
            # a block added later (here 我的材料, saved before it was there): it goes in where the default has it
            self.assertEqual(nx._today_order('["week", "plan", "line", "news", "extra"]'), ['week', 'plan', 'line', 'mine', 'news', 'extra'])
            self.assertEqual(nx._today_order('not json'), list(nx.TODAY_KEYS))

    def test_accent_is_kept_with_the_account(self):
        with app.db() as c:
            nx.save_profile(c, 1, {'level': 'B1'})
            self.assertEqual(nx.profile(c, 1)['accent'], 'green')  # 配色 A by default
            self.assertEqual(nx.set_accent(c, 1, {'accent': 'purple'})[1], 400)
            self.assertEqual(nx.set_accent(c, 1, {'accent': 'indigo'}), ({'accent': 'indigo'}, 200))
            self.assertEqual(nx.profile(c, 1)['accent'], 'indigo')
            nx.save_profile(c, 1, {'level': 'B2'})  # other settings saved later keep it
            self.assertEqual(nx.profile(c, 1)['accent'], 'indigo')
            self.assertEqual(nx.post(c, 1, '/api/next/accent', {'accent': 'green'}), ({'accent': 'green'}, 200))  # the route


if __name__ == '__main__':
    unittest.main()


class AssetVersionTests(unittest.TestCase):
    def test_shell_and_service_worker_carry_the_same_content_version(self):
        import re as _re
        html, sw = app.shell_file('next.html').decode(), app.shell_file('sw.js').decode()
        v = _re.search(r'/next\.js\?v=([0-9a-f]{10})', html).group(1)
        self.assertIn(f'/next.css?v={v}', html); self.assertIn(f"flow-shell-{v}", sw); self.assertIn(f'/next.js?v={v}', sw)
        self.assertNotIn('__ASSET__', html + sw)
        self.assertEqual(app.shell_file('survey.js'), (Path(app.ROOT) / 'public' / 'survey.js').read_bytes())  # other files untouched
        import slim  # next.js and next.css go out slimmed (tests/test_slim.py)
        self.assertEqual(app.shell_file('next.js'), slim.js((Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')).encode())


    def test_the_service_worker_asks_the_server_for_the_page_past_the_browsers_copy(self):
        """The browser may keep the page to open at once (app.PAGE_CACHE); the service worker must not install or keep
        that old copy, or a phone with it would get a new release one opening later than before."""
        import re as _re
        sw = app.shell_file('sw.js').decode()
        self.assertRegex(sw, r"u === '/' \? new Request\(u, \{ cache: 'no-cache' \}\)")  # installing a release
        nav = sw[sw.index("req.mode === 'navigate'"):]
        self.assertRegex(nav[:nav.index('respondWith')], r"fetch\(req\.url, \{ cache: 'no-cache'")  # the copy for next time
        self.assertFalse(_re.search(r"addAll\(SHELL_FILES\)", sw))

class FrontSourceTests(unittest.TestCase):
    def test_next_js_and_css_are_built_from_their_parts(self):
        """flow/public/src/next/* are the source; next.js and next.css must be their exact join (tools/build_front.py)."""
        import subprocess
        tool = Path(__file__).resolve().parents[2] / 'tools' / 'build_front.py'
        r = subprocess.run([sys.executable, str(tool), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)


class DictionaryBuildTests(unittest.TestCase):
    def test_prebuilt_dictionary_matches_its_sources(self):
        """corpus_data/dictionary-flow.json must be what tools/build_dictionary.py makes from the sources."""
        import subprocess
        tool = Path(__file__).resolve().parents[2] / 'tools' / 'build_dictionary.py'
        r = subprocess.run([sys.executable, str(tool), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)

    def test_restart_does_not_reparse_the_reference_list(self):
        import reference_service as ref
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        with patch.object(app, 'DB', Path(tmp.name) / 'r.db'):
            app.init()
            with patch.object(ref, 'dataset', side_effect=AssertionError('parsed again')):
                app.init()  # same file already imported: no parse


class ServerErrorTests(NextAudioTests):
    """An unexpected exception is recorded (path only), counted in /api/deploy-status and listed for the operator."""

    def test_crash_is_recorded_without_the_query_and_shown(self):
        import ops_errors, flow_admin
        with patch.object(nx, 'get', side_effect=RuntimeError('boom in get')):
            st, body, _ = self.get('/api/next/home?level=B1&secret=abc')
        self.assertEqual(st, 500); self.assertNotIn(b'boom', body)  # the learner sees the friendly message only
        with app.db() as c:
            row = c.execute('SELECT method, path, kind, message, trace FROM server_errors').fetchone()
            self.assertEqual((row['method'], row['path'], row['kind'], row['message']), ('GET', '/api/next/home', 'RuntimeError', 'boom in get'))
            self.assertIn('Traceback', row['trace'])
            with patch.object(nx, 'get', side_effect=RuntimeError('boom in get')):
                self.get('/api/next/home?level=A2')
            rec = ops_errors.recent(c)
            self.assertEqual((rec['total'], len(rec['groups']), rec['groups'][0]['count']), (2, 1, 2))  # same place: one group
        st, body, _ = self.get('/api/deploy-status')
        live = json.loads(body)['live']
        self.assertEqual(live['errors_24h'], 2); self.assertIn('uptime_min', live)
