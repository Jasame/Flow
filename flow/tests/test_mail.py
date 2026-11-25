"""Mail layout (mail_layout.py, the owner's 「A 简洁卡片」): every mail goes as text and HTML; a code is in the subject,
is the first line of the text and one run of digits in the HTML, so phones and password managers can pick it up; the
HTML loads nothing from elsewhere and escapes what it is given; the 内测版 still marks its subjects."""
import email, os, re, smtplib, struct, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, account_service, auth_service, mail_layout  # noqa: E402


class LayoutTests(unittest.TestCase):
    def test_a_code_comes_first_in_the_text_and_whole_in_the_html(self):
        text, page = mail_layout.message(['第一段', '第二段'], code='048213')
        self.assertEqual(text.splitlines()[0], '验证码：048213')
        self.assertIn('第一段', text)
        self.assertIn(mail_layout.FROM_LINE, text)
        self.assertEqual(len(re.findall(r'048213', page)), 2)  # the preview line and the card's code, each whole
        self.assertNotRegex(page, r'0\s*<[^>]+>\s*4')  # never one digit per box

    def test_the_html_loads_only_the_logo_and_escapes_what_it_is_given(self):
        text, page = mail_layout.message(['<b>a</b> & "b"'], rows=[('x<y', 'z')], button=('打开', 'https://flowlang.cn/#/review'),
                                         foot=[('退订', 'https://flowlang.cn/api/next/weekly-mail/off?t=1&x=2')])
        for bad in ('url(', '@import', '<link', '<script', 'data:'):
            self.assertNotIn(bad, page)
        # the one picture: the logo the site serves (never inlined: Gmail and QQ 邮箱 block that), its size fixed, and
        # 「语流 Flow」 as text beside it for a mail app that blocks pictures
        self.assertEqual(re.findall(r'<img src="([^"]+)" width="32" height="32"', page), ['https://flowlang.cn/icon-192.png'])
        self.assertEqual(page.count(' src='), 1)
        self.assertIn('>语流 Flow</td>', page)
        self.assertNotIn('>流</td>', page)
        with patch.dict(os.environ, {'FLOW_PUBLIC_URL': 'https://flow.jasa.hk/'}):
            self.assertIn('src="https://flow.jasa.hk/icon-192.png"', mail_layout.message(['x'])[1])
        icon = (Path(app.ROOT) / 'public' / 'icon-192.png').read_bytes()  # what both sites serve, 6x for 32 px
        self.assertEqual((icon[:8], struct.unpack('>II', icon[16:24])), (b'\x89PNG\r\n\x1a\n', (192, 192)))
        # the button is a table cell with its colour (Outlook), one column at most 560 px wide
        self.assertRegex(page, r'<td class="fl-btn" bgcolor="#1f9d55"[^>]*><a href="https://flowlang.cn/#/review"')
        self.assertIn('max-width:560px', page)
        self.assertIn('&lt;b&gt;a&lt;/b&gt; &amp; &quot;b&quot;', page)
        self.assertIn('x&lt;y', page)
        self.assertIn('href="https://flowlang.cn/api/next/weekly-mail/off?t=1&amp;x=2"', page)
        self.assertIn('name="color-scheme" content="light dark"', page)
        self.assertIn('@media (prefers-color-scheme: dark)', page)
        self.assertIn('退订：https://flowlang.cn/api/next/weekly-mail/off?t=1&x=2', text)
        self.assertIn('打开：https://flowlang.cn/#/review', text)


class Sending(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / 'outbox'
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_MAIL_OUTBOX': str(self.outbox), 'FLOW_CHANNEL': ''})]
        for p in self.patches:
            p.start()
        app.init()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def last(self):
        txt = sorted(self.outbox.glob('*.txt'))[-1]
        return txt.read_text(encoding='utf-8'), txt.with_suffix('.html')

    def test_the_code_mail_puts_the_code_where_autofill_looks(self):
        with app.db() as c:
            body, st = auth_service.request(c, {'email': 'new@example.com', 'purpose': 'register'}, '10.0.0.1')
        self.assertEqual(st, 200, body)
        raw, html_file = self.last()
        subject = next(l for l in raw.splitlines() if l.startswith('Subject: '))[9:]
        code = re.fullmatch(r'语流验证码：(\d{6})', subject).group(1)  # one fixed form for every purpose
        body = raw.split('\n\n', 1)[1]
        self.assertEqual(body.splitlines()[0], f'验证码：{code}')
        self.assertIn('注册语流 Flow 的验证码，十分钟内有效', body)  # how long, in words
        self.assertIn('请勿把验证码转发', body)
        self.assertEqual(re.findall(r'\d+', body), [code])  # the code once, and no other number
        page = html_file.read_text(encoding='utf-8')
        self.assertEqual(page.count(code), 2)  # the preview line and the card
        seen = re.sub(r'<style.*?</style>|<[^>]+>', ' ', page, flags=re.S)
        self.assertEqual(set(re.findall(r'\d+', seen)), {code})
        self.assertIn(f'验证码：<span style="display:block', page)  # 「验证码：」 and the code in one line of text

    def test_the_reset_mail_still_tells_the_username(self):
        with app.db() as c:
            c.execute("INSERT INTO users(username,password,email) VALUES('xiaolin','x','lin@example.com')"); c.commit()
            auth_service.request(c, {'email': 'lin@example.com', 'purpose': 'reset'}, '10.0.0.2')
        raw, html_file = self.last()
        self.assertIn('你的用户名是：xiaolin', raw)
        self.assertIn('你的用户名是：xiaolin', html_file.read_text(encoding='utf-8'))

    def test_the_password_notice_is_laid_out_too(self):
        with app.db() as c:
            c.execute("INSERT INTO users(username,password,email) VALUES('xiaolin','x','lin@example.com')"); c.commit()
            uid = c.execute("SELECT id FROM users WHERE username='xiaolin'").fetchone()[0]
            with patch('threading.Thread') as thread:
                account_service.password_changed(c, uid, '修改')
                thread.call_args.kwargs['target']()  # send it here instead of on a thread
        raw, html_file = self.last()
        self.assertIn('Subject: Flow 密码已修改', raw)
        self.assertIn('忘记密码', raw)
        self.assertIn('密码已修改', html_file.read_text(encoding='utf-8'))

    def test_the_beta_still_marks_the_subject(self):
        with patch.dict(os.environ, {'FLOW_CHANNEL': 'beta'}), app.db() as c:
            auth_service.request(c, {'email': 'beta@example.com', 'purpose': 'register'}, '10.0.0.3')
        raw, _ = self.last()
        self.assertRegex(raw, r'Subject: 【内测版】语流验证码：\d{6}')

    def test_over_smtp_it_is_one_message_with_text_and_html(self):
        sent = []

        class Fake:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def login(self, *a): pass
            def send_message(self, msg): sent.append(msg)

        env = {'FLOW_SMTP_HOST': 'smtp.example.com', 'FLOW_SMTP_FROM': 'Flow <no-reply@flowlang.cn>', 'FLOW_SMTP_USER': 'u', 'FLOW_SMTP_PASSWORD': 'p'}
        with patch.dict(os.environ, env), patch.object(account_service.smtplib, 'SMTP_SSL', Fake):
            os.environ.pop('FLOW_MAIL_OUTBOX')
            text, page = mail_layout.message(['正文'], code='123456')
            account_service.mail('a@example.com', '语流 Flow 登录验证码：123456', text, html=page)
        msg = email.message_from_bytes(sent[0].as_bytes())
        self.assertEqual(msg.get_content_type(), 'multipart/alternative')
        parts = {p.get_content_type(): p.get_payload(decode=True).decode('utf-8') for p in msg.walk() if not p.is_multipart()}
        self.assertEqual(set(parts), {'text/plain', 'text/html'})
        self.assertTrue(parts['text/plain'].startswith('验证码：123456'))
        self.assertIn('123456', parts['text/html'])


PRIMARY = {'FLOW_SMTP_HOST': 'smtp.primary.example', 'FLOW_SMTP_FROM': 'Flow <no-reply@primary.example>', 'FLOW_SMTP_USER': 'u', 'FLOW_SMTP_PASSWORD': 'p'}
FALLBACK = {'FLOW_SMTP_FALLBACK_HOST': 'smtp.fallback.example', 'FLOW_SMTP_FALLBACK_FROM': 'Flow <me@fallback.example>',
            'FLOW_SMTP_FALLBACK_USER': 'u2', 'FLOW_SMTP_FALLBACK_PASSWORD': 'p2'}


class Servers:
    """Stand-ins for smtplib.SMTP_SSL / SMTP. how: host -> what goes wrong there ('connect', 'login', 'refuse' or
    'goodbye', a failed QUIT after the mail was taken). took: (host, From) of every mail a server took."""
    def __init__(self, **how):
        self.how, self.took = how, []
        servers = self

        class Connection:
            def __init__(self, host, port, local_hostname=None, **kw):
                self.host = host
                if servers.how.get(host) == 'connect':
                    raise ConnectionRefusedError(host)
            def __enter__(self): return self
            def __exit__(self, kind, *a):
                if kind is None and servers.how.get(self.host) == 'goodbye':
                    raise smtplib.SMTPResponseException(421, b'closing')
                return False
            def ehlo(self): pass
            def starttls(self, **kw): pass
            def login(self, *a):
                if servers.how.get(self.host) == 'login':
                    raise smtplib.SMTPAuthenticationError(535, b'no')
            def send_message(self, msg):
                if servers.how.get(self.host) == 'refuse':
                    raise smtplib.SMTPRecipientsRefused({msg['To']: (554, b'no')})
                servers.took.append((self.host, msg['From']))
        self.connection = Connection

    def __enter__(self):
        self.patches = [patch.object(account_service.smtplib, 'SMTP_SSL', self.connection), patch.object(account_service.smtplib, 'SMTP', self.connection)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self.patches:
            p.stop()


class Fallback(unittest.TestCase):
    """Two ways out (the owner, 2026-11-25: 「被拒收就用 i@jasa.hk，当然，优先 flowlang」): the primary first; a failure on
    the spot goes once more by the fallback; a code asked for again within account_service.AGAIN goes by the fallback
    first; mail_events says which one took it. Without FLOW_SMTP_FALLBACK_* everything is as before."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = dict(PRIMARY, **FALLBACK, FLOW_CHANNEL='', FLOW_PUBLIC_URL='https://flow.example.com')
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, env), patch.object(auth_service, 'RESEND', 0)]  # no one-minute wait here
        for p in self.patches:
            p.start()
        os.environ.pop('FLOW_MAIL_OUTBOX', None)
        app.init()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def send(self):
        return account_service.mail('a@example.com', 's', 't')

    def channels(self):
        with app.db() as c:
            return [tuple(r) for r in c.execute('SELECT status,channel FROM mail_events ORDER BY id')]

    def test_without_a_fallback_mail_goes_as_before(self):
        for k in FALLBACK:
            del os.environ[k]
        with Servers() as s:
            self.assertEqual(self.send(), 'primary')
        self.assertEqual(s.took, [('smtp.primary.example', PRIMARY['FLOW_SMTP_FROM'])])
        with Servers(**{'smtp.primary.example': 'connect'}), self.assertRaises(OSError):
            self.send()

    def test_a_failure_on_the_spot_goes_once_more_by_the_fallback(self):
        for what in ('connect', 'login', 'refuse'):
            with self.subTest(what), Servers(**{'smtp.primary.example': what}) as s:
                self.assertEqual(self.send(), 'fallback')
                self.assertEqual(s.took, [('smtp.fallback.example', FALLBACK['FLOW_SMTP_FALLBACK_FROM'])])

    def test_when_both_fail_the_mail_fails(self):
        with Servers(**{'smtp.primary.example': 'refuse', 'smtp.fallback.example': 'connect'}) as s, self.assertRaises(OSError):
            self.send()  # the last error, the fallback's
        self.assertEqual(s.took, [])

    def test_no_second_copy_once_the_server_took_the_mail(self):
        with Servers(**{'smtp.primary.example': 'goodbye'}) as s:
            self.assertEqual(self.send(), 'primary')
        self.assertEqual([host for host, _ in s.took], ['smtp.primary.example'])

    def test_preferring_the_fallback_still_falls_back_to_the_primary(self):
        with Servers() as s:
            self.assertEqual(account_service.mail('a@example.com', 's', 't', prefer='fallback'), 'fallback')
        with Servers(**{'smtp.fallback.example': 'login'}) as s:
            self.assertEqual(account_service.mail('a@example.com', 's', 't', prefer='fallback'), 'primary')
        self.assertEqual([host for host, _ in s.took], ['smtp.primary.example'])

    def test_a_code_asked_for_again_within_ten_minutes_goes_by_the_fallback(self):
        with Servers() as s, app.db() as c:
            c.execute("INSERT INTO users(username,password,email) VALUES('xiaolin','x','lin@example.com')"); c.commit()
            for purpose in ('login', 'login', 'reset'):  # the same purpose again, then another purpose
                body, st = auth_service.request(c, {'email': 'lin@example.com', 'purpose': purpose}, '10.0.0.9')
                self.assertEqual(st, 200, body)
            c.execute('UPDATE email_codes SET created=created-?', (account_service.AGAIN + 1,)); c.commit()
            auth_service.request(c, {'email': 'lin@example.com', 'purpose': 'login'}, '10.0.0.9')  # long after: the primary again
        self.assertEqual(self.channels(), [('sent', 'primary'), ('sent', 'fallback'), ('sent', 'primary'), ('sent', 'primary')])
        self.assertEqual([host for host, _ in s.took], ['smtp.primary.example', 'smtp.fallback.example', 'smtp.primary.example', 'smtp.primary.example'])

    def test_a_reset_link_asked_for_again_goes_by_the_fallback(self):
        with Servers(), app.db() as c:
            c.execute("INSERT INTO users(username,password,email) VALUES('xiaolin','x','lin@example.com')"); c.commit()
            uid = c.execute("SELECT id FROM users WHERE username='xiaolin'").fetchone()[0]
            self.assertTrue(account_service.issue(c, uid, 'lin@example.com', 'reset'))
            self.assertTrue(account_service.issue(c, uid, 'lin@example.com', 'reset'))
        self.assertEqual(self.channels(), [('sent', 'primary'), ('sent', 'fallback')])

    def test_a_failed_code_mail_is_counted_without_a_channel(self):
        with Servers(**{'smtp.primary.example': 'connect', 'smtp.fallback.example': 'connect'}), app.db() as c:
            body, st = auth_service.request(c, {'email': 'new@example.com', 'purpose': 'register'}, '10.0.0.8')
        self.assertEqual(st, 502, body)
        self.assertEqual(self.channels(), [('failed', None)])

    def test_only_code_mails_ask_for_the_fallback_first(self):
        """The weekly mail, the vocab reminder and the rest go by the primary first, to spare the fallback's daily limit."""
        flow = Path(__file__).resolve().parents[1]
        asking = {f.name for f in flow.glob('*.py') if "prefer='fallback'" in f.read_text(encoding='utf-8')}
        self.assertLessEqual(asking, {'account_service.py', 'auth_service.py'})
        self.assertIn('auth_service.py', asking)


if __name__ == '__main__':
    unittest.main()
