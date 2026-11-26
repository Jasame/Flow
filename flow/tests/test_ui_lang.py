"""全英文界面 (docs/english-ui.md): the request's language, English error messages, the choice kept with the account, and
the front end's English tables read the way 00-i18n.js reads them."""
import json, os, re, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'flow'))
sys.path.insert(0, str(ROOT / 'tools'))
import app, next_service as nx, ui_lang  # noqa: E402
import check_i18n  # noqa: E402

HAN = re.compile('[㐀-鿿豈-﫿]')
SRC = ROOT / 'flow' / 'public' / 'src' / 'next'


class RequestLanguageTests(unittest.TestCase):
    def tearDown(self):
        ui_lang.use(None)

    def test_chinese_unless_the_page_says_english(self):
        for h in (None, '', 'zh', 'fr', 'EN-us', 'en-GB'):
            ui_lang.use(h)
            self.assertEqual(ui_lang.lang(), 'zh', h)
            self.assertEqual(ui_lang.L('复习', 'Review'), '复习')
        for h in ('en', 'EN', ' en '):
            ui_lang.use(h)
            self.assertEqual(ui_lang.L('复习', 'Review'), 'Review')

    def test_error_messages_get_their_english(self):
        ui_lang.use('en')
        self.assertEqual(ui_lang.answer({'error': '材料不存在'}), {'error': 'Text not found'})
        self.assertEqual(ui_lang.answer({'error': '一句没人写过的话', 'code': 'x'}), {'error': '一句没人写过的话', 'code': 'x'})  # kept
        self.assertEqual(ui_lang.answer({'ok': True}), {'ok': True})
        ui_lang.use('zh')
        self.assertEqual(ui_lang.answer({'error': '材料不存在'}), {'error': '材料不存在'})

    def test_numbers_and_plurals(self):
        table = {'最多 {n} 个词': 'Up to {1} {1|word|words}', '还剩 {n} 次，{n} 点重置': '{1} left, resets at {2}'}
        self.assertEqual(ui_lang.english('最多 1 个词', table), 'Up to 1 word')
        self.assertEqual(ui_lang.english('最多 30 个词', table), 'Up to 30 words')
        self.assertEqual(ui_lang.english('还剩 3 次，8 点重置', table), '3 left, resets at 8')
        self.assertIsNone(ui_lang.english('最多三个词', table))
        self.assertIsNone(ui_lang.english('No Chinese here', table))

    def test_the_error_table_is_chinese_to_english(self):
        for zh, en in ui_lang.ERRORS.items():
            self.assertTrue(HAN.search(zh), zh)
            self.assertFalse(HAN.search(en), (zh, en))
            self.assertEqual(zh, ' '.join(zh.split()), zh)  # looked up with spaces folded
            used = {int(i) for i in re.findall(r'\{(\d+)', en)}
            self.assertTrue(not used or max(used) <= zh.count('{n}'), (zh, en))


class AccountLanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'l.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def test_kept_with_the_account(self):
        self.assertEqual(nx.set_lang(self.c, 1, {'lang': 'en'}), ({'lang': 'en', 'kept': False}, 200))  # no profile yet
        nx.save_profile(self.c, 1, {'level': 'B1'})
        self.assertEqual(nx.profile(self.c, 1)['lang'], 'zh')  # Chinese by default
        self.assertEqual(nx.set_lang(self.c, 1, {'lang': 'fr'})[1], 400)
        self.assertEqual(nx.set_lang(self.c, 1, {'lang': 'en'}), ({'lang': 'en', 'kept': True}, 200))
        nx.save_profile(self.c, 1, {'level': 'B2'})  # other settings saved later keep it
        self.assertEqual(nx.profile(self.c, 1)['lang'], 'en')
        self.assertEqual(nx.post(self.c, 1, '/api/next/lang', {'lang': 'zh'}), ({'lang': 'zh', 'kept': True}, 200))


class HttpLanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'h.db'); self.p.start()
        app.init()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.p.stop(); self.tmp.cleanup()

    def get(self, path, lang=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', headers={'X-Flow-Lang': lang} if lang else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_an_english_page_gets_english_errors_and_the_next_request_does_not(self):
        self.assertEqual(self.get('/api/no-such-thing', 'en'), (404, {'error': 'Not found'}))
        self.assertEqual(self.get('/api/no-such-thing'), (404, {'error': '接口不存在'}))  # the same thread, Chinese again


def tables():
    """[(file, key, value)] from the enTable({...}) parts, read with check_i18n's reader."""
    rows = []
    for f in sorted(SRC.glob('01-en-*.js')):
        src = f.read_text(encoding='utf-8')
        found = check_i18n.strings(src)
        for (k, _, _, kend), (v, _, vst, _) in zip(found, found[1:]):
            if src[kend:vst].strip() == ':':
                rows.append((f.name, k.replace("\\'", "'"), v.replace("\\'", "'")))
    return rows


class FrontTableTests(unittest.TestCase):
    def test_tables_read_the_way_the_page_reads_them(self):
        rows = tables()
        self.assertGreater(len(rows), 20)
        seen = {}
        for f, zh, en in rows:
            self.assertTrue(HAN.search(zh), (f, zh))
            self.assertTrue(en.strip(), (f, zh))
            slots = zh.count('{n}') + zh.count('{x}')
            used = {int(i) for i in re.findall(r'\{(\d+)', en)}
            self.assertTrue(not used or max(used) <= slots, (f, zh, en))  # every {k} has a number or {x} to fill it
            # English that keeps Chinese is only the marks that must stay (AI marks, the name)
            if HAN.search(en):
                self.assertRegex(en, r'^(语流 Flow.*|.*AI 生成 · AI-generated|.*· AI voice)$', (f, zh, en))
            key = ' '.join(zh.split())
            self.assertFalse(key in seen and seen[key] != en, (f, zh, en, seen.get(key)))  # one Chinese, one English
            seen[key] = en

    def test_the_front_end_tells_the_server_its_language(self):
        head = (SRC / '00-head.js').read_text(encoding='utf-8')
        self.assertIn("opt.headers['X-Flow-Lang'] = 'en'", head)

    def test_english_never_comes_from_the_browser(self):
        js = (SRC / '00-i18n.js').read_text(encoding='utf-8') + (SRC / '07-lang.js').read_text(encoding='utf-8')
        self.assertNotIn('navigator.language', js)


if __name__ == '__main__':
    unittest.main()
