#!/usr/bin/env python3
"""The user's weekly spot-check of new featured materials: two per level, picked at random (用户决策「每级每周抽 2 篇」).

    python3 tools/review_list.py <out.md> <material id or v5 file> [...] [--base https://flow.jasa.hk] [--seed 2026-11-24]

Writes a Markdown checklist: for each picked material, a link on the 内测版, its numbers next to the level's bands,
and what to look at closely, pulled from the text itself: sentences with figures or claims about research, names of
people and places, quoted lines and their stated source, the longest sentences (where Chinglish tends to hide), and
the questions with their answers and evidence. The pick is random but repeatable for a given seed (default: today).
Batch-wide problems the user finds go into the prompts and tools/corpus_validate.py, not only into the one text
(flow/corpus_data/v5/PRODUCTION.md).
"""
import datetime, json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flow'))
sys.path.insert(0, str(ROOT / 'tools'))

LEVELS = ('A2', 'B1', 'B2', 'C1')
PER_LEVEL = 2
CLAIM = re.compile(r'\d|percent|per cent|hundred|thousand|million|billion|research|researchers|scientists|studies|study shows|'
                   r'experiments?|evidence|century|centuries|always|never|everyone|nobody', re.I)
LABEL = re.compile(r'^([A-Z][a-z]+(?: [A-Z][a-z]+)?):\s+')
NOT_NAMES = set('I Mr Mrs Ms Dr Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May '
                'June July August September October November December English Chinese Q Interviewer Flow OK Okay'.split())
TYPE = {'main': '主旨', 'inference': '推断', 'vocab': '词义', 'detail': '细节'}


def materials():
    import content_v50
    return {p['id']: p for p in content_v50.v5_materials()}


def names(p, sents):
    """People, places and works: speaker labels, titled names (Dr Shaw), and capitalised words that do not start a
    sentence. Days, months and the like are left out."""
    found = []
    add = lambda w: found.append(w) if w not in found else None
    for s in sents:
        m = LABEL.match(s)
        if m:
            add(m.group(1))
        s = LABEL.sub('', s)
        for m in re.finditer(r"\b((?:Dr|Mr|Mrs|Ms) [A-Z][a-z]+|[A-Z][a-z]+(?: [A-Z][a-z]+)*)", s):
            w = m.group(1)
            if m.start() == 0 and ' ' not in w:
                continue  # a single capitalised first word is just the start of the sentence; two (Mark Twain) are a name
            if w.split()[0].rstrip('s') in NOT_NAMES or w.split()[0] in NOT_NAMES and ' ' not in w:
                continue
            add(w)
    return found


def section(p, base):
    import next_service as nx
    import corpus_validate as cv
    sents = nx.sentences(p['body'])
    d = cv.difficulty(p['body'])
    lv = p['cefr']
    lo, hi = cv.WORDS[lv]; slo, shi = cv.SENT_LEN[lv]; rlo, rhi = cv.RARE[lv]
    flag = lambda ok: '' if ok else ' ⚠'
    out = [f"### {p['title']}　{p['title_en']}",
           f"- 链接：{base}/#/m/{p['id']}　（`{p['id']}`，{p['genre']}，目的：{'、'.join(p.get('purposes') or [])}）",
           f"- 难度：{d['words']} 词（{lv} {lo}–{hi}）{flag(lo <= d['words'] <= hi)}；{d['sentences']} 句；"
           f"平均句长 {d['avg_len']}（{slo}–{shi}）{flag(slo <= d['avg_len'] <= shi)}；"
           f"低频词 {d['rare']:.0%}（{rlo:.0%}–{rhi:.0%}）{flag(rlo <= d['rare'] <= rhi)}。读的时候想一想：{lv} 的学习者读得下来吗？"]
    claims = [s for s in sents if CLAIM.search(LABEL.sub('', s))]
    out.append('- **事实和数字**（拿不准的说法，直接标出来）：' + ('' if claims else '没有带数字或研究结论的句子。'))
    out += [f'  - {s}' for s in claims[:6]]
    who = names(p, sents)
    out.append('- **人名、地名、作品名**：' + ('、'.join(who) if who else '没有。') + '　（不应出现在世的真实人物；虚构的就没问题）')
    q = p.get('quotes') or []
    if q or re.search(r'["“”]', p['body']):
        out.append('- **引用**：' + ('；'.join(f"“{x['text']}”—— {x['author']}，{x['work']}（{x['year']}），作者卒于 {x['author_died']}" for x in q)
                                   or '正文里有引号，看一看引的是不是已有作品的原句'))
        out.append('  - 核对：原句和出处对吗？已进入公有领域了吗？有没有影视台词？')
    longest = sorted(sents, key=len, reverse=True)[:2]
    out.append('- **中式英语**：通读一遍，标出读着别扭的句子。最长的两句最容易出问题：')
    out += [f'  - {s}' for s in longest]
    out.append(f"- **导读**：{p.get('summary_zh', '')}　（和正文对得上吗？）")
    out.append('- **题目**（答案唯一吗？依据真的支持吗？）：')
    for i, x in enumerate(p['questions']):
        out.append(f"  {i + 1}. [{TYPE.get(x.get('type'), '—')}] {x['prompt']}　答案：{x['options'][x['answer']]}　依据：“{x['evidence']}”")
    out.append('- **录音**：在「听」这一步放 30 秒，听听停顿和对话里的人声。')
    out.append('- 发现的问题：')
    return '\n'.join(out)


def main(argv):
    base, seed, args = 'https://flow.jasa.hk', datetime.date.today().isoformat(), []
    it = iter(argv)
    for a in it:
        if a == '--base':
            base = next(it).rstrip('/')
        elif a == '--seed':
            seed = next(it)
        else:
            args.append(a)
    if len(args) < 2:
        sys.exit(__doc__)
    out, picks = Path(args[0]), args[1:]
    allp = materials()
    ids = []
    for a in picks:
        if a.endswith('.json'):
            ids += [p['id'] for p in json.loads(Path(a).read_text(encoding='utf-8'))]
        elif a in allp:
            ids.append(a)
        else:
            sys.exit('unknown material ' + a)
    rnd = random.Random(seed)
    chosen = []
    for lv in LEVELS:
        pool = sorted(i for i in dict.fromkeys(ids) if allp[i]['cefr'] == lv)
        chosen += rnd.sample(pool, min(PER_LEVEL, len(pool)))
    head = [f'# 新精选抽查清单 · {seed}', '',
            f'这批新精选一共 {len(set(ids))} 篇，每个级别随机抽 {PER_LEVEL} 篇，共 {len(chosen)} 篇，约 {len(chosen) * 4} 分钟。',
            '链接打开的是内测版。每篇按下面列的几项看；有问题就写在那一篇的「发现的问题」后面，或者直接告诉语流 14。',
            '同一类问题出现两次以上，语流 14 会改写作提示词和自动检查，下一批起整批避免，不只改这一篇。', '']
    out.write_text('\n'.join(head) + '\n' + '\n\n'.join(section(allp[i], base) for i in chosen) + '\n', encoding='utf-8')
    print(f'{out}: {len(chosen)} materials ({", ".join(chosen)})')


if __name__ == '__main__':
    main(sys.argv[1:])
