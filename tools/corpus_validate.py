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
BASE_NODES = NODES  # the knowledge graph links materials through these 18 (test_corpus_v5)
# The 26 further points (voice, modals, determiners, comparison, linking, prepositions, emphasis) are valid tags too.
NODES += tuple(n['id'] for n in __import__('grammar_more').NODES_MORE)
WORDS = {'A2': (90, 140), 'B1': (140, 210), 'B2': (210, 300), 'C1': (280, 380)}
SENT_LEN = {'A2': (5, 12.5), 'B1': (9, 17), 'B2': (12, 24), 'C1': (15, 30)}
# share of words whose easiest form ranks beyond 3000: soft bands
RARE = {'A2': (0, 0.07), 'B1': (0.01, 0.12), 'B2': (0.03, 0.16), 'C1': (0.045, 0.25)}  # calibrated on v5 (base-form ranks)
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
# SPEC v5.1 (r27 content line). What a material is for, beside its theme and genre: the learner's goal picks from these
# (r28): media -> news-commentary, film-culture; work -> workplace; abroad -> campus-life, daily-life; exam -> expository,
# argumentative; interest/daily -> story, daily-life.
PURPOSES = ('news-commentary', 'film-culture', 'workplace', 'campus-life', 'daily-life', 'expository', 'argumentative', 'story')
QTYPES = ('main', 'inference', 'vocab', 'detail')
MIN_SENTENCES = 13  # v5.1: every new material has at least 13 sentences
STOP = set('a an the of to in on for and or with without how why what when who is are be your you my our its it not but at by from'.split())


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
    elif not set(g) & set(BASE_NODES):
        E.append('grammar 至少要有 1 个基础节点（18 个之一），知识图谱靠它把材料连上语法点')
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
    E2, W2 = check_v51(p, body, d)
    return E + E2, W + W2, d


def check_v51(p, body, d):
    """Rules added in SPEC v5.1: question types, purposes, provenance labels, quotes. A material marked
    "spec": "5.1" (everything written from the r27 content line on) must meet all of them."""
    E, W = [], []
    new = p.get('spec') == '5.1'
    qs = p.get('questions') if isinstance(p.get('questions'), list) else []
    types = [q.get('type') for q in qs if isinstance(q, dict)]
    if any(t is not None and t not in QTYPES for t in types):
        E.append('题型 type 只能是 ' + ' / '.join(QTYPES))
    pur = p.get('purposes')
    if pur is None:
        E.append('缺少 purposes（目的标签）')
    elif not isinstance(pur, list) or not 1 <= len(pur) <= 3 or any(x not in PURPOSES for x in pur) or len(set(pur)) != len(pur):
        E.append('purposes 需要 1–3 个，取自 ' + ' / '.join(PURPOSES))
    if p.get('reviewed'):
        E.append('不能标「人工审校」（reviewed）：没有人工逐篇审校的记录')
    # 经人工审核 (2026-11-25): only a text the user has read in full, with the day; never true by default
    if 'reviewed_by_human' in p:
        if not isinstance(p['reviewed_by_human'], bool):
            E.append('reviewed_by_human 只能是 true 或 false')
        elif p['reviewed_by_human'] and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(p.get('reviewed_on', ''))):
            E.append('reviewed_by_human 为 true 时要写 reviewed_on（用户读完这篇的日期，YYYY-MM-DD）')
    if 'ai' in p and p['ai'] != 'AI 辅助编写':
        E.append('ai 只能写「AI 辅助编写」')
    for r in p.get('references') or []:
        if not isinstance(r, dict) or not str(r.get('url', '')).startswith('https://') or not r.get('title') \
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(r.get('verified', ''))):
            E.append('references 每条要有 title、https 的 url 和核实日期 verified（YYYY-MM-DD）；没核实过的不要放')
    for qt in p.get('quotes') or []:
        if not isinstance(qt, dict) or not qt.get('text') or qt['text'] not in body:
            E.append('quotes.text 必须是正文原样子串'); continue
        if not qt.get('author') or not qt.get('work') or type(qt.get('year')) is not int or type(qt.get('author_died')) is not int:
            E.append(f'名句 {qt["text"][:30]!r} 要写出处：author、work、year（发表年）、author_died（作者卒年）')
        elif qt['year'] > 1900 or qt['author_died'] > 1955:
            E.append(f'名句 {qt["text"][:30]!r} 可能还没进入公有领域（只用 1900 年前发表、作者 1955 年前去世的）')
    if new:
        if d and d['sentences'] < MIN_SENTENCES:
            E.append(f'v5.1 材料至少 {MIN_SENTENCES} 句（现在 {d["sentences"]} 句）')
        if not 3 <= len(qs) <= 4:
            E.append('v5.1 材料要 3–4 道题')
        if any(t is None for t in types):
            E.append('v5.1 每道题都要标题型 type')
        elif not {'main', 'inference', 'vocab'} <= set(types):
            E.append('v5.1 题型至少含主旨 main、推断 inference、词义 vocab 各一道')
        if p.get('ai') != 'AI 辅助编写':
            E.append('v5.1 材料要写 "ai": "AI 辅助编写"')
    elif len(qs) < 3:
        W.append('只有 2 道题，补题时补到 3–4 道并标题型')
    return E, W


def _tokens(text):
    return {w.lower() for w in WORD.findall(text or '') if w.lower() not in STOP}


def _shingles(body, n=6):
    w = [x.lower() for x in WORD.findall(body)]
    return {' '.join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def similar(packs):
    """Pairs of v5 materials that look like the same topic (English titles share most content words) or share
    whole passages (6-word runs): (error?, message). Same-story rewrites at another level are expected only for
    graded-* and are not in v5."""
    out = []
    t = [(p, _tokens(p.get('title_en')), _shingles(p.get('body', ''))) for p in packs]
    for i in range(len(t)):
        for j in range(i + 1, len(t)):
            a, ta, sa = t[i]
            b, tb, sb = t[j]
            same_series = (a.get('series') or {}).get('id') and (a.get('series') or {}).get('id') == (b.get('series') or {}).get('id')
            if ta and tb and not same_series and len(ta & tb) / len(ta | tb) >= 0.6:
                out.append((False, f'{a["id"]} 和 {b["id"]} 的英文标题很像，确认不是同一个话题'))
            if sa and sb and len(sa & sb) / min(len(sa), len(sb)) >= 0.15:
                out.append((True, f'{a["id"]} 和 {b["id"]} 有大段相同的句子'))
    return out


def gaps():
    """Counts per level: purposes, genres and themes, to pick the next batch's topics where the corpus is thin."""
    import collections
    packs = [p for f in sorted(V5.glob('*.json')) if not f.name.startswith('EXAMPLE') for p in json.loads(f.read_text(encoding='utf-8'))]
    for cefr in CEFR:
        ps = [p for p in packs if p['cefr'] == cefr]
        print(f'== {cefr} · {len(ps)} 篇（v5.1 {sum(p.get("spec") == "5.1" for p in ps)} 篇）')
        for name, key, values in (('目的', 'purposes', PURPOSES), ('体裁', 'genre', GENRES), ('话题', 'theme', THEMES)):
            cnt = collections.Counter(x for p in ps for x in (p.get(key) if isinstance(p.get(key), list) else [p.get(key)]))
            print(f'  {name}：' + '  '.join(f'{v} {cnt.get(v, 0)}' for v in values))


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
    every = [p for f in sorted(V5.glob('*.json')) if not f.name.startswith('EXAMPLE') for p in json.loads(f.read_text(encoding='utf-8'))]
    names = {f.name for f in files}
    mine = {p.get('id') for f in files if f.exists() and f.name in names for p in (json.loads(f.read_text(encoding='utf-8')) or [])
            if isinstance(p, dict)}
    for err, msg in similar(every + [p for f in files if f.resolve().parent != V5.resolve() for p in json.loads(f.read_text(encoding='utf-8'))]):
        if not any(m in msg for m in mine if m):
            continue
        print(('✗ 错误：' if err else '! 警告：') + msg)
        total_e += err; total_w += not err
    print(f'\n共 {n} 篇 · {total_e} 个错误 · {total_w} 个警告')
    return 1 if total_e else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--gaps']:
        gaps(); sys.exit(0)
    sys.exit(main(sys.argv[1:]))
