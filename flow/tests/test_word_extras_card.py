"""单词详细模式第 4 步 on the learner's side (B2, 2026-11-26): the card shows B7's checked AI 常用搭配和近义词 less the ones
this learner marked 「这条不对」; a mark keeps one row per learner and item with a cleaned note; 放回 takes it back;
the word's detail lists the marked ones; the word-book exports carry them marked 「AI 生成」; B7's reported() counts them."""
import csv, io, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, account_data, next_service as nx, vocab_service as vs, word_extras as wx  # noqa: E402


class ExtrasOnTheCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'x.db'); self.p.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        wx.store(self.c, 'decision', [('colloc', 'make a decision', '做决定', ''), ('colloc', 'a tough decision', '艰难的决定', ''),
                                      ('near', 'choice', '选择', '更口语')], 'test')
        self.c.commit()
        self.cid = nx.save_card(self.c, 1, {'text': 'decision'})[0]['card']['id']
        nx.save_card(self.c, 2, {'text': 'decision'})
        self.ids = {r[1]: r[0] for r in self.c.execute("SELECT id, en FROM vocab_extras WHERE norm='decision'")}

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def card(self, uid=1):
        r = self.c.execute('SELECT * FROM next_cards WHERE user_id=? AND norm=?', (uid, 'decision')).fetchone()
        return vs.card_out(r, rich=True, c=self.c)

    def test_the_card_shows_the_checked_items_with_their_ids(self):
        ex = self.card()['extras']
        self.assertEqual([(x['kind'], x['en']) for x in ex], [('colloc', 'make a decision'), ('colloc', 'a tough decision'), ('near', 'choice')])
        self.assertEqual(ex[2]['diff'], '更口语'); self.assertTrue(all(isinstance(x['id'], int) for x in ex))

    def test_this_is_wrong_hides_it_for_that_learner_only_and_put_back_shows_it_again(self):
        bad = self.ids['a tough decision']
        self.assertEqual(vs.flag_extra(self.c, 1, {'id': bad, 'note': '  不常用\x00‮  '})[1], 200)
        self.assertNotIn(bad, [x['id'] for x in self.card(1)['extras']])
        self.assertIn(bad, [x['id'] for x in self.card(2)['extras']])  # the other learner still sees it
        marked = vs.detail(self.c, 1, self.cid)[0]['marked']
        self.assertEqual([(m['en'], m['note']) for m in marked], [('a tough decision', '不常用')])  # trimmed, control marks gone
        # B7's count for the console (B6): one learner, the note, no name
        rep = wx.reported(self.c)
        self.assertEqual([(r['en'], r['users'], r['notes']) for r in rep], [('a tough decision', 1, ['不常用'])])
        self.assertEqual(vs.unflag_extra(self.c, 1, {'id': bad})[1], 200)
        self.assertIn(bad, [x['id'] for x in self.card(1)['extras']]); self.assertEqual(vs.detail(self.c, 1, self.cid)[0]['marked'], [])

    def test_marking_again_keeps_one_row_with_the_latest_note_and_a_note_has_100_at_most(self):
        bad = self.ids['choice']
        vs.flag_extra(self.c, 1, {'id': bad, 'note': '第一次'})
        with patch('vocab_service.time.time', return_value=time.time() + 60):
            vs.flag_extra(self.c, 1, {'id': bad, 'note': '长' * 150})
        rows = self.c.execute('SELECT note FROM vocab_extras_flags WHERE user_id=1').fetchall()
        self.assertEqual([len(r[0]) for r in rows], [100])

    def test_a_bad_request_is_refused(self):
        self.assertEqual(vs.flag_extra(self.c, 1, {'id': 'x'})[1], 400)
        self.assertEqual(vs.flag_extra(self.c, 1, {'id': 999999})[1], 404)
        self.assertEqual(vs.flag_extra(self.c, 1, {'id': self.ids['choice'], 'note': ['not', 'text']})[1], 200)  # no note kept
        self.assertEqual(self.c.execute('SELECT note FROM vocab_extras_flags').fetchone()[0], '')

    def test_taken_down_on_the_console_it_leaves_every_card(self):
        wx.take_down(self.c, self.ids['make a decision'], '搭配不对', 'admin'); self.c.commit()
        self.assertNotIn('make a decision', [x['en'] for x in self.card(2)['extras']])

    def test_the_exports_carry_them_marked_ai_generated_less_the_marked_ones(self):
        vs.flag_extra(self.c, 1, {'id': self.ids['a tough decision']})
        rows = list(csv.reader(io.StringIO(account_data.cards_csv(self.c, 1).decode('utf-8-sig'))))
        head, row = rows[0], rows[1]
        self.assertEqual(head[-2:], ['常用搭配（AI 生成，仅供参考）', '近义词（AI 生成，仅供参考）'])
        self.assertEqual(row[-2:], ['make a decision 做决定', 'choice 选择（更口语）'])
        anki = account_data.cards_anki(self.c, 1).decode('utf-8')
        self.assertIn('常用搭配（AI 生成）：make a decision 做决定', anki); self.assertIn('近义词（AI 生成）：choice 选择（更口语）', anki)
        self.assertNotIn('tough', anki)

    def test_the_marks_are_in_the_learners_data_and_go_with_the_account(self):
        vs.flag_extra(self.c, 1, {'id': self.ids['choice'], 'note': '不对'})
        self.assertIn('vocab_extras_flags', account_data.GUIDE)
        self.assertIn('user_id', [r[1] for r in self.c.execute('PRAGMA table_info(vocab_extras_flags)')])


class ExtrasRouteTests(unittest.TestCase):
    def test_the_routes_reach_the_service(self):
        with patch('vocab_service.flag_extra', return_value=({'ok': True}, 200)) as f, patch('vocab_service.unflag_extra', return_value=({'ok': True}, 200)) as u:
            self.assertEqual(vs.post(None, 1, '/api/next/vocab/extra-flag', {'id': 1})[1], 200)
            self.assertEqual(vs.post(None, 1, '/api/next/vocab/extra-unflag', {'id': 1})[1], 200)
        self.assertEqual((f.call_count, u.call_count), (1, 1))


if __name__ == '__main__':
    unittest.main()
