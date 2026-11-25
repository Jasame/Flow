"""The release test and the day's AI stop (2026-11-25, 语流 A5): once the site answers ai_day_full, a check that fails
right after it on the same thread is recorded as skipped, not failed, so a full day (¥10) never blocks a release or a
fix. Anything else still fails."""
import importlib.util, io, json, sys, threading, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qa_e2e', ROOT / 'tools' / 'qa_e2e.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class DayFullTests(unittest.TestCase):
    def setUp(self):
        qa.CHECKS.clear(); qa.NOTES.clear(); qa.DAY_FULL.clear(); qa.LAST_AI.full = False

    def ai(self, status, body):
        cl = qa.Client('guard')
        with patch.object(qa.Client, 'post', lambda self, path, data: (status, body)), patch('sys.stdout', io.StringIO()):
            return cl.ai('/api/next/essay', {'text': 'x'}, 'es')

    def test_a_check_after_the_stop_is_skipped(self):
        self.ai(429, {'error': '今天的 AI 用量已满，北京时间早上 8 点恢复。', 'code': 'ai_day_full'})
        with patch('sys.stdout', io.StringIO()):
            qa.check('guard', 'AI marks an essay', False, None)
        self.assertEqual((qa.CHECKS[0]['ok'], qa.CHECKS[0]['skipped']), (True, True))
        self.assertIn('额度已满', qa.CHECKS[0]['detail'])
        self.assertTrue(qa.DAY_FULL.is_set())

    def test_other_failures_still_fail(self):
        for status, body in ((429, {'error': '你今天的 100 次 AI 调用已用完', 'code': ''}), (500, {'error': 'boom'})):
            self.ai(status, body)
            with patch('sys.stdout', io.StringIO()):
                qa.check('guard', 'AI marks an essay', False, None)
        self.assertEqual([(x['ok'], x['skipped']) for x in qa.CHECKS], [(False, False), (False, False)])
        self.assertFalse(qa.DAY_FULL.is_set())

    def test_the_mark_is_per_thread_and_cleared_by_the_next_answer(self):
        self.ai(429, {'code': 'ai_day_full'})
        other = []
        t = threading.Thread(target=lambda: other.append(getattr(qa.LAST_AI, 'full', False))); t.start(); t.join()
        self.assertEqual(other, [False])  # another learner thread is not excused
        self.ai(200, {'result': {}})
        with patch('sys.stdout', io.StringIO()):
            qa.check('guard', 'something checked after a normal answer', False, None)
        self.assertFalse(qa.CHECKS[0]['ok'])


if __name__ == '__main__':
    unittest.main()
