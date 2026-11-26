"""The experience round: 撤销 of the latest review rating, and the page parts of instant pages and preloading, 复读,
字号和行距 and the first visit (their behaviour in a browser is checked by tools/ui_test.py)."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, vocab_service as vs  # noqa: E402

JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
CSS = (Path(app.ROOT) / 'public' / 'next.css').read_text(encoding='utf-8')


class UndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('lin', 'x'))
            self.uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]
            now = time.time()
            for w in ('harbour', 'ledger'):
                c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due,state) VALUES(?,?,?,?,?,?,'new')", (self.uid, w, w, 'word', now, now - 60))
            c.commit()
            self.cards = [r[0] for r in c.execute('SELECT id FROM next_cards ORDER BY id')]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def card(self, c, cid):
        return {k: c.execute('SELECT * FROM next_cards WHERE id=?', (cid,)).fetchone()[k] for k in vs.UNDO_FIELDS}

    def test_the_latest_rating_is_taken_back_as_if_it_never_happened(self):
        with app.db() as c:
            before = self.card(c, self.cards[0])
            self.assertEqual(vs.rate(c, self.uid, {'id': self.cards[0], 'rating': 'again'})[1], 200)
            self.assertNotEqual(self.card(c, self.cards[0]), before)
            body, st = vs.undo(c, self.uid, {'id': self.cards[0]})
            self.assertEqual(st, 200)
            self.assertEqual(self.card(c, self.cards[0]), before)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM next_reviews WHERE card=?', (self.cards[0],)).fetchone()[0], 0)
            self.assertIn('due', body)
            self.assertEqual(vs.undo(c, self.uid, {'id': self.cards[0]})[1], 409)  # once

    def test_only_the_latest_and_only_for_ten_minutes(self):
        with app.db() as c:
            vs.rate(c, self.uid, {'id': self.cards[0], 'rating': 'good'})
            vs.rate(c, self.uid, {'id': self.cards[1], 'rating': 'good'})
            self.assertEqual(vs.undo(c, self.uid, {'id': self.cards[0]})[1], 409)  # not the latest any more
            c.execute('UPDATE next_undo SET created=created-?', (vs.UNDO_SECONDS + 1,)); c.commit()
            self.assertEqual(vs.undo(c, self.uid, {'id': self.cards[1]})[1], 409)
            self.assertEqual(vs.undo(c, self.uid, {'id': 'nonsense'})[1], 409)

    def test_one_learner_cannot_undo_for_another(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('ma', 'x')); c.commit()
            other = c.execute("SELECT id FROM users WHERE username='ma'").fetchone()[0]
            vs.rate(c, self.uid, {'id': self.cards[0], 'rating': 'again'})
            self.assertEqual(vs.undo(c, other, {'id': self.cards[0]})[1], 409)


class PageTests(unittest.TestCase):
    def test_instant_pages_and_preloading(self):
        for s in ("const SNAP = 'flow-snap'", 'delete h.session.user.csrf', 'await DATA.ready', 'dataForget()', "addEventListener('pointerdown'",
                  'function prefetchTabs', 'requestIdleCallback', 'snapClear();', 'function redrawQuietly', 'snapMaterialGet(path)',
                  "[/^#\\/review$/, () => (S.user ? ['/api/next/review'] : [])]"):
            self.assertIn(s, JS)
        # the review queue brings in today's new words: never preloaded while idle
        idle = JS[JS.index('function prefetchTabs'):JS.index('// A link\'s page')]
        self.assertNotIn('/api/next/review', idle)

    def test_repeat_undo_text_size_and_first_visit(self):
        for s in ('data-rep="${n}"', 'data-gap="${n}"', "save('flow-next-loop', LOOP)", 'function takeBack', "api('/api/next/review/undo'",
                  'OUTBOX.unpush', 'function habitsView', "save('flow-next-text', TEXT)", 'data-tap="welcome-start"', 'data-tap="trial-level"',  # r27: the one start page took the place of 先试读一篇
                  "load('flow-wx-guide')"):
            self.assertIn(s, JS)
        self.assertIn(':root[data-size=xl]{--read-zoom:1.25}', CSS)


if __name__ == '__main__':
    unittest.main()
