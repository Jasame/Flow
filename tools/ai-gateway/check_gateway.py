#!/usr/bin/env python3
"""Checks the AI gateway the way Flow uses it. Run on the Flow server after README.md step 6, and after every switch
of vendor in the console:

    python3 /opt/ai-gateway/check_gateway.py [--public https://api.xmc.hk] [--json report.json]

Reads FLOW_TEXT_AI_URL / FLOW_TEXT_AI_KEY / FLOW_TEXT_AI_MODEL from /etc/flow.env (--env-file to change), so it
tests exactly what Flow will call. Prints no key and no model output beyond its length; makes three small model
calls. Exit status 0 when every check passed.
"""
import argparse, json, sys, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

KEYS = ('FLOW_TEXT_AI_URL', 'FLOW_TEXT_AI_KEY', 'FLOW_TEXT_AI_MODEL')


def read_env(path):
    out = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def call(url, key=None, body=None, timeout=60):
    """(status, content type, body bytes); network errors become status 0."""
    h = {'User-Agent': 'flow-gateway-check/1.0'}
    if key:
        h['Authorization'] = 'Bearer ' + key
    if body is not None:
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', '') if e.headers else '', e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, '', str(e).encode()


def run(env, public=None, out=print):
    results = []

    def check(name, ok, detail=''):
        results.append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
        out(f"{'通过' if ok else '失败'}  {name}{'' if ok or not detail else '：' + str(detail)[:300]}")
        return ok

    url, key, model = (env.get(k, '') for k in KEYS)
    if not check('Flow 的配置里有网关地址、令牌和模型名', url and key and model, '在 /etc/flow.env 里填 ' + '、'.join(k for k in KEYS if not env.get(k))):
        return results
    parts = urlsplit(url)
    local = parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost', '::1')
    check('网关地址是本机（不经过公网和 Cloudflare）', local or parts.scheme == 'https', url)
    base = f'{parts.scheme}://{parts.netloc}'

    st, _, body = call(base + '/api/status', timeout=15)
    try:
        alive = st == 200 and json.loads(body).get('success') is True
    except ValueError:
        alive = False
    if not check('网关在运行', alive, f'HTTP {st}' if st else body.decode(errors='replace')):
        return results

    st, _, body = call(base + '/v1/models', key, timeout=15)
    try:
        models = [m.get('id') for m in json.loads(body).get('data', [])]
    except (ValueError, AttributeError):
        models = []
    if not check('令牌有效', st == 200, f'HTTP {st}（令牌不对、已过期或被禁用）'):
        return results
    check(f'令牌能用模型 {model}', model in models, f'这个令牌能用的模型：{", ".join(m for m in models if m) or "没有"}（在令牌的「模型限制」里勾上它，并确认有渠道提供它）')

    t0 = time.monotonic()
    st, _, body = call(url, key, {'model': model, 'messages': [{'role': 'user', 'content': 'Reply with one short English greeting.'}], 'max_tokens': 30})
    try:
        d = json.loads(body); text = d['choices'][0]['message']['content']; served = d.get('model', '')
    except (ValueError, KeyError, IndexError, TypeError):
        d, text, served = {}, '', ''
    check('普通调用有回答', st == 200 and isinstance(text, str) and text.strip(),
          f'HTTP {st}' + (f'，{body[:160].decode(errors="replace")}' if st != 200 else '，回答是空的'))
    results[-1]['seconds'] = round(time.monotonic() - t0, 2)
    if served:
        out(f'      实际回答的模型：{served}，用时 {results[-1]["seconds"]} 秒')

    t0 = time.monotonic(); first = None; deltas = 0; done = False
    req = urllib.request.Request(url, data=json.dumps({'model': model, 'stream': True, 'max_tokens': 60,
                                 'messages': [{'role': 'user', 'content': 'Count from one to five in English words.'}]}).encode(),
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'flow-gateway-check/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            stream = 'text/event-stream' in r.headers.get('Content-Type', '')
            for raw in r:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    done = True; break
                try:
                    ch = json.loads(data).get('choices') or [{}]
                except ValueError:
                    continue
                if (ch[0].get('delta') or {}).get('content'):
                    deltas += 1; first = first or time.monotonic()
                if ch[0].get('finish_reason'):
                    done = True
        check('流式输出（Flow 边生成边显示要用）', stream and deltas and done, f'流式={stream}，片段={deltas}，结束={done}')
        if first:
            out(f'      第一个字出来用了 {round(first - t0, 2)} 秒')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        check('流式输出（Flow 边生成边显示要用）', False, e)

    st, _, body = call(url, key, {'model': model, 'max_tokens': 120, 'messages': [
        {'role': 'system', 'content': 'You are an English tutor. Return only JSON.'},
        {'role': 'user', 'content': 'Give feedback on "I like apples.". Return only JSON with strength (Chinese), revision (English).'}]})
    try:
        raw = json.loads(body)['choices'][0]['message']['content'].strip()
        if raw.startswith('```'):
            raw = raw.strip('`').split('\n', 1)[-1]
        parsed = json.loads(raw[raw.find('{'):raw.rfind('}') + 1])
        ok = isinstance(parsed, dict) and 'revision' in parsed
    except (ValueError, KeyError, IndexError, TypeError):
        ok = False
    check('按要求只回 JSON（批改、出题都靠它）', ok, f'HTTP {st}' if st != 200 else '回答不是要求的 JSON，换模型前先看看 Flow 的批改是否正常')

    if public:
        st, ctype, body = call(public.rstrip('/') + '/v1/models', timeout=20)
        exposed = st == 401 or (st == 200 and b'"data"' in body) or (b'"error"' in body and 'json' in ctype)
        check('模型接口不对公网开放', st and not exposed,
              f'从 {public} 访问 /v1 得到 HTTP {st}：按 nginx-api.xmc.hk.conf 关掉 /v1' if st else body.decode(errors='replace'))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--public', help='the console address, e.g. https://api.xmc.hk: checks that /v1 is closed there')
    ap.add_argument('--json', help='write a report (no secrets) to this file')
    a = ap.parse_args()
    results = run(read_env(a.env_file), a.public)
    ok = bool(results) and all(r['ok'] for r in results)
    print('全部通过' if ok else '有检查没通过，见上面的「失败」行')
    if a.json:
        Path(a.json).write_text(json.dumps({'ok': ok, 'checks': results}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
