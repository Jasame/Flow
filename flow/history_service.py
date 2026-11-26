"""练习记录 (the page: practice-history/api.md, 2026-11-27): a learner's own finished practices that had AI feedback,
read back from what is already kept. Nothing new is stored.

- lab_jobs: each AI result as the practice page got it (lab_service.run_job), kept 180 days (ai_quota.JOB_KEEP_DAYS).
  One record is one finished practice: a dialog's end (its rounds are the turns before it), the IELTS feedback (Part 1's
  answers are the rows before it), and each retelling, essay, translation and rewrite.
- next_assess and next_exam_results: in the list only. They are results, and are not deleted here.

Deleting a record takes its rows (a dialog's rounds with it), the sentences 周报 kept from it (next_evidence), and, when
the learner says so, the mistake cards it made. The scores (next_skill_events) stay: they hold no content, and 进步,
周报 and the radar read them. Every read and delete is for the signed-in learner's own rows only."""
import datetime
import json
import math
from urllib.parse import quote

import next_service as nx
import ui_lang

JOB_KINDS = {'next-dialog': 'dialog', 'next-ielts': 'ielts', 'next-retell': 'retell', 'next-essay': 'essay',
             'next-translate': 'translate', 'next-rewrite': 'rewrite'}
JOB_OF = {v: k for k, v in JOB_KINDS.items()}
KINDS = tuple(JOB_KINDS.values()) + ('assess', 'exam')
TYPES = ('speaking', 'writing', 'translation', 'assess', 'exam')
LIMIT, MAX_LIMIT = 20, 50
GAP = 30 * 60  # a dialog's rounds (and Part 1's answers) follow each other within this; a longer pause is another sitting
BEIJING = datetime.timezone(datetime.timedelta(hours=8))

# The row that is the record: a dialog's end has a summary, IELTS's feedback the four criteria; every row of the others.
# CASE first, so a row that is not JSON is never read as JSON.
_JSON = "CASE WHEN json_valid(result) THEN json_type(result,'$.%s') END IS NOT NULL"
RECORD = ("(kind IN ('next-retell','next-essay','next-translate','next-rewrite')"
          " OR (kind='next-dialog' AND " + _JSON % 'summary' + ")"
          " OR (kind='next-ielts' AND " + _JSON % 'criteria' + "))")
TYPE_SQL = {'speaking': "(kind IN ('next-dialog','next-ielts') OR (kind='next-retell' AND skill='speaking'))",
            'writing': "(kind IN ('next-essay','next-rewrite') OR (kind='next-retell' AND skill!='speaking'))",
            'translation': "kind='next-translate'"}

LABELS = {'scene': ('口语情景', 'Speaking scene'), 'dialog': ('对话', 'Dialogue'), 'ielts': ('雅思口语', 'IELTS speaking'),
          'retell': ('复述', 'Retelling'), 'essay': ('作文批改', 'Essay feedback'), 'translate': ('翻译', 'Translation'),
          'rewrite': ('仿写', 'Rewriting'), 'assess': ('能力测评', 'Skill test'), 'exam': ('考试练习', 'Exam practice')}
VERDICTS = {'natural': ('自然', 'Natural'), 'minor': ('小改', 'Small fixes'), 'rewrite': ('要重写', 'Rewrite')}
SKILLS_EN = {'listening': 'Listening', 'reading': 'Reading', 'vocab': 'Vocabulary', 'grammar': 'Grammar',
             'speaking': 'Speaking', 'writing': 'Writing'}
OUTPUT = {'dialog': 'dialog', 'retell': 'retell', 'essay': 'essay', 'translate': 'translate', 'rewrite': ''}  # #/m/<pack>/output/<this>


def _L(pair):
    return ui_lang.L(*pair)


def _load(text):
    try:
        r = json.loads(text or '')
    except ValueError:
        return {}
    return r if isinstance(r, dict) else {}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _day(t):
    return datetime.datetime.fromtimestamp(t, BEIJING).date().isoformat()


def _fixes(r):
    xs = r.get('changes') if 'changes' in r else r.get('fixes')  # 仿写 calls them changes
    return [x for x in xs if isinstance(x, dict)] if isinstance(xs, list) else []


def _norms(r):
    """The mistake cards a result made, by the norm skills_service.mistakes_from_changes gives them (same rule;
    test_history locks it). Matching on the text is exact for old cards too, which have no request id."""
    out = []
    for ch in _fixes(r):
        frm, to = (ch.get('from') or '').strip(), (ch.get('to') or '').strip()
        if not to or frm in ('', '—') or frm.lower() == to.lower() or len(frm) > 160:
            continue
        out.append(('fix:' + nx._norm(frm + ' > ' + to))[:300])
    return out


def _chunks(xs, n=500):
    xs = list(xs)
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _cards(c, uid, norms):
    out = []
    for part in _chunks(set(norms)):
        out += [r['id'] for r in c.execute("SELECT id FROM next_cards WHERE user_id=? AND source='mistake' AND norm IN (%s)"
                                           % ','.join('?' * len(part)), (uid, *part))]
    return out


def _saved(c, uid, r):
    """The sentences of this feedback the learner can 收藏 (expressions, 值得收藏, versions, word use) that are in the
    word book now, compared by text as save_card keeps it."""
    texts = []
    for k in ('expressions', 'versions', 'word_use', 'used_well'):
        for x in r.get(k) if isinstance(r.get(k), list) else []:
            t = x.get('text') if isinstance(x, dict) else x if isinstance(x, str) else None
            if isinstance(t, str) and t.strip():
                texts.append(t.strip())
    if isinstance(r.get('keep'), dict) and isinstance(r['keep'].get('text'), str):
        texts.append(r['keep']['text'].strip())
    norms = {nx._norm(t): t for t in texts if nx._norm(t)}
    if not norms:
        return []
    have = {row['norm'] for row in c.execute("SELECT norm FROM next_cards WHERE user_id=? AND COALESCE(source,'')!='mistake' AND norm IN (%s)"
                                             % ','.join('?' * len(norms)), (uid, *norms))}
    return [t for n, t in norms.items() if n in have]


# ---------- what a record is called ----------

def _title(c, uid, pack, cache):
    if pack in cache:
        return cache[pack]
    t = ''
    if pack.startswith('scene-'):
        s = __import__('scenarios').SCENES.get(pack[6:])
        t = ui_lang.L(s[1], s[2]) if s else ''
    elif pack.startswith('ielts-p'):
        ie = __import__('ielts_speaking')
        part, _, key = pack[7:].partition('-')
        v = (ie.PART1 if part == '1' else ie.PART2 if part == '2' else {}).get(key)
        t = 'Part %s · %s' % (part, ui_lang.L(v[0], v[1])) if v else ''
    else:
        row = c.execute("SELECT json_extract(content,'$.title') t, json_extract(content,'$.title_en') e FROM lab_packs "
                        "WHERE id=? AND (owner IS NULL OR owner=?)", (pack, uid)).fetchone()
        if row and row['t']:
            t = ui_lang.L(row['t'], row['e'] or row['t'])
    cache[pack] = t
    return t


def _label(kind, pack):
    return _L(LABELS['scene' if kind == 'dialog' and (pack or '').startswith('scene-') else kind])


def _points(v):
    n = round(v * 100)
    return ui_lang.L('%d 分' % n, '%d/100' % n)


def _score(kind, r):
    if kind in ('dialog', 'translate') and _num(r.get('score')):
        return _points(r['score'])
    if kind == 'retell' and isinstance(r.get('points'), list) and r['points'] and isinstance(r.get('fixes'), list):
        return _points(__import__('output_service').retell_score(r))
    if kind == 'ielts' and _num(r.get('overall')):
        return '%.1f' % r['overall']
    if kind == 'essay':
        if r.get('level'):
            return r['level']
        return '%d/20' % sum(r['scores'].values()) if isinstance(r.get('scores'), dict) else ''  # out of 20, not 100 like the others
    if kind == 'rewrite' and r.get('verdict') in VERDICTS:
        return _L(VERDICTS[r['verdict']])
    return ''


def _fixed(n):
    return ui_lang.L('改了 %d 处' % n, '%d fix%s' % (n, '' if n == 1 else 'es')) if n else ui_lang.L('没有要改的', 'Nothing to fix')


def _note(kind, r, rounds):
    n = len(_fixes(r))
    if kind == 'dialog':
        bits = [ui_lang.L('说了 %d 句' % len([x for x in rounds if 'heard' in x[1]]), '%d lines' % len([x for x in rounds if 'heard' in x[1]]))] if rounds else []
        if 'challenge_met' in r:
            bits.append(ui_lang.L('挑战完成', 'Challenge met') if r['challenge_met'] else ui_lang.L('挑战没完成', 'Challenge not met'))
        return ' · '.join(bits + [_fixed(n)])
    if kind == 'ielts':
        if _num(r.get('answered')):
            return ui_lang.L('答了 %d 题' % r['answered'], '%d answers' % r['answered']) + ' · ' + _fixed(n)
        if _num(r.get('seconds')) and r['seconds']:
            return ui_lang.L('说了 %d 秒' % r['seconds'], '%d s' % r['seconds']) + ' · ' + _fixed(n)
        return _fixed(n)
    if kind == 'retell' and isinstance(r.get('points'), list) and r['points']:
        got = sum(1 for x in r['points'] if isinstance(x, dict) and x.get('covered'))
        return ui_lang.L('讲到 %d/%d 个要点' % (got, len(r['points'])), '%d of %d points' % (got, len(r['points']))) + ' · ' + _fixed(n)
    return _fixed(n)


def _again(c, uid, kind, pack):
    """Where 再练一次 goes: the practice page itself; nothing when the text is no longer there."""
    if kind == 'dialog' and pack.startswith('scene-'):
        return '#/speak/' + quote(pack[6:], safe='') if pack[6:] in __import__('scenarios').SCENES else ''
    if kind == 'ielts':
        return '#/speak/ielts/' + quote(pack[6:], safe='')  # ielts-p1-<key> → #/speak/ielts/p1-<key>
    if kind == 'assess':
        return '#/radar/test/' + pack if pack in ('listening', 'reading', 'speaking', 'writing') else '#/radar/test'
    if kind == 'exam':
        return '#/exam/' + quote(pack, safe='')
    if kind in OUTPUT and nx._pack_row(c, uid, pack):
        return '#/m/' + quote(pack, safe='') + '/output' + ('/' + OUTPUT[kind] if OUTPUT[kind] else '')
    return ''


# ---------- the rows of one record ----------

def _rounds(c, uid, row):
    """The rows before a record that belong to it, oldest first, as (row, result): a dialog's turns and its opening,
    IELTS Part 1's answers. Same account and pack, after the previous record there, each within GAP of the next, at
    most the lines a round can have; an opening is where a dialog starts. Nothing else ties them together (no shared id)."""
    kind, pack = row['kind'], row['pack'] or ''
    if kind == 'next-dialog':
        most = __import__('output_service').DIALOG_LINES
    elif kind == 'next-ielts' and pack.startswith('ielts-p1-'):
        most = len(__import__('ielts_speaking').PART1.get(pack[9:], ('', '', ()))[2]) or 6
    else:
        return []
    prev = c.execute("SELECT MAX(created) m FROM lab_jobs WHERE user_id=? AND kind=? AND pack=? AND status='complete' AND created<? AND "
                     + RECORD, (uid, kind, pack, row['created'])).fetchone()['m'] or 0
    out, t, lines = [], row['created'], 0
    for x in c.execute("SELECT id, request_id, result, created FROM lab_jobs WHERE user_id=? AND kind=? AND pack=? AND status='complete' "
                       "AND created>? AND created<? ORDER BY created DESC, id DESC LIMIT ?", (uid, kind, pack, prev, row['created'], most * 2 + 2)):
        r = _load(x['result'])
        if t - x['created'] > GAP:
            break
        if 'heard' in r:
            if lines == most:
                break
            lines += 1
        elif 'scene' not in r:
            continue
        out.append((x, r))
        t = x['created']
        if 'scene' in r:  # the opening: the AI's first line, the start of this dialog
            break
    return out[::-1]


def _round(c, uid, row):
    """This is the learner's nth go at this practice (same kind and text)."""
    return c.execute("SELECT COUNT(*) n FROM lab_jobs WHERE user_id=? AND kind=? AND pack=? AND status='complete' AND created<=? AND "
                     + RECORD, (uid, row['kind'], row['pack'], row['created'])).fetchone()['n']


def _minutes(kind, r, rounds, row):
    if rounds:
        return max(1, math.ceil((row['created'] - rounds[0][0]['created']) / 60))
    if kind == 'ielts' and _num(r.get('seconds')) and r['seconds']:
        return max(1, math.ceil(r['seconds'] / 60))
    return None


def _job_item(c, uid, row, cache, r=None, rounds=None):
    kind = JOB_KINDS[row['kind']]
    r = _load(row['result']) if r is None else r
    rounds = _rounds(c, uid, row) if rounds is None and kind == 'dialog' else rounds or []
    typ = 'speaking' if kind in ('dialog', 'ielts') or (kind == 'retell' and row['skill'] == 'speaking') else \
        'translation' if kind == 'translate' else 'writing'
    return {'id': 'j%d' % row['id'], 'kind': kind, 'type': typ, 'title': _title(c, uid, row['pack'] or '', cache),
            'label': _label(kind, row['pack']), 'at': int(row['created']), 'day': _day(row['created']),
            'score': _score(kind, r), 'note': _note(kind, r, rounds), 'round': _round(c, uid, row), 'open': ''}


def _assess_item(row):
    dims = dict(__import__('ability_radar').DIMS)
    return {'id': 'a%d' % row['id'], 'kind': 'assess', 'type': 'assess',
            'title': ui_lang.L(dims.get(row['skill'], row['skill']), SKILLS_EN.get(row['skill'], row['skill'])),
            'label': _L(LABELS['assess']), 'at': int(row['created']), 'day': _day(row['created']), 'score': row['level'] or '',
            'note': '', 'round': None, 'open': '#/radar'}


def _exam_item(row):
    e = __import__('exam_service').EXAMS.get(row['exam']) or {}
    mins = max(1, math.ceil((row['seconds'] or 0) / 60)) if row['seconds'] else 0
    return {'id': 'x%d' % row['id'], 'kind': 'exam', 'type': 'exam', 'title': e.get('title', row['exam']),
            'label': _L(LABELS['exam']), 'at': int(row['created']), 'day': _day(row['created']),
            'score': '%d/%d' % (row['score'], row['total']), 'note': ui_lang.L('用时 %d 分钟' % mins, '%d min' % mins) if mins else '',
            'round': None, 'open': '#/exam/' + quote(row['exam'], safe='')}


def _table(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


# ---------- 1. the list ----------

def _sources(typ, kind):
    if kind:
        return ('assess',) if kind == 'assess' else ('exam',) if kind == 'exam' else ('job',)
    if typ:
        return ('assess',) if typ == 'assess' else ('exam',) if typ == 'exam' else ('job',)
    return ('job', 'assess', 'exam')


def _where(src, uid, typ, kind, pack, before):
    if src == 'job':
        w, a = ["user_id=?", "status='complete'", RECORD], [uid]
        if kind:
            w.append('kind=?'); a.append(JOB_OF[kind])
        if typ:
            w.append(TYPE_SQL[typ])
        col = 'pack'
    else:
        w, a, col = ['user_id=?'], [uid], 'skill' if src == 'assess' else 'exam'
    if pack:
        w.append(col + '=?'); a.append(pack)
    if before is not None:
        w.append('created<?'); a.append(before)
    return ' AND '.join(w), a


TABLE = {'job': 'lab_jobs', 'assess': 'next_assess', 'exam': 'next_exam_results'}
COLS = {'job': 'id, request_id, kind, pack, skill, result, created', 'assess': 'id, skill, level, created',
        'exam': 'id, exam, score, total, seconds, created'}


def listing(c, uid, q):
    one = lambda k: (q.get(k) or [''])[0]
    typ, kind, pack = one('type'), one('kind'), one('pack')
    if (typ and typ not in TYPES) or (kind and kind not in KINDS) or (pack and not kind):
        return {'error': '筛选条件不对'}, 400
    try:
        limit = max(1, min(MAX_LIMIT, int(one('limit') or LIMIT)))
        before = float(one('before')) if one('before') else None
    except ValueError:
        return {'error': '筛选条件不对'}, 400
    if typ and kind and (kind in ('assess', 'exam') or typ in ('assess', 'exam')) and kind != typ:
        return {'items': [], 'more': False, 'total': 0, 'last': None}, 200  # e.g. a translation that is a test: none
    rows, total, last = [], 0, None
    for src in _sources(typ, kind):
        if not _table(c, TABLE[src]):
            continue
        w, a = _where(src, uid, typ, kind, pack, before)
        rows += [(r['created'], src, r) for r in c.execute('SELECT %s FROM %s WHERE %s ORDER BY created DESC, id DESC LIMIT ?'
                                                           % (COLS[src], TABLE[src], w), (*a, limit + 1))]
        w, a = _where(src, uid, typ, kind, pack, None)
        n = c.execute('SELECT COUNT(*) n, MAX(created) m FROM %s WHERE %s' % (TABLE[src], w), a).fetchone()
        total += n['n']
        last = n['m'] if n['m'] is not None and (last is None or n['m'] > last) else last
    rows.sort(key=lambda x: -x[0])
    cache = {}
    items = [_job_item(c, uid, r, cache) if src == 'job' else _assess_item(r) if src == 'assess' else _exam_item(r)
             for _, src, r in rows[:limit]]
    return {'items': items, 'more': len(rows) > limit, 'total': total, 'last': int(last) if last is not None else None}, 200


# ---------- 2. one record ----------

def _job(c, uid, rid):
    if not (rid[:1] == 'j' and rid[1:].isdigit()):
        return None
    return c.execute("SELECT id, request_id, kind, pack, skill, result, created FROM lab_jobs WHERE id=? AND user_id=? AND status='complete' AND "
                     + RECORD, (int(rid[1:]), uid)).fetchone()


def one(c, uid, rid):
    if rid[:1] in ('a', 'x') and rid[1:].isdigit():
        src = 'assess' if rid[0] == 'a' else 'exam'
        if not _table(c, TABLE[src]):
            return {'error': '没有这条记录'}, 404
        row = c.execute('SELECT %s FROM %s WHERE id=? AND user_id=?' % (COLS[src], TABLE[src]), (int(rid[1:]), uid)).fetchone()
        if not row:
            return {'error': '没有这条记录'}, 404
        item = _assess_item(row) if src == 'assess' else _exam_item(row)
        pack = row['skill'] if src == 'assess' else row['exam']
        return {**item, 'lang': 'zh', 'minutes': None, 'result': None, 'said': None, 'fixes': None, 'saved': [],
                'again': _again(c, uid, src, pack)}, 200
    row = _job(c, uid, rid)
    if not row:
        return {'error': '没有这条记录'}, 404
    kind, r = JOB_KINDS[row['kind']], _load(row['result'])
    rounds = _rounds(c, uid, row)
    item = _job_item(c, uid, row, {}, r, rounds)
    if kind == 'retell' and 'score' not in r and isinstance(r.get('points'), list) and r['points'] and isinstance(r.get('fixes'), list):
        r['score'] = __import__('output_service').retell_score(r)  # as the page got it (added after the result was kept)
    if kind == 'essay' and 'score' not in r and isinstance(r.get('scores'), dict):
        r['score'] = __import__('output_service').essay_score(r)
    said = [x[1]['heard'] for x in rounds if isinstance(x[1].get('heard'), str)] if rounds else None
    del item['open']
    return {**item, 'lang': r.get('lang') or 'zh', 'minutes': _minutes(kind, r, rounds, row), 'result': r, 'said': said,
            'fixes': {'total': len(_fixes(r)), 'kept': len(_cards(c, uid, _norms(r)))}, 'saved': _saved(c, uid, r),
            'again': _again(c, uid, kind, row['pack'] or '')}, 200


def origin(c, uid, request_id, cache=None):
    """错题卡的「来自 …」 (B2): the record a mistake card came from, by the request id the card keeps (extra.rid);
    None when there is none or the record has gone (deleted, or past 180 days)."""
    if not request_id:
        return None
    row = c.execute("SELECT id, kind, pack, created FROM lab_jobs WHERE user_id=? AND request_id=? AND status='complete' AND "
                    + RECORD, (uid, str(request_id))).fetchone()
    if not row:
        return None
    return {'id': 'j%d' % row['id'], 'label': _label(JOB_KINDS[row['kind']], row['pack']),
            'title': _title(c, uid, row['pack'] or '', {} if cache is None else cache), 'at': int(row['created'])}


# ---------- 3. delete ----------

def _remove(c, uid, rows, results, mistakes):
    """Deletes these lab_jobs rows (with the disputes on them and the 周报 sentences kept from them); with mistakes, the
    mistake cards the results made, as delete_card does (their review history stays, unlinked). Returns the cards gone."""
    ids = [r['id'] for r in rows]
    gone = 0
    if mistakes:
        norms = [n for r in results for n in _norms(r)]
        for part in _chunks(_cards(c, uid, norms)):
            q = ','.join('?' * len(part))
            gone += c.execute('DELETE FROM next_cards WHERE user_id=? AND id IN (%s)' % q, (uid, *part)).rowcount
            c.execute('UPDATE next_reviews SET card=-card WHERE user_id=? AND card IN (%s)' % q, (uid, *part))
    if _table(c, 'next_evidence'):
        for part in _chunks({'ev:' + r['request_id'] for r in rows if r['request_id']}):
            c.execute('DELETE FROM next_evidence WHERE user_id=? AND source IN (%s)' % ','.join('?' * len(part)), (uid, *part))
    for part in _chunks(ids):
        q = ','.join('?' * len(part))
        if _table(c, 'feedback_disputes'):
            c.execute('DELETE FROM feedback_disputes WHERE job IN (%s)' % q, part)  # these ids are the learner's own rows
        c.execute('DELETE FROM lab_jobs WHERE user_id=? AND id IN (%s)' % q, (uid, *part))
    return gone


def _mistakes(data):
    m = data.get('mistakes')
    return m if isinstance(m, bool) else None


def delete(c, uid, data):
    m = _mistakes(data)
    rid = str(data.get('id') or '')
    if m is None:
        return {'error': '请选择错题要不要一起删', 'code': 'mistakes'}, 400
    if rid[:1] in ('a', 'x'):
        return {'error': '测评和考试的成绩不在这里删'}, 400
    row = _job(c, uid, rid)
    if not row:
        return {'error': '没有这条记录'}, 404
    r = _load(row['result'])
    rounds = _rounds(c, uid, row)
    gone = _remove(c, uid, [row] + [x[0] for x in rounds], [r], m)
    c.commit()
    return {'ok': True, 'mistakes': gone}, 200


def delete_all(c, uid, data):
    """Every record from lab_jobs, and the rest of those practices' rows too (a dialog left before its end, Part 1
    answers without the feedback); a job still being answered is left to finish. 测评 and 考试 stay."""
    m = _mistakes(data)
    if m is None:
        return {'error': '请选择错题要不要一起删', 'code': 'mistakes'}, 400
    kinds = tuple(JOB_KINDS)
    q = ','.join('?' * len(kinds))
    records = c.execute("SELECT result FROM lab_jobs WHERE user_id=? AND status='complete' AND " + RECORD, (uid,)).fetchall()
    rows = c.execute("SELECT id, request_id FROM lab_jobs WHERE user_id=? AND status!='pending' AND kind IN (%s)" % q, (uid, *kinds)).fetchall()
    gone = _remove(c, uid, rows, [_load(r['result']) for r in records], m)
    c.commit()
    return {'ok': True, 'records': len(records), 'mistakes': gone}, 200
