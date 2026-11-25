"""AI 常用搭配和近义词 (word_extras, 2026-11-25): the program's checks, one row per item, the reviewer's doubts kept
hidden, and a batch from writing to the card, with the models stood in for."""
import json, os, sqlite3, sys, tempfile, unittest
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
        with patch.object(topic_guard, 'hits', lambda p, dated=True: ['碰到'] if 'election' in p.get('body', '') else []):
            keep, why = wx.check('win', {'collocations': [{'en': 'win an election', 'zh': '赢得选举'}, {'en': 'win a prize', 'zh': '获奖'}]},
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


class RouteTests(unittest.TestCase):
    def test_batch_work_on_the_batch_lane_and_outside_the_learners_stop(self):
        self.assertEqual(ai_routes.LANE_OF.get('word-extras'), 'batch')
        self.assertEqual(ai_routes.EXTRA['word-extras'][1], 'next-examples')
        self.assertIn('word-extras', ai_routes.BATCH); self.assertIn('word-extras', ai_routes.NOT_LEARNER)


if __name__ == '__main__':
    unittest.main()
