"""The 操作指南 stays in step with the site: every page a learner can open is explained, every picture exists, the PDF
was made from the current text, and every file ships. When one of these fails after a change to the site, update
flow/public/guide/guide.md (and run tools/guide_shots.py for new pictures) in the same change.

The PDF and its manifest.json are not kept in git: they are printed when a commit is released (tools/build_release.py),
and that build runs this file with FLOW_REQUIRE_BUILT=1 on the files about to ship. CI prints them before the tests too.
On a laptop that has not run tools/build_release.py --here, the tests of the PDF itself are skipped."""
import hashlib, json, os, re, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import user_guide as ug  # noqa: E402

SRC = ROOT / 'public' / 'src' / 'next'


def built():
    """Whether the PDF and its manifest are here; missing is a failure where they must have been built (CI, a release)."""
    if ug.PDF.is_file() and ug.MANIFEST.is_file():
        return True
    if os.getenv('FLOW_REQUIRE_BUILT') or os.getenv('CI'):
        raise AssertionError('the guide PDF was not built: python3 tools/build_release.py --here')
    return False
# pages that need an id and are reached from pages the guide explains (a material from 今日 / 全部材料, a 连载 story)
DYNAMIC = {'m', 'series', 'class', 'two'}  # class: one page per class, for its teacher (我的 → 我的班级); two: one per text,
# opened from 今天的计划 on a 5-minute 表达日 (the guide explains it there)


def routes():
    """The page names the router knows (02-shell.js), '' being 今日."""
    shell = (SRC / '02-shell.js').read_text(encoding='utf-8')
    return set(re.findall(r"name === '([a-z]+)'", shell)) | {''}


class GuideContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = ug.parse()
        cls.links = [l for ch in cls.g['chapters'] for l in ch['links']]
        cls.text = ' '.join(ch['text'] for ch in cls.g['chapters'])

    def test_the_guide_has_its_chapters_with_unique_ids_and_a_date(self):
        ids = [ch['id'] for ch in self.g['chapters']]
        self.assertGreaterEqual(len(ids), 12)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertRegex(self.g['updated'], r'\d{4}-\d{2}-\d{2}')
        for ch in self.g['chapters']:
            self.assertGreater(len(ch['text']), 120, ch['id'])

    def test_every_page_of_the_site_is_explained_in_the_guide(self):
        linked = {l[2:].split('/')[0] for l in self.links}
        missing = routes() - DYNAMIC - linked
        self.assertFalse(missing, f'add these pages to guide.md (a [去看看](#/…) line in the right chapter): {sorted(missing)}')

    def test_every_link_in_the_guide_opens_a_real_page(self):
        known = routes()
        for l in self.links:
            self.assertIn(l[2:].split('/')[0], known, l)

    def test_every_tile_of_the_practice_hub_and_every_tab_is_in_the_guide(self):
        hub = (SRC / '49-practice.js').read_text(encoding='utf-8')
        for href, title in re.findall(r"\['(#/[^']*)', '([^']+)'", hub):
            self.assertIn(href, self.links + ['#/'], f'练习 tile {title} ({href}) is not linked from the guide')
        tabs = re.findall(r'data-nav="[a-z]+">.*?<span>([^<]+)</span>', (ROOT / 'public' / 'next.html').read_text(encoding='utf-8'))
        self.assertEqual(tabs, ['今日', '练习', '单词', '我的'])  # r20: the grammar map moved into 练习
        tab_chapter = next(ch for ch in self.g['chapters'] if ch['id'] == 'tabs')
        for t in tabs:
            self.assertIn(t, tab_chapter['text'], f'tab {t} is missing from the 底部标签 chapter')

    def test_keyboard_shortcuts_in_the_guide_match_the_shortcut_sheet(self):
        shell = (SRC / '02-shell.js').read_text(encoding='utf-8')
        sheet = shell[shell.index("const rows = [['通用'"):shell.index('openSheet(', shell.index("const rows = [['通用'"))]
        for desc in re.findall(r"\['[^']+', '([^']+)'\]", sheet):
            self.assertIn(desc.replace('这张', ''), self.text, f'shortcut "{desc}" is not in the 键盘 chapter')

    def test_every_picture_exists_and_no_stray_picture_is_left(self):
        used = {s for ch in self.g['chapters'] for s in ch['shots']}
        for s in used:
            self.assertTrue((ug.DIR / f'{s}.jpg').is_file(), f'missing screenshot {s}.jpg: run tools/guide_shots.py')
        stray = {p.stem for p in ug.DIR.glob('*.jpg')} - used
        self.assertFalse(stray, f'screenshots no longer used by guide.md: {sorted(stray)}')

    def test_the_pdf_was_made_from_the_current_text_and_pictures(self):
        if not built():
            self.skipTest('the guide PDF is printed at release (python3 tools/build_release.py --here makes it here)')
        m = json.loads(ug.MANIFEST.read_text())
        self.assertEqual(m['source_sha256'], ug.source_hash(), 'guide.md changed: run python3 tools/build_release.py --here')
        self.assertEqual(m['pdf_sha256'], hashlib.sha256(ug.PDF.read_bytes()).hexdigest())
        for s, h in m['shots'].items():
            self.assertEqual(h, hashlib.sha256((ug.DIR / f'{s}.jpg').read_bytes()).hexdigest(), f'{s}.jpg changed: run python3 tools/build_release.py --here')
        self.assertTrue(ug.PDF.read_bytes().startswith(b'%PDF-'))
        self.assertLess(ug.PDF.stat().st_size, 8_000_000)

    def test_every_guide_file_ships_with_a_release(self):
        listed = set((ROOT.parent / 'tools' / 'release-files.txt').read_text().split()) if (ROOT.parent / 'tools' / 'release-files.txt').exists() else None
        if listed is None:
            self.skipTest('release list is not part of an installed copy')
        for p in [ROOT / 'user_guide.py', *ug.DIR.iterdir()]:
            self.assertIn(p.relative_to(ROOT.parent).as_posix(), listed)
        self.assertIn('user_guide.py', (ROOT / 'upgrade.sh').read_text())


class GuideRenderingTests(unittest.TestCase):
    def test_markup_is_escaped_and_the_subset_renders(self):
        g = ug.parse('% T\n% 更新于 2026-01-01\n# 一章 {#one}\n\n第一段 <script>x</script> **粗** `K`\n\n1. 第一步\n   - 小点\n2. 第二步\n\n'
                     '> 提示：<b>\n\n| 键 | 作用 |\n| --- | --- |\n| ? | 帮助 |\n\n![图](shot:today)\n\n[去看看](#/easy)\n')
        h = g['chapters'][0]['html']
        self.assertNotIn('<script>', h); self.assertIn('&lt;script&gt;', h)
        self.assertIn('<b>粗</b>', h); self.assertIn('<kbd>K</kbd>', h)
        self.assertIn('<ol><li>第一步<ul><li>小点</li></ul></li><li>第二步</li></ol>', h)
        self.assertIn('<div class="tip">提示：&lt;b&gt;</div>', h)
        self.assertIn('<td>?</td><td>帮助</td>', h)
        self.assertIn('src="/guide/today.jpg"', h)
        self.assertIn('href="#/easy"', h)
        self.assertEqual(g['chapters'][0]['links'], ['#/easy']); self.assertEqual(g['chapters'][0]['shots'], ['today'])

    def test_a_command_block_is_kept_as_written_and_escaped(self):
        h = ug.parse('# 章 {#a}\n\n运行：\n\n```\npython3 app.py --reset-link <名字>\n```\n\n之后\n')['chapters'][0]['html']
        self.assertIn('<pre class="cmd"><code>python3 app.py --reset-link &lt;名字&gt;</code></pre>', h)
        self.assertIn('<p>之后</p>', h)

    def test_text_before_the_first_chapter_is_refused(self):
        with self.assertRaises(ValueError):
            ug.parse('stray line\n# 章 {#a}\n')

    def test_the_api_offers_the_pdf_only_when_it_matches_the_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf, m = Path(tmp) / 'flow-guide.pdf', Path(tmp) / 'manifest.json'
            with patch.object(ug, 'PDF', pdf), patch.object(ug, 'MANIFEST', m):
                for made, source, offered in ((False, ug.source_hash(), None), (True, ug.source_hash(), '/guide.pdf'), (True, 'old', None)):
                    pdf.unlink(missing_ok=True)
                    if made:
                        pdf.write_bytes(b'%PDF-1.4 test')
                    m.write_text(json.dumps({'source_sha256': source}))
                    ug._CACHE.clear()
                    self.assertEqual(ug.api()['pdf'], offered, (made, source))
        ug._CACHE.clear()


class GuideHttpTests(unittest.TestCase):
    def setUp(self):
        import app
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'g.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'}); self.env.start()
        app.SECURE = False
        app.init()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', timeout=10) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_the_guide_its_pictures_and_the_pdf_are_served_without_signing_in(self):
        ug._CACHE.clear()
        st, body, _ = self.get('/api/next/guide')
        self.assertEqual(st, 200)
        g = json.loads(body)
        self.assertGreaterEqual(len(g['chapters']), 12)
        st, body, h = self.get('/guide/today.jpg')
        self.assertEqual(st, 200); self.assertEqual(h['Content-Type'], 'image/jpeg'); self.assertTrue(body.startswith(b'\xff\xd8'))
        st, body, h = self.get('/guide.pdf')
        if not built():  # no PDF here: the guide offers none and the address answers 404
            self.assertIsNone(g['pdf']); self.assertEqual(st, 404)
            return
        self.assertEqual(g['pdf'], '/guide.pdf')
        self.assertEqual(st, 200); self.assertEqual(h['Content-Type'], 'application/pdf'); self.assertTrue(body.startswith(b'%PDF-'))
        self.assertIn('inline', h['Content-Disposition'])

    def test_only_guide_pictures_can_be_fetched(self):
        for path in ('/guide/guide.md', '/guide/manifest.json', '/guide/../app.py', '/guide/%2e%2e/app.py', '/guide/nope.jpg', '/guide/a.b.jpg', '/guide/../../etc/passwd.jpg'):
            st, _, _ = self.get(path)
            self.assertEqual(st, 404, path)


class FrontEndPartsTests(unittest.TestCase):
    def test_no_two_parts_declare_the_same_function(self):
        """The parts are joined into one script, so a second declaration silently replaces the first."""
        names = re.findall(r'^  (?:async )?function ([A-Za-z0-9_]+)', ''.join(p.read_text(encoding='utf-8') for p in sorted(SRC.glob('*.js'))), re.M)
        dupes = sorted({n for n in names if names.count(n) > 1})
        self.assertFalse(dupes, dupes)


if __name__ == '__main__':
    unittest.main()
