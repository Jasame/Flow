"""The front end runs on the Safari of older iPhones and iPads too (iOS 15 on an iPhone 7 or an iPad Air 2, 16.0–16.3
not yet updated). One regex with lookbehind made all of next.js a syntax error there (2026-11-25: 「正在打开…」 and
nothing else, on iPhones and iPads; fine on Android), so no script part may use one."""
import re, unittest
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / 'public'
LOOKBEHIND = re.compile(r'\(\?<[=!]')


class OlderSafariTests(unittest.TestCase):
    def test_no_regex_lookbehind_in_any_script_safari_before_16_4_cannot_parse_it(self):
        files = sorted(PUBLIC.glob('src/next/*.js')) + sorted(PUBLIC.glob('*.js'))
        self.assertTrue(files)
        bad = [f'{f.relative_to(PUBLIC)}:{n}' for f in files for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1) if LOOKBEHIND.search(line)]
        self.assertEqual(bad, [], 'a regex lookbehind (?<= or (?<! stops all of next.js on Safari before iOS 16.4: ' + ', '.join(bad))


if __name__ == '__main__':
    unittest.main()
