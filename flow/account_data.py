"""我的数据: what Flow keeps for an account is the learner's, to take away or to delete.

- 导出单词本: the word book (words, expressions, mistakes) as a table for Excel, WPS or Numbers (CSV in UTF-8 with a
  BOM, so Excel reads the Chinese), or as a file Anki imports (tab-separated; its header lines tell Anki how).
- 下载全部学习记录: every row the account has, table by table, as JSON. Password hashes, sessions, sign-in codes and
  reset links are left out.
- 注销账号: with the password once more (wrong ones count toward the same 15-minute pause as signing in), every row
  that belongs to the account is deleted. The rows are found from the database itself, so a table added later is
  not missed: every table with a user_id column, and every row that refers to those rows or to the account (as ON
  DELETE CASCADE would: owned imports, their bookmarks, word-graph nodes and edges ...). Then the screenshots it sent
  with 问题反馈. Nothing is kept: signing up again with the same name or email starts from nothing.
"""
import csv, datetime, html, io, json, shutil, sqlite3, time
from urllib.parse import quote

CN = datetime.timezone(datetime.timedelta(hours=8))
LEFT_OUT_TABLES = {'sessions', 'recovery_tokens', 'email_codes', 'login_failures', 'users'}
LEFT_OUT_COLUMNS = {'password', 'token', 'csrf', 'digest', 'salt'}
# What the main tables are, for someone reading the file (the rest are from earlier versions of the site).
GUIDE = {
    'next_cards': '单词本：单词、表达和错题（含复习安排）', 'next_corrections': 'AI 改错记录：哪一次练习里改了哪个语法点（看哪些问题反复出现）',
    'next_evidence': '周报「这周的一次进步」：后来你自己写对的句子（每个语法点最多两句，90 天后删）', 'next_reviews': '每一次复习：什么时候、记得怎么样',
    'next_progress': '学过的材料和步骤（听、读、理解、用出来）', 'next_profiles': '学习设置：水平、目标、每天几分钟、每周目标、我的考试和日期、朗读声音、主题色',
    'next_goals': '能力目标', 'next_assess': '水平测评', 'next_radar': '能力雷达的每次结果', 'next_skill_events': '各项练习的得分',
    'next_exam_results': '考试练习的成绩', 'next_exam_type_results': '题型专练每一组的成绩', 'next_easy_reads': '轻松读：读了什么、多快', 'next_word_practice': '单词练习的每一题',
    'next_node_notes': '语法点笔记', 'next_grammar_review': '语法复习', 'next_vocab_plans': '词书计划', 'next_reminders': '每天提醒',
    'feedback': '你发过的问题反馈（截图不在文件里）', 'lab_packs': '你导入的文章',
    'next_goal_weeks': '每周目标改过几次：每个目标从哪一周开始算', 'next_weekly': '每周进度邮件：收不收、上次什么时候发的',
    'class_members': '加入过的班级：什么时候加入、什么时候退出（班级名在最上面的「班级」里）',
}


def _day(t):
    return datetime.datetime.fromtimestamp(t, CN).strftime('%Y-%m-%d') if t else ''


def _ids(values, n=400):
    values = list(dict.fromkeys(v for v in values if v is not None))
    for i in range(0, len(values), n):
        yield values[i:i + n]


def _tables(c):
    return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]


def _columns(c, t):
    return [r[1] for r in c.execute(f'PRAGMA table_info("{t}")').fetchall()]


# ---------- the word book ----------

def _titles(c, uid, packs):
    out = {}
    for chunk in _ids(packs):
        q = f'SELECT id, content FROM lab_packs WHERE id IN ({",".join("?" * len(chunk))}) AND (owner IS NULL OR owner=?)'
        for r in c.execute(q, (*chunk, uid)).fetchall():
            try:
                out[r[0]] = str(json.loads(r[1]).get('title') or '')
            except (ValueError, AttributeError):
                pass
    return out


def _kind(r):
    if r['source'] == 'mistake':
        return '错题·' + {'fix': '改错', 'question': '理解题', 'sound': '发音'}.get(r['kind'], '其他')
    return '单词' if r['kind'] == 'word' else '表达'


def _state(card):
    if card['known']:
        return '标记认识'
    if card['mastered']:
        return '已掌握'
    return {'new': '还没学', 'learning': '学习中', 'relearning': '重新学', 'review': '复习中'}.get(card['state'], card['state'] or '')


def word_book(c, uid):
    """The word book as the learner sees it (the meaning from the dictionary where the list shows it from there),
    oldest first, with the material each came from."""
    import vocab_service, next_service as nx
    rows = c.execute('SELECT * FROM next_cards WHERE user_id=? ORDER BY created, id', (uid,)).fetchall()
    titles, now, words = _titles(c, uid, [r['pack'] for r in rows]), time.time(), nx.dictionary()
    out = []
    for r in rows:
        card = vocab_service.card_out(r, now)
        entry = words.get(r['norm']) if r['kind'] == 'word' else None
        title = titles.get(r['pack'])
        out.append({'text': r['text'], 'meaning': card['meaning'] or '', 'phonetic': (entry or {}).get('phonetic') or '',
                    'context': r['context'] or '', 'kind': _kind(r),
                    'source': f'《{title}》' if title else {'book': '词书', 'import': '导入的词表', 'mistake': '错题'}.get(r['source'] or '', ''),
                    'added': _day(r['created']), 'due': '' if r['state'] == 'new' or card['mastered'] else _day(r['due']),
                    'reps': r['reps'] or 0, 'lapses': r['lapses'] or 0, 'state': _state(card)})
    return out


def _cell(v):
    # a cell that starts like a formula stays text in Excel (a leading ' is the spreadsheet's own text marker)
    v = str(v)
    return "'" + v if v[:1] in ('=', '+', '-', '@') else v


def cards_csv(c, uid):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\r\n')
    w.writerow(['英文', '中文意思', '音标', '原文例句', '类型', '来源', '加入日期', '下次复习', '复习次数', '忘记次数', '状态'])
    for x in word_book(c, uid):
        w.writerow([_cell(x[k]) for k in ('text', 'meaning', 'phonetic', 'context', 'kind', 'source', 'added', 'due', 'reps', 'lapses', 'state')])
    return buf.getvalue().encode('utf-8-sig')


def cards_anki(c, uid):
    """Anki: 文件 → 导入, this file. The header lines set the separator and the columns (Anki 2.1.55 and later read
    them; earlier versions ask): 正面 is the English, 背面 the meaning, the phonetic and the sentence it came in."""
    clean = lambda s: html.escape(' '.join(str(s).split()))
    lines = ['#separator:tab', '#html:true', '#columns:正面\t背面\t标签', '#tags column:3']
    for x in word_book(c, uid):
        back = [f'<b>{clean(x["meaning"])}</b>' if x['meaning'] else '', f'<span style="color:#888">{clean(x["phonetic"])}</span>' if x['phonetic'] else '',
                f'<i>{clean(x["context"])}</i>' if x['context'] else '', f'<small>{clean(x["source"])}</small>' if x['source'] else '']
        tag = '语流 ' + x['kind'].replace('·', '_')
        lines.append('\t'.join([clean(x['text']), '<br>'.join(b for b in back if b), tag]))
    return ('\n'.join(lines) + '\n').encode('utf-8')


# ---------- every record ----------

def _value(v):
    if isinstance(v, str) and v[:1] in ('{', '[') and len(v) < 2_000_000:
        try:
            return json.loads(v)
        except ValueError:
            return v
    if isinstance(v, bytes):
        return None  # no binary columns are the learner's own words
    return v


def records(c, u):
    uid = u['id']
    row = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    import privacy_service as pv
    tables = {}
    for t in _tables(c):
        if t in LEFT_OUT_TABLES:
            continue
        cols = _columns(c, t)
        key = 'user_id' if 'user_id' in cols else 'owner' if t in ('lab_packs', 'lexicon', 'kg_nodes') and 'owner' in cols else None
        if not key:
            continue
        keep = [x for x in cols if x not in LEFT_OUT_COLUMNS]
        rows = c.execute(f'SELECT {",".join(chr(34) + x + chr(34) for x in keep)} FROM "{t}" WHERE "{key}"=?', (uid,)).fetchall()
        if rows:
            tables[t] = [{k: _value(r[i]) for i, k in enumerate(keep)} for r in rows]
    out = {'说明': '语流 Flow 为这个账号保存的全部学习记录。时间是 Unix 时间戳（秒）；每张表一组记录，常用的几张在「目录」里有说明。',
           'exported_at': datetime.datetime.now(CN).isoformat(timespec='seconds'),
           'account': {'username': row['username'], 'email': row['email'] or '', '年龄段': pv.label(pv.info(row)['age']),
                       **({'监护人同意': _day(row['guardian_ok'])} if pv.info(row)['guardian'] else {}),
                       '数据存放在香港': {'ok': '同意（' + _day(row['storage_ok']) + '）', 'no': '不同意或撤回（' + _day(row['storage_no']) + '），账号暂停'}.get(pv.storage(row), '还没问') if 'storage_ok' in row.keys() else '还没问',
                       '用户协议和隐私和数据': ('同意 ' + row['terms_version'] + '（' + _day(row['terms_ok']) + '）') if 'terms_version' in row.keys() and row['terms_version'] else '还没同意'},
           **__import__('class_service').export_rows(c, uid),
           '目录': {t: GUIDE[t] for t in tables if t in GUIDE}, 'tables': tables}
    return json.dumps(out, ensure_ascii=False, indent=1).encode('utf-8')


def export(c, u, path):
    """GET /api/next/export/<file>: (body, mime, ASCII file name, file name) or None for an unknown file."""
    day = datetime.datetime.now(CN).strftime('%Y%m%d')
    if path == '/api/next/export/cards.csv':
        return cards_csv(c, u['id']), 'text/csv; charset=utf-8', f'flow-words-{day}.csv', f'语流单词本-{day}.csv'
    if path == '/api/next/export/cards-anki.txt':
        return cards_anki(c, u['id']), 'text/plain; charset=utf-8', f'flow-words-anki-{day}.txt', f'语流单词本-Anki-{day}.txt'
    if path == '/api/next/export/records.json':
        return records(c, u), 'application/json; charset=utf-8', f'flow-records-{day}.json', f'语流学习记录-{day}.json'
    return None


def disposition(ascii_name, name):
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


# ---------- 注销账号 ----------

def _references(c):
    """{parent table: [(child table, child column, parent column)]} from the declared foreign keys (one column each)."""
    out = {}
    for t in _tables(c):
        fks = {}
        for r in c.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
            fks.setdefault(r[0], []).append(r)
        for rs in fks.values():
            if len(rs) != 1:
                continue
            r = rs[0]
            to = r[4] or next((x[1] for x in c.execute(f'PRAGMA table_info("{r[2]}")').fetchall() if x[5] == 1), 'rowid')
            out.setdefault(r[2], []).append((t, r[3], to))
    return out


def _cascade(c, refs, table, col, values, depth=0):
    """Delete the rows of table whose col is one of values, and every row that refers to them, however deep."""
    values = list(dict.fromkeys(v for v in values if v is not None))
    if not values or depth > 12:
        return 0
    n = 0
    for child, ccol, pcol in refs.get(table, []):
        if child == table and ccol == col:
            continue
        keys = values
        if pcol != col:
            keys = [r[0] for chunk in _ids(values) for r in c.execute(f'SELECT "{pcol}" FROM "{table}" WHERE "{col}" IN ({",".join("?" * len(chunk))})', chunk).fetchall()]
        n += _cascade(c, refs, child, ccol, keys, depth + 1)
    for chunk in _ids(values):
        n += c.execute(f'DELETE FROM "{table}" WHERE "{col}" IN ({",".join("?" * len(chunk))})', chunk).rowcount
    return n


def erase(c, u, data, verify, data_dir=None):
    """POST /api/account/delete {password}: the account and everything it has, gone. ({ok, rows}, 200) or an error."""
    import auth_service
    uid = u['id']
    if u['admin']:
        return {'error': '这是管理员账号，不能在这里注销'}, 400
    p = str(data.get('password', ''))
    if not 1 <= len(p) <= 200:
        return {'error': '请输入密码', 'field': 'password'}, 400
    key, now = 'u:%d' % uid, time.time()
    lock = c.execute('SELECT * FROM login_failures WHERE key=?', (key,)).fetchone()
    if lock and lock['until'] > now:
        return {'error': '密码错了太多次，请 %d 分钟后再试' % max(1, round((lock['until'] - now) / 60)), 'field': 'password'}, 429
    stored = c.execute('SELECT password, email FROM users WHERE id=?', (uid,)).fetchone()
    if not stored or not verify(p, stored['password']):
        left = auth_service.LOCK_TRIES - auth_service.failed(c, key, lock, now)
        return {'error': '密码不正确' + ('，再错 %d 次会暂停 15 分钟' % left if 0 < left <= 2 else '，已暂停 15 分钟' if left <= 0 else ''), 'field': 'password'}, 400
    return {'ok': True, 'rows': forget(c, uid, data_dir)}, 200


def forget(c, uid, data_dir=None):
    """Delete the account uid and everything it has (its rows in every table, its own articles' voice, its feedback
    pictures): 注销账号 once the password is right (erase), and a paused account PAUSE_DAYS on (privacy_service.purge_paused).
    Returns how many rows went. The caller has checked who may; a staff account is never passed here."""
    key = 'u:%d' % uid
    stored = c.execute('SELECT email FROM users WHERE id=?', (uid,)).fetchone()
    if not stored:
        return 0
    shots = [r[0] for r in c.execute("SELECT id FROM feedback WHERE user_id=? AND images!='[]'", (uid,)).fetchall()] if 'feedback' in _tables(c) else []
    refs = _references(c)
    c.commit()
    c.execute('BEGIN IMMEDIATE')
    try:
        c.execute('PRAGMA defer_foreign_keys=ON')  # the order of the deletes does not matter: checked at the commit
        n = 0
        for t in _tables(c):
            if t != 'users' and 'user_id' in _columns(c, t):
                n += _cascade(c, refs, t, 'user_id', [uid])
        for t, col, _ in refs.get('users', []):
            if col not in ('user_id', 'owner'):  # a shared record that only names the account (who reviewed a material) keeps the record
                try:
                    c.execute(f'UPDATE "{t}" SET "{col}"=NULL WHERE "{col}"=?', (uid,))
                except sqlite3.IntegrityError:
                    pass  # it cannot be without one: deleted with the account below
        n += _cascade(c, refs, 'users', 'id', [uid])  # what refers to the account by another name (owner), and the account
        if stored['email']:
            n += c.execute('DELETE FROM email_codes WHERE email=?', (stored['email'],)).rowcount
        c.execute('DELETE FROM login_failures WHERE key IN (?, ?, ?)', (key, 'class:%d' % uid, 'pw:%d' % uid))  # and the invite-code and own-password pauses
        if 'mail_limits' in _tables(c):
            c.execute('DELETE FROM mail_limits WHERE key=?', ('bind:%d' % uid,))
        c.commit()
    except Exception:
        c.rollback()
        raise
    __import__('tts_service').forget(uid)  # the voice of the learner's own articles (data/tts-own/<id>)
    if shots:
        import feedback_service
        base = feedback_service.folder() if data_dir is None else data_dir / 'feedback'
        for rid in shots:
            shutil.rmtree(base / str(rid), ignore_errors=True)
    return n
