"""r14: every review item has a way out (no loops), interleaved grammar rounds, a connected graph with Chinese-speaker
traps, and flexible daily limits."""
import unittest, tempfile, sys, json, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, grammar_bank as GB, graph_links as GL, vocab_service as vs, skills_service as sk

DAY = 86400


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'sys.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def card(self, norm):
        return self.c.execute('SELECT * FROM next_cards WHERE user_id=1 AND norm=?', (norm,)).fetchone()

    def review_item(self, cid):
        return next(x for x in vs.queue(self.c, 1)['items'] if x['id'] == cid)

    # ---------------- mistakes: the same one again ----------------
    def test_the_same_mistake_again_brings_its_card_back_to_today_and_keeps_one_card(self):
        cid = sk.add_mistake(self.c, 1, 'fix', 'went', 'fix:goed > went', 'past tense')
        self.c.execute('UPDATE next_cards SET due=?, known=1 WHERE id=?', (time.time() + 5 * DAY, cid)); self.c.commit()
        again = sk.add_mistake(self.c, 1, 'fix', 'went', 'fix:goed > went', 'past tense')
        row = self.card('fix:goed > went')
        self.assertEqual((again, row['id'], row['known']), (cid, cid, 0))
        self.assertLessEqual(row['due'], time.time())
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE norm='fix:goed > went'").fetchone()[0], 1)

    def test_the_same_mistake_twice_at_once_is_one_card_and_no_error(self):
        import threading
        start, out, errors = threading.Barrier(2), [], []

        def tap():
            c = app.db()
            try:
                start.wait()
                out.append(sk.add_mistake(c, 1, 'fix', 'children', 'fix:childs > children', 'irregular plural'))
            except Exception as e:  # noqa: BLE001 — the test reports any of them
                errors.append(repr(e))
            finally:
                c.close()
        threads = [threading.Thread(target=tap) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        rows = self.c.execute("SELECT id, due FROM next_cards WHERE norm='fix:childs > children'").fetchall()
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(out, [rows[0]['id']] * 2)
        self.assertLessEqual(rows[0]['due'], time.time())

    # ---------------- review: no loops ----------------

    def test_a_reading_mistake_comes_back_once_with_its_passage_then_leaves(self):
        pid = nx.home(self.c, None, 'B2')['today'][0]['id']
        p = json.loads(nx._pack_row(self.c, None, pid)['content'])
        q = p['questions'][0]
        nx.check(self.c, 1, {'pack': pid, 'index': 0, 'choice': (q['answer'] + 1) % 4})
        cid = self.card(f'q:{pid}:0')['id']
        item = self.review_item(cid)
        self.assertEqual(item['mode'], 'question')
        self.assertIn(q['evidence'][:40], item['passage']['text'])  # the part of the text the answer rests on
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'again'})
        self.assertEqual(r['outcome'], 'later')
        self.assertGreaterEqual(self.card(f'q:{pid}:0')['due'], time.time() + 1.9 * DAY)  # not again in minutes
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'again'})
        self.assertEqual(r['outcome'], 'reread'); self.assertEqual(self.card(f'q:{pid}:0')['known'], 1)
        self.assertNotIn(cid, [x['id'] for x in vs.queue(self.c, 1)['items']])
        # Getting it wrong again in the material brings it back; answering it right then passes it.
        nx.check(self.c, 1, {'pack': pid, 'index': 0, 'choice': (q['answer'] + 1) % 4})
        self.assertEqual(self.card(f'q:{pid}:0')['known'], 0)
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})
        self.assertEqual(r['outcome'], 'passed'); self.assertEqual(self.card(f'q:{pid}:0')['known'], 1)

    def test_a_grammar_mistake_is_reviewed_on_other_questions_and_passes_after_two_right(self):
        ans = {r['id']: r['answer'] for r in self.c.execute("SELECT id, answer FROM questions WHERE node='det-article'")}
        first = next(iter(ans))
        nx.node_answer(self.c, 1, {'question': first, 'choice': (ans[first] + 1) % 4})
        cid = self.card(f'gq:{first}')['id']
        v1 = self.review_item(cid)['variant']
        self.assertNotEqual(v1['id'], first); self.assertEqual(sorted(v1['map']), [0, 1, 2, 3])
        # Answering the variant in review is evidence for the point but makes no new mistake card.
        nx.node_answer(self.c, 1, {'question': v1['id'], 'choice': (ans[v1['id']] + 1) % 4, 'from': 'review'})
        self.assertIsNone(self.card(f"gq:{v1['id']}"))
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})
        self.assertEqual(r['outcome'], 'once-more')
        self.c.execute('UPDATE next_cards SET due=? WHERE id=?', (time.time() - 1, cid)); self.c.commit()
        self.assertNotEqual(self.review_item(cid)['variant']['id'], v1['id'])  # the next time, another question
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})
        self.assertEqual(r['outcome'], 'passed'); self.assertEqual(self.card(f'gq:{first}')['known'], 1)

    def test_a_card_missed_twice_in_a_day_waits_until_tomorrow(self):
        nx.save_card(self.c, 1, {'text': 'reluctant'})
        cid = self.card('reluctant')['id']
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'again'})
        self.assertIsNone(r['outcome']); self.assertLess(self.card('reluctant')['due'], time.time() + 3600)
        r, _ = vs.rate(self.c, 1, {'id': cid, 'rating': 'again'})
        self.assertEqual(r['outcome'], 'tomorrow')
        self.assertGreaterEqual(self.card('reluctant')['due'], vs._day_start() + DAY)
        self.assertNotIn(cid, [x['id'] for x in vs.queue(self.c, 1)['items']])  # the session can end

    # ---------------- interleaved grammar ----------------

    def test_mixed_rounds_interleave_points_and_do_not_pile_up_cards(self):
        m, code = GB.mix(self.c, 1, pair='tense-past,tense-perfect', seed=3)
        self.assertEqual((code, m['kind'], len(m['items'])), (200, 'pair', 6))
        self.assertTrue(all(a['node'] != b['node'] for a, b in zip(m['items'], m['items'][1:])))  # alternating
        self.assertIn('具体的过去时间', m['note'])
        self.assertEqual(GB.mix(self.c, 1, pair='tense-past,nope')[1], 404)
        t, _ = GB.mix(self.c, 1, topic='modal'); self.assertEqual(len(t['items']), 4)
        p, _ = GB.mix(self.c, 1); self.assertEqual(p['kind'], 'practice'); self.assertGreaterEqual(len(p['items']), 4)
        # With points due, the round is made of them; missing one in the round schedules it, it adds no card.
        GB.schedule(self.c, 1, 'voice-basic', True, time.time() - 2 * DAY); GB.schedule(self.c, 1, 'det-zero', True, time.time() - 2 * DAY)
        self.c.commit()
        d, _ = GB.mix(self.c, 1)
        self.assertEqual(d['kind'], 'due'); self.assertEqual({n['id'] for n in d['nodes']}, {'voice-basic', 'det-zero'})
        self.assertEqual(len(d['items']), 4)
        q = d['items'][0]
        right = self.c.execute('SELECT answer FROM questions WHERE id=?', (q['id'],)).fetchone()[0]
        nx.node_answer(self.c, 1, {'question': q['id'], 'choice': (right + 1) % 4, 'from': 'mix'})
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1 AND source='mistake'").fetchone()[0], 0)
        self.assertEqual(GB.review_of(self.c, 1, q['node'])['in_days'], 1)

    # ---------------- connected graph ----------------

    def test_the_route_orders_all_points_and_every_point_has_a_trap_and_a_confusable(self):
        g = nx.graph(self.c, 1)
        ids = [n['id'] for b in g['route'] for n in b['nodes']]
        self.assertEqual(len(ids), 44); self.assertEqual(len(set(ids)), 44)
        self.assertEqual([b['band'] for b in g['route']], ['A2', 'B1', 'B2', 'C1'])
        pos = {n: i for i, n in enumerate(ids)}
        self.assertTrue(all(pos[a] < pos[b] for a, b in g['links']['prereq']))  # prerequisites come first on the route
        self.assertEqual(len(g['links']['confusable']), len(GL.CONFUSABLE))
        for nid in ids:
            n, _ = nx.node(self.c, 1, nid)
            self.assertTrue(n['l1'] and n['l1']['wrong'] != n['l1']['right'], nid)
            self.assertTrue(n['related']['confusable'], nid)
        n, _ = nx.node(self.c, 1, 'link-contrast')
        self.assertIn('clause-adverb', [x['id'] for x in n['related']['confusable']])
        self.assertTrue(n['related']['together'])

    # ---------------- flexible limits ----------------

    def test_any_daily_word_count_up_to_200_and_more_words_on_request(self):
        self.assertEqual(vs.save_plan(self.c, 1, {'book': 'cet4', 'daily_new': 137, 'retention': 0.9})[1], 200)
        for bad in (0, 201, 'x', 12.5):
            self.assertEqual(vs.save_plan(self.c, 1, {'book': 'cet4', 'daily_new': bad, 'retention': 0.9})[1], 400)
        vs.save_plan(self.c, 1, {'book': 'cet4', 'daily_new': 5, 'retention': 0.9})
        vs.introduce(self.c, 1)
        new = lambda: self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1 AND source='book'").fetchone()[0]
        self.assertEqual(new(), 5)
        r, code = vs.more_new(self.c, 1, {'n': 10})
        self.assertEqual((code, r['added']), (200, 10)); self.assertEqual(new(), 15)
        vs.introduce(self.c, 1); self.assertEqual(new(), 15)  # the plan itself is unchanged
        self.assertEqual(vs.more_new(self.c, 1, {'n': 51})[1], 400)

    def test_longer_days_get_a_second_material(self):
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 45})
        keys = [s['key'] for s in nx.home(self.c, 1)['path']['steps']]
        self.assertIn('read2', keys)
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 20})
        self.assertNotIn('read2', [s['key'] for s in nx.home(self.c, 1)['path']['steps']])
        self.assertEqual(nx.profile(self.c, 1)['minutes'], 20)


if __name__ == '__main__':
    unittest.main()
