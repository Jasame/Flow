#!/usr/bin/env python3
"""The 《用户协议》 and 《隐私和数据》 the app shows on its first start, before anything is agreed to (privacy/Consent.kt).

They are the two chapters of flow/public/guide/guide.md, made into HTML by the site's own renderer (flow/user_guide.py,
standard library only) every time the app is built (the Gradle task legalDocs). So the app reaches nothing on the network
before the learner agrees, and the words are the site's own. Their 生效日期 make the version agreed to, written as
privacy_service.CONSENT_VERSION is ("<用户协议>/<隐私和数据>"): a new 生效日期 in a new build asks again.

    python3 tools/legal_docs.py <dir>    → <dir>/legal/legal.json  {version, docs: {terms|privacy: {title, html}}}

Links: to the other of the two chapters (or a section of one) → flow-doc:<id>[#g-<section>], opened in the same layer;
to a site (https) → as they are, the phone's browser when tapped; to another page of 语流 → plain text (it is there after
agreeing). A 「去看看」 button is left out.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'flow'))
import user_guide  # noqa: E402  (the site's renderer)

DOCS = ('terms', 'privacy')
GO = re.compile(r'<p><a class="btn small go" href="[^"]*">.*?</a></p>\n?')
LINK = re.compile(r'<a href="([^"]*)">(.*?)</a>')
EFFECTIVE = re.compile(r'生效日期：(\d{4}-\d{2}-\d{2})')


def build():
    chapters = {c['id']: c for c in user_guide.parse()['chapters'] if c['id'] in DOCS}
    missing = [d for d in DOCS if d not in chapters]
    if missing:
        raise SystemExit(f'guide.md has no chapter {missing}')
    place = {d: d for d in DOCS}  # where #/guide/<id> goes: one of the two chapters, or a section ({#id}) in one of them
    for d in DOCS:
        for a in re.findall(r'id="g-([a-z0-9-]+)"', chapters[d]['html']):
            place.setdefault(a, f'{d}#g-{a}')

    def link(m):
        href, text = m.group(1), m.group(2)
        k = re.fullmatch(r'#/guide/([a-z0-9-]+)', href)
        if k and k.group(1) in place:
            return f'<a href="flow-doc:{place[k.group(1)]}">{text}</a>'
        if href.startswith('https://'):
            return f'<a href="{href}">{text}</a>'
        return f'<span class="dead">{text}</span>'

    docs, dates = {}, []
    for d in DOCS:
        c = chapters[d]
        m = EFFECTIVE.search(c['html'])
        if not m:
            raise SystemExit(f'guide.md: the {d} chapter has no 生效日期')
        dates.append(m.group(1))
        docs[d] = {'title': c['title'], 'html': LINK.sub(link, GO.sub('', c['html']))}
    return {'version': '/'.join(dates), 'docs': docs}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: tools/legal_docs.py <output dir>')
    out = Path(sys.argv[1]) / 'legal'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'legal.json').write_text(json.dumps(build(), ensure_ascii=False), encoding='utf-8')
