"""我的数据: the word book exported for Excel and Anki, every record as JSON, and 注销账号, which deletes everything
the account has (and nothing of anyone else's)."""
import base64, csv, io, json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, account_data  # noqa: E402

PW, PW_B = 'a long password here', 'another long password'
JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')


class Site(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.patches = [patch.object(app, 'DB', self.data / 'a.db'), patch.object(app, 'DATA', self.data),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_SURVEY_SALT': 'test-salt', 'FLOW_DATA_DIR': str(self.data)})]
        for p in self.patches:
            p.start()
        app.SECURE = False
        app.init()
        with app.db() as c:
            for name, pw in (('lin', PW), ('ma', PW_B)):
                c.execute('INSERT INTO users(username,password,email) VALUES(?,?,?)', (name, app.password(pw), name + '@example.com'))
            self.a, self.b = (c.execute('SELECT id FROM users WHERE username=?', (n,)).fetchone()[0] for n in ('lin', 'ma'))
            c.execute("INSERT INTO lab_packs(id,owner,origin,content,created) VALUES('noise',NULL,'daily',?,?)",
                      (json.dumps({'id': 'noise', 'title': '降噪耳机为什么能“消音”'}), time.time()))
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()

    def tearDown(self):
        self.site.shutdown(); self.site.server_close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def call(self, path, data=None, headers=None, raw=False):
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                b = r.read()
                return r.status, (b if raw else json.loads(b or b'{}')), dict(r.headers)
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (b if raw else json.loads(b or b'{}')), dict(e.headers)

    def sign_in(self, name='lin', pw=PW):
        st, body, h = self.call('/api/login', {'username': name, 'password': pw})
        self.assertEqual(st, 200, body)
        cookie = h['Set-Cookie'].split(';')[0]
        return {'Cookie': cookie, 'X-CSRF-Token': self.call('/api/session', headers={'Cookie': cookie})[1]['user']['csrf']}

    def card(self, c, uid, text, kind='word', source='', meaning='', context='', pack='', state='review', stability=3.0):
        now = time.time()
        c.execute('INSERT INTO next_cards(user_id,text,norm,meaning,context,pack,kind,created,due,state,source,stability,reps,lapses) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid, text, text.lower(), meaning, context, pack, kind, now, now + 3 * 86400, state, source, stability, 4, 1))
        return c.execute('SELECT last_insert_rowid()').fetchone()[0]


class ExportTests(Site):
    def fill(self):
        with app.db() as c:
            self.card(c, self.a, 'harbour', meaning='港口')
            self.card(c, self.a, 'feels almost like magic', kind='phrase', meaning='感觉简直像魔法一样', pack='noise',
                      context='The effect feels almost like magic: the low roar simply drains away.')
            self.card(c, self.a, 'had went', kind='fix', source='mistake', meaning='had gone', context='I had went home <early>.')
            self.card(c, self.a, '=SUM(A1)', kind='phrase', meaning='a formula-looking note')
            self.card(c, self.b, 'ledger', meaning='账本')

    def test_the_word_book_opens_in_excel(self):
        self.fill()
        h = self.sign_in()
        st, body, hd = self.call('/api/next/export/cards.csv', headers=h, raw=True)
        self.assertEqual(st, 200)
        self.assertTrue(hd['Content-Type'].startswith('text/csv'))
        self.assertIn("attachment; filename=\"flow-words-", hd['Content-Disposition'])
        self.assertIn("filename*=UTF-8''%E8%AF%AD%E6%B5%81", hd['Content-Disposition'])  # 语流单词本-<day>.csv
        self.assertTrue(body.startswith(b'\xef\xbb\xbf'))  # the BOM: Excel reads the file as UTF-8
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
        self.assertEqual(rows[0][:5], ['英文', '中文意思', '音标', '原文例句', '类型'])
        got = {r[0]: r for r in rows[1:]}
        self.assertEqual(set(got), {'harbour', 'feels almost like magic', 'had went', "'=SUM(A1)"})  # not ma's ledger
        self.assertEqual(got['feels almost like magic'][4:6], ['表达', '《降噪耳机为什么能“消音”》'])
        self.assertEqual(got['had went'][4], '错题·改错')
        self.assertEqual(got['harbour'][1], '港口')
        self.assertEqual(got['harbour'][10], '复习中')

    def test_the_word_book_imports_into_anki(self):
        self.fill()
        st, body, hd = self.call('/api/next/export/cards-anki.txt', headers=self.sign_in(), raw=True)
        self.assertEqual(st, 200)
        lines = body.decode('utf-8').splitlines()
        self.assertEqual(lines[:4], ['#separator:tab', '#html:true', '#columns:正面\t背面\t标签', '#tags column:3'])
        notes = [l.split('\t') for l in lines[4:]]
        self.assertTrue(all(len(n) == 3 for n in notes))
        fix = next(n for n in notes if n[0] == 'had went')
        self.assertIn('<i>I had went home &lt;early&gt;.</i>', fix[1])  # the learner's text is text, not HTML
        self.assertEqual(fix[2], '语流 错题_改错')

    def test_every_record_as_json_without_secrets(self):
        self.fill()
        with app.db() as c:
            c.execute('INSERT INTO next_profiles(user_id,level,goal,themes,minutes,created,updated) VALUES(?,?,?,?,?,?,?)', (self.a, 'B1', 'work', '[]', 10, 1, 1))
        st, body, hd = self.call('/api/next/export/records.json', headers=self.sign_in(), raw=True)
        self.assertEqual(st, 200)
        out = json.loads(body)
        self.assertEqual(out['account'], {'username': 'lin', 'email': 'lin@example.com'})
        self.assertEqual(len(out['tables']['next_cards']), 4)
        self.assertEqual(out['tables']['next_profiles'][0]['themes'], [])  # JSON kept as JSON
        self.assertIn('next_cards', out['目录'])
        text = body.decode('utf-8')
        for secret in ('sessions', 'password', 'csrf', 'ledger', 'pbkdf'):
            self.assertNotIn(secret, text)

    def test_signed_in_only(self):
        self.assertEqual(self.call('/api/next/export/cards.csv')[0], 401)
        self.assertEqual(self.call('/api/next/export/nothing', headers=self.sign_in())[0], 404)


class DeleteTests(Site):
    def test_the_password_is_needed_and_wrong_ones_count_like_signing_in(self):
        h = self.sign_in()
        self.assertEqual(self.call('/api/account/delete', {'password': PW}, headers={'Cookie': h['Cookie']})[0], 403)  # no CSRF token
        for k in range(4):
            st, body, _ = self.call('/api/account/delete', {'password': 'wrong one'}, headers=h)
            self.assertEqual((st, body['field']), (400, 'password'))
        st, body, _ = self.call('/api/account/delete', {'password': 'wrong one'}, headers=h)
        self.assertIn('暂停', body['error'])
        self.assertEqual(self.call('/api/account/delete', {'password': PW}, headers=h)[0], 429)  # paused, even with the right one
        self.assertEqual(self.call('/api/login', {'username': 'lin', 'password': PW})[0], 429)  # the same pause as signing in
        with app.db() as c:
            self.assertTrue(c.execute('SELECT 1 FROM users WHERE id=?', (self.a,)).fetchone())

    def test_an_administrator_account_is_not_deleted_here(self):
        with app.db() as c:
            c.execute('UPDATE users SET admin=1 WHERE id=?', (self.a,))
        st, body, _ = self.call('/api/account/delete', {'password': PW}, headers=self.sign_in())
        self.assertEqual(st, 400)
        self.assertIn('管理员', body['error'])

    def test_everything_of_the_account_goes_and_nothing_of_anyone_else(self):
        h, hb = self.sign_in(), self.sign_in('ma', PW_B)
        shot = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'0' * 120).decode()
        st, fb, _ = self.call('/api/feedback', {'kind': 'display', 'text': '底部按钮跑到中间了', 'page': '#/cards', 'images': [shot]}, headers=h)
        self.assertEqual(st, 200)
        with app.db() as c:
            fid = c.execute('SELECT id FROM feedback WHERE user_id=?', (self.a,)).fetchone()[0]
            for uid in (self.a, self.b):
                cid = self.card(c, uid, 'harbour')
                c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (uid, cid, 3, time.time()))
                c.execute('INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,?,?)', (uid, 'noise', 'read', time.time()))
            # lin's own imported article, which ma had bookmarked; lin's word-graph nodes; a review lin wrote of a material
            c.execute("INSERT INTO lab_packs(id,owner,origin,content,created) VALUES('lin-import',?,'import','{}',?)", (self.a, time.time()))
            c.execute("INSERT INTO lab_bookmarks(user_id,pack,created) VALUES(?,'lin-import',?)", (self.b, time.time()))
            c.execute("INSERT INTO lab_bookmarks(user_id,pack,created) VALUES(?,'noise',?)", (self.b, time.time()))
            c.execute("INSERT INTO kg_nodes(id,kind,title,owner,ref) VALUES('w:lin','word','harbour',?,''), ('w:sys','word','ledger',NULL,'')", (self.a,))
            c.execute("INSERT INTO kg_edges(source,target,relation,origin) VALUES('w:lin','w:sys','related','x'), ('w:sys','w:sys','self','x')")
            c.execute("INSERT INTO material_reviews(pack,content_hash,status,checks,note,actor,created) VALUES('noise','h','ok','[]','',?,?)", (self.a, time.time()))
            before = self.counts(c)
        self.assertTrue((self.data / 'feedback' / str(fid)).is_dir())

        st, body, hd = self.call('/api/account/delete', {'password': PW}, headers=h)
        self.assertEqual((st, body['ok']), (200, True))
        self.assertIn('flow_session=;', hd['Set-Cookie'])
        self.assertIn('Max-Age=0', hd['Set-Cookie'])

        with app.db() as c:
            for t in account_data._tables(c):
                cols = account_data._columns(c, t)
                for col in ('user_id', 'owner', 'actor'):
                    if col in cols:
                        self.assertEqual(c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE "{col}"=?', (self.a,)).fetchone()[0], 0, f'{t}.{col}')
            self.assertIsNone(c.execute('SELECT 1 FROM users WHERE id=?', (self.a,)).fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM email_codes WHERE email='lin@example.com'").fetchone()[0], 0)
            after = self.counts(c)
            # ma keeps everything, except the bookmark of lin's article, which is gone with it
            self.assertEqual(after['b'], {**before['b'], 'lab_bookmarks': before['b']['lab_bookmarks'] - 1})
            self.assertEqual([r[0] for r in c.execute("SELECT source||'>'||target FROM kg_edges WHERE source LIKE 'w:%' OR target LIKE 'w:%'")], ['w:sys>w:sys'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM material_reviews WHERE actor IS NULL').fetchone()[0], 1)  # the review stays, unnamed
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertFalse((self.data / 'feedback' / str(fid)).exists())
        self.assertIsNone(self.call('/api/session', headers={'Cookie': h['Cookie']})[1].get('user'))
        self.assertEqual(self.call('/api/next/export/cards.csv', headers=hb, raw=True)[0], 200)  # ma is still signed in
        # the name is free again: signing up starts from nothing
        st, body, _ = self.call('/api/register', {'username': 'lin', 'password': PW})
        self.assertEqual(st, 200, body)

    def counts(self, c):
        out = {'b': {}}
        for t in account_data._tables(c):
            if 'user_id' in account_data._columns(c, t):
                out['b'][t] = c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE user_id=?', (self.b,)).fetchone()[0]
        return out


class PageTests(unittest.TestCase):
    def test_me_has_the_data_section(self):
        for s in ("'/api/next/export/cards.csv'", "'/api/next/export/cards-anki.txt'", "'/api/next/export/records.json'",
                  "api('/api/account/delete'", 'function dataSheet', 'function deleteAccountSheet', "'me-data')", "'me-delete')", 'data-tap="words-export"',
                  "localStorage.removeItem('flow-next-outbox')", 'await OUTBOX.flush(); try { await api(\'/api/logout\''):
            self.assertIn(s, JS)
        import flow_admin
        for k in ('me-data', 'me-delete', 'words-export', 'export-csv', 'export-anki', 'export-json'):
            self.assertIn(k, flow_admin.TAP_LABEL)


if __name__ == '__main__':
    unittest.main()
