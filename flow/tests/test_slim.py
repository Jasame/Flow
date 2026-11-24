"""A lighter first open (slim.py): next.js and next.css go out without comments and indentation, with every literal
as written and every line where it was."""
import gzip, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, slim  # noqa: E402

PUBLIC = Path(app.ROOT) / 'public'


class JsTests(unittest.TestCase):
    def test_the_site_script_keeps_its_literals_and_lines(self):
        src = (PUBLIC / 'next.js').read_text(encoding='utf-8')
        before, after = [], []
        out = slim.js(src, before)
        self.assertEqual(slim.js(out, after), out)  # slimming twice changes nothing
        self.assertEqual(before, after)  # every string, template and regular expression exactly as written
        self.assertEqual(out.count('\n'), src.count('\n'))  # an error's line number is still the line in next.js
        self.assertLess(len(gzip.compress(out.encode())), len(gzip.compress(src.encode())) * 0.9)
        if shutil.which('node'):
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
                f.write(out)
            r = subprocess.run(['node', '--check', f.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[:500])

    def test_tricky_pieces(self):
        cases = {
            "const a = 4 / 2 / 1; // half\n": "const a = 4 / 2 / 1;\n",
            "x = s.replace(/\\/\\/ not a comment/g, '//');\n": "x = s.replace(/\\/\\/ not a comment/g, '//');\n",
            "if (/[/'\"]/.test(c)) go(); /* a /* note */\n": "if (/[/'\"]/.test(c)) go();\n",
            "return /a`b/.test(t)\n": "return /a`b/.test(t)\n",
            "const h = `<p>${a ? `<b>${'}'}</b>` : '/* kept */'}</p>   // kept`;\n": "const h = `<p>${a ? `<b>${'}'}</b>` : '/* kept */'}</p>   // kept`;\n",
            "    let x = a\n    ++b\n": "let x = a\n++b\n",  # the line break stays: x = a; ++b
            "a = b /* gap */ - -c\n": "a = b - -c\n",
            "f(a) / g(b)\n": "f(a) / g(b)\n",
            "const re = x => /\\d+/g\n": "const re = x => /\\d+/g\n",
        }
        for src, want in cases.items():
            self.assertEqual(slim.js(src), want, src)

    def test_a_broken_file_is_sent_as_it_is(self):
        self.assertEqual(slim.slim('next.js', b"const s = 'never closed\n"), b"const s = 'never closed\n")


class CssTests(unittest.TestCase):
    def test_comments_and_indentation_go_strings_stay(self):
        src = "/* head */\n.a{\n  content:'/* kept */';\n  color:red; /* note */\n}\n\n"
        self.assertEqual(slim.css(src), ".a{\ncontent:'/* kept */';\ncolor:red;\n}\n")
        site = (PUBLIC / 'next.css').read_text(encoding='utf-8')
        out = slim.css(site)
        self.assertEqual(slim.css(out), out)
        self.assertEqual(out.count('{'), site.count('{') - sum(c.count('{') for c in __import__('re').findall(r'/\*.*?\*/', site, __import__('re').S)))


if __name__ == '__main__':
    unittest.main()
