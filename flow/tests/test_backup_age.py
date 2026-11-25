"""每日备份里的 flow.env 加密 (flow/ops.py backup, flow-backup.service at 03:15).

With FLOW_BACKUP_AGE_RECIPIENT set (the owner's age public key), /etc/flow.env goes into the backup only as flow.env.age
(age -r) and is never readable there; its private key stays with the owner, and the restore notes say to ask for it.
The database stays as it is, so the copy 杭州 pulls every day can be restored straight away. Not set: as before.
The real age is used where the machine has it (age, age-keygen); elsewhere those cases are skipped and the rest runs
with age stood in for."""
import contextlib, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ops  # noqa: E402

AGE = bool(shutil.which('age') and shutil.which('age-keygen'))
SECRET = b'FLOW_SMTP_PASSWORD=not-a-real-one\nFLOW_GATEWAY_KEY=sk-test-only\n'
REAL_RUN = subprocess.run


class BackupEnvTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_dir.name)
        self.root = self.tmp / 'site'
        (self.root / 'data').mkdir(parents=True)
        (self.root / 'app.py').write_text('# the site\n')
        with sqlite3.connect(self.root / 'data/flow.sqlite3') as c:
            c.execute('CREATE TABLE migrations(version TEXT)')
            c.execute("INSERT INTO migrations VALUES('2.1')")
            c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)')
            c.execute("INSERT INTO users(username) VALUES('owner')")
        self.env = self.tmp / 'flow.env'
        self.env.write_bytes(SECRET)
        self.umask = os.umask(0o022)  # backup() sets 0077 for the process; the test's own is put back afterwards
        os.umask(self.umask)
        self.patches = [patch.object(ops, 'ROOT', self.root), patch.object(ops, 'BACKUPS', self.tmp / 'backups'),
                        patch.object(ops, 'ENV_FILE', self.env), patch.object(ops, 'prune_deploy_copies', lambda **k: []),
                        patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': ''})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        os.umask(self.umask)
        self.tmp_dir.cleanup()

    def backup(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as said:
            folder = ops.backup(**kw)
        return folder, said.getvalue()

    def status(self):
        return json.loads((self.root / 'data/backup-status.json').read_text())

    def folders(self):
        return set((self.tmp / 'backups').glob('flow-*'))

    @staticmethod
    def stand_in(output=None, fail=None):
        """age as subprocess.run sees it: writes what age would (or `output`), or raises `fail`."""
        seen = []

        def run(cmd, **kw):
            seen.append(cmd)
            if fail:
                raise fail
            Path(cmd[cmd.index('-o') + 1]).write_bytes(ops.AGE_HEADER + b'-> X25519 stand-in\n' if output is None else output)
            return subprocess.CompletedProcess(cmd, 0, b'', b'')
        return run, seen

    def assertNoEnvKept(self, folder):
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['flow.sqlite3', 'manifest.json', 'source.tar.gz'])

    def test_without_a_recipient_flow_env_is_copied_as_before(self):
        folder, _ = self.backup()
        self.assertEqual((folder / 'flow.env').read_bytes(), SECRET)
        self.assertFalse((folder / 'flow.env.age').exists())
        self.assertEqual(json.loads((folder / 'manifest.json').read_text())['env'], 'flow.env')
        self.assertTrue(self.status()['ok'])
        self.env.unlink()  # no /etc/flow.env: nothing of it, as before
        folder, _ = self.backup()
        self.assertNoEnvKept(folder)
        self.assertIsNone(json.loads((folder / 'manifest.json').read_text())['env'])

    def test_with_a_recipient_only_the_encrypted_copy_is_kept(self):
        if not AGE:
            self.skipTest('no age here')
        key = self.tmp / 'owner.key'  # the owner's: in the test only; on the server there is only the public half
        REAL_RUN(['age-keygen', '-o', str(key)], check=True, capture_output=True)
        public = REAL_RUN(['age-keygen', '-y', str(key)], check=True, capture_output=True, text=True).stdout.strip()
        with patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': public}):
            folder, _ = self.backup()
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['flow.env.age', 'flow.sqlite3', 'manifest.json', 'source.tar.gz'])
        sealed = (folder / 'flow.env.age').read_bytes()
        self.assertTrue(sealed.startswith(ops.AGE_HEADER))
        self.assertNotIn(b'not-a-real-one', sealed)
        self.assertEqual((folder / 'flow.env.age').stat().st_mode & 0o777, 0o600)
        opened = REAL_RUN(['age', '-d', '-i', str(key), str(folder / 'flow.env.age')], check=True, capture_output=True).stdout
        self.assertEqual(opened, SECRET)  # the private key opens it, and nothing else is needed
        self.assertEqual(json.loads((folder / 'manifest.json').read_text())['env'], 'flow.env.age')
        self.assertTrue(self.status()['ok'])
        ops.check(folder / 'flow.sqlite3')  # the database is not encrypted: it opens and restores as it is
        with sqlite3.connect(folder / 'flow.sqlite3') as c:
            self.assertEqual(c.execute('SELECT username FROM users').fetchone()[0], 'owner')

    def test_the_recipient_from_flow_env_itself_and_several_of_them(self):
        """The backup unit has no EnvironmentFile: the line in flow.env counts as well (quoted as systemd allows)."""
        run, seen = self.stand_in()
        self.env.write_bytes(SECRET + b'FLOW_BACKUP_AGE_RECIPIENT="age1owner"\n')
        with patch.object(ops.subprocess, 'run', run):
            folder, _ = self.backup()
            self.assertEqual(seen[-1], ['age', '-r', 'age1owner', '-o', str(folder / 'flow.env.age'), str(self.env)])
            with patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': 'age1new, age1old'}):  # the environment first; a key change
                folder, _ = self.backup()
            self.assertEqual(seen[-1][:5], ['age', '-r', 'age1new', '-r', 'age1old'])
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['flow.env.age', 'flow.sqlite3', 'manifest.json', 'source.tar.gz'])

    def test_when_encrypting_fails_nothing_of_flow_env_is_kept_and_the_backup_says_so(self):
        cases = {'no age on the machine': (None, FileNotFoundError(2, 'No such file or directory', 'age'), 'FileNotFoundError'),
                 'age refuses the key': (None, subprocess.CalledProcessError(1, ['age'], b'', b'age: error: unknown recipient type: "x"\n'),
                                         'unknown recipient type'),
                 'what came out is not age': (SECRET, None, 'age 的输出不是加密文件')}
        for name, (output, fail, why) in cases.items():
            with self.subTest(name):
                before = self.folders()
                run, _ = self.stand_in(output, fail)
                with patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': 'age1owner'}), patch.object(ops.subprocess, 'run', run), \
                        contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(RuntimeError) as e:
                        ops.backup()
                self.assertIn('flow.env 没有存进备份', str(e.exception))
                self.assertIn(why, str(e.exception))
                (folder,) = self.folders() - before
                self.assertNoEnvKept(folder)  # never the readable copy instead
                self.assertIsNone(json.loads((folder / 'manifest.json').read_text())['env'])
                ops.check(folder / 'flow.sqlite3')  # the day's database is kept all the same
                self.assertFalse(self.status()['ok'])  # and the console shows the backup as failed
        # the copy restore makes before replacing the database does not wait for flow.env
        run, _ = self.stand_in(fail=FileNotFoundError(2, 'No such file or directory', 'age'))
        with patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': 'age1owner'}), patch.object(ops.subprocess, 'run', run):
            folder, said = self.backup(env_required=False)
        self.assertIn('flow.env 没有存进备份', said)
        self.assertNoEnvKept(folder)

    def test_the_restore_notes_say_to_ask_for_the_private_key(self):
        run, _ = self.stand_in()
        with patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': 'age1owner'}), patch.object(ops.subprocess, 'run', run):
            sealed, _ = self.backup()
        plain, _ = self.backup()
        for folder, asks in ((sealed, True), (plain, False)):
            with contextlib.redirect_stdout(io.StringIO()) as said:
                ops.restore(folder, False)
            self.assertEqual('找用户要 age 私钥' in said.getvalue(), asks, said.getvalue())
            if asks:
                self.assertIn(f'age -d -i <私钥文件> -o /etc/flow.env {folder.resolve() / "flow.env.age"}', said.getvalue())
        self.assertIn('ask the user (the owner) for it', ops.__doc__)


if __name__ == '__main__':
    unittest.main()
