"""tools/check_undo.py: a branch squashed onto an origin/main that had moved takes the newer pull request back out
(2026-11-26: #456 undid #450); a branch that rewrites another's lines is only a note."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'check_undo.py'


class CheckUndoTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='check-undo-')
        env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 't',
               'GIT_COMMITTER_EMAIL': 't@example.com'}
        self.git = lambda *a: subprocess.run(['git', *a], cwd=self.dir, check=True, capture_output=True, text=True, env=env).stdout
        self.git('init', '-q', '-b', 'main')
        self.write('page.js', 'one\nold hold screen\nthree\n'); self.write('other.js', 'x\n')
        self.git('add', '-A'); self.git('commit', '-qm', 'start')
        self.start = self.git('rev-parse', 'HEAD').strip()
        # pull request #2 replaces a line with three, merged into main
        self.git('checkout', '-qb', 'reroute')
        self.write('page.js', 'one\nif (!consent) go(consent)\nshow the tick\nshow one button\nthree\n')
        self.git('commit', '-qam', 'reroute')
        self.git('checkout', '-q', 'main'); self.git('merge', '-q', '--no-ff', 'reroute', '-m', 'Merge pull request #2 from x/reroute')

    def write(self, name, text):
        Path(self.dir, name).write_text(text)

    def run_tool(self, head):
        return subprocess.run([sys.executable, str(TOOL), '--head', head, '--base', 'main'], cwd=self.dir, capture_output=True, text=True)

    def test_a_squash_onto_a_moved_main_is_stopped(self):
        self.git('checkout', '-qb', 'stale', self.start)  # the branch began before #2
        self.write('other.js', 'x\ny\n'); self.git('commit', '-qam', 'my work')
        self.git('reset', '--soft', 'main'); self.git('commit', '-qm', 'squashed')  # onto the main that has #2 now
        r = self.run_tool('stale')
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('UNDOES #2', r.stdout)

    def test_a_rewrite_of_anothers_lines_passes_with_a_note_at_most(self):
        self.git('checkout', '-qb', 'rewrite', 'main')
        self.write('page.js', 'one\nconsentGate()\nthree\n'); self.git('commit', '-qam', 'rewrite the gate')
        r = self.run_tool('rewrite')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn('UNDOES', r.stdout)

    def test_a_branch_that_merged_main_in_passes(self):
        self.git('checkout', '-qb', 'fresh', self.start)
        self.write('other.js', 'x\ny\n'); self.git('commit', '-qam', 'my work')
        self.git('merge', '-q', 'main', '-m', 'merge main')
        r = self.run_tool('fresh')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn('UNDOES', r.stdout)


if __name__ == '__main__':
    unittest.main()
