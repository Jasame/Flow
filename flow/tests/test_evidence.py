"""周报「这周的一次进步」的数据 (r29, the user's picks 2026-11-26 with B7 and B6): every AI correction on a grammar point
noted once per output (反复出现: 14 days, at least 2 days, at least 3 different outputs; a rule-marked answer right without
help clears it), and a sentence the learner later wrote with the corrected form kept as evidence (written only, two a
point, 90 days, only for them; in the account export, gone with the account)."""
import datetime, inspect, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, progress_service as ps, skills_service as sk  # noqa: E402

DAY = 86400
CN = datetime.timezone(datetime.timedelta(hours=8))
at = lambda *a: datetime.datetime(*a, tzinfo=CN).timestamp()
NOW = at(2026, 11, 26, 12, 0)
GONE = {'from': 'have went', 'to': 'have gone', 'why': '现在完成时用过去分词', 'node': 'tense-perfect'}
ART = {'from': 'a apple', 'to': 'an apple', 'why': '元音前用 an', 'node': 'articles'}


class Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init()
        self.c = app.db()
        self.c.execute("INSERT INTO users(username,password,email) VALUES('lin','x','lin@example.test')"); self.c.commit()
        self.uid = 1

    def tearDown(self):
        self.c.close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def corrected(self, rid, when, *changes, kind='essay'):
        with patch('time.time', return_value=when):
            sk.mistakes_from_changes(self.c, self.uid, list(changes), 'I have went to the library.', 'writing', 'p1', request_id=rid, kind=kind)

    def count(self, table):
        return self.c.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?', (self.uid,)).fetchone()[0]


class CorrectionTests(Db):
    def test_each_output_notes_each_point_once_and_a_retry_adds_nothing(self):
        self.corrected('r1', NOW - DAY, GONE, ART)
        self.corrected('r1', NOW - DAY, GONE, ART)  # the same request again (a replay)
        self.corrected('r2', NOW, GONE)
        self.assertEqual(self.count('next_corrections'), 3)
        self.assertEqual(self.count('next_cards'), 2)  # the mistake book still has one card a mistake
        self.assertEqual(self.c.execute("SELECT kind FROM next_corrections WHERE source='fix:r2'").fetchone()[0], 'essay')
        no_node = dict(GONE, node=None, **{'from': 'is go', 'to': 'is going'})
        self.corrected('r3', NOW, no_node)
        self.assertEqual(self.count('next_corrections'), 3)  # nothing to count without a grammar point

    def test_a_point_recurs_in_three_outputs_on_two_days_within_fourteen(self):
        self.corrected('a', NOW - 3 * DAY, GONE)
        self.corrected('b', NOW - 3 * DAY + 60, GONE)
        self.assertEqual(ps.recurring(self.c, self.uid, NOW), [])  # twice: pointed out there and then, no more
        self.corrected('c', NOW - 3 * DAY + 120, GONE)
        self.assertEqual(ps.recurring(self.c, self.uid, NOW), [])  # three times but on one day
        self.corrected('d', NOW - DAY, GONE)
        rec = ps.recurring(self.c, self.uid, NOW)
        self.assertEqual([(r['node'], r['outputs'], r['days']) for r in rec], [('tense-perfect', 4, 2)])
        self.assertEqual(ps.recurring(self.c, self.uid, NOW + 14 * DAY), [])  # out of the window

    def test_a_right_answer_without_help_in_a_marked_question_clears_it(self):
        for k, t in enumerate((NOW - 4 * DAY, NOW - 3 * DAY, NOW - 2 * DAY)):
            self.corrected(f'x{k}', t, GONE)
        self.assertTrue(ps.recurring(self.c, self.uid, NOW))
        import event_service as ev
        ev.record(self.c, self.uid, 'tense-perfect', 'next-node:q1', 'choice', 'q1', correct=True, assisted=True, evaluator='rule', created=NOW - DAY)
        self.assertTrue(ps.recurring(self.c, self.uid, NOW))  # with help: still counts
        ev.record(self.c, self.uid, 'tense-perfect', 'next-node:q2', 'choice', 'q2', correct=True, assisted=False, evaluator='rule', created=NOW - DAY)
        self.assertEqual(ps.recurring(self.c, self.uid, NOW), [])


class EvidenceTests(Db):
    def test_a_later_written_sentence_with_the_corrected_form_is_kept_with_its_before(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        text = 'I had a busy week. Tom has gone to the library, so he will be late. We have gone over the notes.'
        self.assertEqual(ps.note_evidence(self.c, self.uid, text, [], 'rewrite', 'r9', False, NOW), 1)
        pair = ps.pairs(self.c, self.uid, NOW + 60)
        self.assertEqual(len(pair), 1)
        b, a = pair[0]['before'], pair[0]['after']
        self.assertEqual((pair[0]['node'], b['from'], b['to'], b['kind']), ('tense-perfect', 'have went', 'have gone', 'essay'))
        self.assertEqual(b['sentence'], 'I have went to the library.')
        self.assertEqual((a['sentence'], a['kind'], a['assisted']), ('We have gone over the notes.', 'rewrite', 0))

    def test_not_kept_when_this_output_was_corrected_on_that_point_or_the_form_means_nothing_alone(self):
        self.corrected('r1', NOW - 10 * DAY, GONE, dict(ART, to='the', **{'from': 'a'}))
        self.assertEqual(ps.note_evidence(self.c, self.uid, 'They have gone home.', [GONE], 'essay', 'r2', None, NOW), 0)
        self.assertEqual(ps.note_evidence(self.c, self.uid, 'Open the door.', [], 'essay', 'r3', None, NOW), 0)  # 'the' alone
        self.assertEqual(self.count('next_evidence'), 0)

    def test_two_a_point_and_ninety_days_at_most(self):
        self.corrected('r1', NOW - 100 * DAY, GONE)
        for k in range(3):
            ps.note_evidence(self.c, self.uid, f'We have gone there {k + 2} times.', [], 'essay', f'e{k}', None, NOW - 95 * DAY + k)
        self.assertEqual(self.count('next_evidence'), 2)
        ps.note_evidence(self.c, self.uid, 'She has gone out.', [], 'essay', 'e9', None, NOW)  # has gone ≠ have gone: nothing new
        ps.note_evidence(self.c, self.uid, 'They have gone out.', [], 'essay', 'e10', None, NOW)
        self.assertEqual([r[0] for r in self.c.execute('SELECT sentence FROM next_evidence')], ['They have gone out.'])  # the old two are past 90 days

    def test_a_form_the_text_itself_has_is_copied_not_known(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        text = 'The team have gone home early.'
        self.assertEqual(ps.note_evidence(self.c, self.uid, text, [], 'retell', 'r2', None, NOW, source='By six, the team have gone home early.'), 0)
        self.assertEqual(ps.note_evidence(self.c, self.uid, text, [], 'retell', 'r3', None, NOW, source='The team left early.'), 1)
        for fn, mod in (('retell', 'output_service'), ('essay', 'output_service'), ('translate', 'output_service')):
            self.assertIn("source=p.get('body', '')", inspect.getsource(getattr(__import__(mod), fn)), fn)

    def test_old_rows_go_once_a_day_for_everyone(self):
        self.corrected('old', NOW - 200 * DAY, GONE)
        self.corrected('new', NOW - DAY, ART)
        self.c.execute("INSERT INTO next_evidence(user_id,node,card,kind,sentence,source,assisted,created) VALUES(1,'tense-perfect',1,'essay','We have gone.','e',NULL,?)",
                       (NOW - 100 * DAY,)); self.c.commit()
        ps.prune(self.c, NOW)
        self.assertEqual([r[0] for r in self.c.execute('SELECT source FROM next_corrections')], ['fix:new'])
        self.assertEqual(self.count('next_evidence'), 0)
        self.assertIn("progress_service').prune(c, now)", inspect.getsource(__import__('ai_routes').tick))

    def test_only_written_answers_are_kept(self):
        src = inspect.getsource(__import__('output_service').retell)
        self.assertIn('if not audio:', src)
        self.assertLess(src.index('if not audio:'), src.index('note_evidence'))
        for fn in ('essay', 'translate'):
            self.assertIn("note_evidence(c, uid, text, r['fixes']", inspect.getsource(getattr(__import__('output_service'), fn)))
        self.assertNotIn('note_evidence', inspect.getsource(__import__('output_service').dialog))  # spoken (or chat): never kept
        self.assertNotIn('note_evidence', inspect.getsource(__import__('ielts_speaking')._record))

    def test_in_the_account_export_and_gone_with_the_account(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        ps.note_evidence(self.c, self.uid, 'We have gone over it.', [], 'essay', 'e1', None, NOW); self.c.commit()
        import account_data as ad
        tables = __import__('json').loads(ad.records(self.c, {'id': self.uid}))['tables']
        self.assertIn('next_evidence', tables); self.assertIn('next_corrections', tables)
        ad.forget(self.c, self.uid, Path(self.tmp.name))
        self.assertEqual((self.count('next_evidence'), self.count('next_corrections')), (0, 0))


if __name__ == '__main__':
    unittest.main()


class WeekProgressTests(Db):
    """周报 这周的一次进步 and 还要接着练, the Sunday mail's line, and 明天的语法复习先练它 (r29 第 3 项的页面)."""
    TITLE = '完成时与时间线索'  # tense-perfect in the grammar map

    def records(self, on):  # 按我的学习记录推荐 (我的 → 设置)
        p = patch.object(nx, 'follows_records', lambda prof: on); p.start(); self.addCleanup(p.stop)

    def test_the_pair_with_its_dates_and_practices_on_the_report(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        ps.note_evidence(self.c, self.uid, 'We have gone over the notes.', [], 'rewrite', 'r9', False, NOW)
        g = ps.week_progress(self.c, self.uid, NOW + 60)
        p = g['pair']
        self.assertEqual((p['title'], p['before']['date'], p['before']['label'], p['after']['date'], p['after']['label'], p['after']['assisted']),
                         (self.TITLE, '11月16日', '写作', '11月26日', '仿写', 0))
        self.assertIsNone(g['waiting'])
        self.assertEqual(sk.report(self.c, self.uid, NOW + 60)['progress']['pair']['node'], 'tense-perfect')

    def test_no_pair_yet_names_the_last_written_correction_and_where_to_try_again(self):
        self.assertEqual(ps.week_progress(self.c, self.uid, NOW)['waiting'], None)  # nothing corrected: the page says how it works
        self.corrected('r1', NOW - 14 * DAY, GONE)
        w = ps.week_progress(self.c, self.uid, NOW)['waiting']
        self.assertEqual((w['title'], w['date'], w['label'], w['from'], w['to'], w['sentence']),
                         (self.TITLE, '11月12日', '写作', 'have went', 'have gone', 'I have went to the library.'))
        self.assertIsNone(w['pack'])  # the text is not there (p1 was never saved): no 现在用它写一句
        self.assertIsNone(ps.week_progress(self.c, self.uid, NOW + 20 * DAY)['waiting'])  # older than WAIT_DAYS

    def test_what_was_said_is_never_shown(self):
        with patch('time.time', return_value=NOW - DAY):
            sk.mistakes_from_changes(self.c, self.uid, [GONE], 'I have went there.', 'speaking', 'p1', request_id='s1', kind='retell')
        self.assertIsNone(ps.week_progress(self.c, self.uid, NOW)['waiting'])
        ps.note_evidence(self.c, self.uid, 'They have gone home.', [], 'essay', 'e1', False, NOW)
        self.assertEqual(ps.pairs(self.c, self.uid, NOW + 60), [])

    def test_points_that_keep_coming_back_go_first_tomorrow_only_when_the_records_may_pick(self):
        import grammar_bank as gb
        art = dict(ART, node='det-article')
        for k, t in enumerate((NOW - 4 * DAY, NOW - 3 * DAY, NOW - 2 * DAY)):
            self.corrected(f'x{k}', t, art)
        self.records(True)
        rec = ps.week_progress(self.c, self.uid, NOW)['recurring']
        self.assertEqual([(r['node'], r['outputs']) for r in rec], [('det-article', 3)])
        self.assertEqual(gb.mix_nodes(self.c, self.uid, NOW)[:1], ['det-article'])
        self.records(False)  # patched over the one before
        self.assertIsNone(ps.week_progress(self.c, self.uid, NOW)['recurring'])  # advice from the records: not written
        self.assertNotIn('det-article', gb.mix_nodes(self.c, self.uid, NOW))

    def test_the_sunday_mail_names_the_point_and_never_the_sentences(self):
        self.corrected('r1', NOW - 10 * DAY, GONE)
        self.c.execute("INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,?,?)", (self.uid, 'p1', 'read', NOW - 3600))
        ps.note_evidence(self.c, self.uid, 'We have gone over the notes.', [], 'rewrite', 'r9', False, NOW - 1800)
        self.c.commit()
        subject, text, html, _ = ps.compose(self.c, self.uid, 'lin', NOW, 'https://flow.test')
        self.assertIn(f'「{self.TITLE}」之前要 AI 改，这周自己用对了一次', text)
        for s in ('library', 'have went', 'over the notes'):
            self.assertNotIn(s, text); self.assertNotIn(s, html)

    def test_the_page_and_the_guide(self):
        root = Path(__file__).resolve().parents[1] / 'public'
        js, css = (root / 'next.js').read_text(encoding='utf-8'), (root / 'src' / 'next' / '97-week-pair.css').read_text(encoding='utf-8')
        for s in ('weekPairHTML(r.progress)', '这周的一次进步', '这周还看不出来', '现在用它写一句', '还要接着练', '明天的语法复习先练它',
                  '偶尔出一次的小错，当场提示过就算了，不放在这里。', 'data-tap="week-try"', 'tryHintHTML(id)', 'S.tryNode = null'):
            self.assertIn(s, js)
        self.assertIn('.wp .wp-s s', css)
        guide = (root / 'guide' / 'guide.md').read_text(encoding='utf-8')
        for s in ('**这周的一次进步**', '**还要接着练**', '你写的句子不放进邮件'):
            self.assertIn(s, guide)


class MistakeSourceTests(Db):
    """练习记录 第 4 节 (practice-history/api.md): a fix card keeps the practice it came from (extra.rid, the request_id);
    review cards, a card opened in 错题本 and 错题本's rows carry from: {id, label, title, at} when B7's history module
    finds the record, and nothing when it does not, is not there yet, or fails."""

    def card(self):
        return self.c.execute("SELECT * FROM next_cards WHERE user_id=? AND source='mistake'", (self.uid,)).fetchone()

    def fake(self, found=True, boom=False):
        import types
        m = types.ModuleType('history_service')

        def source_of(c, uid, r, cache=None):
            if boom:
                raise RuntimeError('history down')
            rid = __import__('json').loads(r['extra'] or '{}').get('rid')
            return {'id': 'j7', 'label': '作文批改', 'title': 'A weekend I remember', 'at': NOW - DAY, 'more': 1} if found and uid == self.uid and rid == 'r1' else None
        m.source_of = source_of
        return patch.dict(sys.modules, {'history_service': m})

    def test_a_fix_card_keeps_the_first_practice_it_came_from(self):
        import json
        self.corrected('r1', NOW - DAY, GONE)
        self.corrected('r2', NOW, GONE)  # the same mistake again, in another practice: the card comes back, its source stays
        self.assertEqual(json.loads(self.card()['extra'])['rid'], 'r1')
        sk.mistakes_from_changes(self.c, self.uid, [ART], 'I ate a apple.', 'writing', 'p1')  # no request_id: no rid
        row = self.c.execute("SELECT extra FROM next_cards WHERE user_id=? AND text='an apple'", (self.uid,)).fetchone()
        self.assertNotIn('rid', json.loads(row['extra']))

    def test_from_on_the_review_card_the_opened_card_and_the_mistake_list(self):
        import vocab_service as vs
        self.corrected('r1', NOW - DAY, GONE)
        want = {'id': 'j7', 'label': '作文批改', 'title': 'A weekend I remember', 'at': NOW - DAY}
        with self.fake():
            self.assertEqual(vs.card_out(self.card(), NOW, rich=True, c=self.c)['from'], want)
            self.assertEqual(vs.detail(self.c, self.uid, self.card()['id'])[0]['card']['from'], want)
            self.assertEqual(nx.cards(self.c, self.uid, f='mistake')['items'][0]['from'], want)
        with self.fake(found=False):  # deleted, or an older card that cannot be matched: no line
            self.assertNotIn('from', vs.card_out(self.card(), NOW, rich=True, c=self.c))
            self.assertNotIn('from', nx.cards(self.c, self.uid, f='mistake')['items'][0])
        with self.fake(boom=True):  # the history failing never stops a review
            self.assertNotIn('from', vs.card_out(self.card(), NOW, rich=True, c=self.c))
        with patch.dict(sys.modules, {'history_service': None}):  # B7's module not here yet
            self.assertNotIn('from', vs.card_out(self.card(), NOW, rich=True, c=self.c))
