"""Every table that names an account is deleted with it and in 导出我的数据 (隐私和数据: 「注销后，网站里这个账号的全部记录
马上删除」). The columns that look like an account, by name or by a foreign key to users, are listed from the database
itself, so a table added later fails here until account_data covers it (user_id, a foreign key, ACCOUNT_COLUMNS) or
says why it is not one (NOT_ACCOUNT). 2026-11-26: tts_usage and tts_import named the account in `who` and were missed
(D2); `python3 account_data.py orphans` finds what such a table kept."""
import json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import app, account_data as ad  # noqa: E402

# column names that usually hold an account (an id, a mail or a name): a new one must be covered or explained
LOOKS = {'user_id', 'uid', 'who', 'owner', 'account', 'account_id', 'learner', 'learner_id', 'member', 'member_id', 'student',
         'student_id', 'teacher', 'teacher_id', 'user', 'actor', 'used_by', 'created_by', 'changed_by', 'by', 'visitor',
         'email', 'username'}


def full_schema(c):
    """app.init's tables and every module's own schema(c) (some are made on first use)."""
    for f in sorted(HERE.glob('*.py')):
        if not re.search(r'^def schema\(c\)', f.read_text(encoding='utf-8'), re.M):
            continue
        __import__(f.stem).schema(c)
    c.commit()


class AccountTables(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                  patch.dict(os.environ, {'FLOW_DATA_DIR': self.tmp.name})):
            p.start(); self.addCleanup(p.stop)
        app.init()
        self.c = app.db(); self.addCleanup(self.c.close)
        full_schema(self.c)

    def test_every_column_that_looks_like_an_account_is_covered_or_explained(self):
        missing = []
        for t in ad._tables(self.c):
            if t == 'users':
                continue
            fks = {r[3]: r[2] for r in self.c.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()}
            for col in ad._columns(self.c, t):
                if col not in LOOKS and fks.get(col) != 'users':
                    continue
                covered = col == 'user_id' or fks.get(col) == 'users' or ad.ACCOUNT_COLUMNS.get(t) == col or (t, col) in ad.NOT_ACCOUNT
                if not covered:
                    missing.append(f'{t}.{col}')
        self.assertEqual(missing, [], '这些列像是账号：放进 account_data.ACCOUNT_COLUMNS（注销时删、导出带上），或者 NOT_ACCOUNT（写明为什么不是）')
        for t, col in ad.ACCOUNT_COLUMNS.items():  # what the map names is there
            self.assertIn(col, ad._columns(self.c, t), t)

    def test_the_other_name_tables_go_with_the_account_and_are_exported(self):
        c = self.c
        uid = c.execute("INSERT INTO users(username,password) VALUES('lin','x')").lastrowid
        other = c.execute("INSERT INTO users(username,password) VALUES('ma','x')").lastrowid
        for t, col in ad.ACCOUNT_COLUMNS.items():
            for who in (uid, other, 0):  # 0: the site's own total
                c.execute(f'INSERT INTO "{t}"("{col}") VALUES(?)', (who,)) if t.startswith('lexicon') else \
                    c.execute(f'INSERT INTO "{t}"(day, "{col}", chars) VALUES(?,?,?)', ('2026-11-26', who, 120))
        c.commit()
        got = json.loads(ad.records(c, c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()))
        for t, col in ad.ACCOUNT_COLUMNS.items():
            self.assertEqual([r[col] for r in got['tables'][t]], [uid], t)
            self.assertIn(t, got['目录'])
        ad.forget(c, uid)
        for t, col in ad.ACCOUNT_COLUMNS.items():
            left = sorted(r[0] for r in c.execute(f'SELECT "{col}" FROM "{t}" WHERE "{col}" IS NOT NULL'))  # (the seeded 词库 has none)
            self.assertEqual(left, [0, other], t)  # only that account's rows

    def test_rows_left_by_deleted_accounts_are_found_then_deleted(self):
        c = self.c
        uid = c.execute("INSERT INTO users(username,password) VALUES('lin','x')").lastrowid
        c.execute('INSERT INTO tts_usage(day, who, chars) VALUES(?,?,?)', ('2026-11-20', 999, 50))  # an account deleted before
        c.execute('INSERT INTO tts_usage(day, who, chars) VALUES(?,?,?)', ('2026-11-20', uid, 50))
        c.execute('INSERT INTO tts_usage(day, who, chars) VALUES(?,?,?)', ('2026-11-20', 0, 100))
        c.execute('INSERT INTO ai_usage(user_id, day, count) VALUES(?,?,?)', (998, '2026-11-20', 3))
        c.commit()
        self.assertEqual(ad.orphans(c), {'tts_usage': 1, 'ai_usage': 1})
        self.assertEqual(c.execute('SELECT COUNT(*) FROM tts_usage').fetchone()[0], 3)  # counting deletes nothing
        ad.orphans(c, apply=True)
        self.assertEqual(sorted(r[0] for r in c.execute('SELECT who FROM tts_usage')), [0, uid])
        self.assertEqual(ad.orphans(c), {})


if __name__ == '__main__':
    unittest.main()
