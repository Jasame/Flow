"""The 操作指南: one source (public/guide/guide.md) for the in-site guide (#/guide) and the PDF (tools/build_guide.py).

The source is a small, fixed Markdown subset, so a teacher or the next developer can edit it as text:
  % title / % updated line          # 章 {#id}          ## 小节          blank line = new paragraph
  - bullet     1. step (indent 3 spaces for a bullet under a step)     > 提示        | table | rows |
  ![caption](shot:name)  -> public/guide/name.jpg (tools/guide_shots.py takes these from the local UI server)
  [去看看](#/route) on its own line -> a button to that page;  **bold**  `key`
Everything is HTML-escaped before the markup is applied, so the output is safe to put into the page.
"""
import hashlib, html, json, re
from pathlib import Path

DIR = Path(__file__).resolve().parent / 'public' / 'guide'
SOURCE = DIR / 'guide.md'
PDF = DIR / 'flow-guide.pdf'
MANIFEST = DIR / 'manifest.json'
SHOT = re.compile(r'^!\[([^\]]*)\]\(shot:([a-z0-9-]+)\)$')
GO = re.compile(r'^\[([^\]]+)\]\((#/[^)\s]*)\)$')
HEAD = re.compile(r'^# (.+?)\s*\{#([a-z0-9-]+)\}$')
_CACHE = {}


def _inline(text, link):
    s = html.escape(text, quote=True)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'`([^`]+)`', r'<kbd>\1</kbd>', s)
    return re.sub(r'\[([^\]]+)\]\((#/[^)\s]*|https://[^)\s]+)\)', lambda m: f'<a href="{link(m.group(2))}">{m.group(1)}</a>', s)


def parse(text=None, shot_url=lambda n: f'/guide/{n}.jpg', link=lambda h: h):
    """{'title', 'updated', 'chapters': [{'id', 'title', 'html', 'text', 'shots', 'links'}]}."""
    text = SOURCE.read_text(encoding='utf-8') if text is None else text
    meta, chapters, cur = [], [], None
    lines = text.splitlines() + ['']
    i = 0
    para, items, kind, table = [], [], None, []

    def out(h):
        cur['html'].append(h)

    def flush():
        nonlocal para, items, kind, table
        if para:
            out('<p>' + _inline(' '.join(para), link) + '</p>'); para = []
        if items:
            tag = 'ol' if kind == 'ol' else 'ul'
            parts = []
            for main, subs in items:
                sub = ('<ul>' + ''.join(f'<li>{_inline(x, link)}</li>' for x in subs) + '</ul>') if subs else ''
                parts.append(f'<li>{_inline(main, link)}{sub}</li>')
            out(f'<{tag}>' + ''.join(parts) + f'</{tag}>'); items, kind = [], None
        if table:
            rows = [[c.strip() for c in r.strip().strip('|').split('|')] for r in table if not re.fullmatch(r'\|[\s\-|]+\|', r.strip())]
            head, body = rows[0], rows[1:]
            out('<table><thead><tr>' + ''.join(f'<th>{_inline(c, link)}</th>' for c in head) + '</tr></thead><tbody>'
                + ''.join('<tr>' + ''.join(f'<td>{_inline(c, link)}</td>' for c in r) + '</tr>' for r in body) + '</tbody></table>')
            table = []

    while i < len(lines):
        raw = lines[i]; line = raw.rstrip(); i += 1
        if line.startswith('% '):
            meta.append(line[2:].strip()); continue
        m = HEAD.match(line)
        if m:
            if cur:
                flush()
            cur = {'id': m.group(2), 'title': m.group(1).strip(), 'html': [], 'text': [m.group(1)], 'shots': [], 'links': []}
            chapters.append(cur); continue
        if cur is None:
            if line.strip():
                raise ValueError(f'guide.md: text before the first chapter: {line[:40]}')
            continue
        if not line.strip():
            flush(); continue
        cur['text'].append(re.sub(r'\]\([^)]*\)|[*`>#|!\[\]]|^\s*- ', ' ', line))
        cur['links'] += re.findall(r'\]\((#/[^)\s]*)\)', line)
        if line.startswith('## '):
            flush(); out(f'<h3>{_inline(line[3:].strip(), link)}</h3>'); continue
        m = SHOT.match(line.strip())
        if m:
            flush(); cur['shots'].append(m.group(2))
            out(f'<figure class="shot"><img src="{html.escape(shot_url(m.group(2)))}" alt="{html.escape(m.group(1))}" loading="lazy" width="390" height="760">'
                f'<figcaption>{html.escape(m.group(1))}</figcaption></figure>')
            continue
        m = GO.match(line.strip())
        if m:
            flush(); out(f'<p><a class="btn small go" href="{link(m.group(2))}">{html.escape(m.group(1))} →</a></p>'); continue
        if line.startswith('> '):
            flush(); out('<div class="tip">' + _inline(line[2:].strip(), link) + '</div>'); continue
        if line.startswith('|'):
            if para or items:
                flush()
            table.append(line); continue
        m = re.match(r'^(\d+)\. (.+)$', line)
        if m:
            if para or table or (items and kind != 'ol'):
                flush()
            kind = 'ol'; items.append((m.group(2), [])); continue
        m = re.match(r'^ {2,4}- (.+)$', raw)
        if m and items:
            items[-1][1].append(m.group(1)); continue
        if line.startswith('- '):
            if para or table or (items and kind != 'ul'):
                flush()
            kind = 'ul'; items.append((line[2:], [])); continue
        if items:  # a line continuing the last item
            items[-1] = (items[-1][0] + line.strip(), items[-1][1]); continue
        para.append(line.strip())
    if cur:
        flush()
    for ch in chapters:
        ch['html'] = '\n'.join(ch['html']); ch['text'] = ' '.join(' '.join(ch['text']).split())
    return {'title': meta[0] if meta else '操作指南', 'updated': meta[1] if len(meta) > 1 else '', 'chapters': chapters}


def source_hash():
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def api():
    """What #/guide shows; parsed once per change of the source file."""
    key = SOURCE.stat().st_mtime_ns
    if _CACHE.get('key') != key:
        g = parse()
        built = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        g['pdf'] = '/guide.pdf' if PDF.exists() and built.get('source_sha256') == source_hash() else None
        g['chapters'] = [{k: ch[k] for k in ('id', 'title', 'html', 'text')} for ch in g['chapters']]
        _CACHE.update(key=key, data=g)
    return _CACHE['data']
