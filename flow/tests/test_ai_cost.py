"""AI routes, cost and budget (ai_routes.py): each task asks the gateway model name its route names (flow-text for
Gemini, a 百炼 line such as flow-text-qwen-plus), always without thinking, JSON on 百炼; every call is written down with its
tokens, cache hits, the model that answered and any fallback; costs are list price × the platform's discount, with
DeepSeek-on-百炼's night half price and Gemini's 2027 price; the daily budget mails 管理员 once per level and stops batch
work, never learners; the console switches routes (logged), shows the costs, samples shared
content but never what a learner wrote, and can throw a bad piece of content away; a role-play's opening is asked once;
the nightly check runs once, at night, on 语流 only."""
import datetime, io, json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_routes, chat_service as cs, console_ops, flow_admin, next_service as nx, output_service as out  # noqa: E402

GATEWAY = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://gw.test/v1/chat/completions', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-3.8-flash',
           'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_USER_DAILY_LIMIT': '100', 'FLOW_AI_DAILY_LIMIT': '2000', 'FLOW_COOKIE_SECURE': '0'}
BOSS, INTERN = 'boss@example.com', 'intern@example.com'
TZ = datetime.timezone(datetime.timedelta(hours=8))


def at(y, m, d, h, mi=0):
    return datetime.datetime(y, m, d, h, mi, tzinfo=TZ).timestamp()


class Reply:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.headers = {'Content-Type': 'application/json'}

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *a):
        return False


def gateway(script, sent):
    """urlopen stand-in for the gateway: script maps a model name to outcomes (a reply dict or an exception) in order."""
    def urlopen(req, timeout=None):
        body = json.loads(req.data)
        sent.append(body)
        outcome = script[body['model']].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Reply(outcome)
    return urlopen


def answer(text, model, usage=None):
    d = {'model': model, 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}
    if usage:
        d['usage'] = usage
    return d


def http(code):
    return urllib.error.HTTPError('https://gw.test', code, 'err', None, None)


class Site(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {**GATEWAY, 'FLOW_ADMIN_EMAILS': BOSS}), patch('ai_stream.active', return_value=False), patch('time.sleep')]
        for p in self.patches:
            p.start()
        for k in ('FLOW_AI_ROUTES', 'FLOW_TEXT_AI_URL', 'FLOW_TEXT_AI_KEY', 'FLOW_CHANNEL', 'FLOW_MAIL_OUTBOX'):
            os.environ.pop(k, None)
        os.environ['FLOW_AI_CHOICES'] = 'flow-text-qwen-plus,flow-text-qwen-flash,flow-text-ds-flash'  # what the gateway would offer
        ai_routes._CHOICES.update(at=time.time(), names=[])  # never ask a real gateway
        app.init()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def ask(self, kind, script, messages=None):
        sent = []
        with patch('urllib.request.urlopen', gateway(script, sent)), ai_routes.task(kind):
            try:
                got = cs.request_model(messages or [{'role': 'user', 'content': '只输出 JSON'}])
            except Exception as e:  # noqa: BLE001
                got = e
        return got, sent

    def calls(self):
        with app.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM ai_calls ORDER BY id')]

    def route(self, kind, r):
        console_ops.save_settings({'ai_routes': {**(console_ops.settings().get('ai_routes') or {}), kind: r}}, 'test')


class RouteTests(Site):
    def test_every_task_stays_on_gemini_until_a_route_is_set(self):
        got, sent = self.ask('next-rewrite', {'flow-text': [answer('{"a":1}', 'gemini-3.8-flash')]})
        self.assertEqual(got[0], '{"a":1}')
        self.assertEqual(sent[0]['model'], 'flow-text')
        self.assertIs(sent[0]['enable_thinking'], False)  # for a 百炼 model as the gateway's backup line
        self.assertNotIn('response_format', sent[0])
        self.assertEqual({v['route'] for v in ai_routes.routes().values()}, {'flow-text'})

    def test_a_task_on_a_bailian_line_asks_it_without_thinking_for_json(self):
        self.route('next-rewrite', 'flow-text-qwen-plus')
        got, sent = self.ask('next-rewrite', {'flow-text-qwen-plus': [answer('{"a":1}', 'qwen-plus')]})
        self.assertEqual(sent[0]['model'], 'flow-text-qwen-plus')
        self.assertEqual((sent[0]['enable_thinking'], sent[0]['response_format']), (False, {'type': 'json_object'}))
        self.assertNotIn('thinking', sent[0])
        _, sent = self.ask('next-explain', {'flow-text': [answer('{}', 'gemini-3.8-flash')]})
        self.assertEqual(sent[0]['model'], 'flow-text')  # other tasks keep their own route
        self.route('chat', 'flow-text-qwen-plus')
        _, sent = self.ask('chat', {'flow-text-qwen-plus': [answer('hi', 'qwen-plus')]})
        self.assertNotIn('response_format', sent[0])  # free text

    def test_the_server_default_and_all_tasks_at_once(self):
        with patch.dict(os.environ, {'FLOW_AI_ROUTES': json.dumps({'*': 'flow-text-qwen-flash', 'next-essay': 'flow-text-qwen-plus'})}):
            self.assertEqual(ai_routes.route('next-rewrite'), 'flow-text-qwen-flash')
            self.assertEqual(ai_routes.route('next-essay'), 'flow-text-qwen-plus')
            self.assertEqual(ai_routes.route('fill-examples'), 'flow-text-qwen-flash')  # the batch follows AI 例句
            self.route('next-rewrite', 'flow-text')
            self.assertEqual(ai_routes.routes()['next-rewrite'], {'route': 'flow-text', 'source': 'console'})
        body, status, changes = ai_routes.set_routes({'routes': {'*': 'flow-text-qwen-plus'}}, 'boss')
        self.assertEqual(status, 200)
        self.assertEqual(console_ops.settings()['ai_routes'], {'*': 'flow-text-qwen-plus'})  # per-task exceptions cleared
        self.assertIn(('next-rewrite', 'flow-text', 'flow-text-qwen-plus'), changes)
        for bad in ({'routes': {'next-rewrite': 'flow-gpt'}}, {'routes': {'nope': 'flow-text-qwen-plus'}}, {'routes': {}}):
            self.assertEqual(ai_routes.set_routes(bad, 'boss')[1], 400)  # only names the gateway has

    def test_the_console_offers_the_gateways_flow_names(self):
        ai_routes._CHOICES.update(at=0)
        sent = []

        def urlopen(req, timeout=None):
            sent.append((req.full_url, req.headers.get('Authorization')))
            return Reply({'data': [{'id': 'flow-text'}, {'id': 'flow-text-qwen37-plus'}, {'id': 'flow-eval-qwen37-plus'}, {'id': 'flow-batch-qwen37-flash'},
                                   {'id': 'gemini-3.8-flash'}, {'id': 'qwen-local-256k'}]})
        with patch('urllib.request.urlopen', urlopen), patch.dict(os.environ, {'FLOW_AI_CHOICES': ''}):
            names = [c['name'] for c in ai_routes.choices()]
        self.assertEqual(sent, [('https://gw.test/v1/models', 'Bearer k')])
        self.assertEqual(names, ['flow-text', 'flow-text-qwen37-plus'])  # learners' names only, the default first
        self.assertEqual(ai_routes.set_routes({'routes': {'next-rewrite': 'flow-text-qwen37-plus'}}, 'boss')[1], 200)
        self.assertEqual(ai_routes.set_routes({'routes': {'next-rewrite': 'flow-eval-qwen37-plus'}}, 'boss')[1], 400)

    def test_development_and_batch_calls_take_their_own_gateway_names(self):
        ai_routes._CHOICES.update(at=time.time(), names=['flow-text-qwen37-plus', 'flow-eval-qwen37-plus', 'flow-batch-qwen37-flash', 'flow-text-qwen37-flash'])
        self.route('next-rewrite', 'flow-text-qwen37-plus')
        self.route('next-examples', 'flow-text-qwen37-flash')
        self.assertEqual(ai_routes.route('next-rewrite'), 'flow-text-qwen37-plus')  # learners: the enterprise account
        with patch.dict(os.environ, {'FLOW_AI_LANE': 'eval'}):
            self.assertEqual(ai_routes.route('next-rewrite'), 'flow-eval-qwen37-plus')  # ai_eval / the nightly check
            self.assertEqual(ai_routes.route('next-examples'), 'flow-text-qwen37-flash')  # no flow-eval- name: the learners' one
        self.assertEqual(ai_routes.route('fill-examples'), 'flow-batch-qwen37-flash')  # 例句预生成
        self.assertEqual(ai_routes.route('next-examples'), 'flow-text-qwen37-flash')
        self.route('next-examples', 'flow-text')
        self.assertEqual(ai_routes.route('fill-examples'), 'flow-text')  # no plain flow-batch on the gateway: Gemini
        ai_routes._CHOICES['names'].append('flow-batch')
        self.assertEqual(ai_routes.route('fill-examples'), 'flow-batch')  # the owner's account, while learners stay on Gemini
        self.assertEqual(ai_routes.route('next-examples'), 'flow-text')
        ai_routes._CHOICES['names'].remove('flow-batch')
        _, sent = self.ask('fill-examples', {'flow-text': [answer('{}', 'gemini-3.8-flash')]})
        self.assertEqual(sent[0]['model'], 'flow-text')

    def test_a_bailian_line_failing_hands_over_to_the_main_model_even_when_refused(self):
        self.route('next-rewrite', 'flow-text-qwen-plus')
        for failure in (http(503), http(400), http(401)):
            got, sent = self.ask('next-rewrite', {'flow-text-qwen-plus': [failure], 'gemini-3.8-flash': [answer('{"ok":1}', 'gemini-3.8-flash')]})
            self.assertEqual(got[0], '{"ok":1}', failure.code)
            self.assertEqual([s['model'] for s in sent], ['flow-text-qwen-plus', 'gemini-3.8-flash'])
            self.assertNotIn('enable_thinking', sent[1])  # the main model gets the request as before
        got, sent = self.ask('next-rewrite', {'flow-text-qwen-plus': [http(413)], 'gemini-3.8-flash': [answer('never', 'x')]})
        self.assertIsInstance(got, urllib.error.HTTPError)  # too large: too large everywhere
        got, sent = self.ask('next-explain', {'flow-text': [http(400)], 'gemini-3.8-flash': [answer('never', 'x')]})
        self.assertIsInstance(got, urllib.error.HTTPError)  # flow-text refused: Gemini both times, not asked again

    def test_audio_never_takes_a_route(self):
        self.route('next-shadow', 'flow-text-qwen-plus')
        audio = {'mime_type': 'audio/webm', 'data': __import__('base64').b64encode(b'\x1aE\xdf\xa3' + b'0' * 4000).decode()}
        sent = []
        with patch('urllib.request.urlopen', gateway({'gemini-3.8-flash': [answer('heard', 'gemini-3.8-flash')]}, sent)), ai_routes.task('next-shadow'):
            cs.request_model([{'role': 'user', 'content': 'x'}], audio=audio)
        self.assertEqual(sent[0]['model'], 'gemini-3.8-flash')


class RecordTests(Site):
    def test_each_attempt_is_written_down_with_tokens_cache_and_the_model_that_answered(self):
        self.route('next-rewrite', 'flow-text-qwen-plus')
        use = {'prompt_tokens': 1500, 'completion_tokens': 400, 'prompt_tokens_details': {'cached_tokens': 1200}}
        self.ask('next-rewrite', {'flow-text-qwen-plus': [answer('{"a":1}', 'qwen-plus', use)]})
        self.ask('next-essay', {'flow-text': [http(502)], 'gemini-3.8-flash': [answer('{"b":2}', 'gemini-3.8-flash')]}, [{'role': 'user', 'content': '写作' * 50}])
        rows = self.calls()
        self.assertEqual([(r['kind'], r['service'], r['model'], r['served'], r['ok'], r['fallback']) for r in rows],
                         [('next-rewrite', 'text', 'flow-text-qwen-plus', 'qwen-plus', 1, 0),
                          ('next-essay', 'text', 'flow-text', '', 0, 0), ('next-essay', 'main', 'gemini-3.8-flash', 'gemini-3.8-flash', 1, 1)])
        self.assertEqual((rows[0]['prompt'], rows[0]['cached'], rows[0]['completion'], rows[0]['estimated']), (1500, 1200, 400, 0))
        self.assertEqual(rows[1]['status'], 502)
        self.assertEqual(rows[2]['estimated'], 1)  # the Gemini relay reports no usage: estimated from the text
        self.assertEqual(rows[2]['prompt'], 60)    # 100 汉字 × 0.6

    def test_the_gateway_backup_line_shows_as_backup(self):
        self.route('next-rewrite', 'flow-text-qwen-plus')
        for served in ('qwen-plus', 'qwen-plus', 'gemini-3.8-flash'):  # the last time 百炼 was down: the gateway's Gemini line answered
            self.ask('next-rewrite', {'flow-text-qwen-plus': [answer('{}', served)]})
        with app.db() as c:
            k = next(x for x in ai_routes.summary(c)['kinds'] if x['kind'] == 'next-rewrite')
        self.assertEqual((k['calls'], k['backup'], k['route']), (3, 1, 'flow-text-qwen-plus'))
        names = {c['name']: c['label'] for c in ai_routes.choices()}
        self.assertEqual(names['flow-text-qwen-plus'], '通义千问 Plus（不思考）（flow-text-qwen-plus）')  # named by what answers it


class CostTests(Site):
    def test_list_price_times_the_platforms_discount(self):
        noon = at(2026, 11, 23, 12)
        self.assertAlmostEqual(ai_routes.cost('qwen-plus-2025-12-01', noon, 1_000_000, 0, 1_000_000), (0.8 + 2.0) * 0.65)
        self.assertAlmostEqual(ai_routes.cost('qwen-flash', noon, 1_000_000, 1_000_000, 0), 0.03 * 0.65)  # all from the cache
        self.assertAlmostEqual(ai_routes.cost('gemini-3.8-flash', noon, 1_000_000, 0, 0), 5.33)  # no discount on Vertex
        self.assertEqual(ai_routes.cost('mystery-model', noon, 1_000_000, 0, 1_000_000), 0.0)
        self.assertEqual(ai_routes.price_of('deepseek-v4.1-flash-1017')['label'], 'DeepSeek V4.1 Flash（百炼）')

    def test_deepseek_on_bailian_is_half_price_at_night_and_gemini_doubles_in_2027(self):
        day, night = at(2026, 11, 23, 10), at(2026, 11, 23, 23)
        full = ai_routes.cost('deepseek-v4.1-flash', day, 1_000_000, 0, 1_000_000)
        self.assertAlmostEqual(full, 10.0 * 0.65)
        self.assertAlmostEqual(ai_routes.cost('deepseek-v4.1-flash', night, 1_000_000, 0, 1_000_000), full / 2)
        line = ai_routes.price_of('deepseek-v4.1-flash')
        self.assertEqual(ai_routes.next_quiet(day, line), at(2026, 11, 23, 22))
        self.assertEqual(ai_routes.next_quiet(night, line), night)
        self.assertEqual(ai_routes.next_quiet(day, ai_routes.price_of('qwen-plus')), day)  # Qwen has no busy hours
        g26, g27 = ai_routes.cost('gemini-3.8-flash', at(2026, 12, 31, 13), 1_000_000, 0, 0), ai_routes.cost('gemini-3.8-flash', at(2027, 1, 1, 13), 1_000_000, 0, 0)
        self.assertAlmostEqual(g27, 2 * g26, places=1)

    def test_the_discount_and_prices_are_set_in_the_console(self):
        noon = at(2026, 11, 23, 12)
        body, st = console_ops.set_ai_budget({'discounts': {'bailian': 0.6}}, 'boss')
        self.assertEqual((st, body['discounts']['bailian']), (200, 0.6))
        self.assertAlmostEqual(ai_routes.cost('qwen-plus', noon, 1_000_000, 0, 0), 0.8 * 0.6)
        self.assertEqual(console_ops.set_ai_budget({'discounts': {'bailian': 1.5}}, 'boss')[1], 400)
        body, st = console_ops.set_ai_budget({'prices': {'qwen-plus': {'in': 1, 'cached': 0.2, 'out': 4}, 'kimi-k3': {'in': 4, 'cached': 0.8, 'out': 16, 'platform': 'bailian'}}}, 'boss')
        self.assertEqual(st, 200)
        self.assertAlmostEqual(ai_routes.cost('qwen-plus', noon, 1_000_000, 0, 1_000_000), 5.0 * 0.6)
        self.assertAlmostEqual(ai_routes.cost('kimi-k3', noon, 1_000_000, 0, 0), 4 * 0.6)  # a model added by hand
        self.assertEqual(console_ops.set_ai_budget({'prices': {'qwen-plus': {'in': -1, 'cached': 0, 'out': 1}}}, 'boss')[1], 400)
        console_ops.set_ai_budget({'prices': {'qwen-plus': None}, 'discounts': {'bailian': None}}, 'boss')
        self.assertAlmostEqual(ai_routes.cost('qwen-plus', noon, 1_000_000, 0, 0), 0.8 * 0.65)


class BudgetTests(Site):
    def spend(self, yuan):
        with app.db() as c:  # gemini-priced output: 26.63 yuan a million
            c.execute("INSERT INTO ai_calls(ts,kind,service,model,served,ok,completion) VALUES(?,?,?,?,?,1,?)",
                      (time.time(), 'next-rewrite', 'text', 'flow-text', 'gemini-3.8-flash', int(yuan / 26.63 * 1e6)))

    def test_80_and_100_percent_mail_the_admins_once_a_day_and_stop_batch_work(self):
        outbox = Path(self.tmp.name) / 'outbox'
        with patch.dict(os.environ, {'FLOW_MAIL_OUTBOX': str(outbox)}):
            console_ops.set_ai_budget({'daily': 10}, 'boss')
            self.spend(5)
            with app.db() as c:
                self.assertEqual(ai_routes.check_budget(c), [])
                self.spend(3.5)
                self.assertEqual(ai_routes.check_budget(c), ['warn'])
                self.assertEqual(ai_routes.check_budget(c), [])  # once
                self.assertFalse(ai_routes.over_budget(c))
                self.spend(2)
                self.assertEqual(ai_routes.check_budget(c), ['over'])
                self.assertTrue(ai_routes.over_budget(c))
                self.assertEqual(ai_routes.check_budget(c), [])
            mails = sorted(outbox.iterdir())
            self.assertEqual(len(mails), 2)
            self.assertIn('To: ' + BOSS, mails[1].read_text())
            self.assertIn('超过今日预算', mails[1].read_text())

    def test_no_budget_no_mail(self):
        self.spend(500)
        with app.db() as c:
            self.assertEqual(ai_routes.check_budget(c), [])
            self.assertFalse(ai_routes.over_budget(c))

    def test_learners_are_not_stopped_by_the_budget(self):
        console_ops.set_ai_budget({'daily': 1}, 'boss')
        self.spend(5)
        got, _ = self.ask('next-rewrite', {'flow-text': [answer('{"a":1}', 'gemini-3.8-flash')]})
        self.assertEqual(got[0], '{"a":1}')


class DialogTests(Site):
    def test_the_opening_of_a_role_play_is_asked_once_for_everyone(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('a', 'x')); c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('b', 'x'))
            c.commit()
            ua, ub = [r[0] for r in c.execute('SELECT id FROM users ORDER BY id')]
            for u in (ua, ub):
                nx.save_profile(c, u, {'level': 'B1', 'goal': next(iter(nx.GOALS)), 'themes': [], 'minutes': 15})
            opening = json.dumps({'scene': '在火车上。', 'role': '乘客', 'reply': 'Hi there! Are those new headphones?'})
            sent = []
            with patch('urllib.request.urlopen', gateway({'flow-text': [answer(opening, 'gemini-3.8-flash')]}, sent)):
                r1, s1 = out.dialog(c, ua, {'pack': 'v5-science-b2-noise-cancelling', 'history': [], 'request_id': 'dlg-aaaaaaaaaaaa'})
                r2, s2 = out.dialog(c, ub, {'pack': 'v5-science-b2-noise-cancelling', 'history': [], 'request_id': 'dlg-bbbbbbbbbbbb'})
        self.assertEqual((s1, s2, len(sent)), (200, 200, 1))
        self.assertEqual(r2['result'], r1['result'])
        self.assertTrue(r2['cached'])


class NightlyTests(Site):
    def test_once_a_night_on_the_live_site_only(self):
        started = []
        with patch('subprocess.Popen', lambda cmd, **kw: started.append(cmd)):
            with app.db() as c:
                self.assertFalse(ai_routes.nightly(c, at(2026, 11, 24, 14)))  # daytime
                self.assertTrue(ai_routes.nightly(c, at(2026, 11, 24, 2, 30)))
                self.assertFalse(ai_routes.nightly(c, at(2026, 11, 24, 2, 35)))  # already running
                self.assertIn('--quick', started[0]); self.assertIn('--site-settings', started[0])
                (ai_routes.eval_dir() / 'running.json').unlink()
                (ai_routes.eval_dir() / '2026-11-24.json').write_text(json.dumps({'summary': {'passed': 15, 'total': 16}, 'items': []}))
                self.assertFalse(ai_routes.nightly(c, at(2026, 11, 24, 3)))  # done for today
                self.assertEqual(ai_routes.eval_reports()[0]['passed'], 15)
                with patch.dict(os.environ, {'FLOW_CHANNEL': 'beta'}):
                    self.assertFalse(ai_routes.nightly(c, at(2026, 11, 25, 2, 30)))
                console_ops.set_ai_budget({'nightly': False}, 'boss')
                self.assertFalse(ai_routes.nightly(c, at(2026, 11, 25, 2, 30)))
        self.assertEqual(len(started), 1)


class ConsoleTests(Site):
    def setUp(self):
        super().setUp()
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        threading.Thread(target=self.admin.serve_forever, daemon=True).start()

    def tearDown(self):
        self.admin.shutdown(); self.admin.server_close()
        super().tearDown()

    def console(self, path, data=None, email=BOSS):
        h = {'Cf-Access-Authenticated-User-Email': email, 'Content-Type': 'application/json'}
        if data is not None:
            h['X-Requested-With'] = 'xmc'
        req = urllib.request.Request(f'http://127.0.0.1:{self.admin.server_address[1]}/flow/api{path}',
                                     data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_routes_are_switched_by_a_manager_and_logged(self):
        st, body = self.console('/settings/ai-routes', {'routes': {'next-rewrite': 'flow-text-qwen-plus'}}, email=INTERN)
        self.assertEqual(st, 403)
        st, body = self.console('/settings/ai-routes', {'routes': {'next-rewrite': 'flow-text-qwen-plus'}})
        self.assertEqual((st, body['routes']['next-rewrite']['route']), (200, 'flow-text-qwen-plus'))
        with app.db() as c:
            log = c.execute("SELECT action, detail FROM flow_admin_log WHERE action='ai-routes'").fetchall()
        self.assertEqual([tuple(r) for r in log], [('ai-routes', '仿写批改：flow-text → flow-text-qwen-plus')])
        st, d = self.console('/ai?days=14', email=INTERN)
        self.assertEqual(st, 200)
        rw = next(k for k in d['costs']['kinds'] if k['kind'] == 'next-rewrite')
        self.assertEqual((rw['route'], rw['source']), ('flow-text-qwen-plus', 'console'))
        self.assertIn('flow-text-qwen-flash', [c['name'] for c in d['costs']['choices']])
        self.assertIn('budget', d['costs']); self.assertIn('evals', d); self.assertIn('quality', d)

    def test_budget_and_nightly_check_from_the_console(self):
        st, body = self.console('/settings/ai-budget', {'daily': 20, 'nightly': False})
        self.assertEqual((st, body['daily'], body['nightly']), (200, 20.0, False))
        self.assertEqual(self.console('/settings/ai-budget', {'daily': 'lots'})[0], 400)
        with app.db() as c:
            self.assertEqual(c.execute("SELECT detail FROM flow_admin_log WHERE action='ai-budget'").fetchone()[0], '每日预算 ¥20，每晚小评测关，百炼折扣 0.65')

    def test_samples_show_shared_content_never_a_learners_own_text_and_a_bad_one_can_go(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'x')); c.commit()
            uid = c.execute("SELECT id FROM users WHERE username='learner'").fetchone()[0]
            c.execute('INSERT INTO lab_packs VALUES(?,?,?,?,?)', ('imp-private', uid, 'import', json.dumps({'id': 'imp-private', 'title': '我的日记', 'body': 'My secret.'}), time.time()))
            good = {'translation': '翻译', 'structure': '', 'points': [{'text': 'x', 'note': 'y', 'node': None}], 'pattern': None}
            c.execute('INSERT INTO next_explains VALUES(?,?,?,?,?)', ('v5-science-b2-noise-cancelling', 'Human voices are a different story.', 'B1', json.dumps(good), time.time()))
            c.execute('INSERT INTO next_explains VALUES(?,?,?,?,?)', ('imp-private', 'My secret.', 'B1', json.dumps(good), time.time()))
            c.execute('INSERT INTO next_dialog_openers VALUES(?,?,?,?)', ('imp-private', 'B1', json.dumps({'scene': '日记', 'role': '', 'reply': 'Hi'}), time.time()))
            c.execute('INSERT INTO next_word_examples(norm,sentence,translation,created,sense) VALUES(?,?,?,?,?)',
                      ('perspective', 'Travel gave her a new perspective.', '旅行给了她新的看法。', time.time(), '看法'))
            c.execute("INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,fingerprint,status,result,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (uid, 'rq-aaaaaaaaaaaa', 'next-rewrite', 'p', 'writing', 'f', 'complete',
                       json.dumps({'verdict': 'minor', 'corrected': 'My very private sentence.', 'changes': [{}]}), time.time(), time.time()))
            c.commit()
        st, d = self.console('/ai/samples?kind=next-explain&n=10', email=INTERN)
        self.assertEqual(st, 200)
        self.assertEqual([x['source'] for x in d['items']], ['Human voices are a different story.'])
        st, d = self.console('/ai/samples?kind=next-dialog')
        self.assertEqual(d['items'], [])
        st, d = self.console('/ai/samples?kind=next-examples')
        self.assertEqual([(x['key'], x['output']['translation'], x['output']['sense']) for x in d['items']], [(['perspective'], '旅行给了她新的看法。', '看法')])
        self.assertEqual(self.console('/ai/samples/redo', {'kind': 'next-examples', 'key': ['perspective']})[0], 200)
        st, d = self.console('/ai')
        self.assertNotIn('My very private sentence', json.dumps(d, ensure_ascii=False))
        rw = next(q for q in d['quality'] if q['kind'] == 'next-rewrite')
        self.assertEqual(rw['done'], 1)
        key = ['v5-science-b2-noise-cancelling', 'Human voices are a different story.', 'B1']
        self.assertEqual(self.console('/ai/samples/redo', {'kind': 'next-explain', 'key': key}, email=INTERN)[0], 403)
        self.assertEqual(self.console('/ai/samples/redo', {'kind': 'next-explain', 'key': key})[0], 200)
        self.assertEqual(self.console('/ai/samples/redo', {'kind': 'next-explain', 'key': key})[0], 404)
        with app.db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM next_explains WHERE sentence=?', (key[1],)).fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM flow_admin_log WHERE action='ai-redo'").fetchone()[0], 2)


class EvalCommandTests(unittest.TestCase):
    def test_route_and_site_routes_reach_the_run(self):
        import ai_eval
        seen = {}

        def run(cases, kinds, quick=False):
            seen.update(routes=os.environ.get('FLOW_AI_ROUTES'), quick=quick, kinds=kinds)
            return {'summary': ai_eval.summarize([]), 'models': {'main': '', 'text': ''}, 'items': []}
        with tempfile.TemporaryDirectory() as d, patch.object(ai_eval, 'run', run), patch.dict(os.environ, GATEWAY), \
                patch('lab_service.ai_enabled', return_value=True):
            site = Path(d) / 'console-settings.json'
            site.write_text(json.dumps({'ai_routes': {'next-rewrite': 'flow-text-qwen-plus'}}))
            ai_eval.main(['--env-file', os.devnull, '--quick', '--site-settings', str(site)])
            self.assertEqual((json.loads(seen['routes']), seen['quick']), ({'next-rewrite': 'flow-text-qwen-plus'}, True))
            ai_eval.main(['--env-file', os.devnull, '--route', 'flow-text-qwen-plus', '--only', 'rewrite'])
            self.assertEqual((json.loads(seen['routes']), seen['kinds']), ({'*': 'flow-text-qwen-plus'}, ('rewrite',)))


if __name__ == '__main__':
    unittest.main()
