"""Word books: one grouped registry for the built-in books and the data books (专四、专八、中考… from
corpus_data/wordbooks*.json), the loader's tolerance of bad files, and the plan API with the new ids."""
import io, json, sys, tempfile, time, unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, vocab_service as vs

TEM4 = ['abolish', 'absurd', 'accommodate', 'acknowledge', 'adjacent', 'advocate', 'allocate', 'ambiguous']
TEM8 = ['aberration', 'acquiesce', 'alacrity', 'ameliorate', 'anachronism', 'antipathy']
ZK = ['apple', 'breakfast', 'classroom', 'holiday']
NAWL = ['algorithm', 'anomaly', 'catalyst', 'hypothesis']
BUILTIN = ['core', 'mid', 'high', 'adv', 'ext', 'cet4', 'cet6', 'ky', 'ielts', 'toefl', 'gre']


def book(title, group, words, **k):
    return {'title': title, 'group': group, 'blurb': title + '的说明', 'basis': '按大纲要求的词汇量编成，不是官方词表。', 'words': words, **k}


class Fixture:
    """Data files in a temporary folder, the loader pointed at them, and the caches rebuilt for this test only."""

    def __init__(self, test, files):
        self.dir = tempfile.TemporaryDirectory()
        paths = []
        for name, content in files:
            f = Path(self.dir.name) / name
            if content is not None:
                f.write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False), encoding='utf-8')
            paths.append(f)
        self.log = io.StringIO()
        for p in (patch.object(vs, 'WORDBOOK_FILES', paths), patch.object(vs, '_DATA', None), patch.object(vs, '_BOOK', None)):
            p.start(); test.addCleanup(p.stop)
        test.addCleanup(self.dir.cleanup)
        with redirect_stderr(self.log):
            vs.book_words()  # loaded (and logged) once, here

    @property
    def text(self):
        return self.log.getvalue()


class RegistryTests(unittest.TestCase):
    def test_built_in_books_without_data_files(self):
        Fixture(self, [])
        r = vs.registry()
        self.assertEqual([b['id'] for b in r], BUILTIN)
        self.assertEqual(vs.book_groups(r), ['按词频', '大学英语', '出国留学'])
        for b in r:
            self.assertTrue(b['title'] and b['blurb'] and b['group'], b)
            self.assertEqual(b['count'], b['size']); self.assertGreater(b['count'], 1000, b['id'])
            self.assertNotIn('basis', b)
        self.assertEqual({b['id']: b['group'] for b in r if b['kind'] == 'exam'},
                         {'cet4': '大学英语', 'cet6': '大学英语', 'ky': '大学英语', 'ielts': '出国留学', 'toefl': '出国留学', 'gre': '出国留学'})
        self.assertEqual(r[0]['range'], '1–2000')
        self.assertEqual(vs.LEVEL_BOOK, {'A2': 'core', 'B1': 'mid', 'B2': 'high', 'C1': 'adv'})  # the test's suggestions are unchanged

    def test_data_books_join_their_groups_in_order(self):
        Fixture(self, [('wordbooks.json', {'notice': 'x', 'books': {'tem4': book('专四词汇', '英语专业', TEM4), 'tem8': book('专八词汇', '英语专业', TEM8)}}),
                       ('wordbooks-open.json', {'books': {'nawl': book('学术英语词汇', '学术与职场', NAWL), 'zk': book('中考词汇', '中学英语', ZK),
                                                          'misc': book('其他', '兴趣词表', ['apple'])}})])
        r = vs.registry()
        self.assertEqual([b['id'] for b in r], ['core', 'mid', 'high', 'adv', 'ext', 'zk', 'cet4', 'cet6', 'ky', 'tem4', 'tem8',
                                                 'ielts', 'toefl', 'gre', 'nawl', 'misc'])
        self.assertEqual(vs.book_groups(r), ['按词频', '中学英语', '大学英语', '英语专业', '出国留学', '学术与职场', '兴趣词表'])  # unknown group last
        tem4 = next(b for b in r if b['id'] == 'tem4')
        self.assertEqual({k: tem4[k] for k in ('kind', 'title', 'group', 'blurb', 'count', 'size')},
                         {'kind': 'data', 'title': '专四词汇', 'group': '英语专业', 'blurb': '专四词汇的说明', 'count': len(TEM4), 'size': len(TEM4)})
        self.assertIn('不是官方词表', tem4['basis'])
        self.assertEqual([w for _, w in vs.book_words()['tem4']], TEM4)  # the file's study order, not frequency order
        self.assertEqual(vs.book_words()['tem4'][0][0], nx.dictionary()['abolish']['rank'])  # cards keep the frequency rank
        self.assertEqual((vs.book_title('tem8'), vs.book_title('cet4'), vs.book_title('nope')), ('专八词汇', '四级词汇', '词书'))
        self.assertEqual(vs.score_test(None, None, {'answers': {w: True for w in vs.test_items(seed=2)['items']}})[0]['titles']['tem4'], '专四词汇')

    def test_words_the_dictionary_lacks_are_skipped_and_logged(self):
        fx = Fixture(self, [('wordbooks.json', {'books': {'tem4': book('专四词汇', '英语专业',
                                                                       ['Abolish ', 'zzqxv', 'abolish', 42, '', 'make ends meet', 'absurd', None, 'ebullient'])}})])
        self.assertEqual([w for _, w in vs.book_words()['tem4']], ['abolish', 'absurd'])  # trimmed, lower-cased, once
        self.assertIn('tem4 skips 3', fx.text); self.assertIn('zzqxv', fx.text)

    def test_missing_and_broken_files_add_nothing(self):
        fx = Fixture(self, [('wordbooks.json', None), ('wordbooks-bad.json', '{"books": [1, 2'), ('wordbooks-list.json', {'books': ['tem4']}),
                            ('wordbooks-nokey.json', {'notice': 'no books'}), ('wordbooks-open.json', {'books': {'zk': book('中考词汇', '中学英语', ZK)}})])
        self.assertEqual([b['id'] for b in vs.registry() if b['kind'] == 'data'], ['zk'])  # the good file still counts
        for name in ('wordbooks.json: not found', 'wordbooks-bad.json: not used', 'wordbooks-list.json: not used', 'wordbooks-nokey.json: not used'):
            self.assertIn(name, fx.text)
        Fixture(self, [('wordbooks.json', None)])
        self.assertEqual([b['id'] for b in vs.registry()], BUILTIN)

    def test_id_clashes_bad_ids_and_empty_books(self):
        fx = Fixture(self, [('wordbooks.json', {'books': {'tem4': book('专四词汇', '英语专业', TEM4), 'cet4': book('假四级', '大学英语', TEM4),
                                                          'Bad Id': book('坏', '英语专业', TEM4), 'empty': book('空', '英语专业', ['zzqxv', 'qqqzx']),
                                                          'none': book('无', '英语专业', []), 'notitle': {'words': TEM4}, 'nowords': book('无词', '英语专业', 'abolish')}}),
                            ('wordbooks-open.json', {'books': {'tem4': book('另一个专四', '英语专业', TEM8), 'gk': book('高考词汇', '中学英语', ZK)}})])
        data = {b['id']: b for b in vs.registry() if b['kind'] == 'data'}
        self.assertEqual(list(data), ['gk', 'tem4'])  # grouped: 中学英语 before 英语专业
        self.assertEqual(data['tem4']['title'], '专四词汇')  # the first file keeps the id
        self.assertEqual(next(b for b in vs.registry() if b['id'] == 'cet4')['title'], '四级词汇')  # built-in books cannot be replaced
        self.assertNotIn('empty', vs.book_words()); self.assertNotIn('none', vs.book_words())
        for bit in ("'cet4' is already built in", "'tem4' is already used by wordbooks.json", "'Bad Id'", 'empty has no usable word', 'notitle has no title', 'nowords has no title'):
            self.assertIn(bit, fx.text)


class PlanApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'w.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        self.fx = Fixture(self, [('wordbooks.json', {'books': {'tem4': book('专四词汇', '英语专业', TEM4), 'tem8': book('专八词汇', '英语专业', TEM8),
                                                               'empty': book('空', '英语专业', ['zzqxv'])}})])

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def test_overview_lists_the_grouped_registry(self):
        o, status = nx.get(self.c, 1, '/api/next/vocab', {})
        self.assertEqual(status, 200)
        self.assertEqual(o['groups'], ['按词频', '大学英语', '英语专业', '出国留学'])
        self.assertEqual([b['id'] for b in o['books']], ['core', 'mid', 'high', 'adv', 'ext', 'cet4', 'cet6', 'ky', 'tem4', 'tem8', 'ielts', 'toefl', 'gre'])
        tem8 = next(b for b in o['books'] if b['id'] == 'tem8')
        for k in ('title', 'group', 'blurb', 'count', 'basis', 'skippable'):
            self.assertIn(k, tem8)
        self.assertEqual(o['suggested_book'], 'mid')

    def test_exam_goals_name_only_books_that_exist(self):
        # 中考、高考 come from wordbooks-open.json, which this fixture leaves out: no chip may point at a missing book
        o, _ = nx.get(self.c, 1, '/api/next/vocab', {})
        self.assertEqual([(g['title'], g['book']) for g in o['exam_goals']],
                         [('四级', 'cet4'), ('六级', 'cet6'), ('考研', 'ky'), ('专四', 'tem4'), ('专八', 'tem8'), ('雅思', 'ielts'), ('托福', 'toefl'), ('GRE', 'gre')])
        ids = {b['id'] for b in o['books']}
        self.assertTrue(all(g['book'] in ids for g in o['exam_goals']))

    def test_a_data_book_plan_teaches_its_words_in_study_order(self):
        self.assertEqual(nx.post(self.c, 1, '/api/next/vocab/plan', {'book': 'empty', 'daily_new': 5, 'retention': 0.9})[1], 400)  # hidden
        self.assertEqual(nx.post(self.c, 1, '/api/next/vocab/plan', {'book': ['tem4'], 'daily_new': 5, 'retention': 0.9})[1], 400)
        o, status = nx.post(self.c, 1, '/api/next/vocab/plan', {'book': 'tem4', 'daily_new': 5, 'retention': 0.9})
        self.assertEqual(status, 200); self.assertEqual(o['plan']['book'], 'tem4')
        self.assertEqual((o['book']['title'], o['book']['size'], o['book']['skipped']), ('专四词汇', len(TEM4), 0))
        q, _ = nx.get(self.c, 1, '/api/next/review', {})
        norms = [r[0] for r in self.c.execute("SELECT norm FROM next_cards WHERE user_id=1 AND source='book' ORDER BY id")]
        self.assertEqual(norms, TEM4[:5])
        self.assertEqual(len([i for i in q['items'] if i['source'] == 'book']), 5)
        self.assertTrue(all(i['meaning'] for i in q['items']))
        r, status = nx.post(self.c, 1, '/api/next/vocab/more', {'n': 10})
        self.assertEqual((status, r['added']), (200, len(TEM4) - 5))  # the rest of the book, and no more

    def test_the_vocabulary_test_skip_applies_to_data_books(self):
        nx.post(self.c, 1, '/api/next/vocab/plan', {'book': 'tem4', 'daily_new': 5, 'retention': 0.9})
        self.c.execute('UPDATE next_vocab_plans SET skip_rank=5000, test_skip=5000'); self.c.commit()
        known = sum(1 for w in TEM4 if nx.dictionary()[w]['rank'] <= 5000)
        self.assertGreater(known, 0)
        self.assertEqual(vs.overview(self.c, 1)['book']['skipped'], known)
        vs.introduce(self.c, 1)
        ranks = [r[0] for r in self.c.execute("SELECT rank FROM next_cards WHERE user_id=1 AND source='book'")]
        self.assertTrue(ranks and all(r > 5000 for r in ranks), ranks)

    def test_existing_plans_keep_working(self):
        for b in BUILTIN:
            self.assertEqual(nx.post(self.c, 1, '/api/next/vocab/plan', {'book': b, 'daily_new': 10, 'retention': 0.9})[1], 200, b)
        self.c.execute("UPDATE next_vocab_plans SET book='cet4'"); self.c.commit()  # a plan saved before the registry
        o, _ = nx.get(self.c, 1, '/api/next/vocab', {})
        self.assertEqual((o['book']['id'], o['book']['title']), ('cet4', '四级词汇'))
        self.assertGreater(vs.introduce(self.c, 1), 0)

    def test_a_plan_whose_data_book_went_away_does_not_break(self):
        nx.post(self.c, 1, '/api/next/vocab/plan', {'book': 'tem8', 'daily_new': 5, 'retention': 0.9})
        Fixture(self, [('wordbooks.json', None)])  # the file is gone after an update
        o, status = nx.get(self.c, 1, '/api/next/vocab', {})
        self.assertEqual((status, o['plan']['book'], o['book']), (200, 'tem8', None))
        self.assertEqual(vs.introduce(self.c, 1, time.time() + 86400), 0)
        self.assertEqual(nx.post(self.c, 1, '/api/next/vocab/more', {'n': 5})[1], 400)
        self.assertEqual(nx.get(self.c, 1, '/api/next/review', {})[1], 200)
        self.assertEqual(nx.post(self.c, 1, '/api/next/vocab/plan', {'book': 'cet6', 'daily_new': 5, 'retention': 0.9})[1], 200)


class DefaultFilesTests(unittest.TestCase):
    def test_default_files_are_the_corpus_wordbooks_in_name_order(self):
        with patch.object(vs, 'WORDBOOK_FILES', None), patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('FLOW_WORDBOOKS', None)
            files = vs.wordbook_files()
            self.assertEqual(files, sorted(files))
            self.assertTrue(all(f.parent.name == 'corpus_data' and f.name.startswith('wordbooks') and f.suffix == '.json' for f in files))
            os.environ['FLOW_WORDBOOKS'] = os.pathsep.join(['/x/a.json', '/x/b.json'])
            self.assertEqual([f.name for f in vs.wordbook_files()], ['a.json', 'b.json'])

    def test_upgrade_installs_every_wordbook_file(self):
        script = (Path(__file__).resolve().parents[1] / 'upgrade.sh').read_text()
        self.assertIn('corpus_data/wordbooks*.json', script)


if __name__ == '__main__':
    unittest.main()
