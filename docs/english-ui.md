# 全英文界面（English mode）

语流 E1 · since 2026-11-26. A learner can switch the whole interface to English in 我的 → 使用习惯 (the title row,
「中文 | English」). Chinese is the default and stays the default; English is never picked from the browser's language.
While the English pages are being done it is open only on the 内测版 (and on a local test server).

## How it works

| part | what it does |
| --- | --- |
| `flow/public/src/next/00-i18n.js` | `uiLang()` ('zh' / 'en', read once before the first page), `zhEn(zh, en)`, the tables (`enTable()`), the page put into English as it is drawn, `qty()` `numText()` `dayMonth()` `weekday()` `listJoin()` |
| `flow/public/src/next/01-en-*.js` | the tables, one per area: `enTable({ '中文': 'English', … })` |
| `flow/public/src/next/07-lang.js` | the switch (`langSwitchHTML()` + `langSwitchWire(root)`), `setLang()`, kept with the account, the line to undo a switch |
| `flow/public/src/next/00-lang.css` | Latin fonts first under `html[lang=en]`, English for words in CSS `content:`, the switch and the undo line |
| `flow/ui_lang.py` | the request's language (`X-Flow-Lang: en`), `L(zh, en)`, English for the server's error messages (`ERRORS`) |
| `next_service.set_lang` | `/api/next/lang` → `next_profiles.lang` → `profile.lang` |
| `tools/check_i18n.py` | lists the Chinese in the front end and the server's error messages that have no English yet |

**Switching** reloads the page once (this device's copies of 今日 and the texts are cleared first). Signed in, the
choice is kept with the account and another device follows it; before signing in it stays on the device and goes to
the account after signing in. For 10 s after a switch a line offers to undo it, in both languages.

**Writing a page**
- Text drawn on the page (`innerHTML`, `textContent`, `aria-label`, `placeholder`, `title`, `alt`) gets its English
  from the tables, by its exact Chinese (spaces folded). A number in it is `{n}` in the key; any other part
  (a title, a word) `{x}`. The English names them `{1}`, `{2}` … in order; `{1|day|days}` picks the singular when that
  number is 1. Parts joined by ` · ` are looked up one by one.
  ```js
  enTable({
    '复习': 'Review',
    '今天还剩 {n} 次': '{1} left today',
    '{n} 个词': '{1} {1|word|words}',
    '「{x}」已收藏': 'Saved “{1}”',
  });
  ```
- Text that never reaches the page as text (`document.title`, `confirm()`, a canvas, a share text), or whose parts
  change order around markup, uses `zhEn('中文', 'English')` where it is made. `zhEn('中文')` looks it up in the tables.
  In `00-head.js` only the two-argument form works (the tables are not read yet there).
- Chinese meant to stay Chinese in English mode — a word's meaning, a translation, a Chinese source sentence, what the
  learner wrote — goes in an element with `data-zh`. It is not looked up, a screen reader reads it with a Chinese
  voice, and the missing-English check does not count it. `translate="no"` also leaves a part alone (the switch).
- Counts: `qty(n, '天', 'day')` → 「3 天」 / "3 days" (`qty(2, '个', 'box', 'boxes')` for an irregular plural).
  Dates: `dayMonth(d)` → 「11月26日」 / "Nov 26", `dayMonth(d, true)` with the year, `weekday(d)` → 「周四」 / "Thu".
  Lists: `listJoin(['听', '读'])`. Do not use `Intl.PluralRules`, `Intl.RelativeTimeFormat`, `Intl.ListFormat` or
  `Intl.DurationFormat`: older iPhones do not have them.
- The server: an answer's `error` gets its English from `ui_lang.ERRORS` by itself (add the line there). Other words
  the server writes for the page use `L('中文', 'English')`, or the page's tables. A value kept for everyone (a cache, a
  shared AI explanation) keeps the language in its key.

**Stays Chinese in English mode** (the same words in both modes): 用户协议, 隐私和数据 and every sentence that asks for
agreement (a grey English line may go under them, never instead of them); the logo and the page title 「语流 Flow」
(in running text and on buttons "Flow" is fine); the ICP number and its link; word meanings (the English meaning goes
above, the Chinese stays under it, small); exam explanations (考试练习的解析); the guide (操作指南, with one English line on
top: "The guide is in Chinese for now.").

**AI marks** in English mode carry both languages, Chinese first: 「AI 生成 · AI-generated」, 「AI 朗读 · AI voice」,
「朗读由 AI 合成 · AI voice」. Where that is too long, the Chinese alone. The small tag in a card's info line (`aiTag()`) is the
Chinese alone; the line on top of AI content (`aiMark()`) and the voice lines carry both.

## Style

- American English (color, favorite, practice as noun and verb). The default voice is American too.
- Sentence case everywhere: "Word plan", not "Word Plan". Brand names keep their case: IELTS, CET-4.
- Short and plain; the learner is reading in a second language. A button is a verb or a noun: "Save", "Next".
  No exclamation marks, no "please" on buttons, no "Oops".
- Numbers as digits ("3 words"), "min" in tight labels ("10 min"), "Beijing time" for 北京时间, "8 a.m." for 早上 8 点.
- Dates "Nov 26", "Thu"; weeks start on Monday.
- One word, one meaning: the table below is the only English for each term. A term not in it: add it here first.
- English that is learning material (texts, examples, questions) is never touched by any of this.

## Terms

| 中文 | English | note |
| --- | --- | --- |
| 语流 Flow | 语流 Flow (logo, page title) · Flow (in text) | |
| 今日 | Today | tab, page |
| 练习 | Practice | tab, page |
| 单词 | Words | tab, page |
| 我的 | Me | tab, page |
| 能力 | Skills | tab (the skills radar) |
| 内测版 / 内测 | Beta | 正式版 = the main site (flowlang.cn) |
| 材料 / 文章 / 一篇 | text | "a text", "Study a text"; never "material" |
| 学一篇 | study a text | |
| 听 · 读 · 理解 · 用出来 | Listen · Read · Check · Use it | the four steps |
| 这篇完成了 | Text done | finish card |
| 精选 | Featured | |
| 全部材料 | All texts | |
| 语流文章 | Flow text | |
| 我的文章 | My texts | the learner's own |
| 连载 | Series | |
| 轻松读 | Easy reading | |
| 背单词 | Learn words | |
| 背词计划 | Word plan | |
| 新词 | New words | |
| 复习 | Review | |
| 到期 / 待复习 | due | "12 due" |
| 不认识 · 模糊 · 认识 | Don't know · Not sure · Know it | review buttons (front) |
| 记错了 · 没错 | Wrong · Right | review buttons (after the answer) |
| 收藏 / 已收藏 | Save / Saved | to word cards |
| 保存 / 已保存 | Save / Saved | settings, a form |
| 存到本机 / 已存到本机 | Keep offline / Kept offline | |
| 单词卡 / 卡片 | card / word card | |
| 词书 | Word book | |
| 查词 | Look up | |
| 测词汇量 | Vocabulary test | |
| 错题本 · 错题和句型 | Mistake log · Mistakes & patterns | |
| 讲解 | Explanation (noun) · Explain (button) | |
| 看中文 | Show Chinese | under each AI explanation |
| 例句 | Example | |
| 释义 / 意思 | Meaning | |
| 表达 | Expression | |
| 生词 | New word | in a text |
| 跟读 | Shadow (button) · Shadowing (noun) | |
| 听写 | Dictation | |
| 精听 | Close listening | |
| 听一遍 | Play | |
| 复述 | Retell | |
| 仿写 / 改写 | Rewrite | |
| 翻译 | Translate | |
| 作文 | Essay | |
| 对话 | Dialogue | |
| 今日好句 | Line of the day | |
| 今日热点 | In the news | |
| 今日一读 | Today's read | |
| 听两句，答一句 | Two lines, one reply | |
| 能力雷达 | Skills radar | |
| 知识图谱 | Grammar map | |
| 语法点 | Grammar point | |
| 语法起点小测 | Grammar placement quiz | |
| 起点检查 | Placement check | |
| 词汇辨析 | Word pairs | |
| 口语路线 | Speaking path | |
| 雅思口语 | IELTS Speaking | |
| 发音入门 | Pronunciation basics | |
| 考试练习 | Exam practice | |
| 考试冲刺 | Exam sprint | |
| 混合练习 | Mixed practice | |
| 这周进步 | This week | card on 今日 |
| 我的进步 | My progress | |
| 周报 | Weekly report | |
| 使用习惯 | Preferences | 我的 → 使用习惯 |
| 设置 | Settings | |
| 外观 | Appearance | |
| AI 用量 | AI use | |
| 修改密码 · 退出所有设备 · 注销账号 | Change password · Sign out everywhere · Delete account | |
| 新手引导 · 使用提示 | tour · tips | |
| 开 · 关 | On · Off | |
| 新功能 · 改进 · 修好的问题 · 用法变了 | New features · Improvements · Fixes · Works differently | 更新记录 |
| 今日推荐 · 本周任务 · 还有时间的话 | Today's pick · This week's tasks · If you have time | 今日 |
| 早上好 · 中午好 · 下午好 · 晚上好 · 夜深了 | Good morning · Hello · Good afternoon · Good evening · It's late | greetings |
| 今日的样子 · 列表 · 卡片 | Today view · List · Cards | |
| 主题色 · 松绿 · 靛蓝 | Accent · Green · Indigo | |
| 新词卡 · 复习卡 · 简洁 · 详细 | New-word card · Review card · Simple · Detailed | |
| 字号 · 标准 · 大 · 特大 | Text size · Standard · Large · Extra large | |
| 行距 · 标准 · 宽松 | Spacing · Standard · Wide | 标准 is Standard everywhere |
| 朗读声音 · 美音 · 英音 · 女声 · 男声 | Voice · American · British · female · male | |
| 学习目标 | Goal | |
| 水平 | Level | |
| 入门 · 中级 · 中高级 · 高级 | Elementary (A2) · Intermediate (B1) · Upper intermediate (B2) · Advanced (C1) | |
| 每天 X 分钟 | X min a day | |
| 提醒 | Reminders | |
| 操作指南 | Guide | |
| 更新记录 | What's new | |
| 问题反馈 | Feedback | |
| 帮助 | Help | |
| 班级 | Class | |
| 老师 | Teacher | |
| 登录 · 注册 · 退出登录 | Sign in · Sign up · Sign out | |
| 账号 · 用户名 · 密码 · 邮箱 | Account · Username · Password · Email | |
| 验证码 | Code | |
| 返回 | Back | |
| 下一句 · 上一句 | Next · Previous | |
| 下一步 · 继续 | Next · Continue | |
| 完成 · 好的 · 知道了 | Done · OK · Got it | |
| 取消 · 关闭 | Cancel · Close | |
| 展开 · 收起 | Show · Hide | |
| 撤销 | Undo | |
| 重试 | Try again | |
| 正在打开… | Opening… | |
| AI 还在想 | The AI is still thinking | |
| AI 生成 | AI 生成 · AI-generated | both, Chinese first |
| AI 朗读（自然人声） | AI 朗读 · AI voice | both, Chinese first |
| 北京时间 | Beijing time | |
| 盲听 | Listen only | |
| 朗读 | Read aloud | AI 朗读: see the AI marks |
| 推荐 | Suggested | |
| 以后再说 | Not now | |
| 邀请码 | Invite code | |
| 我的班级 · 新建班级 | My class · New class | |
| 验证码登录 · 忘记密码 · 绑定邮箱 | Sign in with a code · Forgot password · Add your email | |
| 加到手机日历 | Add to phone calendar | |
| 话题卡 | cue card | IELTS |
| 记住率 | recall rate | |
| 中考 · 高考 · 四级 · 六级 · 考研 · 专四 · 专八 · 雅思 · 托福 | Zhongkao · Gaokao · CET-4 · CET-6 · Kaoyan · TEM-4 · TEM-8 · IELTS · TOEFL | exam names |
