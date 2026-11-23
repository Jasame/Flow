"""The learning loop added in r13: ten questions per grammar point with spaced re-checks, the starting check,
exam practice, the serial story and the whole-plan calendar reminder."""
import unittest, tempfile, sys, json, os, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, grammar_bank as GB, exam_service as ex, vocab_service as vs

DAY = 86400


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'loop.db'); self.p.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'): self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def answers(self, node):
        return {r['id']: r['answer'] for r in self.c.execute('SELECT id, answer FROM questions WHERE node=?', (node,))}

    # ---------------- question bank ----------------

    def test_every_point_has_ten_questions_and_a_round_is_four_in_random_order_with_shuffled_options(self):
        counts = dict(self.c.execute("SELECT node, COUNT(*) FROM questions WHERE status='published' AND node IS NOT NULL GROUP BY node").fetchall())
        self.assertEqual(len(counts), 44); self.assertEqual(set(counts.values()), {10})
        stored = {r['id']: json.loads(r['options']) for r in self.c.execute("SELECT id, options FROM questions WHERE node='voice-basic'")}
        seen = set()
        for _ in range(12):
            rnd = nx.practice(self.c, 'voice-basic')
            self.assertEqual(len(rnd), 4); self.assertEqual(len({q['id'] for q in rnd}), 4)
            for q in rnd:
                self.assertNotIn('answer', q); self.assertEqual(sorted(q['map']), [0, 1, 2, 3])
                self.assertEqual(q['options'], [stored[q['id']][i] for i in q['map']])  # shown option j is stored option map[j]
                seen.add(q['id'])
        self.assertGreater(len(seen), 4)  # rounds draw from the whole pool
        # Stored answers are spread over the four positions, not always B.
        pos = [r[0] for r in self.c.execute("SELECT answer FROM questions WHERE node IS NOT NULL")]
        self.assertTrue(all(pos.count(i) > 40 for i in range(4)))
        # No question of the bank is printed on the point's own teaching page (the audit also checks this).
        import content_subskills as cs
        self.assertEqual([x for x in cs.audit(self.c) if x["issues"]], [])

    def test_a_recheck_climbs_one_rung_when_due_and_a_miss_starts_again(self):
        t0 = 1_800_000_000
        r = GB.schedule(self.c, 1, 'tense-past', True, t0)
        self.assertEqual((r['step'], r['in_days'], r['is_due']), (0, 1, False))
        self.assertEqual(GB.schedule(self.c, 1, 'tense-past', True, t0 + 60)['step'], 0)  # extra practice before it is due: no change
        self.assertEqual(GB.due(self.c, 1, t0 + DAY - 60), []); self.assertEqual(GB.due(self.c, 1, t0 + DAY + 1), ['tense-past'])
        r = GB.schedule(self.c, 1, 'tense-past', True, t0 + DAY + 1)
        self.assertEqual((r['step'], r['in_days']), (1, 3))
        self.assertEqual(GB.schedule(self.c, 1, 'tense-past', True, t0 + DAY + 2)['step'], 1)  # once a day at most
        t = t0 + 4 * DAY + 2
        self.assertEqual(GB.schedule(self.c, 1, 'tense-past', True, t)['step'], 2)
        r = GB.schedule(self.c, 1, 'tense-past', False, t + 8 * DAY)
        self.assertEqual((r['step'], r['in_days']), (0, 1))
        self.assertIsNone(GB.review_of(self.c, 2, 'tense-past'))  # per learner

    def test_a_due_recheck_is_todays_grammar_step_and_shows_on_the_graph_and_the_point_page(self):
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': ['work'], 'minutes': 15})
        ans = self.answers('det-quantity')
        q = next(iter(ans))
        nx.node_answer(self.c, 1, {'question': q, 'choice': ans[q]})  # verified today: first re-check tomorrow
        # As if that was yesterday: the re-check has come, and nothing has been practised today yet.
        self.c.execute("UPDATE next_grammar_review SET due=?, last_day='' WHERE user_id=1", (time.time() - 60,))
        self.c.execute('UPDATE learning_events SET created=created-86400 WHERE user_id=1'); self.c.commit()
        step = next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'grammar')
        self.assertEqual((step['href'], step['done']), ('#/graph/det-quantity', False)); self.assertTrue(step['title'].startswith('语法复习：'))
        g = nx.graph(self.c, 1)
        self.assertEqual(g['summary']['due'], 1)
        self.assertTrue(next(n for t in g['topics'] for n in t['nodes'] if n['id'] == 'det-quantity')['due'])
        page, _ = nx.node(self.c, 1, 'det-quantity')
        self.assertTrue(page['review']['is_due']); self.assertEqual(len(page['practice']), 4)
        q2 = next(x['id'] for x in page['practice'] if x['id'] != q)  # the same question again today would be the same evidence row
        r, _ = nx.node_answer(self.c, 1, {'question': q2, 'choice': ans[q2]})
        self.assertEqual((r['review']['step'], r['review']['in_days']), (1, 3))
        step = next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'grammar')
        self.assertTrue(step['done'])
        self.assertFalse(nx.graph(self.c, 1)['summary']['due'])

    # ---------------- starting check ----------------

    def test_place_rule(self):
        P = GB.place
        self.assertEqual(P({'A2': 1}), 'A2'); self.assertEqual(P({'A2': 2}), 'A2')
        self.assertEqual(P({'A2': 4, 'B1': 2}), 'B1'); self.assertEqual(P({'A2': 4, 'B1': 1}), 'A2')
        self.assertEqual(P({'A2': 4, 'B1': 3, 'B2': 3, 'C1': 1}), 'B2'); self.assertEqual(P({'A2': 4, 'B1': 4, 'B2': 4, 'C1': 4}), 'C1')
        self.assertEqual(P({'A2': 3, 'B1': 3, 'B2': 2}), 'B2')

    def test_starting_check_goes_band_by_band_places_and_lights_the_graph(self):
        t = GB.placement_items(self.c, seed=7)
        items = t['items']
        self.assertEqual(len(items), 16); self.assertEqual([i['band'] for i in items], ['A2'] * 4 + ['B1'] * 4 + ['B2'] * 4 + ['C1'] * 4)
        self.assertTrue(all('answer' not in i for i in items))
        self.assertEqual(len({nx.nodes_meta(self.c)[i['node']]['topic'] for i in items[:4]}), 4)  # a band spans topics
        self.assertEqual(len({i['id'] for i in items}), 16)  # C1 has two points: two different questions on each
        right = lambda i: self.c.execute('SELECT answer FROM questions WHERE id=?', (i['id'],)).fetchone()[0]
        a2 = [{'question': i['id'], 'choice': right(i)} for i in items[:4]]
        r, code = GB.placement_score(self.c, 1, {'answers': a2})
        self.assertEqual((code, r), (200, {'done': False}))  # A2 all right: go on, nothing recorded yet
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events WHERE user_id=1').fetchone()[0], 0)
        b1 = [{'question': i['id'], 'choice': right(i) if k < 2 else None} for k, i in enumerate(items[4:8])]  # two right, two "不会"
        r, code = GB.placement_score(self.c, 1, {'answers': a2 + b1})
        self.assertTrue(r['done']); self.assertEqual(r['level'], 'B1'); self.assertTrue(r['saved'])
        self.assertEqual([s['right'] for s in r['scores']], [4, 2])
        self.assertEqual(sorted(g['id'] for g in r['gaps']), sorted(i['node'] for i in items[6:8]))
        states = nx.graph_states(self.c, 1)
        self.assertTrue(all(states[i['node']]['status'] == 'solid' for i in items[:6]))
        self.assertTrue(all(states[i['node']]['status'] == 'watch' for i in items[6:8]))
        firsts = sorted(GB.review_of(self.c, 1, i['node'])['in_days'] for i in items[:6])
        self.assertGreater(len(set(firsts)), 1)  # first re-checks are spread out, not all tomorrow
        # A guest is placed too, and nothing is stored.
        r, _ = GB.placement_score(self.c, None, {'answers': [{'question': i['id'], 'choice': None} for i in items[:4]]})
        self.assertEqual((r['done'], r['level'], r['saved']), (True, 'A2', False))
        for bad in ({'answers': []}, {'answers': [{'question': 'x'}]}, {'answers': [a2[0], a2[0]]}, {'answers': [{'question': 999999, 'choice': 0}]}):
            self.assertEqual(GB.placement_score(self.c, 1, bad)[1], 400)

    # ---------------- exam practice ----------------

    def test_exam_papers_hide_answers_and_build_from_the_right_levels(self):
        o, _ = ex.overview(self.c, 1)
        self.assertEqual([e['id'] for e in o['exams']], ['cet4', 'cet6', 'ky', 'ielts']); self.assertTrue(all(e['words'] > 3000 for e in o['exams']))
        for exam, e in ex.EXAMS.items():
            p, code = ex.paper(self.c, 1, exam)
            self.assertEqual(code, 200)
            vocab, grammar, reading = p['parts']
            self.assertEqual(len(vocab['items']), 10); self.assertEqual(len(grammar['items']), 8)
            self.assertTrue(all(len(set(v['options'])) == 4 and 'answer' not in v for v in vocab['items']))
            self.assertTrue(all(nx.node_level(self.c.execute('SELECT node FROM questions WHERE id=?', (q['id'],)).fetchone()[0]) in e['levels'] for q in grammar['items']))
            packs = {x['id']: x for _, x in nx._public_packs(self.c)}
            self.assertEqual(len(reading['passages']), 2)
            self.assertEqual(len({packs[ps['pack']]['theme'] for ps in reading['passages']}), 2)
            self.assertTrue(all(nx.cefr(packs[ps['pack']]) == e['reading'] and not packs[ps['pack']].get('series') for ps in reading['passages']))
            self.assertTrue(all(set(it) == {'prompt', 'options'} for ps in reading['passages'] for it in ps['items']))
        self.assertEqual(ex.paper(self.c, 1, 'toefl')[1], 400)

    def test_handing_in_scores_records_grammar_evidence_and_only_once(self):
        p, _ = ex.paper(self.c, 1, 'cet6')
        stored = json.loads(self.c.execute('SELECT content FROM next_exam_papers WHERE id=?', (p['paper'],)).fetchone()[0])
        g = p['parts'][1]['items']
        right = lambda q: self.c.execute('SELECT answer FROM questions WHERE id=?', (q['id'],)).fetchone()[0]
        answers = {'vocab': [v['answer'] for v in stored['vocab']], 'grammar': [right(q) for q in g[:-1]] + [(right(g[-1]) + 1) % 4],
                   'reading': [r['answer'] for r in stored['reading']]}
        self.assertEqual(ex.submit(self.c, 2, {'paper': p['paper'], 'answers': answers})[1], 404)  # someone else's paper
        r, code = ex.submit(self.c, 1, {'paper': p['paper'], 'answers': answers, 'seconds': 700})
        self.assertEqual(code, 200)
        self.assertEqual((r['score'], r['total'], r['seconds']), (21, 22, 700))
        self.assertEqual([x['right'] for x in r['parts']], [10, 7, 4])
        self.assertEqual(len(r['history']), 1); self.assertEqual(r['history'][0]['pct'], 95)
        miss = self.c.execute('SELECT node FROM questions WHERE id=?', (g[-1]['id'],)).fetchone()[0]
        self.assertEqual(nx.graph_states(self.c, 1)[miss]['status'], 'watch')
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1 AND norm=?", (f"gq:{g[-1]['id']}",)).fetchone()[0], 1)
        self.assertEqual(ex.submit(self.c, 1, {'paper': p['paper'], 'answers': answers})[1], 404)  # handed in once
        # Blanks score nothing and are not evidence; a guest's paper is scored and not stored.
        gp, _ = ex.paper(self.c, None, 'cet4')
        r, _ = ex.submit(self.c, None, {'paper': gp['paper'], 'answers': {}})
        self.assertEqual(r['score'], 0); self.assertFalse(r['saved'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM next_exam_results').fetchone()[0], 1)

    def test_exam_goal_gets_a_weekly_practice_step(self):
        nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'exam', 'themes': [], 'minutes': 15})
        step = next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'exam')
        self.assertFalse(step['done'])
        p, _ = ex.paper(self.c, 1, 'cet6'); ex.submit(self.c, 1, {'paper': p['paper'], 'answers': {}})
        self.assertTrue(next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'exam')['done'])
        self.c.execute('UPDATE next_exam_results SET created=created-3*86400'); self.c.commit()
        self.assertNotIn('exam', [s['key'] for s in nx.home(self.c, 1)['path']['steps']])  # done this week
        nx.save_profile(self.c, 2, {'level': 'B2', 'goal': 'work', 'themes': [], 'minutes': 15})
        self.assertNotIn('exam', [s['key'] for s in nx.home(self.c, 2)['path']['steps']])

    # ---------------- serial story ----------------

    def test_serial_is_listed_in_order_navigates_and_is_recommended_one_episode_at_a_time(self):
        lst = nx.library(self.c, 1)['series']
        s = next(x for x in lst if x['id'] == 'lighthouse-ledger')
        self.assertEqual((s['of'], s['done'], s['next_part'], s['level']), (6, 0, 1, 'C1'))
        page, _ = nx.series(self.c, 1, 'lighthouse-ledger')
        ids = [e['id'] for e in page['episodes']]
        self.assertEqual([e['part'] for e in page['episodes']], [1, 2, 3, 4, 5, 6])
        m, _ = nx.material(self.c, 1, ids[2])
        self.assertEqual(m['series'], {'id': 'lighthouse-ledger', 'title': '灯塔日志', 'part': 3, 'of': 6, 'prev': ids[1], 'next': ids[3]})
        self.assertIsNone(nx.material(self.c, 1, ids[0])[0]['series']['prev']); self.assertIsNone(nx.material(self.c, 1, ids[5])[0]['series']['next'])
        nx.save_profile(self.c, 1, {'level': 'C1', 'goal': 'interest', 'themes': ['culture'], 'minutes': 15})
        for _ in range(3):
            rec = [x['id'] for x in nx.home(self.c, 1)['today']]
            self.assertFalse(set(rec) & set(ids[1:]))  # never an episode from the middle
        nx.mark(self.c, 1, ids[0], 'check')
        self.assertEqual(nx.series(self.c, 1, 'lighthouse-ledger')[0]['next'], ids[1])
        self.assertFalse({x['id'] for x in nx.home(self.c, 1)['today']} & ({ids[0]} | set(ids[2:])))
        self.assertEqual(nx.series(self.c, 1, 'nope')[1], 404)

    # ---------------- reminder ----------------

    def test_whole_plan_calendar_reminder_is_folded_and_points_at_today(self):
        cal = vs.ics(7, 'plan', 15)
        self.assertIn('SUMMARY:语流：今天的学习（约 15 分钟）', cal.replace('\r\n ', ''))
        self.assertIn('URL:https://flow.jasa.hk/#/', cal); self.assertIn('DURATION:PT15M', cal)
        self.assertTrue(all(len(line.encode()) <= 75 for line in cal.split('\r\n')))
        self.assertIn('UID:flow-vocab-21@flow', vs.ics(21))  # the word-only reminder keeps its id


class LoopHttpTests(unittest.TestCase):
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
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)

    def test_open_routes_record_progress_only_with_the_csrf_token(self):
        self.call('/api/login', {'username': 'learner', 'password': 'correct horse battery'})
        csrf = json.loads(self.call('/api/session')[1])['user']['csrf']
        with app.db() as c:
            q = c.execute("SELECT id, answer FROM questions WHERE node='tense-past' LIMIT 1").fetchone()
        s, body, _ = self.call('/api/next/node/answer', {'question': q['id'], 'choice': q['answer']})
        self.assertEqual(s, 200); self.assertNotIn('status', json.loads(body))  # no token: answered as a guest
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0], 0)
        s, body, _ = self.call('/api/next/node/answer', {'question': q['id'], 'choice': q['answer']}, csrf)
        self.assertEqual(json.loads(body)['status'], 'solid')
        # The pages and routes of this release answer.
        self.assertEqual(len(json.loads(self.call('/api/next/placement')[1])['items']), 16)
        self.assertEqual(self.call('/api/next/exam')[0], 200)
        s, body, _ = self.call('/api/next/exam/paper', {'exam': 'ky'}, csrf); self.assertEqual(s, 200)
        self.assertEqual(self.call('/api/next/exam/submit', {'paper': json.loads(body)['paper'], 'answers': {}}, csrf)[0], 200)
        self.assertEqual(json.loads(self.call('/api/next/series?id=lighthouse-ledger')[1])['of'], 6)
        s, body, h = self.call('/api/next/vocab/reminder.ics?kind=plan&hour=8&minutes=20')
        self.assertEqual(s, 200); self.assertIn('flow-plan.ics', h['Content-Disposition']); self.assertIn(b'DURATION:PT20M', body)


if __name__ == '__main__':
    unittest.main()
