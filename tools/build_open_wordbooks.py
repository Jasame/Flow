#!/usr/bin/env python3
"""Build flow/corpus_data/wordbooks-open.json: four word books made from openly licensed lists.

    python3 -I tools/build_open_wordbooks.py <ecdict.csv> <NAWL_1.2_alphabetized_description.txt> <BSL_1.20_stats.csv>

  zk   中考词汇  ECDICT words tagged zk (MIT)                         by frequency, most common first
  gk   高考词汇  ECDICT words tagged gk, plus the zk ones (MIT)       by frequency
  nawl 学术英语  New Academic Word List 1.2 (CC BY-SA 4.0)           by frequency (the NAWL files are alphabetical)
  bsl  商务英语  Business Service List 1.2 (CC BY-SA 4.0)            in the list's own rank order (BSL Rank)

A word is kept only when Flow's dictionary (next_service.dictionary()) has it the way vocab_service.book_words()
wants it: a plain lower-case word of two or more letters, a lower-case headword and a Chinese meaning. A few list
forms are first mapped to the dictionary's entry for them (ALIASES); bound prefixes the lists carry (anti-, non-…)
are left out. Frequency is the dictionary's rank, the one the exam books sort by. Dropped words are printed.

Rebuild ecdict-flow.json and dictionary-flow.json first (flow/WORDBOOKS-OPEN.md has the commands), so the dictionary
already holds the zk/gk and NAWL/BSL words. Standard library only; the same inputs give the same bytes.
"""
import csv, json, re, sys
from pathlib import Path

FLOW = Path(__file__).resolve().parents[1] / 'flow'
sys.path.insert(0, str(FLOW))
import next_service as nx  # noqa: E402

OUT = FLOW / 'corpus_data' / 'wordbooks-open.json'
PLAIN = re.compile(r'[a-z]+(?:-[a-z]+)*')  # vocab_service.book_words()
CJK = re.compile(r'[\u4e00-\u9fff]')

# List forms whose own spelling has no entry of its own in Flow's dictionary (it folds plurals and -ed/-ing/-er forms
# into the base word), mapped by hand to the entry that carries the listed sense. Each target was checked against its
# dictionary meaning; forms whose base word means something else (goods -> good, means -> mean, latest -> late,
# chips -> chip, shaver -> shave) are dropped instead.
ALIASES = {
    'addicted': 'addict', 'beddings': 'bedding', 'customs': 'custom', 'drier': 'dryer', 'eastwards': 'eastward',
    'founds': 'found', 'grandparents': 'grandparent', 'headquarter': 'headquarters', 'labourer': 'laborer',
    'northwards': 'northward', 'onwards': 'onward', 'organiser': 'organizer', 'refreshments': 'refreshment',
    'regards': 'regard', 'repairs': 'repair', 'scores': 'score', 'skipping': 'skip', 'sneaker': 'sneakers',
    'socks': 'sock', 'souvenirs': 'souvenir', 'unauthorize': 'unauthorized', 'westerner': 'western',
    'westwards': 'westward',
}
# The prefixes NAWL defines as "a prefix meaning ..." (BSL lists some of them too): word parts, not words.
PREFIXES = frozenset(('anti', 'ex', 'micro', 'multi', 'neo', 'non', 'pre', 'semi', 'sub', 'trans'))

CC = 'https://creativecommons.org/licenses/by-sa/4.0/'
NOTICE = ('中考词汇 and 高考词汇: words tagged zk/gk in ECDICT (https://github.com/skywind3000/ECDICT, commit 39cfb96), '
          'MIT License, Copyright (c) 2025 Linwei (corpus_data/ECDICT-LICENSE.txt). '
          '学术英语: adapted from "New Academic Word List" 1.2 by Browne, C., Culligan, B., and Phillips, J. '
          '(https://www.newgeneralservicelist.com/new-academic-word-list). '
          '商务英语: adapted from "Business Service List" 1.2 by Browne, C. and Culligan, B. '
          '(https://www.newgeneralservicelist.com/business-service-list). '
          f'Both are licensed under CC BY-SA 4.0 ({CC}). Adapted by Flow: lower-cased, matched to Flow\'s dictionary '
          '(a few forms mapped to their dictionary entry), prefixes and words without a Chinese meaning removed, NAWL '
          'ordered by word frequency. The adapted 学术英语 and 商务英语 lists are licensed under CC BY-SA 4.0 too '
          '(corpus_data/NGSL-LICENSE.txt). Chinese meanings come from ECDICT. Built by tools/build_open_wordbooks.py.')

BOOKS = {
    'zk': {'title': '中考词汇', 'group': '中学英语', 'blurb': '中考英语词汇，常用词在前',
           'basis': '词表取自开源英汉词典 ECDICT（MIT 许可）中标为“中考”的词，按词频排序；语流词典里没有合适词条的少数词未收录。'},
    'gk': {'title': '高考词汇', 'group': '中学英语', 'blurb': '高考英语词汇（含中考词），常用词在前',
           'basis': '词表取自开源英汉词典 ECDICT（MIT 许可）中标为“高考”或“中考”的词，按词频排序；语流词典里没有合适词条的少数词未收录。'},
    'nawl': {'title': '学术英语', 'group': '学术与职场', 'blurb': '大学课程和学术论文里最常用的学术词，适合掌握常用词以后学',
             'basis': '词表改编自 Browne、Culligan、Phillips 的 New Academic Word List 1.2（CC BY-SA 4.0 许可），按词频排序，去掉了前缀和查不到释义的词；改编后的词表同样以 CC BY-SA 4.0 许可发布。'},
    'bsl': {'title': '商务英语', 'group': '学术与职场', 'blurb': '商务文件、财经新闻和职场里最常用的词，适合掌握常用词以后学',
            'basis': '词表改编自 Browne、Culligan 的 Business Service List 1.2（CC BY-SA 4.0 许可），按原表的频率排名排序，去掉了前缀和查不到释义的词；改编后的词表同样以 CC BY-SA 4.0 许可发布。'},
}


def ecdict_tagged(path, tags):
    """ECDICT headwords that carry any of these tags, in file order: {lower-case word: headword as written}."""
    csv.field_size_limit(10 ** 7)
    out = {}
    with path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            w = (row.get('word') or '').strip()
            if w and set((row.get('tag') or '').split()) & set(tags):
                k = w.lower()
                if k not in out or w == k:  # "china" the dishes over "China"
                    out[k] = w
    return out


def nawl_words(path):
    """NAWL 1.2 alphabetized: a description, its references, then one headword per line (957)."""
    lines = [ln.strip() for ln in path.read_text(encoding='latin-1').splitlines()]
    start = max(i for i, ln in enumerate(lines) if 'Retrieved from' in ln) + 1
    words = [ln for ln in lines[start:] if ln]
    bad = [w for w in words if not re.fullmatch(r"[A-Za-z][A-Za-z'-]*", w)]
    if bad or not 900 <= len(words) <= 1000:
        sys.exit(f'{path.name}: unexpected format ({len(words)} headwords, odd lines {bad[:5]})')
    return words


def bsl_words(path):
    """BSL 1.20 with statistics: Word, BSL Rank, ... -> headwords in rank order (1744)."""
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    if rows[0][:2] != ['Word', 'BSL Rank']:
        sys.exit(f'{path.name}: expected the columns Word, BSL Rank; found {rows[0][:2]}')
    ranked = sorted((int(r[1]), r[0].strip()) for r in rows[1:] if r and r[0].strip())
    if not 1600 <= len(ranked) <= 1800:
        sys.exit(f'{path.name}: unexpected size {len(ranked)}')
    return [w for _, w in ranked]


def usable(d, norm):
    e = d.get(norm)
    return bool(e and PLAIN.fullmatch(norm) and len(norm) >= 2 and e['meaning'] and not e['word'][:1].isupper()
                and CJK.search(e['meaning']))


def why_not(d, written, norm):
    if norm in PREFIXES:
        return 'prefix'
    if not PLAIN.fullmatch(norm) or len(norm) < 2:
        return 'not a single word'
    if written != written.lower() or (norm in d and d[norm]['word'][:1].isupper()):
        return 'name or abbreviation'
    if norm in d:
        return 'no Chinese meaning'
    return 'no own dictionary entry'


def collect(d, written_words, ordered):
    """-> (norms, dropped {reason: [word]}, aliased [(from, to)]); ordered=False sorts by the dictionary's rank."""
    norms, seen, dropped, aliased = [], set(), {}, []
    for written in written_words:
        low = written.lower()
        norm = ALIASES.get(low, low)
        if norm in PREFIXES or not usable(d, norm):
            dropped.setdefault(why_not(d, written, norm), []).append(written)
            continue
        if norm != low:
            aliased.append((low, norm))
        if norm not in seen:
            seen.add(norm)
            norms.append(norm)
    if not ordered:
        norms.sort(key=lambda w: (d[w]['rank'], w))
    return norms, dropped, aliased


def main(argv):
    if len(argv) != 4:
        sys.exit(__doc__)
    ecdict, nawl, bsl = map(Path, argv[1:])
    d = nx.dictionary()
    zk = ecdict_tagged(ecdict, ('zk',))
    gk = ecdict_tagged(ecdict, ('gk', 'zk'))
    sources = {'zk': (list(zk.values()), False), 'gk': (list(gk.values()), False),
               'nawl': (nawl_words(nawl), False), 'bsl': (bsl_words(bsl), True)}
    books = {}
    for key, (written, ordered) in sources.items():
        words, dropped, aliased = collect(d, written, ordered)
        books[key] = {**BOOKS[key], 'words': words}
        print(f'{key} {BOOKS[key]["title"]}: {len(written)} listed -> {len(words)} words; '
              f'{sum(map(len, dropped.values()))} dropped, {len(aliased)} mapped to their entry')
        for reason, ws in sorted(dropped.items()):
            print(f'  {reason} ({len(ws)}): {", ".join(ws)}')
        if aliased:
            print('  mapped: ' + ', '.join(f'{a} -> {b}' for a, b in aliased))
    doc = json.dumps({'notice': NOTICE, 'books': books}, ensure_ascii=False, indent=1) + '\n'
    OUT.write_text(doc, encoding='utf-8')
    print(f'{OUT} ({OUT.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main(sys.argv)
