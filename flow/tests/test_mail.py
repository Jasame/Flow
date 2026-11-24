"""Mail layout (mail_layout.py, the owner's 「A 简洁卡片」): every mail goes as text and HTML; a code is in the subject,
is the first line of the text and one run of digits in the HTML, so phones and password managers can pick it up; the
HTML loads nothing from elsewhere and escapes what it is given; the 内测版 still marks its subjects."""
import email, os, re, sys, tempfile, unittest
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
        self.assertEqual(len(re.findall(r'048213', page)), 2)  # the first line and the big code, each whole
        self.assertNotRegex(page, r'0\s*<[^>]+>\s*4')  # never one digit per box

    def test_the_html_loads_nothing_from_elsewhere_and_escapes_what_it_is_given(self):
        text, page = mail_layout.message(['<b>a</b> & "b"'], rows=[('x<y', 'z')], button=('打开', 'https://flowlang.cn/#/review'),
                                         foot=[('退订', 'https://flowlang.cn/api/next/weekly-mail/off?t=1&x=2')])
        for bad in ('<img', ' src=', 'url(', '@import', '<link', '<script'):
            self.assertNotIn(bad, page)
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
        code = re.fullmatch(r'语流 Flow 注册验证码：(\d{6})', subject).group(1)
        first = raw.split('\n\n', 1)[1].splitlines()[0]
        self.assertEqual(first, f'验证码：{code}')
        self.assertIn(f'{auth_service.TTL // 60} 分钟内有效', raw)
        self.assertIn('请勿把验证码转发', raw)
        page = html_file.read_text(encoding='utf-8')
        self.assertEqual(page.count(code), 2)

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
        self.assertRegex(raw, r'Subject: 【内测版】语流 Flow 注册验证码：\d{6}')

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


if __name__ == '__main__':
    unittest.main()
