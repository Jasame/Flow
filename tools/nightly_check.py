#!/usr/bin/env python3
"""The nightly whole-site check (MSI, about 01:00; 语流 A2, user 2026-11-26 「按推荐做」): what pull requests do not run.

    python3 tools/nightly_check.py <out dir> [--parts compat,ui,pages,materials] [--deadline 06:30] [--limit N] [--no-wait]

Run from a checkout of main (tools/nightly-msi.sh makes one from the MSI's local mirror). Everything is local: the
pages come from tools/ui_server.py (a throwaway database with the UI tests' demo learners, a simulated AI); nothing
reaches the 内测版, 正式版, a real AI or any learner's data, and the browser makes no sound (tools/quiet.py).

  compat     tools/check_compat.py: the served scripts and styles against Safari 15.0. Static only: Linux has no old
             Safari, so whether an iPhone on iOS 15–16.3 really parses next.js is not run here.
  ui         every UI group (run_tests.py --ui, one share at a time, so a few cores are enough); a group that fails is
             run once more, and a failure that does not come back is listed as intermittent.
  pages      every page in tools/ui_test.py PAGES, phone and desktop, Chinese and English: a screenshot each, script
             errors, Chinese left in the English pages (outside data-zh / translate="no"), and how long it took to draw.
  materials  each material's 读 and 听 pages (desktop, Chinese): script errors, an empty or missing page.

Before each unit of work it waits while a CI job runs on this machine (a Runner.Worker process), so CI goes first; at
the deadline it stops and reports what it has. Writes <out>/report.md and <out>/summary.json, shots in <out>/shots.
"""
import ast, json, os, re, socket, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
OUT = Path(sys.argv[1])
ARGS = sys.argv[2:]


def opt(name, default):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


PARTS = opt('--parts', 'compat,ui,pages,materials').split(',')
DEADLINE = opt('--deadline', '06:30')
LIMIT = int(opt('--limit', '0'))  # for a quick try: only the first N pages / materials
NO_WAIT = '--no-wait' in ARGS  # for a quick try while CI is busy: do not wait for it (still 4 cores, lowest priority)
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = OUT / 'shots'
SHOTS.mkdir(exist_ok=True)
LOG = open(OUT / 'nightly.log', 'a')
started = time.time()
result = {'started': datetime.now().isoformat(timespec='minutes'), 'parts': {}, 'waited_for_ci_s': 0, 'stopped_at_deadline': False}


def log(*a):
    line = datetime.now().strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(line, flush=True); LOG.write(line + '\n'); LOG.flush()


def past_deadline():
    h, m = map(int, DEADLINE.split(':'))
    now = datetime.now()
    return now.hour * 60 + now.minute >= h * 60 + m and now.hour < 12


def ci_busy():
    r = subprocess.run(['pgrep', '-x', 'Runner.Worker'], capture_output=True)
    return r.returncode == 0


def make_way():
    """CI first: wait while a runner has a job (checked between units, so a test is never frozen half way)."""
    t = time.time()
    while not NO_WAIT and ci_busy() and not past_deadline():
        time.sleep(20)
    if time.time() - t > 1:
        result['waited_for_ci_s'] += int(time.time() - t)
        log(f'waited {int(time.time() - t)} s for CI')
    if past_deadline():
        result['stopped_at_deadline'] = True
    return not result['stopped_at_deadline']


# ---------- compat ----------
def part_compat():
    r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'check_compat.py')], capture_output=True, text=True)
    lines = (r.stdout + r.stderr).strip().splitlines()
    return {'ok': r.returncode == 0, 'findings': [l for l in lines if re.match(r'\S+:\d+:\d+:', l)], 'last': lines[-1] if lines else ''}


# ---------- ui ----------
def run_ui(args, out):
    cmd = [sys.executable, str(ROOT / 'tools' / 'run_tests.py'), '--ui', *args, '--out', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=40 * 60)
    text = r.stdout + r.stderr
    fails = sorted(set(re.sub(r'\s+', ' ', m.group(1)).strip() for m in re.finditer(r'^\s+FAIL (\[[^\]]+\] .+)$', text, re.M)))
    groups = re.findall(r'^FAIL ui ([\w\- ]+?):', text, re.M)
    return r.returncode, fails, [g for gs in groups for g in gs.split()], text


def part_ui():
    shares = int(subprocess.run([sys.executable, str(ROOT / 'tools' / 'run_tests.py'), '--list', '--ui'], capture_output=True,
                                text=True).stdout.count('\n')) or 5
    out = {'shares': shares, 'failed': [], 'intermittent': [], 'passed_shares': 0}
    for k in range(1, shares + 1):
        if not make_way():
            break
        log(f'ui share {k}/{shares}')
        rc, fails, groups, text = run_ui(['--shard', f'{k}/{shares}'], OUT / 'ui')
        (OUT / f'ui-{k}.log').write_text(text)
        if rc == 0:
            out['passed_shares'] += 1; continue
        if not groups or not make_way():
            out['failed'] += [{'share': k, 'check': f} for f in fails] or [{'share': k, 'check': f'exit {rc}, see ui-{k}.log'}]
            continue
        log(f'  again: {" ".join(groups)}')
        rc2, fails2, _, text2 = run_ui(groups, OUT / 'ui-again')
        (OUT / f'ui-{k}-again.log').write_text(text2)
        for f in fails:
            (out['failed'] if f in fails2 else out['intermittent']).append({'share': k, 'check': f})
    return out


# ---------- the local server and the pages ----------
def pages_from_ui_test():
    tree = ast.parse((ROOT / 'tools' / 'ui_test.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', '') == 'PAGES':
            return node.value
    raise SystemExit('PAGES not found in tools/ui_test.py')


class Server:
    def __enter__(self):
        self.state = Path(tempfile.mkdtemp(prefix='flow-nightly-'))
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'tools' / 'ui_server.py'), str(port), str(self.state)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(240):
            if (self.state / 'sessions.json').exists():
                break
            time.sleep(0.25)
        time.sleep(0.5)
        self.cfg = json.loads((self.state / 'sessions.json').read_text())
        return self

    def __exit__(self, *a):
        self.proc.terminate()


DEVICES = {
    'phone': dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
    'desktop': dict(viewport={'width': 1440, 'height': 900}, is_mobile=False, has_touch=False, device_scale_factor=1),
}
SETTLE = ['#view .skeleton', '#view[data-busy]', '#splash']  # data-busy: a page seen before, on its way (no skeleton)
LEFT_CHINESE = """() => {
  const out = [], seen = new Set();
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const t = n.nodeValue.replace(/\\s+/g, ' ').trim();
    if (!/[\\u4e00-\\u9fff]/.test(t)) continue;
    if (/[A-Za-z]{4,}/.test(t)) continue;  // written in both (AI 生成 · AI-generated, 语流 Flow)
    const el = n.parentElement;
    if (!el || el.closest('[data-zh], [translate="no"], script, style, noscript')) continue;
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    if (!seen.has(t)) { seen.add(t); out.push(t.slice(0, 60)); }
  }
  return out.slice(0, 15);
}"""
EMPTY = "() => { const v = document.getElementById('view'); return !v || v.innerText.replace(/\\s+/g, '').length < 15; }"


def settle(pg, timeout=10000):
    for sel in SETTLE:
        pg.wait_for_selector(sel, state='detached', timeout=timeout)
    try:
        pg.wait_for_selector('#view h1, #view .review, #view .empty, #view .done-card', timeout=timeout)
    except Exception:
        pass
    pg.wait_for_timeout(300)


def open_context(pw, browser, srv, dev, lang):
    ctx = browser.new_context(**DEVICES[dev], locale='zh-CN', bypass_csp=True)
    learner = srv.cfg['learners'].get(dev) or srv.cfg['learners']['b1']
    ctx.add_cookies([{'name': 'flow_session', 'value': learner['token'], 'url': srv.cfg['base']}])
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e).splitlines()[0][:200]))
    pg.on('console', lambda m: errs.append(m.text[:200]) if m.type == 'error' and 'favicon' not in m.text and '/audio/' not in m.text
          and 'Failed to load resource' not in m.text else None)
    pg.goto(srv.cfg['base'] + '/'); settle(pg)
    if lang == 'en':  # as 我的 → 使用习惯 does (07-lang.js): the account's language and this device's copy, then one reload
        r = pg.evaluate('''async c => { const r = await fetch('/api/next/lang', { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': c }, body: JSON.stringify({ lang: 'en' }) });
          localStorage.setItem('flow-lang', JSON.stringify('en')); return r.status; }''', learner.get('csrf', ''))
        pg.reload(); settle(pg)
        if r != 200 or pg.evaluate("() => document.documentElement.lang") not in ('en', 'en-US', 'en-GB'):
            errs.append(f'English did not open (lang API {r})')
    return ctx, pg, errs


def visit(pg, errs, hash_):
    del errs[:]
    t = time.time()
    try:
        pg.evaluate('h => { location.hash = h; }', hash_)
        pg.wait_for_timeout(50)
        settle(pg)
        ok = True
    except Exception as e:
        ok = False; errs.append(f'did not finish drawing: {str(e).splitlines()[0][:120]}')
    return ok, round(time.time() - t - 0.35, 2)


def part_pages():
    from playwright.sync_api import sync_playwright
    from quiet import silent
    tree = pages_from_ui_test()
    found = {'problems': [], 'slow': [], 'left_chinese': [], 'shots': 0, 'timings': {}}
    with Server() as srv:
        with sync_playwright() as pw:
            silent(pw)
            pages = eval(compile(ast.Expression(tree), 'ui_test.py', 'eval'), {'PID': srv.cfg['pid']})
            pages = [p for p in pages if 'not-a-real-link' not in p][:LIMIT or None]
            browser = pw.chromium.launch(channel='chrome')
            for dev in DEVICES:
                for lang in ('zh', 'en'):
                    if not make_way():
                        return found
                    log(f'pages {dev} {lang}')
                    ctx, pg, errs = open_context(pw, browser, srv, dev, lang)
                    for i, h in enumerate(pages):
                        if i and i % 15 == 0 and not make_way():
                            return found
                        ok, secs = visit(pg, errs, h)
                        name = f"{dev}-{lang}-{re.sub(r'[^A-Za-z0-9]+', '_', h).strip('_') or 'home'}.jpg"
                        try:
                            pg.screenshot(path=str(SHOTS / name), type='jpeg', quality=60); found['shots'] += 1
                        except Exception:
                            name = ''
                        found['timings'].setdefault(h, {})[f'{dev}-{lang}'] = secs
                        empty = ok and pg.evaluate(EMPTY)
                        if errs or not ok or empty:
                            found['problems'].append({'page': h, 'device': dev, 'lang': lang, 'shot': name,
                                                      'what': (['empty page'] if empty else []) + errs[:3]})
                        if lang == 'en' and ok:
                            left = pg.evaluate(LEFT_CHINESE)
                            if left:
                                found['left_chinese'].append({'page': h, 'device': dev, 'shot': name, 'text': left})
                        if secs > 3:
                            found['slow'].append({'page': h, 'device': dev, 'lang': lang, 'seconds': secs})
                    ctx.close()
            browser.close()
    return found


def part_materials():
    from playwright.sync_api import sync_playwright
    from quiet import silent
    sys.path.insert(0, str(ROOT / 'flow'))
    from content_v50 import all_materials, SUPERSEDED
    ids = [p['id'] for p in all_materials() if p['id'] not in SUPERSEDED][:LIMIT or None]
    found = {'materials': len(ids), 'opened': 0, 'problems': []}
    with Server() as srv:
        with sync_playwright() as pw:
            silent(pw)
            browser = pw.chromium.launch(channel='chrome')
            ctx, pg, errs = open_context(pw, browser, srv, 'desktop', 'zh')
            for i, pid in enumerate(ids):
                if i % 20 == 0 and not make_way():
                    break
                for step in ('read', 'listen'):
                    h = f'#/m/{pid}/{step}'
                    ok, secs = visit(pg, errs, h)
                    empty = ok and pg.evaluate(EMPTY)
                    if errs or not ok or empty:
                        name = f"material-{re.sub(r'[^A-Za-z0-9]+', '_', pid)}-{step}.jpg"
                        try:
                            pg.screenshot(path=str(SHOTS / name), type='jpeg', quality=60)
                        except Exception:
                            name = ''
                        found['problems'].append({'page': h, 'shot': name, 'what': (['empty page'] if empty else []) + errs[:3]})
                found['opened'] += 1
                if i % 50 == 49:
                    log(f'materials {i + 1}/{len(ids)}')
            browser.close()
    return found


# ---------- the report ----------
def report():
    r = result['parts']
    lines = [f"# 夜间全站检查 {result['started'][:10]}（MSI，main {result.get('main', '?')}）", '',
             '旧版 iPhone（iOS 15–16.3）只做了静态检查（tools/check_compat.py）：Linux 上没有旧版 Safari，真机能不能解析前端脚本这里测不到。', '',
             f"用时 {result['minutes']} 分钟，其中给 CI 让路 {result['waited_for_ci_s'] // 60} 分钟"
             + ('；**到 06:30 停下，后面的没跑**' if result['stopped_at_deadline'] else '') + '。整晚的截图在 MSI 的 ~/nightly/out/<日期>/shots/，报告里点到的就在本报告旁边。', '',
             '## 真问题', '']
    real = 0
    c = r.get('compat')
    if c and not c['ok']:
        real += 1; lines += ['- **兼容检查不过**：'] + [f'  - `{f}`' for f in c['findings'][:10]]
    u = r.get('ui')
    if u:
        for f in u['failed']:
            real += 1; lines.append(f"- 界面测试（第 {f['share']} 组）：{f['check']}")
    p = r.get('pages')
    if p:
        for x in p['problems']:
            real += 1; lines.append(f"- 页面 `{x['page']}`（{x['device']}，{'英文' if x['lang'] == 'en' else '中文'}）：{'；'.join(x['what'])}"
                                    + (f"  截图 `{x['shot']}`" if x['shot'] else ''))
    m = r.get('materials')
    if m:
        for x in m['problems']:
            real += 1; lines.append(f"- 材料 `{x['page']}`：{'；'.join(x['what'])}" + (f"  截图 `{x['shot']}`" if x['shot'] else ''))
    for k, v in r.items():
        if k.endswith('_error'):
            real += 1; lines.append(f"- **夜检自己出错**（{k[:-6]} 这一部分没跑完）：`{v}`")
    if not real:
        lines.append('没有。')
    if p and p['left_chinese']:
        where = {}
        for x in p['left_chinese']:
            for t in x['text']:
                where.setdefault(t, []).append(x)
        lines += ['', f'## 英文界面里还是中文的字（{len(where)} 处，按文字归并；英文界面还在做，给负责它的会话）', '']
        for t, xs in sorted(where.items(), key=lambda kv: -len(kv[1]))[:40]:
            pages = sorted({x['page'] for x in xs})
            first = next(x for x in xs if x['page'] == pages[0])
            lines.append(f"- 「{t}」：{len(pages)} 个页面，如 `{pages[0]}`（截图 `{first['shot']}`）")
        if len(where) > 40:
            lines.append(f'- 另有 {len(where) - 40} 处，见 summary.json')
    lines += ['', '## 偶发（重跑一次就过了）', '']
    lines += [f"- 界面测试（第 {f['share']} 组）：{f['check']}" for f in (u or {}).get('intermittent', [])] or ['没有。']
    lines += ['', '## 概况', '']
    if c:
        lines.append(f"- 兼容检查：{c['last']}")
    if u:
        lines.append(f"- 界面测试：{u['shares']} 组里 {u['passed_shares']} 组一次全过，{len(u['failed'])} 处失败，{len(u['intermittent'])} 处偶发")
    if p:
        lines.append(f"- 页面：{len(p['timings'])} 个页面 × 手机/电脑 × 中/英，截图 {p['shots']} 张；画完超过 3 秒的 {len(p['slow'])} 次")
        slow = sorted(((max(v.values()), k) for k, v in p['timings'].items()), reverse=True)[:5]
        if slow:
            lines.append('- 最慢的页面：' + '，'.join(f'`{k}` {s:.1f} 秒' for s, k in slow))
    if m:
        lines.append(f"- 材料：{m['opened']}/{m['materials']} 篇打开了读和听两页，{len(m['problems'])} 处有问题")
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return real


def main():
    result['main'] = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_front.py')], check=True, stdout=subprocess.DEVNULL)
    for part, fn in (('compat', part_compat), ('ui', part_ui), ('pages', part_pages), ('materials', part_materials)):
        if part not in PARTS or not make_way():
            continue
        log(f'== {part}')
        try:
            result['parts'][part] = fn()
        except Exception as e:  # one part going wrong still leaves the others and a report
            result['parts'][part + '_error'] = f'{type(e).__name__}: {e}'[:300]
            log(f'{part} failed: {e}')
    result['minutes'] = round((time.time() - started) / 60)
    real = report()
    (OUT / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=1))
    log(f'done in {result["minutes"]} min, {real} problem(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
