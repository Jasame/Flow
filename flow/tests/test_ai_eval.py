"""批改考题集 (ai_eval.py): the questions hold together, a right marking passes, and the ways a model gets marking
wrong are caught: a correct sentence changed, an error left, essays scored out of order or unsteadily, a poor
translation scored like a good one, no usable answer. The model here is a stand-in; nothing of the site's data is
touched by a run."""
import json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_eval, chat_service  # noqa: E402

CASES = ai_eval.load()
BY_TEXT = {c['text']: c for c in CASES['rewrite']}
ESSAY = {c['text']: c for c in CASES['essay']}
TRANS = {c['good']: (c, True) for c in CASES['translate']} | {c['bad']: (c, False) for c in CASES['translate']}
AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'test', 'FLOW_AI_MODEL': 'stand-in', 'FLOW_AI_URL': 'https://ai.invalid/v1/chat/completions',
          'FLOW_AI_USER_DAILY_LIMIT': '1000', 'FLOW_AI_DAILY_LIMIT': '1000', 'FLOW_COOKIE_SECURE': '0'}


def between(text, start, end):
    i = text.index(start) + len(start)
    return text[i:text.index(end, i)]


def marker(keep_changed=False, leave_error=None, essay_scores=None, poor_scores=0.3, broken=False, dialog_end=None, over_correct=False):
    """A stand-in for the model that marks the way it is told; by default as a good teacher would."""
    calls = {'essay': {}}

    def request_model(messages, audio=None, grounding=False):
        chat_service.LAST['provider'] = 'text'
        if broken:
            return 'Sorry, I cannot help with that.', 'stop'
        user = messages[-1]['content']
        if '学习者写的英文：' in user:
            text = user.split('学习者写的英文：\n', 1)[1].split('\n\n')[0]
            case = BY_TEXT[text]
            if case['expect'] == 'keep':
                fixed, verdict, changes = (text.replace('.', ' indeed.').replace('?', ' indeed?') if keep_changed else text), 'natural', []
            else:
                fixed = text if case['id'] == leave_error else case['fix']
                verdict, changes = 'minor', [{'from': case['bad'][0], 'to': '…', 'why': '这里要这样改', 'node': None}]
            return json.dumps({'verdict': verdict, 'summary': '意思清楚，有一处要改。', 'corrected': fixed, 'changes': changes,
                               'versions': [{'label': '更自然', 'text': fixed, 'why': '—'}], 'used_well': [], 'keep': None}), 'stop'
        if '学习者的短文：' in user:
            case = ESSAY[user.split('学习者的短文：\n', 1)[1]]
            n = calls['essay'][case['id']] = calls['essay'].get(case['id'], 0) + 1
            s = (essay_scores or {1: [5, 5, 4, 5], 2: [3, 3, 3, 3], 3: [2, 2, 1, 2]})[case['rank']]
            s = s[n - 1] if isinstance(s[0], list) else s
            return json.dumps({'scores': dict(zip(('content', 'organization', 'accuracy', 'range'), s)), 'level': 'B1', 'comment': '结构清楚，用词准确。',
                               'paragraphs': [], 'fixes': [], 'better': [], 'model': 'A model paragraph.'}), 'stop'
        if '学习者的英文译文：' in user:
            case, good = TRANS[between(user, '学习者的英文译文：', '\n\nreference')]
            return json.dumps({'score': 0.9 if good else poor_scores, 'accuracy': '意思准确完整。' if good else '漏译了一部分。', 'fluency': '自然。',
                               'fixes': [], 'reference': case['sentence']}), 'stop'
        system = messages[0]['content']
        if '要讲解的句子：' in user:  # content: what a good model writes, fit to show a learner
            sent = user.split('要讲解的句子：', 1)[1].split('\n')[0]
            w = sent.split()
            return json.dumps({'translation': '中文翻译。', 'structure': '主干和修饰。', 'pattern': {'frame': 'not A so much as B', 'example': 'It is not luck so much as practice.'},
                               'points': [{'text': ' '.join(w[:3]), 'note': '讲解', 'node': None}, {'text': ' '.join(w[3:6]), 'note': '讲解', 'node': None}]}), 'stop'
        if '你是英语词典编辑' in system:
            ws = [line.split('：')[0] for line in user.split('\n') if '：' in line and not line.startswith('单词')]
            return json.dumps({'examples': [{'word': x, 'sentence': f'She talked about the {x} idea with her friends after class.', 'translation': '她下课后和朋友们聊了这个想法。'}
                                            for x in ws]}), 'stop'
        if '把下面的英文材料改写成' in user:
            return json.dumps({'body': user.split('原文：\n', 1)[1].split('\n\n输出 JSON')[0], 'notes': []}), 'stop'
        if '对话结束' in user:  # the summary after the last turn; dialog_end changes it (a key set to None is left out)
            end = {'summary': '整体流利，有几处小错。', 'good': ['They block out most of the noise.'],
                   'fixes': [{'from': 'they works', 'to': 'they work', 'why': '主谓一致', 'node': None}, {'from': 'It take', 'to': 'It takes', 'why': '第三人称单数', 'node': None}],
                   'expressions': [{'text': 'block out', 'meaning': '挡住'}], 'score': 0.8}
            end.update(dialog_end or {})
            return json.dumps({k: v for k, v in end.items() if v is not None}), 'stop'
        if '学习者刚说：' in user:
            said = user.split('学习者刚说：', 1)[1].split('\n')[0]
            corr = ({'original': 'they works', 'better': 'they work', 'why': '主谓一致'} if 'works' in said else
                    {'original': said[:20], 'better': 'Sure.', 'why': '更简洁'} if over_correct else None)
            return json.dumps({'reply': 'That sounds great. Where are you going?', 'correction': corr, 'hint': '说说目的地', 'say': ''}), 'stop'
        if '开始对话' in user:
            return json.dumps({'scene': '你在火车上，旁边的人戴着降噪耳机。', 'role': '乘客', 'reply': 'Hi! Do those headphones really block out the engine noise?'}), 'stop'
        if '你是专业翻译' in system:
            return json.dumps({'zh': '工程师把这叫作相消干涉，它对稳定、可以预测的声音效果最好。'}), 'stop'
        raise AssertionError('unexpected prompt')
    return request_model


class Site(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'site.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, AI_ENV)]
        for p in self.patches:
            p.start()
        app.init()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def run_with(self, **how):
        with patch.object(chat_service, 'request_model', marker(**how)):
            return ai_eval.run(CASES, say=lambda *a: None)

    def failed(self, report):
        return {x['id']: x['why'] for x in report['items'] if not x['ok']}


class QuestionTests(Site):
    def test_the_questions_hold_together(self):
        ids = [c['id'] for k in ai_eval.KINDS for c in CASES[k]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r'[a-z0-9-]{3,60}', i) for i in ids))
        fixes = [c for c in CASES['rewrite'] if c['expect'] == 'fix']
        self.assertGreaterEqual(len(fixes), 20); self.assertGreaterEqual(len(CASES['rewrite']) - len(fixes), 8)
        for c in fixes:
            self.assertTrue(ai_eval.has(c['text'], c['bad'][0]), c['id'])                  # the error is in the sentence (the rest: wrong fixes)
            self.assertFalse(any(ai_eval.has(c['text'], g) for g in c['good']), c['id'])    # and not already put right
            ok = {'result': {'verdict': 'minor', 'corrected': c['fix'], 'changes': [{}], 'summary': '中文'}}
            self.assertEqual(ai_eval.check_rewrite(c, ok, 200), [], c['id'])                # the reference fix passes its own test
        self.assertEqual(sorted(e['rank'] for e in CASES['essay']), [1, 2, 3])
        self.assertTrue(all(40 <= len(re.findall(r"[A-Za-z']+", e['text'])) <= 450 for e in CASES['essay']))
        import next_service as nx, output_service as out
        with app.db() as c:
            p = json.loads(nx._pack_row(c, None, CASES['pack'])['content'])
        sentences = {out._sentence(p, k) for k in range(60)}
        for t in CASES['translate']:
            self.assertIn(t['sentence'], sentences, t['id'])  # still in the material


class MarkingTests(Site):
    def test_a_right_marking_passes_and_the_site_data_is_not_touched(self):
        site_db = app.DB
        report = self.run_with()
        s = report['summary']
        self.assertEqual(self.failed(report), {})
        n = sum(len(CASES[k]) for k in ai_eval.KINDS) + sum(len(CASES['content'][k]) for k in ai_eval.CONTENT)
        self.assertEqual((s['passed'], s['total'], s['no_answer'], s['services']), (n, n, 0, {'text': n, 'main': 0}))
        n_content = sum(len(v) for k, v in CASES['content'].items() if k != 'about')  # every content question
        self.assertEqual(s['content'], {'passed': n_content, 'total': n_content})
        self.assertEqual(app.DB, site_db)  # put back after the run
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username='ai-eval'").fetchone())
            self.assertEqual(c.execute('SELECT COUNT(*) FROM lab_jobs').fetchone()[0], 0)
        self.assertIn('错句改对：25/25', ai_eval.describe(s, report['models']))

    def test_a_correct_sentence_changed_or_an_error_left_is_caught(self):
        report = self.run_with(keep_changed=True, leave_error='because-so')
        failed = self.failed(report)
        keeps = [c['id'] for c in CASES['rewrite'] if c['expect'] == 'keep']
        self.assertEqual(sorted(failed), sorted(keeps + ['because-so']))
        self.assertTrue(all(any(w.startswith('把正确的句子改了') for w in failed[k]) for k in keeps))
        self.assertIn('改后还留着错误：because i was tired so', failed['because-so'])
        self.assertEqual(report['summary']['rewrite_keep'], {'passed': 0, 'total': len(keeps)})

    def test_essays_out_of_order_or_unsteady_are_caught(self):
        report = self.run_with(essay_scores={1: [3, 3, 3, 3], 2: [4, 4, 4, 4], 3: [2, 2, 1, 2]})  # the middling one above the good one
        self.assertEqual([k for k in self.failed(report) if k in {e['id'] for e in CASES['essay']}], ['payment-medium'])
        self.assertTrue(any('分数没有低于' in w for w in self.failed(report)['payment-medium']))
        report = self.run_with(essay_scores={1: [[5, 5, 5, 5], [3, 3, 3, 3]], 2: [3, 3, 2, 3], 3: [1, 1, 1, 1]})
        self.assertTrue(any('两次评分差了' in w for w in self.failed(report)['door-strong']))

    def test_a_poor_translation_scored_like_a_good_one_is_caught(self):
        failed = self.failed(self.run_with(poor_scores=0.8))
        self.assertEqual(sorted(k for k in failed if k in {t['id'] for t in CASES['translate']}), sorted(t['id'] for t in CASES['translate']))

    def test_a_role_play_turn_and_its_summary_are_checked(self):
        self.assertEqual({k: v for k, v in self.failed(self.run_with()).items() if k.startswith('dialog')}, {})
        failed = self.failed(self.run_with(over_correct=True))
        self.assertEqual(set(k for k in failed if k.startswith('dialog')), {'dialog-turn-correct'})  # a right sentence was corrected
        failed = self.failed(self.run_with(dialog_end={'summary': None}))  # the beta's 2026-11-25 case: no summary, the site refuses it
        self.assertIn('dialog-end-three-errors', failed)
        self.assertIn('没有结果', failed['dialog-end-three-errors'][0])
        self.assertEqual(self.failed(self.run_with(dialog_end={'score': '0.8'})).get('dialog-end-three-errors'), None)  # a score as text is read
        failed = self.failed(self.run_with(dialog_end={'fixes': [{'from': 'they works', 'to': 'they work', 'why': '…'}]}))
        self.assertEqual(failed['dialog-end-three-errors'], ['学员的 3 处错误只指出 1 处'])

    def test_no_usable_answer_is_counted(self):
        report = self.run_with(broken=True)
        self.assertEqual(report['summary']['passed'], 0)
        self.assertGreater(report['summary']['no_answer'], 30)


class CommandTests(unittest.TestCase):
    def test_without_a_model_it_says_so(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {k: '' for k in ('FLOW_AI_MODEL', 'FLOW_AI_KEY', 'FLOW_AI_URL', 'GOOGLE_CLOUD_PROJECT')}):
            self.assertEqual(ai_eval.main(['--env-file', str(Path(d) / 'none.env')]), 2)


if __name__ == '__main__':
    unittest.main()
