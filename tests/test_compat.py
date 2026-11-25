"""tools/check_compat.py: the served scripts still run in Safari 15.0 (iOS 15). A lookbehind in one regular expression
made next.js fail to parse before Safari 16.4 (2026-11-25: a teacher's iPhone on iOS 16.1 showed nothing)."""
import importlib.util, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_compat', ROOT / 'tools' / 'check_compat.py')
cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)


def found(src):
    return [what for line, col, what, ver in cc.findings(src)]


class CompatTests(unittest.TestCase):
    def test_a_lookbehind_is_found_in_a_literal_or_a_string_but_not_in_a_comment(self):
        self.assertTrue(found('const f = s => s.split(/(?<=[.!?])\\s+/);'))
        self.assertTrue(found('new RegExp("(?<!x)y")'))
        self.assertTrue(found('const r = `(?<=a)b`;'))
        self.assertEqual(found('// no (?<= lookbehind here, Safari 15 cannot parse it\nconst a = 1;'), [])
        self.assertEqual(found('/* (?<!x) */ x = 2'), [])

    def test_the_line_and_column_point_at_it(self):
        (line, col, what, ver), = cc.findings('a = 1;\n  b = /(?<=x)y/.test(c);\n')
        self.assertEqual((line, col, ver), (2, 8, '16.4'))  # at the (?<= itself

    def test_a_method_of_our_own_with_the_same_name_is_not_array_at(self):
        self.assertEqual(found('const i = PROG.at(PKEY, ls.length);'), [])
        self.assertTrue(found('const last = words.at(-1);'))
        self.assertTrue(found('s.at( 0)'))

    def test_newer_built_ins_and_syntax_are_found_in_code_only(self):
        for src in ('Object.hasOwn(o, "k")', 'const c = structuredClone(x)', 'a.findLast(f)', 'a.toSorted()',
                    'class A { static { init() } }', 'Object.groupBy(a, f)', '/x/v.test(s)'):
            self.assertTrue(found(src), src)
        self.assertEqual(found('class A { static size = 1; static of(x) { return x } }'), [])
        self.assertEqual(found('const help = "Object.hasOwn( and structuredClone( are Safari 15.4";'), [])

    def test_the_built_ins_past_chrome_114_are_found_too(self):
        # HarmonyOS 5.0–5.1's browser and ArkWeb are Chromium 114 (语流 C4); these are past Safari 15 as well
        for src in ('URL.canParse(u)', 'AbortSignal.any([a, b])', 'Promise.try(f)', 'await scheduler.yield()',
                    'Uint8Array.fromBase64(s)', 'RegExp.escape(s)', 'a.union(new Set([1]))', 'new Set(x).isSubsetOf(y)'):
            self.assertTrue(found(src), src)
        self.assertEqual(found('graph.union(a, b); tags.difference(other)'), [])  # not known to be Sets: not taken for them

    def test_division_is_not_a_regular_expression(self):
        self.assertEqual(found('const r = a / b / c, s = (x) / 2, t = arr[0] / n;'), [])
        self.assertEqual(found('const w = total / count; const v = n / (?<=0 ? 1 : 2);'.replace('(?<=0', '(m')), [])

    def test_template_literals_with_code_inside(self):
        src = 'const h = `<p>${ items.map(i => `<i>${ {a: 1}.a }</i>`).join("") }</p>`; const z = q.at(-1);'
        self.assertEqual(found(src), ['Array.prototype.at / String.prototype.at with a number'])

    def test_a_line_marked_compat_ok_passes(self):
        self.assertEqual(found('const r = /(?<=x)y/;  // compat-ok: only on the 内测版 console, Safari 17 there'), [])

    def test_css_needs_a_plain_value_before_a_newer_one_and_a_word_on_a_newer_selector(self):
        css = lambda s: [w for line, col, w, v in cc.css_findings(s)]
        self.assertTrue(css('.bar{background:color-mix(in srgb,var(--bg) 76%,transparent)}'))
        self.assertEqual(css('.bar{background:var(--bg);background:color-mix(in srgb,var(--bg) 76%,transparent)}'), [])
        self.assertEqual(css('.x{--tint:color-mix(in srgb,red 10%,white)}'), [])  # a custom property: its users fall back
        self.assertTrue(css('main{min-height:100dvh}'))
        self.assertEqual(css('main{min-height:100vh;min-height:100dvh}'), [])
        self.assertTrue(css('.row:has(.on){flex-wrap:nowrap}'))
        self.assertEqual(css('.row:has(.on){/* compat-ok: before iOS 15.4 it may wrap */flex-wrap:nowrap}'), [])
        self.assertEqual(css('@supports not (background:color-mix(in srgb,red 50%,blue)){.cal i{opacity:.5}}'), [])
        self.assertEqual(css('/* never color-mix( here */ .a{color:red}'), [])
        self.assertTrue(css('@media (max-width:759px){.tabs{background:color-mix(in srgb,var(--paper) 72%,transparent)}}'))
        self.assertTrue(css('.card{color:red; & .t{color:blue}}') or css('.card .t{} .x & .y{color:blue}'))

    def test_every_served_script_is_checked_and_the_check_runs_wherever_scripts_are_checked(self):
        names = {p.name for p in cc.SCRIPTS}
        self.assertIn('99-boot.js', names); self.assertIn('sw.js', names); self.assertIn('about.js', names)
        self.assertIn('python tools/check_compat.py', (ROOT / '.github' / 'workflows' / 'tests.yml').read_text(encoding='utf-8'))
        self.assertIn("'tools/check_compat.py'", (ROOT / 'tools' / 'build_release.py').read_text(encoding='utf-8'))
        self.assertIn("'tools/check_compat.py'", (ROOT / 'tools' / 'run_tests.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
