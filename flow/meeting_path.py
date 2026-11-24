"""Seven short, original workplace English exercises and their public previews."""
from html import escape

TITLE = '7 天练习英文进度汇报'
DAYS = (
    dict(title='汇报项目进度', context='你正在更新团队的网站。首页草稿已完成，客户还没发来图片。你打算明天跟进。', example='We’ve finished the homepage draft. We’re still waiting for the client’s photos. I’ll follow up tomorrow.', checks=('已完成的工作', '现在的阻碍', '接下来会做什么'), slug='meeting-update'),
    dict(title='说清楚卡在哪里', context='回想昨天怎么说「还在等」。今天是发布前的例会，测试已经做完，但你还在等同事确认文案。说明卡在哪里，并说你会联系谁。', example='We’re still waiting for the final copy. I’ll check with Mei this afternoon.', checks=('正在等待的内容', '跟进动作'), slug=''),
    dict(title='解释为什么要延期', context='原定周三发出报价。供应商还没确认价格，所以你预计周五才能发出。说明原因和新时间。', example='We can’t send the quote on Wednesday because the supplier hasn’t confirmed the price. We expect to send it on Friday.', checks=('延期的原因', '更新后的时间'), slug='explain-delay'),
    dict(title='提出一个下一步建议', context='你们拿不到最终的活动照片。会议上请提出一个可执行的建议，例如先用临时图片完成页面。', example='I suggest using a temporary image so we can finish the page layout today.', checks=('引出一个建议', '描述具体行动'), slug='suggest-next-step'),
    dict(title='确认负责人和截止时间', context='上一次你给出了一项建议。这次请在会后确认安排：Alex 负责检查最终文案，周四前完成，你来发提醒。', example='Alex will review the final copy by Thursday. I’ll send a reminder.', checks=('谁负责', '何时完成', '你的跟进动作'), slug=''),
    dict(title='回答临时追问', context='项目会上同事突然问：“Can we still launch on Friday?” 目前还不确定，你需要先和测试团队确认，并会在下午三点前回复。', example='I can’t confirm yet. I’ll check with the testing team and get back to you by three.', checks=('说明现在能否确认', '如何核实', '何时回复'), slug=''),
    dict(title='换一个项目，再做一次汇报', context='你在筹备一场活动。场地已订好，报名表还在等批准。你打算下午联系负责审批的同事。请在例会上汇报进度。', example='We’ve booked the venue. We’re still waiting for approval on the registration form. I’ll check with the person in charge this afternoon.', checks=('已完成的工作', '现在的阻碍', '接下来会做什么'), slug=''),
)
PUBLIC = {item['slug']: day for day, item in enumerate(DAYS, 1) if item['slug']}


def task(day):
    item = DAYS[day - 1]
    return {key: item[key] for key in ('title', 'context', 'checks')} | {'day': day}


def public_page(slug):
    day = PUBLIC[slug]
    item = DAYS[day - 1]
    title = escape(item['title'])
    related = ''.join(
        f'<li><a href="/practice/{other}/">{escape(DAYS[number - 1]["title"])}</a></li>'
        for other, number in PUBLIC.items() if other != slug
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}｜语流 Flow 英文会议练习</title>
<meta name="description" content="{escape(item["context"], quote=True)}用三分钟练习并检查你的英文表达。">
<link rel="canonical" href="https://flowlang.cn/practice/{slug}/">
<link rel="stylesheet" href="/meeting.css?v=440">
<link rel="stylesheet" href="/flow4.css?v=440">
<meta name="theme-color" content="#fbfcfb">
</head><body class="meeting-public"><main class="meeting-landing">
<a href="/" class="meeting-brand">语流 Flow</a>
<h1>{title}</h1>
<p>{escape(item["context"])}</p>
<h2>回答时试着讲清楚</h2>
<ul>{''.join(f'<li>{escape(check)}</li>' for check in item['checks'])}</ul>
<a class="meeting-cta" href="/?trial={day}#try-meeting/{day}">开始练习 · 约 3 分钟</a>
<p>测试期间，所有内容和功能均免费。你可以直接练习，登录后保存学习进度。</p>
<details><summary>查看英文示例</summary><p lang="en">{escape(item["example"])}</p></details>
<nav aria-label="其他会议练习"><h2>继续练习</h2><ul>{related}</ul></nav>
</main></body></html>'''.encode('utf-8')

# Each item pairs the scenario detail with an expression that can support the objective.
# Evidence is reported as a clue; learners can judge answers outside these examples.
NEGATIVE = r"\b(?:not|never|nobody|no one|haven't|hasn't|aren't|isn't|won't|didn't|don't|can't|cannot)\b"
PHOTO = r"\b(?:photos?|pictures?|images?|assets?)\b"
DRAFT = r"\b(?:draft|homepage|home page)\b"
ACTION = r"\b(?:follow up|chase|check|ask|contact|reach out|message|email|call|remind|ping|get in touch)\b"
WAIT = r"\b(?:wait(?:ing)?|await(?:ing)?|owes?|pending|missing|outstanding|still need|haven't received|hasn't sent|has not sent|yet to (?:send|arrive)|need|not received)\b"
SUGGEST = r"\b(?:suggest|recommend|could we|we could|what if|how about|let's|shall we|why don't we)\b"
CRITERIA = (
    (
        (DRAFT, r"\b(?:finished|completed|ready|done|in place|wrapped up)\b", NEGATIVE),
        (PHOTO, WAIT, r"\b(?:nobody|no one|not waiting|aren't waiting|received the|already (?:sent|received))\b"),
        (r"\btomorrow\b", ACTION, NEGATIVE),
    ),
    (
        (r"\b(?:copy|wording|text|content)\b", WAIT, r"\b(?:not waiting|already (?:sent|received|approved))\b"),
        (r"\b(?:mei|colleague|teammate|copywriter|editor|team|them|her|him|owner)\b", ACTION, NEGATIVE),
    ),
    (
        (r"\b(?:supplier|vendor|price|pricing|cost)\b", r"\b(?:hasn't confirmed|has not confirmed|haven't confirmed|not been confirmed|not confirmed|pending|awaiting|waiting|yet to confirm|still need|unconfirmed|not final)\b", None),
        (r"\bfriday\b", r"\b(?:send|issue|share|deliver|go out|sent|ready|push|move|reschedule)\b", NEGATIVE),
    ),
    (
        (PHOTO, SUGGEST, None),
        (PHOTO, r"\b(?:use|using|add|adding|place|placing|choose|choosing|swap|replace|temporary|placeholder|stock)\b", None),
    ),
    (
        (r"\balex\b", r"\b(?:review|check|read|verify|approve|proofread|look over)\b", NEGATIVE),
        (r"\bthursday\b", r"\b(?:by|before|deadline|until|due|no later than)\b", NEGATIVE),
        (r"\b(?:remind|reminder|follow up|check in)\b", r"\b(?:i'll|i will|i can|i plan|i am going|i'm going|i'll be)\b", NEGATIVE),
    ),
    (
        (r"\b(?:can.t confirm|cannot confirm|not sure|uncertain|not yet|don.t know|too early to say)\b", r"\b(?:confirm|sure|uncertain|yet|know|early)\b", None),
        (r"\b(?:testing|test team|qa|testers?)\b", r"\b(?:check|ask|confirm|speak|talk|verify|contact)\b", NEGATIVE),
        (r"\b(?:three|3)(?:\s*(?:pm|p\.m\.))?\b", r"\b(?:get back|reply|respond|update|let you know|tell you|answer)\b", NEGATIVE),
    ),
    (
        (r"\b(?:venue|space|room|location)\b", r"\b(?:booked|reserved|confirmed|secured|sorted|arranged)\b", NEGATIVE),
        (r"\b(?:registration|form|signups?|sign-ups?)\b", r"\b(?:wait(?:ing)?|pending|not approved|yet to approve|approval|await(?:ing)?|needs sign.off)\b", r"\b(?:already approved|got approval|was approved|has been approved)\b"),
        (r"\b(?:this afternoon|later today)\b", ACTION, NEGATIVE),
    ),
)

FRAMES = (
    "We've finished ___. We're still waiting for ___. I'll ___ tomorrow.",
    "We're still waiting for ___. I'll check with ___.",
    "We need to delay ___ because ___. We expect to send it on ___.",
    "Could we use ___ so we can ___?",
    "___ will review ___ by ___. I'll send ___.",
    "I can't confirm yet. I'll check with ___ and get back to you by ___.",
    "We've booked ___. We're waiting for approval on ___. I'll contact ___ this afternoon.",
)
