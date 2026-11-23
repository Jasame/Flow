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
                     'flow/public/next.js', 'flow-gateway/nginx_update.py']:
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


# Tracked under flow/ or flow-gateway/ but never installed, and why. Anything else there must be in
# tools/release-files.txt: the server installs only listed files, so an unlisted page, picture or module works on a
# laptop and is missing in production (r19: the guide's login.jpg nearly shipped without being listed).
NOT_SHIPPED = {
    'flow/corpus_data/candidates/': 'material candidates still under review',
    'flow/corpus_data/meaning-fixes-notes.md': "the editors' record of the reviewed senses (tools/audit_meanings.py)",
    'flow/corpus_data/pilot/make_audio.py': 'makes the pilot audio on a desktop',
    'flow/corpus_data/v5/EXAMPLE.science.B2.json': 'an example for material authors',
    'flow/public/src/': 'the source parts of next.js and next.css (tools/build_front.py joins them)',
}
CONSOLE = ('index.html', 'admin.js', 'admin.css')  # tools/flow-pull.sh installs these from xmc-admin/ by name


def tracked():
    import shutil, subprocess
    if not shutil.which('git') or not (ROOT / '.git').exists():
        return None
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [n for n in out.splitlines() if n]


class ReleaseListTests(unittest.TestCase):
    def setUp(self):
        self.files = tracked()
        if self.files is None:
            self.skipTest('not a git checkout (the release ZIP has no history)')
        self.listed = [n for n in (ROOT / 'tools/release-files.txt').read_text().splitlines() if n]

    def test_every_shipped_area_file_is_listed_or_explained(self):
        listed = set(self.listed)
        missing = [n for n in self.files if n.startswith(('flow/', 'flow-gateway/')) and n not in listed
                   and not any(n == k or (k.endswith('/') and n.startswith(k)) for k in NOT_SHIPPED)]
        self.assertEqual(missing, [], 'add these to tools/release-files.txt, or to NOT_SHIPPED with the reason')

    def test_every_listed_file_is_in_git(self):
        self.assertEqual(sorted(set(self.listed) - set(self.files)), [])
        self.assertFalse(any(n.startswith(k) for n in self.listed for k in NOT_SHIPPED if k.endswith('/')))

    def test_the_console_files_are_the_ones_the_deploy_installs(self):
        pull = (ROOT / 'tools/flow-pull.sh').read_text()
        self.assertIn('for n in ' + repr(CONSOLE), pull)
        page_parts = sorted(n.split('/')[1] for n in self.files if n.startswith('xmc-admin/') and n.endswith(('.html', '.js', '.css')))
        self.assertEqual(page_parts, sorted(CONSOLE), 'a new console file must be added to tools/flow-pull.sh (names += ...)')

    def test_nothing_of_the_classic_site_ships(self):
        """r20: the classic site is archived in archive/classic/ and is neither listed nor served."""
        self.assertFalse([n for n in self.listed if n.startswith('archive/')])
        public = {n.split('/')[-1] for n in self.listed if n.startswith('flow/public/') and n.count('/') == 2}
        self.assertEqual(public, {'next.html', 'next.js', 'next.css', 'sw.js', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png',
                                  'apple-touch-icon.png', 'survey.html', 'survey.js', 'survey.css', 'literata.woff2'})


if __name__ == '__main__':
    unittest.main()
