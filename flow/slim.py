"""A lighter first open: next.js and next.css are sent without their comments and indentation. The files in the
repository stay as they are written, with their comments, for the people who work on them; the server slims them
once when they change (app.shell_file).

The JavaScript is read token by token: strings, template literals (with ${...} inside, however deep), regular
expressions and comments, so nothing inside a literal changes. Comments go, and the spaces at the start and end of
lines; spaces between tokens become one. Every line break stays, so automatic semicolon insertion reads the code as
before and a line number in an error report (field_service) is still the line in flow/public/next.js.
"""

KEYWORDS = {'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void', 'throw', 'case', 'do', 'else', 'yield', 'await'}
REGEX_AFTER = set('(,=:[!&|?{};+-*%<>~^')


def _string(src, i):
    """The index just after the string that starts at i (quote ' or ")."""
    q, i, n = src[i], i + 1, len(src)
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        i += 1
        if c == q:
            return i
    raise ValueError('unterminated string')


def _regex(src, i):
    """The index just after the regular expression literal that starts at i (with its flags)."""
    i, n, cls = i + 1, len(src), False
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c == '\n':
            raise ValueError('unterminated regular expression')
        i += 1
        if cls:
            cls = c != ']'
        elif c == '[':
            cls = True
        elif c == '/':
            while i < n and (src[i].isalnum() or src[i] in '_$'):
                i += 1
            return i
    raise ValueError('unterminated regular expression')


def _template(src, i):
    """From inside a template literal at i: (end index, True) after its closing backtick, or (index, False) just after
    a ${ that opens an expression."""
    n = len(src)
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c == '`':
            return i + 1, True
        if c == '$' and src.startswith('${', i):
            return i + 2, False
        i += 1
    raise ValueError('unterminated template literal')


def js(src, literals=None):
    """literals: a list to collect every string, template and regular expression as written (for the tests)."""
    out, i, n = [], 0, len(src)
    depth, open_exprs = 0, []  # brace depth; the depth at which each ${ of a template was opened
    prev, word = '', ''        # the last significant character in code, and the last identifier or keyword
    state = {'bol': True, 'space': False}

    def put(s, literal=False):
        if literal and literals is not None:
            literals.append(s)
        if state['space'] and not state['bol']:
            out.append(' ')
        state['space'] = state['bol'] = False
        out.append(s)

    while i < n:
        c = src[i]
        if c == '\n':
            out.append('\n'); state['bol'], state['space'] = True, False; i += 1
        elif c in ' \t\r\f\v ﻿':
            state['space'] = True; i += 1
        elif src.startswith('//', i):
            j = src.find('\n', i); i = n if j < 0 else j
        elif src.startswith('/*', i):
            j = src.find('*/', i + 2)
            if j < 0:
                raise ValueError('unterminated comment')
            lines = src.count('\n', i, j)
            if lines:
                out.append('\n' * lines); state['bol'], state['space'] = True, False
            else:
                state['space'] = True
            i = j + 2
        elif c in '\'"':
            j = _string(src, i); put(src[i:j], True); i = j; prev, word = c, ''
        elif c == '`':
            j, closed = _template(src, i + 1); put(src[i:j], True); i = j; prev, word = '`', ''
            if not closed:
                open_exprs.append(depth); prev = '{'
        elif c == '/':
            if (word in KEYWORDS) if word else (prev == '' or prev in REGEX_AFTER or prev == '}'):
                j = _regex(src, i); put(src[i:j], True); i = j; prev, word = 'r', ''
            else:
                put('/'); i += 1; prev, word = '/', ''
        elif c == '}' and open_exprs and open_exprs[-1] == depth:
            open_exprs.pop()
            j, closed = _template(src, i + 1); put(src[i:j], True); i = j; prev, word = '`', ''
            if not closed:
                open_exprs.append(depth); prev = '{'
        elif c.isalnum() or c in '_$' or ord(c) > 127:
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in '_$' or ord(src[j]) > 127) and src[j] not in ' ﻿':
                j += 1
            put(src[i:j]); word, prev = src[i:j], 'a'; i = j
        else:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            put(c); prev, word = c, ''; i += 1
    if open_exprs:
        raise ValueError('unterminated template expression')
    return ''.join(out)


def css(src):
    """Comments out (not inside strings), lines trimmed, empty lines dropped."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in '\'"':
            j = _string(src, i); out.append(src[i:j]); i = j
        elif src.startswith('/*', i):
            j = src.find('*/', i + 2); i = n if j < 0 else j + 2
        else:
            out.append(c); i += 1
    return '\n'.join(line.strip() for line in ''.join(out).split('\n') if line.strip()) + '\n'


def slim(name, body):
    """The bytes to send for a public file: next.js and next.css slimmed (the file as it is if slimming fails)."""
    try:
        if name == 'next.js':
            return js(body.decode('utf-8')).encode('utf-8')
        if name == 'next.css':
            return css(body.decode('utf-8')).encode('utf-8')
    except (ValueError, UnicodeDecodeError):
        pass
    return body
