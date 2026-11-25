"""One look for every mail 语流 sends. 2026-11-24 the owner chose 「A 简洁卡片」; 2026-11-25 they asked for the real logo,
a plainer layout and codes that phones pick up reliably (via A0). So, as big companies' notices look: the logo at the
top, the words on one white card, one grey line at the bottom. Each mail goes as plain text and HTML together
(account_service.mail(..., html=...)): mail apps that show only text get the same words.

    text, html = mail_layout.message(['第一段', '第二段'], code='482915', rows=[('每周目标', '学了 5 天')],
                                     button=('打开语流', url), foot=[('不想再收到，点这里退订', link)])

The HTML is what mail apps render reliably: one column of tables (no sideways scrolling on a phone), inline styles for
the light look, dark overrides in one <style> under prefers-color-scheme (Apple 邮件 and others that support it; the rest
keep the light look or darken it themselves), a button that is a table cell (Outlook too), no web fonts.
The logo is the site's icon as a PNG the site serves (LOGO, 3x, width and height fixed), never inlined as base64
(Gmail and QQ 邮箱 block that), with 「语流 Flow」 as real text beside it: a mail app that blocks pictures still shows
the name, and the name follows dark mode. Every string given here is plain text and is escaped.

A code (验证码): the subject is 「语流验证码：482915」 (auth_service.send), the first line of the text and of the card is
「验证码：482915」 with the code alone on its own line in large type, one run of digits in one element (never split into
boxes or put in a picture), and the mail carries no other number near it: how long it lasts is written in words
(「十分钟内有效」) and nothing in the layout around it has digits. The preview line mail apps show under the subject is
the same 「验证码：482915」. Apple documents that iOS 17 / macOS 14 offer codes received in Mail for AutoFill and that web
fields should say autocomplete="one-time-code" (ours do); it does not document a mail format, so this keeps to the
plainest one.
"""
import base64
import html as _html
import os
import re

FONT = "-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Helvetica Neue',Arial,sans-serif"
GREEN = '#1f9d55'
INK, MUTED, BG, CARD = '#1b1d1a', '#6b7066', '#f4f5f3', '#ffffff'
FROM_LINE = '这封邮件由语流 Flow（flowlang.cn）自动发送，请不要直接回复。'
LIGHT = f'.fl-bg{{background:{BG}}}.fl-card{{background:{CARD}}}.fl-t{{color:{INK}}}.fl-m{{color:{MUTED}}}.fl-a{{color:#12733c}}'
DARK = ('.fl-bg{background:#111412!important}.fl-card{background:#1a1e1b!important}.fl-t{color:#e9ece7!important}'
        '.fl-m{color:#a1a89d!important}.fl-a{color:#6ee0a0!important}.fl-btn{background:#2fb56a!important}')
# Chinese numerals for how long something lasts, so that a code mail holds no digits but the code
NUMERALS = {5: '五', 10: '十', 15: '十五', 20: '二十', 30: '三十', 60: '六十'}


# The icon at the top of every mail (/mail-logo.png, served by app.py from here; 96 px, shown at 32): the site's mark
# (next.html's .brand svg: a #1f9d55 rounded square, rx 9 of 32, four white bars) rendered by Chrome with a
# transparent ground, so it sits on the light and the dark mail background alike.
LOGO_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAAFBUlEQVR4nOydPYwTRxiG39lzRZFESiIlBXaUxlFAilLFaRGRokhEkYIvde6ORK'
    'ny0+ZK6gQqfu96bCgACQlxHY2pEBKHuAZxpgCJo7jmKthhvvWu8c+uvfbO7syOv0c63fq8d7p9X8/sNz/2W4FmPtv8+Rvf9xpCiK8AWZfAYQF8'
    'qJ46hHJxoP73V+p/fwaIHSnlA8/zO09Xrt2DRgQ0ULu0/AM8nFSCn1APP4Lb7CnZbsLH1d1TrVvISCYDqpebfwqBP9RhHYuJahk4111rn8WczG'
    'VAdbP5GyTW1S8fBqOkUN2UwOnuSvsiZmQmAz6/0Ky+qWBDHR4HE8fW0musPvm93U37C6kNqG4sLwvIK2CmIiF+6a62WmnO9dKcVNts/svip4e0'
    'Is3SnLs07YTa5eX/1LdUf4wZ4tgHPx59f//G9u1JJ000IBBfyL/BzIfAt9NMSDQgbEL8ys8KmfDTkdf71x/djX86Br7h6ifpxjxmQFhq7oLRji'
    'pRa6Ml6lgVFNb5TA7EaTtkQDDC5UFWnhwPNe4z3ALU9AKYfBnRuG9AMLHGczu5QxqT1tHjvgHhrCZTAINaBwYE8/mLO6VsgnqoedgCgsUUplBC'
    'zcMuKFjJsorGp0fw19dNuEtPc0FruFJ6HVgCiT4q/Jn77eDLNYTwG0vvnTh6Ut0UvocFxIlPUGsgOi8ewSWkFA+93u4FO5jU5dBzkRGuQNpXaO'
    'sILMA1cdMh6560ZPDV+ORLLeeUCdK+Em6aYgxA2qsuqHQ71lziUKpFeSY/nDfA9gFdBY4yOqagYxsHdE4akDSgi35mkwlOdkFlGtA51wLKNqBz'
    'rgWUbUDHZahh2ADDsAGG0W6AqytZeV2XtiqoLAOfWcn7urQYUKaBzywUcV1auiBXV7KKuK7MLcDVlayiritzC3B1Jauo6+Iy1DBsgGHYAMOwAY'
    'ZhAwzDBhiGDTAMG2AYNsAwbIBh2ADDOLsxKytp3gyi4w0jbEAGOs+3kRXughIgcSctuFi1IuYqkch5vmmQDZhCJDaZQH2+jm5nEDYgJXmta2c2'
    'oKhqwVUKaQG6m61LZK6CiqoWXEVLCyiiWnAVbV1Q3tWCq2i/B/ArfjacK0PLVpUt5DjApu7RubmgslVlTraAMlVlZMABHPy8iJJUZQeVMKrJ2Q'
    '/ssLkqI+29Xk6WeRZxTom09yikDCXBvcGd2PEoIQ4WsIhzSr10Ps+35iMrk6oUV+eUSPsgwKG20XwJyyIIF2BOaW93tf1xOA4QN1WD+BUW4f6c'
    'EmkejYR9XAVTLKHm/QwZ1Q09Bn+CelHsqO7nCzrozwVRKiiYQhjUeihFqbrR7HKKRr5Q8mp3tV2NHg/PhgqcBpMvIxqP5Yipe8EdcJJSXmypvv'
    '+7wR+MrQdQHi6YXIjTdswASnqj2D0wWiFN44KeY8M8929sb1MApTo8BiY7Auvqxns+7qnENFVK/6QoVkoDBTM/Uvyv+v3EgLyJecKUg8smZIDE'
    'X2v9M+mUqYnagQncHc2O6nYmvfLfnZYSzhhOT1J2cBypt6XQH6Q8XHW4BSaJLdIorfhE6hYwSBDJKrHO0xY9aHqBRrjdlfZFzMhcBkQECay9YM'
    'pFnUXdoYm17lr7LOYkkwERQTBlkI0YxPNZtbKWA3vBYoqaz9891bqFjGgxYBCKRvR9r9ELiJN1imoKk5rKtvfoINwz9Yx2L/QW0P3O05Vr96CR'
    'twAAAP//MZ/zMgAAAAZJREFUAwDkV+nzLYRuNwAAAABJRU5ErkJggg==')


def esc(s):
    return _html.escape(str(s), quote=True)


def minutes(n):
    """「十分钟」 for 10: a duration in words (a code mail keeps its only digits for the code)."""
    return NUMERALS.get(int(n), str(int(n))) + '分钟'


def logo_url():
    """The site's icon for mails, from the site that sends them (FLOW_PUBLIC_URL: flowlang.cn, or the beta's own)."""
    return os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').rstrip('/') + '/mail-logo.png'


def message(paragraphs, code=None, code_label='验证码', rows=None, button=None, foot=None, title=None):
    """(text, html) of one mail.
    paragraphs: plain-text paragraphs. code: a one-time code, shown first. rows: (heading, detail) pairs, a list of
    facts (the weekly mail). button: (label, url). foot: (text, url or None) lines under the card, before the line
    saying where the mail comes from (an unsubscribe link goes here). title: a bold first line for mails without a code."""
    rows, foot = rows or [], foot or []
    # ---- plain text: the code first, then the same words in the same order
    text = []
    if code:
        text += [f'{code_label}：{code}', '']
    if title:
        text += [title, '']
    for p in paragraphs:
        text += [p, '']
    for k, v in rows:
        text.append(f'· {k}：{v}')
    if rows:
        text.append('')
    if button:
        text += [f'{button[0]}：{button[1]}', '']
    text += ['——'] + [f'{t}：{u}' if u else t for t, u in foot] + [FROM_LINE]
    # ---- HTML
    t, m = 'fl-t', 'fl-m'
    para = lambda s: f'<p class="{t}" style="margin:0 0 14px;font:15px/1.75 {FONT};color:{INK}">{esc(s)}</p>'
    inner = ''
    if code:
        # 「验证码：482915」 as one line of text, the code itself alone on its own line, large
        inner += (f'<p class="{t}" style="margin:0 0 18px;font:15px/1.6 {FONT};color:{INK}">{esc(code_label)}：'
                  f'<span style="display:block;margin-top:8px;font:700 34px/1.2 {FONT};letter-spacing:4px;'
                  f'font-variant-numeric:tabular-nums">{esc(code)}</span></p>')
    if title:
        inner += f'<p class="{t}" style="margin:0 0 16px;font:600 18px/1.5 {FONT};color:{INK}">{esc(title)}</p>'
    inner += ''.join(para(p) for p in paragraphs)
    if rows:
        inner += ''.join(
            f'<p style="margin:0 0 12px"><span class="{t}" style="display:block;font:600 15px/1.6 {FONT};color:{INK}">{esc(k)}</span>'
            f'<span class="{m}" style="display:block;font:14px/1.65 {FONT};color:{MUTED}">{esc(v)}</span></p>' for k, v in rows)
    if button:
        # a table cell with the colour (Outlook draws it), the link filling it
        inner += (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0 2px"><tr>'
                  f'<td class="fl-btn" bgcolor="{GREEN}" style="background:{GREEN};border-radius:8px">'
                  f'<a href="{esc(button[1])}" target="_blank" style="display:inline-block;padding:12px 24px;font:600 15px/1.2 {FONT};'
                  f'color:#ffffff;text-decoration:none;border-radius:8px">{esc(button[0])}</a></td></tr></table>')
    footer = ''.join((f'<a class="fl-a" href="{esc(u)}" style="color:#12733c">{esc(tx)}</a>' if u else esc(tx)) + '<br>' for tx, u in foot) + esc(FROM_LINE)
    # what mail apps show under the subject: the code line, or the title, or the first words
    preview = f'{code_label}：{code}' if code else (title or (paragraphs[0] if paragraphs else ''))
    preview = re.sub(r'\s+', ' ', preview)[:90]
    body = f"""<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all">{esc(preview)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="fl-bg" bgcolor="{BG}" style="background:{BG}"><tr><td align="center" style="padding:24px 12px 28px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px">
<tr><td style="padding:0 4px 16px"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="width:32px;vertical-align:middle"><img src="{esc(logo_url())}" width="32" height="32" alt="" style="display:block;width:32px;height:32px;border:0;border-radius:9px"></td>
<td class="{t}" style="padding-left:10px;vertical-align:middle;font:700 18px/1 {FONT};color:{INK};letter-spacing:.3px">语流 Flow</td></tr></table></td></tr>
<tr><td class="fl-card" bgcolor="{CARD}" style="background:{CARD};border-radius:12px;padding:28px 24px 24px;font-family:{FONT}">{inner}</td></tr>
<tr><td class="{m}" style="padding:16px 4px 0;font:12px/1.7 {FONT};color:{MUTED}">{footer}</td></tr>
</table></td></tr></table>"""
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark"><title>语流 Flow</title>
<style>{LIGHT}@media (prefers-color-scheme: dark){{{DARK}}}</style></head>
<body class="fl-bg" style="margin:0;padding:0;background:{BG};-webkit-text-size-adjust:100%">{body}</body></html>"""
    return '\n'.join(text).rstrip() + '\n', page
