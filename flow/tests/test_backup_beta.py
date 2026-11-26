"""The 内测版's own daily backup (2026-11-26, the owner in A1: 「内测版也每天备份」): ops.py picks the site by FLOW_CHANNEL,
as the site does. 语流 keeps /www/wwwroot/flow, /www/backup/flow/daily, /etc/flow.env and the flow service exactly as
before; the 内测版 uses /www/wwwroot/flow-beta, /www/backup/flow-beta/daily, /etc/flow-beta.env and flow-beta, and its
status goes into its own data/, where privacy_service.backup_fresh reads it (its paused accounts are then deleted after
30 days like 语流's)."""
import contextlib, datetime, importlib, io, json, os, sqlite3, sys, tempfile, unittest
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



class BackupPrune(unittest.TestCase):
    """最近 14 天 (the 隐私说明, 2026-11-26: the backups on 香港 and their copy in 杭州): after a backup that succeeded, the
    newest 14 completed backups stay at most, and nothing of this tool made more than 13½ days ago, a failed one
    included, so a copy never outlives 14 days even when days were skipped. When a backup was made is the time in its
    name (A1: a folder's mtime moves whenever a file in it changes), else its manifest, else its mtime; other folders in
    the place are left alone."""
    NOW = datetime.datetime(2026, 11, 26, 21, 0).timestamp()

    def make(self, root, days_ago, done=True, name=None, created=None):
        stamp = datetime.datetime.fromtimestamp(self.NOW - days_ago * 86400).strftime('%Y%m%d-%H%M%S')
        f = root / (name or f'flow-{stamp}-' + ('1234-abc123' if done else '5678-fa11ed')); f.mkdir(); (f / 'flow.sqlite3').write_bytes(b'x')
        if done:
            (f / 'manifest.json').write_text(json.dumps({'created': created} if created is not None else {}))
        os.utime(f, (self.NOW, self.NOW))  # every folder touched today, as A1 found them (an old flow.env deleted)
        return f

    def prune(self, root):
        with patch.object(ops, 'BACKUPS', root):
            return ops.prune_backups(now=self.NOW, say=lambda *a: None)

    def test_old_copies_go_by_the_date_in_their_name_even_when_touched_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = [self.make(root, d) for d in range(0, 16)]  # one a day: today and 15 before, all with today's mtime
            failed_old, failed_new = self.make(root, 20, done=False), self.make(root, 2, done=False)
            other = root / 'notes'; other.mkdir()
            gone = self.prune(root)
            self.assertEqual(sorted(gone), sorted([daily[14], daily[15], failed_old]))
            self.assertTrue(all(d.exists() for d in daily[:14]))  # today's and the 13 before it, as before
            self.assertTrue(failed_new.exists() and other.exists())  # a recent failed one stays a while; not ours stays

    def test_the_newest_fourteen_are_the_newest_by_name_not_by_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folders = [self.make(root, d / 4) for d in range(0, 16)]  # 16 in four days (several a day, as on 11-26)
            old = folders[-1]
            os.utime(old, (self.NOW + 60, self.NOW + 60))  # the oldest touched last: by mtime it would look newest
            self.prune(root)
            self.assertFalse(old.exists())
            self.assertEqual(len(list(root.iterdir())), 14)
            self.assertTrue(folders[0].exists())  # the one just made stays

    def test_after_a_gap_only_what_is_young_enough_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = [self.make(root, d) for d in (0, 10, 13)]
            for d in (14, 20, 30):  # the timer had stopped for a while: fewer than 14 left, some too old
                self.make(root, d)
            self.prune(root)
            self.assertEqual(sorted(root.iterdir()), sorted(keep))

    def test_a_name_without_a_date_falls_back_to_the_manifest_then_the_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            by_manifest = self.make(root, 0, name='flow-handmade', created=self.NOW - 20 * 86400)
            by_mtime = self.make(root, 0, done=False, name='flow-scratch')
            os.utime(by_mtime, (self.NOW - 20 * 86400,) * 2)
            young = self.make(root, 0, name='flow-handmade-new', created=self.NOW - 86400)
            self.prune(root)
            self.assertEqual(sorted(root.iterdir()), [young])


if __name__ == '__main__':
    unittest.main()
