#!/usr/bin/env python3
"""Screenshots for the 操作指南, taken from the local UI server (tools/ui_server.py: throwaway database, simulated AI).

    python3 tools/guide_shots.py [name …]        # needs: pip install playwright; all shots when no name is given

Each ![caption](shot:name) in flow/public/guide/guide.md needs an entry in SHOTS below; the pictures are written to
flow/public/guide/<name>.jpg at phone size. Then run tools/build_guide.py to make the PDF. Nothing here touches production.
"""
import json, socket, subprocess, sys, tempfile, time, atexit
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flow'))
import user_guide  # noqa: E402

OUT = user_guide.DIR
PID = 'v5-science-b2-noise-cancelling'


def login(pg):
    pg.click('#lg')
    pg.wait_for_selector('#authForm', timeout=5000)
    pg.wait_for_timeout(500)


def lookup(pg):
    pg.click('#reader .w:text-is("drains")')  # an inflected word: the card shows its base form
    pg.wait_for_selector('#sheetCard .word', timeout=5000)
    pg.wait_for_timeout(500)


def output(pg):
    pg.evaluate("() => { const t = document.querySelector('#view textarea'); if (t) { t.value = 'I usually wear headphones on the train, so the noise is less.'; t.dispatchEvent(new Event('input', { bubbles: true })); } }")


def review(pg):
    pg.wait_for_selector('#view .review', timeout=6000)


# name -> (page, extra step or None, signed in?)
SHOTS = {
    'welcome': ('#/welcome', None, False),
    'login': ('#/me', login, False),
    'today': ('#/', None, True),
    'listen': (f'#/m/{PID}/listen', None, True),
    'read': (f'#/m/{PID}/read', None, True),
    'lookup': (f'#/m/{PID}/read', lookup, True),
    'output': (f'#/m/{PID}/output', output, True),
    'cards': ('#/cards', None, True),
    'plan': ('#/vocab/plan', None, True),
    'review': ('#/review', review, True),
    'graph': ('#/graph', None, True),
    'node': ('#/graph/voice-basic', None, True),
    'practice': ('#/practice', None, True),
    'easy': ('#/easy', None, True),
    'speak': ('#/speak', None, True),
    'exam': ('#/exam', None, True),
    'radar': ('#/radar', None, True),
    'radartest': ('#/radar/test', None, True),
    'report': ('#/report', None, True),
    'me': ('#/me', None, True),
}


def main(only):
    wanted = [s for ch in user_guide.parse()['chapters'] for s in ch['shots']]
    missing = [s for s in wanted if s not in SHOTS]
    if missing:
        raise SystemExit(f'guide.md uses shots with no entry in SHOTS: {missing}')
    names = only or wanted
    state = Path(tempfile.mkdtemp(prefix='flow-guide-state-'))
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
        browser = p.chromium.launch(channel='chrome')  # the installed Chrome, as tools/ui_test.py does
        for name in names:
            route, step, signed = SHOTS[name]
            ctx = browser.new_context(viewport={'width': 390, 'height': 760}, is_mobile=True, has_touch=True, device_scale_factor=2, locale='zh-CN',
                                      reduced_motion='reduce', service_workers='block', bypass_csp=True)
            if signed:
                ctx.add_cookies([{'name': 'flow_session', 'value': token, 'url': base}])
            pg = ctx.new_page()
            pg.goto(base + '/' + route)
            pg.wait_for_function("() => !document.querySelector('#view .skeleton') && !document.querySelector('#view .loading')", timeout=15000)
            pg.wait_for_selector('#view h1, #view .review, #view .empty', timeout=10000)
            pg.wait_for_timeout(700)
            if step:
                step(pg)
            pg.evaluate("() => { const t = document.getElementById('toast'); if (t) t.style.display = 'none'; window.scrollTo(0, 0); }")
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / f'{name}.jpg'), type='jpeg', quality=62)
            print(f"{name}: {(OUT / f'{name}.jpg').stat().st_size // 1024} KB", flush=True)
            ctx.close()
        browser.close()


if __name__ == '__main__':
    main(sys.argv[1:])
