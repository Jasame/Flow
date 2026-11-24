"""Spoken role-play turn check: how long from the end of the learner's sentence until the reply can be heard, and how
well each path hears and corrects, on synthetic recordings only (never a learner's own).

One turn of a 情景对话 scene (output_service.dialog: the site's own prompt and reply reading) is sent three ways:
- gemini   : the recording to the main model, which writes down what it heard, corrects and replies (as today);
- asr+text : 百炼 speech recognition (gateway name --asr, e.g. flow-eval-asr-flash → qwen3-asr-flash) writes the
             sentence down, then the text model (--text, e.g. flow-eval-ds-flash → DeepSeek) corrects and replies;
- omni     : Qwen-Omni (--omni, e.g. flow-eval-omni-flash → qwen3.8-omni-flash) hears the recording and answers at once.
Every reply is then read aloud by flow-tts, so 'until heard' = model time + speech time (flow-tts is not streamed).
Recordings: the sentences in corpus_data/voice-eval.json, read by flow-tts's CosyVoice voices (native English), plus
any recordings of the same ids found in --clips (e.g. macOS voices with a Chinese accent, made on the owner's Mac).
Each sentence has the mistake it carries, so we can see whether each path catches it.

    python3 voice_eval.py [--env-file /etc/flow.env] [--paths gemini,asr,omni] [--clips DIR] [--output report.json]
A throwaway database; the site's own data is never touched. About ¥1–2 for the whole set."""
import argparse, base64, json, os, re, statistics, sys, tempfile, time, urllib.request
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CASES = HERE / 'corpus_data' / 'voice-eval.json'
VOICES = ('loongabby_v3', 'loongandy_v3', 'loongemily_v3', 'loongeric_v3')
REPLY_VOICE = 'loongemily_v3'
SCENES = {'cafe': 'cafe-order', 'directions': 'ask-way', 'restaurant': 'phone-booking', 'weekend': 'group-project', 'shopping': 'return-item'}
MIME = {'.m4a': 'audio/mp4', '.mp4': 'audio/mp4', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.webm': 'audio/webm', '.ogg': 'audio/ogg'}
# Yuan, list prices (help.aliyun.com/zh/model-studio/model-pricing, read 2026-11-25): qwen3.8-omni-flash 0.8 in / 2.7 out
# per million tokens; CosyVoice ¥1 per 10,000 characters. qwen3-asr-flash's price was not on the page we read: its
# audio seconds are reported instead. Gemini's audio input is not reported by the relay (its tokens are estimated).
OMNI_PRICE = (0.8, 2.7)
TTS_PER_CHAR = 0.0001


# ---------- the gateway, the way the site calls it ----------

def gateway():
    url, key = os.getenv('FLOW_AI_URL', ''), os.getenv('FLOW_AI_KEY', '')
    if not url.endswith('/chat/completions') or not key:
        raise SystemExit('FLOW_AI_URL / FLOW_AI_KEY are not a gateway address and key')
    return url[:-len('/chat/completions')], key


def post(path, body, timeout=90):
    base, key = gateway()
    req = urllib.request.Request(base + path, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'jasa-flow-voice-eval/1.0'})
    return urllib.request.urlopen(req, timeout=timeout)


def stream_chat(body):
    """A streamed chat completion: (text, seconds to the first text, seconds in all, usage)."""
    started = time.monotonic()
    first, text, usage = None, '', None
    with post('/chat/completions', {**body, 'stream': True, 'stream_options': {'include_usage': True}}) as r:
        for raw in r:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            chunk = json.loads(data)
            if chunk.get('usage'):
                usage = chunk['usage']
            for ch in chunk.get('choices') or []:
                delta = (ch.get('delta') or {}).get('content')
                if isinstance(delta, str) and delta:
                    first = first if first is not None else time.monotonic() - started
                    text += delta
    return text, first, time.monotonic() - started, usage


def speak(text, voice, fmt='mp3'):
    """flow-tts: (audio bytes, seconds)."""
    started = time.monotonic()
    with post('/audio/speech', {'model': 'flow-tts', 'input': text, 'voice': voice, 'response_format': fmt}, timeout=60) as r:
        audio = r.read()
    return audio, time.monotonic() - started


def data_url(audio):
    return f"data:{audio['mime_type']};base64,{audio['data']}"


# ---------- the site's own turn ----------

def scene_turn(c, sid, opener, audio=None, text=None):
    """(system, user, convert) exactly as output_service.dialog builds them for one turn after the opener."""
    import output_service as out
    got = {}

    def capture(c_, uid, data, kind, pack, skill, spec, system, user, convert, audio=None):
        got.update(system=system, user=user, convert=convert)
        return {'result': {}}, 200
    data = {'scenario': sid, 'history': [{'role': 'ai', 'text': opener}], 'request_id': 'voice-eval'}
    data.update({'audio': audio} if audio else {'text': text})
    with patch.object(out, '_ai', capture), patch.dict(os.environ, {'FLOW_AI_AUDIO': '1'}):
        result, status = out.dialog(c, 1, data)
    if status != 200 or not got:
        raise RuntimeError(f'dialog prompt not built: {status} {result}')
    return got['system'], got['user'], got['convert']


def read_reply(raw, convert):
    from lab_service import parse
    return convert(parse(raw))


# ---------- scoring ----------

def words(s):
    return re.findall(r"[a-z0-9']+", (s or '').lower().replace('’', "'"))


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return round(d[len(h)] / max(1, len(r)), 3)


def caught(case, corr):
    """Did the correction touch the planted mistake? (None when there is none to catch.)"""
    err = case.get('error')
    if not err:
        return None
    if not corr:
        return False
    orig, better = ' '.join(words(corr.get('original'))), ' '.join(words(corr.get('better')))
    want_from = ' '.join(words(err['original']))
    want_to = [' '.join(words(x)) for x in err['better'].split('/')]
    return bool(want_from and want_from in orig) or any(w and w in better for w in want_to)


# ---------- the three paths ----------

def run_gemini(c, case, audio, opener):
    import ai_routes, chat_service as cs
    system, user, convert = scene_turn(c, SCENES[case['scene']], opener, audio=audio)
    started = time.monotonic()
    with ai_routes.task('next-dialog'):
        raw, reason = cs.request_model([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], audio=audio)
    secs = time.monotonic() - started
    return {'reply': read_reply(raw, convert), 'model_s': round(secs, 2), 'first_s': None, 'served': getattr(cs.INFO, 'served', ''), 'cost': None}


def run_asr(c, case, audio, opener, asr, text_model):
    import ai_routes, chat_service as cs
    heard, first, asr_s, usage = stream_chat({'model': asr, 'messages': [{'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': data_url(audio)}}]}]})
    heard = heard.strip()
    system, user, convert = scene_turn(c, SCENES[case['scene']], opener, text=heard or 'um')
    started = time.monotonic()
    with ai_routes.task('next-dialog'):
        raw, reason = cs._request_text_service([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], text_model, ai_routes.extra_body(text_model, 'next-dialog'))
    text_s = time.monotonic() - started
    served = getattr(cs.INFO, 'served', '')
    u = getattr(cs.INFO, 'usage', None)
    cost = ai_routes.cost(served, time.time(), u[0], u[1], u[2]) if u else None  # usage: prompt, cached, completion, reasoning
    reply = read_reply(raw, convert)
    reply['heard'] = heard
    return {'reply': reply, 'model_s': round(asr_s + text_s, 2), 'asr_s': round(asr_s, 2), 'text_s': round(text_s, 2), 'first_s': None, 'served': served,
            'asr_usage': usage, 'cost': cost}


def run_omni(c, case, audio, opener, omni):
    system, user, convert = scene_turn(c, SCENES[case['scene']], opener, audio=audio)
    fmt = {'audio/mp4': 'mp4', 'audio/wav': 'wav', 'audio/mpeg': 'mp3', 'audio/webm': 'webm', 'audio/ogg': 'ogg'}[audio['mime_type']]
    body = {'model': omni, 'modalities': ['text'], 'enable_thinking': False,
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': data_url(audio), 'format': fmt}}, {'type': 'text', 'text': user}]}]}
    raw, first, secs, usage = stream_chat(body)
    cost = None
    if usage and type(usage.get('prompt_tokens')) is int:
        cost = round((usage['prompt_tokens'] * OMNI_PRICE[0] + (usage.get('completion_tokens') or 0) * OMNI_PRICE[1]) / 1e6, 5)
    return {'reply': read_reply(raw, convert), 'model_s': round(secs, 2), 'first_s': round(first, 2) if first is not None else None, 'usage': usage, 'cost': cost}


# ---------- the run ----------

def recordings(cases, clips_dir):
    """[(case, label, audio dict)]: every sentence read by a CosyVoice voice, plus the owner's recordings of it."""
    out = []
    for i, case in enumerate(cases):
        voice = VOICES[i % len(VOICES)]
        audio, _ = speak(case['text'], voice)
        out.append((case, 'cosyvoice:' + voice, {'mime_type': 'audio/mpeg', 'data': base64.b64encode(audio).decode()}))
        for f in sorted(Path(clips_dir).glob(case['id'] + '.*')) if clips_dir else []:
            if f.suffix in MIME:
                out.append((case, 'clip:' + f.name, {'mime_type': MIME[f.suffix], 'data': base64.b64encode(f.read_bytes()).decode()}))
    return out


def one(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - a path that fails is the finding
        return {'error': type(exc).__name__ + ': ' + str(exc)[:300]}


def summarize(items):
    out = {}
    for path in dict.fromkeys(i['path'] for i in items):
        rows = [i for i in items if i['path'] == path]
        ok = [i for i in rows if 'error' not in i]
        heard = [i['wer'] for i in ok if i.get('wer') is not None]
        catch = [i['caught'] for i in ok if i.get('caught') is not None]
        over = [i for i in ok if i.get('caught') is None and i['reply'].get('correction')]
        q = lambda xs, p: round(sorted(xs)[min(len(xs) - 1, int(p * len(xs)))], 2) if xs else None
        out[path] = {'ok': [len(ok), len(rows)], 'model_s_p50': q([i['model_s'] for i in ok], 0.5), 'model_s_p90': q([i['model_s'] for i in ok], 0.9),
                     'heard_s_p50': q([i['heard_s'] for i in ok if i.get('heard_s') is not None], 0.5), 'heard_s_p90': q([i['heard_s'] for i in ok if i.get('heard_s') is not None], 0.9),
                     'first_s_p50': q([i['first_s'] for i in ok if i.get('first_s') is not None], 0.5),
                     'wer_mean': round(statistics.mean(heard), 3) if heard else None, 'caught': [sum(catch), len(catch)], 'corrected_a_right_sentence': len(over),
                     'cost': round(sum(i.get('cost') or 0 for i in ok), 4), 'errors': [f"{i['case']} {i['recording']}: {i['error']}" for i in rows if 'error' in i]}
    return out


def describe(s):
    lines = []
    for path, v in s.items():
        lines.append(f"== {path}: 成功 {v['ok'][0]}/{v['ok'][1]} | 模型 中位 {v['model_s_p50']} 秒 / P90 {v['model_s_p90']} 秒 | 说完到听见回复 中位 {v['heard_s_p50']} 秒 / "
                     f"P90 {v['heard_s_p90']} 秒 | 首字 {v['first_s_p50']} | 听写词错率 {v['wer_mean']} | 抓到错误 {v['caught'][0]}/{v['caught'][1]} | "
                     f"把对的句子也改了 {v['corrected_a_right_sentence']} | ¥{v['cost']}（不含 Gemini 音频和语音识别）")
        lines += ['   ✗ ' + e for e in v['errors'][:6]]
    return '\n'.join(lines)


def brief(item):
    if 'error' in item:
        return '✗ ' + item['error'][:80]
    return f"model {item['model_s']}s heard {item.get('heard_s')}s wer {item.get('wer')} caught {item.get('caught')}"


def main(argv=None):
    ap = argparse.ArgumentParser(description='情景对话说一句的速度和效果：Gemini、百炼语音识别+文字模型、Qwen-Omni')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--paths', default='gemini,asr,omni')
    ap.add_argument('--asr', default='flow-eval-asr-flash')
    ap.add_argument('--text', default='flow-eval-ds-flash')
    ap.add_argument('--omni', default='flow-eval-omni-flash')
    ap.add_argument('--clips', help='同名录音所在的文件夹（如 c04-agree-zh.m4a）')
    ap.add_argument('--cases', default=str(CASES))
    ap.add_argument('--limit', type=int, default=0, help='只用前几句')
    ap.add_argument('--output')
    args = ap.parse_args(argv)
    if Path(args.env_file).is_file():
        from studio_setup import read_env
        for k, v in read_env(Path(args.env_file).read_text()).items():
            if k.startswith(('FLOW_', 'GOOGLE_')):
                os.environ[k] = v
    tmp = Path(tempfile.mkdtemp(prefix='flow-voice-eval-'))
    os.environ['FLOW_DATA_DIR'] = str(tmp)
    os.environ['FLOW_AI_USER_DAILY_LIMIT'] = os.environ['FLOW_AI_DAILY_LIMIT'] = '100000'
    sys.path.insert(0, str(HERE))
    import app
    app.DB, app.DATA = tmp / 'eval.sqlite3', tmp
    app.init()
    c = app.db()
    c.execute("INSERT OR IGNORE INTO users(id,username,password) VALUES(1,'voice-eval','x')")
    c.commit()
    cases = json.loads(Path(args.cases).read_text(encoding='utf-8'))['cases']
    cases = cases[:args.limit] if args.limit else cases
    paths = [p for p in args.paths.split(',') if p in ('gemini', 'asr', 'omni')]
    items = []
    for case, label, audio in recordings(cases, args.clips):
        opener = case.get('opener') or 'Hi! What can I do for you today?'
        order = paths[len(items) % len(paths):] + paths[:len(items) % len(paths)]  # take turns going first
        for path in order:
            r = one(run_gemini, c, case, audio, opener) if path == 'gemini' else one(run_asr, c, case, audio, opener, args.asr, args.text) if path == 'asr' \
                else one(run_omni, c, case, audio, opener, args.omni)
            item = {'case': case['id'], 'recording': label, 'path': path, **r}
            if 'error' not in r:
                heard = r['reply'].get('heard') or ''
                item['wer'] = wer(case['text'], heard) if heard else None
                item['caught'] = caught(case, r['reply'].get('correction'))
                spoken = one(speak, r['reply'].get('reply') or 'OK.', REPLY_VOICE)
                if isinstance(spoken, tuple):
                    item['tts_s'] = round(spoken[1], 2)
                    item['heard_s'] = round(r['model_s'] + spoken[1], 2)
                    item['cost'] = round((r.get('cost') or 0) + len(r['reply'].get('reply') or '') * TTS_PER_CHAR, 5)
                else:
                    item['tts_error'] = spoken['error']
            items.append(item)
            print(f"{case['id']:<16} {label:<28} {path:<6} {brief(item)}", flush=True)
    report = {'run_at': time.time(), 'paths': paths, 'asr': args.asr, 'text': args.text, 'omni': args.omni, 'summary': summarize(items), 'items': items}
    print(describe(report['summary']))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
