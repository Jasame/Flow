"""发版请求签名校验, the server's half (tools/flow-autodeploy.py; tools/deploy.sh signs, tests/test_ci.py checks that half).

Once a site's key has its line in /etc/flow-release/allowed_signers, that site installs a release only when REQUEST.sig
is a signature of REQUEST by that key in that site's namespace, REQUEST names the tag it came by and a number above the
last release installed there, and TOOLS is the list REQUEST names; every tool is checked against its line in TOOLS
before it runs or replaces the server's copy. A site without its line installs as before. Root's emergency file
/etc/flow-release/unsigned-until lets a missing or bad signature through for at most 24 hours, and says so.

The keys are made for the test (ssh-keygen); without ssh-keygen the cases that sign are skipped."""
import base64, hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, time, unittest, urllib.error, warnings
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools'
KEYGEN = shutil.which('ssh-keygen')
REAL_RUN = subprocess.run
SHA = 'a' * 40
MANIFEST = 'c' * 64
# the commit's tools as tools/release_manifest.py --tools lists them: TOOL_FILES and tools/qa-audio/
FILES = {'tools/flow-pull.sh': b'#!/bin/bash\nF=${FLOW_DIR:-/www/wwwroot/flow}\necho the one in git\n',
         'tools/flow-pull-rollback.sh': b'#!/bin/bash\necho rollback\n',
         'tools/flow-autodeploy.py': b'# the next autodeploy\n',
         'tools/qa_e2e.py': b'# the end-to-end test\n',
         'tools/qa-audio/dialog.m4a': b'first recording',
         'tools/qa-audio/retell.m4a': b'second recording'}
# the 内测版's public key as A2 made it (public, 2026-11-25): the form of a line in allowed_signers
BETA_LINE = ('flow-beta-release namespaces="flow-beta-release" ssh-ed25519 '
             'AAAAC3NzaC1lZDI1NTE5AAAAIPJ76H+6FPgRD5NObSUpAJNFO1JKO4jdZU7Sxlf2UhxZ flow-beta-release\n')
# 语流's: the owner's public key (public, 2026-11-25; its private half stays in the Mac's keychain)
PROD_LINE = ('flow-release namespaces="flow-release" ssh-ed25519 '
             'AAAAC3NzaC1lZDI1NTE5AAAAIDhlEVzFB9+brVIxMYsj8P5AzLQ+mDZNWxlsC05Mn0x0 flow-release\n')
# b65, the first request CI signed (tag b65 on release-beta, f24f8ba, 2026-11-25): REQUEST, REQUEST.sig and TOOLS as
# jsDelivr serves them (public). Its build commit's tools are not in this checkout, so it is checked up to fetching them.
B65 = {
    'REQUEST': (b'3859953796a7312f113a4986ceb0902d8ed22274 bdfdf62fef5babcb5934d701f1ab58349b16b1ee583b4dce581893e693eb4c1d e2e light ref=build-3efd0418c749 tag=b65 tools=6cabec437d5331a86b772d0870d9963fd1fd12348cff64715122415ab19d1c77\n'
        b'# b65 main: Merge pull request #243 from Jasame/rule-fork-workflows = build of 3efd0418c749\n'
        b'# Format: <commit sha> <manifest sha256> [e2e [light]] [ref=<tag>] tag=<tag> tools=<sha256 of TOOLS>; signed in REQUEST.sig. Written by tools/deploy.sh, read by tools/flow-autodeploy.py.\n'),
    'REQUEST.sig': (b'-----BEGIN SSH SIGNATURE-----\n'
        b'U1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAg8nvof7oU+BEPk05tJSkAk0U7Uk\n'
        b'o7iN1lTtLGV/ZSHFkAAAARZmxvdy1iZXRhLXJlbGVhc2UAAAAAAAAABnNoYTUxMgAAAFMA\n'
        b'AAALc3NoLWVkMjU1MTkAAABAFd5E2fBQmU31ehmRkZ56B16BYYhRZ4Z17KRle1ct94nt5s\n'
        b'7MrAssln1eTJuTpLDxisDABxzXF8p2Cqax3fpBCQ==\n'
        b'-----END SSH SIGNATURE-----\n'),
    'TOOLS': (b'3nznG/5giQv4QVw7RcxAjEThW8B3Gc3Ncws0CABuBVA=  tools/flow-autodeploy.py\n'
        b'U6XRqpnxw9vbWuP/X1SMtXYkl8Y9WL2H7GCSdEiVfM0=  tools/flow-pull-rollback.sh\n'
        b'wg6It15K5n24dX7XroWOCEzLqna1wJqcAEmy3PbUgnk=  tools/flow-pull.sh\n'
        b'YfX9xU95XF6Q1nu3F2hHbcemXeR/v9TQ7M6bRTjH59A=  tools/qa-audio/dialog.m4a\n'
        b'b2lxcByHOXBZ4g5Oz5p20F69YjPvn2FSAYR5Cv5+CDU=  tools/qa-audio/retell.m4a\n'
        b'R6Fq3cbcr12tS4i37i25D+nxsIphCTOeCxfYCQFN+Hg=  tools/qa-audio/shadow_s0.m4a\n'
        b'p6yXkVJeNCcndq1/kTvUzH6tBb+nFTj3MstYMUtdf9s=  tools/qa-audio/think_as_sink.m4a\n'
        b'hB8qQv8i5izHRpuYrvu5Y5jwMSFsSeFzYKW+mIx8K/s=  tools/qa-audio/think_ok.m4a\n'
        b'mRyxgwBeTUg4CX8J66GRz/HX+0iT8y2RGq3alzHc80g=  tools/qa_e2e.py\n'),
}


def b64(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def tools_list(files):
    """TOOLS as tools/release_manifest.py --tools writes it: "<base64 sha256>  <path>" per line, sorted."""
    return ''.join(f'{b64(files[p])}  {p}\n' for p in sorted(files)).encode()


def load(beta):
    with patch.object(sys, 'argv', ['flow-autodeploy.py', *(['--beta'] if beta else [])]):
        spec = importlib.util.spec_from_file_location('autodeploy_signing_' + ('b' if beta else 'r'), TOOLS / 'flow-autodeploy.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class CDN:
    """jsDelivr as the server sees it: the request files by tag, the commit's files and their listing by commit."""

    def __init__(self, tags, files=None, listed=None):
        self.tags, self.files = tags, dict(FILES if files is None else files)
        self.listed = dict(self.files if listed is None else listed)
        self.asked = []

    def fetch(self, url, timeout=40):
        self.asked.append(url)
        if url.startswith('https://data.jsdelivr.com/'):
            return json.dumps({'files': [{'name': '/' + p, 'hash': b64(b), 'size': len(b)} for p, b in self.listed.items()]}).encode()
        ref, path = url.split('/gh/Jasame/Flow@', 1)[1].split('/', 1)
        found = self.files.get(path) if ref == SHA else self.tags.get(ref, {}).get(path)
        if found is None:
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
        return found

    def from_commit(self):
        return [u for u in self.asked if f'@{SHA}' in u]


class Signing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keydir = tempfile.TemporaryDirectory()
        cls.keys = Path(cls.keydir.name)
        if KEYGEN:
            for who in ('prod', 'beta', 'other'):
                REAL_RUN(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', who, '-f', str(cls.keys / who)], check=True,
                         capture_output=True, stdin=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_dir.name)
        self.signers = self.tmp / 'allowed_signers'
        self.until = self.tmp / 'unsigned-until'
        self.said, self.mails = [], []

    def tearDown(self):
        self.tmp_dir.cleanup()

    def need_keygen(self):
        if not KEYGEN:
            self.skipTest('no ssh-keygen')

    def pin(self, *who):
        """allowed_signers with the lines of these test keys."""
        names = {'prod': 'flow-release', 'beta': 'flow-beta-release'}
        self.signers.write_text(''.join(f'{names[w]} namespaces="{names[w]}" ' + (self.keys / f'{w}.pub').read_text() for w in who))

    def sign(self, key, ns, body):
        """REQUEST.sig as tools/deploy.sh makes it: ssh-keygen -Y sign -q -f <key> -n <namespace> REQUEST."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'REQUEST').write_bytes(body)
            REAL_RUN(['ssh-keygen', '-Y', 'sign', '-q', '-f', str(self.keys / key), '-n', ns, str(Path(d) / 'REQUEST')], check=True,
                     capture_output=True, stdin=subprocess.DEVNULL)
            return (Path(d) / 'REQUEST.sig').read_bytes()

    @staticmethod
    def request(tag, tools=None, e2e=' e2e light', fields=None):
        """REQUEST as tools/deploy.sh writes it (fields: what follows the commit and manifest, instead of tag= tools=)."""
        if fields is None:
            fields = f' tag={tag} tools={hashlib.sha256(tools_list(FILES) if tools is None else tools).hexdigest()}'
        return (f'{SHA} {MANIFEST}{e2e}{fields}\n# {tag} main: 今日一读：一次测试 = build of {"b" * 12}\n'
                '# Format: <commit sha> <manifest sha256> [e2e [light]] [ref=<tag>] tag=<tag> tools=<sha256 of TOOLS>\n').encode()

    def signed(self, tag, key, ns, body=None, tools=None):
        """A tag's request files: REQUEST, its signature by `key` in `ns` (no key: none) and TOOLS."""
        tools = tools_list(FILES) if tools is None else tools
        body = self.request(tag, tools) if body is None else body
        return {'REQUEST': body, 'TOOLS': tools, **({'REQUEST.sig': self.sign(key, ns, body)} if key else {})}

    def deploy(self, mod, cdn, n=9, installed=None):
        """One run of the timer for tag <prefix><n>: its status, and each flow-pull.sh it ran (as bytes)."""
        ad, home = self.tmp / f"ad-{mod.SITE['prefix']}", self.tmp / f"home-{mod.SITE['prefix']}"
        ad.mkdir(exist_ok=True)
        (ad / 'next').write_text(str(n))
        if installed is not None:
            (ad / 'installed').write_text(str(installed))
        ran = []
        snap = lambda: {p.name: p.read_bytes() for p in home.iterdir()} if home.exists() else {}
        before = snap()

        def run(cmd, **kw):
            if cmd[0] == 'ssh-keygen':
                return REAL_RUN(cmd, **kw)
            if cmd[0] == 'bash':
                ran.append(Path(cmd[1]).read_bytes())
                kw['stdout'].write('2 files to install (0 new)\nflow: active=active health=200\nRESULT=DEPLOYED\n')
            else:
                kw['stdout'].write('the end-to-end test\n')
        with patch.object(mod, 'AD', ad), patch.object(mod, 'STATUS', self.tmp / 'status.json'), patch.object(mod, 'DAILY', self.tmp / 'daily'), \
                patch.object(mod, 'SITE', {**mod.SITE, 'home': home}), patch.object(mod, 'SIGNERS', self.signers), \
                patch.object(mod, 'UNSIGNED_UNTIL', self.until), patch.object(mod, 'fetch', cdn.fetch), \
                patch.object(mod.time, 'sleep', lambda s: None), patch.object(mod.subprocess, 'run', run), \
                patch.object(mod, 'journal', self.said.append), \
                patch.object(mod, 'mail_admins', lambda subject, text: self.mails.append((subject, text)) or 1), \
                warnings.catch_warnings():
            warnings.simplefilter('ignore', ResourceWarning)  # main() holds its lock file until the process ends
            mod.main()
        self.home, self.ad = home, ad
        self.replaced = sorted(k for k, v in snap().items() if before.get(k) != v)  # the server's copies of the tools
        return json.loads((self.tmp / 'status.json').read_text()), ran

    def assertNothingTaken(self, st, cdn, ran):
        """Refused before anything came from the commit: no listing, no tool, nothing run, nothing replaced."""
        self.assertEqual((cdn.from_commit(), ran, self.replaced), ([], [], []), st)

    # ---------- no line for the site: as before ----------

    def test_a_site_without_its_line_installs_as_before(self):
        for beta in (False, True):
            mod = load(beta)
            p = mod.SITE['prefix']
            for body in (self.request(f'{p}9'), f'{SHA} {MANIFEST}\n# an older request\n'.encode()):
                self.said.clear()
                cdn = CDN({f'{p}9': {'REQUEST': body}})
                st, ran = self.deploy(mod, cdn)
                self.assertEqual((st['result'], ran), ('DEPLOYED', [FILES['tools/flow-pull.sh']]), st)
                self.assertNotIn('signature', st)
                self.assertTrue(any('本站没开签名校验' in s for s in self.said), self.said)
                self.assertFalse([u for u in cdn.asked if u.endswith(('/REQUEST.sig', '/TOOLS'))])  # not even asked for
                self.assertEqual((self.home / 'flow-autodeploy.py').read_bytes(), FILES['tools/flow-autodeploy.py'])
                self.assertEqual((self.ad / 'installed').read_text(), '9')  # recorded all the same, for when it is on

    def test_only_the_site_whose_line_is_there_checks(self):
        """上线顺序: the 内测版's line goes in first; 语流 keeps installing as before until its own line is there."""
        self.signers.write_text('# 内测版 first (security-release-signing.md)\n' + BETA_LINE)
        prod, beta = load(False), load(True)
        st, ran = self.deploy(prod, CDN({'r9': {'REQUEST': self.request('r9')}}))
        self.assertEqual((st['result'], len(ran)), ('DEPLOYED', 1), st)
        self.assertTrue(any('本站没开签名校验' in s for s in self.said), self.said)
        cdn = CDN({'b9': {'REQUEST': self.request('b9'), 'TOOLS': tools_list(FILES)}})
        st, ran = self.deploy(beta, cdn)
        self.assertEqual((st['result'], st['error']), ('BAD_SIGNATURE', 'REQUEST.sig missing'))
        self.assertNothingTaken(st, cdn, ran)
        if KEYGEN:  # a good signature by a key that is not the one pinned for the site
            st, ran = self.deploy(beta, CDN({'b9': self.signed('b9', 'beta', 'flow-beta-release')}))
            self.assertEqual(st['result'], 'BAD_SIGNATURE', st)
        self.signers.write_text(BETA_LINE.replace('flow-beta-release namespaces', 'flow-beta-release-old namespaces'))
        st, _ = self.deploy(beta, CDN({'b9': {'REQUEST': self.request('b9')}}))  # a name that only starts like it: not its line
        self.assertEqual(st['result'], 'DEPLOYED', st)
        self.signers.write_text(PROD_LINE)  # the other way round: 语流's line alone switches on 语流 only
        st, ran = self.deploy(beta, CDN({'b9': {'REQUEST': self.request('b9')}}))
        self.assertEqual((st['result'], len(ran)), ('DEPLOYED', 1), st)
        cdn = CDN({'r9': {'REQUEST': self.request('r9'), 'TOOLS': tools_list(FILES)}})
        st, ran = self.deploy(prod, cdn)
        self.assertEqual((st['result'], st['error']), ('BAD_SIGNATURE', 'REQUEST.sig missing'))
        self.assertNothingTaken(st, cdn, ran)
        self.signers.write_text(PROD_LINE + BETA_LINE)  # both lines: both sites check
        for mod, tag in ((prod, 'r9'), (beta, 'b9')):
            st, ran = self.deploy(mod, CDN({tag: {'REQUEST': self.request(tag), 'TOOLS': tools_list(FILES)}}))
            self.assertEqual((st['result'], ran), ('BAD_SIGNATURE', []), st)

    # ---------- signed ----------

    def test_a_good_signature_installs_with_the_checked_tools(self):
        self.need_keygen()
        self.pin('prod', 'beta')
        for beta, key, ns in ((True, 'beta', 'flow-beta-release'), (False, 'prod', 'flow-release')):
            mod = load(beta)
            tag = mod.SITE['prefix'] + '9'
            cdn = CDN({tag: self.signed(tag, key, ns)})
            st, ran = self.deploy(mod, cdn)
            self.assertEqual((st['result'], st['signature']), ('DEPLOYED', 'ok'), st)
            self.assertEqual(ran, [FILES['tools/flow-pull.sh']])
            for name in ('flow-pull.sh', 'flow-pull-rollback.sh', 'flow-autodeploy.py'):  # replaced by the checked copies
                self.assertEqual((self.home / name).read_bytes(), FILES['tools/' + name])
            work = self.ad / tag
            self.assertEqual({p.name: p.read_bytes() for p in (work / 'qa-audio').iterdir()},
                             {Path(p).name: b for p, b in FILES.items() if p.startswith('tools/qa-audio/')})
            self.assertEqual((work / 'qa_e2e.py').read_bytes(), FILES['tools/qa_e2e.py'])
            self.assertEqual((self.ad / 'installed').read_text(), '9')
            self.assertEqual(self.mails, [])

    def test_a_missing_or_wrong_signature_installs_nothing(self):
        self.need_keygen()
        self.pin('prod', 'beta')
        mod = load(True)
        body = self.request('b9')
        cases = {
            'no signature': ({'REQUEST': body, 'TOOLS': tools_list(FILES)}, 'REQUEST.sig missing'),
            'not a signature': ({'REQUEST': body, 'REQUEST.sig': b'-----BEGIN SSH SIGNATURE-----\nnope\n', 'TOOLS': tools_list(FILES)},
                                'signature does not verify'),
            'a key nobody pinned': (self.signed('b9', 'other', 'flow-beta-release'), 'signature does not verify'),
            "the 内测版's key, 语流's namespace": (self.signed('b9', 'beta', 'flow-release'), 'namespace'),
            "语流's signature on the 内测版": (self.signed('b9', 'prod', 'flow-release'), 'signature does not verify'),
            'REQUEST changed after signing': ({**self.signed('b9', 'beta', 'flow-beta-release'), 'REQUEST': body.replace(b' e2e light', b'')},
                                              'incorrect signature'),
            'another commit': ({**self.signed('b9', 'beta', 'flow-beta-release'), 'REQUEST': body.replace(SHA.encode(), b'd' * 40)},
                               'incorrect signature'),
        }
        for name, (files, why) in cases.items():
            with self.subTest(name):
                cdn = CDN({'b9': files})
                st, ran = self.deploy(mod, cdn)
                self.assertEqual(st['result'], 'BAD_SIGNATURE', st)
                self.assertIn(why, st['error'])
                self.assertNothingTaken(st, cdn, ran)
                self.assertFalse((self.ad / 'installed').exists())
                self.assertEqual((self.ad / 'next').read_text(), '10')  # handled once, like any request

    def test_every_tool_must_match_the_signed_list(self):
        """A tool that is not the one TOOLS names (whatever jsDelivr's listing says): nothing runs, nothing is replaced."""
        self.need_keygen()
        self.pin('beta')
        mod = load(True)
        for path in FILES:
            with self.subTest(path):
                swapped = {**FILES, path: FILES[path] + b'\nsomething else\n'}
                cdn = CDN({'b9': self.signed('b9', 'beta', 'flow-beta-release')}, files=swapped)
                st, ran = self.deploy(mod, cdn)
                self.assertEqual(st['result'], 'ABORT_FETCH', st)
                self.assertIn(f'{path}: content does not match TOOLS', st['error'])
                self.assertEqual((ran, self.replaced), ([], []))
        # a recording is only taken for an end-to-end test, and is then checked like the rest
        cdn = CDN({'b9': self.signed('b9', 'beta', 'flow-beta-release', body=self.request('b9', e2e=''))},
                  files={**FILES, 'tools/qa-audio/dialog.m4a': b'other'})
        st, ran = self.deploy(mod, cdn)
        self.assertEqual((st['result'], len(ran)), ('DEPLOYED', 1), st)
        self.assertFalse([u for u in cdn.asked if 'qa-audio' in u])

    def test_the_tool_list_must_be_the_one_signed_and_complete(self):
        self.need_keygen()
        self.pin('beta')
        mod = load(True)
        sign = lambda body, tools=None: self.signed('b9', 'beta', 'flow-beta-release', body=body, tools=tools)
        short = tools_list({p: b for p, b in FILES.items() if p != 'tools/flow-pull-rollback.sh'})
        good = tools_list(FILES)
        cases = {
            'no TOOLS': ({k: v for k, v in sign(None).items() if k != 'TOOLS'}, 'TOOLS missing'),
            'TOOLS changed': ({**sign(None), 'TOOLS': good + f'{b64(b"x")}  tools/qa-audio/x.m4a\n'.encode()},
                              'TOOLS does not match tools='),
            'no tools=': (sign(self.request('b9', fields=' tag=b9')), 'REQUEST has no tools='),
            'no tag=': (sign(self.request('b9', fields=f' tools={hashlib.sha256(good).hexdigest()}')), 'REQUEST has no tag='),
            'tag= twice': (sign(self.request('b9', fields=f' tag=b9 tag=b9 tools={hashlib.sha256(good).hexdigest()}')), 'tag= twice'),
            'a tool not listed': (sign(self.request('b9', tools=short), tools=short), 'not in TOOLS: tools/flow-pull-rollback.sh'),
            'TOOLS not in its form': (sign(self.request('b9', tools=b'tools/flow-pull.sh\n'), tools=b'tools/flow-pull.sh\n'), 'TOOLS line 1'),
        }
        for name, (files, why) in cases.items():
            with self.subTest(name):
                cdn = CDN({'b9': files})
                st, ran = self.deploy(mod, cdn)
                self.assertEqual(st['result'], 'BAD_SIGNATURE', st)
                self.assertIn(why, st['error'])
                self.assertNothingTaken(st, cdn, ran)

    def test_an_old_request_under_a_new_tag_or_an_older_number_is_refused(self):
        self.need_keygen()
        self.pin('beta')
        mod = load(True)
        b5 = self.signed('b5', 'beta', 'flow-beta-release')  # a real request of b5, put under b9
        cdn = CDN({'b9': b5})
        st, ran = self.deploy(mod, cdn)
        self.assertEqual((st['result'], st['error']), ('BAD_SIGNATURE', 'REQUEST is for b5, not b9'), st)
        self.assertNothingTaken(st, cdn, ran)
        # next set back by hand below the last release installed: a signed b7 is refused once b9 is in
        cdn = CDN({'b7': self.signed('b7', 'beta', 'flow-beta-release')})
        st, ran = self.deploy(mod, cdn, n=7, installed=9)
        self.assertEqual((st['result'], st['error']), ('BAD_SIGNATURE', 'b7 is older than b9, the last release installed here'))
        self.assertNothingTaken(st, cdn, ran)
        # the same number again: installed already, nothing to do (and nothing taken)
        cdn = CDN({'b9': self.signed('b9', 'beta', 'flow-beta-release')})
        st, ran = self.deploy(mod, cdn, n=9, installed=9)
        self.assertEqual((st['result'], st['note']), ('NOTHING_TO_DO', 'b9 is installed already'), st)
        self.assertNothingTaken(st, cdn, ran)
        # a higher one goes in, and the number only grows
        cdn = CDN({'b12': self.signed('b12', 'beta', 'flow-beta-release')})
        st, ran = self.deploy(mod, cdn, n=12, installed=9)
        self.assertEqual(st['result'], 'DEPLOYED', st)
        self.assertEqual((self.ad / 'installed').read_text(), '12')
        self.signers.unlink()  # signatures off: an older number installs as before, the record stays where it was
        st, _ = self.deploy(mod, CDN({'b10': {'REQUEST': self.request('b10')}}), n=10)
        self.assertEqual(st['result'], 'DEPLOYED', st)
        self.assertEqual((self.ad / 'installed').read_text(), '12')

    def test_the_first_real_signed_request_checks_out_on_the_beta_only(self):
        """b65 as CI signed it, against both real keys as allowed_signers will hold them."""
        self.need_keygen()
        self.signers.write_text(PROD_LINE + BETA_LINE)
        beta, prod = load(True), load(False)
        words = B65['REQUEST'].decode().splitlines()[0].split()
        ad = self.tmp / 'ad-b'
        ad.mkdir()
        (ad / 'installed').write_text('64')
        with patch.object(beta, 'SIGNERS', self.signers), patch.object(beta, 'UNSIGNED_UNTIL', self.until), patch.object(beta, 'AD', ad), \
                patch.object(prod, 'SIGNERS', self.signers):
            st = {}
            listed = beta.check_request('b65', 65, B65['REQUEST'], words, B65['REQUEST.sig'], B65['TOOLS'], st)
            self.assertEqual(st, {'signature': 'ok'})
            self.assertLessEqual(set(beta.TOOLS), set(listed))
            self.assertEqual(len([p for p in listed if p.startswith(beta.AUDIO)]), 5)
            self.assertEqual(listed['tools/flow-pull.sh'], 'wg6It15K5n24dX7XroWOCEzLqna1wJqcAEmy3PbUgnk=')
            # 语流 never takes it: the 内测版's key is not on 语流's line, and its namespace is not 语流's
            self.assertIn('signature does not verify', prod.signature_problem(B65['REQUEST'], B65['REQUEST.sig']))
            # changed by one character, or put under the next tag: refused
            self.assertIn('incorrect signature', beta.signature_problem(B65['REQUEST'].replace(b'tag=b65', b'tag=b66'), B65['REQUEST.sig']))
            with self.assertRaises(beta.Stop) as e:
                beta.check_request('b66', 66, B65['REQUEST'], words, B65['REQUEST.sig'], B65['TOOLS'], {})
            self.assertEqual((e.exception.result, str(e.exception)), ('BAD_SIGNATURE', 'REQUEST is for b65, not b66'))

    # ---------- the emergency switch ----------

    def test_the_emergency_file_lets_a_bad_signature_through_for_at_most_a_day(self):
        self.need_keygen()
        self.pin('prod', 'beta')
        mod = load(False)
        unsigned = {'REQUEST': self.request('r9'), 'TOOLS': tools_list(FILES)}
        self.until.write_text(f'{int(time.time()) + 3600}\n')
        st, ran = self.deploy(mod, CDN({'r9': unsigned}))
        self.assertEqual((st['result'], st['signature'], st['signature_error']), ('DEPLOYED', 'UNSIGNED_ALLOWED', 'REQUEST.sig missing'), st)
        self.assertIn('unsigned_until', st)
        self.assertEqual((len(ran), st['mailed']), (1, 1))
        self.assertEqual(len(self.mails), 1)
        self.assertIn('r9', self.mails[0][0])
        self.assertIn('REQUEST.sig missing', self.mails[0][1])
        self.assertEqual((self.ad / 'installed').read_text(), '9')
        # a wrong signature too; the rest of the request is still checked: its tag, its tools
        self.mails.clear()
        st, ran = self.deploy(mod, CDN({'r10': self.signed('r10', 'other', 'flow-release')}), n=10)
        self.assertEqual((st['result'], st['signature']), ('DEPLOYED', 'UNSIGNED_ALLOWED'), st)
        st, ran = self.deploy(mod, CDN({'r11': {**unsigned, 'REQUEST': self.request('r5')}}), n=11)
        self.assertEqual((st['result'], st['error']), ('BAD_SIGNATURE', 'REQUEST is for r5, not r11'))
        st, ran = self.deploy(mod, CDN({'r12': {**unsigned, 'REQUEST': self.request('r12')}}, files={**FILES, 'tools/qa_e2e.py': b'x'}), n=12)
        self.assertEqual((st['result'], ran), ('ABORT_FETCH', []), st)
        # expired, more than a day ahead, or not a time: as if there were no file, and the journal says why
        for text, said in ((f'{int(time.time()) - 60}', 'expired'), (f'{int(time.time()) + 25 * 3600}', 'more than 24 hours'),
                           ('tomorrow', 'not a Unix time')):
            with self.subTest(text):
                self.said.clear(); self.mails.clear()
                self.until.write_text(text)
                cdn = CDN({'r20': unsigned | {'REQUEST': self.request('r20')}})
                st, ran = self.deploy(mod, cdn, n=20)
                self.assertEqual((st['result'], st['error']), ('BAD_SIGNATURE', 'REQUEST.sig missing'), st)
                self.assertNothingTaken(st, cdn, ran)
                self.assertTrue(any(said in s for s in self.said), self.said)
                self.assertEqual(self.mails, [])

    def test_the_mail_goes_by_the_sites_own_way_out(self):
        mod = load(False)
        with tempfile.TemporaryDirectory() as outbox:
            with patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': 'boss@example.com, ops@example.com', 'FLOW_MAIL_OUTBOX': outbox}), \
                    patch.object(mod, 'ENV', {**mod.ENV, 'FLOW_DIR': str(ROOT / 'flow')}):
                self.assertEqual(mod.mail_admins('语流 r9 没有通过签名校验，按应急开关照装', 'text'), 2)
            sent = sorted(Path(outbox).glob('*.txt'))
            self.assertEqual(len(sent), 2)
            self.assertIn('Subject: 语流 r9 没有通过签名校验', sent[0].read_text(encoding='utf-8'))
        said = []
        with patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': ''}), patch.object(mod, 'journal', said.append):
            self.assertEqual(mod.mail_admins('s', 't'), 0)
        self.assertTrue(said)

    # ---------- the two halves agree ----------

    def test_the_tool_list_of_release_manifest_reads_here(self):
        """When tools/release_manifest.py writes TOOLS (--tools), this side reads it and finds every tool it takes."""
        mod = load(False)
        rm = (TOOLS / 'release_manifest.py').read_text(encoding='utf-8')
        if '--tools' not in rm:
            self.skipTest('release_manifest.py --tools comes with the signing half (tools/deploy.sh)')
        r = REAL_RUN([sys.executable, str(TOOLS / 'release_manifest.py'), '--tools', 'HEAD'], cwd=ROOT, capture_output=True)
        if r.returncode:
            self.skipTest('no git history here: ' + r.stderr.decode(errors='replace')[-200:])
        listed = mod.tool_lines(r.stdout)
        self.assertLessEqual(set(mod.TOOLS), set(listed))
        self.assertTrue(any(p.startswith(mod.AUDIO) for p in listed))


if __name__ == '__main__':
    unittest.main()
