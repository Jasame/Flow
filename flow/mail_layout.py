"""One look for every mail 语流 sends (owner's choice 2026-11-24: 「A 简洁卡片」): a small brand mark, a white card on a
light ground, a footer saying where the mail comes from. Each mail goes as plain text and HTML together
(account_service.mail(..., html=...)): mail apps that show only text get the same words.

    text, html = mail_layout.message(['第一段', '第二段'], code='482915', rows=[('每周目标', '学了 5 天')],
                                     button=('打开语流', url), foot=[('不想再收到，点这里退订', link)])

The HTML is what mail apps render reliably: tables, inline styles for the light look, dark overrides in one <style>
under prefers-color-scheme (Apple 邮件 and others that support it; the rest keep the light look), no images, no web
fonts, nothing loaded from elsewhere. Every string given here is plain text and is escaped.

A code (验证码) goes so that phones and password managers can pick it up: the first line of the text is
「验证码：482915」, the code is one run of digits in one element (never split into boxes or put in a picture), and
the caller puts it in the subject too (auth_service.send). Apple documents that iOS 17 / macOS 14 offer codes
received in Mail for AutoFill and that web fields should say autocomplete="one-time-code" (ours do); it does not
document a mail format, so this keeps to the plainest one.
"""
import html as _html

FONT = "-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Helvetica Neue',Arial,sans-serif"
MONO = "'SF Mono',Menlo,Consolas,'Courier New',monospace"
GREEN, INK, TINT = '#1f9d55', '#12733c', '#e9f5ee'
FROM_LINE = '这封邮件由语流 Flow（flowlang.cn）自动发送，请不要直接回复。'
LIGHT = ('.fl-bg{background:#f3f5f2}.fl-card{background:#ffffff}.fl-t{color:#1b1d1a}.fl-m{color:#5f6459}.fl-line{border-color:#e7e9e4}'
         '.fl-code{background:#e9f5ee;color:#12733c}.fl-btn{background:#1f9d55}.fl-a{color:#12733c}')
DARK = ('.fl-bg{background:#101412!important}.fl-card{background:#181d1a!important}.fl-t{color:#e8ebe6!important}'
        '.fl-m{color:#a3aa9f!important}.fl-line{border-color:#28302b!important}.fl-code{background:#173024!important;color:#6ee0a0!important}'
        '.fl-btn{background:#2fb56a!important}.fl-a{color:#6ee0a0!important}')


def esc(s):
    return _html.escape(str(s), quote=True)


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
    para = lambda s: f'<p class="{t}" style="margin:0 0 12px;font:15px/1.7 {FONT};color:#1b1d1a">{esc(s)}</p>'
    inner = ''
    if code:
        inner += (f'<p class="{t}" style="margin:0 0 6px;font:600 15px/1.6 {FONT};color:#1b1d1a">{esc(code_label)}：{esc(code)}</p>'
                  f'<div class="fl-code" style="margin:14px 0 20px;padding:18px 0;border-radius:10px;background:{TINT};color:{INK};'
                  f'text-align:center;font:700 36px/1 {MONO};letter-spacing:8px">{esc(code)}</div>')
    if title:
        inner += f'<p class="{t}" style="margin:0 0 14px;font:600 17px/1.5 {FONT};color:#1b1d1a">{esc(title)}</p>'
    inner += ''.join(para(p) for p in paragraphs)
    if rows:
        inner += ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 12px">' + ''.join(
            f'<tr><td class="fl-line" style="padding:12px 0;border-top:1px solid #e7e9e4">'
            f'<div class="{t}" style="font:600 15px/1.5 {FONT};color:#1b1d1a">{esc(k)}</div>'
            f'<div class="{m}" style="font:14px/1.6 {FONT};color:#5f6459">{esc(v)}</div></td></tr>' for k, v in rows) + '</table>')
    if button:
        inner += (f'<p style="margin:8px 0 4px"><a class="fl-btn" href="{esc(button[1])}" style="display:inline-block;background:{GREEN};'
                  f'color:#ffffff;text-decoration:none;font:600 15px {FONT};padding:12px 22px;border-radius:10px">{esc(button[0])}</a></p>')
    footer = ''.join((f'<a class="fl-a" href="{esc(u)}" style="color:{INK}">{esc(tx)}</a>' if u else esc(tx)) + '<br>' for tx, u in foot) + esc(FROM_LINE)
    body = f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="fl-bg" style="background:#f3f5f2"><tr><td align="center" style="padding:28px 14px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px">
<tr><td style="padding:0 6px 14px"><table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="width:28px;height:28px;background:{GREEN};border-radius:8px;color:#ffffff;font:700 15px/28px {FONT};text-align:center">流</td>
<td class="{t}" style="padding-left:9px;font:600 16px {FONT};color:#1b1d1a">语流 Flow</td></tr></table></td></tr>
<tr><td class="fl-card" style="background:#ffffff;border-radius:14px;padding:28px 24px;font-family:{FONT}">{inner}</td></tr>
<tr><td class="{m}" style="padding:16px 8px 0;font:12px/1.7 {FONT};color:#5f6459">{footer}</td></tr>
</table></td></tr></table>"""
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<style>{LIGHT}@media (prefers-color-scheme: dark){{{DARK}}}</style></head>
<body style="margin:0;padding:0">{body}</body></html>"""
    return '\n'.join(text).rstrip() + '\n', page
