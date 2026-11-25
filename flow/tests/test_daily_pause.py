"""今日热点 retired (2026-11-25): the user chose 「改成不碰新闻的话题」 after 语流 23 pointed to the 互联网新闻信息服务管理规定
licence that providing news to the public needs. No news is searched for or written; the news texts written before stay
in the database (kept, not deleted) but are shown nowhere: not on 今日, in no list, not on the material page."""
import json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, daily_service as daily, next_service as nx


class DailyPauseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'p.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute("INSERT INTO users(id,username,password) VALUES(1,'learner','x')"); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'media', 'themes': [], 'minutes': 30})
        base = next(p for _, p in nx._public_packs(self.c, 'B1') if nx.featured(p))
        self.news = dict(base, id='daily-2026-11-24', daily_day='2026-11-24', title='新闻热点', purposes=['news-commentary'],
                         provenance={'sources': [{'title': 'A news site', 'url': 'https://news.example.com/a'}]})
        self.c.execute('INSERT INTO lab_packs VALUES(?,NULL,?,?,?)', (self.news['id'], 'daily', json.dumps(self.news), time.time()))
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def test_the_switch_is_on_until_the_samples_are_read(self):
        # 今日一读 waits for 语流 01 to read samples written on the 内测版 (daily_service.samples): nothing is written daily
        self.assertTrue(daily.PAUSED)
        with patch.object(daily, 'request_model') as model, patch.dict('os.environ', {'FLOW_AI_GROUNDING': '1'}):
            self.assertEqual(daily.run(self.c)['status'], 'paused')
            model.assert_not_called()
            st = daily.status(self.c)
            self.assertTrue(st['paused']); self.assertFalse(st['enabled'])

    def test_news_written_before_is_kept_but_shown_nowhere(self):
        pid = self.news['id']
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_packs WHERE id=?', (pid,)).fetchone()[0], 1)  # kept
        self.assertTrue(daily.retired(self.news))
        h = nx.home(self.c, 1)
        self.assertIsNone(h['news'])
        self.assertNotIn(pid, [m['id'] for m in h['today']])
        self.assertNotIn(pid, [rp[1]['id'] for rp in nx._public_packs(self.c)])
        self.assertIn(pid, [rp[1]['id'] for rp in nx._public_packs(self.c, with_hidden=True)])  # the console still sees it
        lib = nx.library(self.c, 1, page=1, per=500)
        self.assertNotIn(pid, [m['id'] for m in lib['items']])
        self.assertIsNone(nx._pack_row(self.c, 1, pid))  # its own page does not open either

    def test_a_topic_piece_is_not_retired(self):
        self.assertFalse(daily.retired(dict(self.news, kind='topic')))  # the no-news pieces that replace it
        self.assertFalse(daily.retired({'id': 'v5-x'}))

    def test_a_topic_text_says_where_it_comes_from_and_is_checked_for_news(self):
        topic = dict(self.news, kind='topic', title='为什么冬天的叶子会掉', provenance=None)
        o = nx.origin(topic)
        self.assertEqual((o['kind'], o['ai'], o['references']), ('topic', 'AI 生成', []))
        self.assertIn(daily.DAILY_NAME, o['label'])
        quality = __import__('quality_service')
        self.assertFalse([e for e in quality.checks(topic)['errors'] if '今日一读' in e])
        bad = dict(topic, body=topic['body'] + ' The president said so in 2024.')
        errors = [e for e in quality.checks(bad)['errors'] if '今日一读' in e]
        self.assertTrue(any('president' in e for e in errors) and any('2024' in e for e in errors), errors)


if __name__ == '__main__':
    unittest.main()
