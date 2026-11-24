#!/usr/bin/env python3
"""Build Flow's 专四 / 专八 word books (英语专业) into flow/corpus_data/wordbooks.json.

    python3 tools/build_wordbooks.py            # rebuild, print sizes and overlaps
    python3 tools/build_wordbooks.py --check    # exit 1 if wordbooks.json differs from a fresh build

There is no openly licensed TEM-4/TEM-8 word list, and ECDICT has no TEM tag, so Flow compiles both lists itself from
data already in the repository, sized to the vocabulary the syllabus asks for (sources and method: flow/WORDBOOKS.md).
《高等学校英语专业英语教学大纲》(2000), which both exams test against: 四级 认知词汇 5,500–6,500, 八级 10,000–12,000.

  tem4  reference-list frequency ranks CORE_SKIP+1 .. TEM4_FREQ, every CET-4 word, CET-6 words up to rank TEM4_CET6
        and the Oxford 3000 core words;
  tem8  everything else up to rank TEM8_FREQ, every CET-6 and 考研 word, and IELTS / TOEFL / GRE words up to rank
        TEM8_EXAM; nothing that is already in tem4.

Both are in study order (most frequent first) and leave out what nobody studies from a card: the CORE_SKIP most common
words, proper nouns (months, weekdays, place names), abbreviations, interjections, slang-only words, profanity, words
whose only senses are technical glosses, two-letter words no exam list has, inflected forms of a word the dictionary
already has (closest, increased), compounds of known words that no exam list has (long-term, twenty-five), the less
frequent spelling of a pair (colour / color) and words without frequency data. Stdlib only; same inputs, same output.
From the dictionary only its word list, letter case, ranks and tags are used (and that a word has a meaning), so
revised meanings (meaning-fixes.json) never move a word in or out.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / 'flow'
DATA = FLOW / 'corpus_data'
OUT = DATA / 'wordbooks.json'
sys.path.insert(0, str(FLOW))
import next_service as nx  # noqa: E402  the dictionary the app looks words up in
from vocab_service import CORE_SKIP  # noqa: E402  "the", "be", "of"…: the core book skips them too

TEM4_FREQ = 5000    # tem4: reference-list ranks 151–5000, the high-frequency words
TEM4_CET6 = 8000    # tem4: CET-6 words up to this rank (every CET-4 word is in)
TEM8_FREQ = 10000   # tem8: reference-list ranks up to here
TEM8_EXAM = 16000   # tem8: IELTS / TOEFL / GRE words up to this rank (every CET-6 and 考研 word is in)
NO_FREQ = 30000     # ECDICT words without frequency data get this rank; they are left out
EXAMS = ('cet4', 'cet6', 'ky', 'ielts', 'toefl', 'gre')
BOUNDS = {'tem4': (5500, 6500), 'total': (10000, 12000)}  # 大纲 四级 / 八级 认知词汇; the tests hold the build to them

PROPER = {'christ', 'atlantic', 'pacific', 'fahrenheit', 'celsius'}  # proper nouns the general checks miss
# ECDICT keeps no letter case, so a name (london, france) is recognised by having no Collins stars, no Oxford mark, no
# COCA rank and only noun senses; these common nouns look the same and are kept
COMMON = {'bacterium', 'healthcare', 'quart', 'congratulation', 'kilowatt', 'ohm', 'decibel', 'postcode', 'testator',
          'inroad', 'facelift'}
CALENDAR = {'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october',
            'november', 'december', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'}
# months and weekdays are proper nouns written with a capital; "march", "may" and "august" are also ordinary words
CALENDAR_WORDS = {'march', 'may', 'august'}
PROFANITY = {'fuck', 'fucking', 'fucked', 'fucker', 'shit', 'shitty', 'bullshit', 'asshole', 'bitch', 'dammit',
             'goddamn', 'goddamned', 'crap', 'crappy', 'piss', 'pissed', 'slut', 'cunt'}

INFLECTION = re.compile(r'([a-z][a-z-]*)\s*的\s*(过去式|过去分词|现在分词|ing形式|名词复数|复数|第三人称单数|比较级|最高级)')
POS = re.compile(r'^\(?([a-z]{1,6})\s*\.\s*')
SLANG = re.compile(r'^\[(?:俚|美俚|英俚|口|方|谑|贬)\]')
VERB_POS = {'v', 'vt', 'vi'}
# spelling pairs: (pattern, replacement) turning one spelling into the other; a pair counts only if the glosses agree.
# SAME_WORD: other pairs, the first one is left out
VARIANTS = ((r'our', 'or'), (r'(?<=[bcdfghklmnpstvz])re$', 'er'), (r'(?<=[bcdfghklmnpstvz])res$', 'ers'),
            (r'is(e|ed|es|ing|ation|ations|er|ers)$', r'iz\1'), (r'ys(e|ed|es|ing)$', r'yz\1'), (r'ence$', 'ense'),
            (r'll(ed|ing|er|ers|or|ors)$', r'l\1'), (r'ogue$', 'og'), (r'mme$', 'm'), (r'(?<=g)ement$', 'ment'),
            (r'wards$', 'ward'), (r'^en(?=qui)', 'in'), (r'ey$', 'ay'), (r'ium$', 'um'))
SAME_WORD = {'practise': 'practice', 'amongst': 'among', 'whilst': 'while', 'jewellery': 'jewelry', 'plough': 'plow',
             'mum': 'mom', 'kerb': 'curb', 'pyjamas': 'pajamas', 'moustache': 'mustache', 'sceptic': 'skeptic',
             'sceptical': 'skeptical', 'scepticism': 'skepticism', 'mould': 'mold', 'smoulder': 'smolder',
             'manoeuvre': 'maneuver', 'aeroplane': 'airplane', 'cosy': 'cozy', 'ageing': 'aging', 'axe': 'ax',
             'doughnut': 'donut', 'tyre': 'tire', 'grey': 'gray', 'catalogue': 'catalog', 'storey': 'story'}


def load():
    d = nx.dictionary()
    ec = json.loads((DATA / 'ecdict-flow.json').read_text(encoding='utf-8'))['words']
    ref = json.loads((DATA / 'yl-reference.json').read_text(encoding='utf-8'))['terms']
    yl = {t['norm']: t['variants'][0].get('meaning', '') for t in ref}
    return d, ec, yl


def senses(k, ec, yl):
    """The word's own sense lines from the sources (ECDICT, else the reference list), domain glosses ([计]…) dropped.

    Read from the sources rather than the dictionary so that hand-reviewed meanings (meaning-fixes.json) never move a
    word in or out of a book."""
    raw = ec[k][1] if k in ec else []
    lines = [ln.strip() for ln in raw if ln.strip() and not ln.strip().startswith('[')]
    if not lines:
        lines = [ln.strip() for ln in re.split(r'[；\n]', yl.get(k, '')) if ln.strip()]
    return [ln for ln in lines if POS.sub('', ln)]


def pos_of(line):
    m = POS.match(line)
    return m.group(1) if m else ''


def glosses(lines):
    out = set()
    for ln in lines:
        for g in re.split(r'[,，;；、]', POS.sub('', INFLECTION.sub('', ln))):
            g = re.sub(r'[（(][^）)]*[）)]', '', g).strip(' .…')
            if g:
                out.add(g)
    return out


def why_left_out(k, e, lines, d, ec):
    """A short reason when a dictionary word does not belong on a study card, else ''."""
    if not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', k) or len(k) < 2 or not e['meaning'] or e['word'][:1].isupper():
        return 'not a plain lower-case word with a meaning'  # the rule vocab_service.book_words() applies
    if e['rank'] <= CORE_SKIP:
        return 'among the most common words'
    if e['rank'] >= NO_FREQ:
        return 'no frequency data'
    if k in PROFANITY:
        return 'profanity'
    if k in PROPER or (k in CALENDAR and k not in CALENDAR_WORDS):
        return 'proper noun'
    if not lines:
        return 'technical glosses only'
    tagged = bool(set(e['tags']) & set(EXAMS))
    if len(k) < 3 and not tagged:
        return 'two letters'
    if all(SLANG.match(POS.sub('', ln)) for ln in lines):
        return 'slang'
    if (not e['ref'] and k in ec and ec[k][3] == 0 and ec[k][4] == 0 and ec[k][6] == 0 and k not in COMMON
            and {pos_of(ln) for ln in lines} == {'n'}):
        return 'proper noun'
    kinds = {pos_of(ln) for ln in lines}
    if kinds <= {'abbr'}:
        return 'abbreviation'
    if kinds <= {'int', 'interj'}:
        return 'interjection'
    refs = [(b, kind) for ln in lines for b, kind in INFLECTION.findall(ln) if b != k and b in d]
    if refs:
        own = [ln for ln in lines if not INFLECTION.search(ln)]
        if not own and (not tagged or {pos_of(ln) for ln in lines} <= VERB_POS):
            return f'inflection of {refs[0][0]}'
        if not tagged and refs[0][1] in ('比较级', '最高级', '复数', '名词复数', '第三人称单数'):
            return f'inflection of {refs[0][0]}'
    if not tagged and re.search(r'(ed|ing)$', k) and kinds <= VERB_POS and any(b in d for b in nx.lemma_candidates(k)[1:]):
        return 'verb form'
    if '-' in k and not tagged and all(p in d for p in k.split('-')):
        return 'compound of known words'
    return ''


def variant_drops(pool, d):
    """One spelling of word pairs with the same senses (colour/color, centre/center, towards/toward) is dropped: the
    more frequent one in the reference list stays (its rank is comparable with the rest of the book); for SAME_WORD
    pairs the first word is dropped. The spelling kept takes over the other's exam tags and Oxford 3000 mark."""
    drop = {}
    for a in sorted(pool):
        if SAME_WORD.get(a) in pool:
            drop.setdefault(a, SAME_WORD[a])
        for b in {re.sub(pat, rep, a, count=1) for pat, rep in VARIANTS}:
            if b == a or b not in pool or not (pool[a]['gloss'] & pool[b]['gloss']) or {a, b} & set(SAME_WORD):
                continue
            keep, other = sorted((a, b), key=lambda w: (not d[w]['ref'], d[w]['rank'], w))
            drop.setdefault(other, keep)
    return drop


def build():
    d, ec, yl = load()
    pool, left = {}, {}
    for k in sorted(d):
        e = d[k]
        lines = senses(k, ec, yl)
        why = why_left_out(k, e, lines, d, ec)
        if why:
            left[k] = why
        else:
            pool[k] = {'gloss': glosses(lines), 'oxford': bool(k in ec and ec[k][4]), 'tags': set(e['tags']) & set(EXAMS)}
    for k, keep in variant_drops(pool, d).items():
        pool[keep]['tags'] |= pool[k]['tags']
        pool[keep]['oxford'] |= pool[k]['oxford']
        left[k] = f'spelling variant of {keep}'
    for k in left:
        pool.pop(k, None)

    def tags(k):
        return pool[k]['tags']

    rank = lambda k: d[k]['rank']
    tem4 = {k for k in pool if (d[k]['ref'] and rank(k) <= TEM4_FREQ) or pool[k]['oxford'] or 'cet4' in tags(k)
            or ('cet6' in tags(k) and rank(k) <= TEM4_CET6)}
    tem8 = {k for k in pool if k not in tem4 and ((d[k]['ref'] and rank(k) <= TEM8_FREQ) or tags(k) & {'cet6', 'ky'}
                                                  or (tags(k) & {'ielts', 'toefl', 'gre'} and rank(k) <= TEM8_EXAM))}
    order = lambda s: sorted(s, key=lambda k: (rank(k), k))
    return {'tem4': order(tem4), 'tem8': order(tem8)}, left, d


NOTICE = ('Built by tools/build_wordbooks.py from flow/corpus_data/yl-reference.json (frequency ranks) and '
          'ecdict-flow.json (ECDICT, MIT License, Copyright (c) 2025 Linwei; exam tags, Oxford 3000 flag, senses). '
          'Selection by Flow, sized to the vocabulary of 《高等学校英语专业英语教学大纲》 (2000); '
          'not an official TEM-4/TEM-8 word list. Method: flow/WORDBOOKS.md. Do not edit.')


def meta(books):
    n4, n8 = (round(len(books[b]), -2) for b in ('tem4', 'tem8'))
    return {
        'tem4': {'title': '专四词汇', 'group': '英语专业', 'blurb': f'英语专业四级：约 {n4} 词，覆盖四级词汇，常用词在前',
                 'basis': '按《高等学校英语专业英语教学大纲》四级认知词汇 5500–6500 的要求，由 Flow 从词频前 5000 的常用词、'
                          '四级词、较常用的六级词和牛津 3000 核心词中自编，去掉最常见的 150 个词、专有名词、缩写和词形变化。'
                          '按考纲词汇量要求自编，不是官方词表。'},
        'tem8': {'title': '专八词汇', 'group': '英语专业', 'blurb': f'英语专业八级：专四之外再加约 {n8} 词，覆盖六级、考研词汇',
                 'basis': '按大纲八级认知词汇 10000–12000 的要求，在专四之外收入较低频的常用词、其余的六级和考研词，'
                          f'以及较常用的雅思、托福、GRE 词，与专四合计约 {round(n4 + n8, -3)} 词。按考纲词汇量要求自编，不是官方词表。'},
    }


def document(books):
    m = meta(books)
    return {'notice': NOTICE, 'books': {b: {**m[b], 'words': books[b]} for b in ('tem4', 'tem8')}}


def text(doc):
    return json.dumps(doc, ensure_ascii=False, indent=1) + '\n'


def report(books, left, d):
    from collections import Counter
    t4, t8 = set(books['tem4']), set(books['tem8'])
    print(f"tem4 {len(t4)}  tem8 {len(t8)}  together {len(t4 | t8)}  (bounds: tem4 {BOUNDS['tem4']}, together {BOUNDS['total']})")
    for t in EXAMS:
        s = {k for k, e in d.items() if t in e['tags']}
        print(f'  {t:6} {len(s):5}: in tem4 {len(s & t4):5}  in tem8 {len(s & t8):5}  in neither {len(s - t4 - t8):5}')
    print('  left out:', ', '.join(f'{n} {c}' for c, n in Counter(re.sub(r' of .*', '', w) for w in left.values()).most_common()))


if __name__ == '__main__':
    books, left, d = build()
    out = text(document(books))
    if '--check' in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding='utf-8') != out:
            sys.exit('wordbooks.json is out of date with its sources: run python3 tools/build_wordbooks.py')
        print('wordbooks.json is up to date')
    else:
        OUT.write_text(out, encoding='utf-8')
        report(books, left, d)
        print(f'-> {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)')
