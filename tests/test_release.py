"""Archive policy checks; bootability is checked against the extracted ZIP by release.py."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'tools/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_private_and_unsafe_paths_are_rejected(self):
        for path in ['../secret', '/etc/flow.env', 'flow/data/user.json', 'flow/backups/save.tar',
                     'flow/recordings/a.ogg', 'flow/uploads/a', 'flow/flow.env', 'flow/.env',
                     'flow/user.sqlite3', 'flow/user.db-wal', 'flow/adc.json',
                     'flow/service-account.json', 'flow/private.key', 'flow/a\\b']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                release.safe_name(path)
        release.safe_name('flow/flow.env.example')

    def test_missing_upgrade_operand_is_rejected(self):
        files = release.source_files(ROOT)
        for path in ['flow/corpus_data/yl-reference.json', 'flow/flow-daily.timer',
                     'flow/public/ai-live.js', 'flow-gateway/nginx_update.py']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                release.check_requirements({n: b for n, b in files.items() if n != path})

    def test_unlisted_files_do_not_change_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in release.source_files(ROOT).items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (root / 'flow/personal-learning-records.json').write_text('private')
            (root / 'flow/flow.env').write_text('SECRET=private')
            self.assertEqual(release.source_files(ROOT), release.source_files(root))

    def test_corrupted_or_extra_archive_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'package.zip'
            path.write_bytes(release.archive_bytes(ROOT) + b'unexpected private data')
            with self.assertRaises(ValueError):
                release.validate(path, ROOT)


if __name__ == '__main__':
    unittest.main()
