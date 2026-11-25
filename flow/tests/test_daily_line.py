"""今日好句 (r27): a public-domain line and a sentence from a 语流 text on alternate days, each with its meaning and
source, the text's sentence linked to it; 跟读 of a public-domain line; the card's place on 今日."""
import datetime, json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, daily_line as dl  # noqa: E402

CN = datetime.timezone(datetime.timedelta(hours=8))
at = lambda *a: datetime.datetime(*a, tzinfo=CN).timestamp()
EVEN, ODD = at(2026, 11, 24, 9), at(2026, 11, 25, 9)  # ordinals 739579 (even: a public-domain line) and 739580
JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
CSS = (Path(app.ROOT) / 'public' / 'next.css').read_text(encoding='utf-8')


class QuoteTests(unittest.TestCase):
    def test_every_public_domain_line_has_its_source_and_is_old_enough(self):
        self.assertGreaterEqual(len(dl.QUOTES), 40)
        self.assertEqual(len(dl.BY_ID), len(dl.QUOTES))  # ids are unique
        for qid, en, zh, who, work, year, level in dl.QUOTES:
            self.assertRegex(qid, r'^[a-z0-9-]+$')
            y = int(re.search(r'\d{4}', year).group())
            self.assertLess(y, 1929, qid)  # published before 1929: public domain
            self.assertTrue(re.search(r'[A-Za-z]', who) and re.search(r'[一-鿿]', who), qid)  # the author in Chinese and English
            self.assertTrue(work.startswith('《') and re.search(r'[A-Za-z]', work), qid)
            self.assertTrue(re.search(r'[一-鿿]', zh) and not re.search(r'[一-鿿]', en), qid)
            self.assertIn(level, ('A2', 'B1', 'B2', 'C1'))
            self.assertLessEqual(len(en.replace(' / ', ', ')), 160, qid)  # 收藏 takes up to 160 characters
        for banned in ('Be yourself; everyone else', 'Not all those who wander', 'I have a dream', 'Be the change'):
            self.assertFalse(any(banned in q[1] for q in dl.QUOTES), banned)  # misattributed or not public domain


class Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('lin', 'x'))
            self.uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()


class LineTests(Db):
    def test_days_take_turns_and_a_line_is_the_same_for_everyone(self):
        with app.db() as c:
            q = dl.today(c, None, 'B1', EVEN)
            self.assertEqual((q['kind'], q['label']), ('quote', '公版名句'))
            self.assertEqual(q, dl.today(c, self.uid, 'C1', EVEN))  # everyone, every level: the same line
            self.assertRegex(q['source'], r'，(约 )?\d{4}( 年)?$')
            self.assertNotIn(' / ', q['say'])  # a line break in verse is not read out
            t = dl.today(c, None, 'B1', ODD)
            self.assertEqual((t['kind'], t['label'], t['level']), ('text', '语流文章', 'B1'))
            p = json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?', (t['pack'],)).fetchone()[0])
            self.assertTrue(nx.featured(p) and not p.get('series'))
            self.assertEqual(nx.sentences(p['body'])[t['i']], t['en'])  # the text's own sentence, word for word
            self.assertIn(t['expression'].lower(), t['en'].lower())
            self.assertTrue(t['zh'].startswith('「' + t['expression'] + '」：'))
            self.assertEqual(t['href'], f"#/m/{t['pack']}/read")
            self.assertTrue(t['source'].startswith('出自《'))
            self.assertNotEqual(dl.today(c, None, 'B1', ODD + 2 * 86400)['id'], t['id'])

    def test_a_text_the_learner_studied_or_reads_today_is_not_picked(self):
        with app.db() as c:
            t = dl.today(c, self.uid, 'B1', ODD)
            nx.mark(c, self.uid, t['pack'], 'check')
            self.assertNotEqual(dl.today(c, self.uid, 'B1', ODD)['pack'], t['pack'])
            self.assertEqual(dl.today(c, None, 'B1', ODD)['pack'], t['pack'])  # a guest still gets it
            self.assertNotEqual(dl.today(c, None, 'B1', ODD, skip={t['pack']})['pack'], t['pack'])

    def test_it_comes_with_the_home_data(self):
        with app.db() as c:
            h = nx.home(c, None, 'B1')
            self.assertIn(h['line']['kind'], ('quote', 'text'))
            self.assertTrue(h['line']['en'] and h['line']['zh'] and h['line']['source'])
            if h['line']['kind'] == 'text' and h['today']:
                self.assertNotEqual(h['line']['pack'], h['today'][0]['id'])

    def test_shadowing_a_public_domain_line(self):
        import lab_service
        env = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
               'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_AI_AUDIO': '1'}
        with patch.dict(os.environ, env), app.db() as c, patch.object(lab_service, 'audio_enabled', return_value=True), \
                patch('chat_service.request_model', return_value=(json.dumps({'transcript': 'the best way out is always through',
                                                                             'issues': [], 'tip': '很好', 'fluency': 'smooth'}), 'stop')), \
                patch('audio_validation.validate_audio', return_value=b'x' * 2000):
            body, st = nx.shadow(c, self.uid, {'quote': 'frost-through', 'audio': {'mime_type': 'audio/webm', 'data': 'eA=='}, 'request_id': 'ls-test-000001'})
        self.assertEqual(st, 200, body)
        r = body['result']
        self.assertEqual((r['sentence'], r['matched'], len(r['words'])), ('The best way out is always through.', 7, 7))
        self.assertEqual(dl.sentence_of({'quote': 'no-such-line'}), None)


class PageTests(unittest.TestCase):
    def test_today_has_the_line_the_news_and_the_plan_in_that_order_and_the_week_card_under_it(self):
        for s in ('function lineCardHTML', 'function newsCardHTML', 'function bindLine', "api('/api/next/shadow'", 'data-tap="line-shadow"',
                  '今日一读</span>${aiTag()}', 'const short = (innerHeight < 500 && innerWidth > innerHeight) || !!(path && h.path.back)', '${weekCardSlot()}', 'function mountWeekCards',
                  "api('/api/next/week?brief=1')"):
            self.assertIn(s, JS, s)
        order = [JS.index(s) for s in ("${short ? '' : lineCardHTML(h) + newsCardHTML(news)}", '${top}', '${weekCardSlot()}')]
        self.assertEqual(order, sorted(order))
        self.assertIn("${ICON.star}收藏</button>${aiVoiceNote('AI 合成', 'span')}</div>", JS)  # the voice is synthesized: 「AI 合成」 at the end of the row (标识办法)
        for s in ('.line-card', '.lc-en', '.news-card', '.week-slot'):
            self.assertIn(s, CSS, s)


if __name__ == '__main__':
    unittest.main()
