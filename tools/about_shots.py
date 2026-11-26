#!/usr/bin/env python3
"""Screenshots for 认识语流 (/about), taken from the local UI server (tools/ui_server.py: throwaway database, simulated
AI, the test learner 小林), in light and dark.

    python3 tools/about_shots.py [name …]        # needs: pip install playwright; all shots when no name is given

Writes flow/public/about/<name>.jpg and <name>-d.jpg (dark) at phone size, desk.jpg / desk-d.jpg at laptop size, and
share.jpg, the picture a shared link shows. Nothing here touches production.
"""
import base64, json, socket, subprocess, sys, tempfile, time, atexit
from pathlib import Path
from playwright.sync_api import sync_playwright
from quiet import silent  # every browser it starts makes no sound (tools/quiet.py)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'flow' / 'public' / 'about'
PID = 'v5-science-b2-noise-cancelling'  # the same material the page's look-up demo and the promo film use
PHONE = {'width': 390, 'height': 844}
DESK = {'width': 1280, 'height': 800}


def today(pg):
    pg.evaluate("() => { const n = document.getElementById('mailNudge'); if (n) n.remove(); }")  # the test learner has no email


def listen(pg):
    # The local server has no narration files; on the site this material is read by four real voices, so its tip
    # does not carry the "no recording yet" line.
    # (the tip is empty when the AI voice reads it, 21-study-listen.js: then there is nothing to take out)
    pg.evaluate("() => { const t = document.querySelector('.listen-tip'); if (t && t.firstChild) t.firstChild.nodeValue = t.firstChild.nodeValue.replace('这篇还没有录音，先用浏览器朗读。', ''); }")


def check(pg):
    pg.click('#pane .ans[data-q="0"][data-o="0"]')
    pg.wait_for_selector('#pane .q[data-q="0"] .fb:not(:empty)', timeout=6000)
    pg.wait_for_timeout(900)


def output(pg):
    pg.evaluate("() => { const t = document.querySelector('#view textarea'); if (t) { t.value = 'I usually wear headphones on the train, so the noise is less.'; t.dispatchEvent(new Event('input', { bubbles: true })); } }")


def review(pg):
    pg.wait_for_selector('#view .review', timeout=6000)
    # the first-visit guide drawn over the card (60-review.js #zoneGuide, put away by the first tap) is not the card
    pg.wait_for_timeout(800)
    pg.evaluate("() => { const g = document.getElementById('zoneGuide'); if (g) g.remove(); }")


# name -> (page, extra step or None, viewport)
SHOTS = {
    'today': ('#/', today, PHONE),
    'listen': (f'#/m/{PID}/listen', listen, PHONE),
    'read': (f'#/m/{PID}/read', None, PHONE),
    'check': (f'#/m/{PID}/check', check, PHONE),
    'output': (f'#/m/{PID}/output', output, PHONE),
    'review': ('#/review', review, PHONE),
    'desk': (f'#/m/{PID}/read', None, DESK),
}


def share(browser):
    """The 1200×630 picture for shared links: the name, the line, and the 今日 page in a phone."""
    shot = base64.b64encode((OUT / 'today.jpg').read_bytes()).decode()
    font = base64.b64encode((ROOT / 'flow' / 'public' / 'literata.woff2').read_bytes()).decode()
    html = f"""<!doctype html><meta charset="utf-8"><style>
    @font-face{{font-family:L;src:url(data:font/woff2;base64,{font}) format('woff2')}}
    body{{margin:0;width:1200px;height:630px;overflow:hidden;background:radial-gradient(90% 120% at 80% 10%,#e3f2e8,#fbfaf6 60%);font-family:-apple-system,'PingFang SC',sans-serif;color:#1b1d1a}}
    .t{{position:absolute;left:84px;top:150px;width:640px}}
    .b{{display:flex;align-items:center;gap:16px;font-weight:700;font-size:34px}}
    .b svg{{width:64px;height:64px}}
    h1{{margin:44px 0 0;font:700 64px/1.22 L,'Songti SC',serif;letter-spacing:-.01em}}
    h1 em{{font-style:normal;color:#12733c}}
    p{{margin:26px 0 0;font-size:25px;color:#4b4f48}}
    .p{{position:absolute;right:120px;top:60px;width:300px;padding:9px;border-radius:46px;background:#16181a;box-shadow:0 40px 80px -20px rgba(20,40,25,.35);transform:rotate(4deg)}}
    .p img{{display:block;width:100%;border-radius:37px}}
    </style><div class="t"><div class="b"><svg viewBox="0 0 32 32"><rect width="32" height="32" rx="9" fill="#1f9d55"/><path d="M7 20v-6m6 10V8m6 14V11m6 7v-4" stroke="#fff" stroke-width="3" stroke-linecap="round"/></svg>语流 Flow</div>
    <h1>每天一篇短文，<br>把英语<em>用起来</em>。</h1><p>听、读、理解、用出来 · 生词点一下就懂 · flowlang.cn</p></div>
    <div class="p"><img src="data:image/jpeg;base64,{shot}"></div>"""
    pg = browser.new_page(viewport={'width': 1200, 'height': 630})
    pg.set_content(html)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / 'share.jpg'), type='jpeg', quality=82)
    pg.close()
    print(f"share: {(OUT / 'share.jpg').stat().st_size // 1024} KB", flush=True)


def main(only):
    names = only or list(SHOTS) + ['share']
    OUT.mkdir(parents=True, exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix='flow-about-state-'))
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, str(ROOT / 'tools' / 'ui_server.py'), str(port), str(state)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(server.terminate)
    for _ in range(160):
        if (state / 'sessions.json').exists():
            break
        time.sleep(0.25)
    time.sleep(0.5)
    cfg = json.loads((state / 'sessions.json').read_text())
    base, token = cfg['base'], cfg['learners']['guide']['token']
    with sync_playwright() as p:
        silent(p)
        browser = p.chromium.launch(channel='chrome')  # the installed Chrome, as tools/ui_test.py does
        for name in [n for n in names if n in SHOTS]:
            route, step, size = SHOTS[name]
            phone = size is PHONE
            for scheme, suffix in (('light', ''), ('dark', '-d')):
                ctx = browser.new_context(viewport=size, is_mobile=phone, has_touch=phone, device_scale_factor=2 if phone else 1.25, locale='zh-CN',
                                          color_scheme=scheme, reduced_motion='reduce', service_workers='block', bypass_csp=True)
                ctx.add_cookies([{'name': 'flow_session', 'value': token, 'url': base}])
                pg = ctx.new_page()
                # a fixed time of day, so the greeting on 今日 reads 下午好 whenever the shots are taken (today's date, 15:30)
                pg.clock.set_system_time(time.strftime('%Y-%m-%dT15:30:00'))
                pg.goto(base + '/' + route)
                pg.wait_for_function("() => !document.querySelector('#view .skeleton, #view[data-busy]') && !document.querySelector('#view .loading')", timeout=15000)
                pg.wait_for_selector('#view h1, #view .review, #view .empty', timeout=10000)
                pg.wait_for_timeout(700)
                if step:
                    step(pg)
                # the toast and the one-time tips (08-tips.js .tip-once, 「知道了」) belong to a first visit, not to the page shown
                pg.evaluate("() => { const t = document.getElementById('toast'); if (t) t.style.display = 'none'; document.querySelectorAll('#view .tip-once').forEach(e => e.remove()); window.scrollTo(0, 0); }")
                pg.wait_for_timeout(300)
                out = OUT / f'{name}{suffix}.jpg'
                pg.screenshot(path=str(out), type='jpeg', quality=70 if phone else 74)
                print(f"{out.name}: {out.stat().st_size // 1024} KB", flush=True)
                ctx.close()
        if 'share' in names:
            share(browser)
        browser.close()


if __name__ == '__main__':
    main(sys.argv[1:])
