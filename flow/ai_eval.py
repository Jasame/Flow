#!/usr/bin/env python3
"""批改考题集: the AI's marking checked on fixed questions, before a model or a prompt is changed.

    python3 ai_eval.py [--env-file /etc/flow.env] [--text-model NAME] [--main-model NAME] [--route MODEL]
                       [--only rewrite,essay,translate,content] [--quick] [--output report.json]

The questions are in corpus_data/ai-eval.json:
- rewrite (仿写): learners' sentences with one typical error each, which must be put right in the expected way, and
  correct sentences, which must be left alone;
- essay (写作): three short texts on the same task, good, middling and weak, marked twice each: the totals must come
  out in that order, and the two marks of one text close to each other;
- translate (翻译): two translations of the same sentence, a good and a poor one, which must be scored well apart;
- content (内容): a sentence explained, example sentences, a level rewrite, a role-play's opening line, a sentence
  translated: no right answer, but each must be fit to show a learner (the shape, the explanation quoting the sentence,
  each example using its word, the rewrite keeping the text's numbers, the opening line a short English sentence).

It runs the site's own marking code (next_service.rewrite, output_service.essay and output_service.translate: the
same prompts and the same reading of the answers) with the model of the env file, in a throwaway database, so the
site's data is never read or written. --text-model / --main-model try another model of the gateway for this run
only (nothing on the server changes); --route sends every task to one gateway model name for this run (ai_routes:
flow-text for Gemini, a 百炼 line such as flow-qwen-plus); without it the tasks take the server's routes (FLOW_AI_ROUTES, or the console's with --site-settings). Each answer
says which service gave it: when the text service fails, the main one answers, and the report counts those. The report
also has the run's tokens and estimated cost by task and model (usage), and the gateway names it asked (asked): a run
takes the eval lane (flow-eval-X for flow-text-X, the owner's own 百炼 account) where the gateway has it; --lane none
asks the learners' names. About 90 model calls a run; --quick (the
nightly check, ai_routes.nightly) is a sample of about 17. Exit status 0 when every question passed, 1 when some did
not, 2 when no model is configured.
"""
import argparse, json, os, re, secrets, statistics, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / 'corpus_data' / 'ai-eval.json'
HAN = re.compile(r'[㐀-鿿]')
KINDS = ('rewrite', 'essay', 'translate')
CONTENT = ('explain', 'examples', 'variant', 'dialog', 'transsrc')
QUICK = {'rewrite': ('third-person-s', 'although-but', 'if-will', 'suggest-somebody-to', 'keep-second-conditional', 'keep-inversion'),
         'translate': 1}  # the nightly sample: 4 errors to put right, 2 correct sentences to leave alone, 1 translation pair
STABLE = 2         # the two marks of one essay (4–20 points) differ by this much at most
GAP = 1            # a better essay scores at least this much more (on the average of its marks)
GOOD, POOR, APART = 0.7, 0.5, 0.3   # translation scores: the good one at least, the poor one at most, and this far apart


def words(s):
    return re.findall(r"[a-z0-9']+", str(s or '').lower().replace('’', "'"))


def has(text, fragment):
    """Whether the words of fragment occur, in order and whole, in text (punctuation and case aside); a fragment
    starting with ^ must begin the text."""
    f, t = ' '.join(words(fragment)), ' '.join(words(text))
    return (t + ' ').startswith(f + ' ') if fragment.startswith('^') else f' {f} ' in f' {t} '


def load(path=CASES):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# ---------- what a right marking is ----------

def check_rewrite(case, result, status):
    """The reasons this marking is wrong ([] when it is right)."""
    if status != 200:
        return [f'没有批改结果（{status}：{(result or {}).get("error", "")}）']
    r, why = result['result'], []
    fixed = r.get('corrected') or ''
    if case['expect'] == 'fix':
        if r.get('verdict') == 'natural':
            why.append('判成了「没有问题」')
        why += [f'改后还留着错误：{b}' for b in case['bad'] if has(fixed, b)]
        if not any(has(fixed, g) for g in case['good']):
            why.append('改后的句子里没有预期的改法')
        if not r.get('changes'):
            why.append('没有列出改了哪里')
    else:
        if words(fixed) != words(case['text']):
            why.append('把正确的句子改了：' + fixed[:100])
        if r.get('verdict') == 'rewrite':
            why.append('判成了「需要重写」')
    if not HAN.search(r.get('summary') or ''):
        why.append('总评不是中文')
    return why


def check_essays(cases, marks):
    """marks: {id: [totals of each marking]} (4–20). The reasons the marking is wrong, per essay and overall."""
    why = {}
    for e in cases:
        got = marks.get(e['id']) or []
        if not got:
            why.setdefault(e['id'], []).append('没有评分结果')
        elif max(got) - min(got) > STABLE:
            why.setdefault(e['id'], []).append(f'同一篇两次评分差了 {max(got) - min(got)} 分（{"、".join(map(str, got))}）')
    ranked = sorted(cases, key=lambda e: e['rank'])
    for better, worse in zip(ranked, ranked[1:]):
        a, b = marks.get(better['id']), marks.get(worse['id'])
        if a and b and statistics.mean(a) < statistics.mean(b) + GAP:
            why.setdefault(worse['id'], []).append(f'分数没有低于更好的「{better["id"]}」（{statistics.mean(b):g} 对 {statistics.mean(a):g}）')
    return why


def check_translation(case, good, poor):
    """good, poor: (result, status) for the two translations. The reasons the scoring is wrong."""
    why = []
    for name, (result, status) in (('好的译文', good), ('差的译文', poor)):
        if status != 200:
            why.append(f'{name}没有评分结果（{status}）')
    if why:
        return why
    g, p = good[0]['result']['score'], poor[0]['result']['score']
    if g < GOOD:
        why.append(f'好的译文只给了 {g:g}')
    if p > POOR:
        why.append(f'差的译文给了 {p:g}')
    if g - p < APART:
        why.append(f'好坏只差 {g - p:.2f}')
    if not HAN.search(good[0]['result'].get('accuracy') or ''):
        why.append('点评不是中文')
    return why


def check_content(kind, case, result, status, ctx):
    """The reasons this generated content is not fit to show a learner ([] when it is)."""
    if status != 200:
        return [f'没有结果（{status}：{(result or {}).get("error", "")}）']
    why = []
    if kind == 'explain':
        r = result['result']
        if not HAN.search(r.get('translation') or ''):
            why.append('翻译不是中文')
        quoted = [pt for pt in r.get('points') or [] if has(ctx['sentence'], pt.get('text') or '')]
        if len(quoted) < 2:
            why.append(f'讲解的片段只有 {len(quoted)} 个出自原句')
        if not (r.get('pattern') or {}).get('frame'):
            why.append('没有可模仿的句型')
    elif kind == 'examples':
        got = result.get('examples') or {}
        if len(got) < len(case['words']) - 1:
            why.append(f'{len(case["words"])} 个词只写出 {len(got)} 个例句')
        for w, items in got.items():
            e = items[0]
            if not HAN.search(e.get('zh') or ''):
                why.append(f'{w} 的例句没有中文翻译')
            if not 6 <= len(words(e.get('text'))) <= 32:
                why.append(f'{w} 的例句长度不对（{len(words(e.get("text")))} 个词）')
    elif kind == 'variant':
        nums = set(re.findall(r'\d+(?:\.\d+)?', ctx['body']))
        lost = sorted(n for n in nums if n not in result.get('body', ''))
        if lost:
            why.append('改写丢了原文的数字：' + '、'.join(lost))
        if HAN.search(result.get('body') or ''):
            why.append('改写的正文里有中文')
    elif kind == 'dialog':
        r = result['result']
        reply = r.get('reply') or ''
        if HAN.search(reply) or not words(reply):
            why.append('第一句不是英文')
        if len(re.findall(r'[.!?](?:\s|$)', reply)) > 3:
            why.append('第一句太长（超过 3 句）')
        if not HAN.search(r.get('scene') or ''):
            why.append('情景说明不是中文')
    elif kind == 'transsrc':
        zh = (result.get('result') or {}).get('zh') or result.get('zh') or ''
        if len(HAN.findall(zh)) < 8 or re.search(r'[A-Za-z]{4,}', zh):
            why.append('译文不是通顺的中文：' + zh[:60])
    return why


# ---------- the run ----------

def run(cases, kinds=KINDS + ('content',), repeat=2, say=print, quick=False):
    """Every question of these kinds through the site's marking code, in a throwaway database. The report."""
    import app
    keep = (app.DB, app.DATA)
    tmp = Path(tempfile.mkdtemp(prefix='flow-ai-eval-'))
    app.DB, app.DATA = tmp / 'eval.sqlite3', tmp
    try:
        return _run(cases, kinds, repeat, say, quick)
    finally:
        app.DB, app.DATA = keep


def _run(cases, kinds, repeat, say, quick=False):
    import app, ai_routes, chat_service, next_service as nx, output_service as out, vocab_service as vs
    app.init()
    report = {'when': time.strftime('%Y-%m-%d %H:%M:%S'), 'models': {'main': os.getenv('FLOW_AI_MODEL', ''), 'text': os.getenv('FLOW_TEXT_AI_MODEL', '')},
              'routes': {k: v['route'] for k, v in ai_routes.routes().items()}, 'quick': quick, 'items': [], 'summary': {}}
    if quick:
        cases = {**cases, 'rewrite': [x for x in cases['rewrite'] if x['id'] in QUICK['rewrite']], 'translate': cases['translate'][:QUICK['translate']]}
        repeat = 1
    pack = cases['pack']
    with app.db() as c:
        c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('ai-eval', 'no-login'))
        c.commit()
        uid = c.execute("SELECT id FROM users WHERE username='ai-eval'").fetchone()[0]
        nx.save_profile(c, uid, {'level': 'B1', 'goal': next(iter(nx.GOALS)), 'themes': [], 'minutes': 15})
        row = nx._pack_row(c, uid, pack)
        if not row:
            raise SystemExit(f'考题用的材料 {pack} 不在这个版本里')
        p = json.loads(row['content'])

        def call(kind, case, fn, data):
            c.execute('UPDATE next_profiles SET level=? WHERE user_id=?', (case.get('level') or 'B1', uid)); c.commit()
            chat_service.LAST['provider'] = None
            data = {'pack': pack, 'request_id': f'eval-{kind}-{secrets.token_hex(6)}', **data}
            t = time.monotonic()
            result, status = fn(c, uid, data)
            return result, status, {'seconds': round(time.monotonic() - t, 2), 'service': chat_service.LAST.get('provider')}

        if 'rewrite' in kinds:
            for case in cases['rewrite']:
                result, status, meta = call('rewrite', case, nx.rewrite, {'text': case['text']})
                why = check_rewrite(case, result, status)
                r = (result or {}).get('result') or {}
                report['items'].append({'kind': 'rewrite', 'id': case['id'], 'topic': case['topic'], 'expect': case['expect'], 'ok': not why, 'why': why,
                                        'text': case['text'], 'verdict': r.get('verdict'), 'corrected': r.get('corrected'), 'status': status, **meta})
                say(('  ✓ ' if not why else '  ✗ ') + f"仿写 {case['id']}" + ('' if not why else '：' + '；'.join(why)))
        if 'essay' in kinds:
            marks, metas = {}, {}
            for case in cases['essay']:
                for n in range(repeat):
                    result, status, meta = call('essay', case, out.essay, {'text': case['text']})
                    metas.setdefault(case['id'], []).append({**meta, 'status': status})
                    if status == 200:
                        marks.setdefault(case['id'], []).append(sum(result['result']['scores'].values()))
            why = check_essays(cases['essay'], marks)
            for case in cases['essay']:
                w = why.get(case['id'], [])
                report['items'].append({'kind': 'essay', 'id': case['id'], 'rank': case['rank'], 'ok': not w, 'why': w, 'marks': marks.get(case['id'], []),
                                        'seconds': sum(m['seconds'] for m in metas[case['id']]), 'service': metas[case['id']][-1]['service'],
                                        'status': max(m['status'] for m in metas[case['id']])})
                say(('  ✓ ' if not w else '  ✗ ') + f"写作 {case['id']}（{'、'.join(map(str, marks.get(case['id'], []))) or '—'} 分）" + ('' if not w else '：' + '；'.join(w)))
        if 'translate' in kinds:
            for case in cases['translate']:
                i = next((k for k in range(80) if out._sentence(p, k) == case['sentence']), None)
                if i is None:
                    report['items'].append({'kind': 'translate', 'id': case['id'], 'ok': False, 'why': ['材料里没有这一句了：考题要跟着材料更新'], 'status': None})
                    say(f"  ✗ 翻译 {case['id']}：材料里没有这一句了")
                    continue
                c.execute('INSERT OR REPLACE INTO next_translations VALUES(?,?,?,?)', (pack, case['sentence'], case['zh'], time.time())); c.commit()
                good = call('translate', case, out.translate, {'i': i, 'direction': 'zh2en', 'text': case['good']})
                poor = call('translate', case, out.translate, {'i': i, 'direction': 'zh2en', 'text': case['bad']})
                why = check_translation(case, good[:2], poor[:2])
                score = lambda x: (x[0] or {}).get('result', {}).get('score') if x[1] == 200 else None
                report['items'].append({'kind': 'translate', 'id': case['id'], 'ok': not why, 'why': why, 'scores': [score(good), score(poor)],
                                        'seconds': good[2]['seconds'] + poor[2]['seconds'], 'service': poor[2]['service'], 'status': max(good[1], poor[1])})
                say(('  ✓ ' if not why else '  ✗ ') + f"翻译 {case['id']}（好 {score(good)} / 差 {score(poor)}）" + ('' if not why else '：' + '；'.join(why)))
        if 'content' in kinds:
            cc = cases.get('content') or {}
            for case in cc.get('explain', []):
                sent = out._sentence(p, case['i'])
                result, status, meta = call('explain', case, nx.explain, {'sentence': sent})
                why = check_content('explain', case, result, status, {'sentence': sent})
                report['items'].append({'kind': 'content', 'task': 'explain', 'id': case['id'], 'ok': not why, 'why': why, 'status': status, **meta})
            for case in cc.get('examples', []):
                c.execute('UPDATE next_profiles SET level=? WHERE user_id=?', (case.get('level', 'B2'), uid)); c.commit()
                todo = [w for w in case['words'] if vs.needs_example(c, w)]
                result, status, meta = call('examples', case, vs.ai_examples, {'words': todo})
                why = check_content('examples', {**case, 'words': todo}, result, status, {})
                report['items'].append({'kind': 'content', 'task': 'examples', 'id': case['id'], 'ok': not why, 'why': why, 'status': status, **meta})
            for case in cc.get('variant', []):
                result, status, meta = call('variant', case, nx.variant, {'level': case['level']})
                why = check_content('variant', case, result, status, {'body': p['body']})
                report['items'].append({'kind': 'content', 'task': 'variant', 'id': case['id'], 'ok': not why, 'why': why, 'status': status, **meta})
            for case in cc.get('dialog', []):
                result, status, meta = call('dialog', case, out.dialog, {'history': []})
                why = check_content('dialog', case, result, status, {})
                report['items'].append({'kind': 'content', 'task': 'dialog', 'id': case['id'], 'ok': not why, 'why': why, 'status': status, **meta})
            for case in cc.get('transsrc', []):
                result, status, meta = call('transsrc', case, out.translate_source, {'i': case['i']})
                why = check_content('transsrc', case, result, status, {})
                report['items'].append({'kind': 'content', 'task': 'transsrc', 'id': case['id'], 'ok': not why, 'why': why, 'status': status, **meta})
            for x in report['items']:
                if x['kind'] == 'content':
                    say(('  ✓ ' if x['ok'] else '  ✗ ') + f"内容 {x['id']}" + ('' if x['ok'] else '：' + '；'.join(x['why'])))
        s = ai_routes.summary(c, days=1)
        report['asked'] = sorted({r[0] for r in c.execute('SELECT DISTINCT model FROM ai_calls')})
        report['usage'] = {'calls': s['total']['calls'], 'cost': s['total']['cost'], 'prompt': s['total']['prompt'], 'cached': s['total']['cached'],
                           'completion': s['total']['completion'], 'estimated': s['total']['estimated'],
                           'by_task': {k['kind']: {x: k[x] for x in ('calls', 'failed', 'backup', 'prompt', 'cached', 'completion', 'cost', 'seconds')}
                                       for k in s['kinds'] if k['calls']},
                           'models': {m['name']: {x: m[x] for x in ('calls', 'prompt', 'cached', 'completion', 'cost')} for m in s['models']}}
    report['summary'] = summarize(report['items'])
    return report


def summarize(items):
    rw = [x for x in items if x['kind'] == 'rewrite']
    part = lambda xs: {'passed': sum(1 for x in xs if x['ok']), 'total': len(xs)}
    secs = [x['seconds'] for x in items if x.get('seconds') is not None]
    return {'passed': sum(1 for x in items if x['ok']), 'total': len(items),
            'rewrite_fix': part([x for x in rw if x['expect'] == 'fix']), 'rewrite_keep': part([x for x in rw if x['expect'] == 'keep']),
            'essay': part([x for x in items if x['kind'] == 'essay']), 'translate': part([x for x in items if x['kind'] == 'translate']),
            'content': part([x for x in items if x['kind'] == 'content']),
            'no_answer': sum(1 for x in items if x.get('status') not in (200, None)),
            'services': {k: sum(1 for x in items if x.get('service') == k) for k in ('text', 'main')},
            'seconds': {'median': round(statistics.median(secs), 1) if secs else None, 'max': round(max(secs), 1) if secs else None}}


def describe(s, models, usage=None, asked=None):
    pc = lambda d: f"{d['passed']}/{d['total']}"
    text = '、'.join(n for n in (asked or []) if n != models['main']) or models['text'] or '（没有单独的文字模型）'
    answered = '、'.join(n for n in ((usage or {}).get('models') or {}) if n != models['main'])
    lines = [f"模型：文字 {text}" + (f"（实际回答：{answered}）" if answered else '') + f" · 主模型 {models['main'] or '—'}",
             f"错句改对：{pc(s['rewrite_fix'])}　正确句没被改：{pc(s['rewrite_keep'])}　写作评分：{pc(s['essay'])}　翻译评分：{pc(s['translate'])}"
             + (f"　内容：{pc(s['content'])}" if s.get('content', {}).get('total') else ''),
             f"合计 {s['passed']}/{s['total']} 题通过；没拿到结果 {s['no_answer']} 次；由文字服务回答 {s['services']['text']} 题、主服务 {s['services']['main']} 题"
             + (f"；每题用时中位数 {s['seconds']['median']} 秒，最长 {s['seconds']['max']} 秒" if s['seconds']['median'] is not None else '')]
    if models['text'] and s['services']['main']:
        lines.append('注意：有题目是主服务答的（文字服务出错后自动换了），这部分不代表文字模型的水平。')
    if usage:
        lines.append(f"这一轮 {usage['calls']} 次调用，输入 {usage['prompt']:,} token（命中缓存 {usage['cached']:,}），输出 {usage['completion']:,}，"
                     f"估算 ¥{usage['cost']:.3f}" + ('；Gemini 部分按文字长度估算，不含思考 token' if usage.get('estimated') else ''))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='批改考题集：用固定的题检查 AI 批改的质量')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--text-model', help='这次改用网关里的另一个文字模型（服务器设置不变）')
    ap.add_argument('--main-model', help='这次改用另一个主模型')
    ap.add_argument('--route', help='这次所有任务都问网关里的这个模型名（如 flow-text、flow-qwen-plus）')
    ap.add_argument('--site-settings', help='用这个网站的后台设置（console-settings.json）里的线路')
    ap.add_argument('--quick', action='store_true', help='只考一小部分（每晚的小评测，约 17 次调用）')
    ap.add_argument('--lane', choices=('eval', 'none'), default='eval', help='eval（默认）：网关有 flow-eval-* 时走它（研发账号）；none：和学员用同一个名字')
    ap.add_argument('--only', help='只考其中几类：rewrite,essay,translate,content')
    ap.add_argument('--cases', default=str(CASES))
    ap.add_argument('--output', help='把每道题的详细结果写进这个 JSON 文件')
    args = ap.parse_args(argv)
    if Path(args.env_file).is_file():
        from studio_setup import read_env
        for k, v in read_env(Path(args.env_file).read_text()).items():
            if k.startswith(('FLOW_', 'GOOGLE_')):
                os.environ[k] = v
    if args.text_model:
        os.environ['FLOW_TEXT_AI_MODEL'] = args.text_model
    if args.main_model:
        os.environ['FLOW_AI_MODEL'] = args.main_model
    if args.site_settings:  # the site's console routes, read before the run's own throwaway data folder takes over
        try:
            routes = json.loads(Path(args.site_settings).read_text(encoding='utf-8')).get('ai_routes') or {}
        except (OSError, ValueError):
            routes = {}
        if routes:
            os.environ['FLOW_AI_ROUTES'] = json.dumps(routes)
    if args.route:
        os.environ['FLOW_AI_ROUTES'] = json.dumps({'*': args.route})
    # development calls on their own account: flow-text-X asks flow-eval-X when the gateway has it (ai_routes lanes)
    os.environ['FLOW_AI_LANE'] = '' if args.lane == 'none' else 'eval'
    # the run's own throwaway data, and no daily cap on it (the site's counts are elsewhere and untouched)
    os.environ['FLOW_DATA_DIR'] = tempfile.mkdtemp(prefix='flow-ai-eval-data-')
    os.environ['FLOW_AI_USER_DAILY_LIMIT'] = os.environ['FLOW_AI_DAILY_LIMIT'] = '100000'
    sys.path.insert(0, str(HERE))
    from lab_service import ai_enabled
    if not ai_enabled():
        print('没有配置 AI 模型（FLOW_AI_MODEL 等），无法考试。')
        return 2
    kinds = tuple(k for k in (args.only or ','.join(KINDS + ('content',))).split(',') if k in KINDS + ('content',))
    report = run(load(args.cases), kinds, quick=args.quick)
    print(describe(report['summary'], report['models'], report.get('usage'), report.get('asked')))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0 if report['summary']['passed'] == report['summary']['total'] else 1


if __name__ == '__main__':
    sys.exit(main())
