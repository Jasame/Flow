"""corpus_data/wordbooks-open.json: the open word books (中考, 高考, NAWL, BSL) and their licences (WORDBOOKS-OPEN.md)."""
import json, re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import next_service as nx  # noqa: E402

DATA = ROOT / 'corpus_data'
BOOKS = {'zk': ('中考词汇', '中学英语', 1400, 1603), 'gk': ('高考词汇', '中学英语', 3400, 3726),
         'nawl': ('学术英语', '学术与职场', 900, 957), 'bsl': ('商务英语', '学术与职场', 1650, 1744)}
PLAIN = re.compile(r'[a-z]+(?:-[a-z]+)*')
CJK = re.compile(r'[\u4e00-\u9fff]')


def flat(text):
    return ' '.join(text.split())


class OpenWordbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((DATA / 'wordbooks-open.json').read_text(encoding='utf-8'))
        cls.books = cls.doc['books']

    def test_shape(self):
        self.assertEqual(list(self.doc), ['notice', 'books'])
        self.assertEqual(list(self.books), list(BOOKS))
        for key, (title, group, lo, hi) in BOOKS.items():
            with self.subTest(book=key):
                b = self.books[key]
                self.assertEqual(list(b), ['title', 'group', 'blurb', 'basis', 'words'])
                self.assertEqual((b['title'], b['group']), (title, group))
                for field in ('blurb', 'basis'):
                    self.assertIsInstance(b[field], str)
                    self.assertTrue(CJK.search(b[field]) and '\n' not in b[field] and len(b[field]) < 160, field)
                self.assertTrue(all(isinstance(w, str) for w in b['words']))
                self.assertTrue(lo <= len(b['words']) <= hi, len(b['words']))

    def test_words_are_plain_lower_case_and_unique(self):
        for key, b in self.books.items():
            with self.subTest(book=key):
                self.assertEqual(len(b['words']), len(set(b['words'])))
                odd = [w for w in b['words'] if not PLAIN.fullmatch(w) or len(w) < 2]
                self.assertEqual(odd, [])

    def test_every_word_is_in_the_dictionary_with_a_chinese_meaning(self):
        """The same test vocab_service.book_words() applies: an entry, a meaning, no capitalised headword."""
        d = nx.dictionary()
        for key, b in self.books.items():
            with self.subTest(book=key):
                bad = [w for w in b['words'] if w not in d or not CJK.search(d[w]['meaning'] or '') or d[w]['word'][:1].isupper()]
                self.assertEqual(bad, [])

    def test_study_order(self):
        """中考, 高考 and NAWL go by the dictionary's frequency rank; BSL keeps the list's own rank order."""
        d = nx.dictionary()
        for key in ('zk', 'gk', 'nawl'):
            words = self.books[key]['words']
            self.assertEqual(words, sorted(words, key=lambda w: (d[w]['rank'], w)), key)
        self.assertEqual(self.books['bsl']['words'][:4], ['mister', 'equity', 'dividend', 'portfolio'])
        self.assertEqual(self.books['zk']['words'][:3], ['the', 'be', 'and'])

    def test_gaokao_includes_zhongkao_and_prefixes_are_left_out(self):
        self.assertEqual(set(self.books['zk']['words']) - set(self.books['gk']['words']), set())
        for key in ('nawl', 'bsl'):
            self.assertFalse({'anti', 'non', 'pre', 'semi', 'multi'} & set(self.books[key]['words']), key)
        self.assertIn('headquarters', self.books['nawl']['words'])  # NAWL lists it as "headquarter"

    def test_licence_notices(self):
        notice = self.doc['notice']
        for part in ('ECDICT', 'MIT', 'New Academic Word List', 'Business Service List', 'Browne', 'Culligan', 'Phillips',
                     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0/', 'NGSL-LICENSE.txt', 'ECDICT-LICENSE.txt'):
            self.assertIn(part, notice)
        for key in ('zk', 'gk'):
            self.assertIn('ECDICT（MIT 许可）', self.books[key]['basis'])
        for key in ('nawl', 'bsl'):
            self.assertIn('CC BY-SA 4.0', self.books[key]['basis'])
            self.assertIn('Browne', self.books[key]['basis'])
        ngsl = flat((DATA / 'NGSL-LICENSE.txt').read_text(encoding='utf-8'))
        for part in ('New Academic Word List by Browne, C., Culligan, B., and Phillips, J. is licensed under a Creative Commons '
                     'Attribution-ShareAlike 4.0 International License.',
                     'Business Service List by Browne, C. and Culligan, B., is licensed under a Creative Commons '
                     'Attribution-ShareAlike 4.0 International License.',
                     'https://creativecommons.org/licenses/by-sa/4.0/', 'https://www.newgeneralservicelist.com/new-academic-word-list',
                     'https://www.newgeneralservicelist.com/business-service-list', 'Changes made by Flow',
                     'are licensed under CC BY-SA 4.0 as well'):
            self.assertIn(part, ngsl)
        ecdict = (DATA / 'ECDICT-LICENSE.txt').read_text(encoding='utf-8')
        self.assertIn('MIT License', ecdict); self.assertIn('Linwei', ecdict)

    def test_the_files_are_shipped(self):
        names = ('corpus_data/wordbooks-open.json', 'corpus_data/NGSL-LICENSE.txt', 'corpus_data/ECDICT-LICENSE.txt')
        copied = re.findall(r'for name in ([^;]+); do', (ROOT / 'upgrade.sh').read_text())[0].split()
        self.assertEqual([n for n in names if n not in copied], [])
        release = ROOT.parent / 'tools' / 'release-files.txt'
        if not release.exists():
            self.skipTest('release list is not part of an installed copy')
        listed = set(release.read_text().split())
        self.assertEqual([n for n in (*names, 'WORDBOOKS-OPEN.md', 'tests/test_wordbooks_open.py') if 'flow/' + n not in listed], [])


if __name__ == '__main__':
    unittest.main()
