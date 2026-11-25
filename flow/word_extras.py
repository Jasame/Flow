"""AI 常用搭配和近义、易混词 for the word books (单词「详细模式」第 4 步; 2026-11-25, the owner: 「先跑 50 词样稿给我看」,
then B2's format and A0's / D2's rules). Written offline in batches, never while a learner waits:

- DeepSeek on the batch lane writes (kind word-extras, route of AI 例句 like 例句预生成), sent only the word, its level
  and our own Chinese meaning. qwen-plus (FLOW_BACKUP_AI_MODEL) reads what passed the program's checks and names the
  items it doubts; those are kept hidden (hidden=1, its words in flagged), never shown.
- One row per item (B2): vocab_extras(id, norm, kind 'colloc' | 'near', en, zh, diff, pos, model, prompt, created,
  hidden, flagged), unique on (norm, kind, en), written with INSERT OR IGNORE so a run can stop and start again. id
  never changes and is never given again (AUTOINCREMENT): 「这条不对」 keeps it to hide one row for one learner
  (B2's vocab_extras_hidden), and a row is taken down alone by it (D2: 留痕, 单条下架).
- Its own data, shared by every book, not merged into any word list (D2: NAWL and BSL stay CC BY-SA lists of their own).
- Batch work: ai_routes.batch_stop (the day's ¥5 budget, tonight's batch ceiling) stops a run; --max-yuan too.

    python3 word_extras.py --env-file /etc/flow.env --books zk,gk,cet4 --workers 4 --max-yuan 3 [--offpeak] [--dry-run]
"""
import argparse, json, os, re, sys, time
from pathlib import Path

KIND = 'word-extras'
PROMPT = 'v3-2026-11-25'  # kept with every row: which rules wrote it
LEVEL = {'core': '基础', 'mid': '进阶', 'high': '高阶', 'adv': '精通', 'ext': '拓展', 'zk': '中考', 'gk': '高考', 'cet4': '四级',
         'cet6': '六级', 'ky': '考研', 'tem4': '专四', 'tem8': '专八', 'ielts': '雅思', 'toefl': '托福', 'gre': 'GRE', 'nawl': '学术',
         'bsl': '商务'}
EVERYDAY = {'zk', 'gk', 'core', 'mid'}  # school words: collocations from everyday life
ARTICLES = {'a', 'an', 'the'}
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
        '不算）。zh 是通顺的中文，按这个搭配最常见的意思写，不逐词对译，不超过 12 个字；意思要和给出的中文释义对得上，'
        '不写释义里没有的意思。\n'
        '2. near：只写真正的近义词（如 hope / wish），或中国学生真的常混淆的词（如 wonder / wander、affect / effect），'
        '0–3 个，没有合适的就给空数组，不要凑。反义词和只是同一类的词都不算（win 和 lose、blind 和 deaf 都不写）。必须是真实存在的单个英文单词，不能是这个词本身或它的变形。zh 不超过 8 个字；'
        'diff 用一句中文只说两个词的区别，不超过 20 个字（一个英文单词算一个字）。\n'
        + (f'这几个词用日常生活里的搭配：{", ".join(daily)}。\n' if daily else '') +
        '\n单词（级别 | 词 | 中文释义）：\n' + lines + '\n\n'
        '输出 JSON：{"items":[{"word":"…","collocations":[{"en":"…","zh":"…"}],"near":[{"word":"…","zh":"…","diff":"…"}]}]}'}]


def review_messages(items):
    return [{'role': 'system', 'content': '你是严格的英语编辑。只输出 JSON。'}, {'role': 'user', 'content':
        '逐条检查下面给中国学习者的单词卡内容，只列出有问题的条目：搭配不常用、不地道、缺冠词或介词、中文意思不对或不通顺；'
        '近义或易混词其实不近义也不常混淆、其实是反义词或只是同一类的词、区别说错。没把握算错的不要列。\n' + json.dumps(items, ensure_ascii=False) + '\n\n'
        '输出 JSON：{"problems":[{"word":"…","kind":"colloc 或 near","en":"有问题的那条英文","why":"中文，一句"}]}'}]


def _forms(w):
    return {w, w + 's', w + 'es', w + 'ed', w + 'd', w + 'ing', w[:-1] + 'ing', w[:-1] + 'ies', w[:-1] + 'ied',
            w + w[-1:] + 'ed', w + w[-1:] + 'ing'}


def _is_word(token, w, nx):
    return token in _forms(w) or w in nx.lemma_candidates(token)


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
        if not zh or len(zh) > 12 or LATIN.search(zh):
            why.append(f'搭配的中文为空、太长或夹英文：{en}'); continue
        if guard({'body': en, 'summary_zh': zh}, dated=False):
            why.append(f'敏感内容：{en}'); continue
        keep.append(('colloc', en, zh, ''))
    for x in (item.get('near') or [])[:3]:
        nw, zh, diff = str(x.get('word', '')).strip().lower(), str(x.get('zh', '')).strip(), str(x.get('diff', '')).strip()
        if not re.fullmatch(r'[a-z]+', nw):
            why.append(f'近义词不是单个词：{nw}'); continue
        if _is_word(nw, w, nx) or w in _forms(nw):
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
        c.execute('INSERT OR IGNORE INTO vocab_extras(norm, kind, en, zh, diff, pos, model, prompt, created) VALUES(?,?,?,?,?,?,?,?,?)',
                  (norm, kind, en, zh, diff, pos, model, PROMPT, now))


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


def run_batch(c, batch, nx, guard, review=True):
    """Write, check, store and review one batch: {'words', 'rows', 'left_out', 'hidden'}."""
    import chat_service
    out, model = ask(write_messages(batch))
    by = {str(x.get('word', '')).lower(): x for x in (out.get('items') or []) if isinstance(x, dict)}
    rows = left = 0
    passed = []
    for w, _, _, _ in batch:
        keep, why = check(w, by.get(w) or {}, nx, guard)
        store(c, w, keep, model)
        rows += len(keep); left += len(why)
        if keep:
            passed.append({'word': w, 'collocations': [{'en': e, 'zh': z} for k, e, z, _ in keep if k == 'colloc'],
                           'near': [{'word': e, 'zh': z, 'diff': d} for k, e, z, d in keep if k == 'near']})
    hidden = 0
    reviewer = chat_service.backup_model() if review else ''
    if reviewer and passed:
        problems, _ = ask(review_messages(passed), reviewer)
        hidden = flag(c, problems.get('problems'))
    c.commit()
    return {'words': len(batch), 'rows': rows, 'left_out': left, 'hidden': hidden}


def spent(c, since):
    import ai_routes
    rows = c.execute("SELECT served, model, ts, prompt, cached, completion FROM ai_calls WHERE kind=? AND ts>=?", (KIND, since)).fetchall()
    return sum(ai_routes.cost(ai_routes.served_name(s, m), t, p, k, o) for s, m, t, p, k, o in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description='单词的常用搭配和近义、易混词（AI 批量生成，夜里跑）')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--books', default='zk,gk,cet4,cet6,ielts', help='只做这几本（逗号分隔，按这个顺序）')
    ap.add_argument('--per-call', type=int, default=10)
    ap.add_argument('--limit', type=int, default=0, help='最多做几个词（默认不限）')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--max-yuan', type=float, default=3.0, help='这次运行花到这么多元就不再发新请求')
    ap.add_argument('--offpeak', action='store_true', help='北京时间 8–22 点（DeepSeek 忙时价）先等到 22 点再跑')
    ap.add_argument('--no-review', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
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
    print(json.dumps({'pending': len(todo)}), flush=True)
    if a.dry_run or not todo:
        return 0
    while a.offpeak and 8 <= time.localtime().tm_hour < 22:
        time.sleep(300)
    meaning = lambda w: ((nx.lookup(w) or {}).get('meaning') or '')[:60]
    batches = [[(w, LEVEL.get(b, b), meaning(w), b in EVERYDAY) for w, b in todo[i:i + a.per_call]]
               for i in range(0, len(todo), a.per_call)]
    since, total = time.time(), {'words': 0, 'rows': 0, 'left_out': 0, 'hidden': 0, 'failed': 0}

    def one(batch):
        db = app.db()
        try:
            if ai_routes.batch_stop(db) or spent(db, since) >= a.max_yuan:
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
    print(json.dumps(total), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
