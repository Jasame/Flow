"""Server voice (tts_service, r28): a sentence the browser used to say is made by CosyVoice through the gateway once per
voice, stored, and served to everyone after; guests get stored ones only; caps per learner and per day; overnight the
fixed sentences are made while the server is idle; nothing happens without FLOW_TTS_MODEL."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, tts_service as tts  # noqa: E402

MP3 = b'ID3' + b'\x00' * 400


class Gateway:
    """A stand-in for the xmc-api gateway's /v1/audio/speech: answers mp3 bytes (or a set status) and records requests."""
    def __init__(self):
        self.seen, self.status = [], 200
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.seen.append({'path': self.path, 'auth': self.headers.get('Authorization'), **body})
                if outer.status != 200:
                    self.send_response(outer.status); self.send_header('Content-Length', '0'); self.end_headers(); return
                self.send_response(200); self.send_header('Content-Type', 'audio/mpeg'); self.send_header('Content-Length', str(len(MP3)))
                self.end_headers(); self.wfile.write(MP3)
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.srv.server_address[1]}/v1/chat/completions'

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class TtsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.gw = Gateway()
        self.patches = [patch.object(app, 'DB', root / 't.db'), patch.object(nx, 'AUDIO_DIR', root / 'audio'),
                        patch.dict(os.environ, {'FLOW_AI_URL': self.gw.url, 'FLOW_AI_KEY': 'flow-key', 'FLOW_TTS_MODEL': 'flow-tts',
                                                'FLOW_TTS_USER_CHARS': '400', 'FLOW_TTS_DAILY_CHARS': '1000', 'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init(); self.c = app.db()
        for n in ('lin', 'mei'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()

    def tearDown(self):
        self.c.close()
        for p in reversed(self.patches):
            p.stop()
        self.gw.close(); self.tmp.cleanup()


class ServerVoiceTests(TtsCase):
    def test_off_without_a_model_and_the_gateway_address(self):
        with patch.dict(os.environ, {'FLOW_TTS_MODEL': ''}):
            self.assertFalse(tts.enabled())
            self.assertEqual(tts.post(self.c, 1, {'text': 'Hello there.'})[1], 503)
        self.assertTrue(tts.enabled())
        self.assertTrue(tts.speech_url().endswith('/v1/audio/speech'))
        with patch.dict(os.environ, {'FLOW_AI_URL': 'https://api.example.test', 'FLOW_TTS_URL': ''}):
            self.assertEqual(tts.speech_url(), 'https://api.example.test/v1/audio/speech')

    def test_made_once_per_voice_then_served_to_everyone(self):
        text = "Hi there!  What can I get for you today?"
        body, st = tts.post(self.c, 1, {'text': text, 'voice': 'uk-f'})
        self.assertEqual((st, body['made']), (200, True))
        self.assertRegex(body['url'], r'^/audio/tts/uk-f/[0-9a-f]{32}\.mp3$')
        g = self.gw.seen[0]
        self.assertEqual((g['path'], g['auth'], g['model'], g['voice'], g['input'], g['response_format']),
                         ('/v1/audio/speech', 'Bearer flow-key', 'flow-tts', 'loongemily_v3', 'Hi there! What can I get for you today?', 'mp3'))
        f = tts.file('uk-f', body['url'].rsplit('/', 1)[1])
        self.assertEqual(f.read_bytes(), MP3); self.assertEqual(oct(f.stat().st_mode & 0o777), '0o644')
        again, _ = tts.post(self.c, 2, {'text': text + ' ', 'voice': 'uk-f'})  # another learner, the same sentence
        guest, _ = tts.post(self.c, None, {'text': text, 'voice': 'uk-f'})
        self.assertEqual((again['url'], again['made'], guest['url']), (body['url'], False, body['url']))
        self.assertEqual(len(self.gw.seen), 1)  # made once
        other, _ = tts.post(self.c, 1, {'text': text, 'voice': 'us-m'})
        self.assertNotEqual(other['url'], body['url']); self.assertEqual(self.gw.seen[-1]['voice'], 'loongandy_v3')
        self.assertEqual({v: tts.VOICES[v] for v in ('us-f', 'us-m', 'uk-f', 'uk-m')},
                         {'us-f': 'loongabby_v3', 'us-m': 'loongandy_v3', 'uk-f': 'loongemily_v3', 'uk-m': 'loongeric_v3'})

    def test_another_model_or_upstream_voice_never_gets_the_old_file(self):
        # both sites share the folder: a site on another model (or a remapped voice) must make its own files
        text = 'The same sentence, another model.'
        first, _ = tts.post(self.c, 1, {'text': text})
        with patch.dict(os.environ, {'FLOW_TTS_MODEL': 'flow-tts-2'}):
            second, _ = tts.post(self.c, 1, {'text': text})
        with patch.dict(tts.VOICES, {'us-f': 'longxiaochun_v3'}):
            third, _ = tts.post(self.c, 1, {'text': text})
        self.assertEqual(len({first['url'], second['url'], third['url']}), 3)
        self.assertTrue(first['made'] and second['made'] and third['made'])
        self.assertEqual([g['model'] for g in self.gw.seen], ['flow-tts', 'flow-tts-2', 'flow-tts'])
        again, _ = tts.post(self.c, 2, {'text': text})
        self.assertEqual((again['url'], again['made']), (first['url'], False))  # back on flow-tts: the first file

    def test_a_smaller_sample_rate_is_asked_for_and_makes_its_own_files(self):
        first, _ = tts.post(self.c, 1, {'text': 'A smaller file, please.'})
        with patch.dict(os.environ, {'FLOW_TTS_SAMPLE_RATE': '22050'}):
            second, _ = tts.post(self.c, 1, {'text': 'A smaller file, please.'})
        with patch.dict(os.environ, {'FLOW_TTS_SAMPLE_RATE': '44100'}):  # not one the gateway takes: its default
            self.assertEqual(tts.sample_rate(), 0)
        self.assertNotEqual(first['url'], second['url'])
        self.assertEqual([g.get('sample_rate') for g in self.gw.seen], [None, 22050])

    def test_guests_get_stored_sentences_only(self):
        body, st = tts.post(self.c, None, {'text': 'Nothing stored yet.'})
        self.assertEqual((st, body['code']), (404, 'guest')); self.assertEqual(self.gw.seen, [])

    def test_bad_text_and_unknown_voice(self):
        for t in ('', '   ', '你好世界', '1234 5678', 'x' * (tts.MAX_CHARS + 1)):
            self.assertEqual(tts.post(self.c, 1, {'text': t})[1], 400, t[:10])
        body, st = tts.post(self.c, 1, {'text': 'Hello there.', 'voice': 'zz-x'})
        self.assertEqual(st, 200); self.assertIn('/us-f/', body['url'])  # the default voice

    def test_the_day_stop_holds_new_ai_voice_but_stored_audio_plays(self):  # ¥10 stop (the owner: 「¥5 提醒，¥10 硬停」)
        import ai_routes
        self.assertEqual(tts.post(self.c, 1, {'text': 'Stored before the stop.'})[1], 200)
        with patch.object(ai_routes, 'day_full', lambda c=None, now=None: True):
            body, st = tts.post(self.c, 1, {'text': 'A new sentence after the stop.'})
            self.assertEqual((st, body['code']), (429, 'ai_day_full')); self.assertIn('早上 8 点', body['error'])
            self.assertEqual(tts.post(self.c, 1, {'text': 'Stored before the stop.'})[1], 200)
        self.assertEqual(len(self.gw.seen), 1)

    def test_caps_per_learner_and_per_day(self):
        line = 'This sentence is a little longer than the others, on purpose. ' * 3  # ~190 characters
        self.assertEqual(tts.post(self.c, 1, {'text': line})[1], 200)
        self.assertEqual(tts.post(self.c, 1, {'text': line + 'Again.'})[1], 200)
        body, st = tts.post(self.c, 1, {'text': line + 'Third.'})
        self.assertEqual((st, body['code']), (429, 'cap'))  # learner 1 over 400 characters today
        self.assertEqual(tts.post(self.c, 1, {'text': line})[1], 200)  # a stored sentence costs nothing
        for k in range(2):
            self.assertEqual(tts.post(self.c, 2, {'text': line + f'Other {k}.'})[1], 200)
        self.assertEqual(tts.post(self.c, 2, {'text': 'Short one.'})[1], 200)
        made = len(self.gw.seen)
        self.assertEqual(tts.post(self.c, 2, {'text': line[:300] + 'Over the site cap.'})[1], 429)  # the site's 1,000
        self.assertEqual(len(self.gw.seen), made)
        site = self.c.execute('SELECT chars, files FROM tts_usage WHERE who=0').fetchone()
        self.assertEqual(site['files'], made); self.assertLessEqual(site['chars'], 1000)

    def test_a_gateway_failure_stores_and_charges_nothing(self):
        self.gw.status = 502
        body, st = tts.post(self.c, 1, {'text': 'The gateway is down.'})
        self.assertEqual((st, body['code']), (502, 'gateway'))
        self.assertIsNone(self.c.execute('SELECT 1 FROM tts_usage').fetchone())
        self.assertFalse((nx.AUDIO_DIR / 'tts').exists() and any((nx.AUDIO_DIR / 'tts').rglob('*.mp3')))
        row = self.c.execute("SELECT ok, prompt FROM ai_calls WHERE kind='tts'").fetchone()
        self.assertEqual(tuple(row), (0, len('The gateway is down.')))  # in the console's costs, as a failed call

    def test_each_sentence_made_is_a_row_in_the_ai_costs(self):
        tts.post(self.c, 1, {'text': 'Counted in the costs.', 'voice': 'uk-m'})
        tts.post(self.c, 2, {'text': 'Counted in the costs.', 'voice': 'uk-m'})  # stored: no second call, no second row
        rows = [tuple(r) for r in self.c.execute("SELECT kind, service, model, served, ok, prompt FROM ai_calls WHERE kind='tts'")]
        self.assertEqual(rows, [('tts', 'tts', 'flow-tts', 'cosyvoice-v3-flash', 1, len('Counted in the costs.'))])

    def test_the_nightly_prewarm_waits_when_the_days_ai_budget_is_spent(self):
        with patch('ai_routes.over_budget', return_value=True):
            self.assertEqual(tts.prewarm(self.c, budget=10 ** 6), {'status': 'over-budget'})
        self.assertEqual(self.gw.seen, [])

    def test_a_folder_it_cannot_write_is_found_before_the_gateway_is_paid(self):
        # 内测版, 2026-11-24: systemd ProtectSystem=strict kept the folder read-only; every tap was charged, then lost.
        d = nx.AUDIO_DIR / 'tts' / 'us-f'
        d.mkdir(parents=True)
        d.chmod(0o555)
        try:
            if os.access(d, os.W_OK):
                self.skipTest('running as root: a mode bit cannot make the folder read-only')
            with patch('builtins.print') as log:
                body, st = tts.post(self.c, 1, {'text': 'A read-only folder.'})
                tts.post(self.c, 1, {'text': 'Another sentence.'})
                night = tts.prewarm(self.c, budget=10 ** 6)
        finally:
            d.chmod(0o755)
        self.assertEqual((st, body['code']), (503, 'store'))  # 503: the page uses the browser voice from now on
        self.assertEqual(self.gw.seen, [])
        self.assertIsNone(self.c.execute('SELECT 1 FROM tts_usage').fetchone())
        self.assertEqual(sum('tts: cannot write' in str(a) for call in log.call_args_list for a in call.args), 1)  # said once
        self.assertEqual(night['status'], 'store')

    def test_a_file_that_cannot_be_saved_is_reported_as_such(self):
        with patch.object(tts, '_store', side_effect=OSError(30, 'Read-only file system')), patch('builtins.print'):
            body, st = tts.post(self.c, 1, {'text': 'The disk said no.'})
        self.assertEqual((st, body['code']), (503, 'store'))
        self.assertIsNone(self.c.execute('SELECT 1 FROM tts_usage').fetchone())

    def test_stored_names_are_checked(self):
        self.assertIsNone(tts.file('us-f', '../../t.db')); self.assertIsNone(tts.file('xx', 'a' * 32 + '.mp3'))
        self.assertIsNone(tts.file('us-f', 'a' * 32 + '.mp3'))  # well-formed, not stored


class RouteTests(TtsCase):
    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        super().tearDown()

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', **(headers or {})}, method='GET' if body is None else 'POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_the_page_learns_it_is_on_and_the_file_is_served_with_ranges(self):
        st, body, _ = self.call('/api/session')
        self.assertTrue(json.loads(body)['tts'])
        u, made = tts.ensure(self.c, 1, 'Served from here.', 'us-f')
        st, body, h = self.call(u, headers={'Range': 'bytes=0-2'})
        self.assertEqual((st, body, h['Content-Type']), (206, b'ID3', 'audio/mpeg'))
        st, body, _ = self.call('/api/next/tts', {'text': 'Served from here.', 'voice': 'us-f'})  # a guest: stored, so given
        self.assertEqual((st, json.loads(body)['url']), (200, u))
        self.assertEqual(self.call('/api/next/tts', {'text': 'Not stored for guests.'})[0], 404)
        self.assertEqual(self.call('/audio/tts/us-f/' + 'b' * 32 + '.mp3')[0], 404)


class NightTests(TtsCase):
    def test_fixed_sentences_come_from_the_content(self):
        import ielts_speaking as ie, daily_line as dl
        fixed = tts.fixed_texts()
        self.assertIn(tts.norm(next(iter(ie.PART1.values()))[2][0]), fixed)
        self.assertIn(dl.QUOTES[0][1].replace(' / ', ', '), fixed)
        self.assertFalse([t for t in fixed if '…' in t])  # templates with a gap are left to a tap
        self.assertEqual(len(fixed), len(set(fixed)))

    def test_prewarm_makes_them_within_the_budget_once(self):
        fixed = tts.fixed_texts()
        budget = sum(len(t) for t in fixed[:5]) + 1
        r = tts.prewarm(self.c, budget=budget)
        self.assertEqual((r['status'], r['made']), ('budget', 5))
        self.assertEqual(self.c.execute('SELECT chars FROM tts_usage WHERE who=-1').fetchone()[0], budget - 1)
        import ai_routes
        kinds = {r[0] for r in ai_routes._db().execute("SELECT kind FROM ai_calls WHERE service='tts'")} if ai_routes._db() else {'tts-prewarm'}
        self.assertEqual(kinds, {'tts-prewarm'})  # its own name in the costs; never counted for the learners' ¥10 stop
        self.assertIsNone(self.c.execute('SELECT 1 FROM tts_usage WHERE who=0').fetchone())  # not the learners' share
        r = tts.prewarm(self.c, budget=10 ** 6)
        self.assertEqual((r['status'], r['made'], r['stored']), ('done', len(fixed) - 5, 5))
        self.assertEqual(len(self.gw.seen), len(fixed))
        self.assertEqual(tts.prewarm(self.c, budget=10 ** 6)['made'], 0)  # all stored: nothing asked again

    def test_voices_in_use_follow_active_learners(self):
        self.assertEqual(tts.voices_in_use(self.c), ['us-f'])
        nx.save_profile(self.c, 2, {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 15})
        self.c.execute("UPDATE next_profiles SET voice='uk-m' WHERE user_id=2")
        self.c.execute("INSERT INTO next_progress(user_id,pack,step,created) VALUES(2,'v5-x','read',?)", (time.time(),)); self.c.commit()
        self.assertEqual(tts.voices_in_use(self.c), ['us-f', 'uk-m'])

    def test_tick_runs_at_night_once(self):
        started = []
        with patch.object(tts.threading, 'Thread', lambda target, args, daemon: type('T', (), {'start': lambda s: started.append(args)})()):
            tts._NIGHT['day'] = None
            noon = 1_795_000_000  # some day, 12:xx in China (UTC+8) or not: find 03:30 and 12:30 of that day
            import datetime
            day = datetime.datetime.fromtimestamp(noon, nx.TZ).replace(hour=3, minute=30, second=0)
            tts.tick(app.db, day.replace(hour=12).timestamp()); self.assertEqual(started, [])
            tts.tick(app.db, day.timestamp()); tts.tick(app.db, day.timestamp() + 600)
            self.assertEqual(len(started), 1)
            with patch.dict(os.environ, {'FLOW_TTS_MODEL': ''}):
                tts._NIGHT['day'] = None; tts.tick(app.db, day.timestamp()); self.assertEqual(len(started), 1)

    def test_one_off_sentences_go_after_thirty_days_the_fixed_ones_stay(self):
        fixed = tts.fixed_texts()[0]
        tts.ensure(self.c, 1, fixed, 'us-f'); tts.ensure(self.c, 1, 'A reply nobody will hear again.', 'us-f')
        tts.ensure(self.c, 1, 'A reply from this morning.', 'uk-m')
        old = time.time() - 31 * 86400
        for t, v in ((fixed, 'us-f'), ('A reply nobody will hear again.', 'us-f')):
            os.utime(nx.AUDIO_DIR / 'tts' / v / tts.name_of(t, v), (old, old))
        self.assertEqual(tts.prune(), {'removed': 1, 'kept': 2})
        self.assertIsNotNone(tts.file('us-f', tts.name_of(fixed, 'us-f')))
        self.assertIsNone(tts.file('us-f', tts.name_of('A reply nobody will hear again.', 'us-f')))


class SoonTests(TtsCase):
    """声音接力: the AI's line is made in a thread while the reply travels to the page, counted against the learner."""

    def test_made_in_a_thread_and_then_found_by_the_page(self):
        t = tts.start(1, 'Sure thing. Hot or iced?', 'uk-f', wait=True)
        self.assertIsNotNone(t)
        self.assertEqual([g['voice'] for g in self.gw.seen], ['loongemily_v3'])
        self.assertEqual(self.c.execute('SELECT chars, files FROM tts_usage WHERE who=1').fetchone()[:], (24, 1))
        body, st = tts.post(self.c, 1, {'text': 'Sure thing. Hot or iced?', 'voice': 'uk-f'})
        self.assertEqual((st, body['made']), (200, False)); self.assertEqual(len(self.gw.seen), 1)  # the page's request: already made
        self.assertIsNone(tts.start(1, 'Sure thing. Hot or iced?', 'uk-f'))  # stored: nothing to do

    def test_nothing_happens_when_off_busy_or_without_a_connection(self):
        with patch.dict(os.environ, {'FLOW_TTS_MODEL': ''}):
            self.assertIsNone(tts.start(1, 'Off tonight.', 'us-f'))
        with patch.object(tts, 'CONNECT', None):
            self.assertIsNone(tts.start(1, 'No connection.', 'us-f'))
        self.assertIsNone(tts.start(1, 'An unknown voice.', 'xx-y'))
        taken = [tts._SOON.acquire(blocking=False) for _ in range(4)]
        try:
            self.assertIsNone(tts.start(1, 'Four already being made.', 'us-f'))
        finally:
            [tts._SOON.release() for ok in taken if ok]
        self.assertEqual(self.gw.seen, [])

    def test_a_failure_in_the_thread_is_left_to_the_page(self):
        self.gw.status = 502
        tts.start(1, 'The gateway is down.', 'us-f', wait=True)
        self.assertIsNone(self.c.execute('SELECT 1 FROM tts_usage').fetchone())
        self.assertEqual(tts._SOON._value, 4)  # the slot is given back



class OwnTests(RouteTests):
    """没有录音的整篇伴读 (owner, 2026-11-25): an imported article read sentence by sentence in the server voice. Its files are
    its owner's only (data/tts-own/<id>, never listed, served to their session), with an import share of their own, and
    imports give way first when the site's day is running out."""
    TEXT = ('The library opens early on weekdays. Students meet there before their first class. Some of them read quietly '
            'in the corner. Others work on group projects at the long tables. By noon most seats are taken.')

    def setUp(self):
        super().setUp()
        self.data = Path(self.tmp.name) / 'data'; self.data.mkdir()
        self.pd = patch.object(app, 'DATA', self.data); self.pd.start()
        import import_service as im
        with patch.object(tts, 'start_pack'):
            r, _ = im.save(self.c, 1, {'title': '图书馆', 'text': self.TEXT})
        self.pid = r['id']
        self.first = nx.sentences(self.TEXT)[0]

    def tearDown(self):
        self.pd.stop()
        super().tearDown()

    def session(self, uid):
        tok = 'tok-%d-%s' % (uid, '0' * 20)
        self.c.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)', (tok, uid, 'csrf', time.time() + 3600)); self.c.commit()
        return {'Cookie': 'flow_session=' + tok}

    def test_a_sentence_of_my_article_is_kept_for_me_only(self):
        body, st = tts.post(self.c, 1, {'text': self.first, 'voice': 'uk-f', 'pack': self.pid})
        self.assertEqual((st, body['made']), (200, True))
        self.assertRegex(body['url'], r'^/audio/own/uk-f/[0-9a-f]{32}\.mp3$')
        name = body['url'].rsplit('/', 1)[1]
        self.assertTrue((self.data / 'tts-own' / '1' / 'uk-f' / name).is_file())
        self.assertIsNone(tts.file('uk-f', name))  # not in the shared folder
        self.assertEqual(self.call(body['url'], headers=self.session(1))[0], 200)
        st2, _, h = self.call(body['url'], headers=self.session(1))
        self.assertIn('private', h['Cache-Control'])
        self.assertEqual(self.call(body['url'], headers=self.session(2))[0], 404)  # another learner
        self.assertEqual(self.call(body['url'])[0], 404)  # signed out
        self.assertEqual(self.c.execute('SELECT chars FROM tts_import WHERE who=1').fetchone()[0], len(self.first))

    def test_only_its_owner_and_only_its_sentences(self):
        self.assertEqual(tts.post(self.c, 2, {'text': self.first, 'pack': self.pid})[1], 404)
        self.assertEqual(tts.post(self.c, None, {'text': self.first, 'pack': self.pid})[1], 404)
        self.assertEqual(tts.post(self.c, 1, {'text': 'Something else entirely.', 'pack': self.pid})[1], 400)
        self.assertEqual(self.gw.seen, [])

    def test_the_import_share_and_the_sites_day(self):
        with patch.dict(os.environ, {'FLOW_TTS_IMPORT_CHARS': str(len(self.first))}):
            self.assertEqual(tts.post(self.c, 1, {'text': self.first, 'pack': self.pid})[1], 200)
            body, st = tts.post(self.c, 1, {'text': nx.sentences(self.TEXT)[1], 'pack': self.pid})
        self.assertEqual((st, body['code']), (429, 'import_cap'))
        tts._add(self.c, 0, 590, 1); self.c.commit()  # the site (cap 1000 here) has used 59 % + this sentence > 60 %
        body, st = tts.post(self.c, 1, {'text': nx.sentences(self.TEXT)[2], 'pack': self.pid})
        self.assertEqual((st, body['code']), (429, 'busy'))
        self.assertEqual(tts.post(self.c, 1, {'text': 'An AI reply still has its voice.'})[1], 200)  # replies keep the rest

    def test_the_console_sets_the_caps(self):
        import console_ops
        (self.data / 'console-settings.json').write_text(json.dumps({'FLOW_TTS_IMPORT_CHARS': 5, 'FLOW_TTS_IMPORT_PERCENT': 80}))
        console_ops._CACHE.update(path=None, mtime=None, data={})
        self.assertEqual((tts.cap('FLOW_TTS_IMPORT_CHARS'), tts.cap('FLOW_TTS_IMPORT_PERCENT'), tts.cap('FLOW_TTS_USER_CHARS')), (5, 80, 400))
        self.assertEqual(console_ops.limits()['tts']['tts_import_chars_source'], 'console')
        r, st = console_ops.set_limits({'tts_import_chars': 12000, 'tts_import_percent': 101}, 'test')
        self.assertEqual(st, 400)
        r, st = console_ops.set_limits({'tts_import_chars': 12000}, 'test')
        self.assertEqual((st, r['tts']['tts_import_chars']), (200, 12000))
        console_ops._CACHE.update(path=None, mtime=None, data={})

    def test_what_is_made_already_and_the_background_after_importing(self):
        texts = nx.sentences(self.TEXT)
        self.assertEqual(tts.have(self.c, 1, {'pack': self.pid, 'voice': 'us-f', 'texts': texts})[0]['urls'], [None] * len(texts))
        with patch.object(tts, 'CONNECT', app.db):
            tts.start_pack(1, self.pid, wait=True, pause=0)
        urls = tts.have(self.c, 1, {'pack': self.pid, 'voice': 'us-f', 'texts': texts})[0]['urls']
        self.assertTrue(all(u and u.startswith('/audio/own/us-f/') for u in urls))
        self.assertEqual(tts.have(self.c, 2, {'pack': self.pid, 'voice': 'us-f', 'texts': texts})[1], 404)
        self.assertEqual(len(self.gw.seen), len(texts))

    def test_deleting_the_article_or_the_account_takes_the_voice_with_it(self):
        import import_service as im
        tts.post(self.c, 1, {'text': self.first, 'pack': self.pid})
        folder = self.data / 'tts-own' / '1' / 'us-f'
        self.assertEqual(len(list(folder.glob('*.mp3'))), 1)
        im.delete(self.c, 1, {'id': self.pid})
        self.assertEqual(list(folder.glob('*.mp3')), [])
        (folder / ('a' * 32 + '.mp3')).write_bytes(MP3)
        tts.forget(1)
        self.assertFalse((self.data / 'tts-own' / '1').exists())

    def test_the_days_hot_article_is_made_when_it_appears(self):
        body = 'Cities are planting more trees. Shade cools the streets in summer. Residents say the parks feel calmer.'
        self.c.execute('INSERT INTO lab_packs VALUES(?,?,?,?,?)', ('daily-2026-11-25', None, 'daily', json.dumps({'body': body}), time.time())); self.c.commit()
        self.assertEqual(tts.daily_texts(self.c), ('daily-2026-11-25', nx.sentences(body)))
        tts._DAILY.update(done=None, busy=False)
        tts._daily_tick(app.db, inline=True)
        self.assertEqual(len(self.gw.seen), 3)
        self.assertTrue(all(tts.file('us-f', tts.name_of(t, 'us-f')) for t in nx.sentences(body)))
        self.assertEqual(self.c.execute('SELECT chars FROM tts_usage WHERE who=-1').fetchone()[0], sum(map(len, nx.sentences(body))))
        tts._daily_tick(app.db, inline=True); self.assertEqual(len(self.gw.seen), 3)  # done: not again

if __name__ == '__main__':
    unittest.main()
