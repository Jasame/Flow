"""「AI 生成」标识 (2026-11-25, 《人工智能生成合成内容标识办法》): every page part that asks an AI endpoint for something
the learner then reads shows the mark (aiTag() / aiMark(note) from 00-head.js). The endpoints come from the server's own
list (next_service.AI_PATHS), so a new AI feature fails here until its page marks what the AI wrote."""
import ast, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'public' / 'src' / 'next'
# parts that call an AI endpoint but show nothing it wrote (the result shows elsewhere, with the mark)
SHOWS_NOTHING = {'71-import.js': '只是开始出题；题目在 23-study-check.js 里显示，那里有标识'}


def ai_paths():
    tree = ast.parse((ROOT / 'next_service.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'AI_PATHS' for t in node.targets):
            return [e.value for e in node.value.elts]
    raise AssertionError('next_service.AI_PATHS not found')


def calls(text, path):
    """Does this part ask this endpoint? Literally ('/api/next/explain'), or by its parent ('/api/next/assess/' + kind)."""
    parent = path.rsplit('/', 1)[0] + '/'
    return bool(re.search(re.escape("'" + path) + r"['?]", text)) or ("'" + parent + "' +") in text


class AiMarkTests(unittest.TestCase):
    def test_the_mark_and_its_style_exist(self):
        head = (SRC / '00-head.js').read_text(encoding='utf-8')
        self.assertIn('function aiTag()', head)
        self.assertIn('function aiMark(note)', head)
        self.assertIn('>AI 生成<', head)
        # synthesized voices (2026-11-25): one grey line where they play, a faint 「AI」 on each of many speakers
        self.assertIn('function aiVoiceNote(text, tag, cls)', head)
        self.assertIn('function aiBadge()', head)
        css = (SRC / '99-ai-mark.css').read_text(encoding='utf-8')
        self.assertIn('.ai-mark{', css)
        self.assertIn('.ai-line{', css)
        self.assertIn('.ai-voice-note{', css)
        self.assertIn('.ai-badge{', css)

    def test_every_part_that_plays_a_synthetic_voice_says_so(self):
        """Every page part that plays a synthesized voice (a word, an example, a sentence, a whole text, the mini player)
        calls aiVoiceNote: 语流 B7's minimum (《标识办法》) — said where the voice plays, without a tap, ≥12px, 4.5:1. A new
        part that plays one fails here until it says so. The learner's own recording (CLIP.mine) is not synthetic."""
        plays = re.compile(r'\b(?:CLIP\.(?:word|sentence)|TTS\.say|SV\.say|NAR\.play|LONG\.start|MINI\.show)\(')
        missing, checked = [], 0
        for part in sorted(SRC.glob('*.js')):
            text = part.read_text(encoding='utf-8')
            if not plays.search(text):
                continue
            checked += 1
            if 'aiVoiceNote(' not in text:
                missing.append(part.name)
        self.assertGreater(checked, 10)
        self.assertEqual(missing, [], '这些页面会放合成的声音，但没有「AI 合成」提示（aiVoiceNote）')

    def test_what_the_voice_line_says(self):
        """Each line says 「AI」 and 「合成」, or 「AI 朗读」 (B7); the old pill by every button is gone."""
        said = []
        for part in sorted(SRC.glob('*.js')):
            text = part.read_text(encoding='utf-8')
            self.assertNotIn('aiVoice()', text, part.name)
            for t in re.findall(r"aiVoiceNote\('([^']*)'", text):
                said.append(t)
                self.assertTrue('AI 朗读' in t or ('AI' in t and '合成' in t), f'{part.name}: 「{t}」')
        self.assertGreater(len(said), 15)
        css = (SRC / '99-ai-mark.css').read_text(encoding='utf-8')
        size = re.search(r'\.ai-voice-note\{[^}]*font-size:(\d+)px', css)
        self.assertTrue(size and int(size.group(1)) >= 12, 'the line is at least 12px')
        badge = re.search(r'\.ai-badge\{[^}]*font:\d+ (\d+)px', css)
        self.assertTrue(badge and int(badge.group(1)) >= 10, 'the badge is at least 10px')

    def test_every_page_part_that_shows_ai_output_marks_it(self):
        paths = ai_paths()
        self.assertGreater(len(paths), 5)
        missing, checked = [], 0
        for part in sorted(SRC.glob('*.js')):
            text = part.read_text(encoding='utf-8')
            used = [p for p in paths if calls(text, p)]
            if not used or part.name in SHOWS_NOTHING:
                continue
            checked += 1
            if not re.search(r'\bai(Mark|Tag)\(', text):
                missing.append(f'{part.name}: {used}')
        self.assertGreater(checked, 5)
        self.assertEqual(missing, [], '这些页面用了 AI 接口，但没有「AI 生成」标识')

    def test_the_exemptions_still_call_ai_and_show_nothing_of_it(self):
        paths = ai_paths()
        for name in SHOWS_NOTHING:
            text = (SRC / name).read_text(encoding='utf-8')
            self.assertTrue(any(calls(text, p) for p in paths), name + ' no longer calls an AI endpoint: drop it from SHOWS_NOTHING')


if __name__ == '__main__':
    unittest.main()
