"""Layout faults found on phones, kept out at the source (tools/ui_test.py's layout run looks for the symptoms):
- two unrelated components with the same class name: the later style file won, and squeezed the vocabulary result
  into four narrow columns (.bands, r20);
- grid tracks that can grow past the screen: a bare `fr` has its content's size as its minimum, and iOS Safari sized
  the squares of the 单词 calendar so that the page slid sideways (r20);
- the bottom tab bar inside the sticky top bar: iOS Safari carries a fixed element along with a sticky ancestor."""
import re, unittest
from pathlib import Path

NEXT = Path(__file__).resolve().parents[1] / 'public'
PARTS = sorted((NEXT / 'src' / 'next').glob('*.css'))
LAYOUT = ('display', 'grid-template-columns', 'grid-template-rows', 'flex-direction', 'position', 'width', 'min-height', 'columns')
# Classes whose layout is set in more than one file on purpose: one component, adjusted for phones or restyled.
SAME_COMPONENT = {
    'ab': 'ability rows; 70-input-devices.css fits the name column to touch screens',
    'choice': 'answer buttons; 30-words.css makes the bare list three across (review), variants say .two/.three/.opts',
    'expr': 'expressions on 读; 85-phone.css stacks them on phones',
    'filters': 'library filters; 50-phone.css lays the three selects in a row',
    'hero': "今日's card; 80-flat.css spaces it as a grid",
    'mini': 'material rows; 85-phone.css stacks them on phones',
    'pr': 'word rows on 听; 85-phone.css widens the first column',
    'steps': 'the step bar of a material; 20-motion-graph.css makes it sticky',
}


def top_level_rules(css):
    """(selector, body) of rules outside @media/@supports/@keyframes: deliberate overrides live in those."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out, i = [], 0
    while i < len(css):
        m = re.match(r'@(media|supports|keyframes)[^{]*\{', css[i:])
        if m:
            j, depth = i + m.end(), 1
            while depth and j < len(css):
                depth += {'{': 1, '}': -1}.get(css[j], 0); j += 1
            i = j; continue
        out.append(css[i]); i += 1
    return re.findall(r'([^{}]+)\{([^{}]*)\}', ''.join(out))


class FrontLayoutTests(unittest.TestCase):
    def test_one_class_name_one_component(self):
        files = {}
        for f in PARTS:
            for sel, body in top_level_rules(f.read_text(encoding='utf-8')):
                props = {p.split(':')[0].strip() for p in body.split(';') if ':' in p}
                if not props & set(LAYOUT):
                    continue
                for s in sel.split(','):
                    m = re.fullmatch(r'\.([a-zA-Z][\w-]*)', s.strip())
                    if m:
                        files.setdefault(m.group(1), set()).add(f.name)
        clashes = {k: sorted(v) for k, v in files.items() if len(v) > 1 and k not in SAME_COMPONENT}
        self.assertEqual(clashes, {}, 'a class laid out in two files: rename one of them (vt-bands / pl-bands), or list it with the reason')

    def test_grid_columns_cannot_outgrow_the_screen(self):
        bare = []
        for f in PARTS:
            for v in re.findall(r'grid-template-columns:([^;}]*)', f.read_text(encoding='utf-8')):
                rest = re.sub(r'(?:minmax|fit-content)\([^()]*\)', '', v)
                if re.search(r'(?<![\w.-])\d*\.?\d+fr\b', rest) or re.search(r'(?<![\w(-])max-content', rest):
                    bare.append(f'{f.name}: {v.strip()}')
        self.assertEqual(bare, [], 'use minmax(0, …fr): a bare fr (or max-content) track grows with its content')

    def test_the_tab_bar_is_not_inside_the_sticky_top_bar(self):
        html = (NEXT / 'next.html').read_text(encoding='utf-8')
        header = re.search(r'<header class="bar".*?</header>', html, re.S).group(0)
        self.assertNotIn('class="tabs"', header)
        self.assertIn('<nav class="tabs"', html)
        js = (NEXT / 'next.js').read_text(encoding='utf-8')
        self.assertIn("matchMedia('(min-width:760px)')", js)  # wide screens put it back in the bar, as links

    def test_the_result_lists_have_their_own_names(self):
        js = (NEXT / 'next.js').read_text(encoding='utf-8')
        self.assertIn('class="vt-bands"', js); self.assertIn('class="pl-bands"', js)
        self.assertNotIn('class="bands"', js)


class OldSafariTests(unittest.TestCase):
    """iPhones and iPads before iOS 16.4 (Safari 16.3 and older) cannot parse a regular expression with lookbehind
    ((?<= or (?<!), nor a class static block. One of them anywhere in next.js and none of it runs: the page stays at
    next.html's 「正在打开…」 with the tab bar, and nothing reports it (the error reporter is in next.js too). Learners
    on iOS 16.1 met it on 2026-11-25 (30-lookup.js splitSentences, there since 2026-11-22)."""

    def test_no_syntax_older_iphones_cannot_parse(self):
        found = []
        for f in sorted((NEXT / 'src' / 'next').glob('*.js')) + [NEXT / 'sw.js']:
            for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
                if '(?<=' in line or '(?<!' in line or re.search(r'\bstatic\s*\{', line):
                    found.append(f'{f.name}:{n}')
        self.assertEqual(found, [], 'iOS before 16.4 cannot parse these (lookbehind, class static block): write them without')


if __name__ == '__main__':
    unittest.main()
