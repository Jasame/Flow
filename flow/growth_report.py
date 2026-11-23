"""My progress (我的进步): a month at a glance against the month before, and milestones that only count up.

No ranking and no streaks to lose: days studied are counted in total, never as a run that breaks.
"""
import datetime, json, time

import next_service as nx

MASTERED = 21  # days of memory stability from which a word counts as known well (the same line as vocab_service)


def _month(ym=None, now=None):
    """(start, end, label, previous ym) for 'YYYY-MM' (default: this month) in the site's time zone."""
    today = datetime.datetime.fromtimestamp(now or time.time(), nx.TZ)
    if ym:
        try:
            y, m = map(int, ym.split('-'))
            first = datetime.datetime(y, m, 1, tzinfo=nx.TZ)
        except (ValueError, TypeError):
            first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (first + datetime.timedelta(days=32)).replace(day=1)
    prev = (first - datetime.timedelta(days=1)).replace(day=1)
    return first.timestamp(), nxt.timestamp(), f'{first.year} 年 {first.month} 月', prev.strftime('%Y-%m'), first.strftime('%Y-%m')


def _words_read(c, uid, lo, hi):
    """Words read in [lo, hi): materials read in the four steps, plus easy reading."""
    packs = {r[0] for r in c.execute("SELECT DISTINCT pack FROM next_progress WHERE user_id=? AND step='read' AND created>=? AND created<?", (uid, lo, hi))}
    words = 0
    if packs:
        for r in c.execute('SELECT content FROM lab_packs WHERE id IN (%s)' % ','.join('?' * len(packs)), list(packs)):
            words += len(nx.WORD.findall(json.loads(r[0]).get('body', '')))
    words += c.execute('SELECT COALESCE(SUM(words),0) FROM next_easy_reads WHERE user_id=? AND created>=? AND created<?', (uid, lo, hi)).fetchone()[0]
    return words


def _days(c, uid, lo, hi):
    days = set()
    for (t,) in c.execute('SELECT created FROM next_progress WHERE user_id=? AND created>=? AND created<? UNION ALL '
                          'SELECT created FROM next_reviews WHERE user_id=? AND created>=? AND created<? UNION ALL '
                          'SELECT created FROM next_skill_events WHERE user_id=? AND created>=? AND created<? UNION ALL '
                          'SELECT created FROM learning_events WHERE user_id=? AND created>=? AND created<? UNION ALL '
                          'SELECT created FROM next_easy_reads WHERE user_id=? AND created>=? AND created<?', (uid, lo, hi) * 5):
        days.add(nx._day(t))
    return len(days)


def _figures(c, uid, lo, hi):
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    speeds = [r[0] for r in c.execute('SELECT wpm FROM next_easy_reads WHERE user_id=? AND created>=? AND created<? AND wpm IS NOT NULL', (uid, lo, hi))]
    return {
        'days': _days(c, uid, lo, hi),
        'words_read': _words_read(c, uid, lo, hi),
        'materials': q("SELECT COUNT(DISTINCT pack) FROM next_progress WHERE user_id=? AND step IN ('check','output') AND created>=? AND created<?", uid, lo, hi),
        'wpm': round(sum(speeds) / len(speeds)) if speeds else None,
        'reviews': q('SELECT COUNT(*) FROM next_reviews WHERE user_id=? AND created>=? AND created<?', uid, lo, hi),
        'new_words': q("SELECT COUNT(*) FROM next_cards WHERE user_id=? AND kind='word' AND created>=? AND created<?", uid, lo, hi),
        'grammar_checks': q("SELECT COUNT(*) FROM learning_events WHERE user_id=? AND correct IS NOT NULL AND evaluator='rule' AND created>=? AND created<?", uid, lo, hi),
        'speaking': q("SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND skill IN ('speaking','pronunciation') AND created>=? AND created<?", uid, lo, hi),
        'writing': q("SELECT COUNT(*) FROM next_skill_events WHERE user_id=? AND skill IN ('writing','translation') AND created>=? AND created<?", uid, lo, hi),
    }


def _milestones(c, uid):
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    words_read = _words_read(c, uid, 0, time.time() + 1)
    known = q('SELECT COUNT(*) FROM next_cards WHERE user_id=? AND kind=\'word\' AND (known=1 OR stability>=?)', uid, MASTERED)
    states = nx.graph_states(c, uid)
    lit = lambda lv: [n for n in nx.LEVEL_NODES.get(lv, ()) if n in states and nx.node_level(n) == lv]
    solid = lambda lv: sum(1 for n in lit(lv) if states[n]['status'] == 'solid')
    days = _days(c, uid, 0, time.time() + 1)
    series = nx.series_list(c, uid)
    scenes = q("SELECT COUNT(DISTINCT pack) FROM next_skill_events WHERE user_id=? AND kind='dialog' AND pack LIKE 'scene-%'", uid)
    out = []

    def add(key, title, have, need, unit):
        out.append({'key': key, 'title': title, 'have': min(have, need), 'need': need, 'done': have >= need, 'unit': unit})
    for n, t in ((10000, '读满 1 万词'), (50000, '读满 5 万词'), (200000, '读满 20 万词')):
        add(f'read-{n}', t, words_read, n, '词')
    for n in (100, 500, 1000):
        add(f'words-{n}', f'记牢 {n} 个单词', known, n, '个')
    for lv in ('A2', 'B1', 'B2'):
        total = len(lit(lv))
        if total:
            add(f'grammar-{lv}', f'{lv} 语法点全部验证', solid(lv), total, '个点')
    for s in series:
        add(f'series-{s["id"]}', f'读完连载《{s["title"]}》', s['done'], s['of'], '集')
    add('scenes-5', '完成 5 个情景对话', scenes, 5, '个')
    for n in (30, 100):
        add(f'days-{n}', f'累计学习 {n} 天', days, n, '天')
    return out


def month(c, uid, ym=None, now=None):
    lo, hi, label, prev_ym, cur_ym = _month(ym, now)
    plo, phi, *_ = _month(prev_ym, now)
    cur, before = _figures(c, uid, lo, hi), _figures(c, uid, plo, phi)
    ms = _milestones(c, uid)
    return {'month': cur_ym, 'label': label, 'prev': prev_ym, 'now': cur, 'before': before,
            'milestones': sorted(ms, key=lambda m: (m['done'], -m['have'] / max(1, m['need']))),
            'reached': sum(1 for m in ms if m['done']), 'total': len(ms),
            'note': '只和你自己的上个月比。不排名，也不算连续打卡：学习天数只累计，不会因为哪天没学就清零。'}, 200
