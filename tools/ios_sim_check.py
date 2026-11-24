#!/usr/bin/env python3
"""The iPhone checklist (iphone-test.md) in the iOS Simulator, on the real WebKit: the home-screen app's back button,
Dynamic Island and home bar, dark mode, landscape, the on-screen keyboard, word sound and the lock-screen title, and
the microphone sheet.

    python3 tools/ios_sim_check.py OUT [--udid UDID] [--safari] [--only shell,keyboard,audio,mic,update]

It talks to the simulator's Web Inspector socket (the one Safari's Develop menu uses): it reaches the home-screen app
as well as Safari, which safaridriver cannot. A tap in the page is a click with `emulateUserGesture`, so the keyboard
comes up, sound may play and the microphone may be asked for, as after a finger. Screenshots: `xcrun simctl io`.

Before a run (fixed steps, once per simulator; a Claude session does them with the iOS Simulator tool):
  1. Boot it, open https://flow.jasa.hk in Safari, ≡ → 分享 (Share) → View More → 添加到主屏幕 (Add to Home Screen) → 添加.
     「Open as Web App」 stays on. The hardware keyboard stays disconnected (I/O → Keyboard), so the real one shows.
  2. Tap the new 「语流内测」 icon. The script finds that app (com.apple.SafariViewService) and, on the first-visit page,
     goes on as a guest (日常交流, B1). It never signs in on the beta: pages that need an account are reported as
     skipped. Those run against the local test server instead, signed in as its fixture learner by cookie:
       python3 tools/ui_server.py 8766 STATE &   then add http://localhost:8766 to the home screen the same way, and
       python3 tools/ios_sim_check.py OUT --host localhost:8766 --ui-server STATE[:learner] --only shell,keyboard
  3. For landscape, turn the simulator first and run `--only shell` again (the checks that depend on it see it).
  4. The keyboard: iOS raises it for a focus from a script only after one real tap in a field since the app opened;
     if it does not come, the script prints where to tap and waits up to 60 s.
  5. `--only mic`: iOS asks for the microphone in a system alert, which a page cannot answer: the script waits up to
     60 s for 「允许」 (Allow) to be tapped. The simulator draws no orange dot; the check is that no microphone track
     is left live after the recording (the dot shows exactly while one is).

What a simulator cannot tell (only a phone): a word's first sound being cut, earpiece vs loudspeaker, the ringer
switch, a phone call interrupting playback, the lock-screen buttons (the simulator draws none), mail.

Exit status 1 when a check fails. OUT gets <device>-report.md / .json (parts run separately add up) and screenshots.
"""
import json, os, plistlib, socket, struct, subprocess, sys, time, uuid, zlib
from pathlib import Path

ARGS = sys.argv[1:]
if not ARGS or ARGS[0].startswith('-'):
    sys.exit(__doc__)
OUT = Path(ARGS[0]); OUT.mkdir(parents=True, exist_ok=True)
def opt(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default
UDID = opt('--udid', 'booted')
ONLY = set((opt('--only') or 'shell,keyboard,audio,mic,update').split(','))
HOST = opt('--host', 'flow.jasa.hk')
BUNDLE = 'com.apple.mobilesafari' if '--safari' in ARGS else 'com.apple.SafariViewService'

RESULTS = []
def check(group, name, ok, detail=None, shot=None):
    RESULTS.append({'group': group, 'name': name, 'ok': bool(ok), 'detail': detail, 'shot': shot})
    print(('  ok  ' if ok else 'FAIL  ') + f'[{group}] {name}' + ('' if ok else f'  -> {json.dumps(detail, ensure_ascii=False)[:300]}'), flush=True)
def skip(group, name, why):
    RESULTS.append({'group': group, 'name': name, 'ok': None, 'detail': why})
    print(f'skip  [{group}] {name}  ({why})', flush=True)


# ---------------------------------------------------------------- the simulator
def simctl(*a, **kw):
    return subprocess.run(['xcrun', 'simctl', *a], capture_output=True, text=True, **kw)

def device():
    out = json.loads(simctl('list', 'devices', '-j').stdout)
    for runtime, devs in out['devices'].items():
        for d in devs:
            if (UDID == 'booted' and d['state'] == 'Booted') or d['udid'] == UDID:
                return {'udid': d['udid'], 'name': d['name'], 'runtime': runtime.rsplit('.', 1)[-1]}
    sys.exit(f'no simulator {UDID!r} booted')

def shot(name):
    path = OUT / f'{DEV_TAG}-{name.replace(" ", "-")}.png'
    simctl('io', DEV['udid'], 'screenshot', str(path))
    return path.name

def appearance(mode):
    simctl('ui', DEV['udid'], 'appearance', mode)

def png_rows(path, upto):
    """The first `upto` rows of an 8-bit RGB(A) PNG as lists of (r, g, b) — enough for the status bar."""
    data = Path(path).read_bytes(); pos = 8; idat = b''; w = h = 0; ch = 4
    while pos < len(data):
        n = struct.unpack('>I', data[pos:pos + 4])[0]; kind = data[pos + 4:pos + 8]; body = data[pos + 8:pos + 8 + n]; pos += 12 + n
        if kind == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', body[:10]); ch = {2: 3, 6: 4}[ctype]
        elif kind == b'IDAT':
            idat += body
    raw = zlib.decompressobj().decompress(idat, (w * ch + 1) * upto + 1)
    stride = w * ch; prev = bytearray(stride); rows = []
    for y in range(min(upto, h)):
        f = raw[y * (stride + 1)]; line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0; b = prev[i]; c = prev[i - ch] if i >= ch else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * ch:x * ch + 3]) for x in range(w)]); prev = line
    return rows


# ---------------------------------------------------------------- Web Inspector (webinspectord_sim)
class RWI:
    def __init__(self):
        path = simctl('getenv', DEV['udid'], 'RWI_LISTEN_SOCKET').stdout.strip()
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.s.connect(path)
        self.conn = str(uuid.uuid4()).upper(); self.buf = b''; self.apps = {}; self.listing = {}
        self.send('_rpc_reportIdentifier:', {})

    def send(self, sel, arg):
        data = plistlib.dumps({'__selector': sel, '__argument': dict(arg, WIRConnectionIdentifierKey=self.conn)}, fmt=plistlib.FMT_BINARY)
        self.s.sendall(struct.pack('>I', len(data)) + data)

    def recv(self, timeout):
        self.s.settimeout(timeout)
        while len(self.buf) < 4 or len(self.buf) < 4 + struct.unpack('>I', self.buf[:4])[0]:
            chunk = self.s.recv(1 << 20)
            if not chunk: raise EOFError('inspector socket closed')
            self.buf += chunk
        n = struct.unpack('>I', self.buf[:4])[0]; msg = plistlib.loads(self.buf[4:4 + n]); self.buf = self.buf[4 + n:]
        sel, arg = msg.get('__selector'), msg.get('__argument', {})
        if sel == '_rpc_reportConnectedApplicationList:': self.apps = arg.get('WIRApplicationDictionaryKey', {})
        elif sel == '_rpc_applicationConnected:': self.apps[arg['WIRApplicationIdentifierKey']] = arg
        elif sel == '_rpc_applicationDisconnected:': self.apps.pop(arg.get('WIRApplicationIdentifierKey'), None)
        elif sel == '_rpc_applicationSentListing:': self.listing[arg['WIRApplicationIdentifierKey']] = arg.get('WIRListingKey', {})
        return sel, arg

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            try: self.recv(max(0.05, end - time.time()))
            except (socket.timeout, TimeoutError): break

    def page(self, host, bundle, wait=20):
        end = time.time() + wait
        while time.time() < end:
            self.pump(0.6); self.listing = {}
            for aid, a in self.apps.items():
                if a.get('WIRApplicationBundleIdentifierKey') == bundle:
                    self.send('_rpc_forwardGetListing:', {'WIRApplicationIdentifierKey': aid})
            self.pump(0.8)
            for aid, l in self.listing.items():
                for key, p in l.items():
                    if p.get('WIRTypeKey') == 'WIRTypeWebPage' and host in (p.get('WIRURLKey') or ''):
                        return Page(self, aid, p.get('WIRPageIdentifierKey', int(key)))
        return None


class Page:
    def __init__(self, r, app, page):
        self.r, self.app, self.pid, self.login = r, app, page, False; self.sender = str(uuid.uuid4()).upper(); self.mid = 0; self.target = None
        r.send('_rpc_forwardSocketSetup:', {'WIRApplicationIdentifierKey': app, 'WIRPageIdentifierKey': page, 'WIRSenderKey': self.sender, 'WIRAutomaticallyPause': False})
        end = time.time() + 5
        while time.time() < end and not self.target:
            for m in self._msgs(0.5):
                if m.get('method') == 'Target.targetCreated' and m['params']['targetInfo'].get('type') == 'page':
                    self.target = m['params']['targetInfo']['targetId']

    def _msgs(self, timeout):
        try: sel, arg = self.r.recv(timeout)
        except (socket.timeout, TimeoutError): return []
        if sel == '_rpc_applicationSentData:' and arg.get('WIRDestinationKey') == self.sender:
            return [json.loads(arg['WIRMessageDataKey'])]
        return []

    def cmd(self, method, params=None, timeout=20):
        self.mid += 1; mid = self.mid; inner = {'id': mid, 'method': method, 'params': params or {}}
        msg = inner
        if self.target:
            self.mid += 1; msg = {'id': self.mid, 'method': 'Target.sendMessageToTarget', 'params': {'targetId': self.target, 'message': json.dumps(inner)}}
        self.r.send('_rpc_forwardSocketData:', {'WIRApplicationIdentifierKey': self.app, 'WIRPageIdentifierKey': self.pid, 'WIRSenderKey': self.sender,
                                                'WIRSocketDataKey': json.dumps(msg).encode()})
        end = time.time() + timeout
        while time.time() < end:
            for m in self._msgs(0.5):
                if m.get('method') == 'Target.dispatchMessageFromTarget': m = json.loads(m['params']['message'])
                if m.get('id') == mid:
                    if 'error' in m: raise RuntimeError(m['error'])
                    return m.get('result')
        raise TimeoutError(method)

    def js(self, expr, gesture=False, timeout=20):
        """Evaluate once; a promise is awaited (WebKit has its own command for that), an object comes back as JSON."""
        res = self.cmd('Runtime.evaluate', {'expression': expr, 'emulateUserGesture': gesture}, timeout)
        if res.get('wasThrown'): raise RuntimeError(res['result'].get('description'))
        o = res['result']
        if o.get('className') == 'Promise':
            res = self.cmd('Runtime.awaitPromise', {'promiseObjectId': o['objectId'], 'returnByValue': True}, timeout)
            if res.get('wasThrown'): raise RuntimeError(res['result'].get('description'))
            return res['result'].get('value')
        if o.get('objectId'):
            res = self.cmd('Runtime.callFunctionOn', {'objectId': o['objectId'], 'functionDeclaration': 'function () { return this; }', 'returnByValue': True}, timeout)
            return res['result'].get('value')
        return o.get('value')

    def reload(self, settle=3):
        """Reload the page and follow it to its new inspector target."""
        self.js('setTimeout(() => location.reload(), 50)'); old = self.target; end = time.time() + 15
        while time.time() < end and self.target == old:
            for m in self._msgs(0.5):
                if m.get('method') == 'Target.targetCreated' and m['params']['targetInfo'].get('type') == 'page':
                    self.target = m['params']['targetInfo']['targetId']
                elif m.get('method') == 'Target.didCommitProvisionalTarget':
                    self.target = m['params']['newTargetId']
        self.until("document.readyState === 'complete' && !!document.querySelector('.bar')", 10); time.sleep(settle)
        self.no_login()

    def until(self, expr, secs=10, every=0.4):
        end = time.time() + secs; v = None
        while time.time() < end:
            v = self.js(expr)
            if v: return v
            time.sleep(every)
        return v

    def go(self, hash_, settle=1.2):
        self.js(f'location.hash = {json.dumps(hash_)}')
        self.until("!document.querySelector('#view .skel, #view .skeleton')", 8); time.sleep(settle)
        self.login = self.no_login()

    def no_login(self):
        """A page that needs an account opens the sign-in sheet: 先不登录 (the script stays a guest). True if it was there."""
        up = self.js("(c => !!c && !document.getElementById('sheet').hidden && /登录语流/.test(c.innerText))(document.getElementById('sheetCard'))")
        if up:
            self.js("[...document.querySelectorAll('#sheetCard button')].find(b => b.textContent.includes('先不登录'))?.click()"); time.sleep(0.8)
        return bool(up)

    def tap(self, selector_or_text, settle=0.8):
        """A click that counts as the learner's tap. A CSS selector, or text: the last visible button/link that has it."""
        js = f"""(q => {{ let el = null; try {{ el = document.querySelector(q); }} catch (e) {{}}
          if (!el || el.offsetParent === null) el = [...document.querySelectorAll('button, a, [role=button]')].filter(e => e.offsetParent !== null && e.textContent.replace(/\\s+/g, '').includes(q.replace(/\\s+/g, ''))).pop();
          if (!el) return null; el.click(); return (el.id ? '#' + el.id : el.tagName) + ' ' + el.textContent.trim().slice(0, 30); }})({json.dumps(selector_or_text)})"""
        got = self.js(js, gesture=True); time.sleep(settle); return got


# ---------------------------------------------------------------- page measurements
METRICS = """(() => { const q = s => document.querySelector(s), cs = getComputedStyle(document.documentElement), px = v => parseFloat(cs.getPropertyValue(v)) || 0;
  const rect = el => { if (!el || el.offsetParent === null) return null; const r = el.getBoundingClientRect(); return {t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height)}; };
  const tabs = [...document.querySelectorAll('.tabs a')].filter(a => a.offsetParent !== null).map(a => a.getBoundingClientRect());
  const back = q('#backBtn'), brand = q('.bar .brand');
  return { hash: location.hash, standalone: navigator.standalone === true, homeApp: document.documentElement.classList.contains('home-app'),
    sat: px('--sat'), sab: px('--sab'), sal: px('--sal'), sar: px('--sar'), w: innerWidth, h: document.documentElement.clientHeight,
    off: screen.height > screen.width === innerHeight > innerWidth ? Math.max(screen.height, screen.width) - Math.max(document.documentElement.clientHeight, innerWidth) : null,
    back: back && !back.hidden ? Object.assign(rect(back) || {}, {label: back.textContent.trim()}) : null, brand: brand && !brand.hidden ? rect(brand) : null,
    tabsN: tabs.length, tabsLow: tabs.length ? Math.round(Math.max(...tabs.map(r => r.bottom))) : null,
    tabsLeft: tabs.length ? Math.round(Math.min(...tabs.map(r => r.left))) : null, tabsRight: tabs.length ? Math.round(Math.max(...tabs.map(r => r.right))) : null,
    view: rect(q('#view')), dark: matchMedia('(prefers-color-scheme: dark)').matches,
    bodyBg: getComputedStyle(document.body).backgroundColor, barBg: getComputedStyle(q('.bar')).backgroundColor,
    theme: (([...document.querySelectorAll('meta[name=theme-color]')].find(m => !m.media || matchMedia(m.media).matches)) || {}).content };
})()"""

def rgb(css):
    import re
    m = re.findall(r'[\d.]+', css or '')
    return tuple(int(float(x)) for x in m[:3]) if len(m) >= 3 else None

def hex_rgb(h):
    h = (h or '').lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else None

def near(a, b, tol=24):
    return a and b and all(abs(x - y) <= tol for x, y in zip(a, b))


def run_shell(p):
    g = 'shell'
    m = p.js(METRICS)
    check(g, 'opened from the home screen: standalone, html.home-app', m['standalone'] and m['homeApp'] or BUNDLE.endswith('mobilesafari'), m)
    land = m['w'] > m['h']
    # the four tabs: the logo, no back button; the logo clear of the status bar / Dynamic Island; tabs above the home bar
    for h0, name in (('#/', 'today'), ('#/practice', 'practice'), ('#/cards', 'cards'), ('#/me', 'me')):
        h = h0 + (' (landscape)' if land else '')
        p.go(h0); m = p.js(METRICS); s = shot(f'tab-{name}' + ('-land' if land else ''))
        clear_top = m['brand'] and (m['brand']['t'] >= m['sat']) and ((m['off'] or 0) + m['brand']['t'] >= 44 or m['sat'] >= 44 or land)
        check(g, f'{h}: logo, no back button', m['brand'] and not m['back'], m, s)
        check(g, f'{h}: logo clear of the status bar / Dynamic Island', clear_top, {'brand': m['brand'], 'sat': m['sat'], 'off': m['off']}, s)
        check(g, f'{h}: tabs above the home bar', m['tabsN'] == 4 and m['tabsLow'] <= m['h'] - m['sab'], {'low': m['tabsLow'], 'limit': m['h'] - m['sab'], 'n': m['tabsN']}, s)
        if land:
            check(g, f'{h}: nothing under the notch side', m['brand']['l'] >= m['sal'] and m['view']['l'] >= m['sal'] and m['view']['r'] <= m['w'] - m['sar']
                  and m['tabsLeft'] >= m['sal'] and m['tabsRight'] <= m['w'] - m['sar'], {k: m[k] for k in ('sal', 'sar', 'w', 'brand', 'view', 'tabsLeft', 'tabsRight')}, s)
    if land:
        return
    # 今日 → today's text: 「‹ 返回」, and back to 今日
    p.go('#/')
    link = p.js("(document.querySelector('#view a[href^=\"#/m/\"]') || {}).getAttribute?.('href') || null")
    p.tap(f'#view a[href="{link}"]', 1.5); m = p.js(METRICS); s = shot('back-today-text')
    p.tap('#backBtn', 1.2); after = p.js('location.hash')
    check(g, '今日 → 今天这篇: 「‹ 返回」 at the top, and it goes back to 今日', m['back'] and m['back']['label'] == '返回' and not m['brand'] and after in ('#/', ''),
          {'page': m['hash'], 'back': m['back'], 'after': after}, s)
    big = m['back'] and m['back']['w'] >= 44 and m['back']['h'] >= 40 and m['back']['t'] >= m['sat']
    check(g, '「‹ 返回」 is at least 44×40 and clear of the top inset', big, m['back'])
    # 练习 → 考试练习 → a type: back twice, one level at a time
    p.go('#/practice')
    exam = p.js("(a => a ? a.getAttribute('href') : null)([...document.querySelectorAll('#view a[href^=\"#/exam\"]')].find(a => a.offsetParent !== null))")
    p.tap(f'#view a[href="{exam}"]', 1.5)
    if p.js("location.hash") == '#/exam':  # no exam chosen yet: the list of exams first
        p.tap('#view a.opt[href^="#/exam/"]', 1.5)
    trail = [p.js('location.hash')]
    typ = p.js("(a => a ? a.getAttribute('href') : null)(document.querySelector('#view a[data-tap=exam-type]'))")
    if typ:
        p.tap(f'#view a[href="{typ}"]', 1.8); trail.append(p.js('location.hash')); s = shot('back-exam-type')
        b1 = p.js(METRICS)['back']; p.tap('#backBtn', 1.2); trail.append(p.js('location.hash'))
        b2 = p.js(METRICS)['back']; p.tap('#backBtn', 1.2); trail.append(p.js('location.hash'))
        while trail[-1] not in ('#/practice',) and len(trail) < 8 and p.js(METRICS)['back']:
            p.tap('#backBtn', 1.2); trail.append(p.js('location.hash'))
        ok = trail[2] == trail[0] and '#/practice' in trail[3:] and b1 and b1['label'] == '返回' and b2 and b2['label'] == '返回'
        check(g, '练习 → 考试练习 → 题型: 返回 twice goes back one level at a time', ok, {'trail': trail, 'back1': b1, 'back2': b2}, s)
    else:
        check(g, '练习 → 考试练习 → 题型 reachable', False, {'trail': trail, 'view': p.js("document.querySelector('#view').innerText.slice(0, 200)")})
    # 单词 → 测词汇量
    p.go('#/cards')
    t = p.js("(a => a ? a.getAttribute('href') : null)([...document.querySelectorAll('#view a[href^=\"#/vocab/test\"]')].find(a => a.offsetParent !== null))")
    p.tap(f'#view a[href="{t}"]' if t else '#nope', 1.5) if t else p.go('#/vocab/test')
    m = p.js(METRICS); s = shot('back-vocab-test')
    check(g, '单词 → 测词汇量: 「‹ 返回」 at the top (not only the logo)', m['back'] and not m['brand'] and m['hash'].startswith('#/vocab/test'), {'back': m['back'], 'hash': m['hash'], 'via link': bool(t)}, s)
    p.tap('#backBtn', 1.2); check(g, '测词汇量 → 返回 goes back to 单词', p.js('location.hash') == '#/cards' or not t, p.js('location.hash'))
    # review: the tabs fold away; the back button is still there
    p.go('#/cards'); p.go('#/review', 2)
    if p.login:
        skip(g, '复习: tabs folded away, 「‹ 返回」 still there', 'needs an account (登录后才能复习)')
    else:
        m = p.js(METRICS); s = shot('review')
        check(g, '复习: tabs folded away, 「‹ 返回」 still at the top', m['back'] and m['tabsN'] == 0, {'back': m['back'], 'tabs': m['tabsN']}, s)
        p.tap('#backBtn', 1.2); check(g, '复习 → 返回 leaves the review', p.js('location.hash') != '#/review', p.js('location.hash'))
    # dark and light: the status-bar strip has the page's own colour (no white band). iOS paints that strip from the
    # page when it loads, so both are checked: the phone switched while the app is open, and after a reload (= opened
    # afresh in that mode).
    def strip_check(mode, when):
        m = p.js(METRICS); s = shot(f'statusbar-{mode}-{when}')
        rows = png_rows(OUT / s, 60); scale = len(rows[0]) / m['w']
        strip = rows[int(8 * scale)][int(20 * scale)]
        page = hex_rgb(m['theme']) or rgb(m['bodyBg'])
        check(g, f'{mode} mode, {when}: the status bar strip has the page colour (no white or black band)', m['dark'] == (mode == 'dark') and near(strip, page, 28),
              {'strip_px': strip, 'page': m['theme']}, s)
    p.go('#/')
    start = 'dark' if p.js(METRICS)['dark'] else 'light'
    for mode in (('light', 'dark') if start == 'dark' else ('dark', 'light')):
        appearance(mode); time.sleep(2.5)
        strip_check(mode, 'switched while open')
        p.reload(); strip_check(mode, 'after a reload')


FIELDS = [  # (name, page, start button or None, field, its button)
    ('仿写 (用出来)', '#/m/{pid}/output', None, '#ans', '#go'),
    ('写作', '#/m/{pid}/output/essay', None, '#esIn', '#esGo'),
    ('对话 (先点开始对话)', '#/m/{pid}/output/dialog', '#dlgStart', '#dlgText', '#dlgSend'),
    ('导入文章', '#/import', None, 'textarea[name=text]', '#view form .btn.primary'),
]
KB = """(([f, b]) => { const vv = visualViewport, el = document.querySelector(f), bt = document.querySelector(b);
  if (!el) return null; const shift = scrollY - vv.pageTop;  // client rects → the visible part, both before and after iOS 26
  const vis = x => x && x.offsetParent !== null ? (r => [Math.round(r.top + shift), Math.round(r.bottom + shift)])(x.getBoundingClientRect()) : null;
  return {kbUp: document.documentElement.clientHeight - vv.height > 150, visible: Math.round(vv.height), field: vis(el), button: vis(bt), buttonText: bt && bt.textContent.trim(),
          focused: document.activeElement === el, kbVar: getComputedStyle(document.documentElement).getPropertyValue('--kb'), kbOpen: document.body.classList.contains('kb-open')}; })"""

def keyboard_case(p, g, name, field, button, sheet=False):
    p.js(f"document.querySelector({json.dumps(field)}).scrollIntoView({{block: 'center'}})")
    p.js(f"document.querySelector({json.dumps(field)}).focus()", gesture=True)
    up = f"({KB})({json.dumps([field, button])}).kbUp"
    if not p.until(up, 3):
        # iOS raises the keyboard for a focus from a script only once a finger has put the app in a field: one real tap
        pt = p.js(f"""(r => [Math.round(r.left + r.width / 2), Math.round(screen.height - document.documentElement.clientHeight + r.top + Math.min(r.height / 2, 30))])(document.querySelector({json.dumps(field)}).getBoundingClientRect())""")
        print(f'      … no keyboard from a script yet: tap the field at {pt[0]},{pt[1]} (points) in the simulator; waiting up to 60 s', flush=True)
        p.until(up, 60, 0.5)
    time.sleep(1.2)
    k = p.js(f"({KB})({json.dumps([field, button])})")
    # Where things are on the screen is told by the screenshot, not the page: iOS 26+ may move the whole web view up
    # for the keyboard without telling the page (scrollY 0, the field's client rect unchanged). The field is outlined
    # cyan and its button magenta; each counts as in sight when both its top and bottom edges show above the keyboard.
    mark = """(([f, b, on]) => [[f, 'rgb(0,255,255)'], [b, 'rgb(255,0,255)']].forEach(([q, c]) => { const el = document.querySelector(q); if (!el) return;
      if (on) { el.style.setProperty('outline', '4px solid ' + c, 'important'); el.style.setProperty('outline-offset', '0px', 'important'); } else { el.style.removeProperty('outline'); el.style.removeProperty('outline-offset'); } }))"""
    p.js(f"{mark}({json.dumps([field, button, True])})"); time.sleep(0.4)
    s = shot('kb-' + ''.join(c for c in name if c.isalnum() or c in '-_')[:12])
    p.js(f"{mark}({json.dumps([field, button, False])})")
    widths = p.js(f"[{json.dumps(field)}, {json.dumps(button)}].map(q => (e => e ? e.getBoundingClientRect().width : 0)(document.querySelector(q)))")
    seen = edges_in_sight(OUT / s, widths, DEV_W)
    ok = bool(k and k['kbUp'] and k['focused'] and seen['field'] and seen['button'])
    check(g, f'{name}: the field and 「{(k or {}).get("buttonText")}」 in sight above the real keyboard', ok, dict(seen, page=k), s)
    p.js('document.activeElement && document.activeElement.blur()'); p.until('document.documentElement.clientHeight - visualViewport.height < 50', 4)


def edges_in_sight(png, widths, width_pt):
    """In a screenshot: does the cyan outline (field) and the magenta one (button) show both a top and a bottom edge?
    The keyboard is drawn over the page, so an edge under it does not show. Read at one pixel per point (sips)."""
    small = png.with_name('.edges.png')
    subprocess.run(['sips', '--resampleWidth', str(width_pt), str(png), '--out', str(small)], capture_output=True)
    rows = png_rows(small, 10 ** 6); small.unlink()
    out = {}
    for key, w, test in (('field', widths[0], lambda r, g, b: r < 90 and g > 190 and b > 190), ('button', widths[1], lambda r, g, b: r > 190 and g < 90 and b > 190)):
        lines = [y for y, row in enumerate(rows) if sum(1 for px in row if test(*px)) >= 0.6 * w]
        runs = [y for i, y in enumerate(lines) if i == 0 or y - lines[i - 1] > 2]  # first row of each horizontal edge
        out[key] = len(runs) >= 2 and runs[-1] - runs[0] >= 12
        out[key + '_edges'] = runs[:4]
    return out


def run_keyboard(p, pid):
    g = 'keyboard'
    for name, page, start, field, button in FIELDS:
        p.go(page.format(pid=pid), 1.5)
        if p.login:
            skip(g, name, 'needs an account (the script stays a guest)'); continue
        if start:
            p.tap(start, 2)
            if p.no_login():
                skip(g, name, 'needs an account (the script stays a guest)'); continue
            p.until(f"!!document.querySelector({json.dumps(field)}) && document.querySelector({json.dumps(field)}).offsetParent !== null", 15)
        if not p.js(f"!!document.querySelector({json.dumps(field)})"):
            skip(g, name, 'field not on the page for a guest: ' + (p.js("document.querySelector('#view').innerText.slice(0, 80)") or '')); continue
        keyboard_case(p, g, name, field, button)
    # 背词计划 → 导入老师给的词表: the sheet stands on the keyboard
    p.go('#/vocab/plan', 1.5)
    if p.js("!!document.querySelector('#impBook')"):
        p.tap('#impBook', 1.5)
        if p.js("!!document.querySelector('#impText')"):
            keyboard_case(p, g, '背词计划 → 导入词表 (sheet)', '#impText', '#impGo', sheet=True)
            p.js("document.querySelector('#sheet [data-close], #sheetClose')?.click()")
        else:
            p.no_login(); skip(g, '背词计划 → 导入词表', 'needs an account')
    else:
        skip(g, '背词计划 → 导入词表', 'needs an account' if p.login else 'no 导入 button for a guest')


HOOK = """(() => { if (window.__au) return 'hooked'; const log = window.__au = [];
  const P = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { const src = (this.currentSrc || this.src || '').replace(location.origin, ''); log.push({k: 'element', src, t: Math.round(performance.now())}); const r = P.apply(this, arguments);
    if (r && r.then) r.then(() => log.push({k: 'element-playing', src, t: Math.round(performance.now())}), e => log.push({k: 'element-refused', e: e.name, src})); return r; };
  const S0 = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function () { log.push({k: 'webaudio-start', ctx: this.context.state, secs: this.buffer && +this.buffer.duration.toFixed(2), t: Math.round(performance.now())}); return S0.apply(this, arguments); };
  const G = navigator.mediaDevices && navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices); window.__streams = [];
  if (G) navigator.mediaDevices.getUserMedia = c => G(c).then(s => { window.__streams.push(s); log.push({k: 'mic-open'}); return s; }, e => { log.push({k: 'mic-refused', e: e.name}); throw e; });
  addEventListener('error', e => log.push({k: 'error', m: String(e.message)}), true);
  return 'hooked'; })()"""
NOW = "({ title: navigator.mediaSession && navigator.mediaSession.metadata && navigator.mediaSession.metadata.title, state: navigator.mediaSession && navigator.mediaSession.playbackState, session: navigator.audioSession && navigator.audioSession.type, log: window.__au || [] })"

def refused(e):
    """A sound the browser would not play, or a script error. AbortError is a play() cut off by pause()/load(): the
    unlock silence on the first tap (01-audio-offline.js) and a word cut by the next tap end that way on purpose."""
    return e['k'] == 'error' or (e['k'] == 'element-refused' and e.get('e') != 'AbortError')


def run_audio(p, pid):
    g = 'audio'
    p.reload(); p.js(HOOK)  # a fresh page: no sound cached in it yet, as after opening the app
    p.go('#/sounds', 1)
    grp = p.js("(a => a ? a.getAttribute('href') : null)(document.querySelector('#view a[href^=\"#/sounds/\"]'))")
    if grp: p.go(grp, 1.5)
    btns = p.js("[...document.querySelectorAll('#view [data-play]')].slice(0, 5).map(b => b.dataset.play)") or []
    if len(btns) < 5:
        skip(g, 'word sound', 'fewer than 5 word buttons on ' + str(grp))
    else:
        # 我的 → 设置 → 单词读音方式: 连续 (Web Audio, the default) and 标准 (short <audio> clips with silence in front)
        for mode, key in (('连续', None), ('标准', 'compat')):
            p.js(f"localStorage.setItem('flow-audio', {json.dumps(json.dumps(key))}); window.__au.length = 0")
            titles = []; waits = []
            for b in btns:  # five words, one after another: each one should sound, and soon after the tap
                n0 = len(p.js('window.__au')); t0 = p.js('performance.now()')
                p.tap(f'#view [data-play="{b}"]', 0.1); titles.append(p.js(NOW)['title'])
                hit = p.until(f"(window.__au.slice({n0}).find(e => e.k === 'webaudio-start' || e.k === 'element-playing') || {{}}).t", 5, 0.1)
                waits.append(round(hit - t0) if hit else None); time.sleep(0.9)
            now = p.js(NOW); s = shot(f'word-sound-{"auto" if key is None else key}')
            bad = [e for e in now['log'] if refused(e)]
            check(g, f'{mode}: five words, each one plays (ms from tap to sound: {waits}), no error', all(w is not None for w in waits) and not bad,
                  {'ms': waits, 'errors': bad, 'log': now['log'][-6:]}, s)
            # a learner taps the next word before the last has loaded: the newer one wins, nothing piles up
            p.js('window.__au.length = 0')
            for b in btns:
                p.tap(f'#view [data-play="{b}"]', 0.15)
            time.sleep(3); quick = [e['k'] for e in p.js('window.__au') if e['k'] in ('webaudio-start', 'element-playing')]
            check(g, f'{mode}: five quick taps (0.15 s apart): the last word plays, no pile-up of sounds', 1 <= len(quick) <= 5 and not [e for e in p.js('window.__au') if refused(e)], quick)
            if key is None:
                check(g, f'{mode}: the island / lock screen stays 「语流 · 单词」 across the five', all(t == '语流 · 单词' for t in titles) and now['title'] == '语流 · 单词', titles)
                check(g, f'{mode}: the session is playback (the ringer switch does not mute it)', now['session'] in ('playback', 'play-and-record'), now['session'])
        p.js("localStorage.removeItem('flow-audio')")
    # 听 → 播放全文: the lock screen shows the text's name
    p.go(f'#/m/{pid}/listen', 2)
    title = p.js("(document.querySelector('#view h1, #view .h1, #view h2') || {}).textContent || ''").strip()
    p.js('window.__au.length = 0')
    if p.tap('#playAll', 3):
        now = p.js(NOW); s = shot('play-all')
        check(g, '播放全文: plays, and the lock screen is named 「语流 · 文章名」', now['state'] == 'playing' and (now['title'] or '').startswith('语流 · ') and now['title'] != '语流 · 单词',
              {'page title': title, 'now': {k: now[k] for k in ('title', 'state', 'session')}, 'log': now['log'][-3:]}, s)
        p.tap('#playAll', 0.8)
    else:
        skip(g, '播放全文', 'no #playAll on ' + f'#/m/{pid}/listen')


def run_mic(p):
    g = 'mic'
    p.reload(); p.js(HOOK); p.go('#/', 1.5)
    p.js("try { localStorage.removeItem('flow-mic-explained') } catch (e) {}")
    p.tap('跟读', 1.2)
    if not p.js("!!document.querySelector('#lsRec')"):
        skip(g, 'recording', 'no 跟读 ● on 今日 for a guest'); return
    p.tap('#lsRec', 1.2); sheet = p.js("(document.getElementById('sheetTitle') || {}).textContent || null"); s = shot('mic-explain')
    check(g, 'first ● on this phone: the line 「要用一下麦克风」 comes before the system asks', sheet == '要用一下麦克风', sheet, s)
    if sheet != '要用一下麦克风': return
    p.tap('#micGo', 1)
    print('      … waiting up to 60 s for 「允许」 / Allow in the system alert (tap it in the simulator)', flush=True)
    on = p.until("document.querySelector('#lsRec').classList.contains('on') || (window.__au || []).some(e => e.k === 'mic-refused')", 60, 0.5)
    s = shot('mic-recording')
    rec = p.js("document.querySelector('#lsRec').classList.contains('on')")
    check(g, 'recording starts after 允许 (● turns on)', rec, p.js(NOW)['log'], s)
    if not rec: return
    time.sleep(2); p.tap('#lsRec', 1.5)
    st = p.js("({on: document.querySelector('#lsRec').classList.contains('on'), live: (window.__streams || []).flatMap(s => s.getTracks()).filter(t => t.readyState === 'live').length, session: navigator.audioSession && navigator.audioSession.type})")
    s = shot('mic-after')
    check(g, 'after the recording the microphone is let go (no live track: the orange dot goes), the session back to playback', not st['on'] and st['live'] == 0 and st['session'] == 'playback', st, s)


def run_update(p):
    """A newer version on the server, played by answering /api/version with another asset (the page's own logic, on the
    real WebKit; the real thing — the next beta while the app sleeps — is in the checklist)."""
    g = 'update'
    fake = """(() => { const F = window.fetch; window.__marker = 1; window.fetch = (u, o) => String(u).includes('/api/version') ? Promise.resolve(new Response('{"asset":"sim-newer"}', {headers: {'Content-Type': 'application/json'}})) : F(u, o); })()"""
    p.go('#/m/{pid}/check'.format(pid=PID), 2); p.js(fake)
    p.js("Object.defineProperty(document, 'visibilityState', {value: 'visible', configurable: true}); document.dispatchEvent(new Event('visibilitychange'))")
    bar = p.until("document.getElementById('updateBar') && document.getElementById('updateBar').innerText", 8); s = shot('update-line')
    check(g, 'a new version while answering questions: one line 「有新版本，点一下更新」, no reload', bar and '有新版本' in bar and p.js('window.__marker === 1'), bar, s)
    p.js("document.querySelector('#updateBar .ub-x')?.click(); try { localStorage.removeItem('flow-update-later'); localStorage.removeItem('flow-update-tried') } catch (e) {}")
    p.reload()  # the page's own fetch back, nothing of the played version left


# ---------------------------------------------------------------- run
DEV = device(); DEV_W = None; DEV_TAG = ''.join(c for c in DEV['name'].lower().replace(' ', '-') if c.isalnum() or c == '-')
print(f"{DEV['name']} ({DEV['runtime']}, {DEV['udid']}), {'Safari' if '--safari' in ARGS else 'home-screen app'}", flush=True)
r = RWI(); p = r.page(HOST, BUNDLE)
if not p:
    sys.exit(f'{HOST} is not open in {BUNDLE} on this simulator (see the steps at the top of this file)')
UI_SERVER = opt('--ui-server')  # STATE[:LEARNER] of tools/ui_server.py: its fixture learner, signed in by cookie (localhost only)
if UI_SERVER:
    if not HOST.split(':')[0] in ('localhost', '127.0.0.1'):
        sys.exit('--ui-server is for the local test server (--host localhost:PORT) only')
    state, _, who = UI_SERVER.partition(':')
    tok = json.loads((Path(state) / 'sessions.json').read_text())['learners'][who or 'home-app']['token']
    p.js(f"document.cookie = 'flow_session={tok}; path=/; SameSite=Lax'"); p.reload()
if p.js("location.hash").startswith('#/welcome'):
    for t in ('留在内测版', '日常交流', 'B1读懂一般文章', '开始学习'):
        p.tap(t, 1)
    time.sleep(2)
p.js("document.querySelector('#sheet:not([hidden]) [data-close]')?.click()")
PID = (p.js("(p => p ? p.split('/')[2] : null)((document.querySelector('#view a[href^=\"#/m/\"]') || {}).getAttribute?.('href'))") if p.js('location.hash') in ('#/', '') else None)
if not PID:
    p.go('#/'); PID = p.js("(p => p ? p.split('/')[2] : null)((document.querySelector('#view a[href^=\"#/m/\"]') || {}).getAttribute?.('href'))")
VERSION = p.js("fetch('/api/version', {cache: 'no-store'}).then(r => r.json()).then(j => j.asset)")
PAGE_ASSET = p.js("((document.querySelector('script[src*=\"/next.js\"]') || {}).src || '').split('v=')[1] || ''")
DEV_W = p.js('screen.width')  # points across a portrait screenshot (iOS keeps screen.width portrait)
print(f'server asset {VERSION}, page asset {PAGE_ASSET}, today\'s text {PID}', flush=True)
for part, fn in (('shell', lambda: run_shell(p)), ('keyboard', lambda: run_keyboard(p, PID)), ('audio', lambda: run_audio(p, PID)),
                 ('mic', lambda: run_mic(p)), ('update', lambda: run_update(p))):
    if part in ONLY:
        print(f'— {part}', flush=True)
        try:
            fn()
        except Exception as e:
            check(part, 'ran to the end', False, repr(e))
appearance('dark' if 'keep-dark' in ARGS else 'light')

meta = {'device': DEV, 'asset': VERSION, 'page_asset': PAGE_ASSET, 'when': time.strftime('%Y-%m-%d %H:%M'), 'app': BUNDLE}
# parts run one at a time add up in one report per device: a check run again replaces its line
rep = OUT / f'{DEV_TAG}-report.json'
try:
    old = json.loads(rep.read_text())['results'] if rep.exists() else []
except ValueError:
    old = []
fresh = {(x['group'], x['name']) for x in RESULTS}
RESULTS = [x for x in old if (x['group'], x['name']) not in fresh] + RESULTS
rep.write_text(json.dumps({'meta': meta, 'results': RESULTS}, ensure_ascii=False, indent=1))
lines = [f"# {DEV['name']} · {DEV['runtime']} · asset {VERSION} · {meta['when']}", '']
for x in RESULTS:
    mark = '✓' if x['ok'] else '–' if x['ok'] is None else '✗'
    lines.append(f"- {mark} [{x['group']}] {x['name']}" + (f" — {x['detail']}" if x['ok'] is None else '') + (f" ({x['shot']})" if x.get('shot') else ''))
(OUT / f'{DEV_TAG}-report.md').write_text('\n'.join(lines) + '\n')
bad = [x for x in RESULTS if x['ok'] is False]
print(f"\n{sum(1 for x in RESULTS if x['ok'])} passed, {len(bad)} failed, {sum(1 for x in RESULTS if x['ok'] is None)} skipped → {OUT}")
sys.exit(1 if bad else 0)
