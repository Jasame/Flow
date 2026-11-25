"""Check a --smoke-test report (desktop/src-tauri/src/smoke.rs): the page saw window.FlowApp with the agreed
capabilities, the User-Agent ends with FlowDesktop/<version> (Windows|macOS), the media-session hook reached the
app, and the app's media controls started. Exit 1 with the reasons otherwise.

usage: python3 desktop/tools/check_smoke.py smoke.json [windows|macos]"""
import json
import re
import sys


def problems(d, os_name):
    if 'error' in d:
        return [f"no report: {d['error']} (page: {d.get('url')})"]
    p, n = d.get('page') or {}, d.get('native') or {}
    label = {'windows': 'Windows', 'macos': 'macOS'}[os_name]
    out = []
    want = {'flowapp': True, 'v': 1, 'platform': os_name, 'notify': True, 'media': True, 'audio': False,
            'frozen': True, 'mediaSession': True, 'mediaHandlers': 11, 'muted': True}
    for k, v in want.items():
        if p.get(k) != v:
            out.append(f'page.{k} = {p.get(k)!r}, want {v!r}')
    if not p.get('onReturnsOff'):
        out.append('FlowApp.on() does not return an unsubscribe function')
    if not p.get('callUnknownRejects'):
        out.append("FlowApp.call('<unknown>') did not reject")
    h = p.get('hello') or {}
    if h.get('v') != 1 or h.get('platform') != os_name or sorted(h.get('features') or []) != ['media', 'notify']:
        out.append(f"FlowApp.call('hello') = {h!r}")
    if not isinstance(p.get('beta'), bool) or not p.get('build'):
        out.append(f"FlowApp.beta / build missing: {p.get('beta')!r} {p.get('build')!r}")
    if p.get('syncOk') is False:
        out.append(f"notify_plan failed: {p.get('syncError')}")
    if not re.search(r' FlowDesktop/[\d.]+ \(' + label + r'\)$', p.get('ua') or ''):
        out.append(f"User-Agent does not end with FlowDesktop/<version> ({label}): {p.get('ua')!r}")
    if p.get('permission') not in ('granted', 'denied', 'undetermined'):
        out.append(f"notify.permission() = {p.get('permission')!r} {p.get('permissionError') or ''}")
    if p.get('syncError'):
        out.append(f"notify.sync failed: {p['syncError']}")
    if not str(p.get('url', '')).startswith(('https://flow.jasa.hk/', 'https://flowlang.cn/')):
        out.append(f"page is {p.get('url')!r}, not the site")
    if not n.get('mute'):
        out.append('a smoke test must run muted (FLOW_MUTE)')
    if n.get('smoke_notify'):  # FLOW_SMOKE_NOTIFY=1 (CI's Windows runner): the reminders really reached the system
        if not p.get('synced'):
            out.append(f"notify.sync planned nothing: {p.get('synced')!r} {p.get('syncError') or ''}")
        ids = [x.get('id') for x in n.get('pending') or []]
        if not any(i in ('review-once', 'once') for i in ids):
            out.append(f'the one-off reminder is not in the system queue: {ids}')
        if 'review-once' not in (p.get('pendingFromPage') or []):
            out.append(f"FlowApp.notify.pending() does not list it: {p.get('pendingFromPage')!r}")
        if n.get('test_notification') != 'shown':
            out.append(f"test notification: {n.get('test_notification')!r}")
    if not n.get('media_controls'):
        out.append('the system media controls did not start')
    if n.get('media_last_title') != '语流 · 冒烟测试':
        out.append(f"media title did not reach the app: {n.get('media_last_title')!r}")
    return out


def main():
    sys.stdout.reconfigure(encoding='utf-8')  # a Windows runner's console is not UTF-8
    path, os_name = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else ('windows' if sys.platform == 'win32' else 'macos'))
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    bad = problems(d, os_name)
    for b in bad:
        print('FAIL', b)
    print('smoke test', 'failed' if bad else 'passed')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
