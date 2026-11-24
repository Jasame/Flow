#!/usr/bin/env python3
"""Flag word-card meanings that are likely to mislead a learner (stdlib only).

    python3 tools/audit_meanings.py                    # counts per problem and per book
    python3 tools/audit_meanings.py --list noun-first  # the flagged words, most frequent first
    python3 tools/audit_meanings.py --list all --book core --top 50
    python3 tools/audit_meanings.py --without-fixes    # as if meaning-fixes.json were empty (the "before")
    python3 tools/audit_meanings.py --json --unreviewed > flagged.json   # flagged words not in meaning-fixes.json yet

Audits the meaning a word card shows (next_service.dictionary(), meaning-fixes.json applied) for every word book a
learner can choose (vocab_service.registry(): the frequency and exam books and the data books 专四、专八、中考、学术…;
until 2026-11-24 only core, mid, high, cet4, cet6 and ky). The checks are heuristics: they find
candidates for review by hand, and a flagged meaning is not always wrong. Fixes go in
flow/corpus_data/meaning-fixes.json (then run tools/build_dictionary.py); see meaning-fixes-notes.md.
"""
import argparse, json, re, sys
from pathlib import Path

FLOW = Path(__file__).resolve().parents[1] / 'flow'
sys.path.insert(0, str(FLOW))
import next_service as nx  # noqa: E402
import vocab_service as vs  # noqa: E402

BOOKS = tuple(b['id'] for b in vs.registry())
POS = re.compile(r'^([a-z]+)\. ')
NOTE = re.compile(r'^（[^）]*）')  # a line that is only a note, e.g. "（find 的过去式和过去分词）"
NORM_POS = {'vt': 'v', 'vi': 'v', 'a': 'adj', 'int': 'interj'}
# computing jargon that ECDICT mixes into everyday words, often as a line of its own ("handle: n. 句柄");
# its lines tagged [计] are already dropped by next_service._ec_meaning
TECH = ('寄存器', '累加器', '长整型', '整型', '寻址', '汇编', '宏指令', '子程序', '句柄', '分隔符', '文件分配表',
        '偏移量', '批处理文件', '命令处理器', '标准输出', '计算机辅助', '应用接口', '存储器', '模拟运算表', '前导字符')
RARE = re.compile(r'[（(\[<](?:古|废|方|俚|诗|罕|旧)[^）)\]>]{0,3}[）)\]>]')  # explicit markers: (古) [俚] <方>
LETTER = re.compile(r'第.{1,3}个字母|^字母 ?[A-Za-z]|的缩写')  # ECDICT: "a: 第一个字母 A"
CHECKS = {
    'artefact': 'stray characters: \\r, backslashes, brackets, empty or doubled separators, malformed part of speech',
    'domain-tag': 'a domain tag such as [计] [医] still in the text',
    'letter-abbr': 'a letter, abbreviation, prefix or suffix sense comes first',
    'tech-sense': 'computing jargon mixed into an everyday word',
    'no-pos': 'a line without a part of speech (the card shows every 「；」 part on its own line)',
    'noun-first': 'the noun comes first though the reference list gives the word another main part of speech '
                  '(not counted for words reviewed in meaning-fixes.json, where the order is a decision)',
    'rare-first': 'the first sense is marked archaic, dialect, slang or rare',
    'long': 'over 90 characters, or more than 8 senses in one part of speech',
    'duplicate': 'the same sense twice in a line, or the same part of speech twice (unless one is marked 「读」)',
    'no-phonetic': 'no phonetic transcription',
}


def lines_of(meaning):
    return re.split(r'[；;]', meaning)  # the card breaks the line at both


def pos_of(line):
    m = POS.match(line)
    return NORM_POS.get(m.group(1), m.group(1)) if m else None


def glosses(line):
    body = POS.sub('', line, count=1)
    return [g.strip() for g in re.split(r'[,，、]', body)]


def problems(meaning, phonetic, ref_meaning, reviewed=False):
    """The codes in CHECKS that apply to one shown meaning (reviewed: the word is in meaning-fixes.json)."""
    out = set()
    ls = lines_of(meaning)
    if (re.search(r'[\r\n\t\\]|\\r|[\[\]【】]', meaning) or re.search(r'(^|[；;])\s*($|[；;])', meaning)
            or re.search(r', *,|，，|^[ ,，；]|[ ,，；]$', meaning) or re.search(r'\b(?:vt|vi|n|adj|adv|v)\.(?:vt|vi|\S)', meaning)):
        out.add('artefact')
    if re.search(r'\[[^\]]{1,6}\]', meaning):
        out.add('domain-tag')
    first = next((ln for ln in ls if not NOTE.match(ln)), '')
    if re.match(r'^(abbr|pref|suf|symb)\. ', first) or LETTER.search((glosses(first) or [''])[0]):
        out.add('letter-abbr')
    if any(t in meaning for t in TECH):
        out.add('tech-sense')
    if any(ln.strip() and not POS.match(ln) and not NOTE.match(ln) for ln in ls):
        out.add('no-pos')
    ref_pos = pos_of(ref_meaning or '')
    shown = [pos_of(ln) for ln in ls]
    if not reviewed and shown and shown[0] == 'n' and ref_pos and ref_pos != 'n' and ref_pos in shown:
        out.add('noun-first')
    g0 = glosses(first)[:1]
    if g0 and RARE.search(g0[0]):
        out.add('rare-first')
    if len(meaning) > 90 or any(len(glosses(ln)) > 8 for ln in ls):
        out.add('long')
    tags = [m.group(1) for m in (POS.match(ln) for ln in ls if '（读' not in ln) if m]
    if len(tags) != len(set(tags)) or any(len([g for g in glosses(ln) if g]) != len({g for g in glosses(ln) if g}) for ln in ls):
        out.add('duplicate')
    if not (phonetic or '').strip('[] '):
        out.add('no-phonetic')
    return out


def raw_meaning(norm, ec, ref_terms):
    """What the card would show without meaning-fixes.json (next_service.build_dictionary without its last step)."""
    e = ec.get(norm)
    t = ref_terms.get(norm)
    if t is not None:
        return (nx._ec_meaning(e) if e else '') or t['variants'][0].get('meaning', '')
    return nx._ec_meaning(e) if e else ''


def audit(without_fixes=False):
    """[(rank, word, meaning, phonetic, set of codes, books)] for every word in BOOKS, most frequent first."""
    base = FLOW / 'corpus_data'
    d = nx.dictionary()
    ref_terms = {t['norm']: t for t in json.loads((base / 'yl-reference.json').read_text(encoding='utf-8'))['terms']}
    fixes = json.loads((base / 'meaning-fixes.json').read_text(encoding='utf-8'))['words']
    ec = json.loads((base / 'ecdict-flow.json').read_text(encoding='utf-8'))['words'] if without_fixes else {}
    books = {}
    for b in BOOKS:
        for rank, w in vs.book_words()[b]:
            books.setdefault(w, [rank, []])[1].append(b)
    rows = []
    for w, (rank, bs) in sorted(books.items(), key=lambda x: (x[1][0], x[0])):
        e = d[w]
        meaning = raw_meaning(w, ec, ref_terms) if without_fixes and w in fixes else e['meaning']
        ref_m = ref_terms[w]['variants'][0].get('meaning', '') if w in ref_terms else ''
        reviewed = w in fixes and not without_fixes
        rows.append((rank, w, meaning, e['phonetic'], problems(meaning, e['phonetic'], ref_m, reviewed), bs))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--list', metavar='CODE', help='print the words with this problem (or "all")')
    ap.add_argument('--book', choices=BOOKS, help='only this book')
    ap.add_argument('--top', type=int, default=0, help='at most this many words in --list')
    ap.add_argument('--min-rank', type=int, default=vs.CORE_SKIP, help='skip words more frequent than this '
                    '(default: the core book starts after them, %(default)s)')
    ap.add_argument('--without-fixes', action='store_true', help='audit the meanings as if meaning-fixes.json were empty')
    ap.add_argument('--unreviewed', action='store_true', help='only words not in meaning-fixes.json yet')
    ap.add_argument('--json', action='store_true', help='print the flagged words as JSON: [{word, rank, codes, books, meaning, phonetic}]')
    a = ap.parse_args()
    fixed = set(json.loads((FLOW / 'corpus_data' / 'meaning-fixes.json').read_text(encoding='utf-8'))['words']) if a.unreviewed else set()
    rows = [r for r in audit(a.without_fixes) if r[0] > a.min_rank and (not a.book or a.book in r[5]) and r[1] not in fixed]
    if a.json:
        print(json.dumps([{'word': w, 'rank': rank, 'codes': sorted(codes), 'books': bs, 'meaning': m, 'phonetic': ph}
                          for rank, w, m, ph, codes, bs in rows if codes], ensure_ascii=False, indent=0))
        return
    if a.list:
        n = 0
        for rank, w, m, ph, codes, bs in rows:
            if codes and (a.list == 'all' or a.list in codes):
                print(f'{rank:>6} {w:<18} {",".join(sorted(codes)):<28} {m}')
                n += 1
                if a.top and n >= a.top:
                    break
        return
    flagged = sum(1 for r in rows if r[4])
    print(f'{len(rows)} words audited (rank > {a.min_rank}{", " + a.book if a.book else ""}'
          f'{", without meaning-fixes.json" if a.without_fixes else ""}); {flagged} flagged')
    width = max(len(c) for c in CHECKS)
    print(f'{"problem":<{width}}  {"all":>5}  ' + '  '.join(f'{b:>5}' for b in BOOKS))
    for code, what in CHECKS.items():
        per = {b: sum(1 for r in rows if code in r[4] and b in r[5]) for b in BOOKS}
        print(f'{code:<{width}}  {sum(1 for r in rows if code in r[4]):>5}  ' + '  '.join(f'{per[b]:>5}' for b in BOOKS))
    per = {b: sum(1 for r in rows if r[4] and b in r[5]) for b in BOOKS}
    print(f'{"any":<{width}}  {flagged:>5}  ' + '  '.join(f'{per[b]:>5}' for b in BOOKS))


if __name__ == '__main__':
    main()
