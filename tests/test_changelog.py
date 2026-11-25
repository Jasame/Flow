"""tools/changelog.py: the release ledger's drafts come from git (tags, REQUEST, merge commits), and each release is
appended once to LOG.md on its release branch (.github/workflows/beta.yml does it after every 内测版 release)."""
import importlib.util, json, os, subprocess, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('changelog', ROOT / 'tools' / 'changelog.py')
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)

ENV = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid', 'GIT_COMMITTER_NAME': 't',
       'GIT_COMMITTER_EMAIL': 't@example.invalid', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
MAN = 'a' * 64


class AreaTests(unittest.TestCase):
    def test_areas_follow_the_area_owners(self):
        self.assertEqual(cl.areas(['flow/vocab_service.py', 'flow/public/src/next/50-words.js']), ['单词'])
        self.assertEqual(cl.areas(['flow/corpus_data/wordbooks.json', 'flow/corpus_data/v5/x.json']), ['单词', '内容'])
        self.assertEqual(cl.areas(['xmc-admin/admin.js', 'flow/tests/test_classes.py', 'flow/app.py']), ['后台和班级'])
        self.assertEqual(cl.areas(['flow/tests/test_x.py']), ['测试'])  # only tests: then it counts
        self.assertEqual(cl.areas(['flow/app.py']), ['网站其他'])
        self.assertEqual(cl.areas(['flow/upgrade.sh', 'tools/release-files.txt', 'flow/tts_service.py']), ['听和说'])
        self.assertEqual(cl.areas(['.github/workflows/beta.yml', 'tools/changelog.py', 'docs/releases.md']), ['发版和构建'])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        for k in ('GITHUB_RUN_ID', 'GITHUB_REPOSITORY'):
            os.environ.pop(k, None)
        self.remote, self.repo = base / 'origin.git', base / 'repo'
        self.sh('git', 'init', '-q', '--bare', str(self.remote), cwd=base)
        self.sh('git', 'init', '-q', '-b', 'main', str(self.repo), cwd=base)
        self.sh('git', 'remote', 'add', 'origin', str(self.remote))
        self.commit('flow/app.py', 'start')
        self.first = self.sha('HEAD')
        self.m5 = self.merge(5, 'words', {'flow/vocab_service.py': 'x'}, '单词：积压时停新词')
        self.m6 = self.merge(6, 'console', {'xmc-admin/admin.js': 'x', 'flow/tests/test_c.py': 'x'}, '后台：学员详情')
        # 内测版 b1 = the first commit itself; b2 = a build commit of m6 (main + the files a release builds)
        self.sh('git', 'checkout', '-q', '-b', 'build', self.m6)
        self.commit('flow/public/next.js', 'release build of m6')
        self.build = self.sha('HEAD')
        self.sh('git', 'checkout', '-q', 'main')
        # the request branches hold only REQUEST, one commit per release, each tagged (as tools/deploy.sh writes them)
        self.request('release-beta', 'b1', f'{self.first} {MAN} e2e light', f'release b1: {self.first[:12]} (main)')
        self.request('release-beta', 'b2', f'{self.build} {MAN} e2e light',
                     f'release b2: {self.build[:12]} = build of {self.m6[:12]} (main)')
        self.request('release', 'r1', f'{self.build} {MAN} e2e', f'release r1: {self.build[:12]} = build of {self.m6[:12]} (main)')
        self.sh('git', 'push', '-q', 'origin', 'main', 'release', 'release-beta', '--tags')
        self.root = mock.patch.object(cl, 'ROOT', str(self.repo))
        self.root.start()

    def tearDown(self):
        self.root.stop()
        self.env.stop()
        self.tmp.cleanup()

    def sh(self, *cmd, cwd=None):
        return subprocess.run(cmd, cwd=cwd or self.repo, check=True, capture_output=True, text=True).stdout.strip()

    def request(self, branch, tag, line, subject):
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=self.repo, input=line + '\n', check=True,
                              capture_output=True, text=True).stdout.strip()
        tree = subprocess.run(['git', 'mktree'], cwd=self.repo, input=f'100644 blob {blob}\tREQUEST\n', check=True,
                              capture_output=True, text=True).stdout.strip()
        parent = subprocess.run(['git', 'rev-parse', '-q', '--verify', f'refs/heads/{branch}'], cwd=self.repo,
                                capture_output=True, text=True).stdout.strip()
        commit = self.sh('git', 'commit-tree', tree, *(['-p', parent] if parent else []), '-m', subject)
        self.sh('git', 'update-ref', f'refs/heads/{branch}', commit)
        self.sh('git', 'tag', tag, commit)

    def sha(self, ref):
        return self.sh('git', 'rev-parse', ref)

    def commit(self, path, msg):
        f = self.repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(msg)
        self.sh('git', 'add', path)
        self.sh('git', 'commit', '-qm', msg)

    def merge(self, num, branch, files, title):
        self.sh('git', 'checkout', '-q', '-b', branch)
        for path, text in files.items():
            self.commit(path, f'{branch}: {path}')
        self.sh('git', 'checkout', '-q', 'main')
        self.sh('git', 'merge', '-q', '--no-ff', branch, '-m', f'Merge pull request #{num} from Jasame/{branch}', '-m', title)
        return self.sha('HEAD')

    def status(self, tag, failed=0):
        return {'tag': tag, 'result': 'DEPLOYED', 'files': '8 files to install (1 new)', 'e2e_requested': True,
                'e2e': {'checks': 149, 'failed': failed, 'failed_names': ['b1: dialog end gives feedback'][:failed],
                        'server_errors': 0, 'light': True, 'cleanup_ok': True}}

    def test_a_build_tag_resolves_to_its_main_commit_and_lists_the_prs_since_the_last_one(self):
        self.assertEqual(cl.release('b2')['main'], self.m6)
        self.assertEqual(cl.release('b2')['build'], self.build)
        self.assertEqual(cl.release('b1')['main'], self.first)
        self.assertEqual(cl.previous('b2'), 'b1')
        got = cl.prs(self.first, self.m6)
        self.assertEqual([(p['num'], p['title'], p['areas']) for p in got],
                         [(5, '单词：积压时停新词', ['单词']), (6, '后台：学员详情', ['后台和班级'])])
        self.assertEqual(cl.tag_for_main(self.m6), 'b2')
        self.assertIsNone(cl.tag_for_main(self.m5))

    def test_entries_carry_the_e2e_result_and_production_ones_ask_for_what_only_people_can_write(self):
        beta = cl.entry('b2', self.status('b2', failed=1))
        self.assertIn('### b2 · ', beta)
        self.assertIn(f'main `{self.m6[:7]}`，构建 `{self.build[:7]}`', beta)
        self.assertIn('#5 单词：积压时停新词（单词）', beta)
        self.assertIn('轻量 e2e 148/149，没过：b1: dialog end gives feedback', beta)
        self.assertNotIn('用户放行', beta)
        prod = cl.entry('r1', None)
        self.assertIn('内测版上同一个构建：b2', prod)
        for todo in ('学员能看到的变化', '用户放行的原话', '出过的问题和处理'):
            self.assertIn(todo, prod)
        self.assertIn('没取到', prod)  # no deploy-status for this tag

    def test_record_appends_once_to_the_branch_log_and_rows_read_it_back(self):
        cl.record('b2', self.status('b2'), push=True)
        cl.record('b2', self.status('b2'), push=True)  # a second run (a rerun of the workflow) adds nothing
        log = self.sh('git', '--git-dir', str(self.remote), 'show', 'release-beta:LOG.md')
        self.assertEqual(log.count('### b2 '), 1)
        self.assertIn('- 自检：DEPLOYED，装了 8 个文件（1 个新的）；轻量 e2e 149/149，服务器报错 0', log)
        # the request file and the tags are untouched: the server and deploy.sh read only those
        self.assertEqual(self.sh('git', '--git-dir', str(self.remote), 'show', 'b2:REQUEST'),
                         f'{self.build} {MAN} e2e light')
        row = cl.rows('b1', 'b2').splitlines()[0]  # newest first, like the table
        self.assertTrue(row.startswith(f'| b2 | '), row)
        self.assertIn(f'| `{self.m6[:7]}` | #5 #6 | 轻量 e2e 149/149，服务器报错 0 |', row)

    def test_the_reason_a_check_failed_is_logged_when_the_server_gives_it(self):
        d = self.status('b2', failed=1)
        self.assertIn('没过：b1: dialog end gives feedback，', cl.checks(d))  # an older autodeploy: names only
        d['e2e']['failed_details'] = ['b1: dialog end gives feedback: AI returned no summary (502)']
        self.assertIn('没过：b1: dialog end gives feedback: AI returned no summary (502)，', cl.checks(d))

    def test_status_must_be_for_the_same_tag(self):
        f = Path(self.tmp.name) / 'status.json'
        f.write_text(json.dumps(self.status('b3')))
        self.assertIsNone(cl.status('b2', str(f)))
        f.write_text(json.dumps(self.status('b2')))
        self.assertEqual(cl.status('b2', str(f))['tag'], 'b2')


if __name__ == '__main__':
    unittest.main()
