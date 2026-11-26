#!/usr/bin/env python3
"""全英文界面 (docs/english-ui.md): the Chinese in the front end and in the server's error messages that has no English yet.

    python3 tools/check_i18n.py                      # per file: pieces of Chinese, how many have English
    python3 tools/check_i18n.py --missing 10-welcome-today.js 50-words.js   # those files' pieces without English
    python3 tools/check_i18n.py --json out.json      # every piece, its file and line, and whether it has English
    python3 tools/check_i18n.py --errors             # the server's error messages without English (ui_lang.ERRORS)
    python3 tools/check_i18n.py --strict FILE …      # exit 1 when one of these files has a piece without English

A piece is what the page shows as one text: a string or template in flow/public/src/next/*.js, without comments, cut
at HTML tags and line breaks, with each ${…} as {x}. It has English when the tables (enTable({...}) in the 01-en-*.js
parts) have it, numbers and {x} matching any {n} / {x} there, or when it is the first argument of zhEn('中文', 'English').
Parts joined by ' · ' are looked up one by one, as the page does. It reads the source only: what the page really
shows in English mode is checked by tools/ui_test.py's english group (pages opened one by one).
Until 第 1 段 is done this only reports; --strict is for the files already done.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'flow' / 'public' / 'src' / 'next'
HAN = re.compile('[㐀-鿿豈-﫿]')
CANON = re.compile(r'\{[nx]\}|\d+(?:\.\d+)?')
TAG = re.compile(r'<[^<>]*>')
# what the server writes for people other than the learner (the console, checks, operations): not put into English
SERVER_SKIP = re.compile(r'^(flow_admin|console_|ops|ai_check|.*_eval|corpus_import|quality_service|ai_routes|survey_service|migrat)')


def strings(src):
    """(text, line, start, end) for every string and template in a JS source, comments and regexes skipped. A template's
    ${…} becomes {x} (strings inside it are listed on their own)."""
    out, i, n, line = [], 0, len(src), 1
    prev = ''  # the last significant character outside strings, to tell a regex from a division

    def read_str(i, q, line):
        start, buf = i, []
        i += 1
        while i < n and src[i] != q:
            if src[i] == '\\' and i + 1 < n:
                buf.append(src[i:i + 2]); i += 2; continue
            if src[i] == '\n':
                line += 1
            buf.append(src[i]); i += 1
        return ''.join(buf), i + 1, line, start

    def read_tpl(i, line):
        start, buf = i, []
        i += 1
        while i < n and src[i] != '`':
            c = src[i]
            if c == '\\' and i + 1 < n:
                buf.append(src[i:i + 2]); i += 2; continue
            if c == '$' and i + 1 < n and src[i + 1] == '{':
                buf.append('{x}')
                i, line = read_code(i + 2, line, '}')
                continue
            if c == '\n':
                line += 1
            buf.append(c); i += 1
        return ''.join(buf), i + 1, line, start

    def read_code(i, line, close):
        nonlocal prev
        depth = 0
        while i < n:
            c = src[i]
            if c == '\n':
                line += 1; i += 1; continue
            if c in ' \t\r':
                i += 1; continue
            if src.startswith('//', i):
                j = src.find('\n', i); i = n if j < 0 else j; continue
            if src.startswith('/*', i):
                j = src.find('*/', i + 2); seg = src[i:(n if j < 0 else j + 2)]; line += seg.count('\n'); i = n if j < 0 else j + 2; continue
            if c in '\'"':
                s, i2, line2, st = read_str(i, c, line); out.append((s, line, st, i2)); i, line = i2, line2; prev = 'a'; continue
            if c == '`':
                s, i2, line2, st = read_tpl(i, line); out.append((s, line, st, i2)); i, line = i2, line2; prev = 'a'; continue
            word = re.search(r'(\w+)\s*$', src[max(0, i - 12):i])
            if c == '/' and (prev == '' or prev in '(,=:[!&|?{};+-*%<>~^' or (word and word.group(1) in ('return', 'typeof', 'case', 'in', 'of'))):
                j, cls = i + 1, False  # a regex literal
                while j < n and (src[j] != '/' or cls):
                    if src[j] == '\\':
                        j += 1
                    elif src[j] == '[':
                        cls = True
                    elif src[j] == ']':
                        cls = False
                    elif src[j] == '\n':
                        break
                    j += 1
                i = j + 1; prev = 'a'; continue
            if close and c == '{':
                depth += 1
            elif close and c == close:
                if depth == 0:
                    return i + 1, line
                depth -= 1
            prev = c if not (c.isalnum() or c in '_$') else 'a'
            i += 1
        return i, line

    read_code(0, 1, '')
    return out


def pieces(text):
    """A string or template as the pieces of text the page shows: cut at tags, line breaks and attribute quotes."""
    text = text.replace('\\n', '\n').replace("\\'", "'").replace('\\"', '"')
    out = []
    for part in TAG.split(text):
        for p in re.split(r'\n|="|"\s', part):
            p = ' '.join(p.split())
            if HAN.search(p):
                out.append(p)
    # attribute values inside tags (aria-label="…", placeholder="…", title="…")
    for tag in TAG.findall(text):
        for v in re.findall(r'(?:aria-label|placeholder|title|alt|aria-valuetext)="([^"]*)"', tag):
            v = ' '.join(v.split())
            if HAN.search(v):
                out.append(v)
    return out


def canon(s):
    return CANON.sub('{}', ' '.join(s.split()))


def table_keys():
    """Every key in the enTable({...}) tables, as canon() writes it."""
    keys = set()
    for f in sorted(SRC.glob('*.js')):
        src = f.read_text(encoding='utf-8')
        if 'enTable(' not in src:
            continue
        for s, _, st, end in strings(src):  # a key: a string followed by ':'
            if src[end:end + 3].lstrip().startswith(':') and HAN.search(s):
                keys.add(canon(s.replace("\\'", "'").replace('\\"', '"')))
    return keys


def covered(p, keys):
    c = canon(p)
    if c in keys:
        return True
    if ' · ' in p:
        return all(not HAN.search(x) or canon(x) in keys for x in p.split(' · '))
    return False


def front():
    keys, rows = table_keys(), []
    for f in sorted(SRC.glob('*.js')):
        src = f.read_text(encoding='utf-8')
        is_table = f.name.startswith('01-en-')
        lines = src.splitlines()
        for s, line, st, end in strings(src):
            if is_table or not HAN.search(s) or 'i18n: keep' in lines[line - 1]:  # Chinese on purpose (a comment says so)
                continue
            inline = bool(re.search(r'(?<![\w$.])zhEn\(\s*$', src[max(0, st - 12):st])) and src[end:end + 40].lstrip().startswith(',')
            for p in pieces(s):
                rows.append({'file': f.name, 'line': line, 'text': p, 'en': inline or covered(p, keys)})
    return rows


def server_errors():
    sys.path.insert(0, str(ROOT / 'flow'))
    import ui_lang
    have = {canon(k) for k in ui_lang.ERRORS}
    rows = []
    for f in sorted((ROOT / 'flow').glob('*.py')):
        if SERVER_SKIP.match(f.name):
            continue
        for ln, text in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            for m in re.finditer(r"""['"]error['"]\s*:\s*(f?)(['"])(.*?)(?<!\\)\2""", text):
                s = m.group(3)
                if not HAN.search(s):
                    continue
                key = re.sub(r'\{[^{}]*\}', '{n}', s) if m.group(1) else re.sub(r'%\.?\d*[df]', '{n}', s)  # f-string or % formatting
                rows.append({'file': f.name, 'line': ln, 'text': key, 'en': canon(key) in have, 'dynamic': bool(m.group(1))})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--missing', nargs='*', help='print these files\' pieces without English (no file: all)')
    ap.add_argument('--json', help='write every piece to this file')
    ap.add_argument('--errors', action='store_true', help="the server's error messages without English")
    ap.add_argument('--strict', nargs='*', help='exit 1 when one of these files has a piece without English')
    a = ap.parse_args()
    if a.errors:
        rows = server_errors()
        miss = {}
        for r in rows:
            if not r['en']:
                miss.setdefault(r['text'], r)
        for t_, r in miss.items():
            print(f"{r['file']}:{r['line']}\t{t_}")
        print(f'server error messages: {len(rows)}, without English: {len(miss)} different', file=sys.stderr)
        return
    rows = front()
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    if a.missing is not None:
        want = set(a.missing)
        seen = set()
        for r in rows:
            if not r['en'] and (not want or r['file'] in want) and (r['file'], r['text']) not in seen:
                seen.add((r['file'], r['text']))
                print(f"{r['file']}:{r['line']}\t{r['text']}")
        return
    if a.strict:
        bad = [r for r in rows if r['file'] in set(a.strict) and not r['en']]
        for r in bad:
            print(f"{r['file']}:{r['line']}\tno English: {r['text']}")
        sys.exit(1 if bad else 0)
    by = {}
    for r in rows:
        b = by.setdefault(r['file'], [0, 0])
        b[0] += 1
        b[1] += r['en']
    total = sum(b[0] for b in by.values())
    done = sum(b[1] for b in by.values())
    for f, (n, e) in sorted(by.items(), key=lambda x: x[1][1] - x[1][0]):
        print(f'{f:28} {e:5}/{n:<5} {"done" if e == n else ""}')
    print(f'front end: {done}/{total} pieces of Chinese have English')


if __name__ == '__main__':
    main()
