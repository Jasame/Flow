"""周报「这周的一次进步」的数据 (r29, the user's picks 2026-11-26 with B7 and B6): every AI correction on a grammar point
noted once per output (反复出现: 14 days, at least 2 days, at least 3 different outputs; a rule-marked answer right without
help clears it), and a sentence the learner later wrote with the corrected form kept as evidence (written only, two a
point, 90 days, only for them; in the account export, gone with the account)."""
import datetime, inspect, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, progress_service as ps, skills_service as sk  # noqa: E402

DAY = 86400
CN = datetime.timezone(datetime.timedelta(hours=8))
at = lambda *a: datetime.datetime(*a, tzinfo=CN).timestamp()
NOW = at(2026, 11, 26, 12, 0)
GONE = {'from': 'have went', 'to': 'have gone', 'why': '现在完成时用过去分词', 'node': 'tense-perfect'}
ART = {'from': 'a apple', 'to': 'an apple', 'why': '元音前用 an', 'node': 'articles'}


class Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init()
        self.c = app.db()
        self.c.execute("INSERT INTO users(username,password,email) VALUES('lin','x','lin@example.test')"); self.c.commit()
        self.uid = 1

    def tearDown(self):
        self.c.close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def corrected(self, rid, when, *changes, kind='essay'):
        with patch('time.time', return_value=when):
            sk.mistakes_from_changes(self.c, self.uid, list(changes), 'I have went to the library.', 'writing', 'p1', request_id=rid, kind=kind)

    def count(self, table):
        return self.c.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?', (self.uid,)).fetchone()[0]


class CorrectionTests(Db):
    def test_each_output_notes_each_point_once_and_a_retry_adds_nothing(self):
        self.corrected('r1', NOW - DAY, GONE, ART)
        self.corrected('r1', NOW - DAY, GONE, ART)  # the same request again (a replay)
        self.corrected('r2', NOW, GONE)
        self.assertEqual(self.count('next_corrections'), 3)
        self.assertEqual(self.count('next_cards'), 2)  # the mistake book still has one card a mistake
        self.assertEqual(self.c.execute("SELECT kind FROM next_corrections WHERE source='fix:r2'").fetchone()[0], 'essay')
        no_node = dict(GONE, node=None, **{'from': 'is go', 'to': 'is going'})
        self.corrected('r3', NOW, no_node)
        self.assertEqual(self.count('next_corrections'), 3)  # nothing to count without a grammar point

    def test_a_point_recurs_in_three_outputs_on_two_days_within_fourteen(self):
        self.corrected('a', NOW - 3 * DAY, GONE)
        self.corrected('b', NOW - 3 * DAY + 60, GONE)
        self.assertEqual(ps.recurring(self.c, self.uid, NOW), [])  # twice: pointed out there and then, no more
        self.corrected('c', NOW - 3 * DAY + 120, GONE)
        self.assertEqual(ps.recurring(self.c, self.uid, NOW), [])  # three times but on one day
        self.corrected('d', NOW - DAY, GONE)
        rec = ps.recurring(self.c, self.uid, NOW)
        self.assertEqual([(r['node'], r['outputs'], r['days']) for r in rec], [('tense-perfect', 4, 2)])
        self.assertEqual(ps.recurring(self.c, self.uid, NOW + 14 * DAY), [])  # out of the window

    def test_a_right_answer_without_help_in_a_marked_question_clears_it(self):
        for k, t in enumerate((NOW - 4 * DAY, NOW - 3 * DAY, NOW - 2 * DAY)):
            self.corrected(f'x{k}', t, GONE)
        self.assertTrue(ps.recurring(self.c, self.uid, NOW))
        import event_service as ev
        ev.record(self.c, self.uid, 'tense-perfect', 'next-node:q1', 'choice', 'q1', correct=True, assisted=True, evaluator='rule', created=NOW - DAY)
        self.assertTrue(ps.recurring(self.c, self.uid, NOW))  # with help: still counts
        ev.record(self.c, self.uid, 'tense-perfect', 'next-node:q2', 'choice', 'q2', correct=True, assisted=False, evaluator='rule', created=NOW - DAY)
        self.assertEqual(ps.recurring(self.c, self.uid, NOW), [])


class EvidenceTests(Db):
    def test_a_later_written_sentence_with_the_corrected_form_is_kept_with_its_before(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        text = 'I had a busy week. Tom has gone to the library, so he will be late. We have gone over the notes.'
        self.assertEqual(ps.note_evidence(self.c, self.uid, text, [], 'rewrite', 'r9', False, NOW), 1)
        pair = ps.pairs(self.c, self.uid, NOW + 60)
        self.assertEqual(len(pair), 1)
        b, a = pair[0]['before'], pair[0]['after']
        self.assertEqual((pair[0]['node'], b['from'], b['to'], b['kind']), ('tense-perfect', 'have went', 'have gone', 'essay'))
        self.assertEqual(b['sentence'], 'I have went to the library.')
        self.assertEqual((a['sentence'], a['kind'], a['assisted']), ('We have gone over the notes.', 'rewrite', 0))

    def test_not_kept_when_this_output_was_corrected_on_that_point_or_the_form_means_nothing_alone(self):
        self.corrected('r1', NOW - 10 * DAY, GONE, dict(ART, to='the', **{'from': 'a'}))
        self.assertEqual(ps.note_evidence(self.c, self.uid, 'They have gone home.', [GONE], 'essay', 'r2', None, NOW), 0)
        self.assertEqual(ps.note_evidence(self.c, self.uid, 'Open the door.', [], 'essay', 'r3', None, NOW), 0)  # 'the' alone
        self.assertEqual(self.count('next_evidence'), 0)

    def test_two_a_point_and_ninety_days_at_most(self):
        self.corrected('r1', NOW - 100 * DAY, GONE)
        for k in range(3):
            ps.note_evidence(self.c, self.uid, f'We have gone there {k + 2} times.', [], 'essay', f'e{k}', None, NOW - 95 * DAY + k)
        self.assertEqual(self.count('next_evidence'), 2)
        ps.note_evidence(self.c, self.uid, 'She has gone out.', [], 'essay', 'e9', None, NOW)  # has gone ≠ have gone: nothing new
        ps.note_evidence(self.c, self.uid, 'They have gone out.', [], 'essay', 'e10', None, NOW)
        self.assertEqual([r[0] for r in self.c.execute('SELECT sentence FROM next_evidence')], ['They have gone out.'])  # the old two are past 90 days

    def test_only_written_answers_are_kept(self):
        src = inspect.getsource(__import__('output_service').retell)
        self.assertIn('if not audio:', src)
        self.assertLess(src.index('if not audio:'), src.index('note_evidence'))
        for fn in ('essay', 'translate'):
            self.assertIn("note_evidence(c, uid, text, r['fixes']", inspect.getsource(getattr(__import__('output_service'), fn)))
        self.assertNotIn('note_evidence', inspect.getsource(__import__('output_service').dialog))  # spoken (or chat): never kept
        self.assertNotIn('note_evidence', inspect.getsource(__import__('ielts_speaking')._record))

    def test_in_the_account_export_and_gone_with_the_account(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        ps.note_evidence(self.c, self.uid, 'We have gone over it.', [], 'essay', 'e1', None, NOW); self.c.commit()
        import account_data as ad
        tables = __import__('json').loads(ad.records(self.c, {'id': self.uid}))['tables']
        self.assertIn('next_evidence', tables); self.assertIn('next_corrections', tables)
        ad.forget(self.c, self.uid, Path(self.tmp.name))
        self.assertEqual((self.count('next_evidence'), self.count('next_corrections')), (0, 0))


if __name__ == '__main__':
    unittest.main()
