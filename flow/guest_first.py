"""4.5.0: the guest home's first screen as static HTML.

Visitors without a session used to see an empty page until about 45 deferred scripts had loaded, because the guest
home is drawn by meetingGuestHome() in public/meeting.js. For a bare "/" without a session, app.py now puts the same
markup into <div id="app">, so it shows as soon as the stylesheets arrive; meeting.js then replaces it with identical
markup. public/guest-first.js (loaded in <head>) hides it when the address has a hash route such as #login, which the
server cannot see. tests/test_guest_first.py keeps the lists below in step with meeting.js.
"""
from html import escape

BRAND = ('<div class="brand"><span class="mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M8 21V14M14 25V8M20 22V11M26 18V14" '
         'stroke="currentColor" stroke-width="3.5" stroke-linecap="round"/></svg></span><span>Flow<small>语流 · 英语学习</small></span></div>')
TOPICS = [(1, '汇报项目进度'), (3, '解释为什么要延期'), (4, '提出一个下一步建议')]
WORKSPACE = [
    ('home', 'AI 私教', '按目标安排练习，继续上次的对话。'),
    ('studio', '语料库', '选一篇材料，练听、说、读、写。'),
    ('vocab', 'AI 词汇', '学词义和搭配，把词用进句子。'),
    ('learn', '语法学习', '按知识点读讲解、做练习。'),
    ('review', '复习中心', '回练到期的词汇和语法。'),
    ('report', '学习档案', '回看自己的作答和修订。'),
    ('graph', '知识图谱', '查看词汇、语法和材料之间的联系。'),
    ('quiz', '诊断测评', '了解当前基础和下一步。'),
    ('practice', '专项练习', '集中练习需要巩固的技能。'),
]


def trial(day):
    return '/?trial=%d#try-meeting/%d' % (day, day)


def markup():
    topics = ''.join('<li><a href="%s"><strong>%s</strong><span>不用登录 · 约 3 分钟</span></a></li>' % (trial(d), escape(t)) for d, t in TOPICS)
    links = ''.join('<li><a href="/?account=1#%s"><strong>%s</strong><span>%s</span></a></li>' % (r, escape(t), escape(x)) for r, t, x in WORKSPACE)
    return (
        '<main class="meeting-landing meeting-guest-home flow-first">'
        '<header>' + BRAND + '<div class="meeting-guest-tools"><a class="jasa-back" href="https://jasa.hk/" aria-label="返回 Jasa Studio">'
        '<span aria-hidden="true">←</span><span class="jb-long">Jasa Studio</span><span class="jb-short">Studio</span></a>'
        '<a class="text-button" href="/?account=1#login">登录</a></div></header>'
        '<section class="card meeting-focus"><div class="meeting-focus-copy"><h1>你的长期 AI 英语私教</h1>'
        '<p>用语料、词汇和语法练习打基础，让私教根据你的目标和学习记录安排下一步。</p>'
        '<p class="meeting-beta">测试期间，所有内容和功能均免费。</p>'
        '<div class="meeting-home-actions"><a class="meeting-cta" href="' + trial(1) + '">先试一道练习</a>'
        '<a class="text-button" href="/?account=1#home">登录，进入学习空间</a></div></div>'
        '<figure class="meeting-preview"><figcaption>登录后的“今日学习”<span>示例</span></figcaption>'
        '<div class="mp-card mp-due"><strong>复习到期内容</strong><span>现在有 1 项词汇或语法可以回练。</span><em>开始复习</em></div>'
        '<div class="mp-card"><strong>7 天练习英文进度汇报</strong><span>2 / 7 项已完成</span><b class="mp-bar" aria-hidden="true"><i></i></b></div>'
        '<ol class="mp-plan"><li><b aria-hidden="true">1</b><span>单项训练：听力理解</span><small>5 分钟</small></li>'
        '<li><b aria-hidden="true">2</b><span>到期复习：不定代词与单数</span><small>5 分钟</small></li>'
        '<li><b aria-hidden="true">3</b><span>验证理解：不定代词与单数</span><small>5 分钟</small></li></ol></figure></section>'
        '<nav class="meeting-trial-links" aria-label="公开练习"><h2>先试一道练习</h2><p class="muted">不用登录，用英文写一到三句，约 3 分钟。</p>'
        '<ul>' + topics + '</ul></nav>'
        '<nav class="meeting-workspace-links" aria-label="学习空间"><h2>学习空间 <span class="meeting-login-tag">登录后可用</span></h2>'
        '<p class="muted">登录后进入所选模块，学习进度会同步到你的账号。</p><ul>' + links + '</ul></nav></main>'
    )


MARKER = b'<div id="app"></div>'


def inject(index):
    """index.html bytes with the first screen inside #app (unchanged if the marker is missing)."""
    if MARKER not in index:
        return index
    return index.replace(MARKER, b'<div id="app">' + markup().encode('utf-8') + b'</div>', 1)
