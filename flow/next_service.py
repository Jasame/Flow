"""Flow: one learning loop on top of the existing backend (see NEXT.md).

Material -> listen -> read (tap a word, save expressions) -> check -> use it (AI rewrite
comparison) -> review only what you saved. The knowledge graph (44 grammar points in 13 topics, materials,
saved expressions) drives what is recommended next, and AI feedback is mapped onto it.
Guests may read, listen and check answers; saving, AI and progress need an account.
"""
import datetime, hashlib, json, os, re, time
from pathlib import Path

TZ = datetime.timezone(datetime.timedelta(hours=8))
STEPS = ('listen', 'read', 'check', 'output')
UP_LEVEL = {'A2': 'B1', 'B1': 'B2', 'B2': 'C1'}  # where 今日 goes once a level's featured texts are all learned
LEVELS = {
    'A2': {'label': '入门', 'pack': 'A2', 'hard_rank': 2000, 'sample': 'I usually take the bus to school. It is cheap and quick.',
           'desc': '能看懂简单句子，日常交流还比较吃力'},
    'B1': {'label': '中级', 'pack': 'B1', 'hard_rank': 3000, 'sample': 'If the weather is good this weekend, we are planning to go hiking with a few friends.',
           'desc': '能应付日常交流，读工作或学习材料要查不少词'},
    'B2': {'label': '中高级', 'pack': 'B2', 'hard_rank': 6000, 'sample': 'Although the proposal seemed reasonable at first, several colleagues raised concerns about its long-term costs.',
           'desc': '能读懂大部分文章，想说得更自然、写得更地道'},
    'C1': {'label': '高级', 'pack': 'B2', 'hard_rank': 9000, 'sample': 'The findings, while hardly conclusive, cast considerable doubt on the assumptions underpinning the policy.',
           'desc': '接近流利，想打磨措辞、语气和风格'},
}
GOALS = {'daily': '日常交流', 'work': '工作沟通', 'exam': '考试', 'abroad': '留学和海外生活', 'media': '看懂影视、新闻', 'interest': '兴趣'}
THEMES = {'campus': '校园学习', 'travel': '旅行生活', 'life': '日常生活', 'work': '职场沟通', 'culture': '文化交流', 'science': '科学素养'}
MINUTES = (5, 10, 15, 20, 30, 45, 60)
# Pre-generated Kokoro narration (see tools/gen_audio.py): audio/<voice>/<material>.m4a + .json timings.
VOICES = {'us-f': '美音 · 女声', 'us-m': '美音 · 男声', 'uk-f': '英音 · 女声', 'uk-m': '英音 · 男声'}
# Which ids can have narration files: the v5 corpus and, since the r27 content line, the older materials too (简版:
# graded-*, graph-* and the first theme-level texts), so WeChat on Android, which has no browser voice, can play them.
NARRATION_ID = re.compile(r'(?:v5|graded|graph|campus|travel|life|work|culture|science)-[a-z0-9]+(?:-[a-z0-9]+)*')
AUDIO_DIR = Path(os.getenv('FLOW_AUDIO_DIR') or Path(__file__).resolve().parent / 'audio')
_AUDIO = {'mtime': None, 'index': {}}
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

# Knowledge graph: 44 grammar points in 13 topics (the first 18 from content_v05, 26 more from grammar_more).
# Which points a level should be building now.
import grammar_more as GM
import grammar_bank as GB
TOPICS = GM.TOPIC_ORDER
LEVEL_NODES = {
    'A2': ('tense-present', 'tense-past', 'tense-perfect', 'conditional-real', 'nonfinite-infinitive', 'clause-adverb', 'clause-relative') + GM.LEVEL_MORE['A2'],
    'B1': ('tense-perfect', 'clause-relative', 'clause-adverb', 'clause-noun', 'conditional-real', 'conditional-unless', 'conditional-modal',
           'nonfinite-infinitive', 'nonfinite-gerund', 'agreement-head', 'agreement-each') + GM.LEVEL_MORE['B1'],
    'B2': GM.LEVEL_BASE['B2'] + GM.LEVEL_MORE['B2'],
    'C1': GM.LEVEL_BASE['C1'] + GM.LEVEL_MORE['C1'],
}
_GRAMMAR_FOUND = {}  # pack id -> (body length, {point: [sentences]}) for the points grammar_more finds in the text
STATUS_LABEL = {'untouched': '还没接触', 'met': '读到过', 'used': '用出来过', 'watch': '需要留意', 'solid': '做题已验证'}

_DICT = None


def schema(c):
    c.executescript('''
CREATE TABLE IF NOT EXISTS next_profiles(user_id INTEGER PRIMARY KEY REFERENCES users(id), level TEXT NOT NULL,
 goal TEXT NOT NULL DEFAULT 'daily', themes TEXT NOT NULL DEFAULT '[]', minutes INTEGER NOT NULL DEFAULT 10, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS next_progress(user_id INTEGER NOT NULL REFERENCES users(id), pack TEXT NOT NULL, step TEXT NOT NULL,
 created REAL NOT NULL, PRIMARY KEY(user_id, pack, step));
CREATE INDEX IF NOT EXISTS next_progress_time ON next_progress(user_id, created);
CREATE TABLE IF NOT EXISTS next_cards(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), text TEXT NOT NULL,
 norm TEXT NOT NULL, meaning TEXT NOT NULL DEFAULT '', context TEXT NOT NULL DEFAULT '', pack TEXT, kind TEXT NOT NULL DEFAULT 'phrase',
 created REAL NOT NULL, due REAL NOT NULL, interval REAL NOT NULL DEFAULT 0, ease REAL NOT NULL DEFAULT 2.5,
 reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0, last REAL, UNIQUE(user_id, norm));
CREATE INDEX IF NOT EXISTS next_cards_due ON next_cards(user_id, due);
CREATE TABLE IF NOT EXISTS next_reviews(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, card INTEGER NOT NULL, rating TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS next_reviews_time ON next_reviews(user_id, created);
CREATE TABLE IF NOT EXISTS next_variants(pack TEXT NOT NULL, level TEXT NOT NULL, body TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '[]',
 created REAL NOT NULL, PRIMARY KEY(pack, level));
CREATE TABLE IF NOT EXISTS next_node_notes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, node TEXT NOT NULL, pack TEXT NOT NULL,
 kind TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS next_node_notes_user ON next_node_notes(user_id, node);
CREATE TABLE IF NOT EXISTS next_explains(pack TEXT NOT NULL, sentence TEXT NOT NULL, level TEXT NOT NULL, result TEXT NOT NULL,
 created REAL NOT NULL, PRIMARY KEY(pack, sentence, level));''')
    if 'voice' not in {r[1] for r in c.execute('PRAGMA table_info(next_profiles)')}:
        c.execute("ALTER TABLE next_profiles ADD COLUMN voice TEXT NOT NULL DEFAULT 'us-f'")
    if 'weekly_goal' not in {r[1] for r in c.execute('PRAGMA table_info(next_profiles)')}:
        c.execute('ALTER TABLE next_profiles ADD COLUMN weekly_goal INTEGER NOT NULL DEFAULT 4')  # 每周目标: days a week
    if 'exam' not in {r[1] for r in c.execute('PRAGMA table_info(next_profiles)')}:  # 考试冲刺: the exam (exam_service.EXAMS) and its date
        c.execute('ALTER TABLE next_profiles ADD COLUMN exam TEXT')
        c.execute('ALTER TABLE next_profiles ADD COLUMN exam_date TEXT')
    if 'target' not in {r[1] for r in c.execute('PRAGMA table_info(next_profiles)')}:
        # 选方向和目标 (r27): the level the learner wants to reach, and where the current level came from:
        # 'guess' (one band below the target, until a test says more), 'placed' (语法起点小测), 'self' (chosen; older rows: NULL)
        c.execute('ALTER TABLE next_profiles ADD COLUMN target TEXT')
        c.execute('ALTER TABLE next_profiles ADD COLUMN level_source TEXT')
    import vocab_service  # word books, daily plan and FSRS state live on top of next_cards
    vocab_service.schema(c)
    __import__('skills_service').schema(c)  # ability profile, mistake book, weekly report
    __import__('output_service').schema(c)  # translation sources
    GM.install(c)  # the 26 further grammar points: topics, subskills, verification questions, graph nodes (once)
    GB.install(c)  # ten questions on every point (once)
    GB.schema(c)  # spaced re-checks of grammar points
    __import__('graph_links').install(c)  # prerequisite fixes and confusable edges (once)
    __import__('easy_reading').schema(c)  # easy reading: words read, speed, how hard it felt
    __import__('word_links').schema(c)  # practice on words Chinese speakers mix up
    __import__('ability_radar').schema(c)  # goals, assessments and radar snapshots
    __import__('exam_service').schema(c)  # exam practice papers and results
    __import__('exam_sprint').schema(c)  # question-type practice results
    __import__('progress_service').schema(c)  # 这周进步: weekly goals by week, the Sunday mail's switch and link
    __import__('content_v50').sync(c)  # additive edits of published materials (more questions, tags) reach the database


# ---------- helpers ----------

def _day(ts=None):
    return datetime.datetime.fromtimestamp(ts or time.time(), TZ).date().isoformat()


def _text(value, maximum, minimum=0):
    if not isinstance(value, str):
        raise ValueError('内容格式不正确')
    value = ' '.join(value.split()) if '\n' not in value else value.strip()
    if not minimum <= len(value) <= maximum:
        raise ValueError(f'内容长度应在 {minimum}–{maximum} 字之间')
    return value


def _ec_meaning(e):
    """ECDICT translation lines -> one line per part of speech, joined with 「；」 (the UI shows each on its own line)."""
    lines = []
    for ln in e[1]:
        if ln.startswith('['):  # domain glosses such as [计] or [医]
            continue
        ln = re.sub(r'^a\. ', 'adj. ', ln).replace('；', ', ').replace(';', ', ')
        lines.append(ln)
    return '；'.join(lines)


def ipa(p):
    """One phonetic style everywhere: ECDICT and older lists write ' , : for ˈ ˌ ː."""
    p = (p or '').replace('ә', 'ə').replace('є', 'ɛ').strip()
    return re.sub(r",(?=\S)", 'ˌ', p.replace("'", 'ˈ').replace(':', 'ː'))


def _ec_phonetic(e):
    p = ipa(e[0]).replace('^', 'ɡ')  # ECDICT writes the IPA ɡ as ^ in some entries (postgraduate, glandular, fungi)
    return f'[{p}]' if p else ''


def dictionary():
    """norm -> {word, phonetic, meaning, rank, example, ref, tags, collins}; first (most frequent) variant wins.

    Words and frequency ranks come from the reference list (ref=True). Meanings come from ECDICT where it has the
    word, since it lists every part of speech ("even" is also 甚至); exam tags (cet4, cet6, ky, ielts, toefl, gre)
    define the exam word books. Exam words missing from the reference list are added with ECDICT's frequency rank.
    """
    global _DICT
    if _DICT is None:
        _DICT = _load_dictionary() or build_dictionary()
    return _DICT


DICT_FIELDS = ('word', 'phonetic', 'meaning', 'rank', 'example', 'ref', 'tags', 'collins')
DICT_FILE = Path(__file__).resolve().parent / 'corpus_data' / 'dictionary-flow.json'
DICT_SOURCES = ('yl-reference.json', 'ecdict-flow.json', 'meaning-fixes.json', 'irregular-flow.json')
# Headwords ECDICT spells wrongly (reservior is tagged 四级; saut is sauté without its accent): built under the right one
HEADWORD_FIXES = {'reservior': 'reservoir', 'saut': 'saute'}


def _load_dictionary():
    """The prebuilt dictionary (tools/build_dictionary.py): a few MB of rows instead of parsing ~38 MB of source JSON,
    whose freed memory the process rarely gives back."""
    try:
        rows = json.loads(DICT_FILE.read_text(encoding='utf-8'))['words']
    except (OSError, ValueError, KeyError):
        return None
    return {k: {f: (bool(v) if f == 'ref' else v) for f, v in zip(DICT_FIELDS, row)} for k, row in rows.items()}


def build_dictionary():
    """The dictionary from its sources (the reference list, ECDICT, the reviewed senses, irregular forms)."""
    base = Path(__file__).resolve().parent / 'corpus_data'
    data = json.loads((base / 'yl-reference.json').read_text(encoding='utf-8'))
    try:
        ecdoc = json.loads((base / 'ecdict-flow.json').read_text(encoding='utf-8'))
    except OSError:
        ecdoc = {'words': {}}
    ec = ecdoc['words']
    lower = set(ecdoc.get('lower', ()))  # common words the reference list capitalises ("Supreme"): shown as "supreme"
    out = {}
    for t in data['terms']:
        v = t['variants'][0]
        e = ec.get(t['norm'])
        out[t['norm']] = {'word': t['norm'] if t['norm'] in lower else t['word'], 'phonetic': ipa(v.get('phonetic', '')) or (_ec_phonetic(e) if e else ''),
                          'meaning': (_ec_meaning(e) if e else '') or v.get('meaning', ''), 'rank': t.get('rank') or 99999,
                          'example': (v.get('examples') or '').split('\n')[0][3:].strip() if v.get('examples') else '',
                          'ref': True, 'tags': e[2] if e else [], 'collins': e[3] if e else 0}
    for k, e in ec.items():  # alphabetical, so a base form ("abash") is in before its inflections ("abashed")
        if k in out or not _ec_meaning(e) or any(c in out for c in lemma_candidates(k)[1:]):
            continue  # skip inflections of words we already have: "cities" should look up "city"
        out[k] = {'word': k, 'phonetic': _ec_phonetic(e), 'meaning': _ec_meaning(e), 'rank': e[6] or e[5] or 30000,
                  'example': '', 'ref': False, 'tags': e[2], 'collins': e[3]}
    for wrong, right in HEADWORD_FIXES.items():  # ECDICT misspellings: the entry and its exam tags go to the right spelling
        e = out.pop(wrong, None)
        if e is None:
            continue
        if right in out:
            out[right]['tags'] = list(dict.fromkeys(list(out[right]['tags']) + list(e['tags'])))
        else:
            out[right] = {**e, 'word': right}
    try:  # senses reviewed by hand for common words whose dictionary order misleads (mean: 吝啬的 before 意思是)
        fx = json.loads((base / 'meaning-fixes.json').read_text(encoding='utf-8'))
        fixes, phonetics = fx['words'], fx.get('phonetics') or {}
    except (OSError, ValueError, KeyError):
        fixes, phonetics = {}, {}
    for k, m in fixes.items():
        if k in out:
            out[k]['meaning'] = m
    for k, p in phonetics.items():  # transcriptions reviewed by hand: missing in ECDICT (theatre, cosy) or broken there (pouring [por])
        if k in out:
            out[k]['phonetic'] = p
    return out


_IRREG = None


def irregular():
    """Irregular form -> base word (went -> go, mice -> mouse), from corpus_data/irregular-flow.json."""
    global _IRREG
    if _IRREG is None:
        try:
            _IRREG = json.loads((Path(__file__).resolve().parent / 'corpus_data' / 'irregular-flow.json').read_text(encoding='utf-8'))['forms']
        except (OSError, ValueError, KeyError):
            _IRREG = {}
    return _IRREG


def lemma_candidates(word):
    w = word.lower().strip("'")
    if w.endswith("'s"):
        w = w[:-2]
    out = [w]
    if w.endswith('ies') and len(w) > 4: out.append(w[:-3] + 'y')
    if w.endswith('es') and len(w) > 3: out.append(w[:-2])
    if w.endswith('s') and len(w) > 3: out.append(w[:-1])
    if w.endswith('ied') and len(w) > 4: out.append(w[:-3] + 'y')
    if w.endswith('ed') and len(w) > 3:
        out += [w[:-2], w[:-1]]
        if len(w) > 4 and w[-3] == w[-4]: out.append(w[:-3])
    if w.endswith('ing') and len(w) > 4:
        out += [w[:-3], w[:-3] + 'e']
        if len(w) > 5 and w[-4] == w[-5]: out.append(w[:-4])
    if w.endswith('er') and len(w) > 4:
        out += [w[:-2], w[:-1]]
        if w[-3] == w[-4]: out.append(w[:-3])
    if w.endswith('est') and len(w) > 5:
        out += [w[:-3], w[:-2]]
        if w[-4] == w[-5]: out.append(w[:-4])
    if w.endswith('ly') and len(w) > 4: out.append(w[:-2])
    if w in irregular(): out.append(irregular()[w])
    return list(dict.fromkeys(out))


def lookup(word):
    d = dictionary()
    cands = lemma_candidates(word)
    if cands[0] in d:  # the exact form has its own entry (news, planning)
        return {'query': word, 'lemma': cands[0], **d[cands[0]]}
    hits = [x for x in cands[1:] if x in d]
    if not hits:
        return None
    best = min(hits, key=lambda x: d[x]['rank'])  # hoping -> hope (not hop)
    return {'query': word, 'lemma': best, **d[best]}


def easiest_rank(word):
    """Frequency rank of the most common of the word and its base forms ("blocking" is as easy as "block")."""
    d = dictionary()
    ranks = [d[c]['rank'] for c in lemma_candidates(word) if c in d]
    return min(ranks) if ranks else 99999


def sentences(body):
    return [s.strip() for s in re.split(r'(?:(?<=[.!?])|(?<=[.!?]["”’]))\s+', body.strip()) if s.strip()]


def cefr(p):
    return p.get('cefr') or p['level']


def featured(p):
    return p['id'].startswith('v5-')


# Where a text comes from, for the line under its title (r20). A corpus file may say more per material: source (who
# made it), source_url (the original it was adapted from), references (what its facts were checked against, a list of
# {title, url}) and ai (how AI took part). The production corpus (v5) is written by the Flow editors with AI help under
# corpus_data/v5/SPEC.md; daily news is AI-rewritten web search; an imported article is the learner's own text.
V5_AI = 'AI 辅助编写'


def origin(p):
    def links(items, n):
        return [{'title': str(r.get('title') or r.get('url'))[:120], 'url': r['url']} for r in items or []
                if isinstance(r, dict) and str(r.get('url', '')).startswith('https://')][:n]
    if p.get('daily_day'):
        return {'kind': 'news', 'label': '今日热点（联网检索）', 'ai': 'AI 改写', 'reviewed': False, 'url': '',
                'references': links((p.get('provenance') or {}).get('sources'), 5)}
    if p.get('imported'):
        return {'kind': 'import', 'label': '我导入的文章', 'ai': 'AI 出题' if p.get('questions') else '', 'reviewed': None,
                'url': p['source_url'] if str(p.get('source_url', '')).startswith('https://') else '', 'references': []}
    return {'kind': 'original', 'label': p.get('source') or 'Flow 编辑部原创', 'ai': p.get('ai', V5_AI if featured(p) else ''),
            'reviewed': p.get('reviewed'), 'url': p['source_url'] if str(p.get('source_url', '')).startswith('https://') else '',
            'references': links(p.get('references'), 8),
            'quotes': [{k: qt[k] for k in ('text', 'author', 'work', 'year')} for qt in p.get('quotes') or []
                       if isinstance(qt, dict) and all(qt.get(k) for k in ('text', 'author', 'work', 'year'))][:3]}


def _pack_row(c, uid, pid):
    row = c.execute('SELECT * FROM lab_packs WHERE id=? AND (owner IS NULL OR owner=?)', (pid, uid or -1)).fetchone()
    if not row:
        return None
    if __import__('quality_service').info(c, row)['status'] == 'disabled':
        return None
    return row


_PACKS = {'key': None, 'at': 0.0, 'rows': []}


def _public_packs(c, level=None, with_hidden=False):
    """[(row, pack)] for every public material; parsed once and reused until a pack is added or 60 s pass.
    Callers treat the packs as read-only. A material an operator took off the lists (xmc.hk console, r26) is left out
    unless with_hidden; it still opens by its address (_pack_row), so history and links keep working."""
    from content_v30 import SUPERSEDED
    key = tuple(c.execute('SELECT COUNT(*), MAX(rowid) FROM lab_packs WHERE owner IS NULL').fetchone())
    if _PACKS['key'] != key or time.time() - _PACKS['at'] > 60:
        rows = []
        for row in c.execute("SELECT id, origin, created, content FROM lab_packs WHERE owner IS NULL"):
            p = json.loads(row['content'])
            if p['id'] not in SUPERSEDED:
                rows.append(({'id': row['id'], 'origin': row['origin'], 'created': row['created']}, p))
        _PACKS.update(key=key, at=time.time(), rows=rows)
    hidden = () if with_hidden else __import__('console_ops').hidden_packs(c)
    return [rp for rp in _PACKS['rows'] if (not level or cefr(rp[1]) == level) and rp[0]['id'] not in hidden]


_TOKENS = {}


def _tokens(p):
    """Lower-case words of a pack's text, cached: matching a learner's saved words against every material."""
    t = _TOKENS.get(p['id'])
    if t is None or t[0] is not p:
        t = _TOKENS[p['id']] = (p, set(WORD.findall(p['body'].lower())))
    return t[1]


def profile(c, uid):
    if not uid:
        return None
    r = c.execute('SELECT * FROM next_profiles WHERE user_id=?', (uid,)).fetchone()
    if not r:
        return None
    return {'level': r['level'], 'goal': r['goal'], 'themes': json.loads(r['themes']), 'minutes': r['minutes'],
            'voice': r['voice'] if r['voice'] in VOICES else 'us-f', 'weekly_goal': r['weekly_goal'] if 'weekly_goal' in r.keys() else 4,
            'exam': r['exam'] if 'exam' in r.keys() else None, 'exam_date': r['exam_date'] if 'exam_date' in r.keys() else None,
            'target': r['target'] if 'target' in r.keys() else None, 'level_source': (r['level_source'] if 'level_source' in r.keys() else None) or 'self'}


BANDS = ('A2', 'B1', 'B2', 'C1')
# 想达到什么水平: what each target means, and the one suggested for an exam or a goal (the page marks it 推荐)
TARGETS = {'A2': '简单日常', 'B1': '读懂一般文章', 'B2': '自如讨论', 'C1': '接近母语'}
TARGET_FOR = {'zk': 'A2', 'gk': 'B1', 'cet4': 'B1', 'cet6': 'B2', 'ky': 'B2', 'tem4': 'B2', 'tem8': 'C1', 'ielts': 'B2',
              'daily': 'B1', 'work': 'B2', 'abroad': 'B2', 'media': 'B2', 'interest': 'B1', 'exam': 'B1'}
GOAL_HINT = {'exam': '中考到考研、专四专八、雅思', 'daily': '出门、聊天、看懂身边的英文', 'work': '邮件、会议、写报告',
             'abroad': '上课、租房、办事', 'media': '不看字幕也能跟上', 'interest': '没有具体目标，想慢慢学'}


def below(target):
    """Untested, materials start one band below the target (A2 stays A2)."""
    return BANDS[max(0, BANDS.index(target) - 1)] if target in BANDS else 'B1'


def save_profile(c, uid, data):
    """The learner's settings. 选方向和目标 sends goal, target and (for 考试) exam and exam_date, with no level: the level
    is then one band below the target until a test says more (level_source 'guess'). Fields left out keep what was saved."""
    old = profile(c, uid) or {}
    target = data.get('target') if data.get('target') in BANDS else old.get('target')
    level, source = data.get('level'), data.get('level_source')
    if level in LEVELS:
        source = source if source in ('self', 'placed', 'guess') else 'self'
    elif data.get('target') in BANDS:
        level, source = below(target), 'guess'
    else:
        return {'error': '请选择水平'}, 400
    goal = data.get('goal') if data.get('goal') in GOALS else old.get('goal') or 'daily'
    themes = [t for t in (data.get('themes') or []) if t in THEMES][:6] if 'themes' in data else old.get('themes') or []
    minutes = data.get('minutes') if data.get('minutes') in MINUTES else old.get('minutes') or 10
    voice = data.get('voice') if data.get('voice') in VOICES else old.get('voice', 'us-f')
    sp = __import__('exam_sprint')
    if 'exam' in data and data.get('exam') and data.get('exam') not in sp.available():
        return {'error': '没有这个考试'}, 400
    now = time.time()
    c.execute('''INSERT INTO next_profiles(user_id, level, goal, themes, minutes, created, updated, voice, target, level_source) VALUES(?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(user_id) DO UPDATE SET level=excluded.level, goal=excluded.goal, themes=excluded.themes,
      minutes=excluded.minutes, updated=excluded.updated, voice=excluded.voice, target=excluded.target, level_source=excluded.level_source''',
              (uid, level, goal, json.dumps(themes), minutes, now, now, voice, target, source))
    # 每周目标 (r28 第 6 段): 选方向和目标 asks how many days a week (2–7); a new learner who leaves it gets 5 days when
    # preparing for an exam, 4 otherwise. A change keeps the weeks before at the goal they had (progress_service).
    wg = data.get('weekly_goal')
    wg = wg if type(wg) is int and 2 <= wg <= 7 else None if old else 5 if goal == 'exam' else 4
    if wg and wg != (old.get('weekly_goal') or 4):
        if old:
            __import__('progress_service').goal_changed(c, uid, old.get('weekly_goal') or 4, wg)
        c.execute('UPDATE next_profiles SET weekly_goal=? WHERE user_id=?', (wg, uid))
    # the exam goal (考试冲刺) in the same call, when it changed (an exam whose date has passed does not block other settings)
    if 'exam' in data and ((data.get('exam') or None), (data.get('exam_date') or None)) != (old.get('exam'), old.get('exam_date')):
        out, code = sp.set_goal(c, uid, {'exam': data.get('exam') or '', 'date': data.get('exam_date') or ''})
        if code != 200:
            c.commit()
            return out, code
    c.commit()
    # 选方向和目标 with an exam and no word plan yet: one is made on the exam's book, 10 new words a day (the page says so;
    # 单词 → 背词计划 changes it). A guest's choices reach here at sign-in, so the plan comes then.
    import vocab_service as vs
    made, exam = None, (profile(c, uid) or {}).get('exam')
    if data.get('exam') and exam and exam in vs.book_words() and not vs.plan(c, uid):
        vs.save_plan(c, uid, {'book': exam, 'daily_new': 10, 'retention': 0.9})
        made = {'book': exam, 'title': vs.book_title(exam), 'daily_new': 10}
    return {'profile': profile(c, uid), 'plan_made': made}, 200


def set_voice(c, uid, data):
    voice = data.get('voice')
    if voice not in VOICES:
        return {'error': '声音不正确'}, 400
    if c.execute('UPDATE next_profiles SET voice=?, updated=? WHERE user_id=?', (voice, time.time(), uid)).rowcount:
        c.commit()
    return {'voice': voice}, 200


def audio_index():
    """{material id: [voices]} and its version. With R2 in use (media.py), from the release's media manifest, so a
    material has narration as soon as it is uploaded; otherwise from audio/index.json, reloaded when it changes.
    audio/index-old.json lists the narration of the older materials (简版, r27 content line). It is a separate file
    because code before it serves only v5 ids: had their entries gone into index.json, an older release would have
    offered narration it then refused to serve."""
    import media
    listed = media.narration()
    if listed is not None:
        return {k: [v for v in vs if v in VOICES] for k, vs in listed.items()}, media.version()
    files = (AUDIO_DIR / 'index.json', AUDIO_DIR / 'index-old.json')
    mtimes = tuple(f.stat().st_mtime if f.exists() else 0 for f in files)
    if not any(mtimes):
        return {}, 0
    if _AUDIO['mtime'] != mtimes:
        index = {}
        for f in files:
            try:
                index.update({k: [v for v in vs if v in VOICES] for k, vs in json.loads(f.read_text()).items()
                              if NARRATION_ID.fullmatch(k)})
            except (OSError, ValueError, AttributeError):
                pass
        _AUDIO['index'] = index
        _AUDIO['mtime'] = mtimes
    return _AUDIO['index'], int(max(mtimes))


def audio_file(voice, pid, ext):
    """Path of a narration file, or None. Names are validated so nothing outside AUDIO_DIR can be served."""
    if voice not in VOICES or ext not in ('m4a', 'mp4', 'json') or not NARRATION_ID.fullmatch(pid or ''):
        return None
    name = pid + '.' + ('m4a' if ext == 'mp4' else ext)  # .mp4 is the same file, for edge caching
    return __import__('media').path(f'{voice}/{name}', AUDIO_DIR / voice / name)  # fetched from R2 when missing here


def _done(c, uid):
    out = {}
    if uid:
        for r in c.execute('SELECT pack, step FROM next_progress WHERE user_id=?', (uid,)):
            out.setdefault(r['pack'], set()).add(r['step'])
    return out


def _card(pack, done=None, extra=None):
    words = len(pack['body'].split())
    return {'id': pack['id'], 'title': pack['title'], 'title_en': pack.get('title_en', ''), 'level': cefr(pack), 'theme': pack['theme'],
            'theme_label': THEMES.get(pack['theme'], ''), 'genre': pack.get('genre', ''), 'words': words, 'minutes': max(3, round(words / 30) + 4),
            'preview': pack.get('summary_zh') or sentences(pack['body'])[0][:140], 'preview_en': sentences(pack['body'])[0][:160],
            'daily': bool(pack.get('daily_day')), 'featured': featured(pack), 'grammar': pack.get('grammar', []),
            'brief': not featured(pack) and not pack.get('daily_day') and not pack.get('imported'),  # 简版: the older, shorter texts
            'steps': sorted(done or [], key=STEPS.index), **(extra or {})}


# ---------- knowledge graph ----------

def _found(p):
    """{point: [sentences]} for the grammar_more points this material's text shows (worked out once per material)."""
    key = len(p.get('body', ''))
    hit = _GRAMMAR_FOUND.get(p['id'])
    if not hit or hit[0] != key:
        hit = _GRAMMAR_FOUND[p['id']] = (key, GM.examples(p.get('body', '')))
    return hit[1]


def pack_grammar(p):
    """The grammar points a material practises: its own tags, then the further points found in its text."""
    own = list(p.get('grammar', []))
    return own + [n for n in _found(p) if n not in own]


def nodes_meta(c):
    rows = c.execute('SELECT s.id, s.topic, s.title, s.prereq, s.lesson, s.example FROM subskills s ORDER BY s.rowid').fetchall()
    return {r['id']: dict(r) for r in rows}


def graph_states(c, uid):
    """Per grammar node: exposure (read), use (wrote), AI flags, and classic evidence state."""
    meta = nodes_meta(c)
    out = {n: {'node': n, 'met': 0, 'used': 0, 'flags': 0, 'clean': 0, 'evidence': None} for n in meta}
    if not uid:
        for v in out.values():
            v['status'] = 'untouched'
        return out
    packs = {}
    for r in c.execute("SELECT DISTINCT pack, step FROM next_progress WHERE user_id=? AND step IN ('read','output')", (uid,)):
        packs.setdefault(r['pack'], set()).add(r['step'])
    for r in c.execute('SELECT DISTINCT pack FROM next_easy_reads WHERE user_id=?', (uid,)):  # easy reading counts as reading
        packs.setdefault(r['pack'], set()).add('read')
    if packs:
        q = 'SELECT id, content FROM lab_packs WHERE id IN (%s)' % ','.join('?' * len(packs))
        for r in c.execute(q, list(packs)):
            for n in pack_grammar(json.loads(r['content'])):
                if n in out:
                    out[n]['met'] += 1
                    if 'output' in packs[r['id']]:
                        out[n]['used'] += 1
    for r in c.execute('SELECT node, kind, COUNT(*) n FROM next_node_notes WHERE user_id=? AND created>? GROUP BY node, kind', (uid, time.time() - 30 * 86400)):
        if r['node'] in out:
            out[r['node']]['flags' if r['kind'] == 'flag' else 'clean'] += r['n']
    ev = __import__('event_service')
    for n in out:
        rows = [dict(r) for r in c.execute('SELECT * FROM learning_events WHERE user_id=? AND node=? ORDER BY created,id', (uid, n))]
        if rows:
            out[n]['evidence'] = ev.summarize(n, rows)['state']
    for v in out.values():
        stable = v['evidence'] in ('独立完成一次', '独立完成', '延迟记得', '迁移已有证据')
        if v['flags'] > v['clean'] or v['evidence'] == '需要巩固':
            v['status'] = 'watch'
        elif stable:
            v['status'] = 'solid'
        elif v['used']:
            v['status'] = 'used'
        elif v['met'] or v['evidence']:
            v['status'] = 'met'
        else:
            v['status'] = 'untouched'
    return out


def graph(c, uid, level=None):
    prof = profile(c, uid)
    level = (prof or {}).get('level') or (level if level in LEVELS else 'B1')
    meta = nodes_meta(c)
    states = graph_states(c, uid)
    counts = {}
    for _, p in _public_packs(c):
        for n in pack_grammar(p):
            counts[n] = counts.get(n, 0) + 1
    focus = set(LEVEL_NODES.get(level, meta.keys()))
    due = set(GB.due(c, uid)) if uid else set()
    topics = []
    for tid, tname in TOPICS:
        nodes = [{'id': n, 'title': m['title'], 'prereq': m['prereq'], 'materials': counts.get(n, 0), 'focus': n in focus, 'level': node_level(n), 'due': n in due,
                  'status': states[n]['status'], 'label': STATUS_LABEL[states[n]['status']], 'met': states[n]['met'],
                  'used': states[n]['used'], 'flags': states[n]['flags']} for n, m in meta.items() if m['topic'] == tid]
        topics.append({'id': tid, 'title': tname, 'nodes': nodes})
    summary = {k: sum(1 for s in states.values() if s['status'] == k) for k in STATUS_LABEL}
    summary['due'] = len(due)
    GL = __import__('graph_links')
    order = path_order(meta)
    route = [{'band': b, 'nodes': [{'id': n, 'title': meta[n]['title'], 'status': states[n]['status'], 'due': n in due, 'focus': n in focus,
                                    'prereq': meta[n]['prereq']} for n in order if node_level(n) == b]} for b in ('A2', 'B1', 'B2', 'C1')]
    links = {'prereq': [[m['prereq'], n] for n, m in meta.items() if m['prereq'] in meta],
             'confusable': [[a, b] for a, b, _ in GL.CONFUSABLE if a in meta and b in meta]}
    return {'level': level, 'topics': topics, 'summary': summary, 'labels': STATUS_LABEL, 'total': len(meta), 'route': route, 'links': links}


_TOGETHER = {}


def together(c, nid, k=3):
    """The points that turn up in the same materials as this one most often (worked out once per corpus size)."""
    packs = _public_packs(c)
    if _TOGETHER.get('n') != len(packs):
        pairs = {}
        for _, p in packs:
            g = sorted(set(pack_grammar(p)))
            for i, a in enumerate(g):
                for b in g[i + 1:]:
                    pairs[(a, b)] = pairs.get((a, b), 0) + 1
        _TOGETHER.clear(); _TOGETHER.update(n=len(packs), pairs=pairs)
    hits = [(b if a == nid else a, n) for (a, b), n in _TOGETHER['pairs'].items() if nid in (a, b)]
    hits.sort(key=lambda x: -x[1])
    return hits[:k]


def path_order(meta):
    """The order to learn the points in: by level band, and within a band prerequisites first, then topic order."""
    topic_i = {t: i for i, (t, _) in enumerate(TOPICS)}
    out = []
    for band in ('A2', 'B1', 'B2', 'C1'):
        todo = [n for n in meta if node_level(n) == band]
        todo.sort(key=lambda n: (topic_i.get(meta[n]['topic'], 99), list(meta).index(n)))
        placed = set(out)
        group = []
        while todo:
            ready = next((n for n in todo if not meta[n]['prereq'] or meta[n]['prereq'] in placed or meta[n]['prereq'] not in todo), todo[0])
            group.append(ready); placed.add(ready); todo.remove(ready)
        out.extend(group)
    return out


def node_level(nid):
    """The level a point belongs to: the first level that builds it (A2 → C1)."""
    if nid in GM.BY_ID:
        return GM.BY_ID[nid]['level']
    return next((lv for lv in ('A2', 'B1', 'B2', 'C1') if nid in LEVEL_NODES.get(lv, ())), 'B2')


def practice(c, nid, limit=4):
    """A round of verification questions on a point: drawn at random from its ten, options shuffled, no answers."""
    return GB.draw(c, nid, limit)


def node_answer(c, uid, data):
    """Check one practice answer on a point's page. Signed in, it is evidence for that point (one per question per
    day, so an answer remembered a day later counts as delayed recall), and a wrong answer goes to the mistake book."""
    qid, choice = data.get('question'), data.get('choice')
    q = c.execute("SELECT id, node, prompt, options, answer, explanation FROM questions WHERE id=? AND status='published' AND node IS NOT NULL",
                  (qid if type(qid) is int else -1,)).fetchone()
    if not q:
        return {'error': '题目不存在'}, 404
    options = json.loads(q['options'])
    if type(choice) is not int or not 0 <= choice < len(options):
        return {'error': '选项不正确'}, 400
    correct = choice == q['answer']
    out = {'correct': correct, 'answer': q['answer'], 'explanation': q['explanation'] or ''}
    if uid:
        day = int(time.time() // 86400)
        __import__('event_service').record(c, uid, q['node'], f"next-node:{q['id']}:{day}", 'choice', str(q['id']), 'question:' + str(q['id']),
                                           int(correct), 0, 'rule', {'choice': choice, 'from': data.get('from') if data.get('from') in ('review', 'mix', 'exam') else 'node-page'})
        if not correct and data.get('from') not in ('review', 'mix', 'exam'):  # those rounds already reschedule the point
            __import__('skills_service').add_mistake(c, uid, 'question', q['prompt'], f"gq:{q['id']}", '', '', 'grammar', node=q['node'],
                                                     extra={'options': options, 'answer': q['answer'], 'evidence': q['explanation'] or ''}, commit=False)
        review = GB.schedule(c, uid, q['node'], correct)
        c.commit()
        st = graph_states(c, uid)[q['node']]
        out.update(status=st['status'], label=STATUS_LABEL[st['status']], review=review)
    return out, 200


def node(c, uid, nid, level=None):
    meta = nodes_meta(c)
    if nid not in meta:
        return {'error': '知识点不存在'}, 404
    m = meta[nid]
    prof = profile(c, uid)
    level = (prof or {}).get('level') or (level if level in LEVELS else 'B1')
    states_all = graph_states(c, uid)
    st = states_all[nid]
    done = _done(c, uid)
    examples, mats = [], []
    for _, p in _public_packs(c):
        if nid not in pack_grammar(p):
            continue
        for k in p.get('knowledge', []):
            if k.get('node') == nid and len(examples) < 40:
                examples.append({'quote': k['quote'], 'explanation': re.split(r'[；;]', k.get('explanation', ''))[0].strip(), 'pack': p['id'],
                                 'level': cefr(p), 'featured': featured(p)})
        if nid in GM.BY_ID and len(examples) < 40:  # sentences found in the text: what the form is, not a claim about this sentence's meaning
            for q in _found(p).get(nid, [])[:1]:
                examples.append({'quote': q, 'explanation': GM.BY_ID[nid]['note'], 'pack': p['id'], 'level': cefr(p), 'featured': featured(p)})
        mats.append(p)
    target = level if level != 'C1' else 'C1'
    mine = set((prof or {}).get('themes') or [])  # the learner's topics first (职场沟通 for a work learner)
    mats.sort(key=lambda p: (0 if cefr(p) == target else 1, 0 if p['theme'] in mine else 1, 0 if featured(p) else 1, 'check' in done.get(p['id'], set()), p['id']))
    examples.sort(key=lambda e: (0 if e['level'] == target else 1, 0 if e['featured'] else 1))
    notes = [dict(r) for r in c.execute('SELECT pack, kind, detail, created FROM next_node_notes WHERE user_id=? AND node=? ORDER BY created DESC LIMIT 6', (uid or -1, nid))]
    prereq = meta.get(m['prereq']) if m['prereq'] else None
    unlocks = [{'id': k, 'title': v['title'], 'status': states_all[k]['status']} for k, v in meta.items() if v['prereq'] == nid]
    GL = __import__('graph_links')
    l1 = GL.L1.get(nid)
    related = {'confusable': [{'id': o, 'title': meta[o]['title'], 'how': how, 'status': states_all[o]['status']} for o, how in GL.confusable(nid) if o in meta],
               'together': [{'id': o, 'title': meta[o]['title'], 'materials': k, 'status': states_all[o]['status']} for o, k in together(c, nid) if o in meta]}
    return {'id': nid, 'title': m['title'], 'topic': dict(TOPICS).get(m['topic'], m['topic']), 'lesson': m['lesson'], 'example': m['example'],
            'level': node_level(nid), 'focus': nid in set(LEVEL_NODES.get(level, ())), 'page': __import__('content_subskills').page(nid),
            'practice': practice(c, nid), 'review': GB.review_of(c, uid, nid),
            'status': st['status'], 'label': STATUS_LABEL[st['status']], 'met': st['met'], 'used': st['used'], 'flags': st['flags'],
            'evidence': st['evidence'], 'prereq': {'id': prereq['id'], 'title': prereq['title'], 'status': states_all[prereq['id']]['status']} if prereq else None,
            'unlocks': unlocks, 'related': related,
            'l1': {'why': l1[0], 'zh': l1[1], 'wrong': l1[2], 'right': l1[3]} if l1 else None,
            'examples': examples[:6], 'materials': [_card(p, done.get(p['id'])) for p in mats[:6]],
            'notes': [{'pack': n['pack'], 'kind': n['kind'], 'detail': n['detail'], 'created': n['created']} for n in notes]}, 200


# ---------- home & library ----------

def _card_norms(c, uid):
    """(shown text, norm, source) of the learner's saved and studied items; very common book words are left out."""
    if not uid:
        return []
    return [(r['text'], r['norm'], r['source']) for r in c.execute(
        "SELECT text, norm, source FROM next_cards WHERE user_id=? AND known=0 AND (source='saved' OR COALESCE(rank, 99999)>3000)", (uid,))]


def featured_left(c, uid, level, done=None):
    """How many of a level's featured texts the learner has not learned yet (every episode of a serial counts).
    今日 says so from seven down (r27 content line); other parts of 今日 can use it too (今日好句 avoids the last few)."""
    done = _done(c, uid) if done is None else done
    return sum(1 for r, p in _public_packs(c, level) if r['origin'] != 'daily' and featured(p) and 'check' not in done.get(p['id'], set()))


def home(c, uid, level=None, themes=None):
    prof = profile(c, uid)
    level = (prof or {}).get('level') or (level if level in LEVELS else 'B1')
    themes = (prof or {}).get('themes') or [t for t in (themes or []) if t in THEMES]
    done = _done(c, uid)
    day = _day()
    # A serial is recommended one episode at a time: only its next unread episode, never one from the middle.
    serial_next = {s['next'] for s in series_list(c, uid)}
    pool = [(r, p) for r, p in _public_packs(c, level) if r['origin'] != 'daily' and (not p.get('series') or p['id'] in serial_next)]
    learned = lambda p: 'check' in done.get(p['id'], set())
    # What 今日 recommends, tier by tier, until there are three (r27 content line, audit 3.2; the user's choices):
    # this level's featured texts not learned yet; then the next level's (with a word that this level is done); then
    # 精读重学, this level's featured texts again, the longest ago first; only then the older texts (简版); and if even
    # that is empty, anything at this level. C1 has no next level, so it goes straight to 精读重学.
    feat = [rp for rp in pool if featured(rp[1])]
    tiers = [('', [rp for rp in feat if not learned(rp[1])])]
    up = UP_LEVEL.get(level)
    if up:
        tiers.append(('up', [rp for rp in _public_packs(c, up) if rp[0]['origin'] != 'daily' and featured(rp[1]) and not rp[1].get('series')
                             and not learned(rp[1])]))
    last = {}
    if uid:
        # The latest time each text was learned: the first time (next_progress) or again (next_step_log, since #51)
        last = {r['pack']: r['t'] for r in c.execute(
            "SELECT pack, MAX(created) t FROM (SELECT pack, created FROM next_progress WHERE user_id=? AND step='check' "
            "UNION ALL SELECT pack, created FROM next_step_log WHERE user_id=? AND step='check') GROUP BY pack", (uid, uid))}
    tiers.append(('redo', sorted((rp for rp in feat if learned(rp[1])), key=lambda rp: (last.get(rp[1]['id'], 0), rp[1]['id']))))
    tiers.append(('brief', [rp for rp in pool if not featured(rp[1]) and not learned(rp[1])]))
    tiers.append(('any', pool))
    left = featured_left(c, uid, level, done)
    states = graph_states(c, uid) if uid else {}
    focus = set(LEVEL_NODES.get(level, ())) or None
    meta_titles = {k: v['title'] for k, v in nodes_meta(c).items()}
    saved = _card_norms(c, uid)
    # Ties are broken per day and level, not per account, so signing in does not swap the article a guest was shown.
    seed = lambda p: hashlib.sha256(f"{day}|{level}|{p['id']}".encode()).hexdigest()
    # New grammar counts only once the learner has some (a new account ranks like the guest it was a minute ago).
    personal = bool(uid) and any(v.get('status') != 'untouched' for v in states.values())

    def score(p):
        s, reasons = 0.0, []
        if featured(p):
            s += 3
        if themes and p['theme'] in themes:
            s += 2
        for n in p.get('grammar', []):
            st = states.get(n, {}).get('status', 'untouched')
            if st == 'watch':
                s += 4; reasons.append(f'补一补「{meta_titles.get(n, n)}」')
            elif st in ('met', 'untouched') and (focus is None or n in focus) and personal:
                s += 1.2 if st == 'untouched' else 0.8
                if st == 'untouched' and len(reasons) < 1:
                    reasons.append(f'新知识点「{meta_titles.get(n, n)}」')
        words, body = _tokens(p), None
        hits = []
        for t, n, src in saved:
            if len(n) <= 2:
                continue
            if ' ' not in n and "'" not in n and '-' not in n:
                if n in words:
                    hits.append((t, src))
            else:
                body = body or p['body'].lower()
                if re.search(r'(?<![a-z])' + re.escape(n) + r'(?![a-z])', body):
                    hits.append((t, src))
        if hits:
            t, src = next((h for h in hits if h[1] == 'saved'), hits[0])
            s += min(3, 1.5 * len(hits)); reasons.insert(0, f'你收藏的「{t}」又出现了' if src == 'saved' else f'你在背的「{t}」在这篇里')
        return s, reasons[:2]

    picks, taken = [], set()
    for kind, rows in tiers:
        if len(picks) >= 3:
            break
        if kind == 'redo':  # the longest ago first, not by score: each text comes round again in turn
            ranked = [(p, []) for _, p in rows]
        else:
            ranked = sorted(((p,) + score(p) for _, p in rows), key=lambda x: (-x[1], seed(x[0])))
            ranked = [(p, reasons) for p, _, reasons in ranked]
        for p, reasons in ranked:
            if len(picks) >= 3:
                break
            if p['id'] in taken:
                continue
            taken.add(p['id'])
            extra = {'reasons': reasons}
            if kind == 'up':
                extra['reasons'] = [f'这一级的精选学完了，先试试 {up} 的'] + reasons[:1]
            elif kind == 'redo':
                # calendar days in Beijing time, not 24-hour periods: last night's text is 「昨天学过」 this morning
                days = (datetime.date.fromisoformat(_day()) - datetime.date.fromisoformat(_day(last.get(p['id'], time.time())))).days
                when = '今天学过' if days <= 0 else '昨天学过' if days == 1 else f'{days} 天前学过'
                extra = {'reasons': [f'精读重学：{when}' if p['id'] in last else '精读重学'], 'redo': True}
            picks.append(_card(p, done.get(p['id']), extra))
    news = None
    for r, p in sorted(_public_packs(c), key=lambda rp: -rp[0]['created']):
        if r['origin'] == 'daily' and r['created'] > time.time() - 3 * 86400:
            news = _card(p, done.get(p['id']), {'source': p.get('source', ''), 'day': p.get('daily_day')})
            break
    resume = None
    if uid:
        for row in c.execute('SELECT pack, MAX(created) t FROM next_progress WHERE user_id=? GROUP BY pack ORDER BY t DESC LIMIT 5', (uid,)).fetchall():
            if 'output' not in done.get(row['pack'], set()):
                pr = _pack_row(c, uid, row['pack'])
                if pr:
                    resume = _card(json.loads(pr['content']), done.get(row['pack']))
                    break
    g = None
    if uid:
        g = {k: sum(1 for s in states.values() if s['status'] == k) for k in STATUS_LABEL}
        g['total'] = len(states)
        watch = [n for n, s in states.items() if s['status'] == 'watch']
        g['watch'] = [{'id': n, 'title': meta_titles.get(n, n)} for n in watch[:3]]
        g['due'] = [{'id': n, 'title': meta_titles.get(n, n)} for n in GB.due(c, uid) if n not in watch][:3]
    # 今日好句 (r27, daily_line.py): a public-domain line or a sentence from a featured text, not today's own article
    line = __import__('daily_line').today(c, uid, level, skip={p['id'] for p in picks[:1]})
    out = {'profile': prof, 'level': level, 'level_label': LEVELS[level]['label'], 'today': picks, 'news': news, 'resume': resume, 'line': line,
           'featured_left': left if uid else None, 'level_up': up,
           'stats': stats(c, uid) if uid else None, 'graph': g,
           'announce': __import__('console_ops').current_announcement(c),
           'trial_survey': bool(uid) and __import__('class_service').survey_due(c, uid)}  # 公告 from the xmc.hk console, at the top of 今日
    if uid and prof:
        import skills_service as sk
        out['sprint'] = __import__('exam_sprint').brief(c, uid)  # 考试冲刺: the exam and its days left, in the plan's header line
        # 选方向和目标: a level guessed from the target, with no test taken yet: 今日 suggests one (ability_radar)
        out['level_guess'] = prof.get('level_source') == 'guess' and not c.execute('SELECT 1 FROM next_assess WHERE user_id=? LIMIT 1', (uid,)).fetchone()
        out['path'] = sk.daily_path(c, uid, out)
        out['suggest'] = sk.suggest_level(c, uid)
    return out


def stats(c, uid):
    now = time.time()
    week_start = now - 7 * 86400
    days = set()
    for (t,) in c.execute('SELECT created FROM next_progress WHERE user_id=? AND created>?', (uid, week_start)):
        days.add(_day(t))
    for (t,) in c.execute('SELECT created FROM next_reviews WHERE user_id=? AND created>?', (uid, week_start)):
        days.add(_day(t))
    for (t,) in c.execute('SELECT created FROM next_relisten WHERE user_id=? AND created>?', (uid, week_start)):
        days.add(_day(t))
    week = [_day(now - i * 86400) for i in range(6, -1, -1)]
    import vocab_service
    vocab_service.introduce(c, uid, now)  # today's new words from the learner's word book, so home shows the real task
    vc = vocab_service.counts(c, uid, now)
    return {
        'due': vc['due'], 'new': vc['new'], 'minutes': vc['minutes'], 'vocab_plan': bool(vocab_service.plan(c, uid)),
        'cards': c.execute('SELECT COUNT(*) FROM next_cards WHERE user_id=?', (uid,)).fetchone()[0],
        'materials_done': c.execute("SELECT COUNT(DISTINCT pack) FROM next_progress WHERE user_id=? AND step='check'", (uid,)).fetchone()[0],
        'reviews_week': c.execute('SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND created>?', (uid, week_start)).fetchone()[0],
        'week': [{'day': d, 'active': d in days} for d in week],
        'habit': habit(c, uid, ((profile(c, uid) or {}).get('weekly_goal')) or 4, now),
        'progress': __import__('progress_service').week(c, uid, now),  # 这周进步 at the top of 今日 (r27)
    }


def habit(c, uid, goal, now=None):
    """每周目标: this week's study days (Monday to Sunday, China time) against the learner's goal, the weeks that reached
    their goal in total (weeks: only counts up, a missed day or week takes none away), how many in a row (streak, kept
    for older pages) and last week's result for the Monday notice. A day counts when anything was learned
    (progress_service.study_days: a step of a material, a review, a relisten, easy reading, a practice, a question)."""
    PS = __import__('progress_service')
    now = now or time.time()
    D = datetime.timedelta
    today = datetime.datetime.fromtimestamp(now, TZ).date()
    monday = today - D(days=today.weekday())
    days = PS.study_days(c, uid)
    count = lambda mon: sum(1 for k in range(7) if mon + D(days=k) in days)
    done, last = count(monday), count(monday - D(weeks=1))
    streak, w = 0, monday - D(weeks=1)
    while streak < 52 and count(w) >= goal:
        streak += 1; w -= D(weeks=1)
    # r28 第 6 段: the last two weeks both short of the goal they had, each with some study: suggest the goal the learner
    # actually keeps (at least 2 days), once, on Monday (the page). Weeks reached before stay reached.
    hist, lower = PS._history(c, uid), None
    w1, w2 = last, count(monday - D(weeks=2))
    g1, g2 = (PS._goal_for(hist, (monday - D(weeks=k)).isoformat(), goal) for k in (1, 2))
    if 0 < w1 < g1 and 0 < w2 < g2 and max(2, w1, w2) < goal:
        lower = {'goal': max(2, w1, w2), 'weeks': [w2, w1]}
    return {'goal': goal, 'done': done, 'met': done >= goal, 'streak': streak + (done >= goal), 'monday': monday.isoformat(),
            'weeks': PS.weeks_reached(c, uid, goal, days, monday),
            'days': [{'day': (monday + D(days=k)).isoformat(), 'active': monday + D(days=k) in days, 'today': monday + D(days=k) == today} for k in range(7)],
            'last_week': {'done': last, 'met': last >= goal}, 'lower': lower}


def set_weekly_goal(c, uid, data):
    try:
        goal = int(data.get('goal'))
    except (TypeError, ValueError):
        goal = 0
    if not 1 <= goal <= 7:
        return {'error': '每周目标是 1 到 7 天'}, 400
    old = (profile(c, uid) or {}).get('weekly_goal')
    if not c.execute('UPDATE next_profiles SET weekly_goal=?, updated=? WHERE user_id=?', (goal, time.time(), uid)).rowcount:
        return {'error': '请先设置学习目标和水平'}, 400
    if old != goal:  # the weeks before keep the goal they had: a new goal never takes away a week already reached
        __import__('progress_service').goal_changed(c, uid, old, goal)
    c.commit()
    return {'habit': habit(c, uid, goal)}, 200


def library(c, uid, level=None, theme=None, page=1, per=12, featured_only=False):
    done = _done(c, uid)
    rows = _public_packs(c, level if level in LEVELS else None)
    rows = [rp for rp in rows if (not theme or rp[1]['theme'] == theme) and (not featured_only or featured(rp[1]))]
    order = {'A2': 0, 'B1': 1, 'B2': 2, 'C1': 3}
    rows.sort(key=lambda rp: (0 if rp[0]['origin'] == 'daily' else 1, -(rp[0]['created'] if rp[0]['origin'] == 'daily' else 0),
                              0 if featured(rp[1]) else 1, order.get(cefr(rp[1]), 9), rp[1]['id']))
    page = max(1, page)
    return {'total': len(rows), 'page': page, 'per': per, 'themes': THEMES,
            'featured_total': sum(1 for _, p in _public_packs(c) if featured(p)),
            'items': [_card(p, done.get(p['id'])) for _, p in rows[(page - 1) * per: page * per]],
            'series': series_list(c, uid) if page == 1 else []}


def excerpt(c, pid, evidence, around=1):
    """The sentence a question's answer rests on, with one sentence either side: enough of the text to answer it again."""
    row = c.execute('SELECT content FROM lab_packs WHERE id=?', (pid or '',)).fetchone()
    if not row:
        return None
    p = json.loads(row['content'])
    sents = sentences(p.get('body', ''))
    ev = (evidence or '').strip()
    hit = next((i for i, s in enumerate(sents) if ev and ev[:60] in s), None)
    if hit is None:
        words = set(re.findall(r"[a-z']+", ev.lower()))
        scores = [len(words & set(re.findall(r"[a-z']+", s.lower()))) for s in sents]
        hit = max(range(len(sents)), key=scores.__getitem__) if sents and max(scores) >= 3 else None
    if hit is None:
        return None
    lo, hi = max(0, hit - around), min(len(sents), hit + around + 1)
    return {'text': ' '.join(sents[lo:hi]), 'evidence': ev, 'pack': pid, 'title': p.get('title', ''), 'start': lo > 0, 'end': hi < len(sents)}


# ---------- serial stories ----------

def _series_packs(c, sid=None):
    """series id -> its episodes in order (materials whose pack carries a "series" block)."""
    out = {}
    for _, p in _public_packs(c):
        s = p.get('series')
        if isinstance(s, dict) and s.get('id') and (sid is None or s['id'] == sid):
            out.setdefault(s['id'], []).append(p)
    for eps in out.values():
        eps.sort(key=lambda p: p['series'].get('part', 0))
    return out


def _read(steps):
    return 'check' in steps or 'output' in steps


def series_list(c, uid):
    done = _done(c, uid)
    out = []
    for sid, eps in _series_packs(c).items():
        s = eps[0]['series']
        nxt = next((p for p in eps if not _read(done.get(p['id'], set()))), None)
        out.append({'id': sid, 'title': s['title'], 'title_en': s.get('title_en', ''), 'blurb': s.get('blurb', ''), 'level': cefr(eps[0]), 'of': len(eps),
                    'done': sum(1 for p in eps if _read(done.get(p['id'], set()))), 'next': nxt['id'] if nxt else None,
                    'next_part': nxt['series'].get('part') if nxt else None})
    return out


def series(c, uid, sid):
    eps = _series_packs(c, sid).get(sid)
    if not eps:
        return {'error': '连载不存在'}, 404
    done = _done(c, uid)
    s = eps[0]['series']
    cards = [_card(p, done.get(p['id']), {'part': p['series'].get('part'), 'read': _read(done.get(p['id'], set()))}) for p in eps]
    nxt = next((x for x in cards if not x['read']), None)
    return {'id': sid, 'title': s['title'], 'title_en': s.get('title_en', ''), 'blurb': s.get('blurb', ''), 'level': cefr(eps[0]), 'of': len(eps),
            'episodes': cards, 'next': nxt['id'] if nxt else None, 'done': sum(1 for x in cards if x['read'])}, 200


def _series_nav(c, p):
    s = p.get('series')
    if not isinstance(s, dict) or not s.get('id'):
        return None
    ids = [x['id'] for x in _series_packs(c, s['id']).get(s['id'], [])]
    i = ids.index(p['id']) if p['id'] in ids else -1
    return {'id': s['id'], 'title': s['title'], 'part': s.get('part'), 'of': len(ids),
            'prev': ids[i - 1] if i > 0 else None, 'next': ids[i + 1] if 0 <= i < len(ids) - 1 else None}


# ---------- material ----------

def _task(pack, level):
    if isinstance(pack.get('task'), dict) and pack['task'].get('prompt'):
        k = next((k for k in pack.get('knowledge', []) if k.get('quote') and pack['task'].get('model', '') in k['quote']), None)
        return {'prompt': pack['task']['prompt'], 'model': pack['task'].get('model', ''), 'hint': (k or {}).get('explanation', '')}
    k = dict((pack.get('knowledge') or [{}])[0])
    # Old explanations end with internal caveats ("阅读不等于已掌握…"); learners only need the first clause.
    k['explanation'] = re.split(r'[；;]', k.get('explanation', ''))[0].strip()
    vocab = [v['term'] for v in pack.get('vocabulary', [])][:3]
    if k.get('quote'):
        model = k['quote']
        if level == 'A2':
            return {'prompt': '仿照下面这句的结构，写一句关于你自己的话。', 'model': model, 'hint': k.get('explanation', '')}
        return {'prompt': '仿照下面这句的结构，写一两句和你自己的经历有关的话。', 'model': model, 'hint': k.get('explanation', '')}
    if vocab:
        return {'prompt': f"用上 {'、'.join(vocab)}，写一两句和你自己有关的话。", 'model': '', 'hint': ''}
    return {'prompt': '挑一个这篇里你喜欢的表达，用它写一两句和你自己有关的话。', 'model': '', 'hint': ''}


def material(c, uid, pid, level=None, offline=False):
    """offline: also the answers and their evidence, for a copy kept on the phone (the page grades there without a
    connection and sends the answers later, so the mistake book and progress are recorded as usual)."""
    row = _pack_row(c, uid, pid)
    if not row:
        return {'error': '材料不存在'}, 404
    p = json.loads(row['content'])
    prof = profile(c, uid)
    level = (prof or {}).get('level') or (level if level in LEVELS else 'B1')
    hard_rank = LEVELS[level]['hard_rank']
    body = p['body']
    variant = None
    if level != cefr(p):
        v = c.execute('SELECT body, notes FROM next_variants WHERE pack=? AND level=?', (pid, level)).fetchone()
        if v:
            variant = {'level': level, 'body': v['body'], 'notes': json.loads(v['notes'])}
    text = variant['body'] if variant else body
    vocab = {v['term'].lower(): v for v in p.get('vocabulary', [])}
    hard = {}
    for w in WORD.findall(text + ' ' + (body if variant else '')):
        key = w.lower()
        if key in hard or key in vocab:
            continue
        hit = lookup(w)
        if hit and easiest_rank(w) > hard_rank and not hit['meaning'].startswith('num.'):  # forty, eighty: numbers are not "hard"
            hard[key] = {'meaning': hit['meaning'][:80], 'rank': hit['rank']}
    qtypes = __import__('content_v50').QUESTION_TYPES
    qs = [{'prompt': q['prompt'], 'options': q['options'], **({'type': qtypes[q['type']]} if q.get('type') in qtypes else {})}
          for q in p.get('questions', [])]
    done = _done(c, uid).get(pid, set())
    states = graph_states(c, uid)
    meta = nodes_meta(c)
    notes = []
    for k in p.get('knowledge', []):
        n = k.get('node')
        notes.append({'node': n, 'title': meta.get(n, {}).get('title', n), 'quote': k.get('quote', ''),
                      'explanation': re.split(r'[；;]', k.get('explanation', ''))[0].strip() if not featured(p) else k.get('explanation', ''),
                      'status': states.get(n, {}).get('status', 'untouched'), 'label': STATUS_LABEL[states.get(n, {}).get('status', 'untouched')]})
    # two more points found in this text, the learner's level first: the form, shown in one of its sentences
    focus = set(LEVEL_NODES.get((profile(c, uid) or {}).get('level') or level or 'B1', ()))
    found = sorted((n for n in _found(p) if n in meta and n not in {x['node'] for x in notes}), key=lambda n: (n not in focus, GM.BY_ID[n]['level']))
    for n in found[:2]:
        st = states.get(n, {}).get('status', 'untouched')
        notes.append({'node': n, 'title': meta[n]['title'], 'quote': _found(p)[n][0], 'explanation': GM.BY_ID[n]['note'], 'status': st, 'label': STATUS_LABEL[st]})
    return {'id': p['id'], 'title': p['title'], 'title_en': p.get('title_en', ''), 'summary_zh': p.get('summary_zh', ''),
            'level': cefr(p), 'theme': p['theme'], 'theme_label': THEMES.get(p['theme'], ''), 'genre': p.get('genre', ''),
            'source': p.get('source', ''), 'daily_day': p.get('daily_day'), 'featured': featured(p),
            'sentences': sentences(text), 'original_level': cefr(p), 'original': sentences(body) if variant else None,
            'variant': variant, 'vocabulary': list(vocab.values()), 'expressions': p.get('expressions', []), 'hard': hard, 'questions': qs,
            'notes': notes, 'task': _task(p, level), 'steps': sorted(done, key=STEPS.index), 'dictation_index': p.get('dictation_index'),
            'provenance': [{'title': s['title'], 'url': s['url']} for s in (p.get('provenance') or {}).get('sources', [])][:5],
            'origin': origin(p),
            'mine': __import__('vocab_service').mine_in_text(c, uid, text),
            'preread': __import__('vocab_service').preread(c, uid, hard),
            'speaking_task': p.get('speaking', ''), 'writing_task': p.get('writing', ''), 'imported': bool(p.get('imported')),
            'user_level': level, 'can_variant': level != cefr(p) and not variant,
            'audio': {'voices': audio_index()[0].get(p['id'], []), 'version': audio_index()[1]}, 'series': _series_nav(c, p),
            **({'answers': [{'answer': q['answer'], 'evidence': q.get('evidence', '')} for q in p.get('questions', [])]} if offline else {})}, 200


def check(c, uid, data):
    row = _pack_row(c, uid, str(data.get('pack', '')))
    if not row:
        return {'error': '材料不存在'}, 404
    p = json.loads(row['content'])
    i, choice = data.get('index'), data.get('choice')
    qs = p.get('questions', [])
    if type(i) is not int or not 0 <= i < len(qs) or type(choice) is not int or not 0 <= choice < len(qs[i]['options']):
        return {'error': '题目或选项不正确'}, 400
    q = qs[i]
    correct = choice == q['answer']
    if uid:
        import skills_service as sk
        __import__('event_service').record(c, uid, 'skill:reading', f"next:{p['id']}:q{i}", 'next-check', p['id'], p['id'],
                                           int(correct), 0, 'rule', {'choice': choice})
        sk.log(c, uid, 'reading', 'question', 1.0 if correct else 0.0, cefr(p), p['id'], commit=False)
        if not correct:
            sk.add_mistake(c, uid, 'question', q['prompt'], f"q:{p['id']}:{i}", q.get('evidence', ''), '', 'reading', pack=p['id'],
                           extra={'options': q['options'], 'answer': q['answer'], 'evidence': q.get('evidence', '')}, commit=False)
        if i == len(qs) - 1:
            mark(c, uid, p['id'], 'check', commit=False)
        c.commit()
    return {'correct': correct, 'answer': q['answer'], 'evidence': q.get('evidence', '')}, 200


def mark(c, uid, pid, step, commit=True):
    if step not in STEPS:
        raise ValueError('步骤不正确')
    c.execute('INSERT OR IGNORE INTO next_progress VALUES(?,?,?,?)', (uid, pid, step, time.time()))  # the first time only
    __import__('progress_service').log_step(c, uid, pid, step)  # and every day it is done (a text studied again)
    if commit:
        c.commit()


# ---------- expression bank & review ----------

def _norm(text):
    return ' '.join(re.sub(r"[^\w\s'-]", ' ', text.lower()).split())


def save_card(c, uid, data):
    text = _text(data.get('text', ''), 160, 1)
    if not WORD.search(text):
        return {'error': '请收藏英文单词、短语或句子'}, 400
    meaning = _text(data.get('meaning', '') or '', 300)
    context = _text(data.get('context', '') or '', 600)
    pack = data.get('pack') if isinstance(data.get('pack'), str) and len(data.get('pack')) <= 80 else None
    words = len(WORD.findall(text))
    kind = 'word' if words == 1 else 'sentence' if words >= 7 else 'phrase'
    if not meaning and kind == 'word':
        hit = lookup(text)
        meaning = hit['meaning'][:300] if hit else ''
    norm = _norm(text)
    now = time.time()
    existing = c.execute('SELECT id FROM next_cards WHERE user_id=? AND norm=?', (uid, norm)).fetchone()
    if existing:
        c.execute('UPDATE next_cards SET meaning=CASE WHEN ?!="" THEN ? ELSE meaning END, context=CASE WHEN ?!="" THEN ? ELSE context END WHERE id=?',
                  (meaning, meaning, context, context, existing['id']))
        c.commit()
        return {'card': card(c, uid, existing['id']), 'existing': True}, 200
    cur = c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due) VALUES(?,?,?,?,?,?,?,?,?)',
                    (uid, text, norm, meaning, context, pack, kind, now, now))
    c.commit()
    return {'card': card(c, uid, cur.lastrowid), 'existing': False}, 200


def card(c, uid, cid):
    import vocab_service
    r = c.execute('SELECT * FROM next_cards WHERE id=? AND user_id=?', (cid, uid)).fetchone()
    return vocab_service.card_out(r) if r else None


def cards(c, uid, q='', page=1, per=30, f=''):
    rows = c.execute('SELECT * FROM next_cards WHERE user_id=? ORDER BY created DESC', (uid,)).fetchall()
    if f == 'mistake':
        rows = [r for r in rows if r['source'] == 'mistake']
    elif f in ('word', 'phrase'):
        rows = [r for r in rows if r['source'] != 'mistake' and (r['kind'] == 'word') == (f == 'word')]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r['text'].lower() or ql in r['meaning'].lower() or ql in r['context'].lower()]
    page = max(1, page)
    import vocab_service
    now = time.time()
    return {'total': len(rows), 'page': page, 'per': per, 'items': [vocab_service.card_out(r, now) for r in rows[(page - 1) * per: page * per]]}


def delete_card(c, uid, data):
    n = c.execute('DELETE FROM next_cards WHERE id=? AND user_id=?', (int(data['id']), uid)).rowcount
    if n:
        c.execute('UPDATE next_reviews SET card=-card WHERE card=? AND user_id=?', (int(data['id']), uid))
    c.commit()
    return ({'ok': True}, 200) if n else ({'error': '记录不存在'}, 404)


# ---------- AI ----------

def _level_voice(level):
    return {'A2': '讲解全部用简单的中文，例句用最常见的词。',
            'B1': '讲解用中文，必要时给出英文关键词。',
            'B2': '讲解以中文为主，可以夹带英文术语，关注语气和搭配。',
            'C1': '讲解可以中英结合，关注措辞的细微差别、语域和风格。'}[level]


def _node_list(c):
    return '；'.join(f"{k}={v['title']}" for k, v in nodes_meta(c).items())


def kept_own_sentence(answer, corrected):
    """Whether corrected is the learner's own sentence put right (at least half of its words kept, and not a much
    longer text), not another sentence written in its place, such as one on the lesson's topic in the lesson's pattern."""
    from collections import Counter
    a, b = [w.lower() for w in WORD.findall(answer or '')], [w.lower() for w in WORD.findall(corrected or '')]
    if not a or not b:
        return False
    return sum((Counter(a) & Counter(b)).values()) * 2 >= len(a) and len(b) <= 2 * len(a) + 4


def rewrite(c, uid, data):
    """仿写: the learner's own sentence marked. corrected is that sentence put right with the smallest change, never
    another sentence; better ways to say the same thing go in versions, in the learner's own words and topic; using
    the lesson's pattern is suggested in the summary, not done for them. An answer whose corrected is another sentence
    is asked for once more; if it is still not the learner's sentence, it is not shown (ai_eval.py checks this)."""
    from lab_service import run_job, mtext as clean_text, parse  # model output: cut, not refused, when long
    from chat_service import request_model
    row = _pack_row(c, uid, str(data.get('pack', '')))
    if not row:
        return {'error': '材料不存在'}, 404
    p = json.loads(row['content'])
    level = (profile(c, uid) or {}).get('level') or 'B1'
    answer = _text(data.get('text', ''), 600, 2)
    if len(WORD.findall(answer)) < 2:
        return {'error': '请用英文写至少一个短句'}, 400
    task = _task(p, level)
    valid_nodes = set(nodes_meta(c))
    targets = [n for n in p.get('grammar', []) if n in valid_nodes]
    spec = {'pack': p['id'], 'text': answer, 'level': level}
    learning = {r['norm']: r for r in c.execute("SELECT * FROM next_cards WHERE user_id=? AND kind='word' AND known=0", (uid,))}
    studied = []  # words being learned that the learner chose to use: judging them is a real test of the word
    for w in WORD.findall(answer):
        hit = lookup(w)
        if hit and hit['lemma'] in learning and hit['lemma'] not in studied:
            studied.append(hit['lemma'])
    studied = studied[:6]
    # The fixed part first (rules, the node list, the answer's shape), the learner's level after it: the same opening
    # for every learner, which a model's prompt cache can serve cheaply (百炼's implicit cache needs 1024 tokens or more).
    system = ('你是一位耐心、专业的英语写作教练。'
              '先肯定写得好的地方，再改错，最后给出更好的说法。不要编造学习者没写的内容。'
              '最重要的一条：corrected 只能是学习者自己这句话的最小改动，只改语法、用词、拼写和标点上的错误，保留原来的意思、结构和话题；'
              '绝不能换成另一句话，也不要为了套用本课的句型或话题去改写。没有错误时 verdict 写 natural，corrected 原样返回，changes 为空数组。'
              'versions 是同一个意思的更好说法：用学习者自己的意思和话题来写，不要换成课文的话题；本课的目标表达能自然用上时，可以在其中一个版本里用。'
              '学习者没有用上本课的目标表达时，在 summary 里用中文提一句可以怎么用，不要替他改写原句。只输出 JSON。'
              '\n全部语法节点（id=名称）：' + _node_list(c) +
              '\n\n输出 JSON，结构：{"verdict":"natural|minor|rewrite","summary":"一句话总评（中文，先说优点）",'
              '"corrected":"学习者原句的最小改动：只改错误，保留原意和话题，不写新句子（若已正确则原样返回）",'
              '"changes":[{"from":"原文片段","to":"改后片段","why":"为什么（简短）","node":"相关语法节点 id，没有就写 null"}],'
              '"versions":[{"label":"更自然","text":"同一个意思的更自然说法","why":"和原句的差别"},{"label":"更正式","text":"...","why":"..."},{"label":"更简洁","text":"...","why":"..."}],'
              '"used_well":["学习者用对了的语法节点 id"],'
              '"keep":{"text":"最值得收藏的一个英文表达（短语）","meaning":"中文意思"}}。changes 最多 5 条，没有错误就给空数组。'
              '\n\n学习者的水平是 ' + level + '（' + LEVELS[level]['label'] + '）。' + _level_voice(level))
    user = ('学习任务（供参考，用来看学习者有没有用上目标表达；不要据此改写学习者的句子）：' + task['prompt'] + ('\n参考句：' + task['model'] if task['model'] else '') +
            '\n材料主题：' + p['title'] + '\n本篇练习的语法节点：' + (', '.join(targets) or '无') +
            '\n学习者写的英文：\n' + answer +
            ('\n\n学习者正在背这些单词，并在上面的句子里用到了：' + '、'.join(studied) + '。请在 JSON 里再加一个字段 '
             '"word_use":[{"word":"单词原形","ok":true,"note":"一句中文：用法对在哪里，或错在哪里、应该怎么用"}]，逐个判断词义和搭配是否用对。' if studied else ''))

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        out = {'verdict': raw.get('verdict') if raw.get('verdict') in ('natural', 'minor', 'rewrite') else 'minor',
               'summary': clean_text(raw.get('summary'), 1, 300, 'summary_empty'), 'corrected': clean_text(raw.get('corrected'), 1, 900, 'corrected_empty'),
               'changes': [], 'versions': [], 'keep': None, 'used_well': []}
        if not kept_own_sentence(answer, out['corrected']):
            raise ValueError('corrected is another sentence')  # asked for once more already (invoke): not shown
        for ch in (raw.get('changes') or [])[:5]:
            if isinstance(ch, dict) and ch.get('to'):
                n = ch.get('node') if ch.get('node') in valid_nodes else None
                out['changes'].append({'from': clean_text(ch.get('from') or '—', 1, 200), 'to': clean_text(ch['to'], 1, 200),
                                       'why': clean_text(ch.get('why') or '—', 1, 300), 'node': n})
        for v in (raw.get('versions') or [])[:3]:
            if isinstance(v, dict) and v.get('text'):
                out['versions'].append({'label': clean_text(v.get('label') or '参考', 1, 20), 'text': clean_text(v['text'], 1, 900), 'why': clean_text(v.get('why') or '', 0, 300)})
        if not out['versions']:
            raise ValueError('no versions')
        if WORD.findall(out['corrected'].lower()) == WORD.findall(answer.lower()) and out['verdict'] != 'natural':
            out['verdict'] = 'minor' if out['changes'] else 'natural'  # nothing was changed: it was right
        out['used_well'] = [n for n in (raw.get('used_well') or []) if n in valid_nodes][:3]
        k = raw.get('keep')
        if isinstance(k, dict) and isinstance(k.get('text'), str) and WORD.search(k['text']) and len(k['text']) <= 160:
            out['keep'] = {'text': k['text'].strip(), 'meaning': str(k.get('meaning') or '')[:200]}
        out['word_use'] = []
        for u in (raw.get('word_use') or []) if studied else []:
            if isinstance(u, dict) and u.get('word') in studied and isinstance(u.get('ok'), bool):
                out['word_use'].append({'word': u['word'], 'ok': u['ok'], 'note': clean_text(u.get('note') or '', 0, 300)})
        return out

    msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]

    def invoke():
        # An answer whose corrected is another sentence (one on the lesson's topic, in its pattern) is asked for once more.
        reply, reason = request_model(msgs)
        try:
            raw = parse(reply)
        except ValueError:
            return reply, reason  # not JSON: reported as before
        fixed = raw.get('corrected') if isinstance(raw, dict) else None
        if not isinstance(fixed, str) or kept_own_sentence(answer, fixed):
            return reply, reason
        return request_model(msgs + [{'role': 'assistant', 'content': reply}, {'role': 'user', 'content':
            '这次的 corrected 不是学习者原句的最小改动，而是另一句话：「' + fixed[:200] + '」。请重新输出完整的 JSON：corrected 只改学习者原句里的错误，'
            '保留原意和话题（没有错误就原样返回，verdict 写 natural）；更好的说法只放进 versions，也用学习者自己的意思。'}])

    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-rewrite', p['id'], 'writing', spec, invoke, convert, mark_replay=True)
    if status == 200:
        r = result['result']
        rid = str(data.get('request_id', ''))
        meta = nodes_meta(c)
        if not result.get('replayed') and not c.execute('SELECT 1 FROM next_node_notes WHERE user_id=? AND detail LIKE ?', (uid, rid + '%')).fetchone():
            now = time.time()
            for ch in r['changes']:
                if ch['node']:
                    c.execute('INSERT INTO next_node_notes(user_id,node,pack,kind,detail,created) VALUES(?,?,?,?,?,?)',
                              (uid, ch['node'], p['id'], 'flag', rid + '|' + ch['from'] + ' → ' + ch['to'], now))
            flagged = {ch['node'] for ch in r['changes'] if ch['node']}
            for n in r['used_well']:
                if n not in flagged:
                    c.execute('INSERT INTO next_node_notes(user_id,node,pack,kind,detail,created) VALUES(?,?,?,?,?,?)',
                              (uid, n, p['id'], 'clean', rid + '|', now))
            __import__('vocab_service').record_use(c, uid, r.get('word_use') or [], now)
            import skills_service as sk
            sk.log(c, uid, 'writing', 'rewrite', {'natural': 1.0, 'minor': 0.7, 'rewrite': 0.35}[r['verdict']], level, p['id'], commit=False)
            sk.mistakes_from_changes(c, uid, r['changes'], answer, 'writing', p['id'])
        for ch in r['changes']:
            ch['node_title'] = meta.get(ch['node'], {}).get('title') if ch['node'] else None
        r['used_well'] = [n if isinstance(n, dict) else {'id': n, 'title': meta.get(n, {}).get('title', n)} for n in r['used_well']]
        mark(c, uid, p['id'], 'output')
    return result, status


def _words(text):
    return [w.lower() for w in WORD.findall(text)]


def compare_words(target, heard):
    """Word-level alignment of what was heard against the sentence: [{'w': word, 'ok': bool}] for each target word."""
    t, h = _words(target), _words(heard)
    n, m = len(t), len(h)
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            lcs[i][j] = lcs[i + 1][j + 1] + 1 if t[i] == h[j] else max(lcs[i + 1][j], lcs[i][j + 1])
    out, i, j = [], 0, 0
    while i < n:
        if j < m and t[i] == h[j]:
            out.append({'w': t[i], 'ok': True}); i += 1; j += 1
        elif j < m and lcs[i][j + 1] >= lcs[i + 1][j]:
            j += 1
        else:
            out.append({'w': t[i], 'ok': False}); i += 1
    return out


PRON_WEIGHTS = {'accuracy': 0.5, 'fluency': 0.25, 'complete': 0.25}


def pron_score(r):
    """跟读 score of one sentence, 0–100: accuracy and fluency are the AI's estimate from the recording; completeness is
    counted here (the words of the sentence found in what it heard). None when the AI gave no estimate or heard none of
    the sentence (then there is nothing to score)."""
    if r.get('accuracy') is None or not r.get('words') or not r.get('matched'):
        return None
    complete = round(100 * r['matched'] / len(r['words']))
    parts = {'accuracy': r['accuracy'], 'fluency': r.get('fluency_score') if r.get('fluency_score') is not None else 72, 'complete': complete}
    return {**parts, 'total': round(sum(PRON_WEIGHTS[k] * v for k, v in parts.items()))}


def shadow(c, uid, data):
    """Shadowing: the learner reads one sentence aloud; AI transcribes it and points out what to fix."""
    from lab_service import run_job, mtext as clean_text, audio_enabled, Shape, mnum  # model output: lenient
    from chat_service import request_model
    from audio_validation import validate_audio
    if not audio_enabled():
        return {'error': 'AI 听录音暂未开启，可以先用「对比回放」自己听'}, 503
    quote = __import__('daily_line').sentence_of(data)  # 今日好句 (r27): a public-domain line, by its id
    if quote:
        sentence, pid, i, lvl = quote, None, str(data.get('quote')), None
    else:
        row = _pack_row(c, uid, str(data.get('pack', '')))
        if not row:
            return {'error': '材料不存在'}, 404
        p = json.loads(row['content'])
        sents = sentences(p['body'])
        i = data.get('i')
        if not isinstance(i, int) or not 0 <= i < len(sents):
            return {'error': '句子不存在'}, 400
        sentence = re.sub(r'^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+', '', sents[i])  # dialogue labels are not read aloud
        pid, lvl = p['id'], cefr(p)
    audio = data.get('audio')
    raw_audio = validate_audio(audio)
    level = (profile(c, uid) or {}).get('level') or 'B1'
    import sounds as snd
    sets = '；'.join(f"{x['id']}（{x['title']}）" for x in snd.SETS)
    system = ('你是英语口语老师，正在听一位中国学习者（' + level + '）跟读一句英文。先忠实转写你实际听到的英文，听不清的部分写 [听不清]，'
              '不要按原句补全。然后只根据录音本身估计发音：accuracy 是发音准确度（0–100：90 以上几乎每个音都准；75–89 个别音不准、不影响听懂；'
              '60–74 有几处明显错音、要仔细听；40–59 很多词读错或含糊；40 以下大部分听不清），fluency_score 是流利度（0–100：语速自然、'
              '停顿在意群之间为高；一词一顿、反复重来为低）。口音本身不扣分，只看别人能不能听清。漏读的词不算进准确度（完整度另算）。'
              '再找出最需要练的音（最多 3 个，只在有把握时写）和其他要注意的地方（漏读、重音、连读、停顿）。只输出 JSON。')
    user = ('原句：' + sentence + '\n\n发音入门里能练的音（set 填其中一个 id，都不合适就填空字符串）：' + sets +
            '\n\n输出 JSON：{"transcript":"你听到的英文","accuracy":0-100,"fluency_score":0-100,"fluency":"smooth|ok|choppy",'
            '"sounds":[{"sound":"音标，如 /v/","word":"原句中读错这个音的词","note":"中文：读成了什么、怎么改","set":"发音入门的 id 或空字符串"}],'
            '"issues":[{"word":"原句中的词或短语","note":"中文：问题和改法"}],"tip":"一句最重要的中文建议"}。'
            'sounds 最多 3 条，issues 最多 3 条，读得好就给空数组。')

    def score_of(v):  # 85, "85", "85分", "85%", "8.5/10"
        try:
            return int(round(mnum(v, 0, 100)))
        except Shape:
            return None

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        flu = raw.get('fluency') if raw.get('fluency') in ('smooth', 'ok', 'choppy') else 'ok'
        out = {'transcript': clean_text(raw.get('transcript') or '', 0, 600), 'tip': clean_text(raw.get('tip') or '', 0, 300),
               'fluency': flu, 'accuracy': score_of(raw.get('accuracy')), 'fluency_score': score_of(raw.get('fluency_score')), 'issues': [], 'sounds': []}
        if out['fluency_score'] is None and out['accuracy'] is not None:
            out['fluency_score'] = {'smooth': 88, 'ok': 72, 'choppy': 50}[flu]
        said = set(_words(sentence))
        titles = {x['id']: x['title'] for x in snd.SETS}
        for it in (raw.get('sounds') or [])[:3]:
            if isinstance(it, dict) and it.get('sound') and it.get('note') and _words(str(it.get('word') or ''))[:1] and set(_words(str(it['word']))) <= said:
                sid = it.get('set') if it.get('set') in titles else ''
                out['sounds'].append({'sound': clean_text(it['sound'], 1, 16), 'word': clean_text(it['word'], 1, 40), 'note': clean_text(it['note'], 1, 200),
                                      'set': sid, 'set_title': titles.get(sid, '')})
        for it in (raw.get('issues') or [])[:3]:
            if isinstance(it, dict) and it.get('word') and it.get('note'):
                out['issues'].append({'word': clean_text(it['word'], 1, 80), 'note': clean_text(it['note'], 1, 300)})
        return out

    spec = {'pack': pid or 'daily-line', 'i': i, 'audio_sha256': hashlib.sha256(raw_audio).hexdigest()}
    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-shadow', pid or 'daily-line', 'speaking', spec,
                             lambda: request_model([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], audio=audio), convert, mark_replay=True)
    if status == 200:
        r = result['result']
        r['words'] = compare_words(sentence, r['transcript'])
        r['matched'] = sum(1 for w in r['words'] if w['ok'])
        r['sentence'] = sentence
        r['score'] = pron_score(r)
        if result.get('replayed'):
            return result, status
        import skills_service as sk
        sk.log(c, uid, 'speaking', 'shadow', r['matched'] / max(1, len(r['words'])), lvl, pid, commit=False)
        if r['score']:
            sk.log(c, uid, 'pronunciation', 'shadow-pron', r['score']['total'] / 100, lvl, pid, commit=False)
        for it in ([{'word': x['word'], 'note': x['sound'] + '：' + x['note']} for x in r.get('sounds') or []] + r['issues'])[:2]:
            sk.add_mistake(c, uid, 'sound', it['word'], 'sound:' + _norm(it['word']), it['note'], sentence, 'pronunciation', pack=pid, commit=False)
        c.commit()
    return result, status


def explain(c, uid, data):
    """AI explanation of one sentence, grounded in the material's knowledge nodes. Cached site-wide per level."""
    from lab_service import run_job, text as clean_text
    from chat_service import request_model
    row = _pack_row(c, uid, str(data.get('pack', '')))
    if not row:
        return {'error': '材料不存在'}, 404
    p = json.loads(row['content'])
    level = (profile(c, uid) or {}).get('level') or 'B1'
    sentence = _text(data.get('sentence', ''), 600, 2)
    variant = c.execute('SELECT body FROM next_variants WHERE pack=? AND level=?', (p['id'], level)).fetchone()
    if sentence not in p['body'] and not (variant and sentence in variant['body']):
        return {'error': '只能讲解材料里的句子'}, 400
    meta = nodes_meta(c)
    cached = c.execute('SELECT result FROM next_explains WHERE pack=? AND sentence=? AND level=?', (p['id'], sentence, level)).fetchone()
    if cached:
        return {'result': json.loads(cached['result']), 'cached': True}, 200
    hints = [f"{k['node']}（{meta.get(k['node'], {}).get('title', '')}）：{k['quote']}" for k in p.get('knowledge', []) if k.get('quote') and k['quote'] in sentence]
    system = ('你是英语老师。讲解要短、准、能模仿。只输出 JSON。'
              '\n可用语法节点（id=名称）：' + _node_list(c) +
              '\n\n输出 JSON：{"translation":"自然的中文翻译","structure":"一句话拆解句子主干和修饰成分",'
              '"points":[{"text":"句中原样片段","note":"讲解（为什么这样用、语气、搭配）","node":"相关语法节点 id 或 null"}],'
              '"pattern":{"frame":"可替换的句型框架，如 not A so much as B","example":"用这个框架造的一个新句子"}}。points 2–4 条。'
              '\n\n学习者水平 ' + level + '（' + LEVELS[level]['label'] + '）。' + _level_voice(level))
    user = ('材料：' + p['title'] + '\n要讲解的句子：' + sentence + ('\n这句关联的语法节点：' + '；'.join(hints) if hints else ''))

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        out = {'translation': clean_text(raw.get('translation'), 1, 400), 'structure': clean_text(raw.get('structure') or '', 0, 400), 'points': [], 'pattern': None}
        for pt in (raw.get('points') or [])[:4]:
            if isinstance(pt, dict) and pt.get('text') and pt.get('note'):
                n = pt.get('node') if pt.get('node') in meta else None
                out['points'].append({'text': clean_text(pt['text'], 1, 200), 'note': clean_text(pt['note'], 1, 400), 'node': n,
                                      'node_title': meta[n]['title'] if n else None})
        if not out['points']:
            raise ValueError('no points')
        pt = raw.get('pattern')
        if isinstance(pt, dict) and pt.get('frame'):
            out['pattern'] = {'frame': clean_text(pt['frame'], 1, 160), 'example': clean_text(pt.get('example') or '', 0, 300)}
        return out

    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-explain', p['id'], 'reading', {'pack': p['id'], 'sentence': sentence, 'level': level},
                             lambda: request_model([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]), convert)
    if status != 200:
        return result, status
    c.execute('INSERT OR IGNORE INTO next_explains VALUES(?,?,?,?,?)', (p['id'], sentence, level, json.dumps(result['result'], ensure_ascii=False), time.time()))
    c.commit()
    return {'result': result['result'], 'cached': False, 'remaining': result.get('remaining')}, 200


def variant(c, uid, data):
    from lab_service import run_job
    from chat_service import request_model
    row = _pack_row(c, uid, str(data.get('pack', '')))
    level = data.get('level')
    if not row or level not in LEVELS:
        return {'error': '材料或难度不正确'}, 400
    p = json.loads(row['content'])
    cached = c.execute('SELECT body, notes FROM next_variants WHERE pack=? AND level=?', (p['id'], level)).fetchone()
    if cached:
        return {'level': level, 'body': cached['body'], 'notes': json.loads(cached['notes']), 'cached': True}, 200
    n = len(p['body'].split())
    lo, hi = {'A2': (max(40, n * 0.6), n * 1.0), 'B1': (n * 0.8, n * 1.2), 'B2': (n * 0.9, n * 1.4), 'C1': (n * 1.0, n * 1.6)}[level]
    lo, hi = int(max(35, lo)), int(min(420, max(hi, lo + 30)))
    system = '你是英语分级读物编辑。只改写语言难度，不增加、不删除事实、人物、数字和观点。只输出 JSON。'
    user = (f'把下面的英文材料改写成 CEFR {level} 难度（{LEVELS[level]["label"]}），{lo}–{hi} 个英文单词，保持段落为一段。'
            + {'A2': '使用最常见的词和短句，避免从句堆叠。', 'B1': '句子长短结合，常见搭配为主。',
               'B2': '可以使用从句、被动和更精确的词。', 'C1': '使用地道、精确、有层次的表达和多样句式，像高质量媒体文章。'}[level]
            + '\n原文：\n' + p['body'] + '\n\n输出 JSON：{"body":"改写后的英文正文","notes":[{"text":"新出现的一个值得学的表达","meaning":"中文意思"}]}，notes 最多 4 条。')

    def convert(raw):
        body = raw.get('body') if isinstance(raw, dict) else None
        if not isinstance(body, str):
            raise ValueError('no body')
        body = ' '.join(body.split())
        words = len(body.split())
        if not (lo * 0.7 <= words <= hi * 1.3) or len(sentences(body)) < 2:
            raise ValueError('length')
        notes = [{'text': str(x.get('text'))[:120], 'meaning': str(x.get('meaning') or '')[:120]}
                 for x in (raw.get('notes') or [])[:4] if isinstance(x, dict) and x.get('text')]
        return {'body': body, 'notes': notes}

    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-variant', p['id'], 'reading', {'pack': p['id'], 'level': level},
                             lambda: request_model([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]), convert)
    if status != 200:
        return result, status
    v = result['result']
    c.execute('INSERT OR IGNORE INTO next_variants VALUES(?,?,?,?,?)', (p['id'], level, v['body'], json.dumps(v['notes'], ensure_ascii=False), time.time()))
    c.commit()
    return {'level': level, 'body': v['body'], 'notes': v['notes'], 'cached': False, 'remaining': result.get('remaining')}, 200


# ---------- routing ----------

def meta():
    return {'levels': [{'id': k, 'label': v['label'], 'desc': v['desc'], 'sample': v['sample']} for k, v in LEVELS.items()],
            'goals': [{'id': k, 'label': v} for k, v in GOALS.items()], 'themes': [{'id': k, 'label': v} for k, v in THEMES.items()],
            'minutes': list(MINUTES), 'voices': [{'id': k, 'label': v} for k, v in VOICES.items()],
            'goal_hints': GOAL_HINT, 'targets': [{'id': k, 'label': v} for k, v in TARGETS.items()], 'target_for': TARGET_FOR,
            'exams': [{'id': k, 'short': __import__('exam_sprint').short(k), 'book_title': __import__('vocab_service').book_title(k)}
                      for k in __import__('exam_sprint').available()]}


def get(c, uid, path, q):
    one = lambda k, d='': (q.get(k) or [d])[0]
    if path.startswith('/api/next/vocab') or path == '/api/next/review':
        if not uid and path != '/api/next/vocab/test':
            return {'error': '请先登录'}, 401
        return __import__('vocab_service').get(c, uid, path, q)
    if path == '/api/next/sounds':
        return __import__('sounds').listing(), 200
    if path in ('/api/next/ability', '/api/next/report', '/api/next/import'):
        if not uid:
            return {'error': '请先登录'}, 401
        return (__import__('skills_service') if path != '/api/next/import' else __import__('import_service')).get(c, uid, path, q)
    if path in ('/api/next/class', '/api/next/class/teach'):
        # 班级试用 (class_service.py): the class this learner is in; for its teacher, numbers for the whole class only
        if not uid:
            return {'error': '请先登录'}, 401
        cs = __import__('class_service')
        return cs.mine(c, uid) if path == '/api/next/class' else cs.teach(c, uid, one('id'))
    if path == '/api/next/guide':
        return __import__('user_guide').api(), 200
    if path == '/api/next/meta':
        return meta(), 200
    if path == '/api/next/home':
        return home(c, uid, one('level'), one('themes').split(',') if one('themes') else None), 200
    if path == '/api/next/library':
        return library(c, uid, one('level') or None, one('theme') or None, int(one('page', '1') or 1), featured_only=one('featured') == '1'), 200
    if path == '/api/next/material':
        return material(c, uid, one('id'), one('level'), one('offline') == '1')
    if path == '/api/next/graph':
        return graph(c, uid, one('level')), 200
    if path == '/api/next/node':
        return node(c, uid, one('id'), one('level'))
    if path == '/api/next/placement':
        return GB.placement_items(c), 200
    if path == '/api/next/series':
        return series(c, uid, one('id'))
    if path == '/api/next/easy':
        return __import__('easy_reading').listing(c, uid, one('level') or None)
    if path == '/api/next/words/confuse':
        WL = __import__('word_links')
        prog = WL.progress(c, uid)
        return {'groups': [{**g, **prog.get(g['id'], {'right': 0, 'tries': 0})} for g in WL.listing()]}, 200
    if path == '/api/next/words/confuse/round':
        WL = __import__('word_links')
        groups = [g for g in (one('groups') or '').split(',') if g in WL.GROUPS][:6]
        if not groups:
            return {'error': '没有这一组'}, 404
        return {'items': WL.round_of(groups, per=3 if len(groups) == 1 else 2), 'groups': [{'id': g, 'words': WL.GROUPS[g][1], 'how': WL.GROUPS[g][2]} for g in groups]}, 200
    if path == '/api/next/speak':
        return __import__('scenarios').listing(c, uid, (profile(c, uid) or {}).get('level') or one('level') or None), 200
    if path == '/api/next/ielts':
        return __import__('ielts_speaking').listing(c, uid), 200
    if path == '/api/next/mix':
        n = one('n')
        return GB.mix(c, uid, pair=one('pair') or None, topic=one('topic') or None, level=one('level') or None, exam=one('exam') or None,
                      most=int(n) if n.isdigit() else None)
    if path == '/api/next/exam':
        return __import__('exam_service').overview(c, uid)
    if path == '/api/next/exam/type':
        return __import__('exam_sprint').get(c, uid, path, q)
    if path == '/api/next/lookup':
        w = one('w')[:40]
        if not WORD.fullmatch(w or ''):
            return {'error': '只能查英文单词'}, 400
        hit = lookup(w)
        if hit:  # words Chinese speakers mix up with this one, and its recorded pronunciation (a copy: the cached entry stays as it is)
            hit = {**hit, 'confusable': __import__('word_links').group_of(hit['lemma']) or __import__('word_links').group_of(w),
                   'audio': __import__('vocab_service').word_audio(hit['lemma'])}
        return ({'entry': hit} if hit else {'entry': None, 'query': w}), 200
    if not uid:
        return ({'error': '请先登录'}, 401) if path.startswith('/api/next/') else None
    if path == '/api/next/cards':
        return cards(c, uid, one('q')[:80], int(one('page', '1') or 1), f=one('f')), 200
    if path == '/api/next/stats':
        return stats(c, uid), 200
    if path in ('/api/next/week', '/api/next/text-summary', '/api/next/weekly-mail'):
        return __import__('progress_service').get(c, uid, path, q)
    if path == '/api/next/growth':
        return __import__('growth_report').month(c, uid, one('month') or None)
    if path == '/api/next/radar':
        return __import__('ability_radar').radar(c, uid), 200
    if path == '/api/next/assess/test':
        return __import__('ability_radar').comprehension_test(c, uid, one('kind'))
    if path == '/api/next/assess/task':
        return __import__('ability_radar').task(c, uid, one('kind'))
    if path == '/api/next/exam/goal':
        return __import__('exam_sprint').get(c, uid, path, q)
    return None


def tap(c, data):
    """One tap on a counted entry point (flow_admin.TAP_LABEL): per day and key only, nothing about who."""
    key = str(data.get('k', ''))[:40]
    if key not in __import__('flow_admin').TAP_LABEL:
        return {'error': '未知的入口'}, 400
    day = datetime.datetime.now(TZ).date().isoformat()
    c.execute('INSERT INTO ui_taps(day, key, n) VALUES(?,?,1) ON CONFLICT(day, key) DO UPDATE SET n=n+1 WHERE n<20000', (day, key))
    c.commit()
    return {'ok': True}, 200


def post_public(c, uid, path, data):
    """Routes open to guests (no state change for guests)."""
    if path == '/api/next/tts':  # the server voice: guests get stored sentences, learners may make new ones (tts_service)
        return __import__('tts_service').post(c, uid, data)
    if path == '/api/next/tts/have':  # which sentences of an article are made already (伴读: 「正在准备朗读 12/30 句」)
        return __import__('tts_service').have(c, uid, data)
    if path == '/api/next/tap':
        return tap(c, data)
    if path == '/api/next/check':
        return check(c, uid, data)
    if path == '/api/next/vocab/test':
        return __import__('vocab_service').score_test(c, uid, data)
    if path == '/api/next/node/answer':
        return node_answer(c, uid, data)
    if path == '/api/next/placement':
        return GB.placement_score(c, uid, data)
    if path == '/api/next/easy/done':
        return __import__('easy_reading').done(c, uid, data)
    if path == '/api/next/words/confuse/answer':
        return __import__('word_links').answer(c, uid, data)
    if path == '/api/next/exam/paper':
        return __import__('exam_service').paper(c, uid, data.get('exam'))
    if path == '/api/next/exam/submit':
        return __import__('exam_service').submit(c, uid, data)
    if path == '/api/next/exam/type':
        return __import__('exam_sprint').post_public(c, uid, path, data)
    if path == '/api/next/weekly-mail/off':  # the link in the Sunday mail: no sign-in, its token stands for the account
        return __import__('progress_service').post_public(c, path, data)
    return None


AI_PATHS = ('/api/next/assess/speaking', '/api/next/assess/writing', '/api/next/rewrite', '/api/next/variant', '/api/next/explain', '/api/next/shadow', '/api/next/vocab/examples', '/api/next/import/enrich',
            '/api/next/retell', '/api/next/dialog', '/api/next/essay', '/api/next/translate/source', '/api/next/translate', '/api/next/say',
            '/api/next/ielts')


def post(c, uid, path, data):
    if path in ('/api/next/class/create', '/api/next/class/rename'):
        ts = __import__('teacher_service')  # 老师账号: its own classes (teacher_service.py)
        return (ts.create_class if path.endswith('/create') else ts.rename_class)(c, uid, data)
    if path in ('/api/next/class/find', '/api/next/class/join', '/api/next/class/leave'):
        cs = __import__('class_service')  # 班级试用: join of one's own accord with an invite code, leave at any time
        return cs.leave(c, uid) if path.endswith('/leave') else (cs.find if path.endswith('/find') else cs.join)(c, uid, data)
    if path == '/api/next/profile':
        return save_profile(c, uid, data)
    if path == '/api/next/habit':
        return set_weekly_goal(c, uid, data)
    if path == '/api/next/exam/goal':
        return __import__('exam_sprint').set_goal(c, uid, data)
    if path == '/api/next/weekly-mail':
        return __import__('progress_service').post(c, uid, path, data)
    if path == '/api/next/relisten':
        return __import__('relisten_service').record(c, uid, data)
    if path == '/api/next/radar/goals':
        return __import__('ability_radar').set_goals(c, uid, data)
    if path == '/api/next/assess/comprehension':
        return __import__('ability_radar').comprehension_score(c, uid, data)
    if path in ('/api/next/assess/speaking', '/api/next/assess/writing'):
        return __import__('ability_radar').judged(c, uid, path.rsplit('/', 1)[1], data)
    if path == '/api/next/voice':
        return set_voice(c, uid, data)
    if path == '/api/next/progress':
        if not _pack_row(c, uid, str(data.get('pack', ''))):
            return {'error': '材料不存在'}, 404
        mark(c, uid, data['pack'], data.get('step'))
        return {'ok': True}, 200
    if path == '/api/next/cards':
        return save_card(c, uid, data)
    if path == '/api/next/cards/delete':
        return delete_card(c, uid, data)
    if path.startswith('/api/next/vocab/') or path in ('/api/next/review', '/api/next/review/undo'):
        import vocab_service
        if path == '/api/next/vocab/met':
            hit = vocab_service.met_in_reading(c, uid, str(data.get('word', ''))[:40])
            return {'card': hit}, 200
        return vocab_service.post(c, uid, path, data)
    if path == '/api/next/rewrite':
        return rewrite(c, uid, data)
    if path == '/api/next/variant':
        return variant(c, uid, data)
    if path == '/api/next/explain':
        return explain(c, uid, data)
    if path == '/api/next/shadow':
        return shadow(c, uid, data)
    if path == '/api/next/ielts':
        return __import__('ielts_speaking').post(c, uid, data)
    if path == '/api/next/skill':
        return __import__('skills_service').post(c, uid, path, data)
    if path.startswith('/api/next/import'):
        return __import__('import_service').post(c, uid, path, data)
    return __import__('output_service').post(c, uid, path, data)
