"""Interview tags (Q:, A:) are shown on the page but never read aloud, like speaker labels (Tom:, Mr Patel:).
2026-11-26: the Whisper self-check found 15 interviews whose recordings said the letter "Q" before every question."""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEXT = ROOT / 'flow' / 'public' / 'src' / 'next'
# every place that takes the label off a line before it is read, heard or compared
READ_ALOUD = {
    ROOT / 'flow' / 'next_service.py': r"re\.sub\(r'(\^[^']+)', ''",
    NEXT / '21-study-listen.js': r'const stripLabel = s => s\.replace\(/(\^[^/]+)/',
    NEXT / '24-study-output.js': r'lines\(\)\.map\(s => s\.replace\(/(\^[^/]+)/',
    NEXT / '48-radar.js': r'p\.body\.replace\(/(\^[^/]+)/gm',
}


def patterns():
    for path, finder in READ_ALOUD.items():
        text = path.read_text(encoding='utf-8')
        found = [m.group(1) for m in re.finditer(finder, text) if ':' in m.group(1)]
        yield path.name, found


class NarrationTagTests(unittest.TestCase):
    def test_each_place_that_reads_a_line_drops_speaker_labels_and_interview_tags(self):
        for name, found in patterns():
            self.assertTrue(found, f'{name}: the label pattern was not found (moved? update this test)')
            for pat in found:
                rx = re.compile(pat.replace('\\s', r'\s'))
                for line, said in [('Q: So what changed?', 'So what changed?'), ('A: Completely.', 'Completely.'),
                                   ('Tom: Have you got a minute?', 'Have you got a minute?'),
                                   ('Mr Patel: Sit down, please.', 'Sit down, please.'),
                                   ('Sure.', 'Sure.'), ('At 3: 15 we left.', 'At 3: 15 we left.')]:
                    self.assertEqual(rx.sub('', line, count=1), said, f'{name}: {line!r}')

    def test_the_recordings_skip_the_tag_and_keep_the_voice(self):
        src = (ROOT / 'tools' / 'gen_audio.py').read_text(encoding='utf-8')
        tag = re.compile(re.search(r"TAG = re\.compile\(r'([^']+)'\)", src).group(1))
        label = re.compile(re.search(r"LABEL = re\.compile\(r'([^']+)'\)", src).group(1))
        self.assertEqual(tag.match('Q: So what changed?').end(), 3)
        self.assertIsNone(label.match('Q: So what changed?'))   # not a speaker: the voice stays as it is
        self.assertIsNone(tag.match('Tom: Hi.'))
        self.assertIn('elif TAG.match(s):', src)
        self.assertIn('start_char = TAG.match(s).end()', src)


if __name__ == '__main__':
    unittest.main()
