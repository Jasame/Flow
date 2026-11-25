"""r20: where a text comes from (one line under its title, the writing rules or the sources in a sheet, AI tags) and
putting Flow on the home screen (two steps for the phone in hand, one tap where the browser offers it)."""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import next_service as nx  # noqa: E402

SRC = ROOT / 'public' / 'src' / 'next'


class OriginTests(unittest.TestCase):
    def test_an_original_says_who_wrote_it_and_how_ai_helped(self):
        o = nx.origin({'id': 'v5-science-b2-x', 'source': 'Flow 编辑部原创'})
        self.assertEqual((o['kind'], o['label'], o['ai'], o['references']), ('original', 'Flow 编辑部原创', 'AI 辅助编写', []))
        o = nx.origin({'id': 'v5-life-a2-y', 'source': 'Flow 编辑部原创', 'ai': '', 'reviewed': True,
                       'references': [{'title': 'How noise cancelling works', 'url': 'https://example.org/anc'}, {'title': 'bad', 'url': 'http://x'}, 'junk']})
        self.assertEqual((o['ai'], o['reviewed']), ('', True))
        self.assertEqual(o['references'], [{'title': 'How noise cancelling works', 'url': 'https://example.org/anc'}])  # https links only
        self.assertEqual(nx.origin({'id': 'old-1', 'source': '早期练习'})['ai'], '')  # only the v5 corpus is marked as AI-assisted

    def test_news_is_marked_as_ai_rewritten_and_unreviewed_with_its_sources(self):
        o = nx.origin({'id': 'daily-2026-11-23', 'daily_day': '2026-11-23', 'source': 'Gemini 联网检索与教学改写 · 未经人工审核',
                       'provenance': {'sources': [{'title': 'A news site', 'url': 'https://news.example.com/a'}]}})
        self.assertEqual((o['kind'], o['ai'], o['reviewed']), ('news', 'AI 改写', False))
        self.assertEqual(o['references'], [{'title': 'A news site', 'url': 'https://news.example.com/a'}])

    def test_an_imported_text_is_the_learners_own_and_ai_questions_are_marked(self):
        self.assertEqual(nx.origin({'id': 'imp-1', 'imported': True, 'questions': []})['ai'], '')
        o = nx.origin({'id': 'imp-2', 'imported': True, 'questions': [{'q': 1}], 'source_url': 'https://example.org/article'})
        self.assertEqual((o['kind'], o['label'], o['ai'], o['url']), ('import', '我导入的文章', 'AI 出题', 'https://example.org/article'))

    def test_every_published_material_has_an_origin_in_its_payload(self):
        v5 = __import__('content_v50').v5_materials()
        self.assertGreater(len(v5), 200)
        self.assertTrue(all(nx.origin(p)['label'] for p in v5))


class FrontEndTests(unittest.TestCase):
    def test_the_study_header_shows_the_origin_and_the_sheet_has_the_writing_rules(self):
        js = (SRC / '20-study.js').read_text(encoding='utf-8')
        self.assertIn('${originHTML(m)}', js); self.assertIn('${offChip(id)}</div>', js)  # 存到手机: on the kicker line (sh-top) since the phone tidy-up  # r22: 存到手机 rides on the same line; self.assertIn('function originSheet(m)', js)
        for rule in ('不抄、不改写已有的文章', '不写具体的统计数字、年份、价格和研究结论', '不写在世的真实人物', '在原文里找得到依据'):
            self.assertIn(rule, js)
        spec = (ROOT / 'corpus_data' / 'v5' / 'SPEC.md').read_text(encoding='utf-8')
        for rule in ('不得复制、改写或拼贴', '不写具体统计数字、年份、价格、研究结论', '不写真实在世人物，不写时事新闻'):
            self.assertIn(rule, spec)  # the sheet says what the writing rules say
        self.assertIn('AI 改写）', (SRC / '22-study-read.js').read_text(encoding='utf-8'))

    def test_ai_written_texts_say_so_under_the_title_and_on_their_cards(self):
        # 「AI 生成」 (2026-11-25, 人工智能生成合成内容标识办法), in the shared style (aiMark / aiTag, 00-head.js)
        js = (SRC / '20-study.js').read_text(encoding='utf-8')
        for note in ("'经规范检查'", "'经规范检查 · 经人工审核'", "'AI 改写 · 未经人工审核'"):  # the user's words: 「AI 生成，经规范检查」
            self.assertIn(note, js)
        self.assertIn("o.reviewed_by_human ? '经规范检查 · 经人工审核' : '经规范检查'", js)  # 经人工审核 only when set
        self.assertIn("${note === null ? '' : m.featured ? aiCheckLink(aiMark(note)) : aiMark(note)}<div class=\"origin tiny\">", js)
        self.assertIn('href="#/guide/ai-check"', js)  # 「经规范检查」 says what is checked
        guide = (ROOT / 'public' / 'guide' / 'guide.md').read_text(encoding='utf-8')
        self.assertIn('## 「经规范检查」查什么 {#ai-check}', guide)
        self.assertIn('id="g-ai-check"', __import__('user_guide').parse(guide)['chapters'][[c['id'] for c in __import__('user_guide').parse(guide)['chapters']].index('study')]['html'])
        self.assertIn('aiMark(aiNote(m))', (SRC / '44-easy.js').read_text(encoding='utf-8'))
        for f in ('10-welcome-today.js', '44-easy.js'):
            self.assertIn("m.ai ? ' ' + aiTag() : ''", (SRC / f).read_text(encoding='utf-8'), f)
        self.assertIn('aiTag()', (SRC / '12-daily-line.js').read_text(encoding='utf-8'))
        lib = (SRC / '80-library.js').read_text(encoding='utf-8')
        self.assertIn('aiTag()', lib); self.assertIn("aiCheckLink(aiMark('经规范检查'))", lib)

    def test_reviewed_by_human_is_off_unless_the_user_read_the_text(self):
        v5 = __import__('content_v50').v5_materials()
        self.assertFalse(any(nx.origin(p)['reviewed_by_human'] for p in v5))  # nobody has been marked yet
        self.assertTrue(nx.origin(dict(v5[0], reviewed_by_human=True, reviewed_on='2026-11-26'))['reviewed_by_human'])
        self.assertFalse(nx.origin(dict(v5[0], reviewed_by_human='yes'))['reviewed_by_human'])  # only a real true
        sys.path.insert(0, str(ROOT.parent / 'tools'))
        cv = __import__('corpus_validate')
        p = dict(v5[0], spec='5.1', reviewed_by_human=True)
        self.assertTrue(any('reviewed_on' in e for e in cv.check_v51(p, p['body'], {'sentences': 14})[0]))
        p['reviewed_on'] = '2026-11-26'
        self.assertFalse(any('reviewed' in e for e in cv.check_v51(p, p['body'], {'sentences': 14})[0]))

    def test_cards_say_whether_flow_wrote_the_text_with_ai(self):
        v5 = __import__('content_v50').v5_materials()[0]
        self.assertTrue(nx._card(v5)['ai'])
        self.assertTrue(nx._card(dict(v5, id='daily-2026-11-25', daily_day='2026-11-25'))['ai'])
        self.assertTrue(nx._card({'id': 'graded-x', 'title': 't', 'level': 'A2', 'theme': 'life', 'body': 'A short text.'})['ai'])
        self.assertFalse(nx._card(dict(v5, id='imp-3', imported=True))['ai'])

    def test_the_install_guide_knows_the_phone_in_hand(self):
        js = (SRC / '81-me.js').read_text(encoding='utf-8')
        for words in ('底部中间', '添加到主屏幕', '右上角', 'Safari', '⋮', '安装应用', '安装到桌面', '在浏览器打开'):
            self.assertIn(words, js)
        self.assertIn("addEventListener('appinstalled'", js)
        self.assertIn('installNudgeDue(h)', (SRC / '10-welcome-today.js').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
