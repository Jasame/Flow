"""The overview's AI 模型 (2026-11-26, A1: 「模型 未配置」 while AI was in use): FLOW_AI_MODEL is gone from both sites,
the models come from B7's routes (ai_routes.routes); the overview names the one most tasks use, and how many others."""
import os, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_routes, flow_admin  # noqa: E402


class OverviewModel(unittest.TestCase):
    def text(self, env, console=None):
        with patch.dict(os.environ, env, clear=False), patch('console_ops.settings', lambda: {'ai_routes': console} if console else {}):
            for k in ('FLOW_AI_MODEL', 'FLOW_AI_ROUTES', 'FLOW_TEXT_AI_MODEL'):
                if k not in env:
                    os.environ.pop(k, None)
            ai_routes._ENV.update({'raw': None, 'routes': {}, 'problem': None})
            return flow_admin.ai_model_text()

    def test_the_routes_name_the_model(self):
        self.assertEqual(self.text({'FLOW_AI_ROUTES': 'flow-text-ds-flash'}), 'flow-text-ds-flash（各项任务都用它）')
        got = self.text({'FLOW_AI_ROUTES': '*=flow-text-ds-flash,next-essay=flow-text'})
        self.assertTrue(got.startswith('flow-text-ds-flash（另有 1 种模型'), got)
        self.assertTrue(self.text({}, console={'*': 'flow-text-qwen'}).startswith('flow-text-qwen'))  # the console's routes first

    def test_nothing_set_says_so_without_a_wrong_model(self):
        self.assertEqual(self.text({}), '')
        js = (Path(flow_admin.__file__).resolve().parents[1] / 'xmc-admin' / 'admin.js').read_text(encoding='utf-8')
        self.assertNotIn("ai.model || '未配置'", js)
        self.assertIn("cache: 'no-store'", js)


if __name__ == '__main__':
    unittest.main()
