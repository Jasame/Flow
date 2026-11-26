"""更新记录 (updates_service.py): the learners' record of what each 语流 release changed, and 今日's 「语流更新了」 card.
The data is checked the way the ledger's rules say it is written: every change a learner notices, one plain sentence each,
no PR numbers or model names, links only to pages this site has, newest first; only the 内测版 sees what is on it and not
on 语流 yet."""
import json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import updates_service as us  # noqa: E402
import next_service  # noqa: E402

DATA = json.loads(us.FILE.read_text(encoding='utf-8'))
ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / 'public' / 'src' / 'next' / '02-shell.js').read_text(encoding='utf-8')
GUIDE = (ROOT / 'public' / 'guide' / 'guide.md').read_text(encoding='utf-8')
ROUTES = set(re.findall(r"name === '([a-z-]+)'", SHELL)) | {''}


def texts(e):
    return [i['text'] for g in us.GROUPS for i in us.items(e, g)] + ([e['note']] if e.get('note') else []) + list(e.get('highlights') or [])


def lines(e):
    """(text, link) for every line a learner reads; the note and the highlights have no link."""
    return [(i['text'], i.get('link', '')) for g in us.GROUPS for i in us.items(e, g)] + \
        [(s, '') for s in ([e['note']] if e.get('note') else []) + list(e.get('highlights') or [])]


class DataTests(unittest.TestCase):
    def test_each_release_is_a_few_plain_sentences_newest_first(self):
        rel = DATA['released']
        self.assertTrue(rel)
        nums = [int(re.fullmatch(r'r(\d+)', e['id']).group(1)) for e in rel]
        self.assertEqual(nums, sorted(nums, reverse=True), 'newest first, one entry per production release')
        self.assertEqual(len(nums), len(set(nums)))
        for e in rel:
            self.assertFalse(set(e) - {'id', 'date', 'label', 'note', 'highlights', *us.GROUPS}, e['id'])
            items = [i for g in us.GROUPS for i in us.items(e, g)]
            # every change a learner can notice is listed (r33 had 33); the cap only catches a pasted PR list
            self.assertTrue(1 <= len(items) <= 45, (e['id'], len(items)))
            for g in us.GROUPS:
                for x in e.get(g) or []:
                    link = x.get('link') if isinstance(x, dict) else None
                    if link:
                        self.assertRegex(link, us.LINK, e['id'])
                        name = link[2:].split('/')[0]
                        self.assertIn(name, ROUTES, f'{e["id"]}: 「去看看」 goes to a page the router knows: {link}')
                        if name == 'guide' and link.count('/') > 1:
                            self.assertIn('{#' + link.split('/')[2] + '}', GUIDE, f'{e["id"]}: the guide has that chapter: {link}')
            self.assertTrue(re.fullmatch(r'\d{4}-\d{2}-\d{2}', e['date']), e['id'])
            self.assertTrue(e['label'] and not re.search(r'\br\d+\b', e['label']), e['id'])  # the tag is never shown
            self.assertTrue(1 <= len(e.get('highlights') or []) <= 3, e['id'])  # a one-fix hotfix has one
            for s, link in lines(e):
                self.assertIsNone(us.too_technical(s, link), f'{e["id"]}: no PR numbers, tags or model names for learners: {s}')
                self.assertLessEqual(len(s), 90, f'{e["id"]}: one sentence, not a paragraph: {s}')
            for s in e['highlights']:
                self.assertLessEqual(len(s), 30, f'{e["id"]}: a highlight fits one line on a phone: {s}')

    def test_the_beta_block_is_plain_words_too(self):
        for s, link in lines(DATA.get('beta') or {}):
            self.assertIsNone(us.too_technical(s, link), s)

    def test_only_a_privacy_line_may_name_the_ai_vendors(self):
        self.assertIsNone(us.too_technical('隐私说明补上了以前用过、已经停用的谷歌 Gemini。', '#/guide/privacy'))
        self.assertIsNotNone(us.too_technical('朗读换成了 CosyVoice 的声音。', '#/library'))
        self.assertIsNotNone(us.too_technical('隐私说明改了，见 #411。', '#/guide/privacy'))  # never a PR number


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop('FLOW_UPDATES_FILE', None)
        os.environ.pop('FLOW_CHANNEL', None)
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def use(self, data):
        p = Path(self.tmp.name) / 'updates.json'
        p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.environ['FLOW_UPDATES_FILE'] = str(p)

    def test_the_card_gets_the_newest_release_and_at_most_three_highlights(self):
        self.use({'released': [{'id': 'r2', 'label': '今天', 'new': ['a', 'b'], 'highlights': ['1', '2', '3', '4']},
                               {'id': 'r1', 'label': '昨天', 'fixed': ['c']}]})
        self.assertEqual(us.latest(), {'id': 'r2', 'label': '今天', 'highlights': ['1', '2', '3']})
        self.use({'released': [{'id': 'r3', 'label': '今天', 'new': ['a'], 'better': ['b']}]})  # no highlights: the first lines
        self.assertEqual(us.latest()['highlights'], ['a', 'b'])

    def test_only_the_beta_sees_what_is_not_on_its_way_to_yu_liu_yet(self):
        self.use({'released': [{'id': 'r1', 'label': '昨天', 'new': ['a']}], 'beta': {'date': '2026-11-25', 'new': ['内测的'], 'better': [], 'fixed': []}})
        self.assertIsNone(us.listing()['beta'])
        os.environ['FLOW_CHANNEL'] = 'beta'
        self.assertEqual(us.listing()['beta']['new'], [{'text': '内测的'}])
        self.use({'released': [], 'beta': {'new': [], 'better': [], 'fixed': []}})
        self.assertIsNone(us.listing()['beta'], 'an empty 内测中 card is not shown')

    def test_a_file_written_twice_in_a_row_is_read_again(self):
        p = Path(self.tmp.name) / 'updates.json'
        os.environ['FLOW_UPDATES_FILE'] = str(p)
        for label in ('一一', '二二', '三三'):  # the same size each time, and as quick as the disk allows
            p.write_text(json.dumps({'released': [{'id': 'r1', 'label': label, 'new': ['a']}]}, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(us.load()['released'][0]['label'], label)
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns - 10_000_000_000))  # an old file: from the cache
        self.assertEqual(us.load()['released'][0]['label'], '三三')

    def test_no_file_or_a_broken_one_is_no_updates_not_an_error(self):
        os.environ['FLOW_UPDATES_FILE'] = str(Path(self.tmp.name) / 'missing.json')
        self.assertEqual(us.listing(), {'released': [], 'beta': None})
        self.assertIsNone(us.latest())
        p = Path(self.tmp.name) / 'broken.json'
        p.write_text('{', encoding='utf-8')
        os.environ['FLOW_UPDATES_FILE'] = str(p)
        self.assertIsNone(us.latest())

    def test_the_page_reads_it_through_the_learning_api(self):
        self.use({'released': [{'id': 'r1', 'label': '昨天', 'changed': [{'text': '按钮换了位置', 'link': '#/me'}],
                                'new': ['a', {'text': 'b', 'link': 'https://example.com/'}], 'note': '提醒'}]})
        out, status = next_service.get(None, None, '/api/next/updates', {})
        self.assertEqual(status, 200)
        self.assertEqual(out['released'][0], {'id': 'r1', 'label': '昨天', 'changed': [{'text': '按钮换了位置', 'link': '#/me'}],
                                              'new': [{'text': 'a'}, {'text': 'b'}], 'better': [], 'fixed': [], 'note': '提醒'})  # links leave nothing but this site
        self.assertIn("'update': __import__('updates_service').latest()", Path(next_service.__file__).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
