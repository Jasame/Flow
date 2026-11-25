#!/usr/bin/env python3
"""Makes the PDF 操作指南 from the same source as the in-site guide (#/guide).

    python3 tools/guide_shots.py      # 1. fresh screenshots from the local UI server (when pages changed)
    python3 tools/build_guide.py      # 2. flow/public/guide/flow-guide.pdf + manifest.json

The PDF is printed by Chrome (Playwright), so Chinese text, the screenshots and the layout come out the way the site
shows them. manifest.json records which guide.md the PDF was made from; tests/test_guide.py fails when guide.md
changed and the PDF was not rebuilt, and the site only offers the PDF download while the two match.
Neither file is committed: a release prints them from the commit's guide.md and screenshots (tools/build_release.py,
which runs this), so pull requests that edit the guide no longer conflict over the PDF. To see it locally:
python3 tools/build_release.py --here.
"""
import datetime, hashlib, html, json, os, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
import silent  # noqa: F401  (rule 9 in tools/README.md: every browser started here is muted)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flow'))
import user_guide as ug  # noqa: E402

ORIGIN = os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').rstrip('/')
LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#1f9d55"/>'
        '<path d="M7 20v-6m6 10V8m6 14V11m6 7v-4" stroke="#fff" stroke-width="2.6" stroke-linecap="round" fill="none"/></svg>')
CSS = """
@page{size:A4;margin:16mm 17mm 18mm}
*{box-sizing:border-box}
body{margin:0;font-family:"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;color:#1b1d1a;font-size:10.5pt;line-height:1.78;-webkit-print-color-adjust:exact;print-color-adjust:exact}
a{color:#16794a}
.cover{height:255mm;display:flex;flex-direction:column;justify-content:center;gap:5mm;break-after:page}
.cover svg{width:24mm;height:24mm}
.cover .t{font-size:32pt;font-weight:700;line-height:1.25;margin:4mm 0 0;letter-spacing:.02em}
.cover .sub{font-size:14pt;color:#4a4e46;margin:0}
.cover .meta{margin-top:14mm;font-size:10pt;color:#6f7369;line-height:1.9}
.cover .band{margin-top:10mm;padding:5mm 6mm;border-radius:4mm;background:#e8f5ee;font-size:10.5pt}
.toc{break-after:page}
.toc h2{font-size:18pt;margin:0 0 6mm}
.toc a{display:flex;gap:5mm;align-items:baseline;text-decoration:none;color:inherit;padding:2.6mm 0;border-bottom:.4pt solid #e2dfd6;font-size:11.5pt}
.toc .n{flex:none;width:8mm;color:#1f9d55;font-weight:700}
.toc .d{margin-left:auto;color:#8a8d84;font-size:9pt}
.toc .how{margin-top:8mm;font-size:9.5pt;color:#4a4e46}
section.ch{break-before:page;display:flow-root}  /* a chapter holds its own pictures, without an extra block that could start a blank page */
section.ch>h2{font-size:19pt;line-height:1.3;margin:0 0 5mm;padding-bottom:2.5mm;border-bottom:1.2pt solid #1f9d55}
section.ch>h2 .n{color:#1f9d55;margin-right:3mm}
h3{font-size:12.5pt;margin:6mm 0 1.5mm;break-after:avoid}
p{margin:1.8mm 0}
ol,ul{margin:1.5mm 0;padding-left:6.5mm}
li{margin:1mm 0}
li>ul{margin-top:1mm}
b{font-weight:600}
.shot{float:right;clear:right;width:47mm;margin:1mm 0 3mm 7mm;break-inside:avoid}
.shot img{display:block;width:100%;height:auto;border-radius:3.5mm;border:.5pt solid #d6d2c6}
.shot figcaption{font-size:8pt;color:#7a7d74;text-align:center;margin-top:1.5mm;line-height:1.4}
.tip{background:#fbf1dc;border-radius:2.5mm;padding:2.8mm 4mm;margin:3mm 0;break-inside:avoid;font-size:10pt}
table{border-collapse:collapse;width:100%;margin:3mm 0;font-size:10pt;break-inside:avoid}
th,td{text-align:left;vertical-align:top;padding:2mm 2.5mm;border-bottom:.4pt solid #e2dfd6}
th{color:#6f7369;font-weight:600;font-size:9pt}
td:first-child{white-space:nowrap;font-weight:600}
p:has(>a.go){break-before:avoid;margin-top:1mm}  /* a 去看看 button stays with the text above it */
a.go{display:inline-block;font-size:9pt;text-decoration:none;color:#16794a;border:.6pt solid #1f9d55;border-radius:10mm;padding:.6mm 4mm;margin:1mm 0}
pre.cmd{margin:2mm 0;padding:2.5mm 4mm;border-radius:2mm;background:#f1efe8;font-size:9pt;white-space:pre-wrap;break-inside:avoid}
kbd{font-family:inherit;font-size:9pt;padding:0 1.5mm;border:.5pt solid #c9c5b9;border-bottom-width:1.2pt;border-radius:1.2mm;background:#fff}
"""
FOOTER = ('<div style="width:100%;font-size:7.5px;color:#8a8d84;padding:0 17mm;display:flex;justify-content:space-between;'
          'font-family:PingFang SC,Hiragino Sans GB,sans-serif"><span>语流 Flow 操作指南</span>'
          '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')


def eager(h):
    return h.replace(' loading="lazy"', '')  # print loads every picture at once


def page(g):
    toc = ''.join(f'<a href="#ch-{ch["id"]}"><span class="n">{k + 1}</span><span>{html.escape(ch["title"])}</span></a>' for k, ch in enumerate(g['chapters']))
    body = ''.join(f'<section class="ch" id="ch-{ch["id"]}"><h2><span class="n">{k + 1}</span> {html.escape(ch["title"])}</h2>{eager(ch["html"])}</section>'
                   for k, ch in enumerate(g['chapters']))
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(g['title'])}</title><style>{CSS}</style></head><body>
<div class="cover">{LOGO}<div class="t">{html.escape(g['title'])}</div><p class="sub">从第一次打开到每一个页面，一步一步讲清楚，新手一看就会。</p>
<div class="band">每天一篇短文：听一遍、读一遍、答几道题，再用自己的话说出来、写出来。单词按遗忘曲线复习，语法画成一张能点亮的地图，口语和写作有 AI 帮你改。</div>
<div class="meta">网站：{html.escape(ORIGIN.replace('https://', ''))}（手机、电脑的浏览器都能打开，不用下载 App）<br>{html.escape(g['updated'])}<br>网站里的「操作指南」和这份 PDF 内容相同，会随网站一起更新。</div></div>
<nav class="toc"><h2>目录</h2>{toc}<p class="how">刚开始用？先读第 1–4 章就能开始学习，其他章节用到时再翻。点目录里的章节名可以直接跳过去；每章里的「去看看」会在浏览器里打开对应的页面。</p></nav>
{body}
</body></html>"""


def main():
    g = ug.parse(shot_url=lambda n: (ug.DIR / f'{n}.jpg').as_uri(), link=lambda h: ORIGIN + '/' + h)
    shots = [s for ch in g['chapters'] for s in ch['shots']]
    missing = [s for s in shots if not (ug.DIR / f'{s}.jpg').is_file()]
    if missing:
        raise SystemExit(f'missing screenshots (run tools/guide_shots.py): {missing}')
    with tempfile.TemporaryDirectory(prefix='flow-guide-') as tmp:
        src = Path(tmp) / 'guide.html'
        src.write_text(page(g), encoding='utf-8')
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome')
            pg = browser.new_page()
            pg.goto(src.as_uri())
            pg.wait_for_function('() => [...document.images].every(i => i.complete && i.naturalWidth > 0)', timeout=20000)
            pg.pdf(path=str(ug.PDF), format='A4', print_background=True, prefer_css_page_size=True, display_header_footer=True,
                   header_template='<span></span>', footer_template=FOOTER, outline=True, tagged=True)
            browser.close()
    data = ug.PDF.read_bytes()
    ug.MANIFEST.write_text(json.dumps({
        'source_sha256': ug.source_hash(), 'pdf_sha256': hashlib.sha256(data).hexdigest(), 'pdf_bytes': len(data),
        'shots': {s: hashlib.sha256((ug.DIR / f'{s}.jpg').read_bytes()).hexdigest() for s in sorted(set(shots))},
        'built': datetime.date.today().isoformat()}, ensure_ascii=False, indent=1) + '\n')
    print(f'{ug.PDF.relative_to(ROOT)}: {len(data) // 1024} KB, {len(g["chapters"])} chapters, {len(shots)} screenshots')


if __name__ == '__main__':
    main()
