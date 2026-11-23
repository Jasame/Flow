"""专四 / 专八 word books: corpus_data/wordbooks.json, built by tools/build_wordbooks.py (method in WORDBOOKS.md)."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import next_service as nx  # noqa: E402

FILE = ROOT / 'corpus_data' / 'wordbooks.json'
# 《高等学校英语专业英语教学大纲》(2000): 四级 认知词汇 5,500–6,500, 八级 10,000–12,000 (专四 + 专八 together)
SIZES = {'tem4': (5500, 6500), 'tem8': (3500, 6500), 'together': (10000, 12000)}
WORD = re.compile(r'[a-z]+(?:-[a-z]+)*')


class WordbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(FILE.read_text(encoding='utf-8'))
        cls.books = cls.doc['books']
        cls.d = nx.dictionary()

    def words(self, book):
        return self.books[book]['words']

    def test_shape_ids_titles_and_groups(self):
        self.assertEqual(set(self.doc), {'notice', 'books'})
        for part in ('ECDICT', 'MIT', 'not an official'):
            self.assertIn(part, self.doc['notice'])
        self.assertEqual(list(self.books), ['tem4', 'tem8'])
        for book, title in (('tem4', '专四词汇'), ('tem8', '专八词汇')):
            b = self.books[book]
            self.assertEqual(set(b), {'title', 'group', 'blurb', 'basis', 'words'})
            self.assertEqual((b['title'], b['group']), (title, '英语专业'))
            for field in ('blurb', 'basis'):
                self.assertIsInstance(b[field], str)
                self.assertTrue(b[field].strip())
            self.assertLessEqual(len(b['blurb']), 40)  # one line in the book picker
            self.assertIn('按考纲词汇量要求自编，不是官方词表', b['basis'])
            self.assertIsInstance(b['words'], list)

    def test_words_are_plain_unique_and_the_books_do_not_overlap(self):
        for book in self.books:
            w = self.words(book)
            self.assertEqual([x for x in w if not (isinstance(x, str) and WORD.fullmatch(x))], [])
            self.assertEqual(len(w), len(set(w)), f'{book} has duplicates')
        self.assertEqual(set(self.words('tem4')) & set(self.words('tem8')), set())

    def test_every_word_is_in_the_dictionary_with_a_chinese_meaning(self):
        for book in self.books:
            missing = [w for w in self.words(book) if not re.search(r'[一-鿿]', (self.d.get(w) or {}).get('meaning', ''))]
            self.assertEqual(missing, [], book)
            capitalised = [w for w in self.words(book) if self.d[w]['word'][:1].isupper()]
            self.assertEqual(capitalised, [], book)  # the same rule as vocab_service.book_words()

    def test_sizes_follow_the_syllabus(self):
        n4, n8 = len(self.words('tem4')), len(self.words('tem8'))
        for name, n in (('tem4', n4), ('tem8', n8), ('together', n4 + n8)):
            lo, hi = SIZES[name]
            self.assertTrue(lo <= n <= hi, f'{name}: {n} words, documented {lo}–{hi}')

    def test_study_order_is_most_frequent_first(self):
        for book in self.books:
            ranks = [self.d[w]['rank'] for w in self.words(book)]
            self.assertEqual(ranks, sorted(ranks), book)
        self.assertLess(self.d[self.words('tem4')[0]]['rank'], self.d[self.words('tem8')[0]]['rank'])

    def test_what_is_left_out(self):
        books = set(self.words('tem4')) | set(self.words('tem8'))
        for w in ('the', 'of', 'london', 'france', 'april', 'monday', 'oh', 'hello', 'fuck', 'increased', 'closest',
                  'twenty-five', 'long-term'):
            if w in self.d:
                self.assertNotIn(w, books)
        for pair in (('centre', 'center'), ('labour', 'labor'), ('towards', 'toward')):
            self.assertEqual(len(books & set(pair)), 1, pair)  # one spelling of each pair

    def test_the_exam_lists_are_covered(self):
        t4, t8 = set(self.words('tem4')), set(self.words('tem8'))
        for tag, book, share in (('cet4', t4, 0.95), ('cet6', t4 | t8, 0.95), ('ky', t4 | t8, 0.95)):
            listed = {k for k, e in self.d.items() if tag in e['tags']}
            self.assertGreater(len(listed & book) / len(listed), share, tag)
        for w in ('pronoun', 'plural', 'punctual', 'preposition'):  # rare in the frequency list, but CET-4 words
            self.assertIn(w, t4)
        for w in ('haughty', 'obstinate', 'ubiquitous', 'pragmatic'):
            self.assertIn(w, t4 | t8)

    def test_file_matches_a_fresh_build(self):
        tool = ROOT.parent / 'tools' / 'build_wordbooks.py'
        r = subprocess.run([sys.executable, str(tool), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)


if __name__ == '__main__':
    unittest.main()
