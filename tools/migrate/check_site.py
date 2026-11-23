#!/usr/bin/env python3
"""从任何一台电脑运行：不改域名，直接连新服务器的 IP，用正式域名访问网站，逐项检查并和现在的线上网站对比。

    python3 check_site.py 新服务器IP                    HTTPS（新服务器已经有证书）
    python3 check_site.py 新服务器IP --http             证书还没申请时，先走 80 端口
    python3 check_site.py 新服务器IP --insecure         证书还没对上域名时，跳过证书校验（只用于切换前）

只读：只发 GET 请求，不登录，不写任何数据。
"""
import argparse, http.client, json, socket, ssl, sys, time

HOST = 'flow.jasa.hk'
PID = 'v5-science-b2-noise-cancelling'
PATHS = [
    ('健康检查', '/api/health', None),
    ('首页', '/', 'next.js'),
    ('今日数据', '/api/next/home?level=B1', 'today'),
    ('知识图谱', '/api/next/graph?level=B1', 'route'),
    ('一篇材料', f'/api/next/material?id={PID}', 'sentences'),
    ('全部材料', '/api/next/library?level=B1', 'items'),
    ('口语路线', '/api/next/speak?level=B1', 'items'),
    ('连载', '/api/next/series?id=a-new-term', 'episodes'),
    ('朗读录音', f'/audio/us-f/{PID}.mp4', None),
    ('单词发音', '/api/next/lookup?w=borrow', 'entry'),
    ('部署状态', '/api/deploy-status', 'tag'),
]


def fetch(ip, path, use_http, insecure):
    """GET https://HOST/path, connecting to ip instead of what DNS says (the certificate is checked for HOST)."""
    t = time.time()
    if use_http:
        conn = http.client.HTTPConnection(ip, 80, timeout=20)
    else:
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE

        class Conn(http.client.HTTPSConnection):
            def connect(self):
                sock = socket.create_connection((ip, 443), self.timeout)
                self.sock = ctx.wrap_socket(sock, server_hostname=HOST)
        conn = Conn(HOST, 443, timeout=20)
    conn.request('GET', path, headers={'Host': HOST, 'User-Agent': 'flow-migration-check', 'Accept-Encoding': 'identity'})
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, body, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ip')
    ap.add_argument('--http', action='store_true')
    ap.add_argument('--insecure', action='store_true')
    a = ap.parse_args()
    live_ip = socket.gethostbyname(HOST)
    print(f'新服务器 {a.ip}　对比：现在的线上 {HOST}（{live_ip}）\n')
    bad = 0
    for name, path, key in PATHS:
        try:
            s, body, dt = fetch(a.ip, path, a.http, a.insecure)
        except Exception as e:
            print(f'✗ {name}：连不上（{type(e).__name__}: {e}）'); bad += 1; continue
        try:
            ls, lbody, ldt = fetch(live_ip, path, False, False)
        except Exception:
            ls, lbody, ldt = None, b'', None
        ok = s == 200 and (key is None or key.encode() in body)
        same = ''
        if path == '/api/deploy-status' and ok:
            new, old = json.loads(body).get('tag'), json.loads(lbody or b'{}').get('tag')
            same = f'，版本 {new}' + ('，和线上一致' if new == old else f'，线上是 {old}')
        elif ls == 200 and path.startswith('/audio/'):
            same = '，大小和线上一致' if len(body) == len(lbody) else f'，大小不同（新 {len(body)} / 线上 {len(lbody)}）'
        print(f"{'✓' if ok else '✗'} {name}：{s}，{dt * 1000:.0f} ms" + (f'（线上 {ldt * 1000:.0f} ms）' if ldt else '') + same)
        bad += not ok
    print('\n全部通过，可以继续。' if not bad else f'\n有 {bad} 项没通过，先别切换。')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
