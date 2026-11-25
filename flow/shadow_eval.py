"""跟读 (next-shadow) and 发音 (next-say) heard two ways, on the same recordings: does Qwen-Omni score like Gemini?

2026-11-25, the owner on these two recordings: 「不要交给gemini了，延迟太高了」. So 跟读 moves to Omni first (Gemini when it
fails) and 发音 too, its verdict a reference only (output_service.say). This checks how far apart the two are, with the
site's own prompts and the site's own reading of the answer, on synthetic recordings only (never a learner's own):
- gemini : the recording to the main model, as before (chat_service.request_model with no audio route);
- omni   : Qwen-Omni through the gateway (--omni, e.g. flow-eval-omni-flash), the call the site makes (_request_audio_service).
Recordings (corpus_data/shadow-eval.json), made fresh with flow-tts: every 跟读 sentence read as written and with a
planted learner mistake (th as s, a dropped word, a dropped ending…), by an English CosyVoice voice and by a Chinese
one reading English (a light Chinese accent); every 发音 word read right and as its pair word (think as sink).
跟读: the score the learner sees (next_service.pron_score), which words it marks as missed, and which it would file in
the mistake book (the first two sounds / issues). 发音: right or wrong, against what was read.

    python3 shadow_eval.py [--env-file /etc/flow-beta.env] [--tasks shadow,say] [--paths gemini,omni] [--output report.json]
A throwaway database; the site's own data is never touched. Under ¥0.5 for the whole set (Omni and CosyVoice; Gemini
on the relay's account), about 20 minutes (Gemini takes 10–40 s a recording)."""
import argparse, base64, json, os, re, statistics, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_eval as ve  # noqa: E402  the gateway helpers (post, speak) and the throwaway site

CASES = HERE / 'corpus_data' / 'shadow-eval.json'
EN_VOICES = ('loongabby_v3', 'loongeric_v3')
ZH_VOICES = ('longxiaochun_v3', 'longwan_v3')  # Chinese voices reading English: a light accent


class _Built(Exception):
    """Raised by the stand-in model call once the site's prompt is in hand."""


# ---------- the site's own prompts ----------

def shadow_prompt(c, sentence, audio):
    """(messages, convert) exactly as next_service.shadow builds them for this sentence (asked as a 今日好句 line)."""
    import chat_service as cs, daily_line, lab_service, next_service as nx
    got = {}

    def request(messages, audio=None, grounding=False):
        got['messages'] = messages
        raise _Built()

    def run_job(c_, uid, rid, kind, pack, skill, spec, call, convert, **kw):
        got['convert'] = convert
        try:
            call()
        except _Built:
            pass
        return {'error': 'built'}, 599

    with patch.object(cs, 'request_model', request), patch.object(lab_service, 'run_job', run_job), \
            patch.object(daily_line, 'sentence_of', lambda data: sentence), patch.dict(os.environ, {'FLOW_AI_AUDIO': '1'}):
        result, status = nx.shadow(c, 1, {'quote': 'shadow-eval', 'audio': audio, 'request_id': 'shadow-eval'})
    if 'messages' not in got:
        raise RuntimeError(f'shadow prompt not built: {status} {result}')
    return got['messages'], got['convert']


def say_prompt(c, word, audio):
    """(messages, convert) exactly as output_service.say builds them for this word."""
    import output_service as out
    got = {}

    def capture(c_, uid, data, kind, pack, skill, spec, system, user, convert, audio=None):
        got.update(messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], convert=convert)
        return {'error': 'built'}, 599
    with patch.object(out, '_ai', capture), patch.dict(os.environ, {'FLOW_AI_AUDIO': '1'}):
        result, status = out.say(c, 1, {'text': word, 'audio': audio, 'request_id': 'shadow-eval'})
    if 'messages' not in got:
        raise RuntimeError(f'say prompt not built: {status} {result}')
    return got['messages'], got['convert']


# ---------- the two paths ----------

def run_gemini(messages, audio, kind):
    import ai_routes, chat_service as cs
    started = time.monotonic()
    with ai_routes.task(kind), patch.dict(os.environ, {'FLOW_AUDIO_ROUTES': ''}):  # the main model only, as before
        out = cs.request_model(messages, audio=audio)
    return {'raw': out[0], 'model_s': round(time.monotonic() - started, 2), 'served': getattr(cs.INFO, 'served', ''), 'cost': None}


def run_omni(messages, audio, kind, model):
    import ai_routes, chat_service as cs
    started = time.monotonic()
    cs.INFO.__dict__.clear()
    with ai_routes.task(kind):
        raw, _ = cs._request_audio_service(messages, audio, model)
    served, u = getattr(cs.INFO, 'served', ''), getattr(cs.INFO, 'usage', None)
    cost = ai_routes.cost(served, time.time(), u[0], u[1], u[2]) if u else None
    return {'raw': raw, 'model_s': round(time.monotonic() - started, 2), 'served': served, 'cost': cost}


def read(raw, convert):
    from lab_service import parse
    return convert(parse(raw))


# ---------- reading the answers the way the site does ----------

def norm(w):
    return re.sub(r"[^a-z']", '', (w or '').lower().replace('’', "'"))


def shadow_item(case, recording, r):
    """What the learner would see for this answer, and whether the planted mistake shows."""
    import next_service as nx
    sentence = case['sentence']
    r['words'] = nx.compare_words(sentence, r['transcript'])
    r['matched'] = sum(1 for w in r['words'] if w['ok'])
    score = nx.pron_score(r)
    cards = ([x['word'] for x in r.get('sounds') or []] + [x['word'] for x in r['issues']])[:2]  # what shadow() files
    missed = [w['w'] for w in r['words'] if not w['ok']]
    item = {'total': score['total'] if score else None, 'accuracy': r.get('accuracy'), 'fluency': r.get('fluency_score'),
            'complete': score['complete'] if score else None, 'transcript': r['transcript'], 'missed': missed, 'cards': cards,
            'sounds': [x['sound'] + ' ' + x['word'] for x in r.get('sounds') or []], 'tip': r.get('tip', '')}
    if recording['planted']:
        want = {norm(w) for w in case['mistake']['words']}
        item['marked'] = bool(want & {norm(w) for w in missed})  # the transcript shows the change
        item['named'] = any(want & {norm(x) for x in c.split()} for c in cards)  # a card names the word
        item['caught'] = item['marked'] or item['named']
    else:
        item['false_cards'] = len(cards)  # mistakes filed on a sentence read right
        item['false_missed'] = len(missed)
    return item


def say_item(case, recording, r):
    return {'verdict': r['ok'], 'right': r['ok'] is (not recording['planted']), 'heard': r['heard'], 'note': r['note'][:120]}


# ---------- the run ----------

def recordings(data, tasks):
    """[(task, case, recording, audio dict)]: every sentence / word, right and planted, by an English and a Chinese voice."""
    out = []
    for task in tasks:
        for i, case in enumerate(data[task]):
            if task == 'shadow':
                readings = ((case['sentence'], False), (case['mistake']['read'], True))
            else:
                readings = ((case['word'], False), (case['wrong'], True))
            for text, planted in readings:
                for voice in (EN_VOICES[i % 2], ZH_VOICES[i % 2]):
                    audio, _ = ve.speak(text, voice)
                    out.append((task, case, {'read': text, 'voice': voice, 'planted': planted, 'accent': voice in ZH_VOICES},
                                {'mime_type': 'audio/mpeg', 'data': base64.b64encode(audio).decode()}))
    return out


def q(xs, p):
    return round(sorted(xs)[min(len(xs) - 1, int(p * len(xs)))], 2) if xs else None


def mean(xs):
    return round(statistics.mean(xs), 1) if xs else None


def pearson(a, b):
    if len(a) < 3 or len(set(a)) < 2 or len(set(b)) < 2:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return round(num / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5, 2)


def summarize(items):
    out = {}
    for task in dict.fromkeys(i['task'] for i in items):
        rows = [i for i in items if i['task'] == task]
        per = {}
        for path in dict.fromkeys(i['path'] for i in rows):
            mine = [i for i in rows if i['path'] == path]
            ok = [i for i in mine if 'error' not in i]
            v = {'ok': [len(ok), len(mine)], 'model_s_p50': q([i['model_s'] for i in ok], 0.5), 'model_s_p90': q([i['model_s'] for i in ok], 0.9),
                 'model_s_max': max([i['model_s'] for i in ok], default=None), 'cost': round(sum(i.get('cost') or 0 for i in ok), 4),
                 'errors': [f"{i['case']} {i['voice']}{' planted' if i['planted'] else ''}: {i['error']}" for i in mine if 'error' in i]}
            right, planted = [i for i in ok if not i['planted']], [i for i in ok if i['planted']]
            if task == 'shadow':
                v.update(total_right=mean([i['total'] for i in right if i['total'] is not None]),
                         total_planted=mean([i['total'] for i in planted if i['total'] is not None]),
                         total_right_accent=mean([i['total'] for i in right if i['accent'] and i['total'] is not None]),
                         accuracy_right=mean([i['accuracy'] for i in right if i['accuracy'] is not None]),
                         accuracy_planted=mean([i['accuracy'] for i in planted if i['accuracy'] is not None]),
                         caught=[sum(1 for i in planted if i['caught']), len(planted)], named=[sum(1 for i in planted if i['named']), len(planted)],
                         false_cards=[sum(i['false_cards'] for i in right), sum(1 for i in right if i['false_cards']), len(right)],
                         false_missed=sum(i['false_missed'] for i in right))
            else:
                v.update(right_on_right=[sum(1 for i in right if i['right']), len(right)], right_on_planted=[sum(1 for i in planted if i['right']), len(planted)])
            per[path] = v
        if task == 'shadow' and {'gemini', 'omni'} <= set(per):  # the same recording, both answered
            pairs = {}
            for i in rows:
                if 'error' not in i and i['total'] is not None:
                    pairs.setdefault((i['case'], i['voice'], i['planted']), {})[i['path']] = i
            both = [p for p in pairs.values() if {'gemini', 'omni'} <= set(p)]
            d = [p['omni']['total'] - p['gemini']['total'] for p in both]
            da = [p['omni']['accuracy'] - p['gemini']['accuracy'] for p in both if p['omni']['accuracy'] is not None and p['gemini']['accuracy'] is not None]
            per['compare'] = {'n': len(both), 'total_diff_mean': mean(d), 'total_absdiff_mean': mean([abs(x) for x in d]), 'total_absdiff_max': max(map(abs, d), default=None),
                              'within_5': sum(1 for x in d if abs(x) <= 5), 'within_10': sum(1 for x in d if abs(x) <= 10),
                              'accuracy_diff_mean': mean(da), 'pearson_total': pearson([p['gemini']['total'] for p in both], [p['omni']['total'] for p in both]),
                              'caught_agree': [sum(1 for p in both if p['gemini']['planted'] and p['gemini']['caught'] == p['omni']['caught']),
                                               sum(1 for p in both if p['gemini']['planted'])]}
        out[task] = per
    return out


def describe(s):
    lines = []
    for task, per in s.items():
        lines.append('### ' + ('跟读（整句）' if task == 'shadow' else '发音（单词）'))
        for path, v in per.items():
            if path == 'compare':
                lines.append(f"  同一段录音两边都打了分 {v['n']} 段：Omni − Gemini 总分平均 {v['total_diff_mean']}，平均相差 {v['total_absdiff_mean']}，最多 "
                             f"{v['total_absdiff_max']}；相差 5 分以内 {v['within_5']} 段、10 分以内 {v['within_10']} 段；准确度平均差 {v['accuracy_diff_mean']}；"
                             f"总分相关系数 {v['pearson_total']}；故意读错的录音两边判断一致 {v['caught_agree'][0]}/{v['caught_agree'][1]}")
                continue
            head = f"  {path}: 成功 {v['ok'][0]}/{v['ok'][1]} | 用时 中位 {v['model_s_p50']} 秒 / P90 {v['model_s_p90']} / 最长 {v['model_s_max']}"
            if task == 'shadow':
                head += (f" | 读对的总分 {v['total_right']}（中文声音 {v['total_right_accent']}），故意读错的 {v['total_planted']} | 准确度 {v['accuracy_right']} → "
                         f"{v['accuracy_planted']} | 抓到读错 {v['caught'][0]}/{v['caught'][1]}（点名那个词 {v['named'][0]}） | 读对却记进错题本 {v['false_cards'][0]} 条"
                         f"（{v['false_cards'][1]}/{v['false_cards'][2]} 段） | 读对却标成漏读 {v['false_missed']} 个词")
            else:
                head += f" | 读对判对 {v['right_on_right'][0]}/{v['right_on_right'][1]} | 读错判错 {v['right_on_planted'][0]}/{v['right_on_planted'][1]}"
            lines.append(head + (f" | ¥{v['cost']}" if v['cost'] else ''))
            lines += ['     ✗ ' + e for e in v['errors'][:6]]
    return '\n'.join(lines)


def brief(item):
    if 'error' in item:
        return '✗ ' + item['error'][:90]
    if item['task'] == 'say':
        return f"{item['model_s']}s verdict {item['verdict']} right {item['right']} heard {item['heard']}"
    return (f"{item['model_s']}s total {item['total']} acc {item['accuracy']} missed {item['missed'][:4]} cards {item['cards']}"
            + (f" caught {item['caught']}" if item['planted'] else ''))


def main(argv=None):
    ap = argparse.ArgumentParser(description='跟读和发音：同一段录音交给 Gemini 和 Qwen-Omni，分数和判断差多少')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--tasks', default='shadow,say')
    ap.add_argument('--paths', default='gemini,omni')
    ap.add_argument('--omni', default='flow-eval-omni-flash')
    ap.add_argument('--cases', default=str(CASES))
    ap.add_argument('--limit', type=int, default=0, help='每个任务只用前几条')
    ap.add_argument('--output')
    args = ap.parse_args(argv)
    if Path(args.env_file).is_file():
        from studio_setup import read_env
        for k, v in read_env(Path(args.env_file).read_text()).items():
            if k.startswith(('FLOW_', 'GOOGLE_')):
                os.environ[k] = v
    tmp = Path(tempfile.mkdtemp(prefix='flow-shadow-eval-'))
    os.environ['FLOW_DATA_DIR'] = str(tmp)
    os.environ['FLOW_AI_USER_DAILY_LIMIT'] = os.environ['FLOW_AI_DAILY_LIMIT'] = '100000'
    import app
    app.DB, app.DATA = tmp / 'eval.sqlite3', tmp
    app.init()
    c = app.db()
    c.execute("INSERT OR IGNORE INTO users(id,username,password) VALUES(1,'shadow-eval','x')")
    c.commit()
    data = json.loads(Path(args.cases).read_text(encoding='utf-8'))
    tasks = [t for t in args.tasks.split(',') if t in ('shadow', 'say')]
    if args.limit:
        data = {**data, **{t: data[t][:args.limit] for t in tasks}}
    paths = [p for p in args.paths.split(',') if p in ('gemini', 'omni')]
    items = []
    for task, case, rec, audio in recordings(data, tasks):
        kind = 'next-shadow' if task == 'shadow' else 'next-say'
        messages, convert = shadow_prompt(c, case['sentence'], audio) if task == 'shadow' else say_prompt(c, case['word'], audio)
        order = paths[len(items) % len(paths):] + paths[:len(items) % len(paths)]  # take turns going first
        for path in order:
            r = ve.one(run_gemini, messages, audio, kind) if path == 'gemini' else ve.one(run_omni, messages, audio, kind, args.omni)
            item = {'task': task, 'case': case.get('id') or case['word'], 'path': path, **{k: rec[k] for k in ('read', 'voice', 'planted', 'accent')}}
            if 'error' in r:
                item['error'] = r['error']
            else:
                item.update(model_s=r['model_s'], served=r['served'], cost=r['cost'])
                got = ve.one(lambda: (shadow_item if task == 'shadow' else say_item)(case, rec, read(r['raw'], convert)))
                item.update(got if 'error' not in got else {'error': 'answer not read: ' + got['error'], 'raw': r['raw'][:300]})
            items.append(item)
            print(f"{task:<6} {item['case']:<6} {rec['voice']:<16} {'planted' if rec['planted'] else 'right  '} {path:<6} {brief(item)}", flush=True)
    report = {'run_at': time.time(), 'tasks': tasks, 'paths': paths, 'omni': args.omni, 'summary': summarize(items), 'items': items}
    print(describe(report['summary']))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
