"""AI 常用搭配和近义、易混词 (word_extras, 2026-11-25): the program's checks, one row per item, the reviewer's doubts kept
hidden, and a batch from writing to the card, with the models stood in for."""
import json, os, sqlite3, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import next_service as nx, topic_guard, word_extras as wx, ai_routes  # noqa: E402

GOOD = {'word': 'borrow',
        'collocations': [{'en': 'borrow a book from the library', 'zh': '从图书馆借书'}, {'en': 'borrow money from a friend', 'zh': '向朋友借钱'},
                         {'en': 'borrow an idea', 'zh': '借用一个想法'}],
        'near': [{'word': 'lend', 'zh': '借出', 'diff': 'lend 是借给别人，borrow 是借进来'}]}


class CheckTests(unittest.TestCase):
    def check(self, item, w='borrow'):
        return wx.check(w, item, nx, topic_guard.hits)

    def test_good_items_pass(self):
        keep, why = self.check(GOOD)
        self.assertEqual([k for k, *_ in keep], ['colloc', 'colloc', 'colloc', 'near']); self.assertEqual(why, [])

    def test_what_the_sample_showed_is_left_out(self):  # A0 and B2 on the 50-word sample
        item = {'word': 'penny', 'collocations': [{'en': 'a penny', 'zh': '一便士'}, {'en': 'penny coin', 'zh': '便士硬币'}],
                'near': [{'word': 'coin', 'zh': '硬币', 'diff': '硬币' * 13}]}
        keep, why = self.check(item, 'penny')
        self.assertEqual([e for _, e, *_ in keep], ['penny coin'])
        self.assertTrue(any('只是这个词本身' in w for w in why)); self.assertTrue(any('超过 25 个字' in w for w in why))
        keep, why = self.check({'word': 'curl', 'near': [{'word': 'twist', 'zh': 'twists 扭转', 'diff': '扭转和卷曲不同'}]}, 'curl')
        self.assertEqual(keep, []); self.assertTrue(any('夹英文' in w for w in why))

    def test_a_difference_is_measured_as_it_reads(self):  # sample 2: affect / effect fell to a count of letters
        self.assertEqual(wx.units('affect 通常作动词，effect 通常作名词'), 13)  # 2 words + 11 characters
        keep, why = self.check({'near': [{'word': 'affect', 'zh': '影响', 'diff': 'affect 通常作动词，effect 通常作名词'}]}, 'effect')
        self.assertEqual([e for _, e, *_ in keep], ['affect'])

    def test_what_the_owner_review_found_is_not_written_again(self):  # 2026-11-26: the 16 doubts in the review sheet
        item = {'collocations': [{'en': 'win an election', 'zh': '赢得选举'}, {'en': 'and win the game', 'zh': '然后赢了'},
                                 {'en': 'win a prize', 'zh': '获奖'}]}
        keep, why = self.check(item, 'win')
        self.assertEqual([e for _, e, *_ in keep], ['win a prize'])
        self.assertIn('政治、宗教、军事类', why[0]); self.assertIn('半句话', why[1])
        c = sqlite3.connect(':memory:'); wx.schema(c)
        wx.store(c, 'sensible', [('colloc', 'sensible decision', '明智的决定', ''), ('colloc', 'a sensible decision', '明智的决定', '')], 'm')
        wx.store(c, 'hot', [('colloc', 'hot and spicy', '又热又辣', ''), ('colloc', 'a hot drink', '一杯热饮', '')], 'm')
        wx.store(c, 'audience', [('colloc', 'a large audience', '很多观众', '')], 'm')  # the English was fine, the Chinese was not
        self.assertEqual([x['en'] for x in wx.shown(c, 'sensible')], ['a sensible decision'])
        self.assertEqual([x['en'] for x in wx.shown(c, 'hot')], ['a hot drink'])
        self.assertEqual([x['en'] for x in wx.shown(c, 'audience')], ['a large audience'])
        why = json.loads(c.execute("SELECT flagged FROM vocab_extras WHERE en='hot and spicy'").fetchone()[0])
        self.assertEqual(why, {'by': 'review-2026-11-26', 'why': '中文不对，是香辣'})
        self.assertEqual(len(wx.REVIEWED_OUT), 16)
        text = wx.write_messages([('sensible', '易混', '明智的', False)])[1]['content']
        for part in ('a sensible decision', '不写半句话', '不写政治、宗教、军事和战争'):
            self.assertIn(part, text)
        self.assertIn('意思和 meaning 对不上', wx.review_messages([])[1]['content'])

    def test_names_are_not_word_cards(self):
        c = sqlite3.connect(':memory:'); wx.schema(c)
        class VS:
            @staticmethod
            def book_words():
                return {'ielts': [(1, 'york'), (2, 'borrow')]}
        with patch.object(nx, 'lookup', lambda w: {'word': 'York'} if w == 'york' else {'word': w}):
            self.assertEqual(wx.pending(c, VS, ['ielts'], nx), [('borrow', 'ielts')])

    def test_near_words_must_be_other_real_words(self):
        item = {'near': [{'word': 'borrowed', 'zh': '借了', 'diff': '变形'}, {'word': 'zzqx', 'zh': '无', 'diff': '编的'},
                         {'word': 'lend money', 'zh': '借钱', 'diff': '两个词'}]}
        keep, why = self.check(item)
        self.assertEqual(keep, []); self.assertEqual(len(why), 3)

    def test_look_alike_words_are_other_words(self):  # sample 4: besides was taken for a form of beside
        for w, nw in (('beside', 'besides'), ('cloth', 'clothes'), ('sleeping', 'sleepy'), ('besides', 'beside')):
            keep, why = self.check({'near': [{'word': nw, 'zh': '另一个词', 'diff': '意思不同'}]}, w)
            self.assertEqual([e for _, e, *_ in keep], [nw], (w, nw, why))
        for w, nw in (('book', 'books'), ('borrow', 'borrowed'), ('lie', 'lying')):
            keep, why = self.check({'near': [{'word': nw, 'zh': '变形', 'diff': '只是变形'}]}, w)
            self.assertEqual(keep, [], (w, nw)); self.assertIn('就是原词', why[0])
        self.assertNotIn('wind', wx._forms('win')); self.assertIn('making', wx._forms('make'))

    def test_a_collocation_must_hold_the_word(self):
        keep, why = self.check({'collocations': [{'en': 'take out a loan', 'zh': '贷款'}]})
        self.assertEqual(keep, []); self.assertIn('不含这个词', why[0])

    def test_sensitive_items_go_one_by_one(self):
        with patch.object(topic_guard, 'hits', lambda p, dated=True: ['碰到'] if 'bet' in p.get('body', '') else []):
            keep, why = wx.check('win', {'collocations': [{'en': 'win a bet', 'zh': '打赌赢了'}, {'en': 'win a prize', 'zh': '获奖'}]},
                                 nx, topic_guard.hits)
        self.assertEqual([e for _, e, *_ in keep], ['win a prize']); self.assertIn('敏感内容', why[0])

    def test_the_prompt_carries_our_meaning_and_the_rules(self):
        m = wx.write_messages([('penny', '中考', '便士', True), ('feasible', '专四', '可行的', False)])
        text = m[1]['content']
        for part in ('中考 | penny | 便士', '冠词和介词写全', '不要凑', '不超过 20 个字', '日常生活里的搭配：penny'):
            self.assertIn(part, text)
        self.assertIn('不照搬任何一本词典', m[0]['content']); self.assertIn('真人、品牌、政治和时事', m[0]['content'])
        self.assertIn('反义词和只是同一类的词都不算', text)  # A0 on sample 2: blind came back with deaf
        self.assertIn('先写拼写或读音相近', text)  # A0 on sample 3: quiet came back with silent, not quite
        self.assertIn('不要因为意思不近就列出来', wx.review_messages([])[1]['content'])
        self.assertIn('其实是反义词', wx.review_messages([])[1]['content'])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:'); wx.schema(self.c)

    def test_one_row_per_item_once_and_a_doubt_stays_hidden(self):
        keep, _ = wx.check('borrow', GOOD, nx, topic_guard.hits)
        wx.store(self.c, 'borrow', keep, 'flow-batch-ds-flash'); wx.store(self.c, 'borrow', keep, 'flow-batch-ds-flash')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM vocab_extras').fetchone()[0], 4)
        row = self.c.execute("SELECT model, prompt, hidden FROM vocab_extras WHERE en='lend'").fetchone()
        self.assertEqual(row, ('flow-batch-ds-flash', wx.PROMPT, 0))
        n = wx.flag(self.c, [{'word': 'borrow', 'kind': 'colloc', 'en': 'borrow an idea', 'why': '不常用'}, 'junk'])
        self.assertEqual(n, 1)
        self.assertEqual([x['en'] for x in wx.shown(self.c, 'borrow')], ['borrow a book from the library', 'borrow money from a friend', 'lend'])
        why = json.loads(self.c.execute("SELECT flagged FROM vocab_extras WHERE en='borrow an idea'").fetchone()[0])
        self.assertEqual(why, {'by': 'qwen-plus', 'why': '不常用'})

    def test_each_row_keeps_one_id_for_good(self):  # B2: 「这条不对」 and the takedown go by id
        keep, _ = wx.check('borrow', GOOD, nx, topic_guard.hits)
        wx.store(self.c, 'borrow', keep, 'flow-batch-ds-flash')
        first = {x['en']: x['id'] for x in wx.shown(self.c, 'borrow')}
        self.assertEqual(len(set(first.values())), 4)
        wx.store(self.c, 'borrow', keep, 'flow-batch-ds-flash')  # a second run: same rows, same ids
        self.assertEqual({x['en']: x['id'] for x in wx.shown(self.c, 'borrow')}, first)
        self.c.execute('DELETE FROM vocab_extras WHERE id=?', (max(first.values()),))
        wx.store(self.c, 'penny', [('colloc', 'save every penny', '省下每一分钱', '')], 'flow-batch-ds-flash')
        self.assertGreater(wx.shown(self.c, 'penny')[0]['id'], max(first.values()))  # an id is never given again

    def test_the_weekly_look_a_takedown_and_putting_back(self):  # B2's 「这条不对」 marks, B6's console buttons
        keep, _ = wx.check('borrow', GOOD, nx, topic_guard.hits)
        wx.store(self.c, 'borrow', keep, 'flow-batch-ds-flash')
        self.assertEqual(wx.reported(self.c), [])  # B2's table not there yet
        ids = {x['en']: x['id'] for x in wx.shown(self.c, 'borrow')}
        self.c.execute('CREATE TABLE vocab_extras_flags(user_id INTEGER, extra_id INTEGER, created REAL, note TEXT)')
        self.c.executemany('INSERT INTO vocab_extras_flags VALUES(?,?,?,?)', [
            (1, ids['lend'], 10.0, '区别反了'), (2, ids['lend'], 20.0, ' '), (3, ids['lend'], 30.0, None),
            (3, ids['borrow an idea'], 40.0, '不常用')])
        top = wx.reported(self.c)
        self.assertEqual([(x['en'], x['users'], x['last'], x['notes']) for x in top],
                         [('lend', 3, 30.0, ['区别反了']), ('borrow an idea', 1, 40.0, ['不常用'])])
        self.assertEqual([x['en'] for x in wx.reported(self.c, since=25.0)], ['borrow an idea', 'lend'])  # one mark each since then
        self.assertEqual(wx.take_down(self.c, ids['lend'], '区别说错', 'admin@flow'), 1)
        self.assertNotIn('lend', [x['en'] for x in wx.shown(self.c, 'borrow')])
        lend = [x for x in wx.reported(self.c) if x['en'] == 'lend'][0]
        self.assertTrue(lend['hidden']); self.assertTrue(lend['by_admin'])  # still listed, so the console offers 「放回」
        self.assertEqual(wx.put_back(self.c, ids['lend'], 'admin@flow'), 1)
        self.assertIn('lend', [x['en'] for x in wx.shown(self.c, 'borrow')])
        wx.flag(self.c, [{'word': 'borrow', 'kind': 'colloc', 'en': 'borrow an idea', 'why': '不常用'}])  # the reviewer hid it
        self.assertEqual(wx.put_back(self.c, ids['borrow an idea'], 'admin@flow'), 0)  # the console does not undo the reviewer
        self.assertEqual(wx.take_down(self.c, ids['borrow an idea'], '再下架一次', 'admin@flow'), 0)  # nor writes over it,
        self.assertEqual(wx.put_back(self.c, ids['borrow an idea'], 'admin@flow'), 0)  # so 放回 cannot show it after all
        why = json.loads(self.c.execute('SELECT flagged FROM vocab_extras WHERE id=?', (ids['borrow an idea'],)).fetchone()[0])
        self.assertEqual(why, {'by': 'qwen-plus', 'why': '不常用'})
        self.assertEqual(wx.take_down(self.c, ids['lend'], '区别说错', 'admin@flow'), 1)  # taken down again: a new reason
        self.assertEqual(wx.take_down(self.c, ids['lend'], '区别说反了', 'admin@flow'), 1)
        self.assertEqual(json.loads(self.c.execute('SELECT flagged FROM vocab_extras WHERE id=?', (ids['lend'],)).fetchone()[0])['why'], '区别说反了')
        self.assertEqual(wx.take_down(self.c, 99999, 'x', 'admin@flow'), 0)
        self.assertFalse([x for x in wx.reported(self.c) if x['en'] == 'borrow an idea'][0]['by_admin'])
        wx.store(self.c, 'borrow', keep, 'flow-batch-ds-flash')  # a rerun does not show it again
        self.assertNotIn('borrow an idea', [x['en'] for x in wx.shown(self.c, 'borrow')])

    def test_a_batch_from_writing_to_the_card(self):
        calls = []

        def ask(messages, model=None):
            calls.append(model)
            if model is None:
                return {'items': [GOOD, {'word': 'penny', 'collocations': [{'en': 'a penny', 'zh': '一便士'}], 'near': []}]}, 'flow-batch-ds-flash'
            return {'problems': [{'word': 'borrow', 'kind': 'near', 'en': 'lend', 'why': '测试'}]}, model
        with patch.object(wx, 'ask', ask), patch.dict(os.environ, {'FLOW_BACKUP_AI_MODEL': 'flow-text-qwen-plus', 'FLOW_TEXT_AI_MODEL': 'flow-text'}), \
                patch('chat_service.backup_model', lambda: 'flow-text-qwen-plus'):
            r = wx.run_batch(self.c, [('borrow', '四级', '借', False), ('penny', '中考', '便士', True)], nx, topic_guard.hits)
        self.assertEqual(r, {'words': 2, 'rows': 4, 'left_out': 1, 'hidden': 1})
        self.assertEqual(calls, [None, 'flow-text-qwen-plus'])  # the writer on the batch lane, then the reviewer
        self.assertEqual([x['en'] for x in wx.shown(self.c, 'borrow') if x['kind'] == 'near'], [])
        self.assertEqual(wx.shown(self.c, 'penny'), [])  # nothing passed: the card shows nothing, nothing made up

    def test_the_database_is_written_only_after_both_model_calls(self):  # 正式版 2026-11-26: 「database is locked」
        seen = []

        def ask(messages, model=None):
            seen.append((model, self.c.in_transaction))
            return ({'items': [GOOD]}, 'flow-batch-ds-flash') if model is None else ({'problems': []}, model)
        with patch.object(wx, 'ask', ask), patch('chat_service.backup_model', lambda: 'flow-text-qwen-plus'):
            r = wx.run_batch(self.c, [('borrow', '四级', '借', False)], nx, topic_guard.hits)
        self.assertEqual(seen, [(None, False), ('flow-text-qwen-plus', False)])  # no write lock held while a model answers
        self.assertEqual((r['rows'], self.c.in_transaction), (4, False))
        self.assertEqual(len(wx.shown(self.c, 'borrow')), 4)

    def test_no_reviewer_no_items(self):  # the guide (B2's #429): every item on a card was read by a second model
        calls = []

        def ask(messages, model=None):
            calls.append(model)
            return {'items': [GOOD]}, 'flow-batch-ds-flash'
        with patch.object(wx, 'ask', ask), patch('chat_service.backup_model', lambda: ''):
            with self.assertRaises(RuntimeError):
                wx.run_batch(self.c, [('borrow', '四级', '借', False)], nx, topic_guard.hits)
            self.assertEqual(calls, [])  # the writer is not asked either: nothing paid for, nothing stored
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM vocab_extras').fetchone()[0], 0)
            r = wx.run_batch(self.c, [('borrow', '四级', '借', False)], nx, topic_guard.hits, review=False)  # samples only
        self.assertEqual((r['rows'], calls), (4, [None]))


class NightlyTests(unittest.TestCase):  # A0 2026-11-26: one nod from the owner for the whole run, paused on anything odd
    def setUp(self):
        import datetime, subprocess, console_ops, vertex_auth
        self.d = Path(tempfile.mkdtemp()); self.started = []
        self.night = lambda day, h=3: datetime.datetime(2026, 11, day, h, 0, tzinfo=ai_routes.TZ).timestamp()
        for target, attr, value in ((console_ops, 'data_dir', lambda: self.d), (vertex_auth, 'ai_enabled', lambda: True),
                                    (ai_routes, 'batch_stop', lambda c=None: False),
                                    (subprocess, 'Popen', lambda cmd, **kw: self.started.append(cmd))):
            p = patch.object(target, attr, value); p.start(); self.addCleanup(p.stop)
        self.plan = {'books': ['zk', 'gk'], 'max_yuan': 3, 'nights': 3, 'from': '2026-11-27', 'until': '2026-12-05'}

    def tick(self, day, h=3):
        return wx.nightly(None, self.night(day, h))

    def plan_now(self):
        return json.loads((self.d / 'word-extras' / 'plan.json').read_text())

    def night_report(self, day, **r):
        (self.d / 'word-extras' / f'2026-11-{day}.json').write_text(json.dumps(r))
        (self.d / 'word-extras' / 'running.json').unlink()

    def test_nothing_without_the_owner_plan_or_by_day(self):
        self.assertFalse(self.tick(27))
        wx._write(self.d / 'word-extras' / 'plan.json', self.plan)
        self.assertFalse(self.tick(27, h=14)); self.assertEqual(self.started, [])

    def test_one_run_a_night_until_the_words_are_done(self):
        wx._write(self.d / 'word-extras' / 'plan.json', self.plan)
        self.assertTrue(self.tick(27)); self.assertFalse(self.tick(27))  # once a night
        cmd = self.started[0]
        self.assertEqual(cmd[cmd.index('--books') + 1], 'zk,gk'); self.assertEqual(cmd[cmd.index('--max-yuan') + 1], '3.0')
        self.assertTrue(cmd[cmd.index('--output') + 1].endswith('2026-11-27.json'))
        self.night_report(27, words=3400, rows=11000, left_out=300, hidden=900, failed=0, yuan=2.9, pending_after=4600)
        self.assertTrue(self.tick(28))
        self.night_report(28, words=4600, rows=15000, left_out=400, hidden=1200, failed=1, yuan=2.95, pending_after=0)
        self.assertFalse(self.tick(29)); self.assertEqual(self.plan_now()['done'], '2026-11-29'); self.assertEqual(len(self.started), 2)

    def test_an_odd_night_pauses_the_run(self):
        wx._write(self.d / 'word-extras' / 'plan.json', self.plan)
        self.assertTrue(self.tick(27))
        self.night_report(27, words=3000, rows=4000, left_out=3000, hidden=100, failed=0, yuan=2.0, pending_after=5000)
        self.assertFalse(self.tick(28)); self.assertEqual(self.plan_now()['paused'], '程序拦下的超过三成')
        self.assertFalse(self.tick(29)); self.assertEqual(len(self.started), 1)  # waits for the owner, never retries alone
        self.assertEqual(wx.anomaly({'error': 'boom'}, self.plan), '运行出错：boom')
        self.assertIn('超过每晚上限', wx.anomaly({'yuan': 4.5}, self.plan))

    def test_a_night_without_a_reviewer_pauses_the_plan(self):
        wx._write(self.d / 'word-extras' / 'plan.json', self.plan)
        self.assertTrue(self.tick(27))
        out = self.started[0][self.started[0].index('--output') + 1]
        with patch.object(wx, '_main', lambda a: wx.reviewer()), patch('chat_service.backup_model', lambda: ''):
            with self.assertRaises(RuntimeError):
                wx.main(['--output', out])  # what the child process does when the site has no reviewer set
        (self.d / 'word-extras' / 'running.json').unlink()
        self.assertFalse(self.tick(28))
        self.assertTrue(self.plan_now()['paused'].startswith('运行出错：RuntimeError: 没有复查模型'))
        self.assertEqual(len(self.started), 1)  # waits for B7 and the owner

    def test_the_first_night_is_looked_at_first(self):
        wx._write(self.d / 'word-extras' / 'plan.json', {**self.plan, 'hold_after_first': True})
        self.assertTrue(self.tick(27))
        self.night_report(27, words=3400, rows=11000, left_out=300, hidden=900, failed=0, yuan=2.9, pending_after=4600)
        self.assertFalse(self.tick(28)); self.assertEqual(self.plan_now()['paused'], '第一晚跑完，等 B7 抽查')
        plan = self.plan_now(); plan.pop('paused'); plan.pop('paused_at'); plan['hold_after_first'] = False  # B7 has looked
        wx._write(self.d / 'word-extras' / 'plan.json', plan)
        self.assertTrue(self.tick(29)); self.assertEqual(len(self.started), 2)

    def test_the_owner_let_this_run_past_the_caps_for_now(self):  # 「暂时放行预算上限，跑完收紧」
        plan = {**self.plan, 'own_cap': True, 'first_night_yuan': 2, 'max_yuan': 8, 'total_yuan': 10, 'nights': 4}
        wx._write(self.d / 'word-extras' / 'plan.json', plan)
        with patch.object(ai_routes, 'batch_stop', lambda c=None: True):  # the site's caps would stop any other batch work
            self.assertTrue(self.tick(27))
        cmd = self.started[0]
        self.assertIn('--own-cap', cmd); self.assertEqual(cmd[cmd.index('--max-yuan') + 1], '2.0')  # a small first night
        self.night_report(27, words=2400, rows=7800, left_out=200, hidden=600, failed=0, yuan=1.98, pending_after=5600)
        self.assertTrue(self.tick(28)); self.assertEqual(self.started[1][self.started[1].index('--max-yuan') + 1], '8.0')
        self.night_report(28, words=5000, rows=16000, left_out=400, hidden=1300, failed=0, yuan=7.6, pending_after=600)
        self.assertTrue(self.tick(29)); self.assertEqual(self.started[2][self.started[2].index('--max-yuan') + 1], '0.42')  # what is left of ¥10
        self.night_report(29, words=600, rows=1900, left_out=50, hidden=150, failed=0, yuan=0.41, pending_after=0)
        self.assertFalse(self.tick(30)); self.assertIn('done', self.plan_now()); self.assertFalse(wx.own_cap_on())

    def test_the_caps_leave_out_only_that_run_and_only_while_it_lasts(self):
        c = sqlite3.connect(':memory:'); ai_routes.schema(c)
        now = time.time()
        for kind, n in (('word-extras', 7), ('fill-examples', 2), ('next-rewrite', 1)):
            for _ in range(n):
                c.execute("INSERT INTO ai_calls(ts,kind,service,model,ok,status) VALUES(?,?,?,?,?,?)", (now - 5, kind, 'text', 'flow-batch-x', 1, 200))
        with patch.object(ai_routes, 'cost', lambda *a, **k: 1.0), patch.object(ai_routes, 'budget', lambda: 5.0), \
                patch.object(ai_routes, 'batch_line', lambda: 8.0):
            self.assertTrue(ai_routes.over_budget(c)); self.assertTrue(ai_routes.batch_full(c))  # no plan: ¥10 today, ¥9 of batch
            wx._write(self.d / 'word-extras' / 'plan.json', {**self.plan, 'own_cap': True})
            self.assertFalse(ai_routes.over_budget(c)); self.assertFalse(ai_routes.batch_full(c))  # ¥3 and ¥2 without that run
            self.assertEqual(ai_routes.budget_state(c)['exempt'], 7.0)
            wx._write(self.d / 'word-extras' / 'plan.json', {**self.plan, 'own_cap': True, 'done': '2026-11-30'})
            self.assertTrue(ai_routes.over_budget(c)); self.assertTrue(ai_routes.batch_full(c))  # done: the caps are back

    def test_the_nights_and_the_date_are_a_ceiling(self):
        wx._write(self.d / 'word-extras' / 'plan.json', {**self.plan, 'nights': 1})
        self.assertTrue(self.tick(27))
        self.night_report(27, words=3400, rows=11000, left_out=300, hidden=900, failed=0, yuan=2.9, pending_after=4600)
        self.assertFalse(self.tick(28)); self.assertIn('done', self.plan_now())
        wx._write(self.d / 'word-extras' / 'plan.json', {**self.plan, 'until': '2026-11-28'})
        self.assertFalse(self.tick(29)); self.assertIn('done', self.plan_now()); self.assertEqual(len(self.started), 1)


class RouteTests(unittest.TestCase):
    def test_batch_work_on_the_batch_lane_and_outside_the_learners_stop(self):
        self.assertEqual(ai_routes.LANE_OF.get('word-extras'), 'batch')
        self.assertEqual(ai_routes.EXTRA['word-extras'][1], 'next-examples')
        self.assertIn('word-extras', ai_routes.BATCH); self.assertIn('word-extras', ai_routes.NOT_LEARNER)

    def test_the_site_loop_never_falls_over_on_it(self):
        with patch.object(wx, 'nightly', lambda c, now=None: 1 / 0), patch.object(ai_routes, 'check_budget', lambda c, now=None: None), \
                patch.object(ai_routes, 'nightly', lambda c, now=None: False):
            ai_routes.tick(sqlite3.connect(':memory:'), now=1.0)


if __name__ == '__main__':
    unittest.main()
