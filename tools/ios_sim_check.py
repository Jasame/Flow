#!/usr/bin/env python3
"""The iPhone checklist (iphone-test.md) in the iOS Simulator, on the real WebKit: the home-screen app's back button,
Dynamic Island and home bar, dark mode, landscape, the on-screen keyboard, word sound and the lock-screen title, and
the microphone sheet; and the reading (audio-test-plan.md: 听 / 伴读 in the natural voice, 暂停 / 继续 / ✕, where it
was left, offline, the lines while waiting).

    python3 tools/ios_sim_check.py OUT [--udid UDID] [--safari] [--only shell,onescreen,keyboard,audio,mic,update,unify,more]

`unify` and `more` (not run unless asked; about 5 minutes): a guest on the beta takes the text of the day (a recording)
and a 考试练习 result; with --ui-server, the local learner imports three short texts (no recording) and also takes
能力测评听力, a 口语情景 and a 名人名言 今日好句.

Silent (rule 9 in tools/README.md): every sound the page plays is muted on the page's side (elements muted underneath,
Web Audio through a gain of 0, the browser voice at volume 0), so nothing is heard on the Mac; the checks read the
playback state, the media session and the requests.

It talks to the simulator's Web Inspector socket (the one Safari's Develop menu uses): it reaches the home-screen app
as well as Safari, which safaridriver cannot. A tap in the page is a click with `emulateUserGesture`, so the keyboard
comes up, sound may play and the microphone may be asked for, as after a finger. Screenshots: `xcrun simctl io`.

Before a run (fixed steps, once per simulator; a Claude session does them with the iOS Simulator tool):
  1. Boot it, open https://flow.jasa.hk in Safari, ≡ → 分享 (Share) → View More → 添加到主屏幕 (Add to Home Screen) → 添加.
     「Open as Web App」 stays on. The hardware keyboard stays disconnected (I/O → Keyboard), so the real one shows.
  2. Tap the new 「语流内测」 icon. The script finds that app (com.apple.SafariViewService, or com.apple.webapp — 「Web」 in
     the status bar — for an icon added lately on iOS 27.2) and, on the first-visit page,
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
If the script finds no app at all (the inspector answers nothing), the simulator's inspector service is stuck:
    xcrun simctl spawn UDID launchctl kickstart -k user/501/com.apple.webinspectord
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
ONLY = set((opt('--only') or 'shell,onescreen,keyboard,audio,mic,update').split(','))
HOST = opt('--host', 'flow.jasa.hk')
# A home-screen app runs in SafariViewService, or (iOS 27.2, an icon added lately: 「Web」 in the status bar) in com.apple.webapp
BUNDLE = ('com.apple.mobilesafari',) if '--safari' in ARGS else ('com.apple.SafariViewService', 'com.apple.webapp')

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
                if a.get('WIRApplicationBundleIdentifierKey') in bundle:
                    self.send('_rpc_forwardGetListing:', {'WIRApplicationIdentifierKey': aid})
            self.pump(0.8)
            for aid, l in self.listing.items():
                if self.apps.get(aid, {}).get('WIRApplicationBundleIdentifierKey') not in bundle:
                    continue  # Safari sends its own listings unasked: only the app asked for counts
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
        """Reload the page and follow it to its new inspector target. The service worker may answer with the copy it
        kept of an older version, which finds the new one 4 s later and reloads itself when it can (04-home-app.js):
        mid-test that would cut what the test is doing, so the page is reloaded until it is the server's version."""
        self._reload_once(settle)
        for _ in range(3):
            if not globals().get('VERSION') or self.js("((document.querySelector('script[src*=\"/next.js\"]') || {}).src || '').split('v=')[1] || ''") == VERSION:
                break
            self._reload_once(settle)

    def _reload_once(self, settle):
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
        self.until("!document.querySelector('#view .skel, #view .skeleton, #view[data-busy]')", 8); time.sleep(settle)
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
    check(g, 'opened from the home screen: standalone, html.home-app', m['standalone'] and m['homeApp'] or BUNDLE[0].endswith('mobilesafari'), m)
    land = m['w'] > m['h']
    # the four tabs: the logo, no back button; the logo clear of the status bar / Dynamic Island; tabs above the home bar
    for h0, name in (('#/', 'today'), ('#/practice', 'practice'), ('#/cards', 'cards'), ('#/me', 'me')):
        h = h0 + (' (landscape)' if land else '')
        p.go(h0); m = p.js(METRICS); s = shot(f'tab-{name}' + ('-land' if land else ''))
        # the page starts below the status bar (status-bar-style default: off > 0) or keeps the top inset (sat): any
        # height of status bar, notch or Dynamic Island (an iPad's is 24 pt, an iPhone's up to 62)
        clear_top = m['brand'] and m['brand']['t'] >= m['sat'] and ((m['off'] or 0) > 0 or m['sat'] > 0 or land)
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
  // Silent, as the owner asked (2026-11-25: a test in the background makes no sound): every sound is played as the page
  // plays it — its timing, its state, the lock screen — but muted (elements), at gain 0 (Web Audio) or at volume 0 (the
  // browser voice). A muted element is not held to the tap rule, so 「refused」 below is the page's own error only.
  const C0 = AudioNode.prototype.connect;
  AudioNode.prototype.connect = function (dest) { if (dest instanceof AudioDestinationNode) { const c = this.context;
      if (!c.__mute) { c.__mute = c.createGain(); c.__mute.gain.value = 0; C0.call(c.__mute, c.destination); log.push({k: 'muted-context'}); } return C0.apply(this, [c.__mute, ...[].slice.call(arguments, 1)]); }
    return C0.apply(this, arguments); };
  // the page sets muted itself (a clip plays muted until it has jumped to its start): it reads back what it set, the
  // element stays muted underneath
  const MD = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'muted');
  Object.defineProperty(HTMLMediaElement.prototype, 'muted', { configurable: true,
    get() { return this.__want === undefined ? MD.get.call(this) : this.__want; }, set(v) { this.__want = !!v; MD.set.call(this, true); } });
  window.__muted = a => MD.get.call(a);
  const P = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { MD.set.call(this, true); const src = (this.currentSrc || this.src || '').replace(location.origin, ''); log.push({k: 'element', src, t: Math.round(performance.now())}); const r = P.apply(this, arguments);
    if (r && r.then) r.then(() => log.push({k: 'element-playing', src, t: Math.round(performance.now())}), e => log.push({k: 'element-refused', e: e.name, src})); return r; };
  const S0 = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function () { log.push({k: 'webaudio-start', ctx: this.context.state, secs: this.buffer && +this.buffer.duration.toFixed(2), t: Math.round(performance.now())}); return S0.apply(this, arguments); };
  const G = navigator.mediaDevices && navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices); window.__streams = [];
  if (G) navigator.mediaDevices.getUserMedia = c => G(c).then(s => { window.__streams.push(s); log.push({k: 'mic-open'}); return s; }, e => { log.push({k: 'mic-refused', e: e.name}); throw e; });
  addEventListener('error', e => log.push({k: 'error', m: String(e.message)}), true);
  // the browser voice (the robot the learner must not hear unasked), the media elements played, the lines shown while
  // a sentence is made or why the browser voice reads (#lsPrep, #svPrep, #svWait, the toast)
  if (window.speechSynthesis) { const SP = speechSynthesis.speak.bind(speechSynthesis); speechSynthesis.speak = u => { if (u) u.volume = 0; if (u && u.text && u.text.trim()) log.push({k: 'speech', text: u.text, t: Math.round(performance.now())}); return SP(u); }; }  // not the empty unlock line of the first tap
  window.__els = []; const P2 = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { if (!window.__els.includes(this)) window.__els.push(this); return P2.apply(this, arguments); };
  window.__notes = [];
  new MutationObserver(() => { for (const q of ['#lsPrep', '#svPrep', '#svWait', '#aNote', '#toast.show']) { const e = document.querySelector(q);
      const t = e && !e.hidden && e.textContent.trim(); if (t && window.__notes[window.__notes.length - 1] !== t) window.__notes.push(t); } })
    .observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true});
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


# ---------------------------------------------------------------- one screen (the owner's iPhone, 2026-11-25)
def run_onescreen(p):
    """Pages made to fit one screen (复习's card, 测词汇量, 起点小测) fit it on this device, whatever sits above them: the
    top bar with 返回, the 内测版's line, the Dynamic Island. Measured at rest (a card's way in can show a few px)."""
    g = 'onescreen'
    p.js(HOOK)  # silent: a review card says its word as it opens
    for page, sel in (('#/review', '#view .review'), ('#/vocab/test', '#view .review.vtest'), ('#/placement', '#view')):
        p.go(page, 1)
        if p.login:
            skip(g, page, 'needs an account (run with --ui-server)'); continue
        p.js("document.querySelector('#sheet:not([hidden]) [data-close]')?.click()"); time.sleep(0.4)  # the 内测版's once-per-phone sheet
        if not p.until(f"!!document.querySelector({json.dumps(sel)})", 8):
            skip(g, page, 'the page did not open'); continue
        p.until("document.scrollingElement.scrollHeight - innerHeight <= 0", 4, 0.3)
        m = p.js("""({ over: document.scrollingElement.scrollHeight - innerHeight, back: !!document.getElementById('backBtn') && !document.getElementById('backBtn').hidden,
          bar: Math.round(document.getElementById('bar').getBoundingClientRect().height), line: !!document.getElementById('betaBar') })""")
        s = shot(f"one-screen-{page.strip('#/').replace('/', '_')}")
        check(g, f'{page}: fits one screen (no vertical scroll)', m['over'] <= 0, m, s)


# ---------------------------------------------------------------- 朗读统一 (语流 9, #129): audio-test-plan.md
# 听 → 播放全文 and 读 → 伴读 (LONG, 01-audio-offline.js) on the real WebKit: the natural voice, never the browser's
# unasked; 暂停 / 继续 / ✕; where it was left kept per text and per step; the lines while waiting and when offline.
# What only a phone tells (the lock screen's buttons, a phone call) stays in the checklist.
LS = """(() => { const q = s => document.querySelector(s), b = q('#playAll'), m = q('.mini-player'), now = q('#view .line.now'),
  el = (window.__els || []).filter(a => !a.paused).pop() || (window.__els || []).slice(-1)[0];
  return { btn: b ? b.textContent.trim() : null, now: now ? Number(now.dataset.i) : -1,
    mini: !!m && !m.hidden && !m.classList.contains('idle'), lbl: m && !m.hidden && !m.classList.contains('idle') ? (m.querySelector('.lbl') || {}).textContent : null, ms: navigator.mediaSession && navigator.mediaSession.playbackState,
    at: el ? +el.currentTime.toFixed(2) : null, src: el ? (el.currentSrc || el.src || '').replace(location.origin, '').split('?')[0] : null,
    speech: (window.__au || []).filter(e => e.k === 'speech').length, notes: (window.__notes || []).slice(-4) }; })()"""
# mini: the playing bar. On 听 the bar stays docked when idle (#playAll, 「AI 合成」, the speed, 👁) since #325: not playing.
# 从头开始 is in 播放设置 (from 「1×」 in the bar, B9's r36 audit F1): opened, looked at, closed
RS = """(() => { const s = document.querySelector('.mini-player .speed-set'); if (!s) return null; s.click();
  const b = document.getElementById('playRestart'), on = !!b && !b.hidden, d = document.getElementById('psDone'); if (d) d.click(); return on; })()"""


def playset(p, rep):
    """每句 N 遍 from 播放设置: since #325 a sheet opened from the player bar's speed button (the bar stays, docked, on 听)."""
    opened = p.tap('.mini-player:not([hidden]) .speed-set', 0.6) and p.tap(f'#sheetCard [data-rep="{rep}"]', 0.3)
    if not opened:  # the bar has no speed button while a single sentence repeats (停止): stop that first
        raise RuntimeError(f'播放设置 did not open to set 每句 {rep} 遍')
    p.tap('#psDone', 0.5)


RD = """(() => { const b = document.querySelector('#readAlong'), s = document.querySelector('#reader .sent.now');
  return { btn: b ? b.textContent.trim() : null, now: s ? Number(s.dataset.si) : -1, speech: (window.__au || []).filter(e => e.k === 'speech').length }; })()"""
SILENT = "(window.__els || []).every(a => window.__muted(a))"  # every element the page played was muted underneath
SOUNDS = "(window.__au || []).filter(e => (e.k === 'element-playing' && e.src && !e.src.startsWith('data:')) || e.k === 'webaudio-start').length"
PROGRESS = "(k => (JSON.parse(localStorage.getItem('flow-progress') || '{{}}')[k] || {{}}).i)({key})"


def awake(p):
    """A page in the background plays nothing and its media wait: a result from there would mislead."""
    if p.js('document.visibilityState') != 'visible':
        raise RuntimeError('the app is no longer in front (document.visibilityState hidden): put it back and run again')


def fresh_listen(p, aid, clear=True):
    """The text's 听 → 精听, nothing playing; clear: where it was left forgotten (listen and read)."""
    awake(p)
    p.js("document.querySelector('.mini-player:not([hidden]) .close')?.click()")
    if clear:
        p.js(f"(o => {{ delete o['listen:{aid}']; delete o['read:{aid}']; localStorage.setItem('flow-progress', JSON.stringify(o)); }})(JSON.parse(localStorage.getItem('flow-progress') || '{{}}'))")
    p.go('#/', 0.6); p.go(f'#/m/{aid}/listen', 1.5)
    # a server just started (or a text just imported) can take longer than the pause above: wait for the page itself
    p.until("!!document.querySelector('#view .listen-tip, [data-mode=\"listen\"]')", 15, 0.5)
    p.js("document.querySelector('[data-mode=\"listen\"]:not([aria-pressed=true])')?.click()")
    p.until("!!document.querySelector('#playAll')", 10, 0.3); time.sleep(0.3)
    p.js(HOOK); p.js('window.__au.length = 0; window.__notes.length = 0')


def run_unify(p, aid, recorded, extra=None):
    """aid: a text with a recording (recorded=True, the beta's text of the day, a guest) or without one (an import of the
    local test server's learner: extra = {'other': a second import, 'fresh': a third never played, 'scene': a 口语情景 id})."""
    g = 'unify-' + ('recorded' if recorded else 'no-recording')
    kind = '有录音的文章' if recorded else '没有录音的文章'
    p.js("localStorage.removeItem('flow-next-loop')")  # 每句 1 遍, 句后不停: a run stopped half-way may have left 3 遍 (6 sentences × 3 > the wait)
    p.reload(); fresh_listen(p, aid)
    # a recording gives the length in minutes at the foot (21-study-listen.js); the 「AI 合成」 line is in the bar since #325
    foot = p.js("(document.querySelector('#view .section.row .muted.small') || {}).textContent || ''")
    if recorded != ('分钟' in foot):
        check(g, f'{kind}: the page says so', False, foot); return
    # 1① 播放全文: sentence by sentence, the natural voice, a line while a sentence is being made
    t0 = time.time(); p.tap('#playAll', 0.2)
    p.until(LS + '.now >= 2', 45, 0.3); st = p.js(LS); s = shot(f'{g}-playing')
    check(g, f'{kind}: 播放全文 reads on, sentence by sentence, in the natural voice (no browser voice)',
          st['now'] >= 2 and st['speech'] == 0 and p.js(SOUNDS) >= 1 and '暂停' in (st['btn'] or ''), {'state': st, 'secs': round(time.time() - t0, 1)}, s)
    log = p.js('window.__au')
    check(g, 'the test itself is silent: every element the page played muted, Web Audio at gain 0, the browser voice at volume 0',
          p.js(SILENT) and (not any(e['k'] == 'webaudio-start' for e in log) or any(e['k'] == 'muted-context' for e in log)),
          {'elements muted': p.js(SILENT), 'web audio': [e['k'] for e in log if e['k'] in ('webaudio-start', 'muted-context')][:4]})
    # 2① 暂停: the button says 继续, the player 已暂停, the lock screen paused, and it stays where it was
    p.tap('#playAll', 0.6); a = p.js(LS); time.sleep(1.5); b = p.js(LS); s = shot(f'{g}-paused')
    check(g, f'{kind}: 暂停 — the button 继续, the player 已暂停, the lock screen paused, the reading waits',
          '继续' in (a['btn'] or '') and a['lbl'] == '已暂停' and a['ms'] == 'paused' and b['now'] == a['now'] and (not recorded or abs((b['at'] or 0) - (a['at'] or 0)) < 0.05),
          {'paused': a, '1.5 s later': b}, s)
    # 2② 继续: on in the same sentence (a recording: from the second it stopped at), not from the top
    k, at = a['now'], a['at']; p.tap('#playAll', 0.5); c = p.js(LS)
    check(g, f'{kind}: 继续 goes on in the sentence it stopped in' + (' (from the same second)' if recorded else ''),
          c['now'] in (k, k + 1) and '暂停' in (c['btn'] or '') and (not recorded or (c['at'] is not None and at - 0.3 <= c['at'] <= at + 2.5)), {'paused at': [k, at], 'now': c})
    # 2③ the player's own 暂停 / 继续, then ✕: closed, where it was kept
    p.tap('.mini-player .toggle', 0.6); d = p.js(LS); p.tap('.mini-player .toggle', 0.6); e = p.js(LS)
    p.until(LS + '.now >= 0', 10); k2 = p.js(LS)['now']; p.tap('.mini-player .close', 0.6); f = p.js(LS)
    kept = p.js(PROGRESS.format(key=json.dumps(f'listen:{aid}')))
    check(g, f'{kind}: the player — 暂停, 继续, then ✕ closes it and keeps where it was', d['lbl'] == '已暂停' and e['lbl'] not in (None, '已暂停') and not f['mini'] and kept in (k2, k2 + 1 if k2 is not None else None),
          {'paused': d['lbl'], 'resumed': e['lbl'], 'closed': f['mini'], 'kept': kept, 'was at': k2})
    # 3① back on the page later: 「从第 N 句继续」 and 从头开始
    p.go('#/', 0.8); p.go(f'#/m/{aid}/listen', 1.2); p.js("document.querySelector('[data-mode=\"listen\"]:not([aria-pressed=true])')?.click()"); time.sleep(0.4)
    h = p.js(LS); s = shot(f'{g}-continue-from'); h['restart'] = p.js(RS, gesture=True); time.sleep(0.4)
    check(g, f'{kind}: back on the page — 「从第 {(kept or 0) + 1} 句继续」, 从头开始 in 播放设置, nothing playing',
          h['btn'] == f'从第 {(kept or 0) + 1} 句继续' and h['restart'] and not h['mini'], h, s)
    # 3② the app opened again (the page loaded anew): the same
    p.reload(); p.go(f'#/m/{aid}/listen', 1.2); p.js("document.querySelector('[data-mode=\"listen\"]:not([aria-pressed=true])')?.click()"); time.sleep(0.4)
    h2 = p.js(LS); h2['restart'] = p.js(RS, gesture=True); time.sleep(0.4)
    check(g, f'{kind}: after the app loads again — still 「从第 N 句继续」', h2['btn'] == h['btn'] and h2['restart'], h2)
    p.js(HOOK); p.js('window.__au.length = 0; window.__notes.length = 0')
    # 3③ 从第 N 句继续 starts there; 从头开始 at the first
    p.tap('#playAll', 0.3); p.until(LS + '.now >= 0', 30, 0.3); x = p.js(LS)
    p.tap('.mini-player .close', 0.5); p.tap('.mini-player .speed-set', 0.5); p.tap('#playRestart', 0.3); p.until(LS + '.now >= 0', 30, 0.3); y = p.js(LS)
    check(g, f'{kind}: 从第 N 句继续 starts at sentence N, 从头开始 at the first', x['now'] == kept and y['now'] == 0, {'continue': x['now'], 'kept': kept, 'restart': y['now']})
    # 2⑤ a word looked up while it reads: it stops there (已暂停), 继续 goes on
    p.until(LS + '.now >= 1', 30, 0.3); w0 = p.js(LS)
    word = p.js("(w => { if (!w) return null; w.click(); return w.textContent; })(document.querySelector('#view .line.now .txt [data-w]'))", gesture=True); time.sleep(1.5)
    w1 = p.js(LS); sheet = p.js("!document.getElementById('sheet').hidden"); s = shot(f'{g}-lookup')
    p.js("document.querySelector('#sheet [data-close], #sheetCard .close, #sheetCard [aria-label=\"关闭\"]')?.click()"); time.sleep(0.6)
    if sheet: p.js("document.getElementById('sheet').hidden || document.querySelector('#sheet')?.click()")
    p.tap('#playAll', 0.8); w2 = p.js(LS)
    check(g, f'{kind}: looking up a word ({word}) stops the reading there (已暂停); 继续 goes on in that sentence',
          bool(word) and sheet and w1['lbl'] == '已暂停' and w1['now'] == w0['now'] and w2['now'] in (w0['now'], w0['now'] + 1) and '暂停' in (w2['btn'] or ''),
          {'before': w0, 'looking up': w1, 'after 继续': w2}, s)
    p.tap('.mini-player .close', 0.5)
    if recorded:
        # 3⑤ 读 → 伴读 keeps its own place, apart from 听's
        listen_at = p.js(PROGRESS.format(key=json.dumps(f'listen:{aid}')))
        p.go(f'#/m/{aid}/read', 1.5); p.tap('#readAlong', 0.3); p.until(RD + '.now >= 1', 30, 0.3); r1 = p.js(RD)
        p.tap('.mini-player .close', 0.5); p.go('#/', 0.6); p.go(f'#/m/{aid}/read', 1.2); r2 = p.js(RD)
        read_at = p.js(PROGRESS.format(key=json.dumps(f'read:{aid}')))
        check(g, f'{kind}: 伴读 keeps its own place (「从第 N 句继续」), 听\'s left as it was',
              r2['btn'] == f'从第 {(read_at or 0) + 1} 句继续' and read_at == r1['now'] and p.js(PROGRESS.format(key=json.dumps(f'listen:{aid}'))) == listen_at and r1['speech'] == 0,
              {'read': [r1, r2['btn'], read_at], 'listen kept': listen_at})
        return
    # ---- no recording only (an import of the local test server's learner)
    # 1② a sentence's own speaker, and 每句 3 遍: the natural voice each time
    fresh_listen(p, aid, clear=False); n0 = p.js(SOUNDS)
    p.tap('[data-say="2"]', 0.2); p.until(f'{SOUNDS} > {n0}', 20, 0.3); one = p.js(SOUNDS) - n0
    playset(p, 3)
    n1 = p.js(SOUNDS); p.tap('[data-say="1"]', 0.2); p.until(f'{SOUNDS} >= {n1 + 3}', 40, 0.5); three = p.js(SOUNDS) - n1
    p.js("document.querySelector('.mini-player:not([hidden]) .close, .mini-player:not([hidden]) .stop')?.click()"); time.sleep(0.5); playset(p, 1)
    st = p.js(LS)
    check(g, f'{kind}: a sentence\'s speaker and 每句 3 遍 — the natural voice every time', one >= 1 and three >= 3 and st['speech'] == 0, {'speaker': one, '3 遍': three, 'speech': st['speech']})
    # 1③ 伴读 first, then 听 → 播放全文: the sentences 伴读 made sound at once (one address book)
    p.js("(o => { delete o['read:" + aid + "']; localStorage.setItem('flow-progress', JSON.stringify(o)); })(JSON.parse(localStorage.getItem('flow-progress') || '{}'))")
    p.go(f'#/m/{aid}/read', 1.5); p.js(HOOK); p.js('window.__au.length = 0')
    p.tap('#readAlong', 0.3); p.until(RD + '.now >= 2', 45, 0.3); r1 = p.js(RD); p.tap('.mini-player .close', 0.5)
    p.js(f"(o => {{ delete o['listen:{aid}']; localStorage.setItem('flow-progress', JSON.stringify(o)); }})(JSON.parse(localStorage.getItem('flow-progress') || '{{}}'))")
    fresh_listen(p, aid, clear=False)
    t = p.js('performance.now()'); p.tap('#playAll', 0); hit = p.until(f"(window.__au.find(e => (e.k === 'element-playing' && !String(e.src).startsWith('data:')) || e.k === 'webaudio-start') || {{}}).t", 15, 0.1)
    wait = round(hit - t) if hit else None; st = p.js(LS); p.until(LS + '.now >= 1', 30, 0.3); p.tap('.mini-player .close', 0.5)
    check(g, f'{kind}: after 伴读 read {r1["now"] + 1} sentences, 听 starts at once ({wait} ms, nothing to wait for), the natural voice',
          r1['now'] >= 2 and r1['speech'] == 0 and wait is not None and wait < 1500 and st['speech'] == 0 and not any('正在准备' in n for n in st['notes']), {'read along': r1, 'ms': wait, 'state': st})
    # 3⑤ 读 keeps its own place, 听 its own
    rd_at, ls_at = p.js(PROGRESS.format(key=json.dumps(f'read:{aid}'))), p.js(PROGRESS.format(key=json.dumps(f'listen:{aid}')))
    p.go(f'#/m/{aid}/read', 1.2); r2 = p.js(RD)
    check(g, f'{kind}: 伴读 keeps its own place (where it stopped), 听 its own', rd_at in (r1['now'], r1['now'] + 1) and r2['btn'] == f'从第 {rd_at + 1} 句继续' and ls_at is not None,
          {'read': [r1['now'], rd_at, r2['btn']], 'listen': ls_at})
    # 3⑥ another text: its own place (none yet), this one's kept
    if extra and extra.get('other'):
        fresh_listen(p, extra['other'], clear=False); o = p.js(LS)
        check(g, f'{kind}: another text has its own place (播放全文 there), this one keeps its', o['btn'] == '播放全文' and p.js(PROGRESS.format(key=json.dumps(f'read:{aid}'))) == rd_at, o)
    # 3④ heard to the end: 播放全文 again, the place forgotten
    fresh_listen(p, aid); n = p.js("document.querySelectorAll('#view .line').length")
    p.tap('#playAll', 0.3); p.until("(b => b && b.textContent.trim() === '播放全文')(document.querySelector('#playAll'))", 30 + 12 * n, 1); end = p.js(LS)
    end['restart'] = p.js(RS, gesture=True); time.sleep(0.4)
    check(g, f'{kind}: heard to the end ({n} sentences) — 播放全文 again, the place forgotten, no browser voice',
          end['btn'] == '播放全文' and not end['restart'] and p.js(PROGRESS.format(key=json.dumps(f'listen:{aid}'))) is None and end['speech'] == 0, end)
    # 4 offline (the page told it is offline and its sentence requests fail; the audio files themselves still load):
    # sentences heard before play from the addresses kept on this phone in the natural voice; one never heard on this
    # phone reads in the browser voice, and the line says why
    offline = """(() => { Object.defineProperty(Navigator.prototype, 'onLine', { get: () => false, configurable: true }); dispatchEvent(new Event('offline'));
      const F = window.fetch; window.fetch = (u, o) => /\\/api\\/next\\/tts/.test(String(u)) ? Promise.reject(new TypeError('Load failed')) : F(u, o); return 'offline'; })()"""
    p.reload(); p.js(offline); fresh_listen(p, aid)
    p.tap('#playAll', 0.3); p.until(LS + '.now >= 2', 40, 0.3); a = p.js(LS); p.tap('.mini-player .close', 0.5)
    check(g, f'{kind}: offline — sentences heard before still play in the natural voice', a['now'] >= 2 and a['speech'] == 0 and p.js(SOUNDS) >= 1, a)
    if extra and extra.get('fresh'):
        # the browser voice speaking, seen on speechSynthesis itself (a wrapper on speak() can miss it); polled while it reads
        fresh_listen(p, extra['fresh']); p.js("window.__spoke = 0; window.__spk = setInterval(() => { if (speechSynthesis.speaking) window.__spoke += 1; }, 100)")
        p.tap('#playAll', 0.3); p.until(LS + ".speech >= 1 || window.__spoke >= 3", 20, 0.3); time.sleep(0.8); b = p.js(LS); b['spoke'] = p.js('(clearInterval(window.__spk), window.__spoke)'); s = shot(f'{g}-offline-new')
        p.tap('.mini-player .close', 0.5)
        check(g, f'{kind}: offline — a sentence never heard on this phone: the browser voice, and the line says why',
              (b['speech'] >= 1 or b['spoke'] >= 3) and any('离线中' in n for n in b['notes']),
              {'state': b, 'log': [e['k'] + ':' + str(e.get('text') or e.get('src') or e.get('e') or e.get('m') or '') for e in p.js('window.__au')][-8:],
               # for 语流 9: the browser voice's own state, and whether the page reloaded itself meanwhile (a new version)
               'synth': p.js("({ speaking: speechSynthesis.speaking, pending: speechSynthesis.pending, paused: speechSynthesis.paused })"),
               'page': p.js("({ nav: (performance.getEntriesByType('navigation')[0] || {}).type, hooked: !!window.__au, tried: localStorage.getItem('flow-update-tried') })")}, s)
    p.reload()  # online again
    # 5 口语情景: the AI's reply in the role's natural voice; slow to make: 「正在准备朗读…」, then that voice, never the robot
    if extra and extra.get('scene'):
        slow = """(() => { const F = window.fetch; window.fetch = (u, o) => /\\/api\\/next\\/tts$/.test(String(u).split('?')[0]) ? new Promise(ok => setTimeout(ok, 2500)).then(() => F(u, o)) : F(u, o); return 'slow'; })()"""
        awake(p); p.go(f'#/speak/{extra["scene"]}', 1.5); p.js(HOOK); p.js('window.__au.length = 0; window.__notes.length = 0'); p.js(slow)
        p.tap('#dlgStart', 0.3); seen = p.until("(e => e && !e.hidden && e.textContent.includes('正在准备朗读'))(document.getElementById('svWait'))", 20, 0.2); s = shot(f'{g}-speak-preparing')
        p.until(SOUNDS + ' >= 1', 30, 0.3); st = p.js(LS)
        check(g, '口语情景: the reply slow to make — 「正在准备朗读…」, then the natural voice (no browser voice)', bool(seen) and p.js(SOUNDS) >= 1 and st['speech'] == 0,
              {'notes': st['notes'], 'sounds': p.js(SOUNDS), 'speech': [e.get('text') for e in p.js('window.__au') if e['k'] == 'speech'],
               'played': [e.get('src') for e in p.js('window.__au') if e['k'] == 'element-playing']}, s)
        p.reload()


RES = "(q => performance.getEntriesByType('resource').map(e => e.name.replace(location.origin, '')).filter(n => n.includes(q)))"
SLOW_TTS = """(() => { const F = window.fetch; window.fetch = (u, o) => /\\/api\\/next\\/tts$/.test(String(u).split('?')[0]) ? new Promise(ok => setTimeout(ok, 1500)).then(() => F(u, o)) : F(u, o); return 'slow'; })()"""


def run_more(p, local):
    """audio-test-plan.md 第 5 节 (#134, #136): 能力测评听力 and a 名人名言 今日好句 need an account (the local server's
    learner); 没认出的词 and an article's 今日好句 run as a guest on the beta."""
    g = 'unify-more'
    if local:
        # ① 能力测评 · 听力 without a recording: sentence by sentence in the natural voice, 「正在准备朗读第 N 句…」 while one
        # is made (made slow here), ✕ on the player counts as a play heard: the questions, 已听 1 / 2 遍, one more left
        p.reload(); awake(p); p.go('#/radar/test/listening', 1.5); p.js(HOOK); p.js('window.__au.length = 0; window.__notes.length = 0'); p.js(SLOW_TTS)
        if not p.js("!!document.getElementById('aPlay')"):
            skip(g, '能力测评听力', 'no 播放录音 on #/radar/test/listening'); return
        p.tap('#aPlay', 0.3); p.until(f'{SOUNDS} >= 2', 40, 0.4); s = shot(f'{g}-radar-listening')
        st = p.js(LS); asked = p.js(RES + "('/api/next/tts')")
        check(g, '能力测评听力 (no recording): the natural voice sentence by sentence, 「正在准备朗读第 N 句…」 while one is made, no browser voice',
              p.js(SOUNDS) >= 2 and st['speech'] == 0 and any(n.startswith('正在准备朗读第') for n in st['notes']), {'notes': st['notes'], 'sounds': p.js(SOUNDS), 'tts asked': len(asked)}, s)
        p.tap('.mini-player .close', 0.6)
        after = p.js("({ qs: !document.getElementById('aQs').hidden, plays: document.getElementById('aPlays').textContent, btn: document.getElementById('aPlay').textContent, off: document.getElementById('aPlay').disabled })")
        check(g, '能力测评听力: ✕ on the player — the questions show, 已听 1 / 2 遍, 再听一遍 left', after['qs'] and after['plays'] == '已听 1 / 2 遍' and '再听一遍' in after['btn'] and not after['off'], after)
        # ③ a 名人名言 今日好句 (no recording; the day's line is an article's today, so the page is handed a quote):
        # 听一遍 in the natural voice, 「正在准备朗读…」 while it is made
        quote = """(() => { const F = window.fetch; window.fetch = (u, o) => String(u).split('?')[0].endsWith('/api/next/home') ? F(u, o).then(r => r.json()).then(j => {
            j.line = { kind: 'quote', id: 'q:sim', label: '名人名言', en: 'Stay hungry, stay foolish.', say: 'Stay hungry, stay foolish.', zh: '求知若饥，虚心若愚', note: '', source: 'Steve Jobs' };
            return new Response(JSON.stringify(j), { headers: { 'Content-Type': 'application/json' } }); }) : F(u, o); return 'quote'; })()"""
        p.js(quote); p.js(SLOW_TTS); p.go('#/practice', 0.5); p.go('#/', 1.5); p.js(HOOK); p.js('window.__au.length = 0; window.__notes.length = 0')
        label = p.js("(document.querySelector('#lineCard .lc-src') || {}).textContent || ''")  # its source, then 公版名句 / 名人名言
        if '名人名言' not in label and '公版名句' not in label:  # the quote's label was renamed 公版名句 (a quote day shows the real one)
            skip(g, '今日好句 (名人名言)', f'the page kept its own line ({label})')
        else:
            # 列表 (r39): a row under 还有时间的话 that opens in place (12-daily-line.js #lcFold): open both, or 听一遍 is not there to tap
            p.js("(d => { if (d) d.open = true; })(document.querySelector('#view .tv-fold'))")
            if p.js("(b => !!b && b.getAttribute('aria-expanded') === 'false')(document.getElementById('lcFold'))"):
                p.tap('#lcFold', 0.6)
            p.tap('#lcSay', 0.2); p.until(f'{SOUNDS} >= 1', 20, 0.3); st = p.js(LS); s = shot(f'{g}-line-quote')
            check(g, '今日好句, a 名人名言 (no recording): 听一遍 in the natural voice, 「正在准备朗读…」 while it is made, no browser voice',
                  p.js(SOUNDS) >= 1 and st['speech'] == 0 and '正在准备朗读…' in st['notes'], {'notes': st['notes'], 'sounds': p.js(SOUNDS), 'speech': st['speech']}, s)
        p.reload()
        return
    # ② 没认出的词 in a 考试练习 result: the word's own recording (/audio/words/…), as in the word books
    seen = """(() => { const F = window.fetch; window.fetch = (u, o) => { const r = F(u, o); if (String(u).includes('/api/next/exam/submit')) r.then(x => x.clone().json()).then(j => { window.__submit = j; }); return r; }; return 'seen'; })()"""
    p.reload(); awake(p); p.go('#/exam/cet4', 1.5); p.js(seen)
    p.tap('#exStart', 0.5); p.until("!!document.querySelector('.exam-bar')", 10)
    p.tap('#exDone', 0.4); p.tap('#exDone', 0.5); p.until("!!window.__submit && !!document.querySelector('#view [data-say]')", 15)
    word = p.js("(w => w ? w.word : null)(((window.__submit || {}).vocab || []).find(v => !v.correct && v.audio && (v.audio.us || v.audio.uk)))")
    if not word:
        skip(g, '没认出的词', 'no missed word with its own recording in this set (the beta has word audio for some words only)')
    else:
        p.js(HOOK); p.js('window.__au.length = 0; performance.clearResourceTimings()')
        p.tap(f'#view [data-say="{word}"]', 0.2); p.until(f'{SOUNDS} >= 1', 10, 0.3); time.sleep(0.5); s = shot(f'{g}-missed-word')
        got = {'word': word, 'words files': p.js(RES + "('/audio/words/')"), 'tts asked': p.js(RES + "('/api/next/tts')"), 'speech': p.js(LS)['speech'], 'sounds': p.js(SOUNDS)}
        check(g, f'考试练习 → 没认出的词 ({word}): its own recording (/audio/words/…), as in the word books', got['words files'] and not got['tts asked'] and got['speech'] == 0 and got['sounds'] >= 1, got, s)
    # ③ the 今日好句 of a Flow article: that article's recording
    p.go('#/', 1.5); p.js(HOOK); p.js('window.__au.length = 0; performance.clearResourceTimings()')
    # the line this page shows (a guest's own level picks it: read from the card, not asked again)
    line = p.js("""(c => c ? { kind: c.querySelector('.pill.green') ? 'text' : 'quote', audio: true,
        pack: ((c.querySelector('.lc-src a') || {}).getAttribute?.('href') || '').split('/')[2] || '' } : null)(document.getElementById('lineCard'))""")
    if not line or line.get('kind') != 'text' or not line.get('pack'):
        skip(g, '今日好句 (语流文章)', f"today's line here is not an article's ({line})")
    else:
        p.tap('#lcSay', 0.2); p.until(f'{SOUNDS} >= 1', 10, 0.3); time.sleep(0.5); s = shot(f'{g}-line-article')
        got = {'pack': line['pack'], 'files': p.js(RES + "('/audio/')"), 'tts asked': p.js(RES + "('/api/next/tts')"), 'speech': p.js(LS)['speech']}
        check(g, f"今日好句 from a Flow article ({line['pack']}): 听一遍 plays that article's recording",
              any(line['pack'] in f for f in got['files']) and not got['tts asked'] and got['speech'] == 0 and p.js(SOUNDS) >= 1, got, s)


# ---------------------------------------------------------------- run
DEV = device(); DEV_W = None; DEV_TAG = ''.join(c for c in DEV['name'].lower().replace(' ', '-') if c.isalnum() or c == '-')
print(f"{DEV['name']} ({DEV['runtime']}, {DEV['udid']}), {'Safari' if '--safari' in ARGS else 'home-screen app'}", flush=True)
r = RWI(); p = r.page(HOST, BUNDLE)
if not p:
    sys.exit(f'{HOST} is not open in {" or ".join(BUNDLE)} on this simulator (see the steps at the top of this file)')
UI_SERVER = opt('--ui-server')  # STATE[:LEARNER] of tools/ui_server.py: its fixture learner, signed in by cookie (localhost only)
if UI_SERVER:
    if not HOST.split(':')[0] in ('localhost', '127.0.0.1'):
        sys.exit('--ui-server is for the local test server (--host localhost:PORT) only')
    state, _, who = UI_SERVER.partition(':')
    tok = json.loads((Path(state) / 'sessions.json').read_text())['learners'][who or 'home-app']['token']
    CSRF = json.loads((Path(state) / 'sessions.json').read_text())['learners'][who or 'home-app'].get('csrf', '')
    # an earlier run's session cookie is HttpOnly (the server renews it so), which a page script cannot overwrite
    try: p.cmd('Page.deleteCookie', {'cookieName': 'flow_session', 'url': f'http://{HOST}/'})
    except Exception: pass
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
def current():
    """What is tested is the server's front end: a page left from an older one (the service worker's copy) reloads first."""
    for _ in range(4):
        if p.js("((document.querySelector('script[src*=\"/next.js\"]') || {}).src || '').split('v=')[1] || ''") == VERSION:
            return True
        p.reload(2)
    check('unify', 'the page is the server\'s version', False, VERSION)
    return False


def unify():
    if not current():
        return
    if not UI_SERVER:
        return run_unify(p, PID, True)
    text = lambda n: ' '.join(['The library opens early on weekdays.', 'Students meet there before their first class.', 'Some of them read quietly in the corner.',
                               'Others work on group projects at the long tables.', 'By noon most seats are taken.', 'In the evening it is quiet again.'][:n])
    imp = lambda title, body: p.js(f"fetch('/api/next/import', {{method: 'POST', headers: {{'Content-Type': 'application/json', 'X-CSRF-Token': {json.dumps(CSRF)}}}, "
                                   f"body: JSON.stringify({{title: {json.dumps(title)}, text: {json.dumps(body)}}})}}).then(r => r.json()).then(j => j.id)")
    a = imp('图书馆的一天', text(6))
    b = imp('车站的早晨', 'The first train leaves the station at six. A few workers wait on the platform with hot drinks. '
                       'A student reads her notes under a lamp. The doors open and everyone finds a seat. Outside, the sky turns slowly from grey to blue.')
    c = imp('午后的公园', 'The afternoon light falls on the old benches in the park. A cat sleeps by the fountain and nobody wakes it. '
                       'Two children run after a red kite. An old man feeds the pigeons from a paper bag. Later the wind gets cold and people walk home.')
    scene = p.js("fetch('/api/next/speak').then(r => r.json()).then(d => (d.items || [])[0]?.id)")
    run_unify(p, a, False, {'other': b, 'fresh': c, 'scene': scene})


for part, fn in (('shell', lambda: run_shell(p)), ('onescreen', lambda: run_onescreen(p)), ('keyboard', lambda: run_keyboard(p, PID)), ('audio', lambda: run_audio(p, PID)),
                 ('mic', lambda: run_mic(p)), ('update', lambda: run_update(p)), ('unify', unify), ('more', lambda: current() and run_more(p, bool(UI_SERVER)))):
    if part in ONLY:
        print(f'— {part}', flush=True)
        try:
            fn()
        except Exception as e:
            check(part, 'ran to the end', False, repr(e))
appearance('dark' if 'keep-dark' in ARGS else 'light')

meta = {'device': DEV, 'asset': VERSION, 'page_asset': PAGE_ASSET, 'when': time.strftime('%Y-%m-%d %H:%M'), 'app': p.r.apps.get(p.app, {}).get('WIRApplicationBundleIdentifierKey')}
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
