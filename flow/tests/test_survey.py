import unittest, tempfile, sys, json, os, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, survey_service as survey, flow_admin


def full_answers():
    out = {}
    for q in survey.questions():
        if q['type'] == 'single': out[q['id']] = q['options'][0]
        elif q['type'] == 'multi': out[q['id']] = q['options'][:q.get('max') or 2]
        elif q['type'] == 'matrix': out[q['id']] = {r: 4 for r in q['rows']}
        elif q['type'] == 'text': out[q['id']] = '希望能用真实材料练口语'
    return out


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'survey.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_DATA_DIR': self.tmp.name, 'FLOW_SURVEY_SALT': ''}); self.env.start()
        app.init(); self.c = app.db()

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def send(self, answers=None, address='203.0.113.5', seconds=90, **extra):
        return survey.submit(self.c, {'answers': answers if answers is not None else full_answers(), 'seconds': seconds, **extra}, address)

    def test_valid_submission_is_stored_without_any_identity(self):
        out, status = self.send()
        self.assertEqual((status, out), (200, {'ok': True}))
        row = self.c.execute('SELECT * FROM survey_responses').fetchone()
        stored = ' '.join(str(v) for v in tuple(row))
        self.assertNotIn('203.0.113.5', stored)
        cols = {r[1] for r in self.c.execute('PRAGMA table_info(survey_responses)')}
        self.assertFalse(cols & {'ip', 'user_id', 'user_agent', 'address', 'email'})
        key = self.c.execute('SELECT key FROM survey_limits').fetchone()[0]
        self.assertNotIn('203.0.113.5', key); self.assertEqual(len(key), 64)

    def test_validation_rejects_bad_or_incomplete_answers(self):
        a = full_answers(); del a['role']
        self.assertEqual(self.send(a)[1], 400)
        a = full_answers(); a['goals'] = survey.SURVEY['sections'][0]['questions'][2]['options'][:4]
        self.assertIn('最多选 3 项', self.send(a)[0]['error'])
        a = full_answers(); a['role'] = '外星人'
        self.assertEqual(self.send(a)[1], 400)
        a = full_answers(); a['features'] = {r: 9 for r in a['features']}
        self.assertEqual(self.send(a)[1], 400)
        a = full_answers(); a['unknown'] = 'x'
        self.assertIn('刷新', self.send(a)[0]['error'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM survey_responses').fetchone()[0], 0)

    def test_optional_text_may_be_blank_and_long_text_is_trimmed(self):
        a = full_answers(); a['dislike'] = '   '; a['ideal'] = 'x' * 5000; del a['flow_note']
        self.assertEqual(self.send(a)[1], 200)
        stored = json.loads(self.c.execute('SELECT answers FROM survey_responses').fetchone()[0])
        self.assertNotIn('dislike', stored); self.assertEqual(len(stored['ideal']), survey.TEXT_MAX)

    def test_bots_and_rushed_submissions_are_not_stored(self):
        self.assertEqual(self.send(website='http://spam')[0], {'ok': True})
        self.assertEqual(self.send(seconds=3)[1], 400)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM survey_responses').fetchone()[0], 0)

    def test_per_client_daily_limit_and_old_keys_expire(self):
        for _ in range(survey.DAILY_PER_CLIENT): self.assertEqual(self.send()[1], 200)
        self.assertEqual(self.send()[1], 429)
        self.assertEqual(self.send(address='198.51.100.7')[1], 200)
        later = time.time() + 3 * 86400
        self.assertEqual(survey.submit(self.c, {'answers': full_answers(), 'seconds': 60}, '203.0.113.5', now=later)[1], 200)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM survey_limits').fetchone()[0], 1)

    def test_summary_counts_filters_and_hidden_responses(self):
        self.send()
        a = full_answers(); a['role'] = '在职'; a['features'] = {r: 2 for r in a['features']}
        self.send(a, address='198.51.100.9')
        s = survey.summary(self.c)
        self.assertEqual(s['total'], 2)
        role = next(q for q in s['questions'] if q['id'] == 'role')
        self.assertEqual({o['label']: o['count'] for o in role['options']}['在职'], 1)
        feat = next(q for q in s['questions'] if q['id'] == 'features')
        self.assertEqual(feat['rows'][0]['average'], 3.0)
        self.assertEqual(survey.summary(self.c, {'role': '在职'})['total'], 1)
        rid = self.c.execute('SELECT MAX(id) FROM survey_responses').fetchone()[0]
        survey.set_hidden(self.c, rid, True)
        self.assertEqual(survey.summary(self.c)['total'], 1); self.assertEqual(survey.summary(self.c)['hidden'], 1)
        self.assertEqual(survey.responses(self.c)['total'], 2)

    def test_csv_export_neutralises_formulas(self):
        a = full_answers(); a['ideal'] = '=HYPERLINK("http://x")'
        self.send(a)
        text = survey.export_csv(self.c).decode('utf-8-sig')
        self.assertIn('features:每天 10 分钟的小任务', text.splitlines()[0])
        self.assertIn("'=HYPERLINK", text); self.assertNotIn(',=HYPERLINK', text)


class SurveyHttpTests(unittest.TestCase):
    """Public endpoints on the learner site and the loopback operator API."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'http.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_DATA_DIR': self.tmp.name, 'FLOW_ADMIN_PORT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '100', 'FLOW_AI_DAILY_LIMIT': '2000'}); self.env.start()
        app.init()
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler); threading.Thread(target=self.admin.serve_forever, daemon=True).start()

    def tearDown(self):
        self.site.shutdown(); self.admin.shutdown(); self.site.server_close(); self.admin.server_close()
        self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def call(self, server, path, data=None, headers=None):
        url = f'http://127.0.0.1:{server.server_address[1]}{path}'
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r: return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)

    def test_public_survey_flow_without_login(self):
        status, body, headers = self.call(self.site, '/survey')
        self.assertEqual(status, 200); self.assertIn(b'/survey.js', body); self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        for asset in ('/survey.js', '/survey.css'): self.assertEqual(self.call(self.site, asset)[0], 200)
        status, body, _ = self.call(self.site, '/api/survey'); self.assertEqual(json.loads(body)['id'], survey.SURVEY_ID)
        status, body, _ = self.call(self.site, '/api/survey', {'answers': full_answers(), 'seconds': 45}, {'CF-Connecting-IP': '192.0.2.44'})
        self.assertEqual((status, json.loads(body)), (200, {'ok': True}))
        self.assertEqual(self.call(self.site, '/api/survey', {'answers': full_answers(), 'seconds': 45}, {'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_operator_api_reads_and_requires_marker_for_changes(self):
        self.call(self.site, '/api/survey', {'answers': full_answers(), 'seconds': 45})
        status, body, _ = self.call(self.admin, '/flow/api/overview'); o = json.loads(body)
        self.assertEqual(status, 200); self.assertEqual(o['survey_responses'], 1); self.assertEqual(o['ai']['user_limit'], 100)
        s = json.loads(self.call(self.admin, '/flow/api/survey/summary?role=' + urllib.request.quote('中学生'))[1]); self.assertEqual(s['total'], 1)
        r = json.loads(self.call(self.admin, '/flow/api/survey/responses?page=1')[1]); rid = r['items'][0]['id']
        status, body, headers = self.call(self.admin, '/flow/api/survey/export.csv')
        self.assertEqual(status, 200); self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(self.call(self.admin, '/flow/api/survey/hide', {'id': rid})[0], 403)
        self.assertEqual(self.call(self.admin, '/flow/api/survey/hide', {'id': rid}, {'X-Requested-With': 'xmc'})[0], 200)
        self.assertEqual(json.loads(self.call(self.admin, '/flow/api/survey/summary')[1])['total'], 0)
        self.assertEqual(self.call(self.admin, '/api/session')[0], 404)
        self.assertEqual(self.call(self.site, '/flow/api/overview')[0], 404)


if __name__ == '__main__':
    unittest.main()
