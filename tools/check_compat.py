#!/usr/bin/env python3
"""The scripts the site serves still work in Safari 15.0 (iOS 15): exit 1, with file:line, for anything newer.

    python3 tools/check_compat.py              # the served scripts (SCRIPTS: next.js's parts and the other pages)
    python3 tools/check_compat.py FILE…        # these files

The floor is Safari 15.0; the built-ins below are past Chrome 114 too, the Chromium of HarmonyOS 5.0–5.1's browser
and ArkWeb (语流 C4: the HarmonyOS app supports 5.0 and up), whose syntax Safari 15's floor already covers.

Why (2026-11-25): one regular expression with a lookbehind, (?<=…), made next.js fail to parse in Safari before 16.4,
so a teacher's iPhone on iOS 16.1 showed nothing at all. The owner asked for old devices to work: iOS 15 and up fully
(语流 A0's line), 12–14 as far as it goes. Nothing transforms the code (no build tool), so this check keeps it there.

next.js is its parts in flow/public/src/next/ joined byte for byte (tools/build_front.py), so the parts are checked,
and a finding names the part and its line. A light lexer tells code, comments, strings, template strings and regular
expression literals apart, so a comment that mentions a feature is not a finding:
  - syntax Safari 15.0 cannot parse, which breaks the whole file: a lookbehind in a regular expression (literal or a
    string given to RegExp; Safari 16.4), the regex v flag (17), a class static block (16.4);
  - built-ins Safari 15.0 lacks, which break where they run: matched by their usual shape only, so a method of our
    own with the same name (PROG.at(key, n)) is not taken for Array.prototype.at(-1).
A line that needs one anyway says so in a comment on that line: // compat-ok: <why it is safe there>.
Run by CI's frontend job, by every release build (tools/build_release.py) and by run_tests.py --checks.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [*sorted((ROOT / 'flow' / 'public' / 'src' / 'next').glob('*.js')),
           *(ROOT / 'flow' / 'public' / n for n in ('sw.js', 'survey.js', 'about.js'))]
STYLES = [*sorted((ROOT / 'flow' / 'public' / 'src' / 'next').glob('*.css')),
          *(ROOT / 'flow' / 'public' / n for n in ('survey.css', 'about.css'))]

# (what, first Safari with it, pattern): in regular expressions (the literal's body, or a string's text)
REGEX_FEATURES = [('a lookbehind (?<= / (?<! in a regular expression', '16.4', re.compile(r'\(\?<[=!]'))]
# in code only (strings, comments and regular expressions blanked out)
CODE_FEATURES = [
    ('a class static block', '16.4', re.compile(r'\bstatic\s*\{')),
    ('Array.prototype.at / String.prototype.at with a number', '15.4', re.compile(r'\.at\(\s*-?\s*\d')),
    ('Object.hasOwn', '15.4', re.compile(r'\bObject\.hasOwn\(')),
    ('structuredClone', '15.4', re.compile(r'\bstructuredClone\(')),
    ('Array.prototype.findLast / findLastIndex', '15.4', re.compile(r'\.findLast(?:Index)?\(')),
    ('Array.prototype.toSorted / toReversed / toSpliced', '16', re.compile(r'\.(?:toSorted|toReversed|toSpliced)\(')),
    ('Array.fromAsync', '16.4', re.compile(r'\bArray\.fromAsync\(')),
    ('String.prototype.isWellFormed / toWellFormed', '16.4', re.compile(r'\.(?:isWellFormed|toWellFormed)\(')),
    ('Object.groupBy / Map.groupBy', '17.4', re.compile(r'\b(?:Object|Map)\.groupBy\(')),
    ('Promise.withResolvers', '17.4', re.compile(r'\bPromise\.withResolvers\(')),
    # also past Chrome 114, the core of HarmonyOS 5.0–5.1's browser and ArkWeb (语流 C4, harmony-plan.md)
    ('URL.canParse', '17', re.compile(r'\bURL\.canParse\(')),
    ('AbortSignal.any', '17.4', re.compile(r'\bAbortSignal\.any\(')),
    ('Promise.try', '18.2', re.compile(r'\bPromise\.try\(')),
    ('scheduler.yield', '-', re.compile(r'\bscheduler\.yield\(')),
    ('Uint8Array base64 (fromBase64 / toBase64 / fromHex / toHex)', '18.2', re.compile(r'\bUint8Array\.from(?:Base64|Hex)\(|\.to(?:Base64|Hex)\(')),
    ('RegExp.escape', '18.2', re.compile(r'\bRegExp\.escape\(')),
    ('Set methods (union / intersection / difference / symmetricDifference / isSubsetOf / isSupersetOf / isDisjointFrom)',
     '17', re.compile(r'\.(?:union|intersection|difference|symmetricDifference|isSubsetOf|isSupersetOf|isDisjointFrom)\(\s*new\s+Set\b|\bnew\s+Set\([^)]*\)\.(?:union|intersection|difference|symmetricDifference|isSubsetOf|isSupersetOf|isDisjointFrom)\(')),
]
# after these, a / starts a regular expression; after anything else (a name, a number, ) or ]) it divides
REGEX_AFTER = set('(,=:[!&|?{};+-*%<>~^') | {''}
REGEX_KEYWORDS = {'return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw',
                  'instanceof', 'yield', 'await'}


def lex(src):
    """(code, regexes, strings): code is src with comments, strings and regular expressions blanked (newlines kept, so
    positions stay); regexes and strings are (offset, body, flags) and (offset, text)."""
    out, regexes, strings = list(src), [], []
    i, n, last = 0, len(src), ''          # last: the previous significant token ('' at the start)
    stack = []                            # template literals open around the code being read: brace depth in each

    def blank(a, b):
        for k in range(a, b):
            if out[k] != '\n':
                out[k] = ' '

    def read_template(i):
        """From inside a template literal: to its end (returns after `) or into a ${ (returns after ${, pushed)."""
        start = i
        while i < n:
            c = src[i]
            if c == '\\':
                i += 2
            elif c == '`':
                strings.append((start, src[start:i])); blank(start, i + 1)
                return i + 1, False
            elif c == '$' and i + 1 < n and src[i + 1] == '{':
                strings.append((start, src[start:i])); blank(start, i + 2)
                stack.append(0)
                return i + 2, True
            else:
                i += 1
        return n, False

    while i < n:
        c = src[i]
        if c in ' \t\r\n':
            i += 1
        elif src.startswith('//', i):
            j = src.find('\n', i); j = n if j < 0 else j
            blank(i, j); i = j
        elif src.startswith('/*', i):
            j = src.find('*/', i + 2); j = n if j < 0 else j + 2
            blank(i, j); i = j
        elif c in '\'"':
            j = i + 1
            while j < n and src[j] != c and src[j] != '\n':
                j += 2 if src[j] == '\\' else 1
            strings.append((i, src[i + 1:j])); blank(i, j + 1); i = j + 1; last = 'str'
        elif c == '`':
            i, _ = read_template(i + 1); last = 'str'
        elif c == '}' and stack and stack[-1] == 0:
            stack.pop()
            i, _ = read_template(i + 1); last = 'str'
        elif c == '/' and (last in REGEX_AFTER or last in REGEX_KEYWORDS):
            j, cls = i + 1, False
            while j < n and src[j] != '\n':
                if src[j] == '\\':
                    j += 2; continue
                if src[j] == '[':
                    cls = True
                elif src[j] == ']':
                    cls = False
                elif src[j] == '/' and not cls:
                    break
                j += 1
            k = j + 1
            while k < n and (src[k].isalnum() or src[k] == '_'):
                k += 1
            regexes.append((i, src[i + 1:j], src[j + 1:k])); blank(i, k); i = k; last = 're'
        elif c.isalnum() or c in '_$':
            j = i
            while j < n and (src[j].isalnum() or src[j] in '_$'):
                j += 1
            last = src[i:j]; i = j
        else:
            if stack:
                if c == '{':
                    stack[-1] += 1
                elif c == '}':
                    stack[-1] -= 1
            last = c; i += 1
    return ''.join(out), regexes, strings


def findings(src):
    """(line, column, what, safari) for each thing in src that Safari 15.0 lacks, less the lines marked compat-ok."""
    code, regexes, strings = lex(src)
    found = []
    for off, body, flags in regexes:
        for what, ver, pat in REGEX_FEATURES:
            m = pat.search(body)
            if m:
                found.append((off + 1 + m.start(), what, ver))
        if 'v' in flags:
            found.append((off, 'the regular expression v flag', '17'))
    for off, text in strings:
        for what, ver, pat in REGEX_FEATURES:
            m = pat.search(text)
            if m:
                found.append((off + m.start(), what + ' (in a string, as for RegExp)', ver))
    for what, ver, pat in CODE_FEATURES:
        for m in pat.finditer(code):
            found.append((m.start(), what, ver))
    lines = src.split('\n')
    out = []
    for off, what, ver in sorted(set(found)):
        line = src.count('\n', 0, off) + 1
        col = off - (src.rfind('\n', 0, off) + 1) + 1
        if 'compat-ok' not in lines[line - 1]:
            out.append((line, col, what, ver))
    return out


# CSS: an unknown value or selector drops only its own declaration or rule, so the page still opens; but with nothing
# before it, what it set is gone (2026-11-25: color-mix backgrounds lost on iOS 16.1, 语流 B5's #319). So a value
# Safari 15.0 lacks needs a plain one for the same property before it in the same rule, and a selector it lacks a
# compat-ok comment in its rule saying what happens without it.
CSS_VALUES = [('color-mix()', '16.2', re.compile(r'color-mix\(')),
              ('dvh / svh / lvh', '15.4', re.compile(r'\d(?:dvh|svh|lvh|dvw|svw|lvw)\b'))]
CSS_SELECTORS = [(':has()', '15.4', re.compile(r':has\(')), ('nesting with &', '16.5', re.compile(r'&'))]
# container queries (Safari 16): a whole layout, not a declaration, so the fallback may be one for the whole file, an
# @supports not (container-type: …) block that shows something else there (语流 A0, 2026-11-25: about.css's phone)
CQ_UNITS = re.compile(r'\d(?:cqw|cqh|cqi|cqb|cqmin|cqmax)\b')
CQ_FALLBACK = re.compile(r'@supports\s+not\s*\(\s*container-type\s*:')
# properties Safari reads only with -webkit- (None: no Safari yet), or only from that version on without it: the rule
# needs the -webkit- one too (2026-11-26, 语流 B8 #364: user-select:none alone left 盲听's hidden sentence copyable)
PREFIXED = {'user-select': None, 'text-size-adjust': None, 'line-clamp': None, 'box-decoration-break': None,
            'backdrop-filter': '18', 'appearance': '15.4', 'mask': '15.4', 'mask-image': '15.4'}


def css_findings(src):
    """(line, column, what, safari) for what Safari 15.0 lacks with nothing to fall back on (see CSS_VALUES)."""
    text, oks = list(src), []
    for m in re.finditer(r'/\*.*?\*/', src, re.S):
        if 'compat-ok' in m.group():
            oks.append(m.start())
        for k in range(m.start(), m.end()):
            if text[k] != '\n':
                text[k] = ' '
    text = ''.join(text)
    found = []
    cq_ok = bool(CQ_FALLBACK.search(text))
    if not cq_ok:
        for m in re.finditer(r'@container\b', text):
            brace = text.find('{', m.end()); depth, end = 0, len(text)
            for k in range(brace, len(text)):
                depth += {'{': 1, '}': -1}.get(text[k], 0)
                if depth == 0:
                    end = k; break
            if not any(m.start() <= o <= end for o in oks):
                found.append((m.start(), 'a container query (@container) with no @supports not (container-type: …) fallback', '16'))
    start, stack = 0, []                 # start: where the current prelude or declaration list began
    for m in re.finditer(r'[{}]', text):
        if m.group() == '{':
            stack.append((start, m.start()))   # (prelude start, its brace)
            start = m.end()
            continue
        if not stack:
            start = m.end(); continue
        pre_start, brace = stack.pop()
        prelude, body, body_start = text[pre_start:brace], text[brace + 1:m.start()], brace + 1
        start = m.end()
        if '{' in body or prelude.strip().startswith('@'):
            continue                     # @media, @supports …: their rules are checked one by one
        ok = any(pre_start <= o < m.start() for o in oks)
        for what, ver, pat in CSS_SELECTORS:
            s = pat.search(prelude)
            if s and not ok:
                found.append((pre_start + s.start(), what, ver))
        seen = {}                        # property -> it has had a value Safari 15.0 knows
        props = {d.split(':', 1)[0].strip().lower() for d in body.split(';') if ':' in d}
        off = body_start
        for decl in body.split(';'):
            if ':' in decl:
                prop, value = decl.split(':', 1)
                prop = prop.strip().lower()
                if prop in PREFIXED and '-webkit-' + prop not in props and not ok:
                    found.append((off + decl.index(prop), f'{prop} with no -webkit-{prop} in the same rule', PREFIXED[prop]))
                newer = [(what, ver, pat.search(value)) for what, ver, pat in CSS_VALUES if pat.search(value)]
                if not cq_ok and CQ_UNITS.search(value):
                    newer.append(('container query units (cqw, cqh …)', '16', CQ_UNITS.search(value)))
                if newer and not seen.get(prop) and not prop.startswith('--') and not ok:
                    what, ver, s = newer[0]
                    found.append((off + decl.index(value) + s.start(), what + f' in {prop} with no plain {prop} before it', ver))
                if not newer:
                    seen[prop] = True
            off += len(decl) + 1
    lines = src.split('\n')
    out = []
    for off, what, ver in sorted(set(found)):
        line = src.count('\n', 0, off) + 1
        if 'compat-ok' not in lines[line - 1]:
            out.append((line, off - (src.rfind('\n', 0, off) + 1) + 1, what, ver))
    return out


def main(argv):
    files = [Path(a) for a in argv] or [*SCRIPTS, *STYLES]
    bad = 0
    for f in files:
        text = f.read_text(encoding='utf-8')
        lines = text.split('\n')
        for line, col, what, ver in (css_findings(text) if f.suffix == '.css' else findings(text)):
            bad += 1
            rel = f.relative_to(ROOT) if f.is_absolute() and ROOT in f.parents else f
            when = f'Safari {ver} and later only' if ver else 'no Safari reads it without -webkit-'
            print(f'{rel}:{line}:{col}: {what}: {when} (iOS 15 must work)\n    {lines[line - 1].strip()[:160]}')
    if bad:
        print(f'check_compat: {bad} thing(s) Safari 15.0 cannot run; rewrite them (in CSS: a plain value for the same '
              f'property first, -webkit-x next to x), or mark a line that is safe with // compat-ok: <why> (in CSS /* compat-ok: <why> */)')
        return 1
    print(f'check_compat: {len(files)} scripts and stylesheets, nothing newer than Safari 15.0 without a fallback')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
