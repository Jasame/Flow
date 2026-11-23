#!/usr/bin/env python3
"""Multi-device UI tests for Flow /next: phone, phone sideways, tablet and desktop; touch, keyboard and mouse.

    python3 tools/ui_test.py [out dir] [phone|phone-land|tablet|desktop …]   # needs: pip install playwright

Starts its own local server (tools/ui_server.py: throwaway database, simulated AI, one signed-in learner per device),
so every run begins from the same state, and drives the installed Google Chrome.

Checks layout (no sideways scrolling, nothing hidden under the bottom tabs, touch targets), and the input paths that
learners reported problems with: keyboard shortcuts, Enter in answer boxes, swipes in review, closing sheets, the
playback stop button, step switching, list filters. Screenshots of every page per device go to the out dir.
"""
import atexit, json, socket, subprocess, sys, tempfile, time, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

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
         '#/easy', '#/words/confuse', '#/words/confuse/borrow-lend,make-do', '#/speak', '#/speak/cafe-order', '#/growth', '#/series/a-new-term',
         '#/radar', '#/radar/goals', '#/radar/test', '#/radar/test/reading', '#/radar/test/writing']
RESULTS = []


def check(dev, name, ok, detail=''):
    RESULTS.append({'device': dev, 'check': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(f"{'PASS' if ok else 'FAIL'} [{dev}] {name}{'' if ok else '  ' + str(detail)[:300]}", flush=True)
    return ok


def settle(pg, sel='#view h1, #view .review, #view .empty, #view .done-card', timeout=8000):
    pg.wait_for_function("() => !document.querySelector('#view .skeleton')", timeout=timeout)
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
  const els = [...document.querySelectorAll('#view button:not([disabled]), #view a.btn, #view a.link')].filter(e => e.offsetParent !== null);
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
    pg.on('pageerror', lambda e: errors.append(str(e)))
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
    res = pg.evaluate("() => ({h: (document.querySelector('#view h1') || {}).textContent || '', bands: document.querySelectorAll('.bands .band').length})")
    check(dev, 'starting check: ends with a level and band scores', res['h'].startswith('建议从') and 1 <= res['bands'] <= 4 and asked % 4 == 0, (res, asked))

    # ---- exam practice: a timed paper of 22 questions, handed in once, scored by part
    go(pg, '#/exam/cet4')
    pg.click('#exStart'); pg.wait_for_selector('.exam-bar', timeout=8000); pg.wait_for_timeout(300)
    n = pg.evaluate("() => document.querySelectorAll('.exam-part .gq').length")
    check(dev, 'exam: a paper of 22 questions in three parts with a clock', n == 22 and pg.evaluate("() => document.querySelectorAll('.exam-part').length") == 3, n)
    for k in range(n):
        pg.click(f'.exam-part .gq >> nth={k} >> .ans >> nth=0')
    pg.click('#exDone'); pg.wait_for_timeout(900)
    res = pg.evaluate("() => ({h: (document.querySelector('#view h1') || {}).textContent || '', parts: document.querySelectorAll('.exam-score div').length})")
    check(dev, 'exam: handed in, scored by part', '题做对' in res['h'] and res['parts'] == 3, res)

    # ---- serial: six episodes in order, an episode names its place in the series
    go(pg, '#/series/lighthouse-ledger')
    eps = pg.evaluate("() => document.querySelectorAll('.serial .ep').length")
    check(dev, 'serial: six episodes and a way to carry on', eps == 6 and pg.is_visible('#view .btn.primary'), eps)
    go(pg, '#/m/v5-culture-c1-lighthouse-ledger-2/read')
    check(dev, 'serial: an episode shows its place in the series', '第 2 / 6 集' in (pg.text_content('.study-head .kicker') or ''))

    # ---- listen: whole-text playback shows a stop control that stays on screen, and it stops
    go(pg, f'#/m/{PID}/listen')
    pg.click('#playAll')
    pg.wait_for_timeout(250)
    mini = pg.evaluate("() => { const m = document.querySelector('.mini-player'); if (!m || m.hidden) return null; const r = m.getBoundingClientRect(); return [r.top, r.bottom, innerHeight]; }")
    check(dev, 'playing shows the floating stop control in view', mini and mini[0] >= 0 and mini[1] <= mini[2], mini)
    btn = pg.inner_html('#playAll')
    check(dev, 'play button turns into a stop button', '停止' in btn and '<rect' in btn, btn[:120])
    if mini:
        pg.click('.mini-player .stop')
        pg.wait_for_timeout(150)
    check(dev, 'stop hides the control', pg.evaluate("() => { const m = document.querySelector('.mini-player'); return !m || m.hidden; }"))
    if not touch:
        pg.keyboard.press('Space'); pg.wait_for_timeout(200)
        check(dev, 'Space starts playback (desktop)', '停止' in pg.inner_html('#playAll'))
        pg.keyboard.press('Space'); pg.wait_for_timeout(150)

    # ---- read: the ✦ of every sentence sits on the same line as the sentence's last word
    go(pg, f'#/m/{PID}/read')
    bad = pg.evaluate("""() => [...document.querySelectorAll('#reader [data-ex]')].filter(b => {
        const w = b.parentElement.querySelector('.w'); if (!w) return false;
        return Math.abs(b.getBoundingClientRect().top - w.getBoundingClientRect().top) > 12; }).length""")
    check(dev, '✦ never wraps away from its sentence', bad == 0, f'{bad} detached')
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

    # ---- words page: a filter swaps only the list (the header element survives, no flash)
    go(pg, '#/cards')
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
                pg.keyboard.press('1')
            pg.wait_for_timeout(300)
            check(dev, 'know (swipe right / key 1) reveals the answer', pg.query_selector('.open-card') is not None) if step < 2 else None
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
    for _ in range(3):
        if not pg.query_selector('#aNext'):
            break
        for box in range(2):
            pg.click(f'.gq >> nth={box} >> .ans >> nth=0')
        pg.click('#aNext'); pg.wait_for_timeout(600)
    h = pg.text_content('#view h1') or ''
    check(dev, 'radar: the reading check ends with a level and a score', '分' in h and '约' in h, h)
    go(pg, '#/radar'); pg.wait_for_timeout(900)
    rd = pg.evaluate("() => ({axes: document.querySelectorAll('.radar .ax').length, dots: document.querySelectorAll('.radar .dt:not(.none)').length, shown: document.querySelector('.radar .cur').classList.contains('on'), rows: document.querySelectorAll('.rdim').length})")
    check(dev, 'radar: six axes, the measured skill drawn against the goal', rd['axes'] == 6 and rd['dots'] >= 1 and rd['shown'] and rd['rows'] == 6, rd)
    go(pg, '#/radar/test/writing')
    pg.fill('#aText', 'I would like to learn to cook because I live alone now and I want to eat better food every day. ' * 3)
    pg.click('#aGo'); pg.wait_for_timeout(1200)
    h = pg.text_content('#view h1') or ''
    check(dev, 'radar: a short text is judged and recorded', '约 B1' in h, h)

    # ---- welcome: the next button is reachable without scrolling on a phone
    go(pg, '#/welcome/edit')
    nb = pg.evaluate("() => { const r = document.getElementById('wNext').getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom), innerHeight]; }")
    check(dev, 'welcome: next button is on screen', nb[1] <= nb[2] and nb[0] >= 0, nb)
    cols = pg.evaluate("() => getComputedStyle(document.querySelector('.choice.opts')).gridTemplateColumns.split(' ').length")
    check(dev, 'welcome: level cards in 1 column on phones, 2 on wide screens', cols == (1 if opts['viewport']['width'] < 600 else 2), cols)

    # ---- account email, exam word lists, import topic
    go(pg, '#/me'); pg.wait_for_function("() => !document.querySelector('#acctEmail .spin')", timeout=5000)
    check(dev, 'me: email row says whether one is bound', len((pg.text_content('#acctEmail') or '').strip()) > 0, pg.text_content('#acctEmail'))
    go(pg, '#/vocab/plan')
    pg.click('#impBook'); pg.wait_for_selector('#impText', timeout=4000)
    check(dev, 'plan: 专四/专八 entry opens the word-list import', pg.is_visible('#impText'))
    pg.evaluate("document.querySelector('#sheet [data-close]').click()")
    go(pg, '#/import')
    check(dev, 'import: a topic can be chosen', pg.evaluate("() => document.querySelectorAll('#impF select[name=theme] option').length") >= 7)

    # ---- library: filters are remembered after opening a material and coming back
    go(pg, '#/library')
    pg.select_option('#fl', 'B2'); pg.wait_for_timeout(500)
    pg.click('#lib a >> nth=0'); settle(pg)
    pg.go_back(); settle(pg)
    check(dev, 'library keeps its filter after going back', pg.input_value('#fl') == 'B2', pg.input_value('#fl'))

    check(dev, 'no script errors', not [e for e in errors if 'Failed to load resource' not in e], errors[:5])
    ctx.browser.close()


def main():
    with sync_playwright() as pw:
        for dev, opts in DEVICES.items():
            if ONLY and dev not in ONLY:
                continue
            try:
                run_device(pw, dev, opts)
            except Exception:
                check(dev, 'device run finished', False, traceback.format_exc()[-600:])
    failed = [r for r in RESULTS if not r['ok']]
    (OUT / 'ui-report.json').write_text(json.dumps({'total': len(RESULTS), 'failed': failed, 'results': RESULTS}, ensure_ascii=False, indent=1))
    print(f'\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed; screenshots and ui-report.json in {OUT}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
