#!/usr/bin/env python3
"""Multi-device UI tests for Flow /next: phone, phone sideways, tablet and desktop; touch, keyboard and mouse.

    python3 tools/ui_test.py [out dir] [phone|phone-land|tablet|desktop|progress|listen-speak|sprint|start …]   # needs: pip install playwright

Starts its own local server (tools/ui_server.py: throwaway database, simulated AI, one signed-in learner per device),
so every run begins from the same state, and drives the installed Google Chrome.

Checks layout (no sideways scrolling, nothing hidden under the bottom tabs, touch targets), and the input paths that
learners reported problems with: keyboard shortcuts, Enter in answer boxes, swipes in review, closing sheets, the
playback stop button, step switching, list filters. Screenshots of every page per device go to the out dir.
"""
import atexit, json, os, re, socket, subprocess, sys, tempfile, time, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright
from quiet import silent  # every browser it starts makes no sound (tools/quiet.py)

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='flow-ui-out-'))
OUT.mkdir(parents=True, exist_ok=True)
ONLY = sys.argv[2:]
STATE = Path(tempfile.mkdtemp(prefix='flow-ui-state-'))
with socket.socket() as _s:
    _s.bind(('127.0.0.1', 0)); PORT = _s.getsockname()[1]
SERVER = subprocess.Popen([sys.executable, str(Path(__file__).with_name('ui_server.py')), str(PORT), str(STATE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(SERVER.terminate)
for _ in range(120):
    if (STATE / 'sessions.json').exists():
        break
    time.sleep(0.25)
time.sleep(0.5)
CFG = json.loads((STATE / 'sessions.json').read_text())
BASE, PID = CFG['base'], CFG['pid']
DEVICES = {
    'phone': dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
    'phone-land': dict(viewport={'width': 844, 'height': 390}, is_mobile=True, has_touch=True, device_scale_factor=2),
    'tablet': dict(viewport={'width': 820, 'height': 1180}, is_mobile=True, has_touch=True, device_scale_factor=2),
    'desktop': dict(viewport={'width': 1440, 'height': 900}, is_mobile=False, has_touch=False, device_scale_factor=1),
}
PAGES = ['#/', '#/library', f'#/m/{PID}/listen', f'#/m/{PID}/read', f'#/m/{PID}/check', f'#/m/{PID}/output', f'#/m/{PID}/output/retell',
         f'#/m/{PID}/output/dialog', f'#/m/{PID}/output/translate', f'#/m/{PID}/output/essay', '#/cards', '#/cards/mistake', '#/vocab/plan',
         '#/vocab/test', '#/review', '#/sounds', '#/sounds/th-s', '#/report', '#/me', '#/import', '#/graph', '#/graph/voice-basic', '#/graph/emph-inversion', '#/welcome/edit',
         '#/placement', '#/exam', '#/exam/cet6', '#/series/lighthouse-ledger', '#/m/v5-culture-c1-lighthouse-ledger-1/read',
         '#/mix', '#/mix/pair/tense-past,tense-perfect', '#/graph/link-contrast',
         '#/easy', '#/words/confuse', '#/words/confuse/borrow-lend,make-do', '#/speak', '#/speak/cafe-order', '#/speak/ielts', '#/speak/ielts/p1-mornings', '#/speak/ielts/p2-skill', '#/growth', '#/series/a-new-term',
         '#/radar', '#/radar/goals', '#/radar/test', '#/radar/test/reading', '#/radar/test/writing',
         '#/practice', '#/guide', '#/guide/words', '#/feedback', '#/weekly-off/not-a-real-link-0123456789']
RESULTS = []
NEXT_PARTS = sorted((Path(__file__).resolve().parent.parent / 'flow/public/src/next').glob('*.js'))


def page_error(pg, e):
    """A script error with where it happened: the route, and the part file and line of the first frame in next.js
    (next.js is the parts joined byte for byte, so a line number maps back to one part)."""
    where = ''
    m = re.search(r'next\.js[^:\s]*:(\d+):\d+', getattr(e, 'stack', '') or '')
    if m:
        n = int(m.group(1))
        for part in NEXT_PARTS:
            k = part.read_text().count('\n')
            if n <= k:
                where = f' at {part.name}:{n}'
                break
            n -= k
    route = pg.url.split('#', 1)[1] if '#' in pg.url else '/'
    return f'{getattr(e, "message", e)} (#{route}{where})'


def png(w=60, h=120, rgb=(31, 157, 85)):
    """A small real PNG (a screenshot stand-in the page can draw and shrink)."""
    import struct, zlib
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def check(dev, name, ok, detail=''):
    RESULTS.append({'device': dev, 'check': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(f"{'PASS' if ok else 'FAIL'} [{dev}] {name}{'' if ok else '  ' + str(detail)[:300]}", flush=True)
    return ok


def settle(pg, sel='#view h1, #view .review, #view .empty, #view .done-card', timeout=8000):
    # waits that poll without eval, so they work under the page's CSP in WebKit too (it does not honour bypass_csp)
    pg.wait_for_selector('#view .skeleton', state='detached', timeout=timeout)
    pg.wait_for_selector('#splash', state='detached', timeout=timeout)  # 启动动画 (09-start.js) has left
    try:
        pg.wait_for_selector(sel, timeout=timeout)
    except Exception:
        pass
    pg.wait_for_timeout(350)  # entrance animations


def go(pg, hash_):
    pg.evaluate("h => { location.hash = h; }", hash_)
    pg.wait_for_timeout(50)
    settle(pg)


def touch_swipe(pg, sel, dx, dy=0):
    """A one-finger swipe made of real TouchEvents (Playwright only taps)."""
    pg.evaluate("""([sel, dx, dy]) => {
      const el = document.querySelector(sel); const r = el.getBoundingClientRect();
      const x = r.left + r.width / 2, y = r.top + Math.min(r.height / 2, 120);
      const mk = (type, X, Y) => { const t = new Touch({ identifier: 1, target: el, clientX: X, clientY: Y });
        el.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [t], changedTouches: [t] })); };
      mk('touchstart', x, y); for (let k = 1; k <= 6; k++) mk('touchmove', x + dx * k / 6, y + dy * k / 6); mk('touchend', x + dx, y + dy);
    }""", [sel, dx, dy])


LAYOUT_JS = """(touch) => {
  const W = innerWidth, H = innerHeight, out = {};
  out.overflow = document.scrollingElement.scrollWidth - W;
  const wide = [...document.querySelectorAll('#view *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > W + 1 && getComputedStyle(e).position !== 'fixed'; })
    .slice(0, 5).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right));
  out.wide = wide;
  // squeezed text: a run of words forced into a sliver, one word per line (a layout bug the eye catches at once)
  out.squeezed = [...document.querySelectorAll('#view span, #view p, #view div')].filter(e => e.offsetParent !== null && e.children.length === 0)
    .filter(e => { const t = (e.textContent || '').trim(); const r = e.getBoundingClientRect(); return t.split(/\s+/).length >= 6 && r.width > 0 && r.width < 90 && r.height > 120; })
    .slice(0, 5).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().width) + 'px "' + e.textContent.trim().slice(0, 30) + '"');
  // touch targets: interactive controls smaller than 32x32 (inline word spans and links inside running text excluded)
  if (touch) {
    out.small = [...document.querySelectorAll('#view button, #view a, #view select, #view input:not([type=hidden]), .tabs a')]
      .filter(e => e.offsetParent !== null && !e.closest('.text, .p, .ctx, .small p, .muted, .tiny, p, .legend') && !(e.tagName === 'INPUT' && e.closest('label')))
      .map(e => { const r = e.getBoundingClientRect(); return [e, r]; })
      .filter(([e, r]) => r.width && (r.width < 32 || r.height < 32))
      .slice(0, 8).map(([e, r]) => `${e.tagName}${e.id ? '#' + e.id : ''}.${[...e.classList].join('.')} "${(e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 14)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
    // fields under 16px make iOS Safari zoom in on focus and stay zoomed
    out.smallFields = [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]), select, textarea')]
      .filter(e => e.offsetParent !== null && parseFloat(getComputedStyle(e).fontSize) < 16).slice(0, 5)
      .map(e => `${e.tagName}${e.id ? '#' + e.id : ''} ${getComputedStyle(e).fontSize}`);
  }
  return out;
}"""

COVER_JS = """() => {
  // After scrolling to the bottom: is the last control on the page covered by the bottom tabs or another fixed layer?
  scrollTo(0, document.scrollingElement.scrollHeight);
  // (a control inside a folded <details> is not on the page until it is opened)
  const els = [...document.querySelectorAll('#view button:not([disabled]), #view a.btn, #view a.link')].filter(e => e.offsetParent !== null && !(e.closest('details:not([open])') && !e.closest('summary')));
  const last = els[els.length - 1]; if (!last) return null;
  let r = last.getBoundingClientRect();
  const head = document.getElementById('bar').getBoundingClientRect().bottom;
  if (r.top < head) { scrollBy(0, r.top - head - 12); r = last.getBoundingClientRect(); }  // a short page: it was under the top bar
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  if (y > innerHeight || y < 0) return 'offscreen ' + Math.round(y) + ' of ' + innerHeight;
  const hit = document.elementFromPoint(x, y);
  return hit && (hit === last || last.contains(hit)) ? 'ok' : 'covered by ' + (hit ? hit.tagName + '.' + hit.className : 'nothing');
}"""


def run_device(pw, dev, opts):
    ctx = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv).new_context(**opts, locale='zh-CN', bypass_csp=True)
    ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners'][dev]['token'], 'url': BASE}])
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(page_error(pg, e)))
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'favicon' not in m.text and '/audio/' not in m.text else None)
    touch = opts['has_touch']
    starts = []  # each one a round trip; from mainland China about a second
    pg.on('request', lambda r: starts.append(r.url.split('?')[0].split(BASE, 1)[-1]) if r.url.split('?')[0].endswith(('/api/session', '/api/next/home')) else None)
    pg.goto(BASE + '/', wait_until='networkidle')
    settle(pg)

    # ---- start-up: the home data carries the session, so the first screen needs one request; the next time the
    # app is opened the page itself comes from the service worker's cache, without waiting on the network
    check(dev, 'start: one request for session and home', starts == ['/api/next/home'], starts)
    pg.evaluate('navigator.serviceWorker.ready.then(() => true)')
    starts.clear()
    resp = pg.reload(wait_until='networkidle'); settle(pg)
    cached = bool(resp and resp.from_service_worker)
    check(dev, 'reopen: page from the cache, still one request', cached and starts == ['/api/next/home'], (cached, starts))
    k = pg.text_content('#view .greet') or ''
    check(dev, 'reopen: signed in from that one request', f'ui-{dev}' in k, k)

    # ---- every page: no sideways scroll, controls reachable, screenshot
    for h in PAGES:
        try:
            go(pg, h)
            lay = pg.evaluate(LAYOUT_JS, touch)
            check(dev, f'{h} no sideways scroll', lay['overflow'] <= 1, f"{lay['overflow']}px {lay['wide']}")
            check(dev, f'{h} no squeezed text', not lay['squeezed'], lay['squeezed'])
            if touch:
                check(dev, f'{h} touch targets ≥ 32px', not lay['small'], lay['small'])
                check(dev, f'{h} fields ≥ 16px (no zoom on focus)', not lay['smallFields'], lay['smallFields'])
            cov = pg.evaluate(COVER_JS)
            check(dev, f'{h} last control not covered', cov in (None, 'ok'), cov)
            pg.evaluate('scrollTo(0, 0)')
            pg.screenshot(path=str(OUT / f"{dev}-{h.strip('#/').replace('/', '_') or 'home'}.png"), full_page=False)
        except Exception as e:
            check(dev, f'{h} renders', False, repr(e)[:300])

    # ---- home: one clear next action that goes to the plan's next step
    go(pg, '#/')
    first = pg.evaluate("() => { const b = document.querySelector('#view .go-next'); const r = b && b.getBoundingClientRect(); return b ? [b.getAttribute('href'), Math.round(r.top), innerHeight, document.querySelectorAll('#view .go-next').length] : null; }")
    check(dev, 'home: one primary next-step button, on the first screen', first and first[3] == 1 and first[1] < first[2], first)
    nexthref = pg.evaluate("() => (document.querySelector('.prow.next') || {}).getAttribute ? document.querySelector('.prow.next').getAttribute('href') : null")
    check(dev, 'home: the button goes to the highlighted next step', first and nexthref == first[0], (first, nexthref))
    k = pg.text_content('#view .greet') or ''
    check(dev, 'greeting shows the username as written', f'ui-{dev}' in k, k)
    hm = pg.evaluate("() => ({notices: document.querySelectorAll('#notice > *').length, tabs: [...document.querySelectorAll('.tabs a span')].map(s => s.textContent), map: !!document.querySelector('#view .graph-mini'), rows: document.querySelectorAll('#view .mlist .mrow').length, more: (document.querySelector('#view .mrow.more') || {}).getAttribute ? document.querySelector('#view .mrow.more').getAttribute('href') : ''})")
    check(dev, 'home: four tabs, at most one notice, materials as rows ending in 更多材料', hm['tabs'] == ['今日', '练习', '单词', '我的'] and hm['notices'] <= 1 and not hm['map'] and hm['rows'] >= 2 and hm['more'] == '#/library', hm)

    # ---- study steps: the green indicator sits under the selected step after moving between steps
    for st in ('read', 'check', 'output', 'listen'):
        go(pg, f'#/m/{PID}/{st}'); pg.wait_for_timeout(450)
        off = pg.evaluate("() => { const i = document.querySelector('.steps .ind').getBoundingClientRect(), a = document.querySelector('.steps [aria-selected=true]').getBoundingClientRect(); return Math.round(Math.abs(i.left - a.left) + Math.abs(i.width - a.width)); }")
        check(dev, f'step indicator under the selected step ({st})', off <= 2, f'{off}px off')

    # ---- knowledge graph: one next point to practise, 13 topic tiles, a tile takes you to its points
    go(pg, '#/graph')
    pg.evaluate("() => { try { localStorage.removeItem('flow-graph-view'); } catch (e) {} }"); go(pg, '#/'); go(pg, '#/graph'); pg.wait_for_timeout(900)
    rt = pg.evaluate("() => ({nodes: document.querySelectorAll('#gRoute .rnode').length, bands: document.querySelectorAll('#gRoute .rband').length, here: document.querySelectorAll('#gRoute .rnode.here').length, drawn: document.querySelectorAll('#gRoute .rnode.drawn').length, shown: !document.getElementById('gRoute').hidden})")
    check(dev, 'graph: the learning route shows 44 points on 4 lines, one marked as next', rt['shown'] and rt['nodes'] == 44 and rt['bands'] == 4 and rt['here'] == 1 and rt['drawn'] == 44, rt)
    fold = pg.evaluate("() => { const o = [...document.querySelectorAll('#gRoute details.rband[open]')]; return [o.length, o.length === 1 && !!o[0].querySelector('.rnode.here'), !!document.querySelector('.tabs [data-nav=practice][aria-current=page]')]; }")
    check(dev, 'graph: only the level with the next stop is open, under the 练习 tab', fold[0] == 1 and fold[1] and fold[2], fold)
    pg.click('#gRoute details.rband:not([open]) > summary >> nth=0'); pg.wait_for_timeout(300)
    check(dev, 'graph: a folded level opens', pg.evaluate("() => document.querySelectorAll('#gRoute details.rband[open]').length") == 2)
    pg.click('[data-gv="all"]'); pg.wait_for_timeout(300)
    g = pg.evaluate("() => ({next: document.querySelectorAll('#view .go-next').length, href: (document.querySelector('#view .go-next') || {}).getAttribute ? document.querySelector('#view .go-next').getAttribute('href') : '', tiles: document.querySelectorAll('.tgrid .tile').length, rows: document.querySelectorAll('.nrow').length})")
    check(dev, 'graph: one next point and 13 topics with 44 points', g['next'] == 1 and g['href'].startswith('#/graph/') and g['tiles'] == 13 and g['rows'] == 44, g)
    pg.click('.tgrid .tile >> nth=9'); pg.wait_for_timeout(900)
    top = pg.evaluate("() => Math.round(document.getElementById('topic-compare').getBoundingClientRect().top)")
    check(dev, 'graph: a topic tile scrolls to its points', 0 <= top < pg.viewport_size['height'] / 2, top)

    # ---- a point's page: the teaching page, then practice that is checked and lights the point
    go(pg, '#/graph/voice-basic')
    parts = pg.evaluate("() => ({steps: document.querySelectorAll('.steps-list li').length, pits: document.querySelectorAll('.pit').length, qs: document.querySelectorAll('#practice .gq').length})")
    check(dev, 'point page: steps, mistakes and 4 practice questions', parts['steps'] >= 3 and parts['pits'] >= 2 and parts['qs'] == 4, parts)
    rel = pg.evaluate("() => ({l1: document.querySelectorAll('.l1 .l1-rows > div').length, flow: document.querySelectorAll('.rel-flow .rel-step').length, confuse: document.querySelectorAll('.confuse a.btn').length})")
    check(dev, 'point page: the Chinese-speaker trap and the points it connects to', rel['l1'] == 3 and rel['flow'] >= 2 and rel['confuse'] >= 1, rel)
    pg.click('#toPractice'); pg.wait_for_timeout(700)
    # Rounds are drawn at random with shuffled options, so the test does not know the answer: either way the right
    # option is shown, and the point lights up (right) or is marked to fix with a re-check tomorrow (wrong).
    pg.click('#practice .gq >> nth=0 >> .ans >> nth=0'); pg.wait_for_timeout(800)
    fb = pg.evaluate("() => ({fb: document.querySelector('#practice .gq .fb').textContent, right: !!document.querySelector('#practice .gq .ans.right'), status: document.getElementById('nodeStatus').textContent, review: document.getElementById('nodeReview').textContent})")
    ok = fb['fb'].startswith('✓') and fb['status'] == '做题已验证' and '下次复习' in fb['review'] or fb['fb'].startswith('✗') and fb['status'] == '需要留意' and '明天' in fb['review']
    check(dev, 'point page: an answer is checked, the point changes and its next re-check is shown', fb['right'] and ok, fb)
    for k in range(1, 4):
        pg.click(f'#practice .gq >> nth={k} >> .ans >> nth=0'); pg.wait_for_timeout(500)
    check(dev, 'point page: after the round, another round of 4 is offered', pg.is_visible('#again'))
    before = pg.evaluate("() => [...document.querySelectorAll('#practice .gq .prompt')].map(x => x.textContent).join('|')")
    pg.click('#again'); settle(pg); pg.wait_for_timeout(300)
    after = pg.evaluate("() => ({qs: document.querySelectorAll('#practice .gq').length, p: [...document.querySelectorAll('#practice .gq .prompt')].map(x => x.textContent).join('|')})")
    check(dev, 'point page: the next round is a new draw', after['qs'] == 4 and after['p'] != before, after['qs'])

    # ---- starting check: band by band until it is decided, then a level and the points to fix
    go(pg, '#/placement')
    pg.click('#pStart'); pg.wait_for_timeout(300)
    asked = 0
    while asked < 16 and not pg.query_selector('#pUse'):
        pg.click('.place .ans >> nth=0' if asked % 3 else '#pSkip'); asked += 1
        pg.wait_for_timeout(450)
    res = pg.evaluate("() => ({h: (document.querySelector('#view h1') || {}).textContent || '', bands: document.querySelectorAll('.pl-bands .pl-band').length})")
    check(dev, 'starting check: ends with a level and band scores', res['h'].startswith('建议从') and 1 <= res['bands'] <= 4 and asked % 4 == 0, (res, asked))

    # ---- exam practice: a timed paper (its size set by the learner's minutes a day), handed in once, scored by part
    go(pg, '#/exam/cet4')
    ex = pg.evaluate("""() => { const c = document.querySelector('#view .opt[aria-pressed=true]'), d = document.getElementById('examCur');
      return c && d ? [Math.round(d.getBoundingClientRect().top - c.getBoundingClientRect().bottom), getComputedStyle(document.getElementById('exStart')).backgroundColor !== getComputedStyle(document.querySelector('#view .opt:not([aria-pressed=true])')).backgroundColor] : null; }""")
    check(dev, 'exam: the chosen exam opens right under its card, 开始一套 in the primary style', ex and 0 <= ex[0] <= 40 and ex[1], ex)
    with pg.expect_response(lambda r: r.url.endswith('/api/next/exam/paper')) as got:
        pg.click('#exStart')
    paper = got.value.json()
    want = sum(len(p.get('items', [])) + sum(len(x['items']) for x in p.get('passages', [])) for p in paper['parts'])
    pg.wait_for_selector('.exam-bar', timeout=8000); pg.wait_for_timeout(300)
    n = pg.evaluate("() => document.querySelectorAll('.exam-part .gq').length")
    check(dev, 'exam: every question of the paper (as the server sizes it) in three parts with a clock',
          n == want and n >= 18 and pg.evaluate("() => document.querySelectorAll('.exam-part').length") == len(paper['parts']) == 3, (n, want))
    marks = pg.evaluate("""() => ({ passages: [...document.querySelectorAll('.exam-part article h3')].map(h => !!h.querySelector('.ai-mark')),
      grammar: [...document.querySelectorAll('.exam-part')].filter(s => s.querySelector('h2').textContent.startsWith('语法')).map(s => (s.querySelector('.ai-line') || {}).textContent || '') })""")
    check(dev, 'exam: 「AI 生成」 by every passage; 语法 (the bank, original and AI-assisted) says 「题目和解析由 AI 辅助编写」',
          marks['passages'] and all(marks['passages']) and len(marks['grammar']) == 1 and '题目和解析由 AI 辅助编写' in marks['grammar'][0], marks)
    for k in range(n):
        pg.click(f'.exam-part .gq >> nth={k} >> .ans >> nth=0')
    pg.click('#exDone'); pg.wait_for_timeout(900)
    res = pg.evaluate("() => ({h: (document.querySelector('#view h1') || {}).textContent || '', parts: document.querySelectorAll('.exam-score div').length})")
    check(dev, 'exam: handed in, scored by part', '题做对' in res['h'] and res['parts'] == 3, res)
    missed = pg.evaluate("() => [...document.querySelectorAll('#view h2')].filter(h => h.textContent.startsWith('没认出')).map(h => !!h.querySelector('.ai-voice'))")
    check(dev, 'exam: 没认出的词 (their sound is synthesized) says 「AI 朗读」 by its heading', missed in ([], [True]), missed)

    # ---- serial: six episodes in order, an episode names its place in the series
    go(pg, '#/series/lighthouse-ledger')
    eps = pg.evaluate("() => document.querySelectorAll('.serial .ep').length")
    check(dev, 'serial: six episodes and a way to carry on', eps == 6 and pg.is_visible('#view .btn.primary'), eps)
    go(pg, '#/m/v5-culture-c1-lighthouse-ledger-2/read')
    check(dev, 'serial: an episode shows its place in the series', '第 2 / 6 集' in (pg.text_content('.study-head .kicker') or ''))

    # ---- listen: whole-text playback shows a stop control that stays on screen, and it stops
    go(pg, f'#/m/{PID}/listen')
    lp = pg.evaluate("() => { const p = document.getElementById('playAll').getBoundingClientRect(), w = document.querySelector('#view .preread'); return [Math.round(p.top), w ? Math.round(w.getBoundingClientRect().top) : null, w ? w.open : null, innerHeight]; }")
    check(dev, 'listen: 播放全文 comes first, on the first screen; the words to know are folded under it', lp[0] < lp[3] and (lp[1] is None or (lp[1] > lp[0] and lp[2] is False)), lp)
    ps = pg.evaluate("""() => { const d = document.querySelector('#view .playset'), l = document.querySelector('#view .line[data-i="0"]');
      return {open: d ? d.open : null, sum: (document.getElementById('psum') || {}).textContent, first: l ? Math.round(l.getBoundingClientRect().top) : null, h: innerHeight}; }""")
    check(dev, 'listen: 语速、复读 and 停顿 fold into one line that says how it will play', ps['open'] is False and '每句' in (ps['sum'] or ''), ps)
    if dev == 'phone':
        check(dev, 'listen: the first sentence is on the first screen of a phone', ps['first'] is not None and ps['first'] < ps['h'], ps)
    pg.click('#view .playset > summary'); pg.click('#view [data-rate="1.25"]')
    s125 = pg.text_content('#psum') or ''
    pg.click('#view [data-rate="1"]'); pg.click('#view .playset > summary')
    check(dev, 'listen: 播放设置 opens the choices, and the line follows them', '1.25×' in s125 and pg.evaluate("() => !document.querySelector('#view .playset').open"), s125)
    if dev == 'phone-land':
        pa = pg.evaluate("() => { const r = document.getElementById('playAll').getBoundingClientRect(); return [Math.round(r.bottom), innerHeight]; }")
        check(dev, 'listen: a phone held sideways shows 播放全文 on the first screen (a short study header)', pa[0] <= pa[1], pa)
    pg.click('#view [data-mode="shadow"]'); pg.wait_for_selector('#view .line.sh', timeout=5000)
    def shadow_tools():
        return pg.evaluate("""() => [...document.querySelectorAll('#view .line.sh')].map(l => [l.classList.contains('cur'), !!(l.querySelector('[data-r]') || {}).offsetParent, !!(l.querySelector('[data-o]') || {}).offsetParent])""")
    t0 = shadow_tools()
    pg.click('#view .line.sh[data-i="2"] .txt'); t2 = shadow_tools()
    check(dev, '跟读: ● 对比 AI 点评 under the sentence being practised only, ▶ on every one; a tap picks another',
          [x[1] for x in t0].count(True) == 1 and t0[0][1] and all(x[2] for x in t0) and t2[2][0] and t2[2][1] and [x[1] for x in t2].count(True) == 1, (t0[:3], t2[:3]))
    pg.click('#view [data-mode="listen"]'); pg.wait_for_selector('#playAll', timeout=5000)
    pg.click('#playAll')
    pg.wait_for_timeout(250)
    mini = pg.evaluate("() => { const m = document.querySelector('.mini-player'); if (!m || m.hidden) return null; const r = m.getBoundingClientRect(); return [r.top, r.bottom, innerHeight]; }")
    check(dev, 'playing shows the floating stop control in view', mini and mini[0] >= 0 and mini[1] <= mini[2], mini)
    btn = pg.inner_html('#playAll')
    check(dev, 'play button turns into a pause button', '暂停' in btn and '<rect' in btn, btn[:120])
    if mini:
        pg.click('.mini-player .stop')
        pg.wait_for_timeout(150)
    check(dev, 'stop hides the control', pg.evaluate("() => { const m = document.querySelector('.mini-player'); return !m || m.hidden; }"))
    if not touch:
        pg.keyboard.press('Space'); pg.wait_for_timeout(200)
        check(dev, 'Space starts playback (desktop)', '暂停' in pg.inner_html('#playAll'))
        pg.keyboard.press('Space'); pg.wait_for_timeout(150)

    # ---- audio: when this server cannot send a material's narration, the page fetches it from the media domain itself
    hits = []
    def media_origin(route):
        hits.append(route.request.url)
        cors = {'Access-Control-Allow-Origin': '*'}
        if route.request.url.split('?')[0].endswith('.json'):
            route.fulfill(status=200, content_type='application/json', headers=cors,
                          body=json.dumps({'v': 1, 'duration': 2, 'sentences': [{'s': 0, 'e': 2, 'w': [[0, 0, 1]]}]}))
        else:
            route.fulfill(status=200, content_type='audio/mp4', headers=cors, body=b'not really audio')
    pg.route('http://127.0.0.1:9/**', media_origin)
    go(pg, '#/m/v5-culture-c1-lighthouse-ledger-3/listen')
    pg.click('#playAll'); pg.wait_for_timeout(2500)
    check(dev, 'audio: timings and sound come from the media domain when this server cannot send them',
          any('/audio/' in h and '.json?v=uitest000001' in h for h in hits) and any('/audio/' in h and '.m4a?v=uitest000001' in h for h in hits), hits[:4])
    pg.evaluate("() => { const s = document.querySelector('.mini-player .stop'); if (s && !s.closest('[hidden]')) s.click(); }")
    pg.unroute('http://127.0.0.1:9/**')
    # ---- audio: this server sends the timings, but its sound file fails while play() is waiting. The page switches to
    # the media domain inside the file's error event, and play() reports its failure only after that, so the report
    # must not end the playback with a false alarm. (A context without the service worker, so requests can be held.)
    # The page uses a recording only when its timings have one entry per sentence of the text (else the browser voice).
    sound = (Path(__file__).with_name('ui-fixtures') / 'audio' / 'words' / 'us' / 'w000.m4a').read_bytes()  # 2 s
    mctx = ctx.browser.new_context(**opts, locale='zh-CN', bypass_csp=True, service_workers='block')
    mctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners'][dev]['token'], 'url': BASE}])
    n = len(mctx.request.get(BASE + '/api/next/material?id=v5-culture-c1-lighthouse-ledger-3').json()['sentences'])
    timing = json.dumps({'v': 1, 'duration': 2, 'sentences': [{'s': 2 * i / n, 'e': 2 * (i + 1) / n, 'w': [[0, 2 * i / n, 2 * (i + 1) / n]]} for i in range(n)]})
    mp, held, alt = mctx.new_page(), [], []
    mp.route(BASE + '/audio/**', lambda r: r.fulfill(status=200, content_type='application/json', body=timing) if '.json' in r.request.url else held.append(r))
    mp.route('http://127.0.0.1:9/**', lambda r: (alt.append(r.request.url), r.fulfill(status=200, content_type='audio/mp4', headers={'Access-Control-Allow-Origin': '*'}, body=sound)))
    mp.goto(BASE + '/#/m/v5-culture-c1-lighthouse-ledger-3/listen', wait_until='domcontentloaded'); settle(mp, '#playAll')
    mp.click('#playAll'); mp.wait_for_timeout(150)
    for r in held:
        r.fulfill(status=404, body='')
    mp.wait_for_timeout(600)
    toast = mp.evaluate("() => { const t = document.getElementById('toast'); return t && t.classList.contains('show') ? t.textContent : ''; }")
    media = mp.evaluate("[...document.querySelectorAll('audio')].some(a => a.src.startsWith('http://127.0.0.1:9/') && !a.paused)")
    check(dev, "audio: this server's sound failing while play() waits, the media domain's plays on, with no false alarm",
          held and media and '没加载出来' not in toast and '无法播放' not in toast and mp.evaluate("document.body.classList.contains('playing')"),
          {'held': len(held), 'alt': alt[:2], 'playing from the media domain': media, 'toast': toast})
    mctx.close()

    # ---- read: the ✦ of every sentence sits on the same line as the sentence's last word
    go(pg, f'#/m/{PID}/read')
    bad = pg.evaluate("""() => [...document.querySelectorAll('#reader [data-ex]')].filter(b => {
        const w = b.parentElement.querySelector('.w'); if (!w) return false;
        return Math.abs(b.getBoundingClientRect().top - w.getBoundingClientRect().top) > 12; }).length""")
    check(dev, '✦ never wraps away from its sentence', bad == 0, f'{bad} detached')
    rd2 = pg.evaluate("() => { const r = document.getElementById('reader').getBoundingClientRect(), t = document.getElementById('toCheck'), g = document.getElementById('gains'); return {gap: Math.round(t.getBoundingClientRect().top - r.bottom), primary: t.classList.contains('primary'), folded: g ? !g.open : null, tabs: g ? g.querySelectorAll('[data-gt]').length : 0}; }")
    check(dev, 'read: the next step comes right after the text; the extras fold into one card with tabs', rd2['gap'] < 120 and rd2['primary'] and rd2['folded'] and rd2['tabs'] >= 2, rd2)
    pg.evaluate("document.getElementById('gains').open = true"); pg.click('#gains [data-gt="words"]'); pg.wait_for_timeout(200)
    shown = pg.evaluate("() => [...document.querySelectorAll('#gains [data-gp]')].filter(p => !p.hidden).map(p => p.dataset.gp)")
    check(dev, 'read: a tab of 这篇的收获 shows only its own part', shown == ['words'], shown)
    pg.evaluate("document.getElementById('gains').open = false")
    # step switch from far down the page: the first question is visible right under the step bar
    pg.evaluate("scrollTo(0, document.scrollingElement.scrollHeight)")
    pg.wait_for_timeout(200)
    pg.click('#toCheck')
    settle(pg, '.q')
    pg.wait_for_timeout(300)
    pos = pg.evaluate("""() => { const q = document.querySelector('.q .prompt'), s = document.querySelector('.steps');
        return [Math.round(q.getBoundingClientRect().top), Math.round(s.getBoundingClientRect().bottom), innerHeight]; }""")
    check(dev, 'after 读完了 the first question is visible below the step bar', pos[0] >= pos[1] - 2 and pos[0] < pos[2] - 40, pos)

    # ---- lookup sheet: opens on a word; Esc closes and gives focus back (keyboard); dragging down closes (touch)
    go(pg, f'#/m/{PID}/read')
    pg.click('#reader .w >> nth=3')
    pg.wait_for_selector('#sheetCard .word', timeout=5000)
    if touch:
        touch_swipe(pg, '#sheetCard', 0, 160)
        pg.wait_for_timeout(250)
        check(dev, 'dragging the sheet down closes it', pg.is_hidden('#sheet'))
    else:
        pg.keyboard.press('Tab'); pg.keyboard.press('Tab'); pg.keyboard.press('Tab'); pg.keyboard.press('Tab'); pg.keyboard.press('Tab'); pg.keyboard.press('Tab'); pg.keyboard.press('Tab')
        inside = pg.evaluate("() => document.getElementById('sheetCard').contains(document.activeElement)")
        check(dev, 'Tab stays inside the open sheet', inside)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        check(dev, 'Esc closes the sheet', pg.is_hidden('#sheet'))
        # keyboard reading: focus the text, → moves a word cursor, ↵ opens it; Esc brings focus back to the text
        pg.focus('#reader'); pg.keyboard.press('ArrowRight'); pg.keyboard.press('ArrowRight'); pg.keyboard.press('Enter')
        pg.wait_for_selector('#sheetCard .word', timeout=5000)
        check(dev, 'arrow keys + Enter look up a word', pg.is_visible('#sheetCard .word'))
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        check(dev, 'focus returns to the text after closing', pg.evaluate("() => document.activeElement && document.activeElement.id === 'reader'"))
        pg.keyboard.press('?'); pg.wait_for_timeout(200)
        check(dev, '? shows the shortcut list', '键盘快捷键' in (pg.text_content('#sheetCard') or ''))
        pg.keyboard.press('Escape')

    # ---- saving from the sheet keeps it open and marks the word in the text
    pg.click('#reader .w >> nth=5')
    pg.wait_for_selector('#saveW', timeout=5000)
    w = (pg.text_content('#sheetCard .word') or '').strip().lower()
    pg.click('#saveW'); pg.wait_for_timeout(900)
    check(dev, 'sheet stays open after saving a word', pg.is_visible('#sheet') and '已' in (pg.text_content('#saveW') or ''), pg.text_content('#saveW'))
    pg.evaluate("document.querySelector('#sheet [data-close]').click()")

    # ---- typing on a phone hides the bottom tabs; ⌘/Ctrl+Enter submits on desktop
    go(pg, f'#/m/{PID}/output/essay')
    pg.click('#esIn')
    pg.wait_for_timeout(200)
    if touch and opts['viewport']['width'] < 760:
        check(dev, 'bottom tabs step aside while typing', not pg.is_visible('.tabs'))
    pg.fill('#esIn', ' '.join(['The train is noisy but my headphones help me focus on my work every morning.'] * 4))
    if not touch:
        pg.keyboard.press('Meta+Enter' if sys.platform == 'darwin' else 'Control+Enter')
        pg.wait_for_selector('#esOut .result', timeout=8000)
        check(dev, '⌘/Ctrl+Enter submits the essay', pg.is_visible('#esOut .result'))
    pg.evaluate('document.activeElement && document.activeElement.blur()')

    # ---- dialogue: after the AI's line the answer box is on screen, above the tabs
    go(pg, f'#/m/{PID}/output/dialog')
    pg.click('#dlgStart')
    pg.wait_for_selector('#dlgIn:not([hidden])', timeout=8000)
    pg.wait_for_timeout(700)
    vis = pg.evaluate("""() => { const t = document.querySelector('#dlgText').getBoundingClientRect(), tabs = document.querySelector('.tabs').getBoundingClientRect();
        const tabTop = getComputedStyle(document.querySelector('.tabs')).position === 'fixed' && document.querySelector('.tabs').offsetParent !== null ? tabs.top : innerHeight;
        return [Math.round(t.top), Math.round(t.bottom), Math.round(tabTop)]; }""")
    check(dev, 'dialogue answer box is visible above the tabs', vis[0] >= 0 and vis[1] <= vis[2] + 1, vis)

    # ---- 读: 中文导读、改写 and 伴读 in one row, the key and hints in one line, the text on a phone's first screen
    go(pg, f'#/m/{PID}/read')
    rd = pg.evaluate("""() => { const r = document.getElementById('reader'), t = document.querySelector('#view .read-tools');
      return {tools: t ? [...t.querySelectorAll('button')].map(b => b.id) : [], top: r ? Math.round(r.getBoundingClientRect().top) : null, h: innerHeight}; }""")
    check(dev, 'read: the tools sit in one row above the text', 'readAlong' in rd['tools'], rd)
    kinds = pg.evaluate("() => [...document.querySelectorAll('#view .read-tools button:not([hidden])')].map(b => b.className.includes('btn small') ? 'btn' : b.id)")
    check(dev, 'read: one kind of button in the row, 「AI 朗读 · 声音由 AI 合成」 on its own line under it',
          all(k == 'btn' for k in kinds) and pg.is_visible('#view .read-ai .ai-voice') and '合成' in (pg.text_content('#view .read-ai') or ''), kinds)
    if dev == 'phone':
        check(dev, 'read: the text starts on the first screen of a phone', rd['top'] is not None and rd['top'] < rd['h'] * 0.6, rd)
    if pg.query_selector('#zhGuide'):
        pg.click('#zhGuide'); opened = pg.is_visible('#zhText'); pg.click('#zhGuide')
        check(dev, 'read: 中文导读 opens under the row and closes again', opened and not pg.is_visible('#zhText'))

    # ---- 用出来: the sub-tab names the exercise, the card does not repeat it
    go(pg, f'#/m/{PID}/output/retell')
    k = pg.evaluate("() => [...document.querySelectorAll('#pane .task .kicker')].map(e => e.textContent.trim())")
    check(dev, '用出来: no heading under the tabs that repeats the tab (复述、对话、用出来)', not set(k) & {'复述', '情景对话', '用出来'}, k)

    # ---- 练习: the grammar map is the wide first card of the 语法 group
    go(pg, '#/practice')
    pm = pg.evaluate("() => { const m = document.querySelector('#view .ptile.pmap'); return m ? [m.getAttribute('href'), m.closest('.pgroup').querySelector('h2').textContent, Math.round(m.getBoundingClientRect().width / m.parentElement.getBoundingClientRect().width * 100), Math.round(m.getBoundingClientRect().top), innerHeight] : null; }")
    check(dev, 'practice: the grammar map is the wide card of the 语法 group, on the first screen', pm and pm[0] == '#/graph' and pm[1] == '语法' and pm[2] >= 98 and pm[3] < pm[4], pm)
    pr = pg.evaluate("""() => ({rows: document.querySelectorAll('#view .px-list .px-row').length, tiles: document.querySelectorAll('#view .ptile:not(.pmap)').length,
      noicon: [...document.querySelectorAll('#view .px-row .pico svg')].filter(x => !x.children.length).length,
      wide: [...document.querySelectorAll('#view .px-row')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).length,
      tall: [...document.querySelectorAll('#view .px-row .t .tiny')].filter(e => e.getBoundingClientRect().height > 24).length})""")
    check(dev, '练习: one row per practice, each with an icon and a one-line note, inside the screen',
          pr['rows'] >= 15 and pr['tiles'] == 0 and pr['noicon'] == 0 and pr['wide'] == 0 and pr['tall'] == 0, pr)
    # r20: a tap on a counted entry point sends its key only (the console compares releases with these counts)
    with pg.expect_request(lambda r: r.url.endswith('/api/next/tap'), timeout=4000) as tap:
        pg.click('#view .ptile.pmap')
    check(dev, 'a counted entry point sends its key and nothing else', json.loads(tap.value.post_data or '{}') == {'k': 'practice-map'}, tap.value.post_data)
    settle(pg)

    # ---- words page: five tools, the stats folded, one short row per word
    go(pg, '#/cards')
    wd = pg.evaluate("() => { const rows = [...document.querySelectorAll('#clist .xrow')]; return {tools: document.querySelectorAll('#view .tools a, #view .tools button').length, folded: !document.getElementById('vStats').open, rows: rows.length, tallest: Math.max(0, ...rows.map(r => Math.round(r.getBoundingClientRect().height)))}; }")
    check(dev, 'words: five tools, the stats folded, one short row per word', wd['tools'] == 5 and wd['folded'] and wd['rows'] >= 10 and wd['tallest'] <= 80, wd)
    # ---- words page: a filter swaps only the list (the header element survives, no flash)
    pg.evaluate("document.querySelector('#view h1').dataset.keep = '1'")
    pg.click('[data-f="mistake"]')
    pg.wait_for_timeout(600)
    check(dev, 'filter swaps only the list', pg.evaluate("() => document.querySelector('#view h1').dataset.keep === '1'"))
    check(dev, 'mistake filter lists mistakes', '错题' in (pg.text_content('#listSlot') or ''))
    pg.click('[data-f="phrase"]'); pg.wait_for_timeout(500)

    # ---- review: stable total; keyboard (desktop) or swipes (touch); Enter submits a fix card
    go(pg, '#/review')
    foot0 = pg.text_content('.rfoot') or ''
    total0 = foot0.split('/')[-1].split('·')[0].strip()
    seen_fix = seen_passage = False
    for step in range(16):
        if pg.query_selector('.done-card'):
            break
        if pg.query_selector('#fixIn'):
            seen_fix = True
            pg.fill('#fixIn', 'would have arrived')
            pg.press('#fixIn', 'Enter'); pg.wait_for_timeout(250)
            # Right: one "next" button. Other words than the reference: the learner says whether it means the same.
            nxt = pg.query_selector('#go') or pg.query_selector('#fixMiss')
            check(dev, 'Enter submits a fix card', nxt is not None and (pg.query_selector('#go') or pg.query_selector('#fixSame')))
            nxt.click(); pg.wait_for_timeout(350); continue
        if pg.query_selector('.qopt'):
            seen_passage = seen_passage or bool(pg.query_selector('.passage-q .ptext'))
            pg.click('.qopt >> nth=0'); pg.wait_for_selector('#go', timeout=5000); pg.click('#go'); pg.wait_for_timeout(350); continue
        if pg.query_selector('#spellIn'):
            pg.fill('#spellIn', 'x'); pg.press('#spellIn', 'Enter'); pg.wait_for_timeout(250); pg.click('#go'); pg.wait_for_timeout(350); continue
        if pg.query_selector('[data-claim]'):
            if touch:
                touch_swipe(pg, '.review', 160)
            else:
                pg.keyboard.press('3')  # 1 2 3 by place: 「认识」 is on the right (KNOW, 50-words.js)
            pg.wait_for_timeout(300)
            check(dev, 'know (swipe right / key 3, the right button) reveals the answer', pg.query_selector('.open-card') is not None) if step < 2 else None
            if touch:
                touch_swipe(pg, '.review', 160)
            else:
                pg.keyboard.press('Enter')
            pg.wait_for_timeout(400)
            foot = pg.text_content('.rfoot') if pg.query_selector('.rfoot') else ''
            if foot and '/' in foot:
                check(dev, 'review total does not grow after a right answer', foot.split('/')[-1].split('·')[0].strip() == total0, f'{foot0} -> {foot}') if step < 3 else None
            continue
        if pg.query_selector('[data-self]'):
            pg.click('[data-self="good"]'); pg.wait_for_timeout(350); continue
        break
    check(dev, 'review reached a fix card', seen_fix)
    check(dev, 'a reading mistake comes back with its part of the text', seen_passage)

    # ---- mixed grammar round: a confusable pair, interleaved, ends with a result
    go(pg, '#/mix/pair/tense-past,tense-perfect')
    n = 0
    while n < 8 and pg.query_selector('#mixQ .ans'):
        pg.click('#mixQ .ans >> nth=0'); pg.wait_for_selector('#mixNext', timeout=5000); pg.click('#mixNext'); pg.wait_for_timeout(250); n += 1
    pg.wait_for_timeout(500)
    res = pg.evaluate("() => ({h: (document.querySelector('#view h1') || {}).textContent || '', rows: document.querySelectorAll('.mix-done .nrow').length})")
    check(dev, 'mixed round: six interleaved questions, then a result per point', n == 6 and '6 题做对' in res['h'] and res['rows'] == 2, (n, res))

    # ---- easy reading: a text one level down, tap a word, say how it felt, see words and speed
    go(pg, '#/easy')
    pg.click('#view .grid-list a.mini >> nth=0'); settle(pg); pg.wait_for_timeout(300)
    pg.click('#easyText .w >> nth=3'); pg.wait_for_timeout(600)
    looked = pg.is_visible('#sheet')
    if looked:
        pg.keyboard.press('Escape') if not touch else pg.click('#sheet [data-close] >> nth=-1'); pg.wait_for_timeout(400)
    pg.click('[data-r="ok"]'); pg.wait_for_selector('.easy-done', timeout=5000)
    res = pg.evaluate("() => [...document.querySelectorAll('.easy-done .easy-stats b')].map(b => b.textContent)")
    check(dev, 'easy reading: a word looks up, and reading gives words and speed', looked and len(res) == 3 and res[0].isdigit(), (looked, res))

    # ---- word confusables: pick two groups, an interleaved round, a result
    go(pg, '#/words/confuse')
    pg.click('.cf-row input >> nth=0'); pg.click('.cf-row input >> nth=1'); pg.wait_for_timeout(100)
    pg.click('#cfMix'); settle(pg)
    n = 0
    while n < 8 and pg.query_selector('#mixQ .ans'):
        pg.click('#mixQ .ans >> nth=0'); pg.wait_for_selector('#mixNext', timeout=5000); pg.click('#mixNext'); pg.wait_for_timeout(250); n += 1
    h = pg.text_content('#view h1') or ''
    check(dev, 'word confusables: two groups mixed into one round', n == 4 and '4 题做对' in h, (n, h))

    # ---- speaking route: twelve scenes, a scene opens a role-play
    go(pg, '#/speak')
    sc = pg.evaluate("() => ({rows: document.querySelectorAll('#view .nrow').length, next: !!document.querySelector('#view a.btn.primary')})")
    check(dev, 'speaking route: twelve scenes and the next one to do', sc['rows'] == 12 and sc['next'], sc)
    go(pg, '#/speak/cafe-order')
    pg.click('#dlgStart'); pg.wait_for_selector('#chat .msg.ai', timeout=8000)
    pg.fill('#dlgText', 'Could I have a large latte, please?'); pg.click('#dlgSend'); pg.wait_for_selector('#chat .msg.me', timeout=8000)
    check(dev, 'speaking route: the AI answers in the scene', pg.evaluate("() => document.querySelectorAll('#chat .msg').length") >= 3)

    # ---- my progress: this month, last month, milestones
    go(pg, '#/growth')
    gw = pg.evaluate("() => ({tiles: document.querySelectorAll('.gtile').length, miles: document.querySelectorAll('.mile').length})")
    check(dev, 'my progress: eight figures and the milestones', gw['tiles'] == 8 and gw['miles'] >= 10, gw)

    # ---- ability radar: set goals, take the reading check, the radar draws the skill against the goal
    go(pg, '#/radar/goals')
    pg.click('[data-all="B2"]'); pg.wait_for_timeout(150); pg.click('[data-d="speaking"][data-l="B1"]'); pg.wait_for_timeout(150)
    pg.click('#gSave'); pg.wait_for_selector('.radar', timeout=8000); pg.wait_for_timeout(300)
    go(pg, '#/radar/test/reading')
    check(dev, 'radar: the reading passage\'s title carries 「AI 生成」', pg.evaluate("!!document.querySelector('#view h2 .ai-mark')"))
    for _ in range(3):
        if not pg.query_selector('#aNext'):
            break
        for box in range(2):
            pg.click(f'.gq >> nth={box} >> .ans >> nth=0')
        pg.click('#aNext'); pg.wait_for_timeout(600)
    h = pg.text_content('#view h1') or ''
    check(dev, 'radar: the reading check ends with a level and a score', '分' in h and '约' in h, h)
    if dev == 'phone':
        # the listening check without a recording: the server's natural voice sentence by sentence (the whole passage
        # at once took 10 s and more before a sound, and fell back to the browser voice past 1500 characters, unsaid);
        # ✕ on the player counts as a play heard, the questions then shown
        asked = []
        on_req = lambda q: asked.append((q.post_data_json or {}).get('text')) if q.url.endswith('/api/next/tts') and q.method == 'POST' else None
        pg.on('request', on_req)
        go(pg, '#/radar/test/listening'); pg.wait_for_selector('#aPlay')
        pg.evaluate("""() => { window.__rspeaks = []; if (window.speechSynthesis) { const s = speechSynthesis.speak.bind(speechSynthesis);
          speechSynthesis.speak = u => { window.__rspeaks.push(u && u.text); return s(u); }; } }""")
        pg.click('#aPlay'); pg.wait_for_selector('.mini-player:not([hidden])', timeout=8000)
        pg.wait_for_timeout(1500)
        got = pg.evaluate("() => ({ speaks: window.__rspeaks.slice(), btn: document.getElementById('aPlay').textContent, status: document.getElementById('aNote').getAttribute('role') })")
        pg.remove_listener('request', on_req)
        check(dev, 'radar: the listening check says 「AI 朗读」 by its player (a synthesized voice, 《标识办法》)', pg.evaluate("!!document.querySelector('#view .ai-voice')"))
        check(dev, 'radar: listening without a recording is the server voice sentence by sentence, not the browser voice, a status line for the wait',
              len(asked) >= 2 and all(t and len(t) < 300 and not re.search(r'[.!?]\s+[A-Z]', t[:-1]) for t in asked) and not got['speaks'] and got['status'] == 'status', (asked[:3], got))
        pg.click('.mini-player .close'); pg.wait_for_timeout(300)
        after = pg.evaluate("() => ({ qs: !document.getElementById('aQs').hidden, plays: document.getElementById('aPlays').textContent, btn: document.getElementById('aPlay').textContent, off: document.getElementById('aPlay').disabled })")
        check(dev, 'radar: ✕ on the player counts as one play: the questions show, 再听一遍 left', after['qs'] and after['plays'] == '已听 1 / 2 遍' and '再听一遍' in after['btn'] and not after['off'], after)
    go(pg, '#/radar'); pg.wait_for_timeout(900)
    rd = pg.evaluate("() => ({axes: document.querySelectorAll('.radar .ax').length, dots: document.querySelectorAll('.radar .dt:not(.none)').length, shown: document.querySelector('.radar .cur').classList.contains('on'), rows: document.querySelectorAll('.rdim').length})")
    check(dev, 'radar: six axes, the measured skill drawn against the goal', rd['axes'] == 6 and rd['dots'] >= 1 and rd['shown'] and rd['rows'] == 6, rd)
    pg.evaluate("document.getElementById('abFold').open = true"); pg.wait_for_selector('#abFold .ab', timeout=5000)
    check(dev, 'radar: the folded estimate from practice lists 8 skills (was 能力画像 on 我的)', pg.evaluate("() => document.querySelectorAll('#abFold .ab').length") == 8)
    go(pg, '#/radar/test/writing')
    pg.fill('#aText', 'I would like to learn to cook because I live alone now and I want to eat better food every day. ' * 3)
    pg.click('#aGo'); pg.wait_for_timeout(1200)
    h = pg.text_content('#view h1') or ''
    check(dev, 'radar: a short text is judged and recorded', '约 B1' in h, h)

    # ---- 学习目标和水平 (the start page from 我的): goals two across on phones, three on wide screens; 保存 reachable
    go(pg, '#/welcome/edit')
    cols = pg.evaluate("() => getComputedStyle(document.querySelector('.wg-goals')).gridTemplateColumns.split(' ').length")
    check(dev, 'welcome: goals in 2 columns on phones, 3 on wide screens', cols == (2 if opts['viewport']['width'] < 768 else 3), cols)
    nb = pg.evaluate("() => { const b = document.getElementById('wgGo'); b.scrollIntoView({ block: 'center' }); const r = b.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom), innerHeight]; }")
    check(dev, 'welcome: 保存 can be brought on screen above the tabs', nb[0] >= 0 and nb[1] <= nb[2], nb)

    # ---- account email, exam word lists, import topic
    go(pg, '#/me'); pg.wait_for_function("() => !document.querySelector('#acctEmail .spin')", timeout=5000)
    check(dev, 'me: email row says whether one is bound', len((pg.text_content('#acctEmail') or '').strip()) > 0, pg.text_content('#acctEmail'))
    # ---- account and security: change the password (the eye shows what was typed; a mismatch is said at once)
    check(dev, 'me: account card offers change password and sign out everywhere', pg.is_visible('#chPw') and pg.is_visible('#outAll'))
    me = pg.evaluate("() => ({groups: [...document.querySelectorAll('#view .gsec .ghead')].map(h => h.textContent), ability: !!document.querySelector('#view #ability'), out: !!document.querySelector('#view #out'), classic: /经典版|classic/.test(document.getElementById('view').innerHTML)})")
    check(dev, 'me: rows grouped as 进步, 设置, 账号, 帮助, then 退出登录; no ability card, no way to the classic site', me['groups'] == ['进步', '设置', '账号', '帮助'] and not me['ability'] and me['out'] and not me['classic'], me)
    pg.click('#meVoice'); pg.wait_for_selector('#sheet [data-voice]', timeout=4000)
    pg.click('#sheet [data-voice="uk-m"]'); pg.wait_for_timeout(300)
    check(dev, 'me: the voice row opens a sheet, and the row shows the new voice', '英音 · 男' in (pg.text_content('#meVoiceV') or ''), pg.text_content('#meVoiceV'))
    pg.click('#sheet [data-voice="us-f"]'); pg.wait_for_timeout(200); pg.evaluate("document.querySelector('#sheet [data-close]').click()"); pg.wait_for_timeout(300)
    pg.click('#chPw'); pg.wait_for_selector('#cp', timeout=4000)
    pg.click('#cp [data-eye] >> nth=0')
    check(dev, 'change password: the eye shows the password', pg.get_attribute('#cp [name=old]', 'type') == 'text')
    pg.fill('#cp [name=new]', 'a long new password'); pg.fill('#cp [name=again]', 'something else'); pg.click('#cp [type=submit]')
    check(dev, 'change password: a mismatch is marked on the field', pg.get_attribute('#cp [name=again]', 'aria-invalid') == 'true' and '不一样' in (pg.text_content('#cpErr') or ''))
    pg.evaluate("document.querySelector('#sheet [data-close]').click()")
    # ---- 问题反馈: from 我的, a few words and a screenshot (shrunk on the page before it is sent), then 已收到
    go(pg, '#/me'); pg.click('[data-tap="me-feedback"]'); pg.wait_for_selector('#fbForm', timeout=5000)
    pg.click('#fbForm [data-k="broken"]')
    pg.fill('#fbText', '单词页往下滑，底部按钮跑到了中间')
    pg.set_input_files('#fbFile', files=[{'name': 'shot.png', 'mimeType': 'image/png', 'buffer': png()}])
    pg.wait_for_selector('#fbShots img', timeout=5000)
    shot = pg.evaluate("document.querySelector('#fbShots img').src.slice(0, 23)")
    pg.click('#fbSend'); pg.wait_for_selector('.fb-done', timeout=8000)
    check(dev, '问题反馈: a screenshot goes as a shrunk JPEG with the words, and 已收到 counts it',
          shot == 'data:image/jpeg;base64,' and '1 张截图' in (pg.text_content('#view') or ''), shot)
    # ---- signed out: the sign-in sheet, a forgotten password, sign-up checks said before any request
    gctx = ctx.browser.new_context(**opts, locale='zh-CN', bypass_csp=True); gp = gctx.new_page()
    gp.goto(BASE + '/#/me'); settle(gp)
    gp.click('#lg'); gp.wait_for_selector('#authForm', timeout=4000)
    check(dev, 'sign-in: three ways in (password, code, sign-up)', gp.evaluate("() => document.querySelectorAll('#sheet [role=tab]').length") == 3)
    gp.click('[data-tab=reset]'); gp.wait_for_selector('#authForm [name=code]', timeout=4000)
    check(dev, 'sign-in: 忘记密码 opens email, code and new password', all(gp.is_visible(f'#authForm [name={n}]') for n in ('email', 'code', 'password')))
    gp.click('[data-tab=pw]'); gp.click('[data-tab=reg]'); gp.wait_for_selector('#authForm [name=username]', timeout=4000)
    gp.fill('#authForm [name=username]', 'a b'); gp.click('#authForm [type=submit]')
    check(dev, 'sign-up: a username with a space is refused on the field', gp.get_attribute('#authForm [name=username]', 'aria-invalid') == 'true')
    wide = gp.evaluate("() => document.getElementById('sheetCard').scrollWidth <= document.getElementById('sheetCard').clientWidth + 1")
    check(dev, 'sign-in sheet fits the width', wide)
    gctx.close()
    # ---- the word-book picker: books under group headings; 专四、专八、中考、学术 come from the data files
    # (tools/ui-fixtures/wordbooks*.json here), each with how it was made; picking one is plain to see
    go(pg, '#/vocab/plan')
    pick = pg.evaluate("""() => ({groups: [...document.querySelectorAll('#view .bookgroup > .kicker')].map(e => e.textContent.trim()),
      tem: [...document.querySelectorAll('#view .bookgroup')].filter(g => g.querySelector('.kicker').textContent.trim() === '英语专业')
        .flatMap(g => [...g.querySelectorAll('[data-book]')].map(b => b.dataset.book)),
      count: (document.querySelector('#view [data-book=tem4] .bk-n') || {}).textContent,
      basis: !!document.querySelector('#view [data-book=tem4] ~ details.basis > summary'),
      wide: [...document.querySelectorAll('#view .bookc, #view details.basis')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).length})""")
    check(dev, 'plan: books grouped 按词频 → 中学 → 大学 → 英语专业 → 出国 → 学术与职场, then 自己的词表',
          pick['groups'] == ['按词频', '中学英语', '大学英语', '英语专业', '出国留学', '学术与职场', '自己的词表'], pick['groups'])
    check(dev, 'plan: 专四 and 专八 from the data file, with a word count and a 怎么来的 note, inside the width',
          pick['tem'] == ['tem4', 'tem8'] and pick['count'] == '30 词' and pick['basis'] and not pick['wide'], pick)
    fold = pg.evaluate("() => ({hidden: document.getElementById('allBooks').hidden, now: document.getElementById('bookNow').textContent, imp: !!document.getElementById('impBook') && document.getElementById('impBook').offsetParent !== null})")
    check(dev, 'plan: the book list is folded; the chosen book is named on top, the word-list import stays in view', fold['hidden'] and '已选《' in fold['now'] and fold['imp'], fold)
    pg.click('#moreBooks')
    check(dev, 'plan: 换一本 opens every book', pg.is_visible('[data-book=tem4]') and pg.text_content('#moreBooks') == '收起')
    pg.click('[data-book=tem4]')
    sel = pg.evaluate("""() => ({pressed: [...document.querySelectorAll('#view [data-book][aria-pressed=true]')].map(b => b.dataset.book),
      tag: getComputedStyle(document.querySelector('#view [data-book=tem4] .bk-on')).display, now: document.getElementById('bookNow').textContent})""")
    check(dev, 'plan: choosing 专四 marks only that card 已选 and names it', sel['pressed'] == ['tem4'] and sel['tag'] != 'none' and '专四词汇' in sel['now'], sel)
    goal = lambda: pg.evaluate("""() => ({goal: [...document.querySelectorAll('#goal [aria-pressed=true]')].map(b => b.textContent.trim()),
      book: [...document.querySelectorAll('#view [data-book][aria-pressed=true]')].map(b => b.dataset.book), now: document.getElementById('bookNow').textContent})""")
    g = goal()
    check(dev, 'plan: 你在准备什么考试？ follows the chosen book (专四 lit after picking the 专四 card)', g['goal'] == ['专四'] and g['book'] == ['tem4'], g)
    pg.click('#goal [data-goal=tem8]'); g = goal()
    check(dev, 'plan: tapping the 专八 exam chip picks the 专八 book and says so', g['goal'] == ['专八'] and g['book'] == ['tem8'] and '专八词汇' in g['now'], g)
    pg.click('#goal [data-goal=""]'); g = goal()
    check(dev, 'plan: 不考试 goes back to the suggested book by frequency', g['goal'] == ['不考试'] and g['book'] == ['mid'], g)
    wide = pg.evaluate("() => [...document.querySelectorAll('#goal .chip')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).length")
    check(dev, 'plan: the exam chips wrap inside the screen', wide == 0, wide)
    pg.click('[data-book=tem4]')
    pg.click('[data-book=tem4] ~ details.basis > summary'); pg.wait_for_timeout(200)
    check(dev, 'plan: 这份词书怎么来的 opens the note', pg.is_visible('[data-book=tem4] ~ details.basis > p') and
          '不是官方词表' in (pg.text_content('[data-book=tem4] ~ details.basis > p') or ''))
    if dev == 'phone':
        pg.evaluate("document.querySelector('[data-book=tem4]').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / 'phone-vocab_plan-wordbooks.png'))
        pg.click('#savePlan'); pg.wait_for_function("() => location.hash === '#/cards'", timeout=5000); settle(pg)
        check(dev, 'plan: a 专四 plan is saved and the 单词 page shows it', '《专四词汇》' in (pg.text_content('#view .vtoday') or ''))
        go(pg, '#/vocab/plan')
    pg.click('#impBook'); pg.wait_for_selector('#impText', timeout=4000)
    check(dev, 'plan: the 导入老师给的词表 entry opens the word-list import', pg.is_visible('#impText'))
    pg.evaluate("document.querySelector('#sheet [data-close]').click()")
    go(pg, '#/import')
    check(dev, 'import: a topic can be chosen', pg.evaluate("() => document.querySelectorAll('#impF select[name=theme] option').length") >= 7)

    # ---- library: one row per material; filters are remembered after opening a material and coming back
    go(pg, '#/library')
    lib = pg.evaluate("() => { const rows = [...document.querySelectorAll('#lib .mrow')]; return [rows.length, Math.max(0, ...rows.map(r => Math.round(r.getBoundingClientRect().height)))]; }")
    check(dev, 'library: one short row per material', lib[0] >= 3 and lib[1] <= 80, lib)
    pg.select_option('#fl', 'B2'); pg.wait_for_timeout(500)
    pg.click('#lib a >> nth=0'); settle(pg)
    pg.go_back(); settle(pg)
    check(dev, 'library keeps its filter after going back', pg.input_value('#fl') == 'B2', pg.input_value('#fl'))

    check(dev, 'no script errors', not [e for e in errors if 'Failed to load resource' not in e], errors[:5])
    ctx.browser.close()


# ---- the phone in hand: how to put Flow on the home screen (iPhone, Android with and without the browser's own
# install offer), where a text comes from, and a 360-pixel-wide phone
IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
ANDROID_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
OFFER = """window.__prompted = 0; addEventListener('load', () => { const e = new Event('beforeinstallprompt');
  e.prompt = () => { window.__prompted++; }; e.userChoice = Promise.resolve({ outcome: 'accepted' }); dispatchEvent(e); });"""


def platform_run(pw):
    dev = 'platforms'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    token = CFG['learners']['phone']['token']

    def page(ua, width=390, init=None):
        ctx = browser.new_context(viewport={'width': width, 'height': 800}, is_mobile=True, has_touch=True, device_scale_factor=2, user_agent=ua, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': token, 'url': BASE}])
        if init:
            ctx.add_init_script(init)
        pg = ctx.new_page(); pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        return ctx, pg

    def install_text(pg):
        go(pg, '#/me'); pg.click('#meInstall'); pg.wait_for_selector('#sheetCard h2', timeout=4000); pg.wait_for_timeout(200)
        return pg.text_content('#sheetCard') or ''
    try:
        # iPhone (Safari): two steps from the share button; the source line under a title, and its sheet
        ctx, pg = page(IPHONE_UA)
        t = install_text(pg)
        check(dev, 'iPhone: share button at the bottom, then 添加到主屏幕', '底部中间' in t and '添加到主屏幕' in t and not pg.query_selector('#doInstall'), t[:120])
        pg.evaluate("document.querySelector('#sheet [data-close]').click()")
        go(pg, f'#/m/{PID}/read')
        o = pg.text_content('#view .origin') or ''
        mark = pg.text_content('#view .study-head .ai-line') or ''  # 「AI 生成」 under the title (人工智能生成合成内容标识办法)
        check(dev, 'a text says where it comes from and that AI wrote it', '来源：' in o and 'AI 生成' in mark and '经规范检查' in mark and '人工审核' not in mark, (o, mark))
        pg.click('#originMore'); pg.wait_for_selector('#sheetCard .origin-rules', timeout=4000)
        check(dev, 'the source line opens the writing rules', '在原文里找得到依据' in (pg.text_content('#sheetCard') or ''))
        pg.evaluate("document.querySelector('#sheet [data-close]').click()")
        # the 今日 notice, for a learner who has studied once: after the email notice is put off, 放到桌面 comes next
        pg.evaluate("""async pid => { const s = await (await fetch('/api/session')).json();
            await fetch('/api/next/progress', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': s.user.csrf }, body: JSON.stringify({ pack: pid, step: 'check' }) }); }""", PID)
        go(pg, '#/'); pg.wait_for_timeout(300)
        if pg.query_selector('#mnLater'):
            pg.click('#mnLater'); pg.wait_for_timeout(200)
        check(dev, '今日: after the email notice, one about the home screen', pg.query_selector('#installNudge') is not None and pg.query_selector('#notice > *:nth-child(2)') is None,
              pg.text_content('#notice')[:80] if pg.query_selector('#notice') else '')
        if pg.query_selector('#inGo'):
            pg.click('#inGo'); pg.wait_for_selector('#sheetCard .isteps', timeout=4000)
            check(dev, '今日: 怎么放 opens the same two steps', '添加到主屏幕' in (pg.text_content('#sheetCard') or ''))
        ctx.close()
        # Android without the browser's offer: the menu, two steps
        ctx, pg = page(ANDROID_UA)
        t = install_text(pg)
        check(dev, 'Android: the browser menu, then 添加到主屏幕 / 安装应用', '⋮' in t and '安装应用' in t, t[:120])
        ctx.close()
        # Android with the offer (beforeinstallprompt): one button, the browser's own install
        ctx, pg = page(ANDROID_UA, init=OFFER)
        install_text(pg)
        has = pg.query_selector('#doInstall') is not None
        if has:
            pg.click('#doInstall'); pg.wait_for_timeout(400)
        check(dev, "Android: one tap uses the browser's own install", has and pg.evaluate('window.__prompted') == 1)
        ctx.close()
        # a 360-pixel-wide phone: nothing wider than the screen on the pages changed here
        ctx, pg = page(ANDROID_UA, width=360)
        wide = {}
        for h in ('#/', f'#/m/{PID}/read', f'#/m/{PID}/listen', '#/me'):
            go(pg, h); pg.wait_for_timeout(300)
            wide[h] = pg.evaluate('document.scrollingElement.scrollWidth - innerWidth')
        check(dev, '360 px wide: no page scrolls sideways', all(v <= 0 for v in wide.values()), wide)
        ctx.close()
        # what the browser reports about the site: the opening time once the first page is drawn, and page errors
        # (a script error, a picture that did not load) when the page is left
        ctx = browser.new_context(viewport={'width': 390, 'height': 800}, is_mobile=True, has_touch=True, user_agent=IPHONE_UA, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': token, 'url': BASE}])
        pg = ctx.new_page(); sent = {}
        pg.on('request', lambda r: sent.setdefault(r.url.split('/api/next/')[-1], []).append(r.post_data) if r.url.endswith(('/api/next/issues', '/api/next/opentime')) else None)
        pg.goto(BASE + '/#/cards', wait_until='networkidle'); settle(pg); pg.wait_for_timeout(2200)
        ot = json.loads((sent.get('opentime') or ['{}'])[0])
        check(dev, 'the opening time is sent once the first page is drawn', len(sent.get('opentime', [])) == 1 and (ot.get('first_view') or 0) > 0 and ot.get('ttfb') is not None, ot)
        check(dev, 'the opening time says when the page asked, when the script ran, and which page it opened on',
              ot.get('startup') is not None and ot.get('boot') is not None and ot.get('hidden') is False and ot.get('page') == 'other', ot)  # opened on #/cards
        pg.evaluate("() => { setTimeout(() => { throw new Error('ui-test boom'); }, 0); const i = new Image(); i.src = '/no-such-picture.png'; document.body.appendChild(i); }")
        pg.wait_for_timeout(600); pg.evaluate("() => dispatchEvent(new Event('pagehide'))"); pg.wait_for_timeout(400)
        items = [x for body in sent.get('issues', []) for x in json.loads(body)['items']]
        check(dev, 'page errors are sent when the page is left: a script error and a picture that did not load',
              any(x['kind'] == 'js' and 'ui-test boom' in x['message'] for x in items) and any(x['kind'] == 'resource' and '/no-such-picture.png' in x['message'] for x in items), items[:4])
        ctx.close()
        # instant pages and preloading (05-data.js): the second visit draws 今日 from the copy kept on the phone while the
        # server is still answering; idle time preloads the other tabs; a touch on a link starts that page's request
        ctx = browser.new_context(viewport={'width': 390, 'height': 800}, is_mobile=True, has_touch=True, user_agent=IPHONE_UA, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['b1']['token'], 'url': BASE}])  # signed out at the end
        pg = ctx.new_page(); asked = []
        pg.on('request', lambda r: asked.append(r.url.split(BASE, 1)[-1]) if '/api/' in r.url else None)
        pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_timeout(1500)
        snap = pg.evaluate("() => JSON.parse(localStorage.getItem('flow-snap') || 'null')")
        check(dev, 'preload: 今日 is kept on the phone, without the session token', bool(snap and snap.get('home')) and 'csrf' not in json.dumps(snap), (snap or {}).keys())
        check(dev, 'preload: idle time fetched 单词 before it was opened', any(a.startswith('/api/next/vocab') for a in asked), [a for a in asked][:8])
        held = []
        pg.route('**/api/next/home*', lambda r: held.append(r))
        t0 = time.time(); pg.reload(wait_until='domcontentloaded')
        pg.wait_for_selector('#view .today-plan, #view .hello', timeout=4000); quick = time.time() - t0
        check(dev, 'preload: the second visit draws 今日 at once, while the server is still answering', quick < 2.5 and held, f'{quick:.2f}s, home held: {len(held)}')
        for r in held:
            r.continue_()
        pg.unroute('**/api/next/home*'); pg.wait_for_timeout(800)
        go(pg, '#/library'); pg.wait_for_timeout(300); asked.clear()
        links = pg.query_selector_all('#view a[href^="#/m/"]'); link = links[-1] if links else None
        if link:
            link.dispatch_event('pointerdown'); pg.wait_for_timeout(250)
        check(dev, 'preload: touching a material link starts its request before the tap ends', link is not None and any(a.startswith('/api/next/material?id=') for a in asked), asked[:5])
        go(pg, '#/me'); pg.click('#out'); pg.wait_for_timeout(800)
        left = pg.evaluate("() => localStorage.getItem('flow-snap') || ''")
        check(dev, 'preload: signing out clears the copy kept on the phone (a guest\'s 今日 may follow, nothing of the account)',
              '"owner":"u' not in left and 'username' not in left, left[:120])
        ctx.close()
    finally:
        browser.close()


# ---- WeChat's built-in browser: sound only when it starts inside a tap (or on a player an earlier tap unlocked), and
# no browser voice. Chrome allows more, so the page gets a play() that refuses the way WeChat's does. Its own server,
# with the narration timings and a word index from tools/ui-fixtures (no sound files: what is checked is that every
# play() is one WeChat would allow, and that the bar telling how to open the page in the browser is there).
WECHAT_UA = ('Mozilla/5.0 (Linux; Android 13; V2241A Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 '
             'Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160065 MMWEBSDK/20231202 MicroMessenger/8.0.47.2560(0x28002F30) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64')
IPHONE_WECHAT_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 '
                    'MicroMessenger/8.0.47(0x18002f2c) NetType/WIFI Language/zh_CN')
WECHAT_RULES = """(() => {
  let tap = false;
  const on = () => { tap = true; setTimeout(() => { tap = false; }, 0); };
  ['click', 'touchend', 'keydown'].forEach(t => window.addEventListener(t, on, true));
  window.__plays = [];
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    const ok = tap || !!this.__unlocked;
    window.__plays.push({ src: String(this.getAttribute('src') || '').slice(0, 90), tap, ok });
    if (!ok) return Promise.reject(new DOMException('play() can only be initiated by a user gesture.', 'NotAllowedError'));
    this.__unlocked = true;
    return play.call(this);
  };
  for (const o of [window, Window.prototype]) { try { delete o.speechSynthesis; delete o.SpeechSynthesisUtterance; } catch (e) {} }
})();"""


# iPhones and iPads: short sounds on Web Audio (01-audio-offline.js AUDIO). A stand-in AudioContext records what is
# started (offset, length, rate), the audio session type asked for, and the lock-screen handlers (navigator.mediaSession).
IOS_AUDIO_FAKE = """(() => {
  const W = window.__wa = { created: 0, resumed: 0, suspended: 0, closed: 0, starts: [], stops: 0, types: [], failDecode: false, refuse: false, ms: {} };
  class Src { constructor() { this.playbackRate = { value: 1 }; this.buffer = null; this.onended = null; }
    connect() {} start(when, off, dur) { W.starts.push({ when, off, dur, rate: this.playbackRate.value }); setTimeout(() => { if (this.onended) this.onended(); }, 250); }
    stop() { W.stops++; } }
  class Ctx { constructor() { W.created++; this.state = 'suspended'; this.currentTime = 0; this.destination = {}; this.onstatechange = null; }
    resume() { W.resumed++; this.state = 'running'; return Promise.resolve(); }
    suspend() { W.suspended++; this.state = 'suspended'; return Promise.resolve(); }
    close() { W.closed++; this.state = 'closed'; return Promise.resolve(); }
    createBufferSource() { return new Src(); }
    decodeAudioData(buf, ok, no) { if (W.failDecode) { const e = new Error('cannot decode'); if (no) no(e); return Promise.reject(e); } const b = { duration: 5 }; if (ok) ok(b); return Promise.resolve(b); } }
  window.AudioContext = Ctx; window.webkitAudioContext = Ctx;
  let type = 'auto';
  Object.defineProperty(navigator, 'audioSession', { configurable: true, value: { get type() { return type; }, set type(v) { W.types.push(v); if (!W.refuse) type = v; } } });
  if (navigator.mediaSession) { const set = navigator.mediaSession.setActionHandler.bind(navigator.mediaSession); navigator.mediaSession.setActionHandler = (k, f) => { W.ms[k] = f; try { set(k, f); } catch (e) {} }; }
})();"""


# 语流's iOS / Android app as the page sees it (docs/native-bridge.md §2–3): the apps' own native/flowapp.js behind a
# made-up transport that writes down every command and answers like the app (what it plays survives a reload, in
# localStorage); the test sends the app's news (FlowApp._emit) itself.
APP_AUDIO_FAKE = """(() => {
  const KEEP = 'ui-fake-app';
  const st = () => { try { return JSON.parse(localStorage.getItem(KEEP)) || {}; } catch (e) { return {}; } };
  const put = o => localStorage.setItem(KEEP, JSON.stringify(Object.assign(st(), o)));
  window.__cmds = []; window.__fakeApp = { st, put }; window.__said = [];
  if (window.speechSynthesis) { const s = speechSynthesis.speak.bind(speechSynthesis); speechSynthesis.speak = u => { if (u && u.text && u.text.trim()) window.__said.push(u.text); return s(u); }; }
  window.__flowAppTransport = {
    cfg: { v: 1, app: '1.0.0', build: 'ui', beta: true, platform: 'ios', features: ['audio'] },
    send(cmd, args) {
      window.__cmds.push([cmd, args]);
      const s = st();
      if (cmd === 'audio.play') {
        put({ playing: { key: args.key, state: 'playing', i: args.from || 0, n: (args.texts || args.sentences || []).length, title: args.title } });
        return Promise.resolve({ ok: true, state: 'playing' });
      }
      if (cmd === 'audio.state') return Promise.resolve(s.playing || { state: 'idle' });
      if (cmd === 'audio.progress') return Promise.resolve((s.progress || {})[args.key] || null);
      if (cmd === 'audio.resume') return Promise.resolve(Object.assign({ ok: true }, s.playing || {}));
      return Promise.resolve({ ok: true });
    },
  };
})();
""" + (Path(__file__).resolve().parents[1] / 'native' / 'flowapp.js').read_text()


def app_audio_run(pw):
    """In 语流's iOS / Android app (window.FlowApp has 'audio'), 听's 播放全文 and 读's 伴读 are played by the app: the page
    sends play / pause / set and follows the app's news: the button, the mini player, the lit sentence and where it got
    to (PROG). Loaded again while the app plays, the page takes the text back without starting it over; the app's newer
    place counts, its 读完 clears this phone's (docs/native-bridge.md §3; 语流 B3's review of PR #152)."""
    dev = 'app-audio'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        ctx = browser.new_context(**DEVICES['phone'], locale='zh-CN', bypass_csp=True, service_workers='block')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['app-audio']['token'], 'url': BASE}])
        ctx.add_init_script(APP_AUDIO_FAKE)
        pg = ctx.new_page(); errs = []; tts = []
        pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.on('request', lambda r: tts.append(r.url) if '/api/next/tts' in r.url else None)
        key = f'listen:{PID}'
        cmds = lambda: pg.evaluate('window.__cmds.map(c => c[0])')
        last = lambda name: pg.evaluate("n => { const c = window.__cmds.filter(x => x[0] === n); return c.length ? c[c.length - 1][1] : null; }", name)
        emit = lambda typ, d: pg.evaluate('([t, d]) => FlowApp._emit(t, d)', [typ, d])
        prog = lambda k=key: pg.evaluate("k => { const p = JSON.parse(localStorage.getItem('flow-progress') || '{}')[k]; return p ? p.i : null; }", k)
        btn = lambda sel='#playAll': (pg.text_content(sel) or '').strip()
        mini = lambda: pg.evaluate("(() => { const m = document.querySelector('.mini-player'); return m && !m.hidden ? m.querySelector('.lbl').textContent : null; })()")
        lit = lambda: pg.evaluate("(() => { const l = document.querySelector('.line.now'); return l ? l.dataset.i : null; })()")
        listen = lambda: (go(pg, f'#/m/{PID}/listen'), pg.wait_for_selector('#playAll'), pg.wait_for_timeout(400))

        pg.goto(BASE + '/', wait_until='load'); settle(pg)
        listen()
        n = pg.evaluate("document.querySelectorAll('.line[data-i]').length")
        pg.click('#playAll'); pg.wait_for_timeout(300)
        play = last('audio.play')
        check(dev, '播放全文: the app plays it (audio.play with the key, the sentences, 复读 and 语速)',
              bool(play) and play.get('key') == key and play.get('from') == 0 and bool(play.get('texts') or play.get('sentences'))
              and play.get('rate') == 1 and 'rep' in play and len(play.get('gap') or []) == n, play)
        check(dev, '播放全文: the page plays nothing itself (no server voice asked, no browser voice)', not tts and not pg.evaluate('window.__said.length'), tts[:3])
        emit('audio', {'key': key, 'state': 'playing', 'i': 2, 'n': n, 'title': 't'}); pg.wait_for_timeout(200)
        check(dev, "the app's news moves the page: 暂停 on the button, 第 3 句 on the mini player, that line lit, 第 3 句 kept",
              btn().endswith('暂停') and (mini() or '').startswith('第 3 /') and lit() == '2' and prog() == 2, (btn(), mini(), lit(), prog()))
        pg.evaluate("k => FlowApp._emit('audio-tick', { key: k, i: 3, t: 12.5, at: Date.now(), rate: 1 })", key); pg.wait_for_timeout(200)
        check(dev, 'a tick from the next sentence moves the page on too (第 4 句)', (mini() or '').startswith('第 4 /') and lit() == '3' and prog() == 3, (mini(), lit(), prog()))
        # the app reads a sentence in the phone's own voice (offline): the page says why, as everywhere on the site, once
        pg.evaluate(TOASTS_JS)
        emit('audio', {'key': key, 'state': 'playing', 'i': 3, 'n': n, 'title': 't', 'fail': {'code': 'offline', 'server': ''}}); pg.wait_for_timeout(200)
        line = (pg.text_content('#lsPrep') or '').strip() if pg.is_visible('#lsPrep') else ''
        emit('audio', {'key': key, 'state': 'playing', 'i': 3, 'n': n, 'title': 't', 'fail': {'code': 'offline', 'server': ''}}); pg.wait_for_timeout(200)
        said = [x for x in (pg.evaluate('window.__toasts') or []) if x.startswith('离线中')]
        check(dev, "the app fell back to the phone's voice (offline): the line under 播放全文 and one toast say why",
              line.startswith('离线中，这句还没存到本机') and len(said) == 1, (line, said))
        emit('audio', {'key': key, 'state': 'playing', 'i': 3, 'n': n, 'title': 't'}); pg.wait_for_timeout(200)
        check(dev, 'the next sentence in the AI voice again: the line goes', not pg.is_visible('#lsPrep') or not (pg.text_content('#lsPrep') or '').strip(), pg.text_content('#lsPrep'))
        pg.evaluate("document.querySelector('.playset').open = true")  # 语速 and 复读 sit in 播放设置
        pg.click('[data-rate="0.75"]'); pg.wait_for_timeout(200)
        s = last('audio.set')
        check(dev, '语速 0.75× while the app plays: it gets it at once (audio.set)', bool(s) and s.get('rate') == 0.75, s)
        pg.click('[data-rate="1"]'); pg.wait_for_timeout(100)
        pg.click('#playAll'); pg.wait_for_timeout(200)
        check(dev, '暂停 goes to the app, the button says 继续', 'audio.pause' in cmds()[-2:] and btn().endswith('继续'), (cmds()[-3:], btn()))
        pg.click('#playAll'); pg.wait_for_timeout(200)
        check(dev, '继续 goes to the app', 'audio.resume' in cmds()[-2:] and btn().endswith('暂停'), (cmds()[-3:], btn()))

        # loaded again while the app plays on (第 5 句): the page keeps that place and takes the text back, no new start
        pg.evaluate(f"k => window.__fakeApp.put({{ playing: {{ key: k, state: 'playing', i: 4, n: {n}, title: 't' }} }})", key)
        pg.reload(wait_until='load'); settle(pg); pg.wait_for_selector('#playAll'); pg.wait_for_timeout(500)
        check(dev, 'loaded again while the app plays: the mini player is back on 第 5 句, and so is the kept place',
              (mini() or '').startswith('t · 第 5 /') and prog() == 4 and btn().endswith('从第 5 句继续'), (mini(), prog(), btn()))
        emit('audio', {'key': key, 'state': 'playing', 'i': 5, 'n': n, 'title': 't'}); pg.wait_for_timeout(200)
        check(dev, '…and while the app reads on, the button follows it (从第 6 句继续)', btn().endswith('从第 6 句继续') and prog() == 5 and (mini() or '').startswith('t · 第 6 /'), (btn(), prog(), mini()))
        pg.click('#playAll'); pg.wait_for_timeout(300)
        after = cmds()
        check(dev, "…and 播放全文 takes the app's text back: no new audio.play, 复读 and 语速 sent, 暂停, 第 6 句 lit",
              'audio.play' not in after and 'audio.set' in after and btn().endswith('暂停') and lit() == '5', (after, btn(), lit()))
        emit('audio', {'key': key, 'state': 'idle', 'why': 'ended', 'i': n - 1, 'n': n}); pg.wait_for_timeout(200)
        check(dev, 'read to the end: the kept place cleared, the mini player gone, 播放全文 again',
              prog() is None and mini() is None and btn().endswith('播放全文'), (prog(), mini(), btn()))

        # the app played on while this page slept: its newer place counts; its 读完 clears this phone's
        k = max(1, n - 2)
        pg.evaluate("([key, k]) => { window.__fakeApp.put({ playing: null, progress: { [key]: { i: k, t: 30, at: Date.now() } } });"
                    " const o = JSON.parse(localStorage.getItem('flow-progress') || '{}'); o[key] = { i: 1, at: Date.now() - 60000 };"
                    " localStorage.setItem('flow-progress', JSON.stringify(o)); }", [key, k])
        pg.reload(wait_until='load'); settle(pg); pg.wait_for_selector('#playAll'); pg.wait_for_timeout(500)
        check(dev, f"the app's newer place counts: 从第 {k + 1} 句继续", btn().endswith(f'从第 {k + 1} 句继续') and prog() == k, (btn(), prog()))
        pg.evaluate("key => window.__fakeApp.put({ progress: { [key]: { i: 0, ended: true, at: Date.now() } } })", key)
        pg.reload(wait_until='load'); settle(pg); pg.wait_for_selector('#playAll'); pg.wait_for_timeout(500)
        check(dev, "the app read it to the end since: 播放全文 again", btn().endswith('播放全文') and prog() is None, (btn(), prog()))

        # 读's 伴读 goes to the app the same way
        go(pg, f'#/m/{PID}/read'); pg.wait_for_selector('#readAlong'); pg.wait_for_timeout(300)
        pg.click('#readAlong'); pg.wait_for_timeout(600)
        p = last('audio.play')
        check(dev, '伴读: the app plays it too', bool(p) and p.get('key') == f'read:{PID}' and btn('#readAlong').endswith('暂停'), (p and p.get('key'), btn('#readAlong')))
        check(dev, 'no server voice asked, no browser voice, no script errors', not tts and not pg.evaluate('window.__said.length') and not errs, (tts[:3], errs[:3]))
        ctx.close()
    finally:
        browser.close()


def ios_audio_run(pw):
    """iPhone (Safari / the home-screen app): a word, an example sentence and the learner's recording play on Web Audio
    from their first sound, under a 'playback' audio session (the ringer switch does not mute it) and named 「语流 · …」
    on the lock screen; where that cannot be (decoding fails, the type is refused, ?audio=element) the <audio> clip
    plays; a whole text keeps its <audio>, with the lock screen's controls and a page that follows a pause from outside."""
    dev = 'ios-audio'
    state = Path(tempfile.mkdtemp(prefix='flow-ui-ios-'))
    with socket.socket() as so:
        so.bind(('127.0.0.1', 0)); port = so.getsockname()[1]
    srv = subprocess.Popen([sys.executable, str(Path(__file__).with_name('ui_server.py')), str(port), str(state)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={**os.environ, 'FLOW_AUDIO_DIR': str(Path(__file__).with_name('ui-fixtures') / 'audio')})
    browser = None
    try:
        for _ in range(120):
            if (state / 'sessions.json').exists():
                break
            time.sleep(0.25)
        time.sleep(0.5)
        cfg = json.loads((state / 'sessions.json').read_text()); base, pid = cfg['base'], cfg['pid']
        word = json.loads((Path(__file__).with_name('ui-fixtures') / 'audio' / 'words' / 'index.json').read_text())['us']['drain']
        browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)

        sample = (Path(__file__).with_name('ui-fixtures') / 'tts-sample.mp3').read_bytes()

        def page(query='', refuse=False, undecodable=False, narration=False):
            ctx = browser.new_context(**DEVICES['phone'], user_agent=IPHONE_UA, locale='zh-CN', bypass_csp=True, service_workers='block')
            ctx.add_cookies([{'name': 'flow_session', 'value': cfg['learners']['phone']['token'], 'url': base}])
            ctx.add_init_script(IOS_AUDIO_FAKE + ('window.__wa.refuse = true;' if refuse else '') + ('window.__wa.failDecode = true;' if undecodable else ''))
            pg = ctx.new_page(); errs = []; asked = []
            pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
            pg.on('request', lambda r: asked.append(r.url.split(base, 1)[-1]) if '/audio/' in r.url else None)
            if narration:  # this server has the narration's timings, not its sound: a short mp3 stands in, before the page asks
                pg.route(f'**/audio/*/{pid}.mp4*', lambda r: r.fulfill(status=200, content_type='audio/mpeg', body=sample))
            pg.goto(base + '/' + query + '#/m/' + pid + '/read', wait_until='load'); settle(pg, '#reader'); pg.wait_for_timeout(500)
            return ctx, pg, errs, asked

        def tap_word(pg):
            pg.click('#reader .w:text-is("drains")'); pg.wait_for_selector('#sheetCard .word', timeout=5000); pg.wait_for_timeout(600)

        elements = "[...document.querySelectorAll('audio')].map(a => a.getAttribute('src') || '').filter(s => s.includes('/audio/words/'))"
        length = word[2] - word[1]
        clip_url = f"/audio/words/us/{word[0]}.aac?s={word[1]}&e={word[2]}&l=0.2"
        # 自动 (the default): Web Audio, from just before the word, under a 'playback' session, named on the lock screen
        ctx, pg, errs, asked = page()
        tap_word(pg)
        wa = pg.evaluate('window.__wa')
        st = wa['starts'][-1] if wa['starts'] else {}
        check(dev, 'by default a word plays on Web Audio from its clip: from just before the word for its length, at the reading speed',
              st and abs(st['off'] - 0.18) < 0.005 and abs(st['dur'] - (length + 0.06)) < 0.005 and st['rate'] == 1
              and any(clip_url in u for u in asked) and not pg.evaluate(elements), (st, asked[-3:]))
        check(dev, "the audio session is 'playback' (the ringer switch does not mute it), and the context was started inside the first tap",
              'playback' in wa['types'] and wa['created'] == 1 and wa['resumed'] >= 1, wa)
        title = pg.evaluate("navigator.mediaSession && navigator.mediaSession.metadata && navigator.mediaSession.metadata.title")
        check(dev, 'the lock screen and the Dynamic Island say 「语流 · 单词」, not an address', title == '语流 · 单词', title)
        pg.evaluate("Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true }); document.dispatchEvent(new Event('visibilitychange'))")
        wa = pg.evaluate('window.__wa')
        check(dev, 'leaving the page closes the context (iOS 26 home-screen apps went silent with an old one) and clears the lock screen',
              wa['closed'] == 1 and pg.evaluate("!(navigator.mediaSession && navigator.mediaSession.metadata)"), wa)
        pg.evaluate("Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true }); document.dispatchEvent(new Event('visibilitychange'))")
        # 我的 → 设置 → 单词读音方式: the switch the home-screen app can reach (no address bar there), kept on the phone
        pg.evaluate("document.querySelector('#sheet [data-close]').click()"); pg.wait_for_timeout(300)  # the word's card
        pg.evaluate("location.hash = '#/me'"); settle(pg); pg.wait_for_timeout(300)
        row = pg.text_content('#meSound') if pg.query_selector('#meSound') else ''
        pg.click('#meSound'); pg.wait_for_selector('#sheetCard [data-sound="compat"]', timeout=4000); pg.click('#sheetCard [data-sound="compat"]'); pg.wait_for_timeout(200)
        picked = pg.text_content('#meSoundV')
        pg.click('#sheetCard [data-lead="0.15"]'); pg.wait_for_timeout(200)
        leaded = pg.text_content('#meSoundV')
        pg.evaluate("document.querySelector('#sheet [data-close]').click()")
        pg.reload(wait_until='load'); settle(pg); pg.wait_for_timeout(300)
        kept = pg.text_content('#meSoundV') if pg.query_selector('#meSoundV') else ''
        check(dev, '我的 → 设置 has 单词读音方式 (连续 by default); 标准 and 0.15 s chosen there stay after the app is opened again',
              '单词读音方式' in row and '连续' in row and picked == '标准 · 前面 0.2 秒' and leaded == kept == '标准 · 前面 0.15 秒', (row, picked, leaded, kept))
        n = len(pg.evaluate('window.__wa.starts')); pg.evaluate("location.hash = '#/m/" + pid + "/read'"); settle(pg, '#reader'); pg.wait_for_timeout(400)
        asked.clear(); tap_word(pg)
        check(dev, '标准: the word plays its <audio> clip with the silence chosen (0.15 s), not Web Audio',
              any(clip_url.replace('l=0.2', 'l=0.15') in u for u in asked) and len(pg.evaluate('window.__wa.starts')) == n, asked[-3:])
        pg.wait_for_timeout(1500)
        check(dev, '标准: a clip that has ended lets its source go (WebKit then stops counting it for Now Playing)', not pg.evaluate(elements), pg.evaluate(elements))
        check(dev, 'no script errors (连续 and 标准)', not errs, errs[:3])
        ctx.close()
        # ?audio=element in Safari: the same 兼容模式; ?lead=: the silence in front (0.05–0.4 s)
        ctx, pg, errs, asked = page('?audio=element&lead=0.15')
        tap_word(pg)
        check(dev, '?audio=element is 标准, and ?lead=0.15 asks for a clip with 0.15 s of silence',
              not pg.evaluate('window.__wa.starts') and any(clip_url.replace('l=0.2', 'l=0.15') in u for u in asked), asked[-3:])
        pg.goto(base + '/?audio=auto&lead=auto#/m/' + pid + '/read', wait_until='load'); settle(pg, '#reader'); pg.wait_for_timeout(400)
        tap_word(pg)
        check(dev, '?audio=auto: Web Audio again', len(pg.evaluate('window.__wa.starts')) >= 1, pg.evaluate('window.__wa'))
        ctx.close()
        # decoding fails: the <audio> clip instead
        ctx, pg, errs, asked = page(undecodable=True)
        tap_word(pg)
        check(dev, 'a clip Web Audio cannot decode plays on an <audio> instead',
              not pg.evaluate('window.__wa.starts') and sum(clip_url in u for u in asked) >= 2, asked[-3:])  # fetched for Web Audio, then by the <audio>
        ctx.close()
        # neither the clip nor the sprite (audio-inventory.md, 语流 9): one line saying why, then the browser voice
        for off, line in ((False, '网络不好，这个词的读音没加载出来，先用浏览器的声音'), (True, '离线中，这个词的读音还没存到本机，先用浏览器的声音')):
            ctx, pg, errs, asked = page()
            pg.route('**/audio/words/**', lambda r: r.fulfill(status=404, content_type='application/json', body='{}'))
            pg.evaluate(TOASTS_JS)
            if off:
                pg.evaluate("Object.defineProperty(navigator, 'onLine', { get: () => false, configurable: true })")
            tap_word(pg); pg.wait_for_timeout(1500)
            said = pg.evaluate('window.__toasts') or []
            check(dev, f"no word sound at all{' (offline)' if off else ''}: it says why, then the browser voice reads it", line in said, said)
            ctx.close()
        # the type refused (a browser that does not let the page set it): <audio> clips, which the ringer switch does not mute
        ctx, pg, errs, asked = page(refuse=True)
        tap_word(pg)
        wa = pg.evaluate('window.__wa')
        check(dev, "where 'playback' is refused, words play their <audio> clip (no Web Audio, so the ringer switch cannot mute them)",
              not wa['starts'] and 'playback' in wa['types'] and any(clip_url in u for u in asked), (wa, asked[-3:]))
        ctx.close()
        # a whole text: <audio> (the lock screen controls it), named, and a pause from outside shows on the page
        ctx, pg, errs, asked = page(narration=True)
        pg.evaluate("location.hash = '#/m/" + pid + "/listen'"); settle(pg, '#playAll'); pg.wait_for_timeout(600)
        pg.click('#playAll')
        playing = "[...document.querySelectorAll('audio')].find(a => !a.paused && a.currentTime > 0)"  # the narration (its preloaded copy is a blob: URL)
        pg.wait_for_function(f"!!{playing}", timeout=8000)
        pg.evaluate(f"window.__nar = {playing}")
        ms = pg.evaluate("({ title: navigator.mediaSession.metadata && navigator.mediaSession.metadata.title, artist: navigator.mediaSession.metadata && navigator.mediaSession.metadata.artist, state: navigator.mediaSession.playbackState, acts: Object.keys(window.__wa.ms).filter(k => window.__wa.ms[k]) })")
        check(dev, 'a whole text: the lock screen shows 「语流 · 标题」 and 「AI 朗读」 with play, pause, previous and next sentence',
              (ms['title'] or '').startswith('语流 · ') and 'AI 朗读' in (ms['artist'] or '') and ms['state'] == 'playing' and {'play', 'pause', 'previoustrack', 'nexttrack'} <= set(ms['acts']), ms)
        nar = "window.__nar"
        pg.evaluate(f"{nar}.pause()"); pg.wait_for_timeout(300)  # what a call does
        mini = pg.evaluate("({ label: document.querySelector('.mini-player .lbl').textContent, resume: !!document.querySelector('.mini-player .resume'), state: navigator.mediaSession.playbackState })")
        check(dev, 'paused by a call: the page says 已暂停 with 继续 (not still playing), and so does the lock screen',
              mini['label'] == '已暂停' and mini['resume'] and mini['state'] == 'paused', mini)
        pg.click('.mini-player .resume'); pg.wait_for_timeout(400)
        mini = pg.evaluate(f"({{ resume: !!document.querySelector('.mini-player .resume'), playing: !{nar}.paused, state: navigator.mediaSession.playbackState }})")
        check(dev, '继续 plays on from where it was', mini['playing'] and not mini['resume'] and mini['state'] == 'playing', mini)
        t0 = pg.evaluate(f"{nar}.currentTime"); pg.evaluate('window.__wa.ms.nexttrack()'); pg.wait_for_timeout(200)
        check(dev, "the lock screen's next goes to the next sentence", pg.evaluate(f"{nar}.currentTime") > t0, (t0, pg.evaluate(f"{nar}.currentTime")))
        pg.evaluate("(m => m && !m.hidden && m.querySelector('.stop').click())(document.querySelector('.mini-player'))"); pg.wait_for_timeout(300)  # or the short sample ended
        check(dev, '停止 (or the end) clears the lock screen', pg.evaluate("!navigator.mediaSession.metadata && navigator.mediaSession.playbackState === 'none'"), pg.evaluate("navigator.mediaSession.playbackState"))
        check(dev, 'no script errors (a whole text)', not errs, errs[:3])
        ctx.close()
    finally:
        if browser:
            browser.close()
        srv.terminate()

# every toast as it is set (two in a row replace each other on screen); window.__toasts
TOASTS_JS = """() => { const el = document.getElementById('toast'), d = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent'); window.__toasts = [];
  Object.defineProperty(el, 'textContent', { configurable: true, get() { return d.get.call(this); }, set(v) { window.__toasts.push(v); d.set.call(this, v); } }); }"""


def wechat_run(pw):
    dev = 'wechat'
    state = Path(tempfile.mkdtemp(prefix='flow-ui-wx-'))
    with socket.socket() as so:
        so.bind(('127.0.0.1', 0)); port = so.getsockname()[1]
    srv = subprocess.Popen([sys.executable, str(Path(__file__).with_name('ui_server.py')), str(port), str(state)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={**os.environ, 'FLOW_AUDIO_DIR': str(Path(__file__).with_name('ui-fixtures') / 'audio')})
    try:
        for _ in range(120):
            if (state / 'sessions.json').exists():
                break
            time.sleep(0.25)
        time.sleep(0.5)
        cfg = json.loads((state / 'sessions.json').read_text()); base, pid = cfg['base'], cfg['pid']
        browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
        ctx = browser.new_context(**DEVICES['phone'], user_agent=WECHAT_UA, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': cfg['learners']['phone']['token'], 'url': base}])
        ctx.add_init_script(WECHAT_RULES)
        pg = ctx.new_page(); errors = []
        pg.on('pageerror', lambda e: errors.append(page_error(pg, e)))
        pg.goto(base + '/#/', wait_until='networkidle'); settle(pg)
        guide = pg.text_content('.wx-guide') if pg.query_selector('.wx-guide') else ''
        check(dev, 'the first visit points at the ··· menu: two steps, and a way to copy the address', '「···」' in guide and '在浏览器打开' in guide and pg.is_visible('#wxCopy'), guide[:80])
        pg.click('#wxStay'); pg.wait_for_timeout(150)
        bar = pg.text_content('.wx-bar') if pg.query_selector('.wx-bar') else ''
        check(dev, 'a slim bar says how to open the page in the browser', '在浏览器打开' in bar and pg.is_visible('.wx-bar .wx-x'), bar[:80])
        pg.click('.wx-bar .wx-x'); pg.reload(); settle(pg)
        check(dev, 'the bar, once closed, stays away', pg.query_selector('.wx-bar') is None)
        plays = lambda: pg.evaluate('window.__plays')
        # listen: the first tap unlocks both players; 播放全文 starts the narration inside the tap
        pg.evaluate("location.hash = '#/m/" + pid + "/listen'"); settle(pg, '#playAll'); pg.wait_for_timeout(400)
        pg.click('#playAll'); pg.wait_for_timeout(300)
        nar = [x for x in plays() if pid in x['src']]
        check(dev, '播放全文 starts the recording inside the tap', nar and nar[-1]['ok'] and nar[-1]['tap'], plays()[-3:])
        if pg.is_visible('.mini-player .stop'):
            pg.click('.mini-player .stop')
        # read: 伴读 starts inside the tap, because the timings were fetched when the page opened
        pg.evaluate("location.hash = '#/m/" + pid + "/read'"); settle(pg, '#reader'); pg.wait_for_timeout(500)
        n0 = len(plays()); pg.click('#readAlong'); pg.wait_for_timeout(300)
        new = plays()[n0:]
        check(dev, '伴读 starts the recording inside the tap', new and new[0]['ok'] and new[0]['tap'], new)
        pg.click('#readAlong'); pg.wait_for_timeout(200)
        # a word: its recorded pronunciation, started after the look-up arrives, on the player the first tap unlocked
        n0 = len(plays()); pg.click('#reader .w:text-is("drains")'); pg.wait_for_selector('#sheetCard .word', timeout=5000); pg.wait_for_timeout(400)
        new = [x for x in plays()[n0:] if '/audio/words/' in x['src']]
        check(dev, 'a looked-up word plays its recording (no browser voice here)', new and all(x['ok'] for x in new), plays()[n0:])
        pg.evaluate("document.querySelector('#sheet [data-close]').click()"); pg.wait_for_timeout(200)
        # review: a card says its word when it appears (after the queue arrives) and again on the speaker button
        n0 = len(plays()); pg.evaluate("location.hash = '#/review'"); settle(pg); pg.wait_for_timeout(800)
        if pg.query_selector('#sayW'):
            pg.click('#sayW'); pg.wait_for_timeout(400)
        new = [x for x in plays()[n0:] if '/audio/words/' in x['src']]
        check(dev, 'a review card says its word, by itself and on the speaker button', new and all(x['ok'] for x in new), plays()[n0:])
        # 雅思口语 Part 1: WeChat has no browser voice, so the examiner's question is on screen, with no "cannot play" notice
        pg.evaluate("location.hash = '#/speak/ielts/p1-mornings'"); settle(pg, '#ieStart'); pg.wait_for_timeout(2600)  # an earlier notice has gone
        n0 = len(plays())
        pg.evaluate("document.getElementById('toast').classList.remove('show')"); pg.click('#ieStart'); pg.wait_for_timeout(1500)
        note = pg.evaluate("(document.querySelector('.toast.show') || {}).textContent || ''")
        check(dev, '雅思口语 Part 1 starts: the question on screen, no notice about sound', pg.is_visible('#chat .msg.ai') and not note, note)
        # the server voice (tts_service): WeChat has no browser voice, so the examiner is heard through a stored mp3
        said = [x for x in plays()[n0:] if '/audio/tts/' in x['src']]
        check(dev, 'the examiner is heard in WeChat: the server voice, on the player the first tap unlocked', said and all(x['ok'] for x in said), plays()[n0:])
        check(dev, 'every sound started was one WeChat allows', all(x['ok'] for x in plays()), [x for x in plays() if not x['ok']][:3])
        check(dev, 'Android: words play from their sprite, as before (no clip)', all('.aac' not in x['src'] for x in plays() if '/audio/words/' in x['src']),
              [x['src'] for x in plays() if '/audio/words/' in x['src']][:3])
        check(dev, 'no script errors', not errors, errors[:3])
        # iPhone (Safari, the app on the home screen, WeChat): a word is its own small clip with 0.3 s of silence in front,
        # played from its start (word_clip.py: an iPhone waking its audio lost the start of a word played inside its sprite)
        ictx = browser.new_context(**DEVICES['phone'], user_agent=IPHONE_WECHAT_UA, locale='zh-CN', bypass_csp=True, service_workers='block')
        ictx.add_cookies([{'name': 'flow_session', 'value': cfg['learners']['phone']['token'], 'url': base}])
        ictx.add_init_script(WECHAT_RULES)
        ip = ictx.new_page(); ierrors = []
        ip.on('pageerror', lambda e: ierrors.append(page_error(ip, e)))
        iplays = lambda: ip.evaluate('window.__plays')
        word = lambda: (ip.click('#reader .w:text-is("drains")'), ip.wait_for_selector('#sheetCard .word', timeout=5000), ip.wait_for_timeout(700))
        ip.goto(base + '/#/m/' + pid + '/read', wait_until='load'); settle(ip, '#reader'); ip.wait_for_timeout(600)
        away = lambda: [ip.click(sel) for sel in ('#wxStay', '.wx-bar .wx-x') if ip.query_selector(sel) and ip.is_visible(sel)]  # WeChat's first-visit guide
        away(); ip.wait_for_timeout(200)
        word()
        new = [x for x in iplays() if '/audio/words/' in x['src']]
        check(dev, 'iPhone: a looked-up word plays its own clip (.aac, from its start), as WeChat allows',
              new and all(x['ok'] and '.aac?s=' in x['src'] for x in new), new)
        clip = next(x['src'] for x in new if '.aac?s=' in x['src']) if new else ''
        # it plays to its end, then lets its source go (no Now Playing for it after that)
        ip.wait_for_function("![...document.querySelectorAll('audio')].some(x => (x.getAttribute('src') || '').includes('.aac'))", timeout=5000)
        info = ip.evaluate("""async u => { const r = await fetch(u); const b = await r.arrayBuffer();
          const buf = await new OfflineAudioContext(1, 1, 44100).decodeAudioData(b);
          return { type: r.headers.get('content-type'), dur: buf.duration, ended: true }; }""", clip)
        idx = json.loads((Path(__file__).with_name('ui-fixtures') / 'audio' / 'words' / 'index.json').read_text())['us']['drain']
        want = 0.2 + (idx[2] - idx[1])  # silence, then the word (its quiet tail trimmed, to the end of a frame)
        check(dev, 'iPhone: the clip is audio/aac with 0.2 s of silence and the whole word, and it plays to its end',
              info and info['type'].startswith('audio/aac') and want - 0.12 <= info['dur'] <= want + 0.15 and info['ended'], (info, want))
        # no clip from the server (an older server, an error): the word plays from its sprite, as before
        ip.route('**/*.aac*', lambda r: r.fulfill(status=404, content_type='application/json', body='{}'))
        ip.reload(wait_until='load'); settle(ip, '#reader'); ip.wait_for_timeout(600); away()
        n0 = len(iplays()); word()
        new = [x for x in iplays()[n0:] if '/audio/words/' in x['src']]
        check(dev, 'iPhone: without a clip, the sprite plays instead', any('.aac' not in x['src'] and x['ok'] for x in new), new)
        # neither the clip nor the sprite, and WeChat has no browser voice either: how to hear it, nothing about a voice
        ip.route('**/audio/words/**', lambda r: r.fulfill(status=404, content_type='application/json', body='{}'))
        ip.reload(wait_until='load'); settle(ip, '#reader'); ip.wait_for_timeout(600); away(); ip.evaluate(TOASTS_JS)
        word(); ip.wait_for_timeout(800)
        said = ip.evaluate('window.__toasts') or []
        check(dev, 'iPhone WeChat: no word sound and no browser voice: it says how to hear it, not 「先用浏览器的声音」',
              any('在浏览器打开' in t for t in said) and not any('先用浏览器的声音' in t for t in said), said)
        check(dev, 'iPhone: no script errors', not ierrors, ierrors[:3])
        ictx.close()
        browser.close()
    finally:
        srv.terminate()


# ---- layout on every page and in the states learners reach (a test's result, an open fold, each kind of review card),
# on a phone and a small phone, dark and light, in Chrome and (when installed) WebKit, the engine of iPhone Safari.
# Each check is a kind of fault found on phones, looked for everywhere at once:
#   wide      the page is wider than the screen, so it slides sideways (and iOS lets it zoom out, carrying the bars);
#   beyond    something reaches past the screen's edge (cut off, or pushing the page wider);
#   squeezed  text squeezed into a column about one character wide (two layouts fighting over one class name);
#   fixed-in  a fixed bar inside a box that moves or transforms (it is carried along instead of staying put);
#   tabs      after scrolling a long page to the end, the tab bar is still at the bottom of the screen;
#   q-top     a review question without a word to show starts near the top, not under a screen of empty space.
AUDIT_JS = r"""() => {
  const W = innerWidth, H = innerHeight, out = { wide: document.scrollingElement.scrollWidth - W, beyond: [], squeezed: [], fixedIn: [] };
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.classList.length ? '.' + [...el.classList].slice(0, 3).join('.') : '');
  // a scroller or a clipping box of its own (not the page's main column) holds what reaches past it on purpose
  const held = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    if (p.tagName === 'MAIN') continue; const ox = getComputedStyle(p).overflowX; if (ox !== 'visible') return true; } return false; };
  const flagged = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.skip, .sr-only, [hidden], #sheet[hidden]')) continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const straddles = (r.left < -1 && r.right > 0) || (r.right > W + 1 && r.left < W);
    if (straddles && cs.position !== 'fixed' && !held(el) && !flagged.some(f => f.contains(el))) { flagged.push(el); out.beyond.push(name(el) + ' ' + Math.round(r.left) + '…' + Math.round(r.right)); }
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
    if (own.length >= 2) { const fs = parseFloat(cs.fontSize) || 16, lh = parseFloat(cs.lineHeight) || fs * 1.5;
      if (r.width < fs * 1.6 && r.height > lh * 2.5) out.squeezed.push(name(el) + ' "' + own.slice(0, 12) + '"'); }
    if (cs.position === 'fixed') for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ps = getComputedStyle(p), bf = ps.backdropFilter || ps.webkitBackdropFilter || 'none';
      if (ps.position === 'sticky' || ps.transform !== 'none' || ps.filter !== 'none' || bf !== 'none' || ps.perspective !== 'none' || /paint|layout|strict|content/.test(ps.contain || '') || /transform|filter/.test(ps.willChange || '')) {
        out.fixedIn.push(name(el) + ' inside ' + name(p)); break; } }
  }
  return out;
}"""
TABS_JS = """() => { const t = document.querySelector('.tabs'); if (!t) return null; const cs = getComputedStyle(t);
  if (cs.position !== 'fixed' || cs.display === 'none') return null; return Math.round(innerHeight - t.getBoundingClientRect().bottom); }"""
QTOP_JS = """() => { const r = document.querySelector('#view .review'); if (!r || !r.querySelector('.qopts, #fixIn') || r.querySelector('.wordbig')) return null;
  const f = r.querySelector('.rtag') || r.firstElementChild; return f ? Math.round(f.getBoundingClientRect().top / innerHeight * 100) : null; }"""


def layout_run(pw, engine):
    dev = 'layout-' + engine
    try:
        browser = pw.webkit.launch() if engine == 'webkit' else pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    except Exception as e:
        if engine == 'webkit' and 'webkit' not in ONLY:  # not installed here (CI): the Chrome run still covers the rest
            print(f'SKIP [{dev}] WebKit is not installed (python -m playwright install webkit)'); return
        raise
    found = {}  # (size, theme, kind) -> [where: what]

    def note(where, size, theme, res):
        for kind in ('beyond', 'squeezed', 'fixedIn'):
            for x in res[kind][:4]:
                found.setdefault((size, theme, kind), []).append(f'{where}: {x}')
        if res['wide'] > 1:
            found.setdefault((size, theme, 'wide'), []).append(f"{where}: +{res['wide']} px")
    try:
        for (w, h), theme in ((390, 844), 'dark'), ((360, 780), 'light'), ((390, 844), 'light'), ((360, 780), 'dark'):
            size = f'{w}'
            opts = dict(viewport={'width': w, 'height': h}, has_touch=True, device_scale_factor=2, color_scheme=theme, locale='zh-CN', bypass_csp=True)
            if engine != 'webkit':
                opts['is_mobile'] = True
            ctx = browser.new_context(**opts)
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['phone']['token'], 'url': BASE}])
            pg = ctx.new_page(); pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
            audit = lambda where: note(where, size, theme, pg.evaluate(AUDIT_JS))
            for p in PAGES:
                go(pg, p); audit(p)
            # the states behind a tap: the statistics fold on 单词, the end of the vocabulary test, the placement result
            go(pg, '#/cards'); pg.evaluate("() => { const d = document.getElementById('vStats'); if (d) d.open = true; }"); pg.wait_for_timeout(250); audit('#/cards (统计 open)')
            go(pg, '#/vocab/test')
            for _ in range(240):
                if not pg.query_selector('[data-a="1"]'):
                    break
                pg.click('[data-a="1"]')
            pg.wait_for_selector('#view .done-card', timeout=8000); pg.wait_for_timeout(300); audit('#/vocab/test (result)')
            go(pg, '#/placement')
            if pg.query_selector('#pStart'):
                pg.click('#pStart'); pg.wait_for_timeout(300)
            placed = lambda: pg.evaluate("() => [...document.querySelectorAll('#view .place .kicker')].some(k => k.textContent.includes('小测结果'))")
            for _ in range(60):  # 「不会」 to every question: the test ends early, at the result
                if placed():
                    break
                s = pg.query_selector('#pSkip:not([disabled])')
                if s:
                    s.click()
                pg.wait_for_timeout(350)
            if placed():
                audit('#/placement (result)')
            else:
                found.setdefault((size, theme, 'beyond'), []).append('#/placement: the result was not reached, so not checked')
            # review: each card as it comes, answered so the next one shows; questions start near the top
            go(pg, '#/review'); pg.wait_for_timeout(300); asked = 0
            for k in range(40):  # word cards come first; mistakes (questions) after them
                if not pg.query_selector('#view .review') or asked:
                    break  # a question is checked and left unanswered, so it is still due for the next run
                audit(f'#/review card {k + 1}')
                top = pg.evaluate(QTOP_JS)
                asked += top is not None
                if top is not None and top > 40:
                    found.setdefault((size, theme, 'q-top'), []).append(f'#/review card {k + 1}: question starts {top}% down the screen')
                if top is not None:
                    continue
                b = pg.query_selector('.qopt:not([disabled])') or pg.query_selector('#fixNo') or pg.query_selector('#giveup') or pg.query_selector('.choice button[data-claim="forgot"]') or pg.query_selector('.choice button[data-self]')
                if not b:
                    break
                b.click(); pg.wait_for_timeout(250)
                for sel in ('#view #go', '#view [data-rate="again"]', '#view [data-rate]'):  # the answer side: 下一个, or a rating
                    nb = pg.query_selector(sel)
                    if nb and nb.is_visible():
                        nb.click(); pg.wait_for_timeout(250); break
            if not asked:
                found.setdefault((size, theme, 'q-top'), []).append('#/review: no question card came up, so none was checked')
            # the tab bar stays at the bottom of the screen when a long page is scrolled to its end
            for p in ('#/library', '#/cards', '#/guide'):
                go(pg, p); pg.evaluate('window.scrollTo(0, document.scrollingElement.scrollHeight)'); pg.wait_for_timeout(500)
                gap = pg.evaluate(TABS_JS)
                if gap is not None and abs(gap) > 2:
                    found.setdefault((size, theme, 'tabs'), []).append(f'{p}: tab bar {gap} px above the bottom')
                pg.evaluate('window.scrollTo(0, 0)')
            ctx.close()
        for kind, label in (('wide', 'no page is wider than the screen'), ('beyond', 'nothing reaches past the edge of the screen'),
                            ('squeezed', 'no text squeezed into a narrow column'), ('fixedIn', 'fixed bars are not carried by a moving box'),
                            ('tabs', 'the tab bar stays at the bottom of long pages'), ('q-top', 'review questions start near the top')):
            bad = {f'{s}px {t}': v for (s, t, k), v in found.items() if k == kind}
            check(dev, label, not bad, json.dumps(bad, ensure_ascii=False)[:380])
    finally:
        browser.close()


# ---- the experience round: 复读 in 听, 撤销 in review, 字号和行距, and a first visit that can start with an article
FAKE_TTS = """(() => { window.__said = []; if (!window.speechSynthesis) return;
  speechSynthesis.speak = u => { window.__said.push(u.text); setTimeout(() => { u.onstart && u.onstart(); u.onend && u.onend(); }, 40); };
  speechSynthesis.cancel = () => {}; speechSynthesis.getVoices = () => []; })();"""


def ux_run(pw):
    dev = 'ux'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    phone = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True)
    try:
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a2']['token'], 'url': BASE}])
        ctx.add_init_script(FAKE_TTS)
        pg = ctx.new_page(); pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        # the server out of order with no message of ours (nginx's 502 page while it restarts): plain words, no status code
        pg.route('**/api/next/report*', lambda r: r.fulfill(status=502, content_type='text/html', body='<html><body><h1>502 Bad Gateway</h1>nginx</body></html>'))
        go(pg, '#/report'); pg.wait_for_selector('#view .empty', timeout=5000)
        said = pg.text_content('#view .empty') or ''
        check(dev, 'a server error without a message of ours reads 「服务暂时有点忙，请稍后重试」, no status code', '服务暂时有点忙' in said and '502' not in said and '请求失败' not in said, said[:80])
        pg.unroute('**/api/next/report*')
        # 复读: 3 遍, no pause: one tap on a sentence says it three times. The server voice is off on this page (the server's
        # own answer when it is), so the browser voice, faked to end at once, says it and the three times can be counted
        pg.route('**/api/next/tts', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
        go(pg, f'#/m/{PID}/listen'); pg.wait_for_selector('#view .playset', timeout=5000)
        pg.evaluate("document.querySelector('#view .playset').open = true"); pg.wait_for_timeout(100)  # 播放设置: remembered open after the reload below
        pg.click('[data-rep="3"]'); pg.evaluate('window.__said = []')
        pg.click('[data-say="0"]'); pg.wait_for_timeout(30)
        mini = pg.is_visible('.mini-player')  # while it repeats (it goes away when the last time ends)
        pg.wait_for_timeout(900)
        said = pg.evaluate('window.__said')
        check(dev, '复读: a sentence is said three times, with a stop button on screen meanwhile', len(said) == 3 and len(set(said)) == 1 and mini, (len(said), mini))
        pg.unroute('**/api/next/tts')
        # 复读 on the path learners hear: the server voice. A 0.3 s silent WAV for the sentence (its own page with the service
        # worker held off, so the test answers the file), each play() of it counted: three, and the stop button meanwhile
        import io, wave
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0' * 4800)
        short = buf.getvalue()
        c2 = browser.new_context(**phone, service_workers='block')
        c2.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a2']['token'], 'url': BASE}])
        c2.add_init_script(FAKE_TTS)
        c2.add_init_script("""(() => { window.__plays = []; const p = HTMLMediaElement.prototype.play;
            HTMLMediaElement.prototype.play = function () { window.__plays.push(this.getAttribute('src') || ''); return p.apply(this, arguments); }; })()""")
        p2 = c2.new_page()
        p2.route('**/api/next/tts', lambda r: r.fulfill(json={'url': '/audio/tts/us-f/ux-short-0001.wav', 'made': False}))
        p2.route('**/audio/tts/us-f/ux-short-0001.wav', lambda r: r.fulfill(status=200, content_type='audio/wav', body=short))
        p2.goto(BASE + f'/#/m/{PID}/listen', wait_until='networkidle'); settle(p2, '#view .playset')
        p2.evaluate("document.querySelector('#view .playset').open = true"); p2.wait_for_timeout(100)
        p2.click('[data-rep="3"]'); p2.evaluate('window.__plays = []; window.__said = []')
        p2.click('[data-say="0"]'); p2.wait_for_timeout(60)
        mini2 = p2.is_visible('.mini-player')
        p2.wait_for_function("window.__plays.filter(s => s.includes('ux-short')).length >= 3", timeout=8000)
        p2.wait_for_timeout(900)  # a fourth would have started by now
        got = p2.evaluate("({ plays: window.__plays.filter(s => s.includes('ux-short')).length, said: window.__said.length, mini: !!document.querySelector('.mini-player:not([hidden])') })")
        check(dev, '复读 in the server voice: the sentence is played three times (each time it ends, the next), not the browser voice, a stop button meanwhile',
              got['plays'] == 3 and got['said'] == 0 and mini2 and not got['mini'], {**got, 'mini_while': mini2})
        c2.close()
        # the browser voice as iOS sometimes treats it (语流 07, iPhone 17e and iPad simulators): an utterance spoken right
        # after cancel() ends at once without starting, or never starts. 播放全文 with the server voice off: dropped once,
        # the sentence is said again and the text goes on; dropped every time, or never started, the text waits paused at
        # that sentence with why, instead of racing to its end (marked heard) or sitting there "playing". The blank
        # utterance the first tap speaks to unlock the voice is left out
        drops = {
            'once': "let n = 0; speechSynthesis.speak = u => { if (!u.text.trim()) return; window.__said.push(u.text); const k = n++; setTimeout(() => { if (k > 0 && u.onstart) u.onstart(); u.onend && u.onend(); }, 30); };",
            'always': "speechSynthesis.speak = u => { if (!u.text.trim()) return; window.__said.push(u.text); setTimeout(() => { u.onend && u.onend(); }, 30); };",
            'never': "speechSynthesis.speak = u => { if (!u.text.trim()) return; window.__said.push(u.text); };",
            'throws': "speechSynthesis.speak = u => { if (!u.text.trim()) return; window.__said.push(u.text); throw new Error('refused'); };",
            'no-end': "speechSynthesis.speak = u => { if (!u.text.trim()) return; window.__said.push(u.text); setTimeout(() => { u.onstart && u.onstart(); }, 30); };",
        }
        seen = {}
        for kind, js in drops.items():
            c3 = browser.new_context(**phone)
            c3.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a2']['token'], 'url': BASE}])
            c3.add_init_script("(() => { window.__said = []; if (!window.speechSynthesis) return; speechSynthesis.cancel = () => {}; speechSynthesis.getVoices = () => []; " + js + " })()")
            p3 = c3.new_page()
            p3.route('**/api/next/tts', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
            p3.route('**/api/next/tts/have', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
            p3.goto(BASE + f'/#/m/{PID}/listen', wait_until='networkidle'); settle(p3, '#playAll')
            p3.evaluate("localStorage.removeItem('flow-progress')")
            p3.click('#playAll'); p3.wait_for_timeout(3400 if kind == 'never' else 1500)
            seen[kind] = p3.evaluate("""() => ({ said: window.__said.slice(), n: document.querySelectorAll('#view .line').length,
                btn: document.querySelector('#playAll').textContent.trim(), now: (document.querySelector('#view .line.now') || {dataset: {}}).dataset.i,
                note: (document.querySelector('#lsPrep') || {}).textContent || '', mini: (document.querySelector('.mini-player:not([hidden]) .lbl') || {}).textContent || '' })""")
            c3.close()
        # 「留时间跟说」 in 播放全文: the pause after a sentence is as long as that sentence (to say it back), not the next one.
        # A two-word sentence before a long one: the next starts after the 1.5 s minimum, not the ~11 s the long one gets
        c4 = browser.new_context(**phone)
        c4.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a2']['token'], 'url': BASE}])
        c4.add_init_script("(() => { window.__said = []; localStorage.setItem('flow-next-loop', JSON.stringify({rep: 1, gap: -1})); if (!window.speechSynthesis) return; "
                           "speechSynthesis.cancel = () => {}; speechSynthesis.getVoices = () => []; speechSynthesis.speak = u => { if (!u.text.trim()) return; "
                           "window.__said.push([u.text, performance.now()]); setTimeout(() => { u.onstart && u.onstart(); u.onend && u.onend(); }, 30); }; })()")
        p4 = c4.new_page()
        p4.route('**/api/next/tts', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
        p4.route('**/api/next/tts/have', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
        p4.goto(BASE + '/', wait_until='networkidle'); settle(p4)
        body = ('Stop here. The old harbour town grew slowly around a single stone pier that fishermen had built by hand more than '
                'two hundred years ago, long before the railway came. Today the pier is quiet in the mornings, and visitors walk along '
                'it slowly to watch the small boats come back with their catch.')
        art = p4.evaluate("([t, csrf]) => fetch('/api/next/import', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, "
                          "body: JSON.stringify({title: '停顿', text: t})}).then(r => r.json())", [body, CFG['learners']['a2']['csrf']])
        p4.goto(BASE + f"/#/m/{art['id']}/listen", wait_until='networkidle'); settle(p4, '#playAll')
        p4.click('#playAll'); p4.wait_for_timeout(3200)
        said = p4.evaluate('window.__said')
        gap0 = round(said[1][1] - said[0][1]) if len(said) >= 2 else None
        check(dev, '留时间跟说: the pause after a sentence is as long as that sentence (2 words: the 1.5 s minimum), not the next one',
              said and said[0][0] == 'Stop here.' and gap0 is not None and 1400 <= gap0 <= 2600, {'said': len(said), 'gap_after_first_ms': gap0})
        c4.close()
        # opened straight at an article (the page drawn from the 今日 kept on the phone), 播放全文 tapped at once, the
        # server's fresher 今日 arriving a moment later: the page is not redrawn under the reading (it was, and the reading
        # was gone as if read to its end: 语流 07, iPhone 17e)
        c5 = browser.new_context(**phone)
        c5.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a2']['token'], 'url': BASE}])
        c5.add_init_script("(() => { window.__said = []; if (!window.speechSynthesis) return; speechSynthesis.cancel = () => {}; speechSynthesis.getVoices = () => []; "
                           "speechSynthesis.speak = u => { if (!u.text.trim()) return; window.__said.push(u.text); setTimeout(() => u.onstart && u.onstart(), 10); "
                           "setTimeout(() => u.onend && u.onend(), 800); }; })()")
        p5 = c5.new_page()
        p5.route('**/api/next/tts', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
        p5.route('**/api/next/tts/have', lambda r: r.fulfill(status=503, json={'error': '服务器朗读没有开启', 'code': 'off'}))
        # the server's 今日 a moment after the page is drawn from the copy, and not the same (a page-level delay: a blocking
        # route would stall Playwright); only on the second load, so the copy kept by the first stays the server's own
        c5.add_init_script("""(() => { if (sessionStorage.getItem('lateHome') !== '1') return; const f = window.fetch.bind(window);
            window.fetch = (u, o) => !String(u).includes('/api/next/home') ? f(u, o) : new Promise(ok => setTimeout(ok, 3500)).then(() => f(u, o)).then(async res => {
              const j = await res.clone().json().catch(() => null); if (!j || !j.stats) return res;
              j.stats.due = (j.stats.due || 0) + 7; return new Response(JSON.stringify(j), { status: res.status, headers: res.headers }); }); })()""")
        p5.goto(BASE + '/', wait_until='networkidle'); settle(p5); p5.wait_for_timeout(300)  # the 今日 copy kept on the phone
        p5.evaluate("sessionStorage.setItem('lateHome', '1')")
        p5.goto(BASE + f'/?again=1#/m/{PID}/listen', wait_until='domcontentloaded'); p5.wait_for_selector('#playAll', timeout=8000)  # a real load (a new query): the page starts again from the copy
        p5.click('#playAll'); p5.wait_for_timeout(4500)
        kept = p5.evaluate("""() => ({ btn: document.querySelector('#playAll').textContent.trim(), mini: !!document.querySelector('.mini-player:not([hidden])'),
            said: window.__said.length, now: (document.querySelector('#view .line.now') || {dataset: {}}).dataset.i })""")
        check(dev, '播放全文 right after opening an article: the fresher 今日 coming in does not stop the reading',
              kept['btn'] == '暂停' and kept['mini'] and kept['said'] >= 2, kept)
        c5.close()
        o, al, nv, th, ne = seen['once'], seen['always'], seen['never'], seen['throws'], seen['no-end']
        check(dev, 'browser voice dropped once (iOS): that sentence is said again and the text reads on to its end',
              len(o['said']) == o['n'] + 1 and o['said'][0] == o['said'][1] and o['btn'] == '播放全文', {k: o[k] for k in ('n', 'btn', 'now')} | {'said': len(o['said'])})
        check(dev, 'browser voice dropped every time: tried twice, then the text waits paused at that sentence and says why (not "read")',
              len(al['said']) == 2 and al['btn'] == '继续' and al['now'] == '0' and '没有读出' in al['note'] and al['mini'] == '已暂停', al)
        check(dev, 'browser voice never starting: after 2.5 s the text waits paused at that sentence and says why',
              len(nv['said']) == 1 and nv['btn'] == '继续' and nv['now'] == '0' and '没有读出' in nv['note'], nv)
        check(dev, 'browser voice refusing outright (speak throws): tried twice, then the text waits paused there and says why',
              len(th['said']) == 2 and th['btn'] == '继续' and th['now'] == '0' and '没有读出' in th['note'], th)
        # started, then no end and no error, the voice quiet (an iPad simulator, offline: 语流 B5's [flowdbg] log): the
        # sentence counts as said once the voice has been quiet a moment, and the text reads on instead of sticking
        check(dev, 'browser voice starting a sentence but never saying it ended: the text reads on (not stuck "playing")',
              len(ne['said']) >= 2 and ne['said'][0] != ne['said'][1] and '没有读出' not in ne['note'], {k: ne[k] for k in ('btn', 'now', 'note')} | {'said': len(ne['said'])})
        pg.reload(); settle(pg, '[data-rep]')
        check(dev, '复读: the choice is remembered', pg.get_attribute('[data-rep="3"]', 'aria-pressed') == 'true')
        pg.click('[data-rep="1"]')
        # 字号: 特大 makes the reading text larger, and a 360-pixel phone still does not scroll sideways
        go(pg, '#/me'); pg.click('#meText'); pg.wait_for_selector('#sheetCard [data-ts="xl"]', timeout=4000)
        pg.click('#sheetCard [data-ts="xl"]'); pg.click('#sheetCard [data-tl="w"]'); pg.evaluate("document.querySelector('#sheet [data-close]').click()")
        pg.set_viewport_size({'width': 360, 'height': 780}); go(pg, f'#/m/{PID}/read'); pg.wait_for_timeout(400)
        z = pg.evaluate("() => { const t = document.querySelector('#view .text'); return t ? [getComputedStyle(t).zoom, getComputedStyle(t).lineHeight] : null; }")
        wide = pg.evaluate('document.scrollingElement.scrollWidth - innerWidth')
        check(dev, '字号: 特大 and 宽松 apply to the reading text, and the page stays within the screen', z and float(z[0]) == 1.25 and wide <= 0, (z, wide))
        pg.set_viewport_size({'width': 390, 'height': 844}); go(pg, '#/me'); pg.click('#meText'); pg.wait_for_selector('#sheetCard [data-ts="m"]', timeout=4000)
        pg.click('#sheetCard [data-ts="m"]'); pg.click('#sheetCard [data-tl="n"]'); pg.evaluate("document.querySelector('#sheet [data-close]').click()")
        # 撤销: a rating taken back brings the same card up again
        go(pg, '#/review'); pg.wait_for_timeout(400)
        first = pg.text_content('#view .review') or ''
        b = pg.query_selector('.choice button[data-claim="forgot"]')
        if b:
            b.click(); pg.wait_for_timeout(300)
            r = pg.query_selector('#view [data-rate="again"]') or pg.query_selector('#view [data-rate]')
            if r:
                r.click(); pg.wait_for_timeout(500)
        has = pg.query_selector('#undo') is not None
        if has:
            pg.click('#undo'); pg.wait_for_timeout(600)
        again = pg.text_content('#view .review') or ''
        check(dev, '撤销: the latest rating is taken back and the same card comes up again', has and again[:40] == first[:40], (has, first[:40], again[:40]))
        ctx.close()
        # a first visit: the one start page (goal, level to reach), then 今日; a shared material still opens without it
        ctx = browser.new_context(**phone); pg = ctx.new_page()
        pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg)
        start = pg.evaluate('location.hash')
        pg.click('[data-goal="daily"]'); pg.click('#wgGo'); pg.wait_for_function("() => location.hash === '#/'", timeout=6000); settle(pg)
        today = pg.query_selector('#view .hello') is not None
        pg.goto(BASE + f'/#/m/{PID}/read'); settle(pg)
        check(dev, 'first visit: the start page, then 今日 for the level chosen; a link to a material opens it directly', start == '#/welcome' and today and pg.query_selector('#view .steps') is not None,
              (start, today))
        ctx.close()
        # 语法混合 and 辨析练习 while answering (43-mix.js, body.reviewing): no tabs, the question and its four answers on one
        # screen in the home-screen app, 375×667 and 390×844 (UI audit 2026-11-25: 17–133 px past it on the smallest iPhone)
        for (w, h, t, b) in ((375, 667, 20, 0), (390, 844, 47, 34)):
            ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True)
            ctx.add_init_script(HOME_INIT % json.dumps([t, b, 0]))
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a2']['token'], 'url': BASE}])
            pg = ctx.new_page(); pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
            for page in ('#/mix', '#/mix/pair/tense-past,tense-perfect'):
                go(pg, page); pg.wait_for_selector('#mixQ .ans', timeout=8000); pg.wait_for_timeout(500)
                got = pg.evaluate("[document.scrollingElement.scrollHeight - innerHeight, getComputedStyle(document.querySelector('.tabs')).display]")
                check(dev, f'{w}×{h} home-screen app {page}: no tabs while answering, the question and its answers on one screen', got[0] <= 1 and got[1] == 'none', got)
            go(pg, '#/practice')
            check(dev, f'{w}×{h}: the tabs come back on the next page', pg.evaluate("getComputedStyle(document.querySelector('.tabs')).display") != 'none')
            ctx.close()
    finally:
        browser.close()


# ---- the learner round (r22): 每周目标, 存到手机 (study without a connection), 分享卡片, 导出我的数据 and 注销账号
QR_READ = """async sel => { if (!('BarcodeDetector' in window)) return null;
  const f = await new BarcodeDetector({ formats: ['qr_code'] }).detect(document.querySelector(sel)); return f.map(x => x.rawValue); }"""


def learner_run(pw):
    dev = 'learner'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    phone = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True, accept_downloads=True)
    closing = "document.querySelector('#sheet [data-close]').click()"
    try:
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['exam']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        # 每周目标: from the 这周进步 card on 今日 (r27: it replaced the chip), 改每周目标 opens its sheet, and the goal
        # chosen there shows on the card at once
        pg.click('#weekCard'); pg.wait_for_selector('#wkGoal', timeout=6000); pg.click('#wkGoal')
        pg.wait_for_selector('#sheetCard [data-goal="3"]', timeout=4000)
        pg.click('#sheetCard [data-goal="3"]'); pg.wait_for_timeout(600); pg.evaluate(closing)
        goal = (pg.text_content('#weekCard .wk-tile.goal b') or '').strip()
        chip = (pg.text_content('#habitBtn') or '').strip()
        check(dev, '每周目标: the goal set from 今日 shows on the 这周进步 card and the chip by the greeting at once', goal.endswith('/3天') and '/3 天' in chip, (goal[:40], chip[:40]))
        # 草稿 (08-drafts.js): a writing box keeps what was typed when the page is left, its counter too; sending forgets it
        draft = 'A paragraph pasted here, and then the learner tapped another tab by mistake. ' * 4
        go(pg, '#/import'); pg.fill('#impF textarea[name=text]', draft); go(pg, '#/practice'); go(pg, '#/import')
        kept, count = pg.input_value('#impF textarea[name=text]'), (pg.text_content('#impN') or '').strip()
        note = (pg.text_content('#impF .draft-note') or '').strip() if pg.locator('#impF .draft-note').count() else ''
        go(pg, '#/feedback'); pg.fill('#fbText', 'The word page shows the wrong count.'); go(pg, '#/practice'); go(pg, '#/feedback')
        fb = pg.input_value('#fbText'); pg.click('#fbSend'); pg.wait_for_selector('.fb-done', timeout=6000)
        go(pg, '#/practice'); go(pg, '#/feedback'); after = pg.input_value('#fbText')
        check(dev, '草稿: 我的文章 and 问题反馈 keep what was typed after leaving the page (with the counter and 「已恢复…清空」); sent feedback starts empty',
              kept == draft and count == f'{len(draft)} 字符' and note.startswith('已恢复上次没写完的内容') and fb == 'The word page shows the wrong count.' and after == '',
              (len(kept), count, note, fb[:24], after[:24]))
        # 分享卡片: after the questions, a learned expression becomes a picture with a QR code back to the site
        go(pg, f'#/m/{PID}/check'); pg.wait_for_selector('#pane .q', timeout=6000)
        for q in pg.query_selector_all('#pane .q'):
            q.query_selector('.ans').click(); pg.wait_for_timeout(250)
        pg.wait_for_selector('#shareX', timeout=6000); pg.click('#shareX')
        pg.wait_for_selector('#shareImg[src^="data:image/png"]', timeout=6000); pg.wait_for_timeout(300)
        size = pg.evaluate("[document.getElementById('shareImg').naturalWidth, document.getElementById('shareImg').naturalHeight]")
        read = pg.evaluate(QR_READ, '#shareImg')
        fits = pg.evaluate("() => { const r = document.querySelector('#sheetCard [data-close]').getBoundingClientRect(); return r.bottom <= innerHeight; }")
        check(dev, '分享卡片: a 1080×1440 picture, its QR code leads back to the site, and the sheet\'s buttons are on screen',
              size == [1080, 1440] and read in (None, ['https://flowlang.cn/?f=card']) and fits, (size, read if read is not None else 'no BarcodeDetector here (Linux): read on macOS', fits))
        pg.screenshot(path=str(OUT / 'learner-share.png')); pg.evaluate(closing)
        # 存到手机: a material kept on the phone opens and is graded without a connection; the answer is sent once online
        lib = pg.evaluate("fetch('/api/next/library?level=&theme=&page=1&featured=').then(r => r.json())")
        other = next((m['id'] for m in lib.get('items', []) if m['id'] != PID), None)
        if other:
            go(pg, f'#/m/{other}/read'); pg.wait_for_selector('#keepOff', timeout=6000)
            if pg.get_attribute('#keepOff', 'class').find(' on') < 0:
                pg.click('#keepOff')
            pg.wait_for_selector('.offk.on', timeout=8000); go(pg, '#/')
            ctx.set_offline(True); pg.wait_for_timeout(300)
            go(pg, f'#/m/{other}/check')
            shown = pg.query_selector('#pane .q .ans') is not None
            if shown:
                pg.click('#pane .q .ans'); pg.wait_for_timeout(400)
            graded = pg.query_selector('#pane .q .ans.right') is not None
            waiting = pg.evaluate("JSON.parse(localStorage.getItem('flow-next-outbox') || '[]').filter(x => x.path === '/api/next/check').length")
            ctx.set_offline(False); pg.wait_for_timeout(1500)
            sent = pg.evaluate("JSON.parse(localStorage.getItem('flow-next-outbox') || '[]').length")
            check(dev, '存到手机: a kept material opens and is graded offline, and the answer is sent once back online',
                  shown and graded and waiting >= 1 and sent == 0, (shown, graded, waiting, sent))
        else:
            check(dev, '存到手机: a second material to keep', False, 'no other material in the library')
        # 复听: from 今日, the text hidden at first; the answer to 听懂了多少 shows it and says whether it comes back
        go(pg, f'#/m/{PID}/listen/again'); pg.wait_for_selector('#relisten [data-und]', timeout=6000)
        hidden = pg.evaluate("document.querySelectorAll('#pane .line .txt.blind').length")
        pg.wait_for_timeout(300); pg.screenshot(path=str(OUT / 'learner-relisten.png'))
        pg.click('#relisten [data-und="2"]'); pg.wait_for_function("() => !document.querySelector('#relisten [data-und]')", timeout=6000)
        said = (pg.text_content('#relisten') or '').strip()
        shown = pg.evaluate("document.querySelectorAll('#pane .line .txt.blind').length")
        check(dev, '复听: the text is hidden until 听懂了多少 is answered, then shown; understood mostly, it is not brought back again (r27)', hidden > 0 and shown == 0 and '这篇已经听熟了，以后不再安排复听' in said, (hidden, shown, said[:60]))
        # 导出我的数据: the word book as a table for Excel (UTF-8 with a BOM), from 我的
        go(pg, '#/me'); pg.click('#meData'); pg.wait_for_selector('#sheetCard a[href$="cards.csv"]', timeout=4000)
        with pg.expect_download(timeout=8000) as dl:
            pg.click('#sheetCard a[href$="cards.csv"]')
        f = dl.value; body = Path(f.path()).read_bytes()
        check(dev, '导出: the word book downloads as 语流单词本-<day>.csv, readable by Excel', f.suggested_filename.startswith('语流单词本-') and body.startswith('\ufeff英文,中文意思'.encode()),
              (f.suggested_filename, body[:30]))
        pg.evaluate(closing)
        check(dev, 'no script errors on these pages', not errs, errs[:3])
        ctx.close()
        # 注销账号: a wrong password is refused; the right one deletes the account, and this phone forgets it
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['leaver']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.goto(BASE + '/#/me', wait_until='networkidle'); settle(pg)
        pg.click('#meDelete'); pg.wait_for_selector('#sheetCard #da', timeout=4000); pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / 'learner-delete.png'))
        pg.fill('#da input[name=password]', 'not the password'); pg.click('#da [type=submit]'); pg.wait_for_timeout(700)
        refused = (pg.text_content('#daErr') or '').strip()
        pg.fill('#da input[name=password]', CFG['learners']['leaver']['password']); pg.click('#da [type=submit]')
        pg.wait_for_function("() => ['#/', '#/welcome'].includes(location.hash) && document.getElementById('sheet').hidden", timeout=8000); settle(pg)
        who = pg.evaluate("fetch('/api/session').then(r => r.json()).then(j => j.user || null)")
        # (a guest's own copy of 今日 may be there again: the page after the deletion is a guest's)
        kept = pg.evaluate("""['flow-snap', 'flow-offline', 'flow-next-outbox', 'flow-next-review-cache'].filter(k => {
          const v = JSON.parse(localStorage.getItem(k) || 'null'); return v && !(k === 'flow-snap' && v.owner === 'guest'); })""")
        check(dev, '注销账号: a wrong password is refused, the right one deletes the account and signs out, and this phone keeps none of it',
              '密码不正确' in refused and who is None and not kept, (refused, who, kept))
        ctx.close()
    finally:
        browser.close()


# ---- screen readers and colour: every page, light and dark. A control without a name, an image without alt text, a
# field without a label, an id used twice, text below WCAG AA contrast (4.5:1; 3:1 for large text; disabled controls
# exempt), English not marked lang="en" (a screen reader would read it with a Chinese voice), and right/wrong answers
# told apart by colour alone. Pictures of the answered questions as a red-green colour-blind learner sees them are
# saved for a look (a11y-deuteranopia.png, a11y-protanopia.png).
A11Y_JS = """() => {
  // entrance animations and fades played to their end: what is measured is what stays on screen
  document.getAnimations().forEach(a => { try { if (isFinite(a.effect.getComputedTiming().endTime)) a.finish(); } catch (e) { /* not finishable */ } });
  const out = { unnamed: [], noalt: [], unlabeled: [], contrast: [], lang: [], dupid: [] };
  const visible = el => { if (!el.getClientRects().length) return false; const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const hidden = el => !!el.closest('[aria-hidden="true"], [hidden], .sr-only') && !el.closest('.sr-only');
  const sig = el => (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '') + ' ' + (el.outerHTML || '').slice(0, 90)).replace(/\s+/g, ' ');
  const nameOf = el => {
    const al = el.getAttribute('aria-label'); if (al && al.trim()) return al.trim();
    const lb = el.getAttribute('aria-labelledby'); if (lb) { const t = lb.split(/\s+/).map(id => (document.getElementById(id) || {}).textContent || '').join(' ').trim(); if (t) return t; }
    if (el.labels && el.labels.length) { const t = [...el.labels].map(l => l.textContent).join(' ').trim(); if (t) return t; }
    if (!/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) { const t = (el.innerText || el.textContent || '').trim(); if (t) return t; }
    const img = el.querySelector && el.querySelector('img[alt]'); if (img && img.alt.trim()) return img.alt.trim();
    if (el.title && el.title.trim()) return el.title.trim();
    return '';
  };
  const ids = {};
  document.querySelectorAll('[id]').forEach(e => { ids[e.id] = (ids[e.id] || 0) + 1; });
  out.dupid = Object.keys(ids).filter(k => ids[k] > 1);
  document.querySelectorAll('button, a[href], [role=button], [role=radio], [role=tab], [role=checkbox], [role=switch], summary').forEach(el => {
    if (!visible(el) || hidden(el)) return;
    if (!nameOf(el)) out.unnamed.push(sig(el));
  });
  document.querySelectorAll('img').forEach(el => { if (!el.hasAttribute('alt') && !hidden(el) && el.getAttribute('role') !== 'presentation') out.noalt.push(sig(el)); });
  document.querySelectorAll('input, select, textarea').forEach(el => {
    if (el.type === 'hidden' || !visible(el) || hidden(el)) return;
    if (!nameOf(el)) out.unlabeled.push(sig(el) + (el.placeholder ? ' [placeholder only]' : ''));
  });
  // contrast (WCAG 2): 4.5 for text, 3 for large text (24px, or 18.66px bold); disabled controls are exempt
  const parse = s => { const m = s && s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const over = (top, bottom) => { const a = top[3]; return [0, 1, 2].map(i => top[i] * a + bottom[i] * (1 - a)).concat(1); };
  // The colour behind a text: the backgrounds up to the first solid one (the current study step's comes from its sliding
  // indicator, a separate layer), and the opacity of what lies between (the layer with the background fading with
  // its text changes nothing between them).
  const bgOf = el => {
    const layers = []; let e = el, op = 1;
    while (e && e.nodeType === 1) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && !/gradient/.test(cs.backgroundImage)) return null;  // a picture behind: skip
      let c = parse(cs.backgroundColor);
      if (/gradient/.test(cs.backgroundImage)) { const m = cs.backgroundImage.match(/rgba?\([^)]+\)/); if (m) c = parse(m[0]); }
      if ((!c || !c[3]) && e.matches('.steps [aria-selected="true"]')) { const ind = document.querySelector('.steps .ind'); c = ind && parse(getComputedStyle(ind).backgroundColor); }
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
      op *= Number(cs.opacity); e = e.parentElement;
    }
    let bg = [255, 255, 255, 1]; for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg);
    return { bg, op };
  };
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = n.nodeValue.trim(); if (!t || t.length < 1) continue;
    const el = n.parentElement; if (!el || seen.has(el)) continue; seen.add(el);
    if (!visible(el) || hidden(el) || el.closest('[disabled], [aria-disabled="true"], .sheet[hidden], svg, canvas, option')) continue;
    const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
    const cs = getComputedStyle(el); const fg = parse(cs.color); const b = bgOf(el); if (!fg || !b) continue;
    const { bg, op } = b; if (op < 0.05) continue;
    const eff = over([fg[0], fg[1], fg[2], fg[3] * op], bg);
    const size = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700, large = size >= 24 || (bold && size >= 18.66);
    const need = large ? 3 : 4.5, got = ratio(eff, bg);
    if (got < need - 0.05) out.contrast.push({ text: t.slice(0, 40), ratio: Math.round(got * 100) / 100, need, size, fg: cs.color, bg: 'rgb(' + bg.slice(0, 3).map(Math.round).join(',') + ')', sel: sig(el).slice(0, 80) });
  }
  // English that a screen reader would read with a Chinese voice: blocks of English words not inside lang="en"
  const seenL = new Set();
  const w2 = document.createTreeWalker(document.getElementById('view') || document.body, NodeFilter.SHOW_TEXT);
  while ((n = w2.nextNode())) {
    const t = n.nodeValue.trim(); const el = n.parentElement;
    if (!el || seenL.has(el) || !visible(el) || hidden(el)) continue;
    const words = t.match(/[A-Za-z][A-Za-z'’-]+/g) || [];
    if (words.length < 3 || /[㐀-鿿]/.test(t)) continue;
    seenL.add(el);
    if (/[\u3400-\u9fff]/.test(el.textContent)) continue;  // a block mixing both stays Chinese (screen readers switch for Latin letters)
    const l = (el.closest('[lang]') || {}).lang || '';
    if (!/^en/i.test(l)) out.lang.push(t.slice(0, 50) + '  <' + sig(el).slice(0, 60) + '>');
  }
  return out;
}"""

# ---- r27 听和说: the 跟读 pronunciation score and 雅思口语 Part 1 / Part 2, on phone (390 and 360), phone sideways, tablet
# and desktop, with Chrome's fake microphone (a tone) so recording, the timers and the AI round trip really run.
LS_SIZES = {'phone': ('phone', DEVICES['phone']), 'phone-360': ('phone-360', dict(viewport={'width': 360, 'height': 780}, is_mobile=True, has_touch=True, device_scale_factor=2)),
            'phone-land': ('phone-land', DEVICES['phone-land']), 'tablet': ('tablet', DEVICES['tablet']), 'desktop': ('desktop', DEVICES['desktop'])}


def listen_speak_run(pw):
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv,
                                 args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
    try:
        for size, (learner, opts) in LS_SIZES.items():
            dev = 'ls-' + size
            ctx = browser.new_context(**opts, locale='zh-CN', bypass_csp=True)
            ctx.grant_permissions(['microphone'], origin=BASE)
            # every microphone stream the page opens, to check each one is let go when its recording ends (an iPhone
            # plays everything through the earpiece while one is open); the one-time 「要用一下麦克风」 sheet: on the phone
            ctx.add_init_script("""(() => { const md = navigator.mediaDevices; if (!md || !md.getUserMedia) return; window.__mics = [];
                const g = md.getUserMedia.bind(md); md.getUserMedia = c => g(c).then(s => { window.__mics.push(s); return s; }); })()""")
            ctx.add_init_script("""(() => { window.__speaks = []; if (!window.speechSynthesis) return; const s = speechSynthesis.speak.bind(speechSynthesis);
                speechSynthesis.speak = u => { if (u && u.text && u.text.trim()) window.__speaks.push(u.text); return s(u); }; })()""")
            # Chrome has no navigator.audioSession (iOS 16.4+): a stand-in that remembers what the page set it to
            ctx.add_init_script("""(() => { if (navigator.audioSession) return; let t = 'auto';
                Object.defineProperty(navigator, 'audioSession', { configurable: true, value: { get type() { return t; }, set type(v) { t = v; } } }); })()""")
            if size != 'phone':
                ctx.add_init_script("try { localStorage.setItem('flow-mic-explained', '1'); } catch (e) {}")
            mic_free = "window.__mics.length > 0 && window.__mics.every(s => s.getTracks().every(t => t.readyState === 'ended'))"
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners'][learner]['token'], 'url': BASE}])
            pg = ctx.new_page(); errors = []
            pg.on('pageerror', lambda e: errors.append(str(e)))
            touch = opts['has_touch']
            lay = lambda what: (lambda l: (check(dev, f'{what}: no sideways scroll', l['overflow'] <= 1, f"{l['overflow']}px {l['wide']}"),
                                           check(dev, f'{what}: no squeezed text', not l['squeezed'], l['squeezed'])))(pg.evaluate(LAYOUT_JS, touch))
            shot = lambda name: pg.screenshot(path=str(OUT / f'{dev}-{name}.png'), full_page=False)
            pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)

            # 跟读: record the first sentence, AI 点评 -> 发音分 with 准确 / 流利 / 完整 and the sound to practise
            go(pg, f'#/m/{PID}/listen'); pg.click('[data-mode="shadow"]'); pg.wait_for_selector('.line.sh.cur [data-r="0"]')
            pg.click('[data-r="0"]')
            if size == 'phone':  # the first time on a device: why the microphone is asked for, then a fresh tap records
                pg.wait_for_selector('#micGo', timeout=3000)
                sh = pg.text_content('#sheetCard') or ''
                check(dev, '麦克风: the first time, a sheet says when it is open and that iPhones ask again', '只在你点' in sh and 'iOS 的规定' in sh, sh[:90])
                pg.click('#micGo')
            pg.wait_for_selector('[data-r="0"].on', timeout=5000); pg.wait_for_timeout(1200)
            during = pg.evaluate('navigator.audioSession.type'); pg.click('[data-r="0"]')
            pg.wait_for_selector('[data-ai="0"]:not([disabled])', timeout=5000)
            check(dev, '跟读: the microphone is let go when the recording ends', pg.evaluate(mic_free), pg.evaluate('window.__mics.length'))
            after = pg.evaluate('navigator.audioSession.type')
            check(dev, '跟读: iPhone audio session is play-and-record while recording, playback after', (during, after) == ('play-and-record', 'playback'), (during, after))
            pg.click('[data-ai="0"]')
            pg.wait_for_selector('.line[data-i="0"] .sh-res .pron', timeout=10000); pg.wait_for_timeout(400)
            r = pg.evaluate("""() => { const o = document.querySelector('.line[data-i="0"] .sh-res'), n = o.querySelector('.pron-n'), chip = document.querySelector('[data-sc="0"]');
                const link = o.querySelector('.snd a'); return {n: n && n.textContent, est: o.textContent.includes('由 AI 估计') && !o.textContent.includes('AI 听录音给的估计'), bars: [...o.querySelectorAll('.pron .ab .nm')].map(x => x.textContent),
                  widths: [...o.querySelectorAll('.pron .vbar i')].map(i => parseFloat(i.style.width) || 0), link: link && link.getAttribute('href'), chip: chip && !chip.hidden && chip.textContent,
                  avg: (document.querySelector('#shAvg') || {}).textContent || '', heard: o.textContent.includes('AI 听到：') }; }""")
            check(dev, '跟读: 发音分 shows as an AI estimate', r['n'] and r['n'].isdigit() and r['est'], r)
            check(dev, '跟读: 准确 / 流利 / 完整 as three filled bars', r['bars'] == ['准确', '流利', '完整'] and len(r['widths']) == 3 and all(w > 0 for w in r['widths']), r)
            check(dev, '跟读: the sound to practise links to 发音入门', (r['link'] or '').startswith('#/sounds/'), r['link'])
            check(dev, '跟读: the sentence row keeps its score, and the text an average', r['chip'] == r['n'] and ('平均 ' + r['n']) in r['avg'] and r['heard'], r)
            lay('跟读 result'); pg.evaluate("document.querySelector('.line[data-i=\"0\"] .sh-res').scrollIntoView({block: 'center'})"); shot('shadow')
            if size == 'phone':
                pg.click('.line[data-i="0"] .snd a'); pg.wait_for_timeout(600)
                check(dev, '跟读: 去练 opens that 发音入门 set', pg.evaluate("location.hash").startswith('#/sounds/') and bool(pg.query_selector('#view h1')), pg.evaluate('location.hash'))

            if size == 'phone':  # 伴读 of an imported article: the server voice, sentence by sentence, its files its owner's only
                text = ' '.join(['The library opens early on weekdays.', 'Students meet there before their first class.', 'Some of them read quietly in the corner.',
                                 'Others work on group projects at the long tables.', 'By noon most seats are taken.', 'In the evening it is quiet again.'])
                imp = pg.evaluate("([t, csrf]) => fetch('/api/next/import', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, "
                                  "body: JSON.stringify({title: '图书馆的一天', text: t})}).then(r => r.json())", [text, CFG['learners'][learner]['csrf']])
                go(pg, f"#/m/{imp['id']}/read"); pg.wait_for_selector('#readAlong'); pg.wait_for_timeout(300)
                pg.click('#readAlong'); pg.wait_for_selector('#reader .sent.now', timeout=5000)
                pg.wait_for_function("performance.getEntriesByType('resource').some(e => e.name.includes('/audio/own/'))", timeout=8000)
                got = pg.evaluate("""() => { const r = performance.getEntriesByType('resource').map(e => e.name);
                    return {have: r.some(n => n.includes('/api/next/tts/have')), own: r.filter(n => n.includes('/audio/own/')).map(n => n.split(location.host)[1]),
                            first: (document.querySelector('#reader .sent.now') || {}).dataset.si}; }""")
                check(dev, '伴读 of an import: read by the server voice from the learner\'s own files, the sentence lit',
                      got['have'] and got['own'] and got['own'][0].startswith('/audio/own/us-f/') and got['first'] == '0', got)
                marks = pg.evaluate("() => [!!document.querySelector('#view .read-ai .ai-voice'), !!document.querySelector('.mini-player:not([hidden]) .ai-voice'), (document.querySelector('.mini-player .lbl') || {}).textContent]")
                check(dev, '伴读: 「AI 朗读」 on the line under the button and in the mini player (《标识办法》), the label just 第 N / M 句',
                      marks[0] and marks[1] and (marks[2] or '').startswith('第 ') and '伴读' not in (marks[2] or ''), marks)
                pg.click('#readAlong')
                other = browser.new_context(); op = other.new_page()
                st = op.goto(BASE + got['own'][0]).status if got['own'] else 0
                other.close()
                check(dev, '伴读 of an import: someone else (signed out) cannot fetch its voice', st == 404, st)

                # 听 of the same import (no recording): 播放全文 in the server voice, never the browser's (the owner's bug,
                # 2026-11-25: the browser voice, a robot to them, whenever the sentence had not been made before); the
                # sentences 伴读 made are the same files (one address book); 暂停 / 继续 goes on in the same sentence, not
                # from the top; leaving and coming back offers 「从第 N 句继续」 and 从头开始
                pg.evaluate("window.__speaks = []")
                go(pg, f"#/m/{imp['id']}/listen"); pg.wait_for_selector('[data-mode="listen"]'); pg.click('[data-mode="listen"]'); pg.wait_for_selector('#playAll')
                asked = []
                on_req = lambda q: asked.append((q.post_data_json or {}).get('text')) if q.url.endswith('/api/next/tts') and q.method == 'POST' else None
                pg.on('request', on_req)
                pg.click('#playAll')
                now = "(() => { const l = document.querySelector('#view .line.now'); return l ? Number(l.dataset.i) : -1; })()"
                pg.wait_for_function(f"{now} >= 1", timeout=20000)
                got = pg.evaluate(f"() => ({{ speaks: window.__speaks.slice(), btn: document.querySelector('#playAll').textContent, now: {now} }})")
                check(dev, '听 without a recording: 播放全文 is the server voice sentence by sentence, the browser voice never asked',
                      not got['speaks'] and '暂停' in got['btn'] and got['now'] >= 1, got)
                pg.remove_listener('request', on_req)
                check(dev, '听 and 读 share one address book: the sentence 伴读 made is not asked for again', 'The library opens early on weekdays.' not in asked, asked)
                pg.click('#playAll'); pg.wait_for_timeout(300)
                k = pg.evaluate(now)
                paused = pg.evaluate("({ btn: document.querySelector('#playAll').textContent, mini: (document.querySelector('.mini-player .lbl') || {}).textContent, ms: navigator.mediaSession.playbackState })")
                pg.wait_for_timeout(1500)
                check(dev, '暂停: the button says 继续, the mini player 已暂停, the lock screen paused, and the reading waits',
                      '继续' in paused['btn'] and paused['mini'] == '已暂停' and paused['ms'] == 'paused' and pg.evaluate(now) == k, (paused, k, pg.evaluate(now)))
                pg.click('#playAll'); pg.wait_for_timeout(400)
                check(dev, '继续 goes on in the sentence it stopped in, not from the first', pg.evaluate(now) >= k >= 1 and '暂停' in pg.text_content('#playAll'), (k, pg.evaluate(now)))
                pg.click('.mini-player .toggle'); pg.wait_for_timeout(200)  # the mini player's 暂停 too
                k = pg.evaluate(now)
                go(pg, '#/')
                kept = pg.evaluate("(JSON.parse(localStorage.getItem('flow-progress') || '{}')['listen:" + imp['id'] + "'] || {}).i")
                check(dev, 'leaving the page keeps where 听 was, on this phone, under 听 (读 keeps its own)', kept == k, (k, kept))
                go(pg, f"#/m/{imp['id']}/listen"); pg.wait_for_selector('#playAll')
                back = pg.evaluate("({ btn: document.querySelector('#playAll').textContent, restart: !document.querySelector('#playRestart').hidden, mini: !!document.querySelector('.mini-player:not([hidden])') })")
                check(dev, 'back on the page: 「从第 N 句继续」 where it was left, 从头开始 beside it, nothing playing',
                      back['btn'].strip() == f'从第 {k + 1} 句继续' and back['restart'] and not back['mini'], (k, back))
                lay('听 从第 N 句继续')
                pg.click('#playAll'); pg.wait_for_function(f"{now} >= 0", timeout=10000)
                check(dev, '从第 N 句继续 starts there', pg.evaluate(now) == k, (k, pg.evaluate(now)))
                # the mini player fits its words: the label whole, 暂停 on one line, at 390 and 360 px (it was half the screen
                # wide, 「第 4 / 1…」 and 暂停 one character per line: 语流 20's iPhone screenshot)
                fits = []
                for w in (390, 360):
                    pg.set_viewport_size({'width': w, 'height': 780}); pg.wait_for_timeout(150)
                    fits.append(pg.evaluate("""() => { const m = document.querySelector('.mini-player'), l = m.querySelector('.lbl'), t = m.querySelector('.toggle'), x = m.querySelector('.close');
                        const one = el => { const r = el.getBoundingClientRect(); return r.height <= 48; };
                        return { w: innerWidth, label: l.textContent, whole: l.scrollWidth <= l.clientWidth + 1, toggle: one(t), close: one(x), mark: !!m.querySelector('.ai-voice'),
                                 tip: !!document.querySelector('#view .listen-tip .ai-voice'),
                                 inside: m.getBoundingClientRect().left >= 0 && m.getBoundingClientRect().right <= innerWidth }; }"""))
                pg.set_viewport_size(opts['viewport']); pg.wait_for_timeout(150)
                check(dev, 'the mini player fits: the label whole, 暂停 and ✕ on one line, inside the screen (390 and 360 px), with 「AI 朗读」',
                      all(f['whole'] and f['toggle'] and f['close'] and f['inside'] and f['mark'] for f in fits), fits)
                check(dev, '听: 「AI 朗读」 by the player (the voice is synthesized: 《标识办法》)', all(f['tip'] for f in fits), fits)
                pg.click('.mini-player .close'); pg.wait_for_timeout(200)
                pg.click('#playRestart'); pg.wait_for_function(f"{now} >= 0", timeout=10000)
                check(dev, '从头开始 starts at the first sentence', pg.evaluate(now) == 0, pg.evaluate(now))
                pg.click('.mini-player .close'); pg.wait_for_timeout(200)
                check(dev, 'no browser voice anywhere in this', not pg.evaluate('window.__speaks'), pg.evaluate('window.__speaks'))
                # the server out of reach (offline): a sentence heard before plays from the address kept on this phone, not the
                # browser voice; one it cannot make: the browser voice for that sentence, and the reason said, on the page too
                p4 = ctx.new_page(); p4.on('pageerror', lambda e: errors.append(str(e)))
                p4.route('**/api/next/tts', lambda r: r.abort()); p4.route('**/api/next/tts/have', lambda r: r.abort())
                p4.goto(BASE + f"/#/m/{imp['id']}/listen", wait_until='networkidle'); settle(p4)
                p4.click('[data-mode="listen"]'); p4.wait_for_selector('#playAll'); p4.evaluate("window.__speaks = []")
                p4.click('#playAll'); p4.wait_for_function(f"{now} >= 0", timeout=10000); p4.wait_for_timeout(1200)
                off = p4.evaluate(f"({{ speaks: window.__speaks.slice(), now: {now}, prep: document.querySelector('#lsPrep').textContent }})")
                check(dev, 'offline: a sentence heard before plays from the address kept on the phone (no browser voice)', not off['speaks'] and not off['prep'], off)
                p4.click('.mini-player .close'); p4.wait_for_timeout(200)
                p4.unroute('**/api/next/tts'); p4.unroute('**/api/next/tts/have')
                p4.route('**/api/next/tts', lambda r: r.fulfill(status=502, json={'error': 'AI 朗读暂时没有生成出来', 'code': 'gateway'}))
                p4.route('**/api/next/tts/have', lambda r: r.fulfill(json={'urls': [None] * 6}))
                p4.evaluate("localStorage.removeItem('flow-sv-urls'); localStorage.removeItem('flow-progress')"); p4.reload(wait_until='networkidle'); settle(p4)
                p4.click('[data-mode="listen"]'); p4.wait_for_selector('#playAll'); p4.evaluate("window.__speaks = []")
                p4.click('#playAll'); p4.wait_for_function("window.__speaks.length > 0", timeout=25000)
                fail = p4.evaluate("({ speaks: window.__speaks.slice(0, 1), prep: document.querySelector('#lsPrep').textContent, toast: document.getElementById('toast').textContent })")
                check(dev, 'a sentence the server cannot make: the browser voice reads it, and the page says why',
                      fail['speaks'] == ['The library opens early on weekdays.'] and '没有生成出来' in fail['prep'] and '没有生成出来' in fail['toast'], fail)
                p4.close()

            if size == 'phone':  # 留学: today's speaking step is the next 雅思口语 Part 1 topic, and it opens that topic
                # its own learner: by now the device learners have set radar goals and spoken, which changes today's steps
                me = CFG['learners']['abroad']
                c2 = browser.new_context(**opts, locale='zh-CN', bypass_csp=True)
                c2.add_cookies([{'name': 'flow_session', 'value': me['token'], 'url': BASE}])
                p2 = c2.new_page(); p2.goto(BASE + '/', wait_until='networkidle'); settle(p2)
                st = p2.evaluate("([csrf]) => fetch('/api/next/profile', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, "
                                 "body: JSON.stringify({level: 'B1', goal: 'abroad', themes: ['campus'], minutes: 20})}).then(r => r.status)", [me['csrf']])
                p2.goto(BASE + '/#/', wait_until='networkidle'); settle(p2); p2.wait_for_timeout(500)
                step = p2.evaluate("() => { const a = [...document.querySelectorAll('#view a[href^=\"#/speak/ielts/p1-\"]')][0]; return a ? [a.getAttribute('href'), a.textContent.replace(/\\s+/g, ' ')] : null; }")
                check(dev, '留学: 今日 speaks 雅思 Part 1, the next topic', st == 200 and step and step[0] == '#/speak/ielts/p1-study-work' and '雅思 Part 1 · 学习还是工作' in step[1], (st, step))
                if step:  # at 20 minutes a day the speaking step is under 还有时间的话 (r28 time budget): open it first
                    p2.evaluate("h => { const a = document.querySelector(`#view a[href=\"${h}\"]`), d = a && a.closest('details'); if (d) d.open = true; }", step[0])
                    p2.click(f'#view a[href="{step[0]}"]'); settle(p2)
                    check(dev, '留学: the step opens that Part 1 topic', p2.evaluate('location.hash') == step[0] and bool(p2.query_selector('#ieStart')), p2.evaluate('location.hash'))
                c2.close()

            # 口语路线: the 雅思口语 entry is on the first screen; the list says the bands are estimates
            go(pg, '#/speak')
            e = pg.evaluate("() => { const a = document.querySelector('#view .ielts-entry'); const r = a && a.getBoundingClientRect(); return a ? [a.getAttribute('href'), Math.round(r.bottom), innerHeight] : null; }")
            check(dev, '口语路线: 雅思口语 entry', e and e[0] == '#/speak/ielts' and (e[1] <= e[2] or size == 'phone-land'), e)
            pg.click('#view .ielts-entry'); settle(pg)
            li = pg.evaluate("() => ({rows: document.querySelectorAll('#view .plist .nrow').length, note: (document.querySelector('#view .ielts-note') || {}).textContent || ''})")
            check(dev, '雅思口语: 8 Part 1 topics, 8 cue cards, an honest note', li['rows'] == 16 and '不是官方成绩' in li['note'] and '不是真题' in li['note'], li)
            lay('雅思口语 list'); shot('ielts')

            # Part 1: four questions, typed; each answer has a folded 「这句可以更好」; then the four criteria
            go(pg, '#/speak/ielts/p1-mornings'); pg.click('#ieStart'); pg.wait_for_selector('#ieText')
            for k in range(4):
                pg.fill('#ieText', 'I am more of a morning person, because I feel more fresh in the morning.')
                if k == 0:
                    pg.press('#ieText', 'Enter')
                else:
                    pg.click('#ieSend')
                pg.wait_for_function(f"document.querySelectorAll('#chat .msg.me').length >= {k + 1}", timeout=8000)
                if k == 0:
                    q = pg.evaluate("() => [document.querySelectorAll('#chat .msg.ai').length, !!document.querySelector('#chat .msg.me details.better'), document.querySelector('#ieQn').textContent]")
                    check(dev, 'Part 1: the examiner asks the next question; a better way to say it is folded', q[0] == 2 and q[1] and '第 2 / 4 题' in q[2], q)
                    em = pg.evaluate("() => { const l = [...document.querySelectorAll('#view .ai-line')].find(x => x.querySelector('.ai-voice')); return l ? l.textContent : ''; }")
                    check(dev, 'Part 1: 「AI 朗读」 says the examiner\'s voice is synthesized', '考官的声音由 AI 合成' in em, em)
                    pg.click('#chat .msg.me details.better summary'); lay('Part 1 chat'); shot('ielts-p1-chat')
            pg.wait_for_selector('#ieOut .ielts-fb', timeout=10000); pg.wait_for_timeout(400)
            f = pg.evaluate("""() => { const o = document.querySelector('#ieOut'); return {overall: o.querySelector('.ielts-overall b').textContent, crit: [...o.querySelectorAll('.crit .nm')].map(x => x.textContent),
                note: o.querySelector('.ielts-note').textContent, bands: [...o.querySelectorAll('.crit .lv')].map(x => x.textContent), model: !!o.querySelector('#ieModel'), fix: !!o.querySelector('.change'), input: !document.querySelector('#ieIn').hidden}; }""")
            check(dev, 'Part 1 feedback: an overall estimate and the four criteria', f['overall'] == '约 6.0' and f['crit'] == ['流利与连贯', '词汇', '语法', '发音'] and f['bands'][:3] == ['6.0', '6.5', '5.5'], f)
            check(dev, 'Part 1 feedback: says it is an estimate, has a model answer and the fixes', '不是官方成绩' in f['note'] and f['model'] and f['fix'] and not f['input'], f)
            check(dev, 'Part 1: typed only, so 发音 is not judged', f['bands'][3] == '—', f['bands'])
            lay('Part 1 feedback'); pg.evaluate("document.querySelector('#ieOut').scrollIntoView()"); shot('ielts-p1-feedback')

            # Part 2: 开始准备 -> the one-minute clock and notes -> 提前开始说 -> recording -> 说完了 -> feedback
            go(pg, '#/speak/ielts/p2-skill')
            cue = pg.evaluate("() => { const c = document.querySelector('#cue'); return c && [c.querySelectorAll('li').length, c.textContent.includes('You should say')]; }")
            check(dev, 'Part 2: the cue card with three points and the last one', cue == [3, True], cue)
            pg.click('#p2Start'); pg.wait_for_selector('.p2-clock.prep', timeout=5000); pg.wait_for_timeout(1200)
            t = pg.text_content('#p2T')
            check(dev, 'Part 2: one minute to prepare, counting down', t in ('0:59', '0:58'), t)
            pg.fill('#p2Notes', 'cooking · grandma · one year · saves money'); lay('Part 2 preparing'); shot('ielts-p2-prep')
            pg.click('#p2Go'); pg.wait_for_selector('.p2-clock.talk', timeout=3000)
            check(dev, 'Part 2: recording starts with a two-minute clock and the notes kept', pg.text_content('#p2T') in ('2:00', '1:59') and 'grandma' in (pg.text_content('.p2-kept') or ''))
            pg.wait_for_timeout(5600); lay('Part 2 recording'); shot('ielts-p2-talk'); pg.click('#p2Done')
            pg.wait_for_selector('#ieOut .ielts-fb', timeout=15000); pg.wait_for_timeout(400)
            check(dev, 'Part 2: the microphone is let go when the talk ends', pg.evaluate(mic_free), pg.evaluate('window.__mics.length'))
            check(dev, 'Part 2: the audio session is back to playback for the feedback', pg.evaluate('navigator.audioSession.type') == 'playback')
            f = pg.evaluate("""() => { const o = document.querySelector('#ieOut'); return {overall: o.querySelector('.ielts-overall b').textContent, p: [...o.querySelectorAll('.crit .lv')].map(x => x.textContent)[3],
                said: (o.querySelector('details summary') || {}).textContent || '', cov: o.querySelectorAll('.ok-mark, .bad-mark').length}; }""")
            check(dev, 'Part 2 feedback: spoken, so 发音 is judged; what was said, with its length', f['overall'] == '约 6.0' and f['p'] == '6.0' and 'AI 转写' in f['said'] and '0:0' in f['said'], f)
            lay('Part 2 feedback'); pg.evaluate("document.querySelector('#ieOut').scrollIntoView()"); shot('ielts-p2-feedback')
            if size == 'desktop':  # no microphone: typed answer, 发音 not judged
                go(pg, '#/speak/ielts/p2-place'); pg.click('#p2Type')
                pg.fill('#p2Txt', ' '.join(['I often go to the small park near my flat after work because it is quiet and green.'] * 2)); pg.click('#p2Send')
                pg.wait_for_selector('#ieOut .ielts-fb', timeout=10000)
                check(dev, 'Part 2 typed: feedback without 发音', '不评发音' in pg.text_content('#ieOut'))
            # 口语情景 r28: a scene done before comes back as round 2 with one more requirement; each answer sets the AI's pace
            me3 = CFG['learners']['rounds']
            c3 = browser.new_context(**opts, locale='zh-CN', bypass_csp=True)
            c3.add_cookies([{'name': 'flow_session', 'value': me3['token'], 'url': BASE}])
            p3 = c3.new_page(); p3.on('pageerror', lambda e: errors.append(str(e)))
            p3.goto(BASE + '/#/speak', wait_until='networkidle'); settle(p3)
            row = p3.evaluate("() => { const a = document.querySelector('#view a.nrow[href=\"#/speak/cafe-order\"]'); return a ? a.textContent.replace(/\\s+/g, ' ') : ''; }")
            check(dev, '口语情景: a scene done once says so on the route', '练过 1 轮' in row, row)
            p3.goto(BASE + '/#/speak/cafe-order', wait_until='networkidle'); settle(p3)
            hd = p3.evaluate("() => [document.querySelector('#view .kicker').textContent, (document.querySelector('#view .round-extra') || {}).textContent || '']")
            check(dev, '口语情景: round 2 shows the round and its extra requirement', '第 2 轮' in hd[0] and '这一轮多一条' in hd[1], hd)
            vm = p3.evaluate("() => { const l = [...document.querySelectorAll('#view .ai-line')].find(x => x.querySelector('.ai-voice')); return l ? l.textContent : ''; }")
            check(dev, '口语情景: 「AI 朗读」 says the role\'s voice is synthesized', '角色、纠正和声音都由 AI 生成' in vm and 'AI 生成' in vm, vm)
            if size == 'phone':  # B8's audit: on a small phone, Safari's toolbars showing, 「开始对话」 sat under the tab bar
                vp = p3.viewport_size; p3.set_viewport_size({'width': 375, 'height': 553})
                go_at = p3.evaluate("() => { const b = document.getElementById('dlgStart').getBoundingClientRect(), t = document.querySelector('.tabs').getBoundingClientRect(); return [Math.round(b.top), Math.round(b.bottom), Math.round(t.top)]; }")
                check(dev, '口语情景 round 2 at 375×553: 「开始对话」 on the first screen, above the tab bar', 0 < go_at[0] and go_at[1] <= go_at[2], go_at)
                p3.set_viewport_size(vp)
            l3 = p3.evaluate(LAYOUT_JS, touch); check(dev, '口语情景 round 2: no sideways scroll', l3['overflow'] <= 1, f"{l3['overflow']}px {l3['wide']}")
            p3.click('#dlgStart'); p3.wait_for_selector('#chat .msg.ai', timeout=8000)
            if size == 'phone':  # the AI's line is said by the server voice (an mp3 made once and stored), not the browser voice,
                # in its role's voice: the barista is a woman, the accent is the learner's (set to uk-m for this check, then back)
                p3.wait_for_function("performance.getEntriesByType('resource').some(e => e.name.includes('/api/next/tts'))", timeout=8000)
                src = p3.evaluate("new Promise(r => setTimeout(() => r(performance.getEntriesByType('resource').filter(e => e.name.includes('/audio/tts/')).map(e => e.name.split('/audio/')[1])), 1200))")
                check(dev, '口语情景: the AI line is spoken by the server voice', bool(src) and src[0].startswith('tts/us-f/') and src[0].endswith('.mp3'), src)
                set_voice = "([v, csrf]) => fetch('/api/next/voice', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({voice: v})}).then(r => r.status)"
                p3.evaluate(set_voice, ['uk-m', me3['csrf']])
                rv = p3.evaluate("([csrf]) => fetch('/api/next/dialog', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, "
                                 "body: JSON.stringify({scenario: 'cafe-order', history: [], request_id: 'ui-role-voice-01'})}).then(r => r.json()).then(j => j.result.voice)", [me3['csrf']])
                p3.evaluate(set_voice, ['us-f', me3['csrf']])
                check(dev, '口语情景: the role has its own voice, in the learner\'s accent (barista: uk-f for a uk-m learner)', rv == 'uk-f', rv)
            p3.fill('#dlgText', 'yes'); p3.click('#dlgSend'); p3.wait_for_selector('#chat .msg.me .pace', timeout=8000)
            sl = p3.evaluate("() => [document.querySelector('#chat .msg.me .pace').dataset.pace, document.querySelector('#chat .msg.me .pace').textContent, (document.querySelector('#dlgHint .say-line b') || {}).textContent || '']")
            check(dev, '口语情景: a one-word answer slows the AI down, says so, and offers a sentence to use', sl[0] == 'easier' and '放慢' in sl[1] and len(sl[2].split()) >= 3, sl)
            p3.fill('#dlgText', 'I usually take the early train, so I want headphones that block the engine noise.'); p3.click('#dlgSend')
            p3.wait_for_function("document.querySelectorAll('#chat .msg.me').length >= 2", timeout=8000)
            pc = p3.evaluate("() => [...document.querySelectorAll('#chat .msg.me')].map(m => (m.querySelector('.pace') || {dataset: {}}).dataset.pace || '')")
            check(dev, '口语情景: a long, correct answer makes the AI go deeper', pc == ['easier', 'harder'], pc)
            l3 = p3.evaluate(LAYOUT_JS, touch); check(dev, '口语情景 with pace notes: no sideways scroll', l3['overflow'] <= 1, f"{l3['overflow']}px {l3['wide']}")
            p3.screenshot(path=str(OUT / f'{dev}-scene-round2.png'), full_page=False)
            if size == 'desktop':  # 说完就显示进度: a slow reply shows what is happening and for how long; a failed one gives the answer back
                # the reply held back 2.2 s in the page (a blocking route handler would stall the test's own event loop)
                p3.evaluate("""() => { const f = window.fetch; window.__slow = true;
                    window.fetch = (u, o) => (window.__slow && String(u).includes('/api/next/dialog')) ? new Promise(r => setTimeout(r, 2200)).then(() => f(u, o)) : f(u, o); }""")
                p3.fill('#dlgText', 'And a small croissant, please.'); p3.click('#dlgSend')
                p3.wait_for_selector('#chat .dlg-wait', timeout=3000); p3.wait_for_timeout(1300)
                wt = p3.text_content('#chat .dlg-wait') or ''
                p3.wait_for_function("document.querySelectorAll('#chat .msg.me').length >= 3", timeout=8000)
                check(dev, '口语情景: while the reply is on its way, a line says so with the seconds, gone when it comes',
                      '对方正在回' in wt and '1 秒' in wt and not p3.query_selector('#chat .dlg-wait'), wt)
                p3.evaluate('window.__slow = false')
                p3.route('**/api/next/dialog', lambda route: route.fulfill(status=502, json={'error': 'AI 服务暂时繁忙'}))
                p3.fill('#dlgText', 'Can I pay by card?'); p3.click('#dlgSend'); p3.wait_for_timeout(800)
                check(dev, '口语情景: an answer that did not get through goes back into the box', p3.input_value('#dlgText') == 'Can I pay by card?' and not p3.query_selector('#chat .dlg-wait'))
                p3.unroute('**/api/next/dialog'); p3.fill('#dlgText', '')
            if size == 'desktop':  # the end of the round: whether the requirement was met, and how often the AI adjusted
                p3.click('#dlgEnd'); p3.wait_for_selector('#dlgOut .result', timeout=10000)
                end = p3.text_content('#dlgOut') or ''
                check(dev, '口语情景: the feedback says the requirement was met and how the AI adjusted', '这一轮的要求' in end and '做到了' in end and '放慢了 1 次' in end and '加深了 1 次' in end, end[:160])
                check(dev, '口语情景: 「放进错题本」 said once, not twice', end.count('放进错题本') <= 1, end.count('放进错题本'))
            c3.close()
            if size == 'desktop':  # 能力测评的口语题 (2026-11-25): every real recording got 「请求大小不正确」 (the route had the 20 KB limit)
                pr = ctx.new_page(); pr.on('pageerror', lambda e: errors.append(str(e)))
                pr.goto(BASE + '/#/radar/test/speaking', wait_until='networkidle'); settle(pr); pr.wait_for_selector('#aMic', timeout=8000)
                pr.evaluate("""() => { try { localStorage.setItem('flow-mic-explained', '1'); } catch (e) {} window.__recOpts = []; const R = window.MediaRecorder;
                  window.MediaRecorder = class extends R { constructor(st, o) { super(st, o); window.__recOpts.push(o || {}); } }; }""")
                with pr.expect_response(lambda r: '/api/next/assess/speaking' in r.url, timeout=20000) as rs:
                    pr.click('#aMic'); pr.wait_for_timeout(4000); pr.click('#aMic')
                resp = rs.value; sent = len(resp.request.post_data_buffer or b'')
                check(dev, '能力测评 口语: a 4-second recording is taken, not refused for its size', resp.status == 200 and sent > 20000, (resp.status, sent, resp.text()[:100]))
                opts = pr.evaluate('window.__recOpts')
                check(dev, '能力测评 口语: the 75-second answer is recorded at 48 kb/s (an iPhone would make 1.7 MB at its own rate)', any(o.get('audioBitsPerSecond') == 48000 for o in opts), opts)
                pr.wait_for_selector('#view .ab-list', timeout=10000)
                pr.close()
            check(dev, 'no script errors', not errors, errors[:3])
            ctx.close()
    finally:
        browser.close()


def class_run(pw):
    """班级试用: a learner opens the teacher's link, reads what the teacher sees and not, joins and leaves again; the
    teacher's page shows the class's numbers only (no member's name), its bars, and a QR code that reads back as the link."""
    dev = 'class'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    phone = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN')
    k = CFG['class']
    wide = "document.documentElement.scrollWidth <= innerWidth + 1"
    try:
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['student']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/invite/' + k['code'].lower(), wait_until='networkidle')
        pg.wait_for_selector('#clsJoin', timeout=8000)
        terms, found = pg.text_content('#sheetCard .cls-terms') or '', pg.text_content('#clsFound') or ''
        fits = pg.evaluate("() => document.getElementById('clsJoin').getBoundingClientRect().bottom <= innerHeight")
        check(dev, '加入班级: the link opens the sheet with the code filled in, says what the teacher sees and not, and finds the class',
              '老师看不到' in terms and '你的名字' in terms and k['name'] in found and fits, (found[:60], fits))
        pg.screenshot(path=str(OUT / 'class-join.png'))
        pg.click('#clsJoin'); pg.wait_for_timeout(900); settle(pg)
        pg.wait_for_function("document.getElementById('meClassV') && document.getElementById('meClassV').textContent.length > 1", timeout=6000)
        val = pg.text_content('#meClassV') or ''
        check(dev, '加入班级: after joining, 我的 → 班级 shows the class', k['name'] in val, val)
        pg.click('#meClass'); pg.wait_for_selector('#clsOut', timeout=4000); pg.click('#clsOut')
        pg.wait_for_selector('#clsOutYes', timeout=4000); pg.click('#clsOutYes'); pg.wait_for_timeout(900)
        val = pg.text_content('#meClassV') or ''
        check(dev, '退出班级: confirmed once, and 班级 says 未加入 again', val == '未加入', val)
        ctx.close()
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['teacher']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/me', wait_until='networkidle'); settle(pg)
        pg.wait_for_selector('#meTeach a[href="#/class/%d"]' % k['id'], timeout=6000)
        pg.click('#meTeach a[href="#/class/%d"]' % k['id']); pg.wait_for_selector('.cls-weeks', timeout=6000)
        heights = pg.evaluate("[...document.querySelectorAll('.cls-weeks i')].map(i => i.getBoundingClientRect().height)")
        text = pg.text_content('#view') or ''
        points = pg.evaluate("document.querySelectorAll('.cls-points li').length")
        check(dev, '老师: the summary has the bars and the grammar points, and no member\'s name', len(heights) == 4 and heights[-1] > 10 and points >= 1
              and 'ui-member' not in text and pg.evaluate(wide), (heights, points))
        pg.click('#clsQr'); pg.wait_for_timeout(300)
        read = pg.evaluate(QR_READ, '#clsQrC')
        check(dev, '老师: the QR code reads back as the class\'s join link', read in (None, [BASE + '/#/invite/' + k['code']]),
              read if read is not None else 'no BarcodeDetector here (Linux): read on macOS')
        pg.screenshot(path=str(OUT / 'class-teacher.png'), full_page=True)
        ctx.close()
        # 老师模式: a 管理员 makes a 老师注册链接 on the console page (班级 → 老师注册链接), shown once and listed 未使用
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='zh-CN')
        cp = ctx.new_page(); cp.on('pageerror', lambda e: errs.append('console: ' + str(e)))
        cp.goto(CFG['console'] + '#classes', wait_until='networkidle'); cp.wait_for_selector('#tlF', timeout=8000)
        cp.fill('#tlF [name=note]', 'UI 测试 王老师'); cp.fill('#tlF [name=days]', '3'); cp.click('#tlF button')
        cp.wait_for_selector('#tlNew code', timeout=8000); cp.wait_for_selector('#tlList tbody tr', timeout=8000)
        made, row = cp.text_content('#tlNew code') or '', cp.text_content('#tlList tbody tr') or ''
        check(dev, '后台: 生成老师注册链接 shows the link once and lists it as 未使用', '/#/teacher/' in made and 'UI 测试 王老师' in row and '未使用' in row, (made[-20:], row[:60]))
        cp.screenshot(path=str(OUT / 'class-console-link.png'), full_page=True)
        # the link signs up a 老师账号 (no 年龄段); its home is its classes, and it makes one
        pctx = browser.new_context(**phone)
        pg = pctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/teacher/' + made.rsplit('/#/teacher/', 1)[1], wait_until='networkidle')
        pg.wait_for_selector('#authForm [name=username]', timeout=8000)
        bar, ages = pg.evaluate('location.hash'), pg.locator('#authForm [name=age]').count()
        check(dev, '老师注册链接: the sign-up opens, the token leaves the address bar, and no 年龄段 is asked', bar == '#/teacher' and ages == 0, (bar, ages))
        pg.fill('#authForm [name=email]', 'ui-teacher-new@example.com'); pg.click('#authForm [data-send]'); pg.wait_for_timeout(800)
        mail = sorted(Path(CFG['outbox']).glob('*.txt'), key=lambda f: f.stat().st_mtime)[-1].read_text(encoding='utf-8')
        pg.fill('#authForm [name=code]', re.search(r'验证码：(\d{6})', mail).group(1))
        pg.fill('#authForm [name=username]', 'ui-new-teacher'); pg.fill('#authForm [name=password]', 'correct horse 1'); pg.check('#authForm [name=storage]')
        pg.click('#authForm [type=submit]'); pg.wait_for_selector('#tNew', timeout=8000); settle(pg)
        tab = pg.text_content('[data-nav="today"] span') or ''
        check(dev, '老师账号: after signing up, the home is 我的班级 and the first tab says 班级', '我的班级' in (pg.text_content('h1') or '') and tab == '班级', tab)
        pg.fill('#tNew [name=name]', '高二（5）班'); pg.click('#tNew [type=submit]'); pg.wait_for_selector('.cls-code', timeout=8000)
        code = (pg.text_content('.cls-code') or '').strip()
        check(dev, '老师账号: a new class opens on its page with a 6-character invite code', re.fullmatch(r'[A-Z2-9]{6}', code) is not None and pg.evaluate(wide), code)
        pg.screenshot(path=str(OUT / 'class-new-teacher.png'), full_page=True)
        cp.reload(wait_until='networkidle'); cp.wait_for_selector('#tlList tbody tr', timeout=8000)
        row = cp.text_content('#tlList tbody tr') or ''
        check(dev, '后台: the used link now says 已注册 and names the new teacher account', '已注册' in row and 'ui-new-teacher' in row, row[:80])
        pctx.close()
        check(dev, 'no page errors', not errs, errs[:3])
    finally:
        browser.close()


def wait_run(pw):
    """A slow AI answer (the gateway queueing, the model busy): after 15 s a line under the button says the AI is still
    thinking, inside the screen, gone when the answer comes. The page's fetch is held back here, so no server change."""
    dev = 'wait'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    phone = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN')
    try:
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['phone']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/', wait_until='networkidle')
        go(pg, f'#/m/{PID}/output'); pg.wait_for_selector('#ans', timeout=8000)
        pg.evaluate("""() => { const f = window.fetch; window.fetch = (u, o) => /\\/api\\/next\\/rewrite/.test(String(u))
            ? new Promise(r => setTimeout(() => r(f(u, o)), 17500)) : f(u, o); }""")
        pg.fill('#ans', 'I usually wear headphones on the train, so the noise is less.'); pg.click('#go')
        pg.wait_for_timeout(9000)
        early = pg.evaluate("!!document.querySelector('.ai-wait')")
        pg.wait_for_selector('.ai-wait', timeout=9000)
        line = pg.evaluate("""() => { const l = document.querySelector('.ai-wait'), b = document.getElementById('go'), r = l.getBoundingClientRect();
            return { text: l.textContent, status: l.getAttribute('role'), below: r.top >= b.getBoundingClientRect().bottom - 1,
                     inside: r.left >= 0 && r.right <= innerWidth + 1, wide: document.scrollingElement.scrollWidth - innerWidth }; }""")
        check(dev, 'a slow AI answer: nothing in the first 15 s, then 「AI 还在想」 under the button, read out, inside the screen',
              not early and line['text'].startswith('AI 还在想') and line['status'] == 'status' and line['below'] and line['inside'] and line['wide'] <= 0, (early, line))
        pg.evaluate("document.querySelector('.ai-wait').scrollIntoView({ block: 'center' })"); pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / 'ai-wait.png'))
        pg.wait_for_selector('#finSum .fin-row', timeout=20000); pg.wait_for_timeout(400)
        check(dev, 'the line goes once the answer comes', not pg.evaluate("!!document.querySelector('.ai-wait')"))
        check(dev, 'no script errors', not errs, errs[:3])
        ctx.close()
    finally:
        browser.close()


def privacy_run(pw):
    """年龄段 and a guardian's agreement (privacy_service): the sign-up form asks a band and, under 14, the tick, before any
    request; an older account is asked once and cannot dismiss the question; under 14 without the agreement, the AI on
    the learner's own words asks for it and then goes on; the 隐私说明 opens from 我的."""
    dev = 'privacy'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    phone = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN')
    try:
        errs = []
        ctx = browser.new_context(**phone); gp = ctx.new_page(); gp.on('pageerror', lambda e: errs.append(str(e)))
        gp.goto(BASE + '/#/me', wait_until='networkidle'); settle(gp)
        gp.click('#lg'); gp.wait_for_selector('#authForm', timeout=4000); gp.click('[data-tab=reg]'); gp.wait_for_selector('#authForm .agefs', timeout=4000)
        chips = gp.evaluate("[...document.querySelectorAll('#authForm .agechip')].map(c => c.textContent.trim())")
        guard_hidden = gp.evaluate("document.querySelector('#authForm .guard').hidden")
        for name, val in (('email', 'young@example.com'), ('code', '123456'), ('username', 'xiaomei'), ('password', 'a long password 1')):
            if gp.query_selector(f'#authForm [name={name}]'):
                gp.fill(f'#authForm [name={name}]', val)
        gp.click('#authForm [type=submit]'); gp.wait_for_timeout(200)
        no_age = gp.text_content('#authErr') or ''
        gp.click('#authForm .agechip:has-text("不满 14 岁")'); gp.wait_for_timeout(150)
        shown = gp.is_visible('#authForm .guard')
        gp.click('#authForm [type=submit]'); gp.wait_for_timeout(200)
        no_tick = gp.text_content('#authErr') or ''
        check(dev, '注册: three bands, the tick only under 14, and each said before any request',
              chips == ['不满 14 岁', '14–17 岁', '18 岁及以上'] and guard_hidden and '年龄段' in no_age and shown and '家长' in no_tick, (chips, no_age, no_tick))
        gp.screenshot(path=str(OUT / 'privacy-signup.png'))
        gp.click('#authForm .agechip:has-text("14–17 岁")'); gp.wait_for_timeout(150)
        check(dev, '注册: another band hides the tick again', not gp.is_visible('#authForm .guard'))
        gp.click('#authForm [type=submit]'); gp.wait_for_timeout(200)
        no_store = gp.text_content('#authErr') or ''
        check(dev, '注册: the separate 香港 tick is required, and said before any request', '香港' in no_store and gp.is_visible('#authForm [name=storage]'), no_store)
        ctx.close()
        # 数据存放在香港 (privacy_service): an older account is asked on a page of its own, before any other page;
        # 不同意 pauses it (export, delete, sign out, agree again), and ticking goes on
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['unasked']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/', wait_until='networkidle'); pg.wait_for_selector('#stoF', timeout=8000)
        asked = '补一个同意' in (pg.text_content('h1') or '') and pg.is_visible('#stoNo')
        pg.screenshot(path=str(OUT / 'privacy-storage-ask.png'))
        pg.goto(BASE + '/#/cards', wait_until='networkidle'); pg.wait_for_selector('#stoF', timeout=8000)
        other = '补一个同意' in (pg.text_content('h1') or '')
        pg.click('#stoNo'); pg.wait_for_selector('h1:has-text("这个账号已暂停")', timeout=8000)
        paused = pg.is_visible('a[href="/api/next/export/records.json"]') and pg.is_visible('#stoDel') and pg.is_visible('#stoOut')
        pg.screenshot(path=str(OUT / 'privacy-storage-paused.png'))
        pg.click('#stoF [type=submit]'); pg.wait_for_timeout(200)
        err = pg.text_content('#stoErr') or ''
        pg.check('#stoF [name=storage]'); pg.click('#stoF [type=submit]'); pg.wait_for_timeout(1500); settle(pg)
        back = pg.query_selector('#stoF') is None
        check(dev, '数据存放: an older account is asked first on every page, 不同意 pauses it, ticking goes on',
              asked and other and paused and '勾选' in err and back, (asked, other, paused, err, back))
        ctx.close()
        # an older account without a band: asked once, the question stays until answered
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['ageless']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/', wait_until='networkidle'); pg.wait_for_selector('#ageF', timeout=8000)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(200); pg.click('.sheet-scrim', position={'x': 20, 'y': 20}, force=True); pg.wait_for_timeout(200)
        stays = pg.is_visible('#ageF')
        pg.screenshot(path=str(OUT / 'privacy-ask.png'))
        pg.click('#ageF .agechip:has-text("18 岁及以上")'); pg.click('#ageF [type=submit]'); pg.wait_for_timeout(600)
        gone = pg.evaluate("document.getElementById('sheet').hidden")
        pg.goto(BASE + '/#/me', wait_until='networkidle'); settle(pg); pg.wait_for_timeout(800)
        again = pg.query_selector('#ageF') is not None
        val = (pg.text_content('#meAgeV') or '').strip()
        check(dev, '老账号: asked once, Esc and the backdrop do not dismiss it, answered it is not asked again', stays and gone and not again and val == '18 岁及以上',
              (stays, gone, again, val))
        pg.click('a[href="#/guide/privacy"]'); pg.wait_for_timeout(1200)
        text = pg.text_content('#view') or ''
        check(dev, '我的 → 隐私说明 opens the chapter', '香港的服务器' in text and '阿里云百炼' in text, text[:60])
        ctx.close()
        # 不满 14 岁 without the agreement: 仿写 asks for it, then goes on
        ctx = browser.new_context(**phone)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['young']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + f'/#/m/{PID}/output', wait_until='networkidle'); pg.wait_for_selector('#ans', timeout=10000)
        pg.fill('#ans', 'I usually wear headphones on the train, so the noise is less.'); pg.click('#go')
        pg.wait_for_selector('#guardF', timeout=8000)
        pg.screenshot(path=str(OUT / 'privacy-guardian.png'))
        pg.click('#guardF [type=submit]'); pg.wait_for_timeout(200)
        unticked = pg.text_content('#guardErr') or ''
        pg.check('#guardF [name=guardian]'); pg.click('#guardF [type=submit]'); pg.wait_for_timeout(600)
        pg.click('#go'); pg.wait_for_selector('#finSum, .rw-result, .fb', timeout=15000)
        check(dev, '不满 14 岁: 仿写 waits for the tick, then goes on', '勾选' in unticked and pg.evaluate("document.getElementById('sheet').hidden"), unticked)
        check(dev, 'no page errors', not errs, errs[:3])
    finally:
        browser.close()


def trial_survey_run(pw):
    """班级试用问卷: three weeks in a class, 今日 offers the anonymous survey once; 「不用了」 puts it away for good on that
    phone; the survey opens as the trial one, takes the answers and says thanks, and 今日 stops offering it."""
    dev = 'trial-survey'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    phone = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN')
    cookie = [{'name': 'flow_session', 'value': CFG['learners']['veteran']['token'], 'url': BASE}]
    try:
        errs = []
        ctx = browser.new_context(**phone); ctx.add_cookies(cookie)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_selector('#trialSv', timeout=8000)
        text = pg.text_content('#trialSv') or ''
        pg.screenshot(path=str(OUT / 'trial-survey-today.png'))
        pg.click('#tsClose'); pg.wait_for_timeout(200)
        gone = pg.query_selector('#trialSv') is None
        pg.reload(wait_until='networkidle'); settle(pg); pg.wait_for_timeout(500)
        check(dev, '今日: three weeks in, one quiet line; 「不用了」 puts it away for good', '匿名问卷' in text and gone and pg.query_selector('#trialSv') is None, text[:40])
        ctx.close()
        ctx = browser.new_context(**phone); ctx.add_cookies(cookie)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_selector('#trialSv a', timeout=8000)
        pg.click('#trialSv a'); pg.wait_for_selector('.sv-hero h1', timeout=8000)
        title = pg.text_content('.sv-hero h1') or ''
        # as if the survey had been open for a minute (it refuses answers sent within 20 seconds)
        pg.evaluate("""() => { sessionStorage.setItem('flow-survey-draft:id', 'trial-2026-12'); sessionStorage.setItem('flow-survey-draft:start', String(Date.now() - 60000)); }""")
        pg.reload(wait_until='networkidle'); pg.wait_for_selector('#sv-form', timeout=8000)
        for q in pg.query_selector_all('#sv-form [data-q]'):
            first = q.query_selector('input')
            if first:
                first.click()
        pg.fill('#sv-form textarea', '希望多一些考试题')
        pg.click('#sv-form .sv-btn'); pg.wait_for_selector('.sv-done', timeout=8000)
        thanks = pg.text_content('.sv-done') or ''
        pg.screenshot(path=str(OUT / 'trial-survey-done.png'))
        pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_timeout(500)
        check(dev, '问卷: the trial survey takes the answers, thanks, and 今日 stops offering it',
              '班级试用' in title and '结项' in thanks and pg.query_selector('#trialSv') is None, (title, thanks[:40]))
        check(dev, 'no page errors', not errs, errs[:3])
    finally:
        browser.close()


def updates_run(pw):
    """更新记录: 「语流更新了」 is the first card of 今日 (where a 公告 would be), once per release on a phone that saw an
    earlier one; 「知道了」 and 「查看全部变化」 both put it away; a phone new to 语流 just notes the release; at 360 px it fits
    without sideways scroll and takes well under a screen; 我的 → 帮助 opens the record, newest first, 用法变了 first and
    marked, then 新功能 / 改进 / 修好的问题, 「去看看」 where a sentence has a page."""
    dev = 'updates'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv, args=['--mute-audio'])
    # service workers blocked: page.route sees the page's own requests only when no worker answers them
    phone = dict(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', service_workers='block')
    cookie = [{'name': 'flow_session', 'value': CFG['learners']['veteran']['token'], 'url': BASE}]
    release = {'id': 't1'}
    data = {'released': [
        {'id': 't2', 'date': '2026-11-26', 'label': '11 月 26 日晚上', 'changed': [{'text': '单词复习：「认识」挪到了右边，想换回去在「我的 → 设置」。', 'link': '#/me'}],
         'new': [{'text': '今日计划多了一步。', 'link': '#/'}], 'better': [{'text': '朗读更自然了。'}], 'fixed': [{'text': '修好了一个按钮。'}], 'note': '某个练习暂时停用。'},
        {'id': 't1', 'date': '2026-11-25', 'label': '11 月 25 日下午', 'changed': [], 'new': [{'text': '每天一份考试小练。'}], 'better': [], 'fixed': [{'text': '同时保存两次不再出错。'}]}],
        'beta': None}

    def home(route):
        resp = route.fetch()
        body = resp.json()
        e = next(x for x in data['released'] if x['id'] == release['id'])
        body['update'] = {'id': e['id'], 'label': e['label'], 'highlights': ['第一条要点', '第二条要点，写得长一些看看会不会换行', '第三条要点']}
        route.fulfill(response=resp, json=body)

    def wire(pg):
        pg.route('**/api/next/home*', home)
        pg.route('**/api/next/updates', lambda r: r.fulfill(json=data))

    def card(pg):
        pg.goto(BASE + '/#/', wait_until='networkidle'); pg.reload(wait_until='networkidle'); settle(pg); pg.wait_for_timeout(400)
        return pg.evaluate("""() => { const c = document.getElementById('updCard'); if (!c) return null; const r = c.getBoundingClientRect();
            return {text: c.textContent, items: c.querySelectorAll('li').length, h: Math.round(r.height), vh: innerHeight,
                    wide: document.documentElement.scrollWidth > innerWidth + 1, first: document.querySelector('#view .card') === c,
                    all: (document.getElementById('updAll') || {}).textContent}; }""")
    try:
        errs = []
        ctx = browser.new_context(**phone); ctx.add_cookies(cookie)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e))); wire(pg)
        # a phone that opened an earlier release
        pg.goto(BASE + '/#/', wait_until='networkidle'); pg.evaluate("() => localStorage.setItem('flow-update-seen', JSON.stringify('t0'))")
        c = card(pg)
        pg.evaluate("() => { const c = document.getElementById('updCard'); if (c) c.scrollIntoView({ block: 'center' }); }")
        pg.screenshot(path=str(OUT / 'updates-today-card.png'))
        check(dev, '今日: 「语流更新了」 is the first card at the top, three highlights and 「查看全部变化」', bool(c) and '语流更新了' in c['text'] and c['items'] == 3 and c['first'] and c['all'] == '查看全部变化', c)
        check(dev, '360 px: the card fits, no sideways scroll, well under a screen', bool(c) and not c['wide'] and c['h'] < c['vh'] * 0.45, c and (c['h'], c['vh'], c['wide']))
        pg.click('#updOk'); pg.wait_for_timeout(200)
        gone = pg.query_selector('#updCard') is None
        check(dev, '「知道了」 puts it away, the same release does not come back', gone and card(pg) is None)
        release['id'] = 't2'
        c = card(pg)
        check(dev, 'the next release shows once more', bool(c) and '11 月 26 日晚上' in c['text'], c)
        pg.click('#updAll'); pg.wait_for_selector('.upd-page', timeout=8000)
        page = pg.evaluate("""() => { const first = document.querySelector('.upd'); return {h: [...document.querySelectorAll('.upd h2')].map(x => x.textContent),
            groups: [...first.querySelectorAll('.upd-h')].map(x => x.textContent.replace('⚠︎ ', '')), note: !!document.querySelector('.upd-note'),
            go: [...first.querySelectorAll('.upd-go')].map(a => a.getAttribute('href')), marked: !!first.querySelector('.upd-changed'),
            wide: document.documentElement.scrollWidth > innerWidth + 1, beta: !!document.querySelector('.upd-beta')}; }""")
        pg.screenshot(path=str(OUT / 'updates-page.png'), full_page=True)
        check(dev, '更新记录: newest first, 用法变了 first and marked, then 新功能 / 改进 / 修好的问题, 「去看看」 links, the note; no 内测中 on 语流, no sideways scroll',
              page['h'] == ['11 月 26 日晚上', '11 月 25 日下午'] and page['groups'] == ['用法变了', '新功能', '改进', '修好的问题'] and page['marked']
              and page['go'] == ['#/me', '#/'] and page['note'] and not page['beta'] and not page['wide'], page)
        check(dev, '「查看全部」 marks it seen: 今日 does not offer it again', card(pg) is None)
        pg.goto(BASE + '/#/me', wait_until='networkidle'); settle(pg)
        row = pg.query_selector('#view a[href="#/updates"]')
        check(dev, '我的 → 帮助 has 更新记录', bool(row) and '更新记录' in (row.text_content() or ''), row and row.text_content())
        ctx.close()
        # a learner who has studied (小林, the guide's pictures), on a phone that has noted no release yet: it shows
        ctx = browser.new_context(**phone); ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['guide']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e))); wire(pg)
        c = card(pg)
        check(dev, 'a learner who has studied, nothing noted on this phone yet: the card shows', bool(c) and '11 月 26 日晚上' in c['text'], c)
        ctx.close()
        # someone new to 语流: nothing new to them, so no card
        ctx = browser.new_context(**phone)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e))); wire(pg)
        check(dev, 'someone new to 语流: no card', card(pg) is None)
        ctx.close()
        check(dev, 'no page errors', not errs, errs[:3])
    finally:
        browser.close()


def a11y_run(pw):
    dev = 'a11y'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        found = {}
        for theme in ('light', 'dark'):
            ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', color_scheme=theme, bypass_csp=True)
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['a11y']['token'], 'url': BASE}])
            pg = ctx.new_page(); pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
            for p in PAGES:
                go(pg, p); pg.wait_for_timeout(250)
                for kind, items in pg.evaluate(A11Y_JS).items():
                    for x in items:
                        found.setdefault((kind, theme), []).append(f'{p}: {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}')
            if theme == 'light':
                # a sheet is a dialog with a title, and the focus goes into it
                go(pg, '#/me'); pg.click('#meText')
                # openSheet moves the focus in 30 ms after drawing it (02-shell.js): wait for that, up to 2 s, instead of a
                # fixed 200 ms that a busy runner overran once (main 49d610b, 2026-11-24); a focus that never moves in still fails
                try:
                    pg.wait_for_function("() => !document.getElementById('sheet').hidden && document.getElementById('sheetCard').contains(document.activeElement)", timeout=2000)
                except Exception:
                    pass  # the check below says what was there
                dlg = pg.evaluate("""() => { const c = document.getElementById('sheetCard'), t = document.getElementById(c.getAttribute('aria-labelledby'));
                  return [c.getAttribute('role'), c.getAttribute('aria-modal'), !!(t && t.textContent.trim()), c.contains(document.activeElement)]; }""")
                check(dev, 'a sheet is a modal dialog with its title, and the focus moves into it', dlg == ['dialog', 'true', True, True], dlg)
                pg.evaluate("document.querySelector('#sheet [data-close]').click()")
                # right and wrong answers: a mark as well as a colour
                go(pg, f'#/m/{PID}/check'); pg.wait_for_selector('#pane .q', timeout=6000)
                for q in pg.query_selector_all('#pane .q'):
                    q.query_selector_all('.ans')[-1].click(); pg.wait_for_timeout(250)
                marks = pg.evaluate("""() => ['.ans.right', '.ans.wrong'].map(s => { const e = document.querySelector(s); return e ? getComputedStyle(e, '::after').content : null; })""")
                live = pg.evaluate("[...document.querySelectorAll('#pane .fb')].every(f => f.getAttribute('aria-live') === 'polite')")
                check(dev, 'right and wrong answers carry ✓ and ✗, not only green and red, and the result is announced', marks[0] == '"✓"' and marks[1] in ('"✗"', None) and live, (marks, live))
                cdp = ctx.new_cdp_session(pg)
                for vision in ('deuteranopia', 'protanopia'):
                    cdp.send('Emulation.setEmulatedVisionDeficiency', {'type': vision})
                    pg.evaluate("document.querySelector('#pane .q').scrollIntoView()"); pg.wait_for_timeout(200)
                    pg.screenshot(path=str(OUT / f'a11y-{vision}.png'))
                cdp.send('Emulation.setEmulatedVisionDeficiency', {'type': 'none'})
            ctx.close()
        for kind, label in (('unnamed', 'every button and link has a name a screen reader can say'), ('noalt', 'every image has alt text'),
                            ('unlabeled', 'every field has a label (not only a placeholder)'), ('dupid', 'no id is used twice on a page'),
                            ('contrast', 'text contrast meets WCAG AA'), ('lang', 'English is marked lang="en", so it is read with an English voice')):
            for theme in ('light', 'dark'):
                bad = found.get((kind, theme), [])
                check(dev, f'{label} ({theme})', not bad, f'{len(bad)}: ' + ' | '.join(bad[:4]))
    finally:
        browser.close()


# ---- 考试冲刺 (r27): the exam hub, the line on 今日, question-type practice, my exam and its date; five sizes, light and dark
SPRINT_PAGES = ['#/exam', '#/', '#/exam/cet4/banked', '#/exam/cet4/match', '#/exam/ielts/headings', '#/exam/ielts/tfng', '#/exam/tem8/proof',
                '#/exam/gk/seven', '#/exam/ky/cloze', '#/exam/tem4/choice', '#/vocab/plan', '#/mix/exam/cet4']
SPRINT_SIZES = {'phone': (390, 844, True), 'phone-360': (360, 780, True), 'phone-land': (844, 390, True), 'tablet': (820, 1180, True), 'desktop': (1440, 900, False)}


def sprint_run(pw):
    dev = 'sprint'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    tok = CFG['learners']['sprint']['token']

    def context(w, h, touch, theme='light'):
        ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=touch, has_touch=touch, device_scale_factor=2, locale='zh-CN',
                                  color_scheme=theme, bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
        pg = ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        return ctx, pg, errs

    def pick_all(pg, n):  # gap i takes option i (one option per gap)
        for i in range(n):
            pg.click(f'button.gap[data-gap="{i}"]'); pg.wait_for_selector('#sheetCard [data-pick]'); pg.click(f'#sheetCard [data-pick="{i}"]'); pg.wait_for_timeout(120)
    try:
        # every page at every size: nothing wider than the screen, no squeezed text, controls big enough to tap
        for size, (w, h, touch) in SPRINT_SIZES.items():
            ctx, pg, errs = context(w, h, touch)
            for page in SPRINT_PAGES:
                go(pg, page); pg.wait_for_timeout(250)
                lay = pg.evaluate(LAYOUT_JS, touch)
                check(dev, f'{size} {page}: no sideways scroll, no squeezed text', lay['overflow'] <= 1 and not lay['squeezed'], (lay['overflow'], lay['wide'], lay['squeezed']))
                if touch:
                    check(dev, f'{size} {page}: controls at least 32×32, fields 16px', not lay.get('small') and not lay.get('smallFields'), (lay.get('small'), lay.get('smallFields')))
                if page == '#/' and h > w:  # with 这周进步 on top and the exam line under the title, the next step is still on the first screen
                    b = pg.evaluate("Math.round(document.querySelector('#view .go-next').getBoundingClientRect().bottom)")
                    check(dev, f'{size} 今日: the next-step button is on the first screen', b <= h, (b, h))
                pg.screenshot(path=str(OUT / f"sprint-{size}-{page.strip('#/').replace('/', '_') or 'today'}.png"))
            # the hub at this size: the trend is drawn to the width it has, inside the screen
            go(pg, '#/exam'); pg.wait_for_timeout(300)
            tr = pg.evaluate("""() => { const s = document.querySelector('.trend-chart.big svg'); if (!s) return null; const r = s.getBoundingClientRect();
              return [document.querySelectorAll('.trend-chart.big circle').length, Math.round(r.right) <= innerWidth, document.querySelectorAll('.trend-parts .tp').length]; }""")
            check(dev, f'{size} hub: the score trend has four sets and three parts, inside the screen', tr == [4, True, 3], tr)
            check(dev, f'{size}: no script errors', not errs, errs[:3])
            ctx.close()
        # light and dark: contrast, names and labels on the new pages
        for theme in ('light', 'dark'):
            ctx, pg, errs = context(390, 844, True, theme)
            bad = []
            for page in ('#/exam', '#/exam/cet4/banked', '#/exam/ielts/headings', '#/exam/tem8/proof', '#/exam/ielts/tfng'):
                go(pg, page); pg.wait_for_timeout(250)
                for kind, items in pg.evaluate(A11Y_JS).items():
                    bad += [f'{page} {kind}: {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}' for x in items]
            check(dev, f'{theme}: contrast, names and labels on the exam pages', not bad, f'{len(bad)}: ' + ' | '.join(bad[:4]))
            pg.screenshot(path=str(OUT / f'sprint-{theme}-tfng.png'))
            ctx.close()

        ctx, pg, errs = context(390, 844, True)
        # the hub
        go(pg, '#/exam'); pg.wait_for_timeout(300)
        hub = pg.evaluate("""() => ({h: document.querySelector('#view h1').textContent, pace: (document.querySelector('.sp-pace') || {}).textContent || '',
          types: [...document.querySelectorAll('#spTypesH ~ .mlist .mrow b')].map(b => b.textContent), start: !!document.getElementById('exStart'),
          note: document.querySelector('#spTypesH + p').textContent})""")
        hub['api'] = pg.evaluate("fetch('/api/next/exam').then(r => r.json()).then(o => o.exams.find(e => e.id === 'cet4').types.map(t => t.title))")  # from the data
        check(dev, 'hub: my exam on top, the pace said plainly, two question types labelled original, the full set',
              hub['h'] == '大学英语四级' and '背词节奏：跟不上' in hub['pace'] and '每天 40 个' in hub['pace'] and hub['types'] == hub['api'] + ['阅读一篇']
              and hub['start'] and '不是真题' in hub['note'], hub)
        pg.screenshot(path=str(OUT / 'sprint-hub.png'))
        pg.click('.sp-pace [data-daily]')
        pg.wait_for_function("() => (document.querySelector('.sp-pace') || {}).textContent && document.querySelector('.sp-pace').textContent.includes('现在每天 40 个')", timeout=6000)
        check(dev, 'hub: one tap sets the suggested number of new words a day', True)
        # 今日: one line under the plan's title; in the last four weeks the plan has the exam's set and its grammar points
        go(pg, '#/'); pg.wait_for_timeout(300)
        t = pg.evaluate("""() => ({line: (document.querySelector('.tp-head .sprint-line') || {}).textContent || '',
          steps: [...document.querySelectorAll('.today-plan .prow')].map(a => a.getAttribute('href'))})""")
        check(dev, '今日: 「四级 还有 19 天」 under the title; the plan has the exam set and 考点语法',
              '四级' in t['line'] and '还有 19 天' in t['line'] and '#/exam/cet4' in t['steps'] and '#/mix/exam/cet4' in t['steps'], t)
        go(pg, '#/mix/exam/cet4'); pg.wait_for_selector('#mixQ .ans', timeout=6000)
        check(dev, "考点语法: a mixed round on the exam's points", '考点语法' in (pg.text_content('#view .kicker') or ''), pg.text_content('#view .kicker'))
        # 选词填空: a gap opens the options, one option fills one gap (picked again, it moves), then every answer with its reason
        go(pg, '#/exam/cet4/banked'); pg.wait_for_selector('button.gap', timeout=6000)
        pg.click('button.gap[data-gap="0"]'); pg.wait_for_selector('#sheetCard [data-pick]'); pg.click('#sheetCard [data-pick="0"]'); pg.wait_for_timeout(200)
        first = pg.text_content('button.gap[data-gap="0"] .gv')
        pg.click('button.gap[data-gap="1"]'); pg.wait_for_selector('#sheetCard [data-pick]')
        note = pg.text_content('#sheetCard [data-pick="0"]') or ''
        pg.screenshot(path=str(OUT / 'sprint-banked-sheet.png'))
        pg.click('#sheetCard [data-pick="0"]'); pg.wait_for_timeout(200)
        moved = (pg.text_content('button.gap[data-gap="0"] .gv'), pg.text_content('button.gap[data-gap="1"] .gv'))
        check(dev, '选词填空: a picked option fills its gap, and picked for another gap it moves there',
              first.startswith('A.') and '已用在第 1 空' in note and moved[0] == '＿＿＿' and moved[1].startswith('A.'), (first, note[-12:], moved))
        pick_all(pg, 10)
        used = pg.evaluate("document.querySelectorAll('.xt-banklist li.used').length")
        pg.click('#xtDone'); pg.wait_for_selector('.xt .pit', timeout=6000)
        res = pg.evaluate("""() => ({h: document.querySelector('#view h1').textContent, n: document.querySelectorAll('.xt .pit').length,
          why: [...document.querySelectorAll('.xt .pit .tiny')].every(x => x.textContent.trim().length > 4)})""")
        check(dev, '选词填空: ten gaps marked used, handed in, ten answers each with its reason', used == 10 and '题做对' in res['h'] and res['n'] == 10 and res['why'], (used, res))
        pg.screenshot(path=str(OUT / 'sprint-banked-result.png'))
        # the other kinds: the first choice everywhere, handed in
        for page, n in (('#/exam/cet4/match', 10), ('#/exam/ielts/tfng', 7), ('#/exam/tem4/choice', 10), ('#/exam/ky/cloze', 10), ('#/exam/cet4/reading', None)):
            go(pg, page); pg.wait_for_selector('.xt-q', timeout=6000)
            n = n or pg.evaluate("document.querySelectorAll('.xt-q').length")  # 阅读一篇 (考试小练): as many as the passage has, 2–4
            mark = pg.evaluate("({ line: (document.querySelector('.xt .ai-line') || {}).textContent || '', tag: !!document.querySelector('.xt .row .ai-mark') })")
            check(dev, f'{page}: marked as AI-assisted (《标识办法》)', mark['tag'] if page.endswith('/reading') else '题目和解析由 AI 辅助编写' in mark['line'], mark)
            pg.evaluate("() => document.querySelectorAll('.xt-q').forEach(q => q.querySelector('.ans').click())")
            pg.click('#xtDone'); pg.wait_for_selector('.xt .pit', timeout=6000)
            got = pg.evaluate("document.querySelectorAll('.xt .pit').length")
            check(dev, f'{page}: answered and handed in, {n} answers explained', got == n, got)
        go(pg, '#/exam/tem8/proof'); pg.wait_for_selector('.xw', timeout=6000)
        pg.click('.xt-line[data-q="0"] .xw[data-w="1"]'); pg.wait_for_timeout(100)
        pressed = pg.get_attribute('.xt-line[data-q="0"] .xw[data-w="1"]', 'aria-pressed')
        pg.evaluate("() => document.querySelectorAll('.xt-line').forEach(l => l.querySelector('.xw').click())")
        pg.click('#xtDone'); pg.wait_for_selector('.xt .pit', timeout=6000)
        fix = pg.text_content('.xt .pit') or ''
        check(dev, '改错: a tapped word is marked, and the result gives each correction', pressed == 'true' and '→' in fix, (pressed, fix[:60]))
        go(pg, '#/exam/ielts/headings'); pg.wait_for_selector('button.gap', timeout=6000)
        pick_all(pg, pg.evaluate("document.querySelectorAll('button.gap').length"))
        pg.click('#xtDone'); pg.wait_for_selector('.xt .pit', timeout=6000)
        check(dev, '段落标题匹配: every paragraph gets a heading, then the answers', pg.evaluate("document.querySelectorAll('.xt .pit').length") == 7)
        go(pg, '#/exam'); pg.wait_for_timeout(300)
        last = pg.evaluate("[...document.querySelectorAll('#spTypesH ~ .mlist .mrow .tiny')].map(x => x.textContent)")
        check(dev, 'hub: the question types show the last result', any('上次' in x for x in last), last)
        # 我的 → 我的考试: another exam and date; 考试练习 and 背词计划 follow
        go(pg, '#/me'); pg.click('#meExam'); pg.wait_for_selector('#egSave')
        pg.click('#sheetCard [data-exam="ielts"]')
        checked = pg.get_attribute('#sheetCard [data-exam="ielts"]', 'aria-checked')
        import datetime
        pg.fill('#egIn', (datetime.date.today() + datetime.timedelta(days=60)).isoformat())
        pg.click('#egSave'); pg.wait_for_function("() => document.getElementById('sheet').hidden", timeout=6000); settle(pg)
        val = pg.text_content('#meExamV') or ''
        go(pg, '#/exam'); h1 = pg.text_content('#view h1')
        go(pg, '#/vocab/plan'); pg.wait_for_timeout(300)
        plan = pg.evaluate("""() => ({on: [...document.querySelectorAll('#goal [aria-pressed=true]')].map(x => x.textContent), row: !document.getElementById('pxRow').hidden,
          hint: document.getElementById('pxHint').textContent})""")
        check(dev, '我的考试: 雅思 in 60 days; 我的, 考试练习 and 背词计划 all follow',
              checked == 'true' and '雅思' in val and h1 == '雅思' and plan['on'] == ['雅思'] and plan['row'] and '离考试还有 60 天' in plan['hint'], (checked, val, h1, plan))
        pg.evaluate("document.getElementById('goal').scrollIntoView()"); pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / 'sprint-plan.png'))
        check(dev, 'no script errors in the flows', not errs, errs[:3])
        ctx.close()
    finally:
        browser.close()


def about_run(pw):
    """认识语流 (/about), the introduction page: on every device and at 360 px, light and dark, under the page's own CSP:
    nothing scrolls sideways, every part comes in as it is scrolled to, the screenshots load, no errors; then the demos
    (tap a word, the word-book shelf, the questions), the ways in from the learning site, and the page with less motion
    (screen readers, contrast)."""
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    sizes = {**DEVICES, 'phone-360': dict(viewport={'width': 360, 'height': 780}, is_mobile=True, has_touch=True, device_scale_factor=2)}
    try:
        for dev, opts in sizes.items():
            for theme in ('light', 'dark'):
                tag = f'about-{dev}-{theme}'
                ctx = browser.new_context(**opts, locale='zh-CN', color_scheme=theme)
                pg = ctx.new_page(); errors, bad = [], []
                pg.on('pageerror', lambda e: errors.append(str(e)))
                pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                pg.on('response', lambda r: bad.append(f'{r.status} {r.url}') if r.status >= 400 else None)
                pg.goto(BASE + '/about', wait_until='networkidle')
                vh, y, wide = opts['viewport']['height'], 0, []
                while y < pg.evaluate('document.scrollingElement.scrollHeight'):
                    pg.evaluate(f'window.scrollTo(0, {y})'); pg.wait_for_timeout(110)
                    wide.append(pg.evaluate('document.scrollingElement.scrollWidth - innerWidth'))
                    y += int(vh * 0.6)
                pg.wait_for_timeout(1400)
                check(tag, 'no sideways scrolling anywhere on the page', max(wide) <= 0, max(wide))
                left = pg.evaluate("[...document.querySelectorAll('.rv')].filter(e => !e.classList.contains('in')).map(e => e.className)")
                check(tag, 'every part came in as it was scrolled to', not left, left[:4])
                imgs = pg.evaluate("[...document.images].filter(i => i.getClientRects().length && !(i.complete && i.naturalWidth)).map(i => i.currentSrc || i.src)")
                check(tag, 'every screenshot on the page has loaded', not imgs, imgs[:4])
                dark_pics = pg.evaluate("[...document.images].filter(i => i.getClientRects().length && i.closest('picture')).every(i => /-d\\.jpg/.test(i.currentSrc) === matchMedia('(prefers-color-scheme: dark)').matches)")
                check(tag, 'the screenshots follow light and dark', dark_pics)
                check(tag, 'no page errors, CSP refusals or failed requests', not errors and not bad, errors[:3] + bad[:3])
                pg.evaluate('window.scrollTo(0, 0)'); pg.wait_for_timeout(300)
                pg.screenshot(path=str(OUT / f'{tag}.jpg'), type='jpeg', quality=60, full_page=True)
                if theme == 'light':
                    pg.evaluate("document.getElementById('lookup').scrollIntoView()"); pg.wait_for_timeout(600)
                    pg.click('#demoSentence .wd[data-k="roar"]'); pg.wait_for_timeout(250)
                    roar = pg.evaluate("[document.getElementById('lcWord').textContent, !!document.querySelector('#lcSrc mark')]")
                    pg.click('#demoSentence .wd[data-k="drains"]'); pg.wait_for_timeout(250)
                    drain = pg.evaluate("[document.getElementById('lcWord').textContent, document.getElementById('lcPh').textContent]")
                    check(tag, 'tapping a word in the demo shows its dictionary entry (drains → drain, 原形)', roar == ['roar', True] and drain[0] == 'drain' and '原形 drain' in drain[1], (roar, drain))
                    pg.evaluate("document.getElementById('books').scrollIntoView()"); pg.wait_for_timeout(300)
                    pg.click('#shelfTabs .tab:has-text("英语专业")'); pg.wait_for_timeout(400)
                    shelf = pg.evaluate("document.getElementById('shelfPanel').innerText + ' | ' + document.getElementById('shelfBasis').innerText")
                    check(tag, 'the word-book shelf switches groups and says 专四、专八 are not official lists', '专四词汇' in shelf and '6,161' in shelf and '不是官方词表' in shelf, shelf[:160])
                    pg.click('#faq .qa:first-child summary'); pg.wait_for_timeout(600)
                    check(tag, 'a question opens', pg.evaluate("document.querySelector('#faq .qa').open"))
                    # 一分钟看懂语流: plays by itself once on screen, a bar jumps to its part, the button pauses
                    pg.evaluate("document.getElementById('fmStage').scrollIntoView({block: 'center', behavior: 'instant'})"); pg.wait_for_timeout(1600)
                    t1 = pg.evaluate("document.getElementById('fmTime').textContent"); pg.wait_for_timeout(1200)
                    t2 = pg.evaluate("document.getElementById('fmTime').textContent")
                    check(tag, 'the one-minute film plays by itself once it is on screen', t1 != t2 and pg.evaluate("document.getElementById('fmPlayL').textContent") == '暂停', (t1, t2))
                    pg.click('#fmCh .fm-cb:nth-child(5)'); pg.wait_for_timeout(500)
                    now = pg.evaluate("[document.getElementById('fmNow').textContent, document.querySelector('.fm-sc[data-seg=daily]').classList.contains('on')]")
                    pg.click('#fmPlay'); pg.wait_for_timeout(200)
                    t3 = pg.evaluate("document.getElementById('fmTime').textContent"); pg.wait_for_timeout(700)
                    check(tag, 'a bar under the film jumps to its part (5 · 每天一篇) and the button pauses it', now == ['5 / 10 · 每天一篇', True] and t3 == pg.evaluate("document.getElementById('fmTime').textContent"), (now, t3))
                    if dev == 'desktop':
                        pg.evaluate("document.querySelector('.step[data-step=\"2\"]').scrollIntoView({block: 'center', behavior: 'instant'})"); pg.wait_for_timeout(900)
                        on = pg.evaluate("[document.querySelector('.layer.on') && document.querySelector('.layer.on').dataset.i, getComputedStyle(document.querySelector('.stage-in')).position]")
                        check(tag, 'the phone beside the four steps follows the step being read', on == ['2', 'sticky'], on)
                ctx.close()
        # the ways in from the learning site, as a first-time guest
        ctx = browser.new_context(**DEVICES['phone'], locale='zh-CN')
        pg = ctx.new_page(); pg.goto(BASE + '/#/welcome', wait_until='networkidle'); settle(pg)
        check('about', 'a first visit sees the line to 认识语流 under the starting questions', pg.query_selector('#view a[href="/about"]') is not None)
        pg.goto(BASE + '/#/me'); settle(pg)
        check('about', '我的 → 帮助 has 认识语流', pg.query_selector('#view a.grow[href="/about"]') is not None)
        pg.goto(BASE + '/#/about'); pg.wait_for_url('**/about', timeout=6000)
        check('about', '#/about (the guide links there) opens the page', pg.url.endswith('/about'))
        pg.click('a[href="/#/join"]'); pg.wait_for_selector('#sheetCard', timeout=8000); pg.wait_for_timeout(400)
        sheet = pg.evaluate("[document.getElementById('sheetTitle') && document.getElementById('sheetTitle').textContent, location.hash]")
        check('about', '「注册账号」 opens the learning site with the sign-up sheet', sheet[0] == '注册语流' and sheet[1] in ('#/', '#/welcome'), sheet)
        ctx.close()
        # less motion: everything is there at once; names, alt text, contrast and lang in both themes
        found = {}
        for theme in ('light', 'dark'):
            ctx = browser.new_context(**DEVICES['phone'], locale='zh-CN', color_scheme=theme, reduced_motion='reduce')
            pg = ctx.new_page(); pg.goto(BASE + '/about', wait_until='networkidle'); pg.wait_for_timeout(300)
            shown = pg.evaluate("[...document.querySelectorAll('.rv, .display .w')].every(e => getComputedStyle(e).opacity === '1')")
            check('about', f'with less motion every part is shown at once ({theme})', shown)
            pg.evaluate("document.getElementById('fmStage').scrollIntoView({block: 'center', behavior: 'instant'})"); pg.wait_for_timeout(1500)
            still = pg.evaluate("[document.getElementById('fmPlayL').textContent, document.getElementById('fmNow').textContent, document.querySelector('.fm-sc[data-seg=speak]').classList.contains('on')]")
            check('about', f'with less motion the film does not play by itself and shows the café conversation ({theme})', still == ['播放', '2 / 10 · 口语情景', True], still)
            for kind, items in pg.evaluate(A11Y_JS).items():
                found.setdefault((kind, theme), []).extend(items)
            ctx.close()
        # the film's recording view: the stage alone, the long and short cuts, and only the words the server allows
        ctx = browser.new_context(viewport={'width': 1280, 'height': 720}, locale='zh-CN')
        pg = ctx.new_page()
        pg.goto(BASE + '/about?record=1&cut=short&gates=voice,fast', wait_until='networkidle')
        rec = pg.evaluate("[Math.round(FILM.dur * 100) / 100, FILM.segs.map(s => s.id).join(' '), getComputedStyle(document.getElementById('fmStage')).position, FILM.caps.some(c => c[2].includes('一两秒'))]")
        check('about', 'the film records: the short cut is 28.8 s in 6 parts, the stage fills the window', rec == [28.8, 'open speak daily words any end', 'fixed', True], rec)
        pg.goto(BASE + '/about?record=1&cut=long', wait_until='networkidle')  # what this server has on (<html data-film>): the test server reads with the server voice, not on 百炼
        said = pg.evaluate("""(() => { const on = (document.documentElement.dataset.film || '').split(' '), said = FILM.caps.map(c => c[2]).join(' ');
          return [Math.round(FILM.dur * 100) / 100, FILM.segs.length, /一两秒/.test(said) === on.includes('fast'), /更像真人/.test(said) === on.includes('voice'),
                  (getComputedStyle(document.querySelector('.fm-fast')).display === 'none') === !on.includes('fast'), on.join(' ')]; })()""")
        check('about', 'the film mentions the server voice and quick replies only where the server has them on (long cut: 81.5 s, 10 parts)', said[:5] == [81.5, 10, True, True, True], said)
        ctx.close()
        for kind, label in (('unnamed', 'every button and link has a name'), ('noalt', 'every image has alt text'), ('dupid', 'no id is used twice'),
                            ('contrast', 'text contrast meets WCAG AA'), ('lang', 'English is marked lang="en"')):
            for theme in ('light', 'dark'):
                items = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in found.get((kind, theme), [])]
                check('about', f'{label} ({theme})', not items, f'{len(items)}: ' + ' | '.join(items[:4]))
    finally:
        browser.close()


# ---- 这周进步 (r27): the card at the top of 今日 on phones (390 and 360 px), a phone held sideways, a tablet and a
# computer, in light and dark; its details; the three lines after a text; 每周进度邮件 in 我的; the mail's link
PROGRESS_SIZES = {'phone-390': (390, 844), 'phone-360': (360, 780), 'phone-land': (844, 390), 'tablet': (820, 1180), 'desktop': (1440, 900)}
CARD_JS = r"""() => {
  const c = document.getElementById('weekCard'); if (!c) return null;
  const r = el => el.getBoundingClientRect(), plan = document.querySelector('#view .today-plan, #view .hello'), go = document.querySelector('#view .go-next');
  const tiles = [...c.querySelectorAll('.wk-tile')];
  const rgb = s => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  const lum = s => { const [R, G, B] = rgb(s).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * R + .7152 * G + .0722 * B; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const bg = getComputedStyle(c).backgroundColor;
  return {
    tiles: tiles.length, oneRow: new Set(tiles.map(t => Math.round(r(t).top))).size === 1,
    values: tiles.map(t => t.querySelector('b').textContent.trim()),
    clipped: tiles.filter(t => t.scrollWidth > t.clientWidth + 1 || [...t.children].some(x => r(x).right > r(t).right + 1)).map(t => t.textContent.trim()),
    wrapped: tiles.filter(t => [...t.querySelectorAll('.tiny')].some(l => r(l).height > parseFloat(getComputedStyle(l).lineHeight) * 1.5)).map(t => t.textContent.trim()),
    below: !plan || r(c).top >= r(plan).bottom - 1, inView: r(c).left >= 0 && r(c).right <= innerWidth,
    goBottom: go ? Math.round(r(go).bottom) : null, H: innerHeight,
    wide: document.scrollingElement.scrollWidth - innerWidth,
    surface: bg !== getComputedStyle(document.body).backgroundColor,
    contrast: Math.min(ratio(getComputedStyle(c.querySelector('.wk-tile b')).color, bg), ratio(getComputedStyle(c.querySelector('.wk-tile .muted')).color, bg),
                       ratio(getComputedStyle(c.querySelector('.wk-tile .sub')).color, bg)),
    chip: !!document.getElementById('habitBtn'),
  };
}"""

# 今日 from the top: 好句, 热点, the plan, 这周进步; nothing in the 好句 card cut off; its buttons big enough to tap
FOLD_JS = """() => { const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const tabs = q('.tabs'), cs = tabs && getComputedStyle(tabs), tabTop = tabs && cs.position === 'fixed' && cs.display !== 'none' ? r(tabs).top : innerHeight;
  const lc = q('#lineCard'), nc = q('#view .news-card'), h1 = q('#tpTitle'), go = q('#view .today-plan .go-next'), say = q('#lcSay'), ai = nc && nc.querySelector('.ai-mark');
  return { lineH: lc ? Math.round(r(lc).height) : null, newsH: nc ? Math.round(r(nc).height) : null, newsAI: !!(ai && r(ai).height > 0 && r(ai).bottom <= r(nc).bottom),
    planInView: !!(h1 && go && r(h1).top >= 0 && r(go).bottom <= tabTop), say: !!(say && say.offsetParent !== null), foldShown: !!(q('#lcFold') && q('#lcFold').offsetParent !== null) }; }"""
TOP_JS = r"""() => {
  const r = el => el.getBoundingClientRect();
  const blocks = [['lineCard', '#lineCard'], ['news', '#view .news-card'], ['plan', '#view .today-plan'], ['week', '#weekCard']]
    .map(([k, sel]) => [k, document.querySelector(sel)]).filter(([, el]) => el).sort((a, b) => r(a[1]).top - r(b[1]).top).map(([k]) => k);
  const card = document.getElementById('lineCard');
  return { order: blocks, wide: document.scrollingElement.scrollWidth - innerWidth,
           clipped: card ? [...card.querySelectorAll('*')].filter(e => r(e).right > r(card).right + 1).map(e => e.className || e.tagName).slice(0, 3) : ['no card'],
           small: card ? [...card.querySelectorAll('button')].filter(b => b.offsetParent !== null && r(b).height < 40).map(b => b.textContent.trim()) : [] };
}"""

SWIPE_SIZES = {'ipad-land': (1180, 820), 'ipad-mini-land': (1133, 744), 'phone': (390, 844)}
SWIPE_AT = """([x, y, dx, dy]) => {
  const el = document.elementFromPoint(x, y) || document.documentElement;  // a finger's touches go to what is under it
  const mk = (type, X, Y) => { const t = new Touch({ identifier: 1, target: el, clientX: X, clientY: Y });
    el.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [t], changedTouches: [t] })); };
  mk('touchstart', x, y); for (let k = 1; k <= 6; k++) mk('touchmove', x + dx * k / 6, y + dy * k / 6); mk('touchend', x + dx, y + dy);
  return el.tagName + (el.id ? '#' + el.id : '');
}"""
CARD_STATE = """() => ({ front: !!document.querySelector('[data-claim]'), back: !!document.querySelector('.open-card'),
  rates: [...document.querySelectorAll('[data-rate]')].map(b => b.dataset.rate), foot: ((document.querySelector('.rfoot, .vtest .tc') || {}).textContent || '').trim(),
  word: ((document.querySelector('.wordbig') || {}).textContent || '').trim() })"""


def swipe_run(pw):
    """认识 / 不认识 by swiping, from anywhere on the screen: on an iPad sideways the card is a column in the middle and
    a swipe that started beside it or below it did nothing (r27). Not from a button, and not a scroll."""
    dev = 'swipe'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        for size, (w, h) in SWIPE_SIZES.items():
            ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True)
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners'][f'swipe-{size}']['token'], 'url': BASE}])
            pg = ctx.new_page(); errors = []; pg.on('pageerror', lambda e: errors.append(page_error(pg, e)))
            sw = lambda x, y, dx, dy=0: (pg.evaluate(SWIPE_AT, [x, y, dx, dy]), pg.wait_for_timeout(450))[0]
            state = lambda: pg.evaluate(CARD_STATE)
            pg.goto(BASE + f'/?swipe={size}#/review', wait_until='networkidle'); pg.wait_for_selector('[data-claim]', timeout=8000)
            box = pg.evaluate("() => { const r = document.querySelector('.review').getBoundingClientRect(); return [r.left, r.right, r.bottom]; }")
            s0 = state()
            sw(int(w / 2), int(h * 0.45), 0, 0)  # a touch that does not move: nothing
            check(f'{dev} {size}', 'a touch that does not move rates nothing', state() == s0, state())
            sw(int(w / 2), int(h * 0.4), 90, 220)  # mostly down: a scroll, not a swipe
            check(f'{dev} {size}', 'a mostly-down drag is a scroll, not 认识', state() == s0, state())
            end = pg.evaluate("() => { const b = document.querySelector('.rtop a'); const r = b.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
            sw(int(end[0]), int(end[1]), 160)
            check(f'{dev} {size}', 'a swipe that starts on a link (结束) is left to the link', state() == s0, state())
            x = max(12, int(box[0] / 2)) if box[0] > 40 else 24  # beside the card where there is room, else near its edge
            tgt = sw(x, int(h / 2), 160)
            s1 = state()
            check(f'{dev} {size}', f'swipe right from beside the card ({tgt}) is 认识: the answer shows', s1['back'] and s1['rates'] == ['again', 'good'], s1)
            tgt = sw(int(w / 2), h - 24, 160)  # below the card, near the bottom of the screen
            s2 = state()
            check(f'{dev} {size}', f'on the answer, swipe right from below the card ({tgt}) is 没错，下一个', s2['front'] and s2['foot'] != s1['foot'], [s1['foot'], s2['foot']])
            tgt = sw(w - (max(12, int((w - box[1]) / 2)) if w - box[1] > 40 else 24), int(h / 2), -160)
            s3 = state()
            check(f'{dev} {size}', f'swipe left from the other side ({tgt}) is 不认识', s3['back'] and s3['rates'] == ['again'], s3)
            btn = pg.evaluate("() => { const b = document.querySelector('[data-rate]'); const r = b.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
            tgt = sw(int(btn[0]) - 60 if btn[0] > w / 2 else int(btn[0]), int(btn[1]), 160)
            s4 = state()
            check(f'{dev} {size}', f'a swipe that starts on an answer button ({tgt}) counts: on a phone the thumb rests there', s4['foot'] != s3['foot'] and not s4['back'], [s3['foot'], s4['foot']])
            # the vocabulary test: the buttons say ← 不认识 and 认识 →, and the swipe does what they say
            pg.goto(BASE + f'/?swipe={size}-t#/vocab/test', wait_until='networkidle'); pg.wait_for_selector('.vtest', timeout=8000)
            t0 = state()['foot']; sw(24, int(h / 2), 160); t1 = state()['foot']; sw(w // 2, h - 24, -160); t2 = state()['foot']
            check(f'{dev} {size}', 'vocabulary test: swipe right, then left, answers two words', t0.startswith('1 /') and t1.startswith('2 /') and t2.startswith('3 /'), [t0, t1, t2])
            pg.goto(BASE + f'/?swipe={size}-u#/cards', wait_until='networkidle'); settle(pg)
            before = pg.url; sw(w // 2, int(h / 2), 160)
            check(f'{dev} {size}', 'away from the card pages a swipe does nothing', pg.url == before and pg.evaluate("() => !document.body.classList.contains('reviewing')"), pg.url)
            check(f'{dev} {size}', 'no script errors', not errors, errors[:3])
            ctx.close()
    finally:
        browser.close()


# 按时间打包 (r28): today's plan in its groups, as the page draws them
PLAN_JS = r"""() => {
  const s = document.querySelector('#view .today-plan'); if (!s) return null;
  const sum = s.querySelector('.tp-extra > summary'), head = s.querySelector('.tp-head .muted.small'), over = s.querySelector('.tp-over');
  return { must: s.querySelectorAll(':scope > .plist .prow').length, extra: s.querySelectorAll('.tp-extra .prow').length,
           week: s.querySelectorAll('.tp-week .prow').length, head: head ? head.textContent.trim() : '', open: s.querySelector('.tp-extra') ? s.querySelector('.tp-extra').open : null,
           summaryH: sum ? Math.round(sum.getBoundingClientRect().height) : null, wide: s.scrollWidth - s.clientWidth, over: !!over,
           shown: [...s.querySelectorAll('.tp-extra .prow')].every(r => r.getBoundingClientRect().height > 0) };
}"""


# 今日's plan rows (必做, 还有时间的话, 本周任务), each as it is and once marked done (the one check for this; #241 fixed it): the title block keeps its height and no
# fill, the subtitle stays inside the row, no grey bar anywhere in it (feedback 2026-11-25: 本周任务's row was .week, the
# week-days bar's class, so its spans became 6 px grey bars and 「这周的一套做完了」 fell out of the card)
PLAN_ROWS_JS = """() => { const bad = [], seen = [];
  const fill = el => { const c = getComputedStyle(el).backgroundColor; return c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent'; };
  const one = (r, state) => { const rr = r.getBoundingClientRect(), t = r.querySelector('.t'), b = r.querySelector('.t b'), sub = r.querySelector('.t .tiny');
    const name = (b ? b.textContent : '').trim().slice(0, 10) + ' (' + state + ')'; seen.push(name);
    if (!t || !b) { bad.push(name + ': no title'); return; }
    const tr = t.getBoundingClientRect(), br = b.getBoundingClientRect();
    if (tr.height < br.height - 1 || br.height < 16) bad.push(name + ': title squashed to ' + Math.round(Math.min(tr.height, br.height)) + 'px');
    if (br.top < rr.top - 1 || br.bottom > rr.bottom + 1) bad.push(name + ': title outside the row');
    if (sub && sub.textContent.trim()) { const sr = sub.getBoundingClientRect(); if (sr.bottom > rr.bottom + 1 || sr.height < 12) bad.push(name + ': subtitle outside the row or squashed'); }
    [...r.querySelectorAll('span, b, i')].filter(e => !e.classList.contains('num') && !e.closest('.num') && fill(e)).forEach(e => bad.push(name + ': a filled bar ' + e.className + ' ' + Math.round(e.getBoundingClientRect().width) + 'x' + Math.round(e.getBoundingClientRect().height)));
    if (rr.height < 44) bad.push(name + ': row ' + Math.round(rr.height) + 'px tall'); };
  const folds = [...document.querySelectorAll('#view .today-plan details:not([open])')]; folds.forEach(d => { d.open = true; });  // 还有时间的话 too
  const rows = [...document.querySelectorAll('#view .today-plan .prow')];
  rows.forEach(r => one(r, r.classList.contains('done') ? 'done' : 'to do'));
  rows.filter(r => !r.classList.contains('done')).forEach(r => { r.classList.add('done'); one(r, 'marked done'); r.classList.remove('done'); });
  folds.forEach(d => { d.open = false; });
  return { bad, seen, week: document.querySelectorAll('#view .tp-week .prow').length }; }"""


def progress_run(pw):
    dev = 'progress'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        for size, (w, h) in PROGRESS_SIZES.items():
            for theme in ('light', 'dark'):
                tag = f'{size} {theme}'
                touch = w < 1000
                ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=touch, has_touch=touch, device_scale_factor=2 if touch else 1,
                                          color_scheme=theme, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
                ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['guide']['token'], 'url': BASE}])
                pg = ctx.new_page(); errors = []
                pg.on('pageerror', lambda e: errors.append(str(e)))
                pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_selector('#weekCard', timeout=8000)
                card = pg.evaluate(CARD_JS)
                home = pg.evaluate("fetch('/api/next/home').then(r => r.json())")
                pr, hb = home['stats']['progress'], home['stats']['habit']
                acc = pr['accuracy']['now']
                want = [str(pr['remembered']['now']), str(pr['finished']['now']),
                        f"{acc['rate']}%" if acc['rate'] is not None else (f"{acc['right']}/{acc['total']}" if acc['total'] else '—'), f"{hb['done']}/{hb['goal']}天"]
                check(dev, f'{tag}: 这周进步 sits under the plan, the week chip by the greeting', card and card['below'] and card['chip'] and card['inView'], card)
                # phones (the owner, 2026-11-25): 好句 and 今日一读 one line each, 「AI 生成」 on 今日一读's line, so 今天的计划 and its
                # button are on the first screen; a tap opens 好句 in place, again closes it. iPad and computer: both cards whole
                fold = pg.evaluate(FOLD_JS)
                if w < 760:
                    pg.click('#lcFold'); pg.wait_for_timeout(300); opened = pg.evaluate(FOLD_JS)
                    pg.click('#lcFold'); pg.wait_for_timeout(300); closed = pg.evaluate(FOLD_JS)
                    check(dev, f'{tag}: 好句 and 今日一读 one line each (今日一读 marked AI 生成 on it), the plan and its button on the first screen; 好句 opens and closes in place',
                          fold['lineH'] <= 70 and fold['newsH'] <= 64 and fold['newsAI'] and fold['planInView'] and not fold['say'] and opened['say'] and not closed['say'], (fold, opened['say'], closed['say']))
                else:
                    check(dev, f'{tag}: 好句 and 今日一读 shown whole (no fold on a wide screen)', fold['say'] and not fold['foldShown'] and fold['newsH'] > 70, fold)
                top = pg.evaluate(TOP_JS)
                check(dev, f'{tag}: 今日 runs 好句, 今日一读, the plan, 这周进步 from the top (the plan first on a phone held sideways), nothing cut off or wider than the screen',
                      top['order'] == (['plan', 'lineCard', 'news', 'week'] if h < 500 else ['lineCard', 'news', 'plan', 'week']) and not top['clipped'] and top['wide'] <= 0 and (not touch or top['small'] == []), top)
                nc = pg.text_content('#view .news-card') or ''
                check(dev, f'{tag}: the card is 今日一读, marked AI 生成, never an old 今日热点', '今日一读' in nc and 'AI 生成' in nc and '旧热点' not in nc, nc[:80])
                # the plan's rows, 本周任务 included (an exam learner has one): nothing squashed, filled or out of its row
                ec = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=touch, has_touch=touch, device_scale_factor=2 if touch else 1,
                                         color_scheme=theme, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
                ec.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['exam']['token'], 'url': BASE}])
                ex = ec.new_page(); ex.goto(BASE + '/#/', wait_until='networkidle'); settle(ex); ex.wait_for_selector('#view .today-plan .prow', timeout=8000)
                rows = ex.evaluate(PLAN_ROWS_JS)
                check(dev, f'{tag}: 今日 plan rows, 本周任务 too, to do and done: title and subtitle inside the row, no grey bars', rows['week'] >= 1 and not rows['bad'], rows)
                ec.close()
                check(dev, f'{tag}: its four numbers are the learner\'s own (as the server counts them)', card and card['values'] == want, (card and card['values'], want))
                path = home['path']; plan = pg.evaluate(PLAN_JS)
                grp = {g: [x for x in path['steps'] if x.get('group', 'must') == g] for g in ('must', 'extra', 'week')}
                head = (f"约 {path['must_minutes']} 分钟" if not path['done'] else '都做完了' if path['done'] >= path['total'] else f"还要约 {path['left_minutes']} 分钟")
                check(dev, f'{tag}: the plan shows 必做 (counted), 还有时间的话 folded and 本周任务 as the server packs them, its title the real minutes of 必做',
                      plan and (plan['must'], plan['extra'], plan['week']) == (path['total'], len(grp['extra']), len(grp['week'])) and head in plan['head']
                      and plan['wide'] <= 0 and (not grp['extra'] or (plan['summaryH'] >= 44 and plan['open'] == (path['done'] >= path['total']))), (plan, head))
                if grp['extra'] and not plan['open']:
                    pg.click('#view .tp-extra > summary'); pg.wait_for_timeout(150)
                    check(dev, f'{tag}: 还有时间的话 opens with a tap and its rows show', pg.evaluate(PLAN_JS)['shown'] and pg.evaluate(PLAN_JS)['open'], pg.evaluate(PLAN_JS))
                    if size == 'phone-390':
                        pg.screenshot(path=str(OUT / f'progress-plan-extra-{theme}.png'))
                    pg.click('#view .tp-extra > summary'); pg.wait_for_timeout(100)
                check(dev, f'{tag}: four numbers in one row, nothing cut off or wrapped', card and card['tiles'] == 4 and card['oneRow'] and not card['clipped'] and not card['wrapped'],
                      card and (card['oneRow'], card['clipped'], card['wrapped']))
                check(dev, f'{tag}: no sideways scrolling; a surface of its own; text contrast at least 4.5:1',
                      card and card['wide'] <= 0 and card['surface'] and card['contrast'] >= 4.5, card and (card['wide'], card['surface'], round(card['contrast'], 2)))
                if size in ('phone-390', 'phone-360'):
                    check(dev, f'{tag}: the plan\'s next-step button is still on the first screen', card['goBottom'] is not None and card['goBottom'] <= card['H'], (card['goBottom'], card['H']))
                pg.screenshot(path=str(OUT / f'progress-today-{size}-{theme}.png'))
                # the details: the same numbers, the words behind them, closes with Escape (or a tap on 关闭)
                pg.click('#weekCard'); pg.wait_for_selector('.wk-sheet', timeout=8000); pg.wait_for_timeout(250)
                sheet = pg.evaluate("""() => { const s = document.querySelector('.wk-sheet'), c = document.getElementById('sheetCard');
                  return { nums: [...s.querySelectorAll('.wk-num')].map(n => n.textContent.trim()), words: s.querySelectorAll('.wk-words .pill').length,
                           days: s.querySelectorAll('.wk-days > span').length, wide: c.scrollWidth - c.clientWidth }; }""")
                check(dev, f'{tag}: the details show the same numbers and the words remembered',
                      sheet['nums'][:3] == want[:3] and sheet['words'] == min(40, pr['remembered']['now']) and sheet['days'] == 7 and sheet['wide'] <= 0, (sheet, want))
                if size == 'phone-390' and theme == 'light':
                    pg.screenshot(path=str(OUT / 'progress-sheet.png'))
                pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
                check(dev, f'{tag}: the details close', pg.evaluate("document.getElementById('sheet').hidden"))
                # the three lines after a text, each going on to its work
                go(pg, f'#/m/{PID}/output'); pg.wait_for_selector('#ans', timeout=8000)
                pg.fill('#ans', 'I usually wear headphones on the train, so the noise is less.'); pg.click('#go')
                pg.wait_for_selector('#finSum .fin-row', timeout=15000); pg.wait_for_timeout(250)
                fin = pg.evaluate("""() => { const b = document.getElementById('finSum'), c = document.getElementById('finCard');
                  return { rows: [...b.querySelectorAll('.fin-row')].map(r => [r.querySelector('.k').textContent, r.getAttribute('href') || '']),
                           inside: b.getBoundingClientRect().right <= c.getBoundingClientRect().right + 1, wide: document.scrollingElement.scrollWidth - innerWidth,
                           share: !!document.getElementById('shareDone') }; }""")
                check(dev, f'{tag}: 这篇完成了 has three lines (expressions, words, a grammar point), each with where to go',
                      [r[0] for r in fin['rows']] == ['表达', '新词', '语法'] and fin['rows'][2][1] == '#/graph/agreement-head' and fin['rows'][1][1] == '#/cards/word'
                      and fin['inside'] and fin['wide'] <= 0 and fin['share'], fin)
                pg.evaluate("document.getElementById('finCard').scrollIntoView({ block: 'center' })"); pg.wait_for_timeout(200)
                pg.screenshot(path=str(OUT / f'progress-finish-{size}-{theme}.png'))
                if theme == 'light':
                    go(pg, '#/me'); pg.wait_for_selector('#meMail', timeout=6000)
                    row = pg.inner_text('#meMail')
                    pg.click('#meMail'); pg.wait_for_timeout(250)
                    title = pg.evaluate("(document.getElementById('sheetTitle') || {}).textContent")
                    pg.keyboard.press('Escape')
                    check(dev, f'{tag}: 我的 → 每周进度邮件 says how it stands and opens its switch', '每周进度邮件' in row and '绑定邮箱' in row and title == '每周进度邮件', (row, title))
                check(dev, f'{tag}: no page errors', not errors, errors[:3])
                ctx.close()
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True)
        ctx.add_init_script(FAKE_TTS)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['guide']['token'], 'url': BASE}])
        pg = ctx.new_page(); pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_selector('#lineCard', timeout=8000)
        line = pg.evaluate("fetch('/api/next/home').then(r => r.json()).then(h => h.line)")
        voiced = []  # the server voice (tts_service) says it now; the browser voice when that is off
        pg.on('request', lambda r: voiced.append(json.loads(r.post_data or '{}').get('text')) if '/api/next/tts' in r.url else None)
        pg.click('#lcFold'); pg.wait_for_timeout(250)  # one line on a phone: open it first
        pg.click('#lcSay'); pg.wait_for_timeout(600)
        said = pg.evaluate('window.__said || []') + voiced
        mark = pg.evaluate("() => { const m = document.querySelector('#lineCard .lc-acts .ai-voice'), b = document.getElementById('lcSay'); "
                           "return m && [m.textContent.trim(), Math.abs(m.getBoundingClientRect().top + m.offsetHeight / 2 - b.getBoundingClientRect().top - b.offsetHeight / 2) < 8, !!m.title]; }")
        check(dev, '好句: 「AI 朗读」 right by 听一遍, on its row, with what it means on hover', mark == ['AI 朗读', True, True], mark)
        pg.click('#lcShadow'); pg.wait_for_timeout(200)
        panel = pg.evaluate("() => { const p = document.getElementById('lcPanel'); return [p.hidden, !!p.querySelector('#lsRec'), document.getElementById('lsBack').disabled, document.getElementById('lcShadow').getAttribute('aria-expanded')]; }")
        pg.click('#lcShadow'); pg.wait_for_timeout(150)
        closed = pg.evaluate("document.getElementById('lcPanel').hidden")
        check(dev, '好句: 听一遍 says the line (verse without its line marks), 跟读 opens a recorder and closes again',
              (said[-1:] == [line['say']] or line['kind'] == 'text') and panel == [False, True, True, 'true'] and closed, (said[-1:], line['say'], panel, closed))
        pg.click('#lcKeep'); pg.wait_for_timeout(700)
        cards = pg.evaluate("fetch('/api/next/cards?q=&page=1&f=').then(r => r.json())")
        kept = line['say'] if line['kind'] == 'quote' else line['expression']
        check(dev, '好句: 收藏 puts it into the word book, for review', any(x.get('text') == kept for x in cards.get('items', [])), kept)
        # a sentence from a 语流 text: its expression marked, its meaning, where it comes from, a link to the text
        m = pg.evaluate(f"fetch('/api/next/material?id={PID}').then(r => r.json())")
        ex = m['expressions'][0]; k = next(i for i, x in enumerate(m['sentences']) if ex['text'].lower() in x.lower())
        fake = {'kind': 'text', 'id': f'm:{PID}:{k}', 'label': '语流文章', 'en': m['sentences'][k], 'say': m['sentences'][k], 'zh': f"「{ex['text']}」：{ex['meaning']}",
                'note': ex.get('note', ''), 'expression': ex['text'], 'meaning': ex['meaning'], 'source': f"出自《{m['title']}》 · B2", 'pack': PID, 'i': k,
                'title': m['title'], 'level': 'B2', 'audio': 0, 'href': f'#/m/{PID}/read', 'day': '2026-11-25'}
        pg.route('**/api/next/home*', lambda route: (lambda r: route.fulfill(response=r, json={**r.json(), 'line': fake}))(route.fetch()))
        pg.evaluate("() => { localStorage.removeItem('flow-snap'); }"); pg.reload(wait_until='networkidle'); settle(pg); pg.wait_for_selector('#lcFold', timeout=8000)
        pg.click('#lcFold'); pg.wait_for_selector('#lineCard .lc-en b', timeout=8000)  # another line: one line again until opened
        shown = pg.evaluate("() => { const c = document.getElementById('lineCard'); return [c.querySelector('.lc-en b').textContent, c.querySelector('.lc-src a').getAttribute('href'), c.querySelector('.pill').textContent]; }")
        check(dev, '好句 from a 语流 text: its expression marked, a link to the text, labelled as 语流文章', shown == [ex['text'], f'#/m/{PID}/read', '语流文章'], shown)
        pg.screenshot(path=str(OUT / 'progress-line-text.png'))
        ctx.close()
        # the link in the mail opens without signing in, asks before it turns anything off, and says when a link is wrong
        ctx = browser.new_context(viewport={'width': 360, 'height': 780}, is_mobile=True, has_touch=True, locale='zh-CN', bypass_csp=True)
        pg = ctx.new_page(); pg.goto(BASE + '/#/weekly-off/not-a-real-link-0123456789', wait_until='networkidle'); settle(pg)
        first = (pg.evaluate('location.hash'), pg.inner_text('#view h1'))
        pg.click('#offGo'); pg.wait_for_timeout(600)
        err = pg.inner_text('#view .err')
        check(dev, 'the unsubscribe link opens signed out, asks first, and explains a link that no longer works',
              first == ('#/weekly-off/not-a-real-link-0123456789', '退订每周进度邮件') and '失效' in err, (first, err))
        ctx.close()
    finally:
        browser.close()


# The area that takes a tap around an element: true when points 20 px out from its centre, on all four sides, land on it
# (44 x 44 at least, even where the text itself is smaller: .hit44 in 70-input-devices.css).
TAP44_JS = """sel => { const el = document.querySelector(sel); if (!el) return null; el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const hit = (dx, dy) => { const t = document.elementFromPoint(x + dx, y + dy); return !!t && (t === el || el.contains(t)); };
  return { ok: [[-20, 0], [20, 0], [0, -20], [0, 20]].every(([a, b]) => hit(a, b)), w: Math.round(r.width), h: Math.round(r.height) }; }"""


SIDE_STATE = """() => ({ claims: [...document.querySelectorAll('.choice [data-claim]')].map(b => b.dataset.claim),
  keys: [...document.querySelectorAll('.choice [data-claim] small')].map(s => s.textContent),
  rates: [...document.querySelectorAll('[data-rate]')].map(b => b.dataset.rate), back: !!document.querySelector('.open-card'),
  foot: (document.querySelector('.rfoot') || {}).textContent || '', tip: !!document.getElementById('knowTip') })"""


def review_side_run(pw):
    """「认识」放在 (a trial student and the owner, 2026-11-25): on the right by default, as in most word apps; 我的 → 设置
    moves it to the left. The buttons, the keys (1 2 3 and ← → by place), the swipe and the vocabulary test follow it; one
    who reviewed on this device before sees once that it moved. 这次什么时候复习: a time today or tomorrow is the next
    reminder, then the daily hour again."""
    dev = 'review-side'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        st = lambda: pg.evaluate(SIDE_STATE)
        pg.goto(BASE + '/#/cards', wait_until='load'); settle(pg)
        pg.evaluate("localStorage.setItem('flow-next-review-cache', JSON.stringify({at: Date.now(), q: {items: []}}))")  # this device reviewed before
        go(pg, '#/review'); pg.wait_for_selector('[data-claim]', timeout=8000); pg.wait_for_timeout(200)
        s = st()
        check(dev, 'by default 不认识 / 模糊 / 认识 from left to right, keys 1 2 3 by place',
              s['claims'] == ['forgot', 'fuzzy', 'know'] and s['keys'] == ['1', '2', '3'], s)
        tip = pg.text_content('#knowTip') if s['tip'] else ''
        check(dev, 'one who reviewed before is told once that 认识 moved, and where to move it back', '「认识」换到右边了，想换回去：我的 → 设置' in tip, tip)
        pg.click('#knowTipOk'); pg.wait_for_timeout(100)
        gone = not st()['tip']
        go(pg, '#/cards'); go(pg, '#/review'); pg.wait_for_selector('[data-claim]', timeout=8000)
        check(dev, '知道了 puts the tip away for good', gone and not st()['tip'], st())
        pg.keyboard.press('3'); pg.wait_for_timeout(250); s = st()
        check(dev, 'key 3 (the right button) is 认识; on the answer 记错了 left, 没错 right', s['back'] and s['rates'] == ['again', 'good'], s)
        f0 = s['foot']; pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(450); s = st()
        check(dev, '→ is the right button there: 没错，下一个', not s['back'] and s['claims'] and s['foot'] != f0, [f0, s])
        pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(250); s = st()
        check(dev, '← on the card is the left button: 不认识', s['back'] and s['rates'] == ['again'], s)
        pg.keyboard.press('Enter'); pg.wait_for_timeout(450)
        # 我的 → 设置 → 「认识」放在 → 左边
        go(pg, '#/me'); pg.click('#meKnow'); pg.wait_for_selector('#sheetCard [data-know="left"]'); pg.click('#sheetCard [data-know="left"]'); pg.wait_for_timeout(150)
        label = pg.text_content('#meKnowV') or ''
        pg.click('#sheetCard [data-close]'); pg.wait_for_timeout(150)
        go(pg, '#/review'); pg.wait_for_selector('[data-claim]', timeout=8000); s = st()
        check(dev, '我的 → 设置: 「认识」放在左边, and the card says 认识 / 模糊 / 不认识', label.strip() == '左边' and s['claims'] == ['know', 'fuzzy', 'forgot'] and not s['tip'], (label, s))
        pg.keyboard.press('1'); pg.wait_for_timeout(250); s = st()
        check(dev, 'left: key 1 is 认识, and on the answer 没错 left, 记错了 right', s['back'] and s['rates'] == ['good', 'again'], s)
        f0 = s['foot']; pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(450); s = st()
        check(dev, 'left: ← is 没错，下一个', not s['back'] and s['foot'] != f0, [f0, s])
        go(pg, '#/vocab/test'); pg.wait_for_selector('.vtest', timeout=8000)
        btns = pg.evaluate("[...document.querySelectorAll('.vtest [data-a]')].map(b => b.dataset.a + ':' + b.textContent)")
        t0 = pg.text_content('.bar-progress') or ''
        pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(300)
        check(dev, 'left: the vocabulary test says 认识 ← and 不认识 →', btns == ['1:认识←', '0:不认识→'], btns)
        # 这次什么时候复习: the next reminder at a time picked today or tomorrow
        go(pg, '#/vocab/plan'); pg.click('#onceBtn'); pg.wait_for_selector('#oncePicks [data-at]', timeout=5000)
        pick = pg.get_attribute('#oncePicks [data-at]', 'data-at'); name = pg.text_content('#oncePicks [data-at]')
        pg.click('#oncePicks [data-at]'); pg.wait_for_selector('#onceOk', timeout=5000)
        ok = pg.text_content('#onceOk') or ''; cal = pg.get_attribute('#onceOk a', 'href') or ''
        r = pg.evaluate("fetch('/api/next/vocab').then(r => r.json()).then(o => o.reminder)")
        check(dev, f'这次什么时候复习: 「{name}」 is the next reminder, said so, with a calendar event for that time',
              r['once'] == float(pick) and ok.startswith('好，') and '提醒你复习' in ok and cal.endswith(f'at={int(float(pick))}'), (pick, r, ok, cal))
        pg.click('#sheetCard [data-close]'); pg.wait_for_timeout(150)
        check(dev, 'the plan page says when the next reminder is', (pg.text_content('#onceNow') or '').startswith('下一次：'), pg.text_content('#onceNow'))
        ics = pg.evaluate("u => fetch(u).then(r => r.text())", cal)
        check(dev, 'the calendar file is one event, not a daily one', 'BEGIN:VEVENT' in ics and 'RRULE' not in ics, ics[:200])
        pg.click('#onceBtn'); pg.wait_for_selector('#onceOff', timeout=5000); pg.click('#onceOff'); pg.wait_for_timeout(300)
        r = pg.evaluate("fetch('/api/next/vocab').then(r => r.json()).then(o => o.reminder)")
        check(dev, '取消这次: back to every day at the hour', r['once'] is None, r)
        check(dev, 'no script errors (computer)', not errs, errs[:3])
        ctx.close()
        # in an app (iOS, Android, desktop; FlowApp before the page): the reminder goes to its notifications, said for its device
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
        ctx.add_init_script("window.__synced = []; window.__perm = 'undetermined'; window.FlowApp = { v: 1, platform: 'macos', has: k => k === 'notify', notify: { ask: () => { window.__perm = 'granted'; return Promise.resolve(true); }, sync: r => { window.__synced.push(r); return Promise.resolve({}); }, permission: () => Promise.resolve(window.__perm), settings: () => { window.__settings = 1; return Promise.resolve(); } } };")  # every call a Promise, as the real apps (native-bridge.md 2)
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/#/vocab/plan', wait_until='load'); settle(pg); pg.wait_for_selector('#rApp', timeout=5000)
        note = pg.text_content('#rAppNote') or ''
        pg.click('#rApp'); pg.wait_for_timeout(500)
        synced = pg.evaluate('window.__synced')
        check(dev, 'in the desktop app on a Mac: 到点用 App 通知提醒 says 这台 Mac, and hands the reminder (with the forecast) to the app',
              note.startswith('在这台 Mac 上') and synced and synced[-1].get('hour') == 20 and isinstance(synced[-1].get('forecast'), list), (note, synced[-1:]))
        on = pg.text_content('#rAppOn') if pg.query_selector('#rAppOn') else ''
        pg.click('#rAppSet') if pg.query_selector('#rAppSet') else None
        check(dev, 'once on, the row says so, and 通知设置 opens the system settings (no 关闭 where the app cannot turn it off)',
              on.startswith('已开启：在这台 Mac 上') and not pg.query_selector('#rAppOff') and pg.evaluate('window.__settings') == 1, on)
        pg.click('#onceBtn'); pg.wait_for_selector('#oncePicks [data-at]', timeout=5000); pick = pg.get_attribute('#oncePicks [data-at]', 'data-at')
        pg.click('#oncePicks [data-at]'); pg.wait_for_selector('#onceOk', timeout=5000)
        synced = pg.evaluate('window.__synced')
        check(dev, 'in the app: a time picked for the next review goes to its notifications too', synced and synced[-1].get('once') == float(pick), synced[-1:])
        pg.click('#sheetCard [data-close]'); pg.wait_for_timeout(200); pg.click('#onceBtn')  # opened again: 取消这次 is there now
        pg.wait_for_selector('#sheetCard #onceOff', timeout=5000); pg.click('#sheetCard #onceOff'); pg.wait_for_timeout(300)
        check(dev, 'in the app: 取消这次 too', pg.evaluate('window.__synced')[-1].get('once') is None, pg.evaluate('window.__synced')[-1:])
        check(dev, 'no script errors (app)', not errs, errs[:3])
        ctx.close()
        # the Android app: on already (permission granted), and it can turn its notifications off itself (notify.off)
        ctx = browser.new_context(viewport={'width': 412, 'height': 900}, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
        ctx.add_init_script("window.__perm = 'granted'; window.FlowApp = { v: 1, platform: 'android', has: k => k === 'notify', notify: { ask: () => { window.__perm = 'granted'; return Promise.resolve(true); }, sync: () => Promise.resolve({ exact: false }), permission: () => Promise.resolve(window.__perm), off: () => { window.__perm = 'undetermined'; window.__off = 1; return Promise.resolve(); }, settings: () => Promise.resolve() } };")
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/#/vocab/plan', wait_until='load'); settle(pg); pg.wait_for_selector('#rAppOn', timeout=5000)  # once the app has answered
        on = pg.text_content('#rAppOn') if pg.query_selector('#rAppOn') else ''
        pg.click('#rAppOff'); pg.wait_for_timeout(300)
        pg.click('#rApp'); pg.wait_for_selector('#rAppOn', timeout=5000)  # on again: ask() true turns it back on
        check(dev, 'Android app: 已开启：在这台手机上…, 关闭 turns it off, and the button turns it on again',
              on.startswith('已开启：在这台手机上') and pg.evaluate('window.__off') == 1 and pg.query_selector('#rAppOn') is not None, on)
        check(dev, 'no script errors (Android app)', not errs, errs[:3])
        ctx.close()
        # the iOS app on a narrow iPhone: 「已开启：在这台 iPhone 上…」 wraps before 关闭, which stays at the end of its line (语流 C1)
        for w in (375, 320):
            ctx = browser.new_context(viewport={'width': w, 'height': 667}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
            ctx.add_init_script("window.FlowApp = { v: 1, platform: 'ios', has: k => k === 'notify', notify: { ask: () => Promise.resolve(true), sync: () => Promise.resolve({}), permission: () => Promise.resolve('granted'), off: () => Promise.resolve() } };")
            pg = ctx.new_page()
            pg.goto(BASE + '/#/vocab/plan', wait_until='load'); settle(pg); pg.wait_for_selector('#rAppOn', timeout=5000)
            box = pg.evaluate("() => { const t = document.getElementById('rAppOn').getBoundingClientRect(), o = document.getElementById('rAppOff').getBoundingClientRect(); "
                              "return { textTop: Math.round(t.top), textBottom: Math.round(t.bottom), textRight: Math.round(t.right), offTop: Math.round(o.top), offBottom: Math.round(o.bottom), offLeft: Math.round(o.left), vw: innerWidth, offRight: Math.round(o.right) }; }")
            check(dev, f'iOS app at {w}px: 关闭 stays beside 「已开启：在这台 iPhone 上…」, not on a line of its own',
                  box['offTop'] < box['textBottom'] and box['offBottom'] > box['textTop'] and box['offLeft'] >= box['textRight'] and box['offRight'] <= box['vw'], box)
            ctx.close()
        # 语流 B8's audit: 知道了 on one line on a phone; 复习 and 测词汇量 name themselves to a screen reader (a hidden h1);
        # 词汇辨析's round is one screen like 复习, 怎么区分 folded from the second question; a word page with no words yet
        # shows how to start, not counts of 0, a search box and filters
        for w in (375, 390):
            ctx = browser.new_context(viewport={'width': w, 'height': 667 if w == 375 else 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
            ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
            pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
            pg.goto(BASE + '/#/cards', wait_until='load'); settle(pg)
            pg.evaluate("localStorage.setItem('flow-next-review-cache', JSON.stringify({at: Date.now(), q: {items: []}})); localStorage.removeItem('flow-know-tip')")
            go(pg, '#/review'); pg.wait_for_selector('#knowTipOk', timeout=8000)
            ok = pg.evaluate("(() => { const b = document.getElementById('knowTipOk'), g = document.createRange(); g.selectNodeContents(b); return { lines: new Set([...g.getClientRects()].map(x => Math.round(x.top))).size, h: Math.round(b.getBoundingClientRect().height), text: b.textContent }; })()")
            check(dev, f'{w}px: 知道了 on one line, not 知道 / 了', ok['lines'] <= 1, ok)
            h1 = pg.evaluate("[...document.querySelectorAll('main h1')].map(h => h.textContent)")
            go(pg, '#/vocab/test'); pg.wait_for_selector('.vtest [data-a]', timeout=8000)
            h1t = pg.evaluate("[...document.querySelectorAll('main h1')].map(h => h.textContent)")
            if w == 375:
                check(dev, '复习 and 测词汇量 have a heading for a screen reader: 复习单词, 测词汇量', h1 == ['复习单词'] and h1t == ['测词汇量'], [h1, h1t])
            ctx.close()
        ctx = browser.new_context(viewport={'width': 375, 'height': 667}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/#/words/confuse', wait_until='load'); settle(pg)
        grp = pg.evaluate("(() => { const a = document.querySelector('#view a.btn[href^=\"#/words/confuse/\"]'); return a ? a.getAttribute('href') : null; })()")
        if grp:
            go(pg, grp); pg.wait_for_selector('#mixQ .ans', timeout=8000); pg.wait_for_timeout(300)
            cf = lambda: pg.evaluate("({ page: document.scrollingElement.scrollHeight, H: innerHeight, tabs: !!document.querySelector('.tabs') && getComputedStyle(document.querySelector('.tabs')).display !== 'none', how: document.getElementById('cfHow').open, last: Math.round(Math.max(...[...document.querySelectorAll('#mixQ .ans')].map(b => b.getBoundingClientRect().bottom))) })")
            a1 = cf()
            pg.click('#mixQ .ans'); pg.wait_for_selector('#mixNext', timeout=4000); pg.click('#mixNext'); pg.wait_for_selector('#mixQ .ans:not([disabled])', timeout=4000); pg.wait_for_timeout(300)
            a2 = cf()
            check(dev, '词汇辨析 on a phone: no tabs while answering, 怎么区分 open for the first question and folded from the second',
                  not a1['tabs'] and a1['how'] and not a2['how'], [a1, a2])
            check(dev, '词汇辨析 at 375×667 from the second question: one screen, the last answer on it', a2['page'] <= a2['H'] and a2['last'] <= a2['H'], a2)
            pg.click('#cfHow summary'); pg.wait_for_timeout(150)
            check(dev, '词汇辨析: a tap on 怎么区分 opens it again', pg.evaluate("document.getElementById('cfHow').open"), None)
        else:
            check(dev, '词汇辨析: a group to practise', False, 'no group on #/words/confuse')
        check(dev, 'no script errors (B8 audit pages)', not errs, errs[:3])
        ctx.close()
        ctx = browser.new_context(viewport={'width': 375, 'height': 667}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['nowords']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/#/cards', wait_until='load'); settle(pg)
        e = pg.evaluate("({ start: !!document.querySelector('#view a[href=\"#/vocab/plan\"].btn'), stats: !!document.getElementById('vStats'), search: !!document.getElementById('sf'), chips: !!document.querySelector('#view [data-f]'), count: /共 0 个/.test(document.getElementById('view').textContent) })")
        check(dev, 'no words yet: the word page shows how to start, without counts of 0, the search box or the filters',
              e['start'] and not e['stats'] and not e['search'] and not e['chips'] and not e['count'], e)
        check(dev, 'no script errors (no words yet)', not errs, errs[:3])
        ctx.close()
        # a search that finds nothing says what was searched and offers a way out (语流 B9): 清除搜索, and with a filter on, 在全部里找
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/#/cards', wait_until='load'); settle(pg)
        n0 = pg.evaluate("document.querySelectorAll('#listSlot [data-card]').length")
        pg.fill('#sf input', 'zzqx'); pg.press('#sf input', 'Enter'); pg.wait_for_selector('#sfClear', timeout=5000)
        msg = pg.text_content('#listSlot .empty p')
        pg.click('#sfClear'); pg.wait_for_selector('#listSlot [data-card]', timeout=5000)
        back = [pg.input_value('#sf input'), pg.evaluate("document.querySelectorAll('#listSlot [data-card]').length")]
        check(dev, '单词 search with no result: 没找到「zzqx」 and 清除搜索 brings the whole list back', '没找到「zzqx」' in msg and back == ['', n0] and n0 > 0, [msg, back, n0])
        pg.click('[data-f="mistake"]'); pg.wait_for_timeout(300)
        pg.fill('#sf input', 'zzqx'); pg.press('#sf input', 'Enter'); pg.wait_for_selector('#sfAll', timeout=5000)
        msg2 = pg.text_content('#listSlot .empty p')
        pg.click('#sfAll'); pg.wait_for_timeout(400)
        all_on = pg.get_attribute('[data-f=""]', 'aria-pressed')
        check(dev, 'with a filter on: says where it looked (只在「错题」里找了); 在全部里找 searches all of them',
              '只在「错题」里找了' in msg2 and all_on == 'true' and '只在' not in (pg.text_content('#listSlot .empty p') or ''), [msg2, all_on])
        check(dev, 'no script errors (search)', not errs, errs[:3])
        ctx.close()
        # a phone: the swipe follows the side
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['side']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        st = lambda: pg.evaluate(SIDE_STATE)
        pg.goto(BASE + '/#/review', wait_until='load'); pg.wait_for_selector('[data-claim]', timeout=8000); pg.wait_for_timeout(700)
        touch_swipe(pg, '.review', 160); pg.wait_for_timeout(400); s = st()
        check(dev, 'phone, by default: swipe right is 认识', s['back'] and s['rates'] == ['again', 'good'], s)
        f0 = s['foot']; touch_swipe(pg, '.review', 160); pg.wait_for_timeout(500); s = st()
        check(dev, 'phone: swipe right again is 没错，下一个', not s['back'] and s['foot'] != f0, [f0, s])
        touch_swipe(pg, '.review', -160); pg.wait_for_timeout(400); s = st()
        check(dev, 'phone: swipe left is 不认识', s['back'] and s['rates'] == ['again'], s)
        pg.evaluate("localStorage.setItem('flow-know-side', 'left')")
        pg.reload(wait_until='load'); pg.wait_for_selector('[data-claim]', timeout=8000); pg.wait_for_timeout(500)
        touch_swipe(pg, '.review', -160); pg.wait_for_timeout(400); s = st()
        check(dev, 'phone, 「认识」放在左边: swipe left is 认识', s['back'] and s['rates'] == ['good', 'again'], s)
        f0 = s['foot']; touch_swipe(pg, '.review', -160); pg.wait_for_timeout(500); s = st()
        check(dev, 'phone, left: swipe left again is 没错，下一个', not s['back'] and s['foot'] != f0, [f0, s])
        check(dev, 'no script errors (phone)', not errs, errs[:3])
        ctx.close()
    finally:
        browser.close()


# 复习 and 测词汇量 on a phone are one screen: the card below the top bar, the answers at the bottom where the thumb is,
# nothing to scroll. On an iPhone's home-screen app the back button (r30) and the status bar / Dynamic Island made the top
# bar taller and the page ran past the screen (the owner, 2026-11-25). Sizes: an iPhone SE (its status bar 20px in the
# home-screen app), an iPhone 14 (notch 47, home bar 34) and an iPhone 15 Pro (Dynamic Island 59, home bar 34), each in
# Safari and from the home screen.
ONE_SCREEN_JS = """() => { const H = innerHeight, m = document.querySelector('main').getBoundingClientRect(), bar = document.getElementById('bar').getBoundingClientRect();
  const sab = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sab')) || 0;
  const answers = [...document.querySelectorAll('.review .choice button, #mixQ .ans')].map(b => Math.round(b.getBoundingClientRect().bottom));
  const last = (document.querySelector('.review') || document.querySelector('#mixQ .q')).lastElementChild.getBoundingClientRect();
  return { H, page: document.scrollingElement.scrollHeight, bar: Math.round(bar.height), barH: getComputedStyle(document.documentElement).getPropertyValue('--bar-h').trim(),
           mainBottom: Math.round(m.bottom), answers, lastBottom: Math.round(last.bottom), sab, tip: !!document.getElementById('knowTip') }; }"""


def one_screen_run(pw):
    dev = 'one-screen'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    tok = CFG['learners']['screen']['token']
    sizes = {'iphone-se': (375, 667, 20, 0), 'iphone-14': (390, 844, 47, 34), 'iphone-15-pro': HOME_SIZES['iphone-15-pro'][:4]}
    try:
        for size, (w, h, top, bottom) in sizes.items():
            for home in (False, True):
                where = f"{size} {'home-screen app' if home else 'Safari'}"
                ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=3, locale='zh-CN',
                                          bypass_csp=True, reduced_motion='reduce')
                if home:
                    ctx.add_init_script(HOME_INIT % json.dumps([top, bottom, 0]))
                ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
                pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
                pg.goto(BASE + '/#/cards', wait_until='load'); settle(pg)
                # this device reviewed before, so the one-time 「认识」换到右边了 tip shows too: the tallest the card gets
                pg.evaluate("localStorage.setItem('flow-next-review-cache', JSON.stringify({at: Date.now(), q: {items: []}}))")
                for page, wait in (('#/review', '[data-claim]'), ('#/vocab/test', '.vtest [data-a]')):
                    go(pg, page); pg.wait_for_selector(wait, timeout=8000); pg.wait_for_timeout(400)
                    s = pg.evaluate(ONE_SCREEN_JS)
                    name = '复习卡' if page == '#/review' else '测词汇量'
                    pg.screenshot(path=str(OUT / f"one-screen-{size}-{'home' if home else 'safari'}-{page.strip('#/').replace('/', '_')}.png"))
                    check(dev, f'{where} {name}: one screen, nothing to scroll ({s["page"]} of {s["H"]}px)', s['page'] <= s['H'], s)
                    check(dev, f'{where} {name}: the page fills the screen, the answers at the bottom', abs(s['mainBottom'] - s['H']) <= 1 and min(s['answers'] or [0]) > s['H'] * 0.6, s)
                    check(dev, f'{where} {name}: the answers and the line below them clear the home bar', s['answers'] and max(s['answers'] + [s['lastBottom']]) <= s['H'] - s['sab'], s)
                    if page == '#/review':
                        check(dev, f'{where}: the 「认识」换到右边了 tip is on the card (the tallest it gets)', s['tip'], s)
                    if home:
                        check(dev, f'{where} {name}: --bar-h is the top bar\'s height', s['barH'] == f"{s['bar']}px", s)
                # 词汇辨析's round (语流 B8's audit: 119-213 px past the screen): no tabs, 怎么区分 open for the first question,
                # one line from the second; both questions one screen, the answers at the bottom and clear of the home bar
                go(pg, '#/words/confuse/borrow-lend,make-do'); pg.wait_for_selector('#mixQ .ans', timeout=8000); pg.wait_for_timeout(400)
                for k in (1, 2):
                    if k == 2:
                        pg.click('#mixQ .ans'); pg.wait_for_selector('#mixNext', timeout=4000); pg.click('#mixNext')
                        pg.wait_for_selector('#mixQ .ans:not([disabled])', timeout=4000); pg.wait_for_timeout(400)
                    s = pg.evaluate(ONE_SCREEN_JS)
                    pg.screenshot(path=str(OUT / f"one-screen-{size}-{'home' if home else 'safari'}-confuse-q{k}.png"))
                    check(dev, f'{where} 词汇辨析第 {k} 题: one screen, nothing to scroll ({s["page"]} of {s["H"]}px)', s['page'] <= s['H'], s)
                    check(dev, f'{where} 词汇辨析第 {k} 题: the answers at the bottom, clear of the home bar',
                          abs(s['mainBottom'] - s['H']) <= 1 and s['answers'] and min(s['answers']) > s['H'] * 0.6 and max(s['answers']) <= s['H'] - s['sab'], s)
                check(dev, f'{where}: no script errors', not errs, errs[:3])
                ctx.close()
    finally:
        browser.close()


def backlog_run(pw):
    """Reviews piled up after a break (ux-longterm-audit 1.1, 11, 16, 2026-11-24): no new words today and the word page
    says so; the review page says 「先做 40 个（还有 N 个）」 and, after those 40, offers a place to stop; the small links
    a finger needs (结束, 去读, 去练, 按 B1 挑选 · 调整, 怎么写的) take a tap 44 px around them. r28 section 3: 单词每天
    (a cap in minutes: done at the cap, 继续复习 past it, the new words a day it keeps up with) and a finished book's next."""
    dev = 'backlog'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['pile']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/#/cards', wait_until='networkidle'); settle(pg)
        o = pg.evaluate("fetch('/api/next/vocab').then(r => r.json())")
        note = pg.text_content('#newPaused') if pg.query_selector('#newPaused') else ''
        check(dev, 'reviews piled up (60 > 3 x 10): no new words today, and the word page says why',
              o['new_paused'] and o['due'] >= 60 and note.strip() == '到期的词比较多，今天先复习，新词明天继续。', (o['due'], o['new'], o['new_paused'], note))
        home = pg.evaluate("fetch('/api/next/home').then(r => r.json())")
        step = next((x for x in (home.get('path') or {}).get('steps', []) if x.get('key') == 'review'), {})
        check(dev, "today's word step says new words wait", '新词明天继续' in step.get('sub', ''), step)
        go(pg, '#/review'); pg.wait_for_timeout(300)
        total = o['due'] + o['new']
        foot = pg.text_content('.rfoot') or ''
        check(dev, 'the review page says 先做 40 个（还有 N 个）, not 1 / 40 alone', f'先做 40 个（还有 {total - 40} 个）' in foot and '1 / 40' in foot, foot)
        check(dev, '结束 on the review page takes a tap 44 px around it', (pg.evaluate(TAP44_JS, '.rtop a.link') or {}).get('ok'), pg.evaluate(TAP44_JS, '.rtop a.link'))
        for k in range(60):
            # the next card or the end page, whichever comes: after the 40th answer the end page first asks the server
            # what is left (60-review.js), which on a slow runner outlasts a fixed pause (A2: two misses on GitHub)
            try:
                pg.wait_for_selector('#view .done-card, #view [data-claim], #view [data-self]', timeout=10000)
            except Exception:
                break
            if pg.query_selector('.done-card'):
                break
            if pg.query_selector('[data-claim]'):
                pg.click('[data-claim="know"]'); card = pg.wait_for_selector('#view .open-card', timeout=4000); pg.keyboard.press('Enter')
                card.wait_for_element_state('hidden', timeout=10000); continue  # this answer has gone: the next card is drawn
            el = pg.query_selector('[data-self="good"]'); el.click(); el.wait_for_element_state('hidden', timeout=10000)
        try:
            pg.wait_for_selector('.done-card #stopOk', timeout=10000)
        except Exception:
            pass
        head = pg.text_content('.done-card h2') if pg.query_selector('.done-card') else ''
        stop = pg.text_content('#stopOk') if pg.query_selector('#stopOk') else ''
        again = pg.text_content('#again') if pg.query_selector('#again') else ''
        check(dev, 'after the 40: a place to stop, 今天做到这里也行 as the main button, 再做 beside it', head.startswith('这一轮复习了 40 个') and '今天做到这里也行' in stop
              and again.startswith('再做') and 'primary' not in (pg.get_attribute('#again', 'class') or '')
              and (pg.text_content('.done-card a.btn.primary[href="#/"]') or '').strip() == '今天就到这里', (head, stop, again))
        for page, sel, name in (('#/report', '.card a.link[href="#/easy"]', '周报「去读」'), ('#/report', '.card a.link[href="#/speak"]', '周报「去练」'),
                                ('#/', '.section-head a.link[href="#/welcome/edit"]', '今日「按 B1 挑选 · 调整」'), (f'#/m/{PID}/listen', '#originMore', '材料的「怎么写的」')):
            go(pg, page); pg.wait_for_timeout(300)
            t = pg.evaluate(TAP44_JS, sel)
            check(dev, f'{name} takes a tap 44 px around it', t is not None and t['ok'], t)
        # 背词计划: 20 new words a day at 90 % comes to over half an hour a month in: the number, the way out, and one tap to 10
        go(pg, '#/vocab/plan'); pg.click('#dn [data-v="20"]'); pg.wait_for_timeout(200)
        hint = pg.text_content('#dnHint') or ''
        # every learner has the day's word time now (time_budget, r28 第 1 段: 15 minutes at 60 a day), so the way out is the
        # number of new words that time keeps up with (单词每天, r28 第 3 段), not a flat 10
        wmh = pg.text_content('#wmHint') or ''
        fit = pg.get_attribute('#wmFit', 'data-n')
        check(dev, 'plan: more than the day\'s word time says the minutes and offers the number that fits, one tap away',
              '连新词约' in hint and '按单词每天 15 分钟' in wmh and '比 15 分钟多' in wmh and pg.is_visible('#wmFit') and not pg.is_visible('#dnTen'), (hint, wmh))
        pg.click('#wmFit'); pg.wait_for_timeout(200)
        check(dev, 'plan: after the tap, that number is chosen and the offer is gone',
              fit and pg.input_value('#dnOwn') == fit and not pg.is_visible('#wmFit'), (fit, pg.input_value('#dnOwn'), pg.text_content('#wmHint')))
        # r28 section 3: 单词每天 5 分钟. The 40 answered above are past it: today's words are done, the rest waits for the
        # coming days, 继续复习 goes on past the cap
        csrf = CFG['learners']['pile']['csrf']
        plan = pg.evaluate("fetch('/api/next/vocab').then(r => r.json()).then(o => o.plan)")
        st = pg.evaluate("([p, csrf]) => fetch('/api/next/vocab/plan', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, "
                         "body: JSON.stringify({book: p.book, daily_new: 10, retention: p.retention, word_minutes: 5})}).then(r => r.status)", [plan, csrf])
        fresh = lambda: (pg.reload(wait_until='load'), settle(pg), go(pg, '#/cards'), pg.wait_for_timeout(300))  # the page keeps API answers in memory (05-data.js)
        fresh()
        o = pg.evaluate("fetch('/api/next/vocab').then(r => r.json())")
        later = pg.text_content('#laterLine') if pg.query_selector('#laterLine') else ''
        check(dev, 'a cap of 5 minutes already used: 今天的单词做完了, the rest waits, 继续复习 one tap away',
              st == 200 and o['cap'] == 5 and o['due'] + o['new'] == 0 and o['later'] > 0 and f"还有 {o['later']} 个复习留到之后几天" in later
              and '单词每天 5 分钟' in later and pg.is_visible('#moreRev'), (st, o.get('cap'), o.get('due'), o.get('later'), later))
        pg.click('#moreRev'); pg.wait_for_timeout(500)
        check(dev, '继续复习 goes on past the cap', 'review/more' in pg.url and bool(pg.query_selector('[data-claim], [data-self]')), pg.url)
        # the plan page: 5 minutes keep up with about 3 new words a day; 10 a day is more: the number that fits, one tap away
        go(pg, '#/vocab/plan'); pg.wait_for_timeout(300)
        wmh = pg.text_content('#wmHint') or ''
        check(dev, 'plan: 单词每天 5 分钟 says the new words a day it keeps up with, and offers that number',
              pg.get_attribute('#wm [data-m="5"]', 'aria-pressed') == 'true' and '按单词每天 5 分钟，每天大约能学 3 个新词' in wmh and pg.is_visible('#wmFit'), wmh)
        pg.click('#wmFit'); pg.wait_for_timeout(200)
        check(dev, 'plan: after the tap, 3 new words a day and no more offer', pg.input_value('#dnOwn') == '3' and not pg.is_visible('#wmFit'),
              (pg.input_value('#dnOwn'), pg.text_content('#wmHint')))
        # a book nearly done, then done: what comes next, one tap away (the API's answer is changed here; test_vocab tests vocab_service)
        def book(route, kind):
            r = route.fetch(); o = r.json()
            o['book'].update(left=12, days=2, soon=kind == 'soon', done=kind == 'done', finish=None if kind == 'done' else o['book'].get('finish'),
                             next={'id': 'high', 'title': '高阶词汇', 'new': 2400}, exam_first=False)
            route.fulfill(response=r, json=o)
        pg.route('**/api/next/vocab', lambda route: book(route, 'soon'))
        fresh()
        soon = pg.text_content('#bookSoon') if pg.query_selector('#bookSoon') else ''
        check(dev, 'a book nearly done: the new words left, the days, and the next book with its new words',
              '还剩 12 个新词，大约 2 天背完' in soon and '接下来推荐《高阶词汇》' in soon and '还剩约 2,400 个新词' in soon, soon)
        pg.unroute('**/api/next/vocab'); pg.route('**/api/next/vocab', lambda route: book(route, 'done'))
        fresh()
        done = pg.text_content('#bookDone') if pg.query_selector('#bookDone') else ''
        check(dev, 'a finished book: 背完了, 换成 the next one as the main button, 先只复习 beside it',
              '背完了' in done and (pg.text_content('#bookNext') or '') == '换成《高阶词汇》' and 'primary' in (pg.get_attribute('#bookNext', 'class') or '')
              and pg.is_visible('#bookRest'), done)
        pg.click('#bookRest'); pg.wait_for_timeout(100)
        gone = not pg.query_selector('#bookDone')
        fresh()
        check(dev, '先只复习 puts the card away, and it stays away', gone and not pg.query_selector('#bookDone'), gone)
        pg.unroute('**/api/next/vocab')
        check(dev, 'no script errors', not errs, errs[:3])
        ctx.close()
    finally:
        browser.close()


# ---- 启动动画 and 选方向和目标 (r27): the mark on every opening, the one page a new learner answers once, the same page
# from 我的; five sizes, light and dark
START_SIZES = {'phone': (390, 844, True), 'phone-360': (360, 780, True), 'phone-land': (844, 390, True), 'tablet': (820, 1180, True), 'desktop': (1440, 900, False)}
SPLASH_JS = "() => { const s = document.getElementById('splash'); return s ? [s.className, getComputedStyle(s).visibility] : null; }"


def start_run(pw):
    dev = 'start'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    try:
        for size, (w, h, touch) in START_SIZES.items():
            for theme in ('light', 'dark'):
                tag = f'{size} {theme}'
                ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=touch, has_touch=touch, device_scale_factor=2, locale='zh-CN',
                                          color_scheme=theme, bypass_csp=True)
                pg = ctx.new_page(); errs = []
                pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
                # a first visit: the full mark (name and line), about a second, then the page, which is the one-page start
                pg.goto(BASE + '/', wait_until='commit'); pg.wait_for_selector('#splash', state='attached', timeout=5000); pg.wait_for_timeout(120)
                first = pg.evaluate(SPLASH_JS)
                if size == 'phone':
                    pg.wait_for_timeout(500); pg.screenshot(path=str(OUT / f'start-splash-{theme}.png'))
                pg.wait_for_selector('#splash', state='detached', timeout=5000)
                gone = pg.evaluate('Math.round(performance.now())')
                check(dev, f'{tag}: a first visit shows the full mark for about a second, then the start page', first and 'first' in first[0] and 900 <= gone <= 2500
                      and pg.evaluate('location.hash') == '#/welcome', (first, gone, pg.evaluate('location.hash')))
                settle(pg); pg.wait_for_timeout(200)
                lay = pg.evaluate(LAYOUT_JS, touch)
                tabs = pg.evaluate("getComputedStyle(document.querySelector('.tabs')).display")
                check(dev, f'{tag}: the start page fits (no sideways scroll, nothing squeezed, controls big enough), without the tabs',
                      lay['overflow'] <= 1 and not lay['squeezed'] and not lay.get('small') and not lay.get('smallFields') and tabs == 'none',
                      (lay['overflow'], lay['squeezed'], lay.get('small'), lay.get('smallFields'), tabs))
                bad = []
                for kind, items in pg.evaluate(A11Y_JS).items():
                    bad += [f'{kind}: {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}' for x in items]
                check(dev, f'{tag}: contrast, names and labels on the start page', not bad, f'{len(bad)}: ' + ' | '.join(bad[:4]))
                # 考试 opens the exams; an exam suggests a level (推荐), picked unless one was chosen by hand
                pg.click('[data-goal="exam"]'); pg.click('[data-exam="cet4"]'); pg.wait_for_timeout(150)
                rec = pg.evaluate("[...document.querySelectorAll('[data-target]')].filter(b => !b.querySelector('.rec').hidden).map(b => [b.dataset.target, b.getAttribute('aria-checked')])")
                pg.click('[data-exam="cet6"]'); pg.wait_for_timeout(100)
                rec6 = pg.evaluate("document.querySelector('[data-target][aria-checked=true]').dataset.target")
                pg.click('[data-target="C1"]'); pg.click('[data-exam="ielts"]'); pg.wait_for_timeout(100)
                kept = pg.evaluate("document.querySelector('[data-target][aria-checked=true]').dataset.target")
                check(dev, f'{tag}: 考试 opens the exams; 四级 suggests B1, 六级 B2; a level picked by hand stays', rec == [['B1', 'true']] and rec6 == 'B2' and kept == 'C1', (rec, rec6, kept))
                # 一周学几天 (每周目标): 5 for an exam, 4 otherwise, until picked by hand
                days = lambda: pg.evaluate("(b => b && +b.dataset.days)(document.querySelector('[data-days][aria-checked=true]'))")
                d_exam = days(); pg.click('[data-goal="daily"]'); d_daily = days()
                pg.click('[data-days="6"]'); pg.click('[data-goal="exam"]'); d_kept = days()
                row = pg.evaluate("new Set([...document.querySelectorAll('[data-days]')].map(b => Math.round(b.getBoundingClientRect().top))).size")
                check(dev, f'{tag}: 一周学几天: 5 days for an exam, 4 otherwise, 2–7 in one row; a number picked by hand stays', (d_exam, d_daily, d_kept, row) == (5, 4, 6, 1), (d_exam, d_daily, d_kept, row))
                if size == 'phone':
                    pg.click('[data-target="B2"]'); pg.wait_for_timeout(100)
                    pg.screenshot(path=str(OUT / f'start-page-{theme}.png'), full_page=True)
                pg.fill('#wgDateIn', (__import__('datetime').date.today() + __import__('datetime').timedelta(days=60)).isoformat())
                pg.click('#wgGo'); pg.wait_for_function("() => location.hash === '#/'", timeout=6000); settle(pg)
                guest = pg.evaluate("JSON.parse(localStorage.getItem('flow-next-guest'))")
                check(dev, f'{tag}: started as a guest: the choices kept on the phone, materials one band below the target, today shown',
                      guest['goal'] == 'exam' and guest['exam'] == 'ielts' and guest['level_source'] == 'guess' and guest['level'] == {'C1': 'B2', 'B2': 'B1'}[guest['target']] and guest['weekly_goal'] == 6
                      and pg.query_selector('#view .hello, #view .today-plan') is not None, guest)
                # the next opening: the mark alone and short; never the start page again
                pg.reload(wait_until='commit'); pg.wait_for_selector('#splash', state='attached', timeout=5000)
                again = pg.evaluate(SPLASH_JS)
                pg.wait_for_selector('#splash', state='detached', timeout=5000); settle(pg)
                check(dev, f'{tag}: opened again: the short mark only, then 今日 (the start page does not come back)', again and 'first' not in again[0] and pg.evaluate('location.hash') in ('', '#/'),
                      (again, pg.evaluate('location.hash')))
                check(dev, f'{tag}: no script errors', not errs, errs[:3])
                ctx.close()
        # a new account without settings: the page, written to the account in one call; 今日 then suggests a test
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['fresh']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        check(dev, 'a signed-in account without settings gets the start page (no 登录 link there)', pg.evaluate('location.hash') == '#/welcome' and not pg.query_selector('#wgLogin'), pg.evaluate('location.hash'))
        pg.click('[data-goal="exam"]'); pg.click('[data-exam="cet6"]'); pg.wait_for_timeout(100)
        said = pg.evaluate("(el => el && !el.hidden ? el.textContent : '')(document.getElementById('wgPlan'))")
        pg.screenshot(path=str(OUT / 'start-plan-note.png'), full_page=True)
        pg.click('#wgGo')
        pg.wait_for_function("() => location.hash === '#/'", timeout=6000); settle(pg); pg.wait_for_timeout(300)
        vp = pg.evaluate("fetch('/api/next/vocab').then(r => r.json()).then(o => o.plan && [o.plan.book, o.plan.daily_new])")
        check(dev, 'with an exam, the page says a word plan will be made, and starting makes it: the exam\'s book, 10 a day',
              '《六级词汇》每天 10 个新词' in said and vp == ['cet6', 10], (said, vp))
        prof = pg.evaluate("fetch('/api/next/home').then(r => r.json()).then(h => [h.profile, h.level_guess])")
        note = pg.evaluate("(document.getElementById('levelGuess') || {}).textContent || ''")
        check(dev, 'the account keeps goal, exam (the exam goal of 考试冲刺), target and a guessed level; 今日 suggests a test',
              prof[0]['goal'] == 'exam' and prof[0]['exam'] == 'cet6' and prof[0]['target'] == 'B2' and prof[0]['level'] == 'B1' and prof[0]['weekly_goal'] == 5 and prof[1]
              and '去能力里测一下' in note and pg.get_attribute('#levelGuess a', 'href') == '#/radar/test', (prof, note[:40]))
        pg.screenshot(path=str(OUT / 'start-today-hint.png'))
        pg.click('#lgLater'); pg.wait_for_timeout(200)
        check(dev, '「以后再说」 puts the suggestion away', pg.query_selector('#levelGuess') is None)
        # 我的 → 学习目标和水平: the same page, with the current level, minutes and topics; saved, it goes back to 我的
        go(pg, '#/me'); pg.click('a[href="#/welcome/edit"]'); settle(pg)
        edit = pg.evaluate("""() => ({goal: (document.querySelector('[data-goal][aria-checked=true]') || {}).dataset, level: (document.querySelector('[data-level][aria-checked=true]') || {}).textContent,
          exam: (document.querySelector('[data-exam][aria-checked=true]') || {}).textContent, tabs: getComputedStyle(document.querySelector('.tabs')).display})""")
        pg.click('[data-level="B2"]'); pg.click('[data-min="20"]'); pg.click('#wgGo')
        pg.wait_for_function("() => location.hash === '#/me'", timeout=6000); settle(pg)
        p2 = pg.evaluate("fetch('/api/next/home').then(r => r.json()).then(h => h.profile)")
        check(dev, '我的 opens the same page with what was chosen (tabs shown); a level chosen there counts as the learner choice',
              edit['level'] and edit['level'].startswith('B1') and edit['exam'] == '六级' and edit['tabs'] != 'none'
              and (p2['level'], p2['level_source'], p2['minutes'], p2['exam']) == ('B2', 'self', 20, 'cet6'), (edit, p2))
        check(dev, 'no script errors (account)', not errs, errs[:3])
        ctx.close()
        # no word plan yet: 今日's first step asks for a book (not ticked); with an exam set, 背词计划 opens with its book chosen
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='zh-CN', bypass_csp=True)
        ctx.add_cookies([{'name': 'flow_session', 'value': CFG['learners']['fresh2']['token'], 'url': BASE}])
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        pg.click('[data-goal="daily"]'); pg.click('#wgGo'); pg.wait_for_function("() => location.hash === '#/'", timeout=6000); settle(pg)
        step = pg.evaluate("(a => a && [a.querySelector('b').textContent, a.getAttribute('href'), a.classList.contains('done')])(document.querySelector('.today-plan .prow'))")
        pg.screenshot(path=str(OUT / 'start-choose-book.png'))
        csrf = CFG['learners']['fresh2']['csrf']
        pg.evaluate("t => fetch('/api/next/exam/goal', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': t}, body: JSON.stringify({exam: 'cet4', date: ''})})", csrf)
        go(pg, '#/vocab/plan'); pg.wait_for_timeout(300)
        chosen = pg.evaluate("[document.getElementById('bookNow').textContent, [...document.querySelectorAll('#goal [aria-pressed=true]')].map(x => x.textContent)]")
        check(dev, 'no word plan: 今日 starts with 选一本词书 (not ticked, to 背词计划), which opens with the exam\'s book chosen',
              step == ['选一本词书', '#/vocab/plan', False] and '《四级词汇》' in chosen[0] and chosen[1] == ['四级'], (step, chosen))
        check(dev, 'no script errors (no word plan)', not errs, errs[:3])
        ctx.close()
        # reduced motion: no rising bars, the mark only fades
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='zh-CN', bypass_csp=True, reduced_motion='reduce')
        ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { const i = document.querySelector('.sp-mark i'); window.__spAnim = i ? getComputedStyle(i).animationName : 'gone'; })")
        pg = ctx.new_page(); pg.goto(BASE + '/', wait_until='domcontentloaded')
        anim = pg.evaluate('window.__spAnim')
        pg.wait_for_selector('#splash', state='detached', timeout=5000)
        check(dev, 'reduced motion: the bars do not move and the mark leaves once the page is drawn', anim == 'none', anim)
        ctx.close()
    finally:
        browser.close()


# ---- 主屏 App (Safari 「添加到主屏幕」, 04-home-app.js): opened from the home screen there is no browser back, the
# Dynamic Island and the home bar take the screen's edges, the keyboard covers what is fixed, and the app may sleep for
# days. Chrome stands in for the iPhone: navigator.standalone, the safe areas set through --sat/--sab/--sal/--sar
# (00-base.css), and a visualViewport whose height the test sets as a keyboard would.
HOME_SIZES = {  # name -> (width, height, top, bottom, left/right inset)
    'iphone-15-pro': (393, 852, 59, 34, 0), 'iphone-15-pro-land': (852, 393, 0, 21, 59), 'iphone-se': (375, 667, 0, 0, 0)}
HOME_INIT = """(([t, b, s]) => {
  Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true, configurable: true });
  const vv = new EventTarget(); let h = null;
  Object.defineProperties(vv, { height: { get: () => h == null ? innerHeight : h }, offsetTop: { get: () => 0 }, offsetLeft: { get: () => 0 },
    width: { get: () => innerWidth }, scale: { get: () => 1 }, pageTop: { get: () => scrollY } });
  Object.defineProperty(window, 'visualViewport', { value: vv, configurable: true });
  window.__kb = px => { h = px ? innerHeight - px : null; vv.dispatchEvent(new Event('resize')); };
  document.addEventListener('DOMContentLoaded', () => { const r = document.documentElement.style;
    r.setProperty('--sat', t + 'px'); r.setProperty('--sab', b + 'px'); r.setProperty('--sal', s + 'px'); r.setProperty('--sar', s + 'px'); });
})(%s)"""
HOME_SUB = ['#/m/{pid}/listen', '#/m/{pid}/read', '#/m/{pid}/output/essay', '#/review', '#/vocab/test', '#/vocab/plan', '#/exam/cet4', '#/exam/cet4/banked',
            '#/graph', '#/graph/voice-basic', '#/import', '#/report', '#/growth', '#/radar', '#/radar/test', '#/guide', '#/guide/words', '#/feedback',
            '#/library', '#/welcome/edit', '#/speak', '#/easy', '#/sounds', '#/placement', '#/mix', '#/words/confuse']
BACK_JS = """() => { const b = document.getElementById('backBtn'); if (!b || b.hidden || b.offsetParent === null) return null; const r = b.getBoundingClientRect();
  return { top: Math.round(r.top), bottom: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height), label: b.textContent.trim(),
           brand: !document.querySelector('.bar .brand').hidden }; }"""


def home_app_run(pw):
    dev = 'home-app'
    browser = pw.chromium.launch(channel='chrome', headless='--headed' not in sys.argv)
    tok = CFG['learners']['home-app']['token']

    def context(size, theme='light', signed=True):
        w, h, t, b, s = HOME_SIZES[size]
        ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=3, locale='zh-CN',
                                  color_scheme=theme, bypass_csp=True)
        ctx.add_init_script(HOME_INIT % json.dumps([t, b, s]))
        if signed:
            ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
        pg = ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(page_error(pg, e)))
        return ctx, pg, errs
    try:
        for size, (w, h, top, bottom, side) in HOME_SIZES.items():
            ctx, pg, errs = context(size)
            pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
            check(dev, f'{size}: the page knows it is a home-screen app', pg.evaluate("document.documentElement.classList.contains('home-app')"))
            for page in ('#/', f'#/m/{PID}/read'):  # --bar-h, for pages that fill one screen: the bar's real height, back button or not
                go(pg, page); pg.wait_for_timeout(150)
                bh = pg.evaluate("[parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bar-h')), Math.round(document.getElementById('bar').getBoundingClientRect().height)]")
                check(dev, f'{size} {page}: --bar-h is the top bar\'s height ({bh[1]}px, the inset included)', bh[0] == bh[1] and bh[1] >= 48 + top, bh)
            # the four tabs: no back button, the logo below the Dynamic Island, every tab above the home bar
            for page in ('#/', '#/practice', '#/cards', '#/me'):
                go(pg, page)
                tabs = pg.evaluate("""() => { const t = [...document.querySelectorAll('.tabs a')].filter(a => a.offsetParent !== null).map(a => a.getBoundingClientRect());
                  const brand = document.querySelector('.bar .brand').getBoundingClientRect();
                  return { n: t.length, low: t.length ? Math.round(Math.max(...t.map(r => r.bottom))) : null, brandTop: Math.round(brand.top), back: !document.getElementById('backBtn').hidden }; }""")
                check(dev, f'{size} {page}: no back button; the logo clears the top inset; the tabs clear the home bar',
                      not tabs['back'] and tabs['brandTop'] >= top and (tabs['n'] == 0 or tabs['low'] <= h - bottom), tabs)
            # every other page: a back button in the first screen, below the Dynamic Island, big enough to tap
            pid = PID
            for page in HOME_SUB:
                page = page.format(pid=pid)
                go(pg, page); pg.wait_for_timeout(150)
                bk = pg.evaluate(BACK_JS)
                check(dev, f'{size} {page}: a back button at the top, clear of the inset, at least 44×40',
                      bk and bk['top'] >= top and bk['bottom'] <= top + 80 and bk['w'] >= 44 and bk['h'] >= 40 and not bk['brand'], bk)
                if size == 'iphone-15-pro' and page in (f'#/m/{pid}/read', '#/vocab/test', '#/review'):
                    pg.screenshot(path=str(OUT / f"home-app-{page.strip('#/').replace('/', '_')}.png"))
            # review (the tabs hidden): its answers clear the home bar
            go(pg, '#/review'); pg.wait_for_timeout(300)
            low = pg.evaluate("() => { scrollTo(0, document.scrollingElement.scrollHeight); const b = [...document.querySelectorAll('#view .review button, #view .review a')].filter(x => x.offsetParent !== null).map(x => x.getBoundingClientRect().bottom); return b.length ? Math.round(Math.max(...b)) : null; }")
            check(dev, f'{size} review: with the tabs hidden, its controls clear the home bar', low is None or low <= h - bottom, (low, h - bottom))
            check(dev, f'{size}: no script errors', not errs, errs[:3])
            ctx.close()

        ctx, pg, errs = context('iphone-15-pro')
        # back goes to the page before when the app has one; opened straight on a page, to that page's tab
        pg.goto(BASE + f'/#/m/{PID}/read', wait_until='networkidle'); settle(pg)
        first = pg.evaluate(BACK_JS)
        pg.click('#backBtn'); settle(pg)
        to_tab = pg.evaluate('location.hash')
        go(pg, '#/library'); go(pg, f'#/m/{PID}/listen')
        second = pg.evaluate(BACK_JS)
        pg.click('#backBtn'); settle(pg)
        check(dev, 'back: opened straight on a material it says 今日 and goes there; after 全部材料 it says 返回 and goes back to it',
              first and first['label'] == '今日' and to_tab in ('#/', '') and second and second['label'] == '返回' and pg.evaluate('location.hash') == '#/library',
              (first, to_tab, second, pg.evaluate('location.hash')))
        go(pg, '#/exam/cet4/banked')
        bk = pg.evaluate(BACK_JS); pg.click('#backBtn'); settle(pg)
        check(dev, 'back from 题型专练 (exam area) returns to the page before (全部材料)', bk and bk['label'] == '返回' and pg.evaluate('location.hash') == '#/library',
              (bk, pg.evaluate('location.hash')))
        # light and dark: the back button and the new-version line are named and readable
        for theme in ('light', 'dark'):
            c2, p2, e2 = context('iphone-15-pro', theme)
            p2.route('**/api/version', lambda r: r.fulfill(status=200, content_type='application/json', body='{"asset": "a11y-version"}'))
            p2.goto(BASE + f'/#/m/{PID}/check', wait_until='networkidle'); settle(p2)
            p2.wait_for_selector('#updateBar', timeout=9000)
            bad = []
            for kind, items in p2.evaluate(A11Y_JS).items():
                bad += [f'{kind}: {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}' for x in items if 'backBtn' in str(x) or 'update' in str(x) or 'ub-' in str(x)]
            check(dev, f'{theme}: the back button and the new-version line have names and contrast', not bad, f'{len(bad)}: ' + ' | '.join(bad[:4]))
            p2.screenshot(path=str(OUT / f'home-app-update-{theme}.png'))
            c2.close()
        check(dev, 'no script errors (back)', not errs, errs[:3])
        ctx.close()

        # the keyboard: a field and its button stay above it (iPhone SE: the smallest screen); a sheet stands on it
        for size, kb in (('iphone-se', 260), ('iphone-15-pro', 336)):
            ctx, pg, errs = context(size)
            hh = HOME_SIZES[size][1]
            pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
            for page, field, button, start in ((f'#/m/{PID}/output', '#ans', '#go', None), (f'#/m/{PID}/output/essay', '#esIn', '#esGo', None),
                                               (f'#/m/{PID}/output/dialog', '#dlgText', '#dlgSend', '#dlgStart'), ('#/import', 'textarea[name=text]', '#view form .btn.primary', None)):
                go(pg, page)
                if start:
                    pg.click(start); pg.wait_for_selector(field, state='visible', timeout=8000)
                pg.wait_for_selector(field, state='visible', timeout=8000)
                pg.focus(field); pg.wait_for_timeout(100)
                pg.evaluate(f'__kb({kb})'); pg.wait_for_timeout(500)
                got = pg.evaluate("""([f, b]) => { const r = document.querySelector(f).getBoundingClientRect(), s = document.querySelector(b).getBoundingClientRect();
                  return [Math.round(r.top), Math.round(r.bottom), Math.round(s.bottom)]; }""", [field, button])
                check(dev, f'{size} keyboard {kb}px on {page}: the field and its button stay above it', got[0] >= 0 and got[1] <= hh - kb and got[2] <= hh - kb, (got, hh - kb))
                if size == 'iphone-se' and field == '#ans':
                    pg.screenshot(path=str(OUT / 'home-app-keyboard-se.png'))
                pg.evaluate('__kb(0)'); pg.evaluate('document.activeElement.blur()'); pg.wait_for_timeout(150)
            go(pg, '#/vocab/plan'); pg.click('#impBook'); pg.wait_for_selector('#impText', timeout=6000); pg.wait_for_timeout(300)
            pg.focus('#impText'); pg.evaluate(f'__kb({kb})'); pg.wait_for_timeout(500)
            sh = pg.evaluate("""() => { const c = document.getElementById('sheetCard').getBoundingClientRect(), t = document.getElementById('impText').getBoundingClientRect(),
              g = document.getElementById('impGo').getBoundingClientRect(); return [Math.round(c.bottom), Math.round(t.top), Math.round(g.bottom), Math.round(c.top)]; }""")
            check(dev, f'{size} keyboard {kb}px in a sheet: the sheet stands on the keyboard, its field and button in sight',
                  sh[0] <= hh - kb + 1 and sh[1] >= sh[3] and sh[2] <= hh - kb, (sh, hh - kb))
            pg.evaluate('__kb(0)')
            check(dev, f'{size}: no script errors (keyboard)', not errs, errs[:3])
            ctx.close()

        # a new version on the server: taken at once on a resting page (and tried once only); elsewhere one line offers it
        ctx, pg, errs = context('iphone-15-pro')
        pg.route('**/api/version', lambda r: r.fulfill(status=200, content_type='application/json', body='{"asset": "newer-version"}'))
        loads = []
        pg.on('load', lambda: loads.append(1))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        pg.wait_for_timeout(9000)  # the check 4 s after opening, the reload, the check after it
        bar_after = pg.query_selector('#updateBar') is not None
        check(dev, 'new version on 今日: reloaded once to take it; when the page is still old after that, only the line offers it (no reload loop)',
              len(loads) == 2 and bar_after, (len(loads), bar_after))
        ctx.close()
        ctx, pg, errs = context('iphone-15-pro')
        pg.route('**/api/version', lambda r: r.fulfill(status=200, content_type='application/json', body='{"asset": "newer-version"}'))
        loads = []
        pg.on('load', lambda: loads.append(1))
        pg.goto(BASE + f'/#/m/{PID}/check', wait_until='networkidle'); settle(pg)
        pg.wait_for_selector('#updateBar', timeout=9000)
        stayed = len(loads) == 1
        pg.click('#updateBar .ub-go'); pg.wait_for_timeout(5500)  # here no new worker comes, so the full 4 s wait
        check(dev, 'new version while answering questions: no reload, one line; a tap on it reloads', stayed and len(loads) == 2, (stayed, len(loads)))
        ctx.close()
        # on 今日 but something playing (the mini player, 好句, shadowing): no reload, only the line
        ctx, pg, errs = context('iphone-15-pro')
        ctx.add_init_script("Object.defineProperty(HTMLMediaElement.prototype, 'paused', { get: () => false, configurable: true })")
        pg.route('**/api/version', lambda r: r.fulfill(status=200, content_type='application/json', body='{"asset": "newer-version"}'))
        loads = []
        pg.on('load', lambda: loads.append(1))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        pg.wait_for_selector('#updateBar', timeout=9000); pg.wait_for_timeout(1000)
        check(dev, 'new version on 今日 while audio plays: no reload, only the line', len(loads) == 1, len(loads))
        ctx.close()
        # on 今日 when the new version is found, but the learner opens a text during the wait for the new worker (up to
        # 4 s): no reload under them (it cut 播放全文 before its first sentence), the line offers it instead
        ctx, pg, errs = context('iphone-15-pro')
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg)
        pg.wait_for_function('!!(navigator.serviceWorker && navigator.serviceWorker.controller)', timeout=10000)  # a worker in charge: the wait happens
        pg.route('**/api/version', lambda r: r.fulfill(status=200, content_type='application/json', body='{"asset": "newer-version"}'))
        pg.reload(wait_until='networkidle'); settle(pg)
        loads = []
        pg.on('load', lambda: loads.append(1))
        pg.wait_for_function("localStorage.getItem('flow-update-tried') !== null", timeout=9000)  # the check after 4 s, the wait begun
        go(pg, f'#/m/{PID}/check'); pg.wait_for_timeout(5500)
        got = {'loads': len(loads), 'bar': pg.query_selector('#updateBar') is not None, 'tried': pg.evaluate("localStorage.getItem('flow-update-tried')")}
        check(dev, 'new version found on 今日, a text opened during the 4-second wait: no reload under it, the line offers it',
              got['loads'] == 0 and got['bar'] and got['tried'] in (None, 'null'), got)
        ctx.close()
        ctx, pg, errs = context('iphone-15-pro')
        loads = []
        pg.on('load', lambda: loads.append(1))
        pg.goto(BASE + '/', wait_until='networkidle'); settle(pg); pg.wait_for_timeout(5500)
        ver = pg.evaluate("fetch('/api/version').then(r => r.json())")
        check(dev, 'the same version: /api/version answers it, and nothing reloads or shows', ver.get('asset') and len(loads) == 1 and pg.query_selector('#updateBar') is None, (ver, len(loads)))
        ctx.close()
        # light → dark while open (an iPhone keeps the status-bar strip of the page's load: a white band): no reload while
        # answering questions; the next tab page reloads to repaint it (tools/ios_sim_check.py checks the strip itself)
        ctx, pg, errs = context('iphone-15-pro')
        loads = []
        pg.on('load', lambda: loads.append(1))
        pg.goto(BASE + f'/#/m/{PID}/check', wait_until='networkidle'); settle(pg)
        pg.emulate_media(color_scheme='dark'); pg.wait_for_timeout(1200)
        stayed = len(loads) == 1
        go(pg, '#/'); pg.wait_for_timeout(1500)
        check(dev, 'light → dark while answering: no reload there; the next tab page reloads once (the status-bar strip)', stayed and len(loads) == 2, (stayed, len(loads)))
        pg.wait_for_timeout(1500)
        check(dev, 'after that reload: no second one', len(loads) == 2, len(loads))
        ctx.close()
        # the iOS app (语流 20: a WKWebView, the user agent ending in FlowiOS/<version>; navigator.standalone is not set
        # there): a home app too, back buttons and all; nothing to add to the desktop; the keyboard left to the app (its
        # web view ends at the keyboard), so no room made below the page for one
        ctx = browser.new_context(viewport={'width': 393, 'height': 852}, is_mobile=True, has_touch=True, device_scale_factor=3, locale='zh-CN', bypass_csp=True,
                                  user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 26_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 FlowiOS/1.0')
        ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
        pg = ctx.new_page()
        pg.goto(BASE + f'/#/m/{PID}/read', wait_until='networkidle'); settle(pg)
        app = pg.evaluate("() => ({ home: document.documentElement.classList.contains('home-app'), standalone: navigator.standalone === true })")
        bk = pg.evaluate(BACK_JS)
        go(pg, '#/me'); pg.wait_for_timeout(200)
        install = pg.evaluate("() => !!document.getElementById('meInstall')")
        go(pg, '#/import'); pg.wait_for_selector('#view textarea'); pg.focus('#view textarea'); pg.wait_for_timeout(200)
        room = pg.evaluate("() => document.body.classList.contains('kb-room')")
        check(dev, 'the iOS app (FlowiOS in the user agent): a home app with back buttons, no 「添加到桌面」, the keyboard left to the app',
              app['home'] and not app['standalone'] and bk and bk['label'] and not install and not room, (app, bk, install, room))
        ctx.close()
        # the desktop app (语流 22: Windows and macOS, FlowDesktop/<version> in the user agent), and any app that says so
        # only by window.FlowApp: a home app too (返回 on a sub-page, the logo on a tab page), nothing to add to the desktop
        for label, ua, init in (('the desktop app (FlowDesktop)', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) FlowDesktop/0.1 (macOS)', None),
                                ('an app known by window.FlowApp only', None, "window.FlowApp = { platform: 'windows' }")):
            ctx = browser.new_context(viewport={'width': 1280, 'height': 800}, locale='zh-CN', bypass_csp=True, **({'user_agent': ua} if ua else {}))
            if init:
                ctx.add_init_script(init)
            ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
            pg = ctx.new_page()
            pg.goto(BASE + f'/#/m/{PID}/read', wait_until='networkidle'); settle(pg)
            home, bk = pg.evaluate("document.documentElement.classList.contains('home-app')"), pg.evaluate(BACK_JS)
            go(pg, '#/me'); pg.wait_for_timeout(200)
            tab = pg.evaluate(BACK_JS); install = pg.evaluate("() => !!document.getElementById('meInstall')")
            check(dev, f'{label}: a home app — 返回 on a sub-page, the logo on a tab page, no 「添加到桌面」',
                  home and bk and bk['label'] and tab is None and not install, (home, bk, tab, install))
            ctx.close()
        # the Android app (语流 21): its WebView gets shorter for the keyboard, nothing is covered, so a field near the end
        # and its button would sit below the page's end (登录 under the keyboard): both are brought into sight
        android = dict(viewport={'width': 393, 'height': 852}, is_mobile=True, has_touch=True, device_scale_factor=3, locale='zh-CN', bypass_csp=True,
                       user_agent='Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36 FlowAndroid/1.0')
        SIGHT = """([f, b]) => { const r = document.querySelector(f).getBoundingClientRect(), bt = document.querySelector(b), q = bt && bt.getBoundingClientRect();
          return { field: [Math.round(r.top), Math.round(r.bottom)], button: q ? Math.round(q.bottom) : null, h: innerHeight, open: document.body.classList.contains('kb-open') }; }"""
        for where, page, opener, field, button in (('导入文章', '#/import', None, '#view textarea', '#view .btn.primary'),
                                                   ('背词计划 → 导入词表 (a sheet)', '#/vocab/plan', '#impBook', '#impText', '#impGo')):
            ctx = browser.new_context(**android); ctx.add_init_script("window.FlowApp = { platform: 'android' }")
            ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
            pg = ctx.new_page(); pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg)
            go(pg, page)
            if opener:
                pg.wait_for_selector(opener, timeout=8000); pg.click(opener)
            pg.wait_for_selector(field, timeout=8000); pg.wait_for_timeout(300)
            pg.evaluate(f"document.querySelector({json.dumps(field)}).scrollIntoView({{block: 'start'}})"); pg.focus(field); pg.wait_for_timeout(200)
            pg.set_viewport_size({'width': 393, 'height': 852 - 330}); pg.wait_for_timeout(600)  # the keyboard: the WebView 330 px shorter
            got = pg.evaluate(SIGHT, [field, button])
            check(dev, f'the Android app, {where}: with the page shorter for the keyboard, the field and its button in sight',
                  got['button'] is not None and got['button'] <= got['h'] and got['field'][0] >= 0 and got['field'][1] <= got['h'] and got['open'], got)
            ctx.close()
        # one-screen pages (复习's card, 测词汇量, 起点小测) fit one screen whatever sits above them: the top bar with
        # 返回 (it made the bar 12 px taller), the 内测版's line, the safe area — the owner's iPhone, 2026-11-25. The
        # home-screen app and Safari, 375×667 and 390×844, 语流 and its 内测版: no vertical scroll.
        ONE = {'375x667': (375, 667, 20, 0), '390x844': (390, 844, 47, 34)}
        BETA_CH = "new MutationObserver((m, o) => { if (document.documentElement) { document.documentElement.dataset.channel = 'beta'; o.disconnect(); } }).observe(document, {childList: true, subtree: true})"
        over = {}
        for size, (w, h, t, b) in ONE.items():
            for env in ('home app', 'Safari'):
                for ch in ('语流', '内测版'):
                    ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN', bypass_csp=True)
                    if env == 'home app':
                        ctx.add_init_script(HOME_INIT % json.dumps([t, b, 0]))
                    if ch == '内测版':
                        ctx.add_init_script(BETA_CH)
                    ctx.add_init_script("try { localStorage.setItem('flow-channel', '\"beta\"') } catch (e) {}")  # no once-per-phone sheet
                    ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
                    pg = ctx.new_page(); pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg)
                    for page, sel in (('#/review', '.review'), ('#/vocab/test', '.review.vtest'), ('#/placement', '#view')):
                        # the card's way in (its parts slide up, a tip comes and goes) can show a few px past the screen for a moment:
                        # what counts is the page at rest, given up to 4 s to settle
                        go(pg, page); pg.wait_for_selector(sel, timeout=8000); pg.wait_for_timeout(600)
                        try:
                            pg.wait_for_function("document.scrollingElement.scrollHeight - innerHeight <= 0", timeout=4000)
                        except Exception:
                            pg.screenshot(path=str(OUT / f"one-screen-{page.strip('#/').replace('/', '_')}-{size}-{'home' if env == 'home app' else 'safari'}-{'beta' if ch == '内测版' else 'main'}.png"), full_page=True)
                        over[(size, env, ch, page)] = pg.evaluate("document.scrollingElement.scrollHeight - innerHeight")
                    ctx.close()
        for page in ('#/review', '#/vocab/test', '#/placement'):
            got = {f'{s} {e} {c}': v for (s, e, c, p), v in over.items() if p == page}
            check(dev, f'one screen: {page} — no vertical scroll in the home-screen app or Safari, 375×667 and 390×844, 语流 and 内测版',
                  all(v <= 0 for v in got.values()), {k: v for k, v in got.items() if v > 0} or got)
        # the 内测版 in one of Flow's apps: the learner installed it on purpose, and flowlang.cn would open the system
        # browser — the line stays without its link, the once-per-phone sheet is not shown (a browser still gets both)
        BETA = "new MutationObserver((m, o) => { if (document.documentElement) { document.documentElement.dataset.channel = 'beta'; o.disconnect(); } }).observe(document, {childList: true, subtree: true})"
        seen = {}
        for label, app in (('in an app', True), ('in a browser', False)):
            ctx = browser.new_context(viewport={'width': 393, 'height': 852}, is_mobile=True, has_touch=True, locale='zh-CN', bypass_csp=True)
            ctx.add_init_script(BETA)
            if app:
                ctx.add_init_script("window.FlowApp = { platform: 'android' }")
            ctx.add_cookies([{'name': 'flow_session', 'value': tok, 'url': BASE}])
            pg = ctx.new_page()
            # the ledger's beta entry as the 内测版 server gives it (this test server is 语流's: it answers beta: null)
            pg.route('**/api/next/updates', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'released': [], 'beta': {
                'date': '2026-11-25', 'changed': [{'text': '「认识」可以放在右边', 'link': '#/me'}], 'new': ['今日的计划按时间排'], 'better': [{'text': '复习卡正好一屏'}], 'fixed': []}}, ensure_ascii=False)))
            pg.goto(BASE + '/#/', wait_until='networkidle'); settle(pg); pg.wait_for_timeout(1200)
            LINE = "() => ({ bar: !!document.getElementById('betaBar'), link: !!document.querySelector('#betaBar a'), pill: !!document.querySelector('#bar .beta-pill'), h: Math.round((document.getElementById('betaBar') || {getBoundingClientRect: () => ({height: 0})}).getBoundingClientRect().height), sheet: !document.getElementById('sheet').hidden && /内测版/.test(document.getElementById('sheetCard').innerText) })"
            seen[label] = pg.evaluate(LINE)
            pg.evaluate("document.querySelector('#sheet:not([hidden]) [data-close]')?.click()")
            go(pg, '#/me'); pg.wait_for_timeout(300)
            seen[label]['me'] = pg.evaluate("""() => ({ section: [...document.querySelectorAll('.gsec h2')].some(h => h.textContent === '内测版'), main: !!document.querySelector('[data-tap=me-beta-main]'), feedback: !!document.querySelector('[data-tap=me-beta-feedback]'),
              changes: [...document.querySelectorAll('#meBetaNew li')].map(li => (li.classList.contains('beta-changed') ? '!' : '') + li.textContent.trim()), go: (document.querySelector('#meBetaNew a') || {}).hash || null })""")
            pg.evaluate("document.querySelector('#betaBar .bb-x').click()"); pg.wait_for_timeout(200)
            pg.reload(wait_until='load'); settle(pg); pg.wait_for_timeout(800)  # 我的 keeps asking (no network idle)
            seen[label]['after ✕ and a reload'] = pg.evaluate(LINE)
            ctx.close()
        a, b = seen['in an app'], seen['in a browser']
        check(dev, 'the 内测版: one thin line (no link: 去正式版 is in 我的), 「内测」 by the logo, ✕ closes it for good on this device',
              a['bar'] and b['bar'] and not a['link'] and not b['link'] and a['pill'] and b['pill'] and b['h'] <= 34
              and not a['after ✕ and a reload']['bar'] and not b['after ✕ and a reload']['bar'] and b['after ✕ and a reload']['pill'], seen)
        check(dev, 'the 内测版: 我的 has 内测版 (feedback; 去正式版 in a browser, not in an app); the once-per-phone sheet in a browser only',
              a['me']['section'] and b['me']['section'] and a['me']['feedback'] and b['me']['main'] and not a['me']['main'] and not a['sheet'] and b['sheet'], seen)
        ch = b['me']['changes']
        check(dev, 'the 内测版 in 我的: what changed in this version, 「用法变了」 first and marked, a link inside the site',
              len(ch) == 3 and ch[0].startswith('!用法变了') and '去看看' in ch[0] and b['me']['go'] == '#/me', b['me'])
    finally:
        browser.close()


def main():
    with sync_playwright() as pw:
        silent(pw)
        if not ONLY or 'about' in ONLY:
            try:
                about_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('about', 'run finished', False, traceback.format_exc()[-600:])
        for dev, opts in DEVICES.items():
            if ONLY and dev not in ONLY:
                continue
            try:
                run_device(pw, dev, opts)
            except Exception:
                check(dev, 'device run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'platforms' in ONLY:
            try:
                platform_run(pw)
            except Exception:
                check('platforms', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'wechat' in ONLY:
            try:
                wechat_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('wechat', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'ios-audio' in ONLY:
            try:
                ios_audio_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('ios-audio', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'app-audio' in ONLY:
            try:
                app_audio_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('app-audio', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'ux' in ONLY:
            try:
                ux_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('ux', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'learner' in ONLY:
            try:
                learner_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('learner', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'progress' in ONLY:
            try:
                progress_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('progress', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'swipe' in ONLY:
            try:
                swipe_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('swipe', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'listen-speak' in ONLY:
            try:
                listen_speak_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('listen-speak', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'home-app' in ONLY:
            try:
                home_app_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('home-app', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'start' in ONLY:
            try:
                start_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('start', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'sprint' in ONLY:
            try:
                sprint_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('sprint', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'review-side' in ONLY:
            try:
                review_side_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('review-side', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'one-screen' in ONLY:
            try:
                one_screen_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('one-screen', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'backlog' in ONLY:
            try:
                backlog_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('backlog', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'trial-survey' in ONLY:
            try:
                trial_survey_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('trial-survey', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'updates' in ONLY:
            try:
                updates_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('updates', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'privacy' in ONLY:
            try:
                privacy_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('privacy', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'class' in ONLY:
            try:
                class_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('class', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'wait' in ONLY:
            try:
                wait_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('wait', 'run finished', False, traceback.format_exc()[-600:])
        if not ONLY or 'a11y' in ONLY:
            try:
                a11y_run(pw)
            except Exception:
                print(traceback.format_exc())
                check('a11y', 'run finished', False, traceback.format_exc()[-600:])
        for engine in ('chrome', 'webkit'):  # last: it takes the vocabulary test and answers review cards
            if not ONLY or 'layout' in ONLY or engine in ONLY:
                try:
                    layout_run(pw, engine)
                except Exception:
                    print(traceback.format_exc())
                    check('layout-' + engine, 'run finished', False, traceback.format_exc()[-600:])
    failed = [r for r in RESULTS if not r['ok']]
    (OUT / 'ui-report.json').write_text(json.dumps({'total': len(RESULTS), 'failed': failed, 'results': RESULTS}, ensure_ascii=False, indent=1))
    print(f'\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed; screenshots and ui-report.json in {OUT}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
