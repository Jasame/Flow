"""The 内测版's own daily backup (2026-11-26, the owner in A1: 「内测版也每天备份」): ops.py picks the site by FLOW_CHANNEL,
as the site does. 语流 keeps /www/wwwroot/flow, /www/backup/flow/daily, /etc/flow.env and the flow service exactly as
before; the 内测版 uses /www/wwwroot/flow-beta, /www/backup/flow-beta/daily, /etc/flow-beta.env and flow-beta, and its
status goes into its own data/, where privacy_service.backup_fresh reads it (its paused accounts are then deleted after
30 days like 语流's)."""
import contextlib, importlib, io, json, os, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ops  # noqa: E402


def load(channel):
    with patch.dict(os.environ, {'FLOW_CHANNEL': channel} if channel else {}, clear=False):
        if not channel:
            os.environ.pop('FLOW_CHANNEL', None)
        return importlib.reload(ops)


class BetaBackup(unittest.TestCase):
    def tearDown(self):
        load(os.environ.get('FLOW_CHANNEL', ''))  # back to how the other tests found it

    def test_each_site_has_its_own_places(self):
        prod = load('')
        self.assertEqual((str(prod.ROOT), str(prod.BACKUPS), str(prod.ENV_FILE), prod.SERVICE, prod.DAILY),
                         ('/www/wwwroot/flow', '/www/backup/flow/daily', '/etc/flow.env', 'flow', 'flow-daily'))
        self.assertEqual(load('prod').ROOT, prod.ROOT)
        beta = load('beta')
        self.assertEqual((str(beta.ROOT), str(beta.BACKUPS), str(beta.ENV_FILE), beta.SERVICE, beta.DAILY),
                         ('/www/wwwroot/flow-beta', '/www/backup/flow-beta/daily', '/etc/flow-beta.env', 'flow-beta', None))
        self.assertEqual(beta.CHANNEL, 'beta')  # chosen when ops.py starts, as the service's Environment= sets it

    def test_the_beta_backup_writes_its_own_status_and_prunes_its_own_copies(self):
        beta = load('beta')
        with tempfile.TemporaryDirectory() as tmp:
            root, env = Path(tmp) / 'flow-beta', Path(tmp) / 'flow-beta.env'
            (root / 'data').mkdir(parents=True)
            with sqlite3.connect(root / 'data' / 'flow.sqlite3') as c:
                c.execute('CREATE TABLE migrations(version TEXT)'); c.execute("INSERT INTO migrations VALUES('2.1')")
            env.write_text('FLOW_CHANNEL=beta\n')
            pruned = []
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'BACKUPS', Path(tmp) / 'backups'), patch.object(beta, 'ENV_FILE', env), \
                    patch.object(beta, 'prune_deploy_copies', lambda **k: pruned.append(k['channel']) or []), \
                    patch.dict(os.environ, {'FLOW_BACKUP_AGE_RECIPIENT': ''}), contextlib.redirect_stdout(io.StringIO()):
                folder = beta.backup()
            status = json.loads((root / 'data' / 'backup-status.json').read_text())
            self.assertTrue(status['ok'])
            self.assertTrue((folder / 'flow.sqlite3').is_file())
            self.assertEqual(folder.parent, Path(tmp) / 'backups')
            self.assertEqual(pruned, ['beta'])  # only the 内测版's own deploy copies

    def test_a_beta_restore_stops_and_starts_flow_beta_only(self):
        beta = load('beta')
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'flow-beta'
            (root / 'data').mkdir(parents=True)
            snap = Path(tmp) / 'snap'; snap.mkdir()
            for target in (root / 'data' / 'flow.sqlite3', snap / 'flow.sqlite3'):
                with sqlite3.connect(target) as c:
                    c.execute('CREATE TABLE migrations(version TEXT)'); c.execute("INSERT INTO migrations VALUES('2.1')")
            run = lambda args, **k: calls.append(args) or type('R', (), {'returncode': 0})()
            fake_pwd = type('P', (), {'getpwnam': staticmethod(lambda n: type('U', (), {'pw_uid': os.getuid(), 'pw_gid': os.getgid()})())})
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'BACKUPS', Path(tmp) / 'backups'), patch.object(beta, 'ENV_FILE', Path(tmp) / 'none.env'), \
                    patch.object(beta, 'prune_deploy_copies', lambda **k: []), patch.object(beta.subprocess, 'run', run), \
                    patch.dict(sys.modules, {'pwd': fake_pwd}), patch.object(beta.os, 'chown', lambda *a: None), contextlib.redirect_stdout(io.StringIO()):
                beta.restore(snap, True)
        services = [a[2] for a in calls if a[:2] in (['systemctl', 'stop'], ['systemctl', 'start'])]
        self.assertEqual(services, ['flow-beta', 'flow-beta'])  # no flow (语流), no flow-daily (the 内测版 has none)


if __name__ == '__main__':
    unittest.main()
