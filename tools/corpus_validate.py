#!/usr/bin/env python3
"""Validate Flow Corpus v5 files (see flow/corpus_data/v5/SPEC.md).

Usage: python3 tools/corpus_validate.py [files...]   (default: every v5 file)
Exit code 1 when any error is found. Warnings are advisory but should be read.
"""
import copy, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / 'flow'
sys.path.insert(0, str(FLOW))
V5 = FLOW / 'corpus_data' / 'v5'

THEMES = ('campus', 'travel', 'life', 'work', 'culture', 'science')
GENRES = ('article', 'story', 'dialogue', 'explainer', 'opinion', 'interview', 'email', 'guide')
CEFR = ('A2', 'B1', 'B2', 'C1')
NODES = ('tense-present', 'tense-past', 'tense-perfect', 'clause-relative', 'clause-noun', 'clause-adverb',
         'conditional-real', 'conditional-unless', 'conditional-modal', 'subjunctive-now', 'subjunctive-past',
         'subjunctive-mixed', 'nonfinite-infinitive', 'nonfinite-gerund', 'nonfinite-participle',
         'agreement-head', 'agreement-each', 'agreement-either')
WORDS = {'A2': (90, 140), 'B1': (140, 210), 'B2': (210, 300), 'C1': (280, 380)}
SENT_LEN = {'A2': (5, 12.5), 'B1': (9, 17), 'B2': (12, 24), 'C1': (15, 30)}
# share of words whose easiest form ranks beyond 3000: soft bands
RARE = {'A2': (0, 0.07), 'B1': (0.01, 0.12), 'B2': (0.03, 0.16), 'C1': (0.045, 0.25)}  # calibrated on v5 (base-form ranks)
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def has_word(term, text):
    return re.search(r'(?<![A-Za-z])' + re.escape(term) + r'(?![A-Za-z])', text, re.I) is not None


def difficulty(body):
    import next_service as nx
    from lab_service import sentences
    sents = sentences(body)
    words = WORD.findall(body)
    ranked = []
    for s in sents:
        toks = WORD.findall(s)
        for i, w in enumerate(toks):
            if i > 0 and w[0].isupper():
                continue  # proper nouns
            # Use the most frequent of the word and its base forms: "wanted"/"said" have their
            # own (rarer) dictionary rows, but are as easy as "want"/"say".
            d = nx.dictionary()
            ranks = [d[c]['rank'] for c in nx.lemma_candidates(w) if c in d]
            if ranks:
                ranked.append(min(ranks))
    rare = sum(r > 3000 for r in ranked) / max(1, len(ranked))
    return {'words': len(words), 'sentences': len(sents), 'avg_len': round(len(words) / max(1, len(sents)), 1), 'rare': round(rare, 3)}


def check_pack(p, theme, cefr, seen):
    from lab_service import validate_pack, sentences
    from quality_service import checks
    E, W = [], []
    need = ('id', 'title', 'title_en', 'summary_zh', 'level', 'cefr', 'theme', 'genre', 'body', 'questions', 'dictation_index',
            'vocabulary', 'expressions', 'grammar', 'knowledge', 'speaking', 'writing', 'task', 'tags', 'source')
    missing = [k for k in need if k not in p]
    if missing:
        return [f'缺少字段：{", ".join(missing)}'], W, None
    pid = p['id']
    if not re.fullmatch(rf'v5-{theme}-{cefr.lower()}-[a-z0-9]+(?:-[a-z0-9]+)*', pid):
        E.append(f'id 格式应为 v5-{theme}-{cefr.lower()}-<slug>')
    if pid in seen:
        E.append(f'id 重复（也出现在 {seen[pid]}）')
    if p['cefr'] != cefr or p['theme'] != theme:
        E.append('cefr/theme 与文件名不一致')
    if p['level'] != ('B2' if cefr == 'C1' else cefr):
        E.append('level 应为 ' + ('B2（C1 材料）' if cefr == 'C1' else cefr))
    if p['genre'] not in GENRES:
        E.append('genre 不在允许范围')
    body = p['body']
    if not isinstance(body, str) or '\n' in body:
        E.append('body 必须是单段字符串'); return E, W, None
    if len(body) > 2600:
        E.append(f'body 超过 2600 字符（{len(body)}）')
    for k, lo, hi in (('title', 2, 30), ('title_en', 4, 120), ('summary_zh', 10, 140), ('speaking', 6, 300), ('writing', 6, 300), ('source', 2, 60)):
        v = p.get(k)
        if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
            E.append(f'{k} 长度应在 {lo}–{hi} 字符')
    try:
        validate_pack(copy.deepcopy(p))
    except (ValueError, TypeError, KeyError) as exc:
        E.append('系统校验失败：' + str(exc))
    q = checks(p)
    E += ['质量检查：' + x for x in q['errors']]
    W += ['质量检查：' + x for x in q['warnings'] if '篇幅偏离' not in x]
    qs = p['questions']
    if isinstance(qs, list):
        for i, qq in enumerate(qs):
            if isinstance(qq, dict) and isinstance(qq.get('evidence'), str) and qq['evidence'] not in body:
                E.append(f'第 {i + 1} 题 evidence 不是正文原样子串（大小写/标点也要一致）')
    vocab = p['vocabulary']
    if not isinstance(vocab, list) or not 3 <= len(vocab) <= 5:
        E.append('vocabulary 需要 3–5 个')
    else:
        for v in vocab:
            if not isinstance(v, dict) or not has_word(v.get('term', ''), body):
                E.append(f'词汇 {v.get("term") if isinstance(v, dict) else v!r} 未以相同词形出现在正文')
    ex = p['expressions']
    if not isinstance(ex, list) or not 4 <= len(ex) <= 6:
        E.append('expressions 需要 4–6 个')
    else:
        for x in ex:
            t = x.get('text', '') if isinstance(x, dict) else ''
            if not t or t not in body:
                E.append(f'表达 {t!r} 不是正文原样子串')
            elif len(WORD.findall(t)) < 2:
                E.append(f'表达 {t!r} 应是搭配/短语（至少两个词）')
            if not isinstance(x, dict) or not x.get('meaning') or not x.get('note'):
                E.append(f'表达 {t!r} 缺少 meaning 或 note')
    g = p['grammar']
    if not isinstance(g, list) or not 1 <= len(g) <= 3 or any(n not in NODES for n in g):
        E.append('grammar 需要 1–3 个合法节点 id')
    kn = p['knowledge']
    if not isinstance(kn, list) or not 1 <= len(kn) <= 3:
        E.append('knowledge 需要 1–3 条')
    else:
        for k in kn:
            if not isinstance(k, dict) or k.get('node') not in NODES:
                E.append('knowledge.node 不合法'); continue
            if isinstance(g, list) and k['node'] not in g:
                E.append(f'knowledge 节点 {k["node"]} 未列在 grammar 中')
            if k.get('quote', '') not in body or not k.get('quote'):
                E.append(f'knowledge {k["node"]} 的 quote 不是正文原样子串')
            if not isinstance(k.get('explanation'), str) or not 8 <= len(k['explanation']) <= 220:
                E.append(f'knowledge {k["node"]} 的 explanation 应为 8–220 字')
    t = p['task']
    if not isinstance(t, dict) or not t.get('prompt') or not t.get('model') or t['model'] not in body:
        E.append('task 需要 prompt，且 model 是正文原样子串')
    if not isinstance(p['tags'], list) or not 1 <= len(p['tags']) <= 4:
        W.append('tags 建议 1–4 个')
    d = difficulty(body)
    lo, hi = WORDS[cefr]
    if not lo * 0.9 <= d['words'] <= hi * 1.1:
        E.append(f'词数 {d["words"]} 明显偏离 {cefr} 的 {lo}–{hi}')
    elif not lo <= d['words'] <= hi:
        W.append(f'词数 {d["words"]} 略偏离 {cefr} 的 {lo}–{hi}')
    slo, shi = SENT_LEN[cefr]
    if not slo <= d['avg_len'] <= shi:
        W.append(f'平均句长 {d["avg_len"]} 词，{cefr} 建议 {slo}–{shi}')
    rlo, rhi = RARE[cefr]
    if not rlo <= d['rare'] <= rhi:
        W.append(f'低频词比例 {d["rare"]:.0%}，{cefr} 建议 {rlo:.0%}–{rhi:.0%}（用词可能{"偏难" if d["rare"] > rhi else "偏简单"}）')
    if not 0 <= p.get('dictation_index', -1) < d['sentences']:
        E.append('dictation_index 超出句子范围')
    return E, W, d


def main(paths):
    files = [Path(x) for x in paths] or sorted(p for p in V5.glob('*.json') if not p.name.startswith('EXAMPLE'))
    seen, titles = {}, {}
    # register ids from all other v5 files for cross-file duplicate detection
    for f in sorted(p for p in V5.glob('*.json') if not p.name.startswith('EXAMPLE')):
        if f not in [x.resolve() for x in files]:
            try:
                for p in json.loads(f.read_text(encoding='utf-8')):
                    seen.setdefault(p.get('id'), f.name)
            except Exception:
                pass
    total_e = total_w = n = 0
    for f in files:
        m = re.fullmatch(r'([a-z]+)\.(A2|B1|B2|C1)(?:\.\d+)?\.json', f.name)
        if not m or m.group(1) not in THEMES:
            print(f'✗ {f.name}: 文件名应为 <theme>.<CEFR>.json 或 <theme>.<CEFR>.<n>.json'); total_e += 1; continue
        theme, cefr = m.groups()
        try:
            packs = json.loads(f.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            print(f'✗ {f.name}: JSON 无法解析：{exc}'); total_e += 1; continue
        if not isinstance(packs, list):
            print(f'✗ {f.name}: 顶层必须是数组'); total_e += 1; continue
        print(f'== {f.name} · {len(packs)} 篇')
        for p in packs:
            n += 1
            if not isinstance(p, dict):
                print('  ✗ 非对象条目'); total_e += 1; continue
            E, W, d = check_pack(p, theme, cefr, seen)
            seen.setdefault(p.get('id'), f.name)
            t = (p.get('title') or '').strip()
            if t and t in titles:
                E.append(f'标题与 {titles[t]} 重复')
            titles.setdefault(t, p.get('id'))
            mark = '✗' if E else ('!' if W else '✓')
            stats = f" · {d['words']}词 {d['sentences']}句 均长{d['avg_len']} 低频{d['rare']:.0%}" if d else ''
            print(f'  {mark} {p.get("id")}{stats}')
            for e in E: print('      错误：' + e)
            for w in W: print('      警告：' + w)
            total_e += len(E); total_w += len(W)
    print(f'\n共 {n} 篇 · {total_e} 个错误 · {total_w} 个警告')
    return 1 if total_e else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
