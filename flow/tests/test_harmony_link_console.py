"""鸿蒙内测链接 in the 内测版's console (2026-11-26, D3 #415: the 内测版's download page shows 「加入内测」 with it,
「即将开放」 without): a 管理员 saves or clears it under 公告; the domain and the last save (from the operator log) are
shown; anything not a full https link is refused with console_ops' own words; 只看数据 sees it without who saved it;
语流's console has no such field and refuses the change."""
import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, console_ops as co, flow_admin  # noqa: E402

BOSS, PEEK = 'boss@example.com', 'peek@example.com'


class HarmonyLinkConsole(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                  patch.object(app, 'CHANNEL', 'beta'), patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': BOSS, 'FLOW_DATA_DIR': self.tmp.name})):
            p.start(); self.addCleanup(p.stop)
        app.init()
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        threading.Thread(target=self.admin.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.admin.shutdown(), self.admin.server_close()))

    def call(self, path, data=None, who=BOSS):
        h = {'Content-Type': 'application/json', 'Cf-Access-Authenticated-User-Email': who}
        if data is not None:
            h['X-Requested-With'] = 'xmc'
        req = urllib.request.Request(f'http://127.0.0.1:{self.admin.server_address[1]}/flow-beta/api{path}',
                                     data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_a_link_is_saved_shown_with_its_domain_and_cleared(self):
        self.assertEqual(self.call('/announcements')[1]['harmony'], {'url': '', 'host': '', 'saved': None})
        link = 'https://appgallery.huawei.com/link/invite-test-wap?taskId=abc&invitationCode=xyz'
        st, body = self.call('/settings/harmony-link', {'url': link})
        self.assertEqual((st, body['url'], body['host']), (200, link, 'appgallery.huawei.com'))
        self.assertEqual(co.harmony_test_url(), link)  # what the 内测版's /about reads
        h = self.call('/announcements')[1]['harmony']
        self.assertEqual((h['url'], h['saved']['by']), (link, BOSS))
        log = self.call('/log')[1]['items']
        self.assertEqual((log[0]['action'], log[0]['detail']), ('harmony-link', 'appgallery.huawei.com'))
        self.assertEqual(self.call('/settings/harmony-link', {'url': ''})[0], 200)
        self.assertEqual(co.harmony_test_url(), '')
        self.assertEqual(self.call('/log')[1]['items'][0]['detail'], '清空')

    def test_a_wrong_link_is_refused_in_console_ops_words(self):
        st, body = self.call('/settings/harmony-link', {'url': 'http://example.com/x'})
        self.assertEqual((st, body['field']), (400, 'url'))
        self.assertIn('https', body['error'])
        self.assertEqual(co.harmony_test_url(), '')

    def test_viewers_see_no_one_and_change_nothing(self):
        self.call('/settings/harmony-link', {'url': 'https://appgallery.huawei.com/link/x'})
        h = self.call('/announcements', who=PEEK)[1]['harmony']
        self.assertEqual(h['url'], 'https://appgallery.huawei.com/link/x')
        self.assertNotIn('by', h['saved'])
        self.assertEqual(self.call('/settings/harmony-link', {'url': ''}, who=PEEK)[0], 403)

    def test_the_prod_console_has_no_such_field(self):
        with patch.object(app, 'CHANNEL', 'prod'):
            self.assertNotIn('harmony', self.call('/announcements')[1])
            self.assertEqual(self.call('/settings/harmony-link', {'url': 'https://appgallery.huawei.com/link/x'})[0], 409)


if __name__ == '__main__':
    unittest.main()
