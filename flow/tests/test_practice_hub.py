"""r18: one place for every kind of practice (the 练习 tab), and a weekly report that also counts easy reading,
speaking scenes and how the ability radar moved."""
import os, re, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app  # noqa: E402

SRC = ROOT / 'public' / 'src' / 'next'
DAY = 86400


class PracticeHubTests(unittest.TestCase):
    def test_the_practice_tab_opens_the_hub_and_its_tiles_open_real_pages(self):
        html = (ROOT / 'public' / 'next.html').read_text(encoding='utf-8')
        self.assertIn('href="#/practice" data-nav="practice"', html)
        shell = (SRC / '02-shell.js').read_text(encoding='utf-8')
        self.assertIn("name === 'practice'", shell); self.assertIn("name === 'guide'", shell)
        known = set(re.findall(r"name === '([a-z]+)'", shell)) | {''}
        hub = (SRC / '49-practice.js').read_text(encoding='utf-8')
        tiles = re.findall(r"\['(#/[^']*)', '([^']+)'", hub)
        self.assertGreaterEqual(len(tiles), 15)  # 简洁化: 今天的材料 (= 今日) and 看进步 (= 我的 → 进步) are no longer repeated here
        for href, title in tiles:
            self.assertIn(href[2:].split('/')[0], known, title)
        # r20: four tabs; the grammar map has no tab of its own and is the 语法 group's wide card in the hub
        self.assertNotIn('data-nav="graph"', html)
        self.assertEqual(re.findall(r'data-nav="([a-z]+)"', html), ['today', 'practice', 'cards', 'me'])
        self.assertIn("['#/graph', '知识图谱', '44 个语法点按顺序连成路线，点亮一个学一个', 'map']", hub)
        for name in ('graph', 'mix', 'placement'):
            self.assertIn(f"name === '{name}') {{ setNav('practice')", shell)
        # 我的 is a grouped list: progress, settings, account and help; practice lives in its tab, not in a list here
        me = (SRC / '81-me.js').read_text(encoding='utf-8')
        for href in ('#/radar', '#/growth', '#/report', '#/cards/mistake', '#/welcome/edit', '#/guide'):
            self.assertIn(f"grow('{href}'", me)
        self.assertNotIn('#/easy', me); self.assertNotIn('abilityHTML', me)

    def test_the_built_script_carries_the_hub_and_the_guide(self):
        js = (ROOT / 'public' / 'next.js').read_text(encoding='utf-8')
        self.assertIn('async function practiceView()', js); self.assertIn('async function guideView(id)', js)
        self.assertIn('function practiceTip(radar, due)', js)


class WeeklyReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'r.db'); self.p.start()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'x'))
            self.uid = c.execute("SELECT id FROM users WHERE username='learner'").fetchone()[0]

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup()

    def test_an_empty_week_still_has_every_section(self):
        import skills_service as sk
        with app.db() as c:
            r = sk.report(c, self.uid)
        self.assertEqual(r['easy'], {'texts': 0, 'words': 0, 'wpm': None, 'wpm_before': None})
        self.assertEqual(r['speaking'], {'scenes_week': 0, 'scenes_done': 0, 'scenes_total': 12})
        self.assertEqual(r['radar']['moves'], []); self.assertEqual(r['radar']['tests_week'], 0)

    def test_easy_reading_scenes_and_the_radar_are_counted_for_the_week(self):
        import skills_service as sk, ability_radar as ar
        now = time.time()
        with app.db() as c:
            for ago, words, wpm in ((1, 400, 130), (2, 300, 120), (10, 350, 100)):  # the last one is in the week before
                c.execute("INSERT INTO next_easy_reads(user_id,pack,words,seconds,wpm,rating,created) VALUES(?,?,?,?,?,'ok',?)",
                          (self.uid, 'p', words, 180, wpm, now - ago * DAY))
            for ago, scene in ((1, 'cafe-order'), (2, 'ask-way'), (20, 'hotel-check-in'), (1, 'not-a-scene')):
                c.execute("INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(?,?,?,?,?,?,?)",
                          (self.uid, 'speaking', 'dialog', 0.8, 'B1', 'scene-' + scene, now - ago * DAY))
            ar.set_goals(c, self.uid, {'goals': {'reading': 'B2', 'speaking': 'B1'}})
            ar.record(c, self.uid, 'reading', 50, now=now - 12 * DAY)
            ar.record(c, self.uid, 'reading', 60, now=now - DAY)
            ar.record(c, self.uid, 'speaking', 40, now=now - DAY)
            c.commit()
            r = sk.report(c, self.uid, now)
        self.assertEqual(r['easy']['texts'], 2); self.assertEqual(r['easy']['words'], 700)
        self.assertEqual(r['easy']['wpm'], 125); self.assertEqual(r['easy']['wpm_before'], 100)
        self.assertEqual(r['speaking'], {'scenes_week': 2, 'scenes_done': 3, 'scenes_total': 12})
        moves = {m['id']: m for m in r['radar']['moves']}
        self.assertGreater(moves['reading']['now'], moves['reading']['before'])  # 60 against 50 a week and more ago
        self.assertIn('speaking', moves); self.assertNotIn('listening', moves)  # speaking was estimated from practice before; listening never measured
        self.assertEqual(r['radar']['tests_week'], 2); self.assertTrue(r['radar']['goals_chosen'])

    def test_the_weekly_email_mentions_reading_speaking_and_what_went_up(self):
        import skills_service as sk, ability_radar as ar, datetime, next_service as nx
        sunday = datetime.datetime(2026, 11, 22, 20, 5, tzinfo=nx.TZ).timestamp()
        sent = []
        with app.db() as c:
            if 'email' not in {x[1] for x in c.execute('PRAGMA table_info(users)')}:
                self.skipTest('no email column in this schema')
            c.execute("UPDATE users SET email='l@example.com' WHERE id=?", (self.uid,))
            c.execute('INSERT INTO next_reminders(user_id,hour,enabled,updated) VALUES(?,?,1,?)', (self.uid, 20, sunday))
            c.execute("INSERT INTO next_easy_reads(user_id,pack,words,seconds,wpm,rating,created) VALUES(?,?,?,?,?,'ok',?)", (self.uid, 'p', 400, 180, 130, sunday - DAY))
            c.execute("INSERT INTO next_skill_events(user_id,skill,kind,score,level,pack,created) VALUES(?,?,?,?,?,?,?)",
                      (self.uid, 'speaking', 'dialog', 0.8, 'B1', 'scene-cafe-order', sunday - DAY))
            ar.record(c, self.uid, 'reading', 50, now=sunday - 12 * DAY)
            ar.record(c, self.uid, 'reading', 60, now=sunday - DAY)
            c.commit()
            n = sk.send_weekly(c, sunday, send=lambda to, subject, body: sent.append(body))
        self.assertEqual(n, 1)
        self.assertIn('· 轻松读：1 篇，共 400 个词，每分钟 130 词', sent[0])
        self.assertIn('· 口语情景：练了 1 个', sent[0])
        self.assertRegex(sent[0], r'· 能力雷达上涨：阅读 \d+→\d+')


if __name__ == '__main__':
    unittest.main()
