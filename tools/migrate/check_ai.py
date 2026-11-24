#!/usr/bin/env python3
"""在新服务器上运行：用 /etc/flow.env 的设置，真的调用一次 AI（文字一次；开了录音功能再听一次录音），
确认这台服务器能连上网站用的 AI。只打印成功与否和耗时，不打印任何密钥。

    sudo python3 check_ai.py              用 Flow 自己的 Python 更稳妥：
    sudo /opt/uv-python/cpython-3.11.18-linux-x86_64-gnu/bin/python3.11 check_ai.py

在买服务器后的退款期内就跑：这一步不通，就不要迁移。
"""
import base64, json, os, sys, time
from pathlib import Path

ENV, APP = Path(os.getenv('FLOW_ENV', '/etc/flow.env')), Path(os.getenv('FLOW_APP', '/www/wwwroot/flow'))


def load_env(path):
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    if not ENV.exists():
        sys.exit(f'找不到 {ENV}：先用 unpack.sh 解包，或者在旧服务器上运行这个检查做对比')
    load_env(ENV)
    sys.path.insert(0, str(APP))
    import chat_service
    provider = os.getenv('FLOW_AI_PROVIDER') or 'openai 兼容接口'
    print(f'AI 服务：{provider}，模型：{os.getenv("FLOW_AI_MODEL") or "（默认）"}')
    msgs = [{'role': 'system', 'content': '只输出 JSON。'}, {'role': 'user', 'content': '输出 JSON：{"ok":true,"word":"hello"}'}]
    t = time.time()
    try:
        text, _ = chat_service.request_model(msgs)
        reply = json.loads(text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip())
        print(f'文字：成功，{time.time() - t:.1f} 秒，回复 {reply}')
    except Exception as e:  # the message says what failed (network, permission, model); it holds no secret
        print(f'文字：失败，{time.time() - t:.1f} 秒：{type(e).__name__}: {str(e)[:300]}')
        sys.exit(1)
    if os.getenv('FLOW_AI_AUDIO') == '1':
        clips = sorted(Path('/root/claude-ops/autodeploy/daily/qa-audio').glob('*'))
        if not clips:
            print('录音：跳过（没有找到测试录音）')
            return
        clip = clips[0]
        mime = 'audio/mp4' if clip.suffix in ('.m4a', '.mp4') else 'audio/ogg' if clip.suffix == '.ogg' else 'audio/webm'
        audio = {'mime_type': mime, 'data': base64.b64encode(clip.read_bytes()).decode()}
        msgs = [{'role': 'system', 'content': '只输出 JSON。'}, {'role': 'user', 'content': '把录音转写成英文，输出 JSON：{"text":"转写"}'}]
        t = time.time()
        try:
            text, _ = chat_service.request_model(msgs, audio=audio)
            print(f'录音：成功，{time.time() - t:.1f} 秒，转写开头：{text[:80]!r}')
        except Exception as e:
            print(f'录音：失败，{time.time() - t:.1f} 秒：{type(e).__name__}: {str(e)[:300]}')
            sys.exit(1)


if __name__ == '__main__':
    main()
