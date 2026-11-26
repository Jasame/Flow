"""内测版的测试账号 (2026-11-26, the owner: 「你说的这些后台都要做上去」: 内测版 要能一键造测试账号、重置测试数据).

Only on the 内测版 (FLOW_CHANNEL=beta): the console refuses both on 语流's. A test account is an ordinary account made
in one click for one of KINDS (the states that are slow to reach by hand), named 「测试-<种类>-<4 位>」, with a random
password shown once. Every one is listed in beta_test_accounts, and 重置测试数据 deletes exactly those, as 注销账号
deletes one (account_data.forget): the people who really test the 内测版 are never touched. The reset asks for the
number it will delete, so a stale page cannot delete more than it showed.
"""
import secrets, time

KINDS = {
    'adult': '学生 · 18 岁及以上',
    'teen': '学生 · 14–17 岁',
    'child': '学生 · 不满 14 岁、家长还没同意',
    'teacher': '老师账号',
    'paused': '没同意数据存放（暂停中）',
    'new': '刚注册、还没开始学',
    'week': '学了一周（有学习记录和单词）',
}
SLUG = {'adult': '成人', 'teen': '中学', 'child': '小学', 'teacher': '老师', 'paused': '暂停', 'new': '新号', 'week': '一周'}
LETTERS = 'abcdefghjkmnpqrstuvwxyz23456789'


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS beta_test_accounts(user_id INTEGER PRIMARY KEY REFERENCES users(id), '
              'kind TEXT NOT NULL, created REAL NOT NULL, by TEXT NOT NULL DEFAULT "")')


def beta():
    import app
    return app.CHANNEL == 'beta'


def make(c, kind, by, now=None):
    """POST /beta-test/create {kind}: (body, status, log target). The password is in the answer only this once."""
    if kind not in KINDS:
        return {'error': '没有这种测试账号'}, 400, ''
    import app, next_service as nx, privacy_service as pv
    now = now or time.time()
    for _ in range(20):
        name = f'测试-{SLUG[kind]}-' + ''.join(secrets.choice(LETTERS) for _ in range(4))
        if not c.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone():
            break
    password = ''.join(secrets.choice(LETTERS) for _ in range(12))
    uid = c.execute('INSERT INTO users(username, password, created, role) VALUES(?,?,?,?)',
                    (name, app.password(password), now, 'teacher' if kind == 'teacher' else None)).lastrowid
    c.execute('INSERT INTO beta_test_accounts(user_id, kind, created, by) VALUES(?,?,?,?)', (uid, kind, now, str(by or '')[:200]))
    if kind != 'paused':
        pv.agreed(c, uid, now)
    else:
        c.execute('UPDATE users SET storage_no=? WHERE id=?', (now, uid))
    pv.agreed_terms(c, uid, now)
    # the 年龄段, as sign-up keeps it; 不满 14 岁 without the guardian's agreement, as an older account answers later
    c.execute('UPDATE users SET age_band=?, age_set=?, guardian_ok=NULL WHERE id=?', ({'teen': '14-17', 'child': 'u14'}.get(kind, '18+'), now, uid))
    if kind not in ('new', 'teacher'):
        nx.save_profile(c, uid, {'level': 'B1', 'goal': 'daily', 'minutes': 15})
    if kind == 'week':
        _a_week(c, uid, now)
    c.commit()
    return ({'ok': True, 'id': uid, 'username': name, 'password': password, 'kind': kind, 'label': KINDS[kind]}, 200,
            f'{name} #{uid}')


def _a_week(c, uid, now):
    """Seven days of study: a few texts' steps and a handful of words reviewed, dated over the last week."""
    import next_service as nx
    packs = [p['id'] for row, p in nx._public_packs(c) if row['origin'] != 'daily'][:4]
    for d, pid in enumerate(packs):
        t = now - (6 - d) * 86400
        for step in nx.STEPS[: 2 + d % 3]:
            c.execute('INSERT OR IGNORE INTO next_progress VALUES(?,?,?,?)', (uid, pid, step, t))
    for i, word in enumerate(('commute', 'deadline', 'improve', 'schedule', 'suggest')):
        t = now - (6 - i) * 86400
        c.execute('INSERT OR IGNORE INTO next_cards(user_id, text, norm, meaning, kind, created, due, reps, last) VALUES(?,?,?,?,?,?,?,?,?)',
                  (uid, word, word, '', 'word', t, now + 86400, 1, t))


def listing(c):
    """GET /beta-tests: the test accounts there are, newest first, and the kinds one can make."""
    rows = [{'id': r['user_id'], 'username': r['username'], 'kind': r['kind'], 'label': KINDS.get(r['kind'], r['kind']),
             'created': r['created'], 'by': r['by']}
            for r in c.execute('SELECT t.*, u.username FROM beta_test_accounts t JOIN users u ON u.id=t.user_id ORDER BY t.created DESC')]
    return {'items': rows, 'kinds': [{'key': k, 'label': v} for k, v in KINDS.items()]}


def reset(c, data, data_dir=None):
    """POST /beta-test/reset {count}: delete every test account (and only those). count must be the number the page
    showed. (body, status, log target)."""
    ids = [r[0] for r in c.execute('SELECT user_id FROM beta_test_accounts')]
    try:
        want = int(data.get('count'))
    except (TypeError, ValueError):
        want = -1
    if want != len(ids):
        return {'error': f'现在有 {len(ids)} 个测试账号，和页面上的不一样。请刷新后再试。', 'count': len(ids)}, 409, ''
    import account_data
    for uid in ids:
        account_data.forget(c, uid, data_dir)
    c.execute('DELETE FROM beta_test_accounts')
    c.commit()
    return {'ok': True, 'deleted': len(ids)}, 200, f'{len(ids)} 个测试账号'
