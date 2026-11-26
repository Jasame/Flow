"""AI 常用搭配和近义、易混词 for the word books (单词「详细模式」第 4 步; 2026-11-25, the owner: 「先跑 50 词样稿给我看」,
then B2's format and A0's / D2's rules). Written offline in batches, never while a learner waits:

- DeepSeek on the batch lane writes (kind word-extras, route of AI 例句 like 例句预生成), sent only the word, its level
  and our own Chinese meaning. qwen-plus (FLOW_BACKUP_AI_MODEL) reads what passed the program's checks and names the
  items it doubts; those are kept hidden (hidden=1, its words in flagged), never shown.
- One row per item (B2): vocab_extras(id, norm, kind 'colloc' | 'near', en, zh, diff, pos, model, prompt, created,
  hidden, flagged), unique on (norm, kind, en), written with INSERT OR IGNORE so a run can stop and start again. id
  never changes and is never given again (AUTOINCREMENT): 「这条不对」 keeps it to hide one row for one learner
  (B2's vocab_extras_flags(user_id, extra_id, created, note)), and the console takes a row down or puts it back by it
  (B6; D2: 留痕, 单条下架). reported() is the one summary of those marks.
- Its own data, shared by every book, not merged into any word list (D2: NAWL and BSL stay CC BY-SA lists of their own).
- Batch work: ai_routes.batch_stop (the day's ¥5 budget, tonight's batch ceiling) stops a run; --max-yuan too.
- Nightly (A0 2026-11-26: the owner nods once for the whole run): <data>/word-extras/plan.json (books, max_yuan a night,
  nights, until, hold_after_first: stop after the first night until B7 has looked at it; own_cap with first_night_yuan
  and total_yuan: the owner's 「暂时放行预算上限，跑完收紧」, the run keeps to its own yuan and is left out of the site's
  day budget and batch ceiling until the plan is done, so the caps tighten again by themselves), written only with the owner's OK, lets ai_routes.tick start one run a night (02:00–05:00 Beijing) as a
  child process, like the nightly check. The night's report is <data>/word-extras/<day>.json. Done when no word is left,
  the nights are used or the date has passed; paused, never retried on its own, when a night looks wrong (anomaly).

    python3 word_extras.py --env-file /etc/flow.env --books zk,gk,cet4 --workers 4 --max-yuan 3 [--offpeak] [--dry-run]
"""
import argparse, datetime, json, os, re, sys, time
from pathlib import Path

KIND = 'word-extras'
PROMPT = 'v5-2026-11-26'  # kept with every row: which rules wrote it
LEVEL = {'core': '基础', 'mid': '进阶', 'high': '高阶', 'adv': '精通', 'ext': '拓展', 'zk': '中考', 'gk': '高考', 'cet4': '四级',
         'cet6': '六级', 'ky': '考研', 'tem4': '专四', 'tem8': '专八', 'ielts': '雅思', 'toefl': '托福', 'gre': 'GRE', 'nawl': '学术',
         'bsl': '商务'}
EVERYDAY = {'zk', 'gk', 'core', 'mid'}  # school words: collocations from everyday life
ARTICLES = {'a', 'an', 'the'}
HALF_SENTENCE = {'and', 'but', 'or', 'so', 'because', 'then'}  # sample 3: 「and consequently failed」 is half a sentence
OFF_TOPIC = {'rights', 'election', 'elections', 'vote', 'votes', 'voting', 'democracy', 'regime', 'protest', 'protests',
             'military', 'army', 'armies', 'war', 'wars', 'weapon', 'weapons', 'soldier', 'soldiers', 'troops', 'gun',
             'guns', 'bomb', 'bombs', 'religion', 'religious', 'church', 'mosque', 'bible', 'god', 'gods'}  # v4: human rights
# The owner's review of the samples (2026-11-26, words-ai-collocations-review.md, B7's 16 doubts): if the writer gives one
# of these again, it is stored hidden. (norm, kind, en, the zh or diff that was wrong, or None when the English is.)
REVIEWED_OUT = [
    ('blind', 'near', 'deaf', None, '只是同一类的词'), ('hot', 'colloc', 'hot and spicy', '又热又辣', '中文不对，是香辣'),
    ('audience', 'colloc', 'a large audience', '大量观众', '中文不准'), ('clone', 'colloc', 'make a clone of the plant',
    '培育该植物的无性系', '中文不通'), ('personnel', 'colloc', 'train the personnel', None, '不自然'),
    ('compliment', 'near', 'praise', 'compliment多指客套称赞，praise更正式', '区别说错'),
    ('consequently', 'colloc', 'and consequently failed', None, '不是搭配'),
    ('consequently', 'colloc', 'consequently lose money', None, '不是搭配'),
    ('practically', 'colloc', 'practically speaking', '实际上说', '中文别扭'),
    ('economical', 'colloc', 'economical car', None, '缺冠词'), ('principal', 'colloc', 'principal reason', None, '缺冠词'),
    ('sensible', 'colloc', 'sensible decision', None, '缺冠词'), ('sensible', 'colloc', 'sensible choice', None, '缺冠词'),
    ('stationary', 'colloc', 'stationary object', None, '缺冠词'), ('custom', 'colloc', 'custom design', None, '和释义对不上'),
    ('human', 'colloc', 'human rights', None, '政治话题')]
LATIN = re.compile(r'[A-Za-z]')


def units(text):
    """How long a line reads on the card: a Chinese character or mark counts 1, an English word counts 1 (sample 2: a
    limit by characters dropped affect / effect for its letters)."""
    return len(re.findall(r"[A-Za-z][A-Za-z'-]*", text)) + len(re.sub(r"[A-Za-z][A-Za-z'-]*|\s", '', text))


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS vocab_extras(id INTEGER PRIMARY KEY AUTOINCREMENT, norm TEXT NOT NULL, '
              'kind TEXT NOT NULL, en TEXT NOT NULL, '
              "zh TEXT NOT NULL DEFAULT '', diff TEXT NOT NULL DEFAULT '', pos INTEGER NOT NULL DEFAULT 0, "
              "model TEXT NOT NULL DEFAULT '', prompt TEXT NOT NULL DEFAULT '', created REAL NOT NULL, "
              "hidden INTEGER NOT NULL DEFAULT 0, flagged TEXT NOT NULL DEFAULT '', UNIQUE(norm, kind, en))")


SYSTEM = ('你是给中国学习者编单词卡的英语老师。只输出 JSON。拿不准就少写，绝不编造，不照搬任何一本词典的条目。'
          '不写暴力、色情、赌博、毒品、自残、歧视，不出现真人、品牌、政治和时事。')


def write_messages(batch):
    """batch: [(word, level label, our Chinese meaning, everyday?)]."""
    lines = '\n'.join(f'{lv} | {w} | {m}' for w, lv, m, _ in batch)
    daily = [w for w, _, _, e in batch if e]
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content':
        '给下面每个英文单词写：\n'
        '1. collocations：3 条最常用、学习者能直接拿来用的搭配。英文 2–6 个词，冠词和介词写全（写 borrow a book from the '
        'library，不写 borrow from library）；动词搭配带上宾语（写 edge closer to the door）；光是冠词加这个词不算（a penny '
        '不算）；形容词搭配也带冠词（写 a sensible decision，不写 sensible decision）；不写半句话（不写 and '
        'consequently failed）。zh 是通顺的中文，按这个搭配最常见的意思写，不逐词对译，不超过 12 个字；意思只按给出的中文'
        '释义写，释义里没有的意思不写（custom 给的是「风俗」，就不写 custom design）。不写政治、宗教、军事和战争。\n'
        '2. near：0–3 个。先写拼写或读音相近、中国学生真的常混淆的词（如 wonder / wander、principle / principal），有就一定'
        '写上，排在最前；再写真正的近义词（如 hope / wish）。没有合适的就给空数组，不要凑。反义词和只是同一类的词都不算（win 和 lose、blind 和 deaf 都不写）。必须是真实存在的单个英文单词，不能是这个词本身或它的变形。zh 不超过 8 个字；'
        'diff 用一句中文只说两个词的区别，不超过 20 个字（一个英文单词算一个字）。\n'
        + (f'这几个词用日常生活里的搭配：{", ".join(daily)}。\n' if daily else '') +
        '\n单词（级别 | 词 | 中文释义）：\n' + lines + '\n\n'
        '输出 JSON：{"items":[{"word":"…","collocations":[{"en":"…","zh":"…"}],"near":[{"word":"…","zh":"…","diff":"…"}]}]}'}]


def review_messages(items):
    return [{'role': 'system', 'content': '你是严格的英语编辑。只输出 JSON。'}, {'role': 'user', 'content':
        '逐条检查下面给中国学习者的单词卡内容（meaning 是我们给这个词的中文释义），只列出有问题的条目：搭配不常用、不地道、'
        '缺冠词或介词、像半句话、意思和 meaning 对不上、中文意思不对或不通顺、中文逐词硬译（hot and spicy 是香辣，不是又热又辣）；'
        '近义或易混词其实不近义也不常混淆、其实是反义词或只是同一类的词、区别说错。拼写或读音相近、学生常混的一对词算易混，'
        '不要因为意思不近就列出来。没把握算错的不要列。\n' + json.dumps(items, ensure_ascii=False) + '\n\n'
        '输出 JSON：{"problems":[{"word":"…","kind":"colloc 或 near","en":"有问题的那条英文","why":"中文，一句"}]}'}]


def _forms(w):
    """The word's own inflections (sample 4: sleepy is not a form of sleeping, nor wind of win)."""
    f = {w, w + 's', w + 'es', w + 'ed', w + 'ing', w + w[-1:] + 'ed', w + w[-1:] + 'ing'}
    if w.endswith('e'):
        f |= {w + 'd', w[:-1] + 'ing'}
    if w.endswith('ie'):
        f.add(w[:-2] + 'ying')  # lie → lying
    if w.endswith('y'):
        f |= {w[:-1] + 'ies', w[:-1] + 'ied'}
    return f


def _is_word(token, w, nx):
    return token in _forms(w) or w in nx.lemma_candidates(token)


def _own(word, nx):
    return ((nx.lookup(word) or {}).get('word') or '').lower() == word


def _same(nw, w, nx):
    """Is the near word only this word again? beside / besides and cloth / clothes are two words: an s-form the
    dictionary keeps as a headword of its own is another word (sample 4 left besides out)."""
    if nw == w:
        return True
    for a, b in ((nw, w), (w, nw)):
        if a in (b + 's', b + 'es') and _own(a, nx):
            return False
    return _is_word(nw, w, nx) or w in _forms(nw)


def check(w, item, nx, guard):
    """The program's checks on one word's answer: ([(kind, en, zh, diff)] that pass, [why each other one was left out])."""
    keep, why = [], []
    for x in (item.get('collocations') or [])[:4]:
        en, zh = re.sub(r'\s+', ' ', str(x.get('en', '')).strip()), str(x.get('zh', '')).strip()
        toks = re.findall(r"[a-z']+", en.lower())
        if not re.fullmatch(r"[A-Za-z' -]+", en) or not 2 <= len(toks) <= 6:
            why.append(f'搭配格式：{en}'); continue
        if not any(_is_word(t, w, nx) for t in toks):
            why.append(f'搭配不含这个词：{en}'); continue
        if not [t for t in toks if t not in ARTICLES and not _is_word(t, w, nx)]:
            why.append(f'搭配只是这个词本身：{en}'); continue
        if toks[0] in HALF_SENTENCE:
            why.append(f'搭配像半句话：{en}'); continue
        if set(toks) & OFF_TOPIC:
            why.append(f'政治、宗教、军事类：{en}'); continue
        if not zh or len(zh) > 12 or LATIN.search(zh):
            why.append(f'搭配的中文为空、太长或夹英文：{en}'); continue
        if guard({'body': en, 'summary_zh': zh}, dated=False):
            why.append(f'敏感内容：{en}'); continue
        keep.append(('colloc', en, zh, ''))
    for x in (item.get('near') or [])[:3]:
        nw, zh, diff = str(x.get('word', '')).strip().lower(), str(x.get('zh', '')).strip(), str(x.get('diff', '')).strip()
        if not re.fullmatch(r'[a-z]+', nw):
            why.append(f'近义词不是单个词：{nw}'); continue
        if _same(nw, w, nx):
            why.append(f'近义词就是原词：{nw}'); continue
        if not nx.lookup(nw):
            why.append(f'近义词词典里查不到：{nw}'); continue
        if not zh or len(zh) > 8 or LATIN.search(zh):
            why.append(f'近义词的中文为空、太长或夹英文：{nw}'); continue
        if not diff or units(diff) > 25:
            why.append(f'近义词的区别为空或超过 25 个字：{nw}'); continue
        if guard({'body': nw, 'summary_zh': zh + diff}, dated=False):
            why.append(f'敏感内容：{nw}'); continue
        keep.append(('near', nw, zh, diff))
    return keep, why


def store(c, norm, keep, model, now=None):
    """The items that passed, one row each (INSERT OR IGNORE: a second run adds nothing twice)."""
    now = now or time.time()
    for pos, (kind, en, zh, diff) in enumerate(keep):
        out = reviewed_out(norm, kind, en, zh, diff)
        c.execute('INSERT OR IGNORE INTO vocab_extras(norm, kind, en, zh, diff, pos, model, prompt, created, hidden, flagged) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?)', (norm, kind, en, zh, diff, pos, model, PROMPT, now, 1 if out else 0,
                  json.dumps({'by': 'review-2026-11-26', 'why': out}, ensure_ascii=False) if out else ''))


def reviewed_out(norm, kind, en, zh, diff):
    """Why the owner's review left this item out, or ''."""
    for n, k, e, bad, why in REVIEWED_OUT:
        if (n, k, e.lower()) == (norm, kind, en.lower()) and bad in (None, zh if kind == 'colloc' else diff):
            return why
    return ''


def flag(c, problems):
    """The reviewer's doubts: those rows stay hidden, with its words kept (D2: 纠错有记录)."""
    n = 0
    for p in problems or []:
        if not isinstance(p, dict):
            continue
        norm, kind, en = str(p.get('word', '')).lower().strip(), str(p.get('kind', '')).strip(), str(p.get('en', '')).strip()
        if kind not in ('colloc', 'near'):
            kind = 'near' if re.fullmatch(r'[a-z]+', en.lower()) else 'colloc'
        note = json.dumps({'by': 'qwen-plus', 'why': str(p.get('why', ''))[:120]}, ensure_ascii=False)
        n += c.execute('UPDATE vocab_extras SET hidden=1, flagged=? WHERE norm=? AND kind=? AND lower(en)=lower(?)',
                       (note, norm, kind, en if kind == 'colloc' else en.lower())).rowcount
    return n


def shown(c, norm):
    """What a word's card shows (B2's page): rows not hidden, in order, each with its id (「这条不对」 and the
    site-wide takedown go by it)."""
    return [dict(zip(('id', 'kind', 'en', 'zh', 'diff'), r)) for r in c.execute(
        'SELECT id, kind, en, zh, diff FROM vocab_extras WHERE norm=? AND hidden=0 ORDER BY kind, pos', (norm,))]


FLAGS = 'vocab_extras_flags'  # B2's table: one row per learner and item they marked 「这条不对」


def _note(row_flagged):
    try:
        v = json.loads(row_flagged or '{}')
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def take_down(c, extra_id, why, by):
    """Hide one row for everyone from the console (B6; the weekly look at 「这条不对」), keeping who, why and when.
    Returns 1 if a row changed. The console keeps its own admin log too."""
    note = json.dumps({'by': str(by)[:40], 'why': str(why)[:120], 'at': int(time.time()), 'admin': True}, ensure_ascii=False)
    return c.execute('UPDATE vocab_extras SET hidden=1, flagged=? WHERE id=?', (note, int(extra_id))).rowcount


def put_back(c, extra_id, by):
    """Show again a row the console took down. Rows the reviewer or the owner's review hid are not touched: 0."""
    row = c.execute('SELECT hidden, flagged FROM vocab_extras WHERE id=?', (int(extra_id),)).fetchone()
    if not row or not row[0] or not _note(row[1]).get('admin'):
        return 0
    note = json.dumps({'put_back_by': str(by)[:40], 'at': int(time.time()), 'was': _note(row[1])}, ensure_ascii=False)
    return c.execute('UPDATE vocab_extras SET hidden=0, flagged=? WHERE id=?', (note, int(extra_id))).rowcount


def reported(c, since=None, limit=200):
    """The rows learners marked 「这条不对」, most learners first, taken-down ones included (B6 shows 「放回」 for those):
    extra_id, norm, kind, en, zh, diff, users, last, notes (the last 5 notes that say something, no names), hidden,
    by_admin (hidden from the console, so put_back works). since: only marks from then on."""
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (FLAGS,)).fetchone():
        return []
    since = float(since or 0)
    rows = c.execute(f'SELECT e.id, e.norm, e.kind, e.en, e.zh, e.diff, e.hidden, e.flagged, COUNT(DISTINCT f.user_id), MAX(f.created) '
                     f'FROM {FLAGS} f JOIN vocab_extras e ON e.id = f.extra_id WHERE f.created >= ? GROUP BY e.id '
                     f'ORDER BY COUNT(DISTINCT f.user_id) DESC, MAX(f.created) DESC LIMIT ?', (since, int(limit))).fetchall()
    out = []
    for i, norm, kind, en, zh, diff, hidden, flagged, users, last in rows:
        notes = [r[0] for r in c.execute(f"SELECT note FROM {FLAGS} WHERE extra_id=? AND created >= ? AND TRIM(COALESCE(note, '')) <> '' "
                                         f'ORDER BY created DESC LIMIT 5', (i, since))]
        out.append({'extra_id': i, 'norm': norm, 'kind': kind, 'en': en, 'zh': zh, 'diff': diff, 'users': users, 'last': last,
                    'notes': notes, 'hidden': bool(hidden), 'by_admin': bool(hidden) and bool(_note(flagged).get('admin'))})
    return out


def pending(c, vs, books, nx=None):
    """Words of these books (in this order) with no row yet: [(norm, book)]. Names (York) are left out."""
    done = {r[0] for r in c.execute('SELECT DISTINCT norm FROM vocab_extras')}
    out, seen = [], set()
    bw = vs.book_words()
    for b in books:
        for w in bw.get(b, []):
            norm = (w[1] if isinstance(w, tuple) else w).lower()
            if norm in seen or norm in done or not re.fullmatch(r'[a-z]+', norm):
                continue
            entry = nx.lookup(norm) if nx else None
            if entry and str(entry.get('word', ''))[:1].isupper():
                continue
            seen.add(norm); out.append((norm, b))
    return out


def ask(messages, model=None):
    """One call on the batch lane (as 例句预生成 does), or on model when given (the reviewer): (parsed JSON, model)."""
    import ai_routes, chat_service
    from lab_service import parse
    with ai_routes.task(KIND):
        name = model or ai_routes.route()
        ai_routes.CTX.route = name
        chat_service.INFO.__dict__.clear()
        started = time.monotonic()
        try:
            reply = chat_service._request_text_service(messages, name, ai_routes.extra_body(name))[0]
        except Exception as exc:
            ai_routes.record('text', name, started, messages, None, dict(chat_service.INFO.__dict__), exc)
            raise
        ai_routes.record('text', name, started, messages, reply, dict(chat_service.INFO.__dict__))
    return parse(reply), name


def reviewer(review=True):
    """The second model that reads every item before a card shows it (the guide: 「再由另一个 AI 模型复查」), or ''
    with review off (--no-review: throwaway sample databases only). Review on and no reviewer set: stop, write nothing,
    rather than put unread items on the cards (2026-11-26, B7 checking B2's #429 wording)."""
    import chat_service
    if not review:
        return ''
    name = chat_service.backup_model()
    if not name:
        raise RuntimeError('没有复查模型（FLOW_BACKUP_AI_MODEL），不写')
    return name


def run_batch(c, batch, nx, guard, review=True):
    """Write, check, store and review one batch: {'words', 'rows', 'left_out', 'hidden'}. The reviewer is looked up
    first: without one nothing is asked or stored."""
    reviewer_name = reviewer(review)
    out, model = ask(write_messages(batch))
    by = {str(x.get('word', '')).lower(): x for x in (out.get('items') or []) if isinstance(x, dict)}
    rows = left = 0
    passed = []
    for w, _, meaning, _ in batch:
        keep, why = check(w, by.get(w) or {}, nx, guard)
        store(c, w, keep, model)
        rows += len(keep); left += len(why)
        if keep:
            passed.append({'word': w, 'meaning': meaning, 'collocations': [{'en': e, 'zh': z} for k, e, z, _ in keep if k == 'colloc'],
                           'near': [{'word': e, 'zh': z, 'diff': d} for k, e, z, d in keep if k == 'near']})
    hidden = 0
    if reviewer_name and passed:
        problems, _ = ask(review_messages(passed), reviewer_name)
        hidden = flag(c, problems.get('problems'))
    c.commit()
    return {'words': len(batch), 'rows': rows, 'left_out': left, 'hidden': hidden}


def spent(c, since):
    import ai_routes
    rows = c.execute("SELECT served, model, ts, prompt, cached, completion FROM ai_calls WHERE kind=? AND ts>=?", (KIND, since)).fetchall()
    return sum(ai_routes.cost(ai_routes.served_name(s, m), t, p, k, o) for s, m, t, p, k, o in rows)


def plan_dir():
    return __import__('console_ops').data_dir() / 'word-extras'


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


def reports(d=None):
    """The nights' reports, oldest first."""
    d = Path(d or plan_dir())
    out = []
    for f in sorted(d.glob('20*.json')):
        r = _read(f)
        if isinstance(r, dict):
            out.append({**r, 'day': f.stem})
    return out


def anomaly(r, plan):
    """Why a night looks wrong (the run then waits for the owner), or ''."""
    if r.get('error'):
        return f"运行出错：{str(r['error'])[:80]}"
    if r.get('failed', 0) > 2:
        return f"{r['failed']} 批没跑成"
    rows, left, hidden, words = r.get('rows', 0), r.get('left_out', 0), r.get('hidden', 0), r.get('words', 0)
    if words >= 50:
        if left > 0.3 * (rows + left):
            return '程序拦下的超过三成'
        if hidden > 0.3 * rows:
            return '复核藏起的超过三成'
        if rows < words:
            return '平均每个词不到 1 条'
    if r.get('yuan', 0) > 1.3 * float(plan.get('max_yuan', 3)):
        return f"花了 ¥{r['yuan']}，超过每晚上限"
    return ''


def own_cap_on():
    """The owner's plan lets this run past the site's budget and batch ceiling for now (own_cap), until it is done."""
    plan = _read(plan_dir() / 'plan.json')
    return isinstance(plan, dict) and bool(plan.get('own_cap')) and not plan.get('done')


def status():
    """For the console: the plan and the nights so far."""
    return {'plan': _read(plan_dir() / 'plan.json'), 'nights': reports()[-14:]}


def nightly(c, now=None):
    """From ai_routes.tick: start tonight's run if the owner's plan says so. Returns True if started."""
    import ai_routes
    now = now or time.time()
    t = datetime.datetime.fromtimestamp(now, ai_routes.TZ)
    if not ai_routes.NIGHT[0] <= t.hour < ai_routes.NIGHT[1]:
        return False
    d = plan_dir()
    plan = _read(d / 'plan.json')
    if not isinstance(plan, dict) or plan.get('done') or plan.get('paused'):
        return False
    day = t.date().isoformat()
    if (d / f'{day}.json').exists():
        return False
    mark = _read(d / 'running.json') or {}
    if now - mark.get('started', 0) < 3 * 3600:
        return False
    past = [r for r in reports(d) if r['day'] >= str(plan.get('from', ''))]
    why = anomaly(past[-1], plan) if past else ''
    if not why and plan.get('hold_after_first') and [r for r in past if r.get('words')]:
        why = '第一晚跑完，等 B7 抽查'  # the first night on a new prompt is looked at before the rest; B7 then clears it
    if why:
        _write(d / 'plan.json', {**plan, 'paused': why, 'paused_at': day})
        return False
    used = sum(float(r.get('yuan') or 0) for r in past)
    total = float(plan.get('total_yuan') or 0)
    ran = [r for r in past if r.get('words')]
    if (past and past[-1].get('pending_after') == 0) or len(ran) >= int(plan.get('nights', 0)) \
            or day > str(plan.get('until', '9999')) or (total and used >= total - 0.05):
        _write(d / 'plan.json', {**plan, 'done': day})
        return False
    cap = float(plan.get('first_night_yuan') or plan.get('max_yuan', 3)) if not ran else float(plan.get('max_yuan', 3))
    if total:
        cap = min(cap, round(total - used, 2))
    from vertex_auth import ai_enabled
    if not ai_enabled() or (not plan.get('own_cap') and ai_routes.batch_stop(c)):
        return False
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, os.path.join(here, 'word_extras.py'), '--env-file', os.devnull, '--books', ','.join(plan.get('books') or []),
           '--max-yuan', str(cap), '--output', str(d / f'{day}.json')] + (['--own-cap'] if plan.get('own_cap') else [])
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f'{day}.log', 'w', encoding='utf-8') as log:
        subprocess.Popen(cmd, cwd=here, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env={**os.environ, 'PYTHONUNBUFFERED': '1'})
    _write(d / 'running.json', {'started': now, 'day': day})
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description='单词的常用搭配和近义、易混词（AI 批量生成，夜里跑）')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--books', default='zk,gk,cet4,cet6,ielts', help='只做这几本（逗号分隔，按这个顺序）')
    ap.add_argument('--per-call', type=int, default=10)
    ap.add_argument('--limit', type=int, default=0, help='最多做几个词（默认不限）')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--max-yuan', type=float, default=3.0, help='这次运行花到这么多元就不再发新请求')
    ap.add_argument('--offpeak', action='store_true', help='北京时间 8–22 点（DeepSeek 忙时价）先等到 22 点再跑')
    ap.add_argument('--no-review', action='store_true', help='不复查，只用于试验用的数据库（正式版卡片上的每一条都要复查过）')
    ap.add_argument('--own-cap', action='store_true', help='用户临时放行：不受网站每天预算和每晚批量上限管，只按 --max-yuan')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--output', default='', help='这一晚的结果写到这个文件（夜里自动跑时用）')
    a = ap.parse_args(argv)
    try:
        return _main(a)
    except Exception as exc:  # noqa: BLE001 - the night's report says what went wrong, and the plan pauses
        if a.output:
            _write(a.output, {'error': f'{type(exc).__name__}: {str(exc)[:160]}', 'when': int(time.time())})
        raise


def _main(a):
    if Path(a.env_file).is_file():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from studio_setup import read_env
        for k, v in read_env(Path(a.env_file).read_text()).items():
            os.environ.setdefault(k, v)
    import app, ai_routes, next_service as nx, vocab_service as vs, topic_guard
    from concurrent.futures import ThreadPoolExecutor
    c = app.db(); schema(c); c.commit()
    todo = pending(c, vs, [b.strip() for b in a.books.split(',') if b.strip()], nx)
    if a.limit:
        todo = todo[:a.limit]
    with ai_routes.task(KIND):
        writer = ai_routes.route()
    import chat_service
    plan = {'pending': len(todo), 'writer': writer, 'reviewer': '' if a.no_review else chat_service.backup_model(),
            'batch_line': ai_routes.batch_line(), 'batch_spent_tonight': round(ai_routes.batch_spent_since(c, ai_routes.learner_day_start(time.time())), 4),
            'max_yuan': a.max_yuan, 'prompt': PROMPT}
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if a.dry_run or not todo:
        return 0
    reviewer(not a.no_review)  # no reviewer: stop before the first batch; main() writes the error and the plan pauses
    while a.offpeak and 8 <= time.localtime().tm_hour < 22:
        time.sleep(300)
    meaning = lambda w: ((nx.lookup(w) or {}).get('meaning') or '')[:60]
    batches = [[(w, LEVEL.get(b, b), meaning(w), b in EVERYDAY) for w, b in todo[i:i + a.per_call]]
               for i in range(0, len(todo), a.per_call)]
    since, total = time.time(), {'words': 0, 'rows': 0, 'left_out': 0, 'hidden': 0, 'failed': 0}

    def one(batch):
        db = app.db()
        try:
            if (not a.own_cap and ai_routes.batch_stop(db)) or spent(db, since) >= a.max_yuan:
                return None
            return run_batch(db, batch, nx, topic_guard.hits, review=not a.no_review)
        except Exception as exc:  # noqa: BLE001 - one batch failing does not stop the run
            print('batch failed:', type(exc).__name__, str(exc)[:120], flush=True)
            return {'failed': 1}
        finally:
            db.close()

    with ThreadPoolExecutor(max(1, min(a.workers, 8))) as ex:
        for r in ex.map(one, batches):
            if r is None:
                continue
            for k, v in r.items():
                total[k] = total.get(k, 0) + v
    total['yuan'] = round(spent(c, since), 4)
    total['pending_after'] = len(pending(c, vs, [b.strip() for b in a.books.split(',') if b.strip()], nx))
    total.update({'prompt': PROMPT, 'when': int(time.time())})
    print(json.dumps(total), flush=True)
    if a.output:
        _write(a.output, total)
    return 0


if __name__ == '__main__':
    sys.exit(main())
