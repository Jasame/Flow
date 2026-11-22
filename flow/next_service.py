"""Flow Next: one learning loop on top of the existing backend (see NEXT.md).

Material -> listen -> read (tap a word, save expressions) -> check -> use it (AI rewrite
comparison) -> review only what you saved. Guests may read, listen and check answers;
saving, AI and progress need an account.
"""
import datetime, hashlib, json, re, time
from pathlib import Path

TZ = datetime.timezone(datetime.timedelta(hours=8))
STEPS = ('listen', 'read', 'check', 'output')
LEVELS = {
    'A2': {'label': '入门', 'pack': 'A2', 'hard_rank': 1500, 'sample': 'I usually take the bus to school. It is cheap and quick.',
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
MINUTES = (5, 10, 15, 30)
RATINGS = ('again', 'hard', 'good', 'easy')
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

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
 created REAL NOT NULL, PRIMARY KEY(pack, level));''')


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


def dictionary():
    """norm -> {word, phonetic, meaning, rank}; first (most frequent) variant wins."""
    global _DICT
    if _DICT is None:
        data = json.loads((Path(__file__).resolve().parent / 'corpus_data' / 'yl-reference.json').read_text(encoding='utf-8'))
        out = {}
        for t in data['terms']:
            v = t['variants'][0]
            out[t['norm']] = {'word': t['word'], 'phonetic': v.get('phonetic', ''), 'meaning': v.get('meaning', ''), 'rank': t.get('rank') or 99999,
                              'example': (v.get('examples') or '').split('\n')[0][3:].strip() if v.get('examples') else ''}
        _DICT = out
    return _DICT


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


def sentences(body):
    return [s.strip() for s in re.split(r'(?:(?<=[.!?])|(?<=[.!?]["”’]))\s+', body.strip()) if s.strip()]


def _pack_row(c, uid, pid):
    row = c.execute('SELECT * FROM lab_packs WHERE id=? AND (owner IS NULL OR owner=?)', (pid, uid or -1)).fetchone()
    if not row:
        return None
    if __import__('quality_service').info(c, row)['status'] == 'disabled':
        return None
    return row


def _public_packs(c, level=None):
    from content_v30 import SUPERSEDED
    out = []
    for row in c.execute("SELECT id, origin, created, content FROM lab_packs WHERE owner IS NULL"):
        p = json.loads(row['content'])
        if p['id'] in SUPERSEDED or (level and p['level'] != level):
            continue
        out.append((row, p))
    return out


def profile(c, uid):
    if not uid:
        return None
    r = c.execute('SELECT * FROM next_profiles WHERE user_id=?', (uid,)).fetchone()
    if not r:
        return None
    return {'level': r['level'], 'goal': r['goal'], 'themes': json.loads(r['themes']), 'minutes': r['minutes']}


def save_profile(c, uid, data):
    level = data.get('level')
    if level not in LEVELS:
        return {'error': '请选择水平'}, 400
    goal = data.get('goal') if data.get('goal') in GOALS else 'daily'
    themes = [t for t in (data.get('themes') or []) if t in THEMES][:6]
    minutes = data.get('minutes') if data.get('minutes') in MINUTES else 10
    now = time.time()
    c.execute('''INSERT INTO next_profiles VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET level=excluded.level,
      goal=excluded.goal, themes=excluded.themes, minutes=excluded.minutes, updated=excluded.updated''',
              (uid, level, goal, json.dumps(themes), minutes, now, now))
    c.commit()
    return {'profile': profile(c, uid)}, 200


def _done(c, uid):
    out = {}
    if uid:
        for r in c.execute('SELECT pack, step FROM next_progress WHERE user_id=?', (uid,)):
            out.setdefault(r['pack'], set()).add(r['step'])
    return out


def _card(pack, done=None, extra=None):
    words = len(pack['body'].split())
    return {'id': pack['id'], 'title': pack['title'], 'level': pack['level'], 'theme': pack['theme'], 'theme_label': THEMES.get(pack['theme'], ''),
            'genre': pack.get('genre', ''), 'words': words, 'minutes': max(3, round(words / 30) + 4),
            'preview': sentences(pack['body'])[0][:140], 'daily': bool(pack.get('daily_day')),
            'steps': sorted(done or [], key=STEPS.index), **(extra or {})}


def home(c, uid, level=None, themes=None):
    prof = profile(c, uid)
    level = (prof or {}).get('level') or (level if level in LEVELS else 'B1')
    pack_level = LEVELS[level]['pack']
    themes = (prof or {}).get('themes') or [t for t in (themes or []) if t in THEMES]
    done = _done(c, uid)
    day = _day()
    pool = [(r, p) for r, p in _public_packs(c, pack_level) if r['origin'] != 'daily']
    fresh = [(r, p) for r, p in pool if 'check' not in done.get(p['id'], set())] or pool
    seed = lambda p: hashlib.sha256(f"{uid or 0}|{day}|{p['id']}".encode()).hexdigest()
    fresh.sort(key=lambda rp: (0 if (not themes or rp[1]['theme'] in themes) else 1, seed(rp[1])))
    picks = [_card(p, done.get(p['id'])) for _, p in fresh[:3]]
    news = None
    for r, p in sorted(_public_packs(c), key=lambda rp: -rp[0]['created']):
        if r['origin'] == 'daily' and r['created'] > time.time() - 3 * 86400:
            news = _card(p, done.get(p['id']), {'source': p.get('source', ''), 'day': p.get('daily_day')})
            break
    resume = None
    if uid:
        r = c.execute('''SELECT pack, MAX(created) t FROM next_progress WHERE user_id=? GROUP BY pack ORDER BY t DESC LIMIT 5''', (uid,)).fetchall()
        for row in r:
            if 'output' not in done.get(row['pack'], set()):
                pr = _pack_row(c, uid, row['pack'])
                if pr:
                    resume = _card(json.loads(pr['content']), done.get(row['pack']))
                    break
    return {'profile': prof, 'level': level, 'level_label': LEVELS[level]['label'], 'today': picks, 'news': news, 'resume': resume,
            'stats': stats(c, uid) if uid else None}


def stats(c, uid):
    now = time.time()
    week_start = now - 7 * 86400
    days = set()
    for (t,) in c.execute('SELECT created FROM next_progress WHERE user_id=? AND created>?', (uid, week_start)):
        days.add(_day(t))
    for (t,) in c.execute('SELECT created FROM next_reviews WHERE user_id=? AND created>?', (uid, week_start)):
        days.add(_day(t))
    week = [_day(now - i * 86400) for i in range(6, -1, -1)]
    return {
        'due': c.execute('SELECT COUNT(*) FROM next_cards WHERE user_id=? AND due<=?', (uid, now)).fetchone()[0],
        'cards': c.execute('SELECT COUNT(*) FROM next_cards WHERE user_id=?', (uid,)).fetchone()[0],
        'materials_done': c.execute("SELECT COUNT(DISTINCT pack) FROM next_progress WHERE user_id=? AND step='check'", (uid,)).fetchone()[0],
        'reviews_week': c.execute('SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND created>?', (uid, week_start)).fetchone()[0],
        'week': [{'day': d, 'active': d in days} for d in week],
    }


def library(c, uid, level=None, theme=None, page=1, per=12):
    done = _done(c, uid)
    rows = _public_packs(c, level if level in ('A2', 'B1', 'B2') else None)
    rows = [rp for rp in rows if not theme or rp[1]['theme'] == theme]
    rows.sort(key=lambda rp: (-(rp[0]['created'] if rp[0]['origin'] == 'daily' else 0), rp[1]['level'], rp[1]['id']))
    page = max(1, page)
    return {'total': len(rows), 'page': page, 'per': per, 'themes': THEMES,
            'items': [_card(p, done.get(p['id'])) for _, p in rows[(page - 1) * per: page * per]]}


def _task(pack, level):
    k = dict((pack.get('knowledge') or [{}])[0])
    # Old explanations end with internal caveats ("阅读不等于已掌握…"); learners only need the first clause.
    k['explanation'] = re.split(r'[；;]', k.get('explanation', ''))[0].strip()
    vocab = [v['term'] for v in pack.get('vocabulary', [])][:3]
    if k.get('quote'):
        model = k['quote']
        if level == 'A2':
            return {'prompt': '仿照下面这句的结构，写一句关于你自己的话。', 'model': model, 'hint': k.get('explanation', '')}
        return {'prompt': '仿照下面这句的结构，写一两句和你自己的经历有关的话。', 'model': model, 'hint': k.get('explanation', '')}
    return {'prompt': f"用上 {'、'.join(vocab) or '文中的一个表达'}，写一两句和你自己有关的话。", 'model': '', 'hint': ''}


def material(c, uid, pid, level=None):
    row = _pack_row(c, uid, pid)
    if not row:
        return {'error': '材料不存在'}, 404
    p = json.loads(row['content'])
    prof = profile(c, uid)
    level = (prof or {}).get('level') or (level if level in LEVELS else 'B1')
    hard_rank = LEVELS[level]['hard_rank']
    body = p['body']
    variant = None
    if level in LEVELS and LEVELS[level]['pack'] != p['level'] or level == 'C1':
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
        if hit and hit['rank'] > hard_rank:
            hard[key] = {'meaning': hit['meaning'][:80], 'rank': hit['rank']}
    qs = [{'prompt': q['prompt'], 'options': q['options']} for q in p.get('questions', [])]
    done = _done(c, uid).get(pid, set())
    return {'id': p['id'], 'title': p['title'], 'level': p['level'], 'theme': p['theme'], 'theme_label': THEMES.get(p['theme'], ''),
            'source': p.get('source', ''), 'daily_day': p.get('daily_day'), 'sentences': sentences(text), 'original_level': p['level'],
            'original': sentences(body) if variant else None,
            'variant': variant, 'vocabulary': list(vocab.values()), 'hard': hard, 'questions': qs,
            'notes': p.get('knowledge', []), 'task': _task(p, level), 'steps': sorted(done, key=STEPS.index),
            'provenance': [{'title': s['title'], 'url': s['url']} for s in (p.get('provenance') or {}).get('sources', [])][:5],
            'user_level': level, 'can_variant': level != p['level'] and not variant}, 200


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
        __import__('event_service').record(c, uid, 'skill:reading', f"next:{p['id']}:q{i}", 'next-check', p['id'], p['id'],
                                           int(correct), 0, 'rule', {'choice': choice})
        if i == len(qs) - 1:
            mark(c, uid, p['id'], 'check', commit=False)
        c.commit()
    return {'correct': correct, 'answer': q['answer'], 'evidence': q.get('evidence', '')}, 200


def mark(c, uid, pid, step, commit=True):
    if step not in STEPS:
        raise ValueError('步骤不正确')
    c.execute('INSERT OR IGNORE INTO next_progress VALUES(?,?,?,?)', (uid, pid, step, time.time()))
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
    r = c.execute('SELECT * FROM next_cards WHERE id=? AND user_id=?', (cid, uid)).fetchone()
    return _card_out(r) if r else None


def _card_out(r):
    return {k: r[k] for k in ('id', 'text', 'meaning', 'context', 'pack', 'kind', 'created', 'due', 'interval', 'reps', 'lapses')}


def cards(c, uid, q='', page=1, per=30):
    rows = c.execute('SELECT * FROM next_cards WHERE user_id=? ORDER BY created DESC', (uid,)).fetchall()
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r['text'].lower() or ql in r['meaning'].lower() or ql in r['context'].lower()]
    page = max(1, page)
    return {'total': len(rows), 'page': page, 'per': per, 'items': [_card_out(r) for r in rows[(page - 1) * per: page * per]]}


def delete_card(c, uid, data):
    n = c.execute('DELETE FROM next_cards WHERE id=? AND user_id=?', (int(data['id']), uid)).rowcount
    c.commit()
    return ({'ok': True}, 200) if n else ({'error': '记录不存在'}, 404)


def review_queue(c, uid, limit=20):
    now = time.time()
    rows = c.execute('SELECT * FROM next_cards WHERE user_id=? AND due<=? ORDER BY due LIMIT ?', (uid, now, limit)).fetchall()
    return {'items': [_card_out(r) for r in rows], 'due': c.execute('SELECT COUNT(*) FROM next_cards WHERE user_id=? AND due<=?', (uid, now)).fetchone()[0]}


def schedule(r, rating, now):
    """Small SM-2 variant. Returns (interval_days, ease, reps, lapses, due)."""
    interval, ease, reps, lapses = r['interval'], r['ease'], r['reps'], r['lapses']
    if rating == 'again':
        return 0, max(1.3, ease - 0.2), 0, lapses + 1, now + 10 * 60
    if rating == 'hard':
        interval = max(1, interval * 1.2) if reps else 1
        return interval, max(1.3, ease - 0.15), reps + 1, lapses, now + interval * 86400
    if reps == 0:
        interval = 1
    elif reps == 1:
        interval = 3
    else:
        interval = max(interval + 1, interval * ease)
    if rating == 'easy':
        interval *= 1.3
        ease += 0.15
    interval = min(interval, 365)
    return interval, ease, reps + 1, lapses, now + interval * 86400


def review(c, uid, data):
    rating = data.get('rating')
    if rating not in RATINGS:
        return {'error': '评分不正确'}, 400
    r = c.execute('SELECT * FROM next_cards WHERE id=? AND user_id=?', (int(data['id']), uid)).fetchone()
    if not r:
        return {'error': '记录不存在'}, 404
    now = time.time()
    interval, ease, reps, lapses, due = schedule(r, rating, now)
    c.execute('UPDATE next_cards SET interval=?, ease=?, reps=?, lapses=?, due=?, last=? WHERE id=?', (interval, ease, reps, lapses, due, now, r['id']))
    c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (uid, r['id'], rating, now))
    c.commit()
    return {'card': card(c, uid, r['id']), 'remaining': review_queue(c, uid, 0)['due']}, 200


# ---------- AI ----------

def _level_voice(level):
    return {'A2': '讲解全部用简单的中文，例句用最常见的词。',
            'B1': '讲解用中文，必要时给出英文关键词。',
            'B2': '讲解以中文为主，可以夹带英文术语，关注语气和搭配。',
            'C1': '讲解可以中英结合，关注措辞的细微差别、语域和风格。'}[level]


def rewrite(c, uid, data):
    from lab_service import run_job, text as clean_text
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
    spec = {'pack': p['id'], 'text': answer, 'level': level}
    system = ('你是一位耐心、专业的英语写作教练，学习者的水平是 ' + level + '（' + LEVELS[level]['label'] + '）。' + _level_voice(level) +
              '先肯定写得好的地方，再改错，最后给出更好的说法。不要编造学习者没写的内容。只输出 JSON。')
    user = ('学习任务：' + task['prompt'] + ('\n参考句：' + task['model'] if task['model'] else '') +
            '\n材料主题：' + p['title'] + '\n学习者写的英文：\n' + answer +
            '\n\n输出 JSON，结构：{"verdict":"natural|minor|rewrite","summary":"一句话总评（中文，先说优点）",'
            '"corrected":"在保留原意的前提下改对的版本（若已正确则原样返回）",'
            '"changes":[{"from":"原文片段","to":"改后片段","why":"为什么（简短）"}],'
            '"versions":[{"label":"更自然","text":"...","why":"和原句的差别"},{"label":"更正式","text":"...","why":"..."},{"label":"更简洁","text":"...","why":"..."}],'
            '"keep":{"text":"最值得收藏的一个英文表达（短语）","meaning":"中文意思"}}。changes 最多 5 条，没有错误就给空数组。')

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        out = {'verdict': raw.get('verdict') if raw.get('verdict') in ('natural', 'minor', 'rewrite') else 'minor',
               'summary': clean_text(raw.get('summary'), 1, 300), 'corrected': clean_text(raw.get('corrected'), 1, 900),
               'changes': [], 'versions': [], 'keep': None}
        for ch in (raw.get('changes') or [])[:5]:
            if isinstance(ch, dict) and ch.get('to'):
                out['changes'].append({'from': clean_text(ch.get('from') or '—', 1, 200), 'to': clean_text(ch['to'], 1, 200), 'why': clean_text(ch.get('why') or '—', 1, 300)})
        for v in (raw.get('versions') or [])[:3]:
            if isinstance(v, dict) and v.get('text'):
                out['versions'].append({'label': clean_text(v.get('label') or '参考', 1, 20), 'text': clean_text(v['text'], 1, 900), 'why': clean_text(v.get('why') or '', 0, 300)})
        if not out['versions']:
            raise ValueError('no versions')
        k = raw.get('keep')
        if isinstance(k, dict) and isinstance(k.get('text'), str) and WORD.search(k['text']) and len(k['text']) <= 160:
            out['keep'] = {'text': k['text'].strip(), 'meaning': str(k.get('meaning') or '')[:200]}
        return out

    result, status = run_job(c, uid, str(data.get('request_id', '')), 'next-rewrite', p['id'], 'writing', spec,
                             lambda: request_model([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]), convert)
    if status == 200:
        mark(c, uid, p['id'], 'output')
    return result, status


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
    lo, hi = int(max(35, lo)), int(min(320, max(hi, lo + 30)))
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
            'minutes': list(MINUTES)}


def get(c, uid, path, q):
    one = lambda k, d='': (q.get(k) or [d])[0]
    if path == '/api/next/meta':
        return meta(), 200
    if path == '/api/next/home':
        return home(c, uid, one('level'), one('themes').split(',') if one('themes') else None), 200
    if path == '/api/next/library':
        return library(c, uid, one('level') or None, one('theme') or None, int(one('page', '1') or 1)), 200
    if path == '/api/next/material':
        return material(c, uid, one('id'), one('level'))
    if path == '/api/next/lookup':
        w = one('w')[:40]
        if not WORD.fullmatch(w or ''):
            return {'error': '只能查英文单词'}, 400
        hit = lookup(w)
        return ({'entry': hit} if hit else {'entry': None, 'query': w}), 200
    if not uid:
        return ({'error': '请先登录'}, 401) if path.startswith('/api/next/') else None
    if path == '/api/next/cards':
        return cards(c, uid, one('q')[:80], int(one('page', '1') or 1)), 200
    if path == '/api/next/review':
        return review_queue(c, uid), 200
    if path == '/api/next/stats':
        return stats(c, uid), 200
    return None


def post_public(c, uid, path, data):
    """Routes open to guests (no state change for guests)."""
    if path == '/api/next/check':
        return check(c, uid, data)
    return None


def post(c, uid, path, data):
    if path == '/api/next/profile':
        return save_profile(c, uid, data)
    if path == '/api/next/progress':
        if not _pack_row(c, uid, str(data.get('pack', ''))):
            return {'error': '材料不存在'}, 404
        mark(c, uid, data['pack'], data.get('step'))
        return {'ok': True}, 200
    if path == '/api/next/cards':
        return save_card(c, uid, data)
    if path == '/api/next/cards/delete':
        return delete_card(c, uid, data)
    if path == '/api/next/review':
        return review(c, uid, data)
    if path == '/api/next/rewrite':
        return rewrite(c, uid, data)
    if path == '/api/next/variant':
        return variant(c, uid, data)
    return None
