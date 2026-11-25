"""No news, no politics (2026-11-25): what an AI-written text must not touch. Flow has no licence to provide news
(互联网新闻信息服务管理规定), so 今日一读 is an original short text on a lasting topic, and the featured corpus keeps to
common knowledge too (SPEC v5.1). hits() lists what it found; a text with any hit is not published.

It is a list, so it is blunt on purpose: it looks for words that only news and politics use (government, election,
protest, 新闻, 据报道 …), the names of news agencies, and the marks of a dated report (a year, a percentage, a sum of
money). Words with an everyday meaning ("party", "trial", "court" in a food court, "police" in a story) are left out:
the model's own check (daily_service.SELF_CHECK) and the weekly spot check are there for what a list cannot see.
"""
import re

# English: whole words or phrases, case-insensitive
EN = (
    'government', 'governments', 'president', 'presidential', 'prime minister', 'minister', 'ministers', 'ministry',
    'parliament', 'congress', 'senate', 'senator', 'election', 'elections', 'electoral', 'ballot', 'political',
    'politics', 'politician', 'politicians', 'political party', 'communist', 'democrats', 'republicans', 'protest',
    'protests', 'protesters', 'riot', 'riots', 'sanction', 'sanctions', 'diplomat', 'diplomatic', 'embassy', 'military',
    'troops', 'warfare', 'missile', 'missiles', 'terrorism', 'terrorist', 'terrorists', 'airstrike', 'invasion',
    'ceasefire', 'refugee crisis', 'breaking news', 'news agency', 'press conference', 'spokesperson', 'spokesman',
    'officials said', 'according to reports', 'it was reported', 'reported on',
    'xinhua', 'reuters', 'associated press', 'bbc news', 'cnn', 'new york times', 'global times', 'people\'s daily',
)
# Chinese: substrings (summaries, titles, explanations)
ZH = (
    '新闻', '据报道', '报道称', '记者', '发言人', '官方', '政府', '总统', '主席', '总理', '部长', '议会', '国会', '选举', '投票',
    '政治', '政党', '党派', '抗议', '示威', '游行', '制裁', '外交', '大使馆', '军队', '军事', '导弹', '战争', '恐怖', '袭击',
    '台湾', '香港', '澳门', '西藏', '新疆', '时政', '突发事件', '热搜',
)
DATED = (
    (re.compile(r'(?<!\d)(1[6-9]\d\d|20\d\d)(?!\d)'), '写了具体年份'),
    (re.compile(r'\d+(?:\.\d+)?\s?(?:%|per ?cent\b)', re.I), '写了百分比'),
    (re.compile(r'[$€£¥]\s?\d|\d\s?(?:dollars|euros|pounds|yuan|元)\b', re.I), '写了具体金额'),
)
_EN = re.compile(r'(?<![A-Za-z])(' + '|'.join(re.escape(w) for w in sorted(EN, key=len, reverse=True)) + r')(?![A-Za-z])', re.I)


def text_of(p):
    """Everything a learner reads in a material: title, summary, body, questions, words and their examples."""
    parts = [p.get('title', ''), p.get('title_en', ''), p.get('summary_zh', ''), p.get('body', '')]
    for q in p.get('questions') or []:
        if isinstance(q, dict):
            parts += [q.get('prompt', '')] + [str(o) for o in q.get('options') or []]
    for v in p.get('vocabulary') or []:
        if isinstance(v, dict):
            parts += [v.get('term', ''), v.get('example', '')]
    for x in p.get('expressions') or []:
        if isinstance(x, dict):
            parts += [x.get('text', ''), x.get('note', '')]
    return '\n'.join(str(s) for s in parts if s)


def hits(p, dated=True):
    """What in this material reads like news or politics: a list of short Chinese notes, empty when there is none.
    dated: also the marks of a dated report (a year, a percentage, a sum of money)."""
    text = text_of(p)
    out = [f'碰到新闻或时政的词：{m.group(1)}' for m in _EN.finditer(text)]
    out += [f'碰到新闻或时政的词：{w}' for w in ZH if w in text]
    if dated:
        out += [f'{why}：{m.group(0)}' for rx, why in DATED for m in rx.finditer(p.get('body', ''))]
    return list(dict.fromkeys(out))
