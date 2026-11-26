"""界面语言 (全英文界面, 语流 E1, 2026-11-26; docs/english-ui.md): which language an answer is written in.

Chinese is the default and stays so. A page in English says so in every request it sends (header X-Flow-Lang: en,
00-head.js request()); anything else is Chinese, and the browser's own language is never looked at. app.py calls
use() at the start of each request, so a module can ask lang() or write L('中文', 'English') without the request being
passed down to it. The learner's choice itself is kept with the account (next_profiles.lang, next_service.set_lang).

Error messages need no change where they are written: app.send() gives an answer's 'error' its English from ERRORS
when the request is in English (english()). A message missing there goes out in Chinese; tools/check_i18n.py lists
those. Keys may hold numbers as {n}; the English names them {1}, {2} … in the order they come, and {1|day|days}
picks the singular when that number is 1 (the front end's enTable() reads the same way).

What an answer holds besides 'error' (plan lines, labels) is the page's to put into English (00-i18n.js), or the
module's, with L(). A value worked out once and kept for everyone (a cache, a shared AI explanation) must keep the
language in its key.
"""
import re
import threading

LANGS = ('zh', 'en')
_LOCAL = threading.local()
HAN = re.compile('[㐀-鿿豈-﫿]')
_NUM = re.compile(r'\d+(?:\.\d+)?')
_SLOT = re.compile(r'\{(\d+)(?:\|([^|{}]*)\|([^|{}]*))?\}')


def use(header):
    """This request's language, from its X-Flow-Lang header: 'en' only when it says so, else 'zh'."""
    _LOCAL.lang = 'en' if str(header or '').strip().lower() == 'en' else 'zh'


def lang():
    return getattr(_LOCAL, 'lang', 'zh')


def L(zh, en):
    """The text for this request: the English when the page is in English, else the Chinese."""
    return en if lang() == 'en' else zh


def fill(en, values):
    """An English template with its slots filled: {1} is the first value, {1|one|many} one of two words by it."""
    def slot(m):
        i = int(m.group(1)) - 1
        v = values[i] if 0 <= i < len(values) else ''
        if m.group(2) is None:
            return v
        try:
            return m.group(2) if float(v) == 1 else m.group(3)
        except ValueError:
            return m.group(3)
    return _SLOT.sub(slot, en)


def english(text, table=None):
    """The English for one of the server's Chinese messages: the exact text, or with its numbers as {n}; None when
    there is none (the caller keeps the Chinese)."""
    table = ERRORS if table is None else table
    if not isinstance(text, str) or not HAN.search(text):
        return None
    s = ' '.join(text.split())
    if s in table:
        return table[s]
    nums = _NUM.findall(s)
    if nums:
        en = table.get(_NUM.sub('{n}', s))
        if en is not None:
            return fill(en, nums)
    return None


def answer(obj):
    """An answer about to be sent: in an English request, its 'error' in English when ERRORS has it."""
    if lang() != 'en' or not isinstance(obj, dict) or not isinstance(obj.get('error'), str):
        return obj
    en = english(obj['error'])
    return obj if en is None else {**obj, 'error': en}


# The server's error messages in English (American spelling, sentence case, short; the terms in docs/english-ui.md).
# Key: the Chinese exactly as the code writes it, numbers as {n}. More come area by area (全英文界面 第 1 段).
ERRORS = {
    # app.py: every request
    '接口不存在': 'Not found',
    '材料或请求参数不正确': 'Something in the request is not right',
    '请求格式或参数不正确': 'Something in the request is not right',
    '服务暂时异常，请稍后重试': 'Something went wrong on our side. Please try again later',
    '用户名已存在，或数据关联无效': 'That username is taken, or something it refers to is missing',
    '不允许跨站请求': 'Requests from other sites are not allowed',
    '安全校验失败': 'Security check failed',
    '安全校验失败，请刷新页面': 'Security check failed. Please reload the page',
    '请求大小不正确': 'The request is the wrong size',
    '请先登录': 'Please sign in first',
    # next_service.py: settings kept with the account
    '没有这个主题色': 'No such accent color',
    '没有这个语言': 'No such language',
    '没有这个设置': 'No such setting',
    '材料不存在': 'Text not found',
    # ability_radar.py
    '目标等级不正确': 'Target level is not valid',
    '没有这项测评': 'No such test',
    '答案格式不正确': 'The answers are in the wrong format',
    '题目不存在': 'Question not found',
    '题目不正确': 'Question is not valid',
    'AI 听录音暂未开启，口语测评暂时做不了': 'AI listening is not available yet, so the speaking test cannot be done for now',
    '写 40–260 个英文词': 'Write 40–260 English words',
    # account_data.py
    '这是管理员账号，不能在这里注销': 'This is an admin account. It cannot be deleted here',
    '请输入密码': 'Please enter your password',
    '密码错了太多次，请 {n} 分钟后再试': 'Too many wrong passwords. Please try again in {1} {1|minute|minutes}',
    '密码不正确': 'Wrong password',
    '密码不正确，再错 {n} 次会暂停 {n} 分钟': 'Wrong password. After {1} more wrong {1|try|tries}, you will have to wait {2} {2|minute|minutes}',
    '密码不正确，已暂停 15 分钟': 'Wrong password. Please wait 15 minutes before you try again',
    # account_service.py
    '重置链接或密码不正确': 'The reset link or password is not valid',
    '重置链接已过期或已使用，请重新申请': 'This reset link has expired or was already used. Please ask for a new one',
    '绑定邮箱已变更，请重新申请': "The account's email has changed. Please ask for a new link",
    '管理员尚未配置邮件服务': 'Email is not set up on this site yet',
    '邮箱格式不正确': 'That email address is not valid',
    '该邮箱无法绑定': 'This email cannot be added to your account',
    '请两分钟后再发送': 'Please wait 2 minutes before sending again',
    '验证邮件发送失败，请联系管理员检查邮件服务': 'The confirmation email could not be sent. Please ask the admin to check the email service',
    '验证令牌不正确': 'The confirmation link is not valid',
    '验证令牌无效或已过期': 'The confirmation link is not valid or has expired',
    # adaptive_service.py
    '尚未到延迟验证时间；可以先做其他任务，或从词库选择普通练习。': 'This delayed check is not due yet. Do another task first, or pick a regular practice from the word bank',
    '任务已结束': 'This task has ended',
    '此任务已提交，请开始下一项': 'This task was already submitted. Please start the next one',
    '任务已暂停，请开始新任务': 'This task is paused. Please start a new one',
    '需要管理员权限': 'Admins only',
    '设置已在其他页面更新，请确认后再保存。': 'Your settings were changed on another page. Please check them, then save again',
    '请求标识已使用': 'This request ID was already used',
    # app.py
    '音频不存在': 'Audio not found',
    '登录内测版后显示': 'Sign in to the Beta to see this',
    '来源不存在': 'Source not found',
    '音频不存在或未开放': 'Audio not found or not available',
    '页面不存在': 'Page not found',
    '请求格式不正确，请刷新页面再试': 'The request is in the wrong format. Please reload the page and try again',
    '请求格式不正确': 'The request is in the wrong format',
    '请求必须为 JSON 对象': 'The request must be a JSON object',
    '排队较久，本次未调用模型，请稍后重试。': 'The wait was too long, so the AI was not asked this time. Please try again shortly',
    '操作过于频繁，请稍后再试': 'Too many tries. Please try again shortly',
    '这个账号已停用。如有疑问，请联系语流。': 'This account is disabled. If you have questions, please contact Flow',
    '登录已过期': 'You have been signed out',
    '排队较久，本次未调用模型。草稿保留，可稍后重试。': 'The wait was too long, so the AI was not asked this time. Your draft is kept; please try again shortly',
    '登录已过期，请重新登录': 'You have been signed out. Please sign in again',
    '新密码需 10–200 个字符': 'The new password must be 10–200 characters',
    '新密码不能与原密码相同': 'The new password must be different from the old one',
    '现在没有到期的语法复习。': 'No grammar review is due right now',
    '暂无可用题目': 'No questions are available right now',
    '这次测评已经提交过，答案不同的重复提交不会记录。': 'This test was already submitted. Sending it again with different answers is not recorded',
    '测评已过期，请重新开始': 'This test has expired. Please start again',
    '请完成所有题目': 'Please answer every question',
    # attempt_service.py
    '测评不存在或已过期': 'Test not found or expired',
    '测评已提交，提示不会再改变记录': 'This test was already submitted. Hints no longer change the record',
    '题目不属于本次测评': 'This question is not part of this test',
    # auth_service.py
    '请求类型不正确': 'Request type is not valid',
    '请输入有效的邮箱地址': 'Please enter a valid email address',
    '邮件服务暂未开启。请稍后再注册。': 'Email is not available yet. Please sign up later',
    '邮件服务暂未开启。请先用密码登录。': 'Email is not available yet. Please sign in with your password for now',
    '这个邮箱已经注册，可以直接用验证码登录。': 'This email is already signed up. You can sign in with a code',
    '这个邮箱还没有绑定账号。老账号请先用密码登录，再到「我的」里绑定邮箱。': 'No account uses this email yet. For an older account, sign in with your password, then add your email under “Me”',
    '没有找到绑定这个邮箱的账号。注册时没有填邮箱的话，请联系老师或管理员，在后台为你生成一个重设密码的链接。': 'No account uses this email. If you did not give an email when you signed up, ask your teacher or the admin to make you a password reset link',
    '操作过于频繁，请一小时后再试': 'Too many tries. Please try again in an hour',
    '这个班这一小时获取验证码的人太多了，请过一会儿再试': 'Too many people in this class asked for a code this hour. Please try again a little later',
    '这台设备获取验证码太频繁，请一小时后再试': 'This device has asked for codes too often. Please try again in an hour',
    '这个邮箱今天已经收到 {n} 封验证码了。为了这个邮箱的安全，请明天再试。': 'This email has had {1} {1|code|codes} today. To keep it safe, please try again tomorrow',
    '这个邮箱今天已经收到 {n} 封验证码了。为了这个邮箱的安全，请明天再试，或者先用密码登录。': 'This email has had {1} {1|code|codes} today. To keep it safe, please try again tomorrow, or sign in with your password for now',
    '现在注册的人很多，请过几分钟再试': 'Many people are signing up right now. Please try again in a few minutes',
    '验证码已发送，请 60 秒后再重新获取': 'A code was sent. You can ask for a new one in 60 seconds',
    '验证码邮件发送失败，请稍后再试': 'The code email could not be sent. Please try again shortly',
    '这个网络今天注册的账号已经很多了，请明天再试。班级的同学请用老师发的邀请链接注册。': 'Many accounts were signed up from this network today. Please try again tomorrow. Students in a class can sign up with the invite link from their teacher',
    '这个班今天通过邀请链接注册的人太多了，请联系老师。': "Too many people signed up with this class's invite link today. Please contact your teacher",
    '用户名需 2–40 个字符，不能有空格、@ 和 < > " \' / \\': 'A username must be 2–40 characters, with no spaces or @ < > " \' / \\',
    '密码需 10–200 个字符': 'The password must be 10–200 characters',
    '这个用户名已被使用，换一个试试': 'This username is taken. Try another one',
    '这个老师注册链接刚刚被用掉了。需要的话，请联系语流重新发一个。': 'This teacher sign-up link was just used. If you need one, please ask Flow for a new link',
    '这个邀请码的名额刚刚用完了，请向发码的人要一个新的。': 'This invite code was just used up. Please ask the person who gave it to you for a new one',
    '这个邮箱还没有绑定账号': 'No account uses this email yet',
    '请输入用户名或邮箱，以及密码': 'Please enter your username or email, and your password',
    '密码错了太多次，这个账号的密码登录暂停 {n} 分钟。可以用「验证码登录」或「忘记密码」。': 'Too many wrong passwords. Password sign-in for this account is paused for {1} {1|minute|minutes}. You can use “Sign in with a code” or “Forgot password”',
    '用户名、邮箱或密码不正确': 'Wrong username, email or password',
    '用户名、邮箱或密码不正确，再错 {n} 次会暂停 {n} 分钟': 'Wrong username, email or password. After {1} more wrong {1|try|tries}, password sign-in pauses for {2} {2|minute|minutes}',
    '用户名、邮箱或密码不正确，密码登录已暂停 15 分钟': 'Wrong username, email or password. Password sign-in is paused for 15 minutes',
    # beta_invites.py
    '内测版要凭邀请码注册，请填写收到的邀请码。': 'You need an invite code to sign up for the Beta. Please enter the code you were given',
    '邀请码错了太多次，请 15 分钟后再试': 'Too many wrong invite codes. Please try again in 15 minutes',
    '邀请码不对，请核对一下（字母不分大小写，横线可以不写）': 'That invite code is wrong. Please check it (capital letters do not matter, and the dashes can be left out)',
    # chat_service.py
    '知识点不存在': 'Topic not found',
    '问题需为1–1000字，请求标识不正确。': 'The question must be 1–1000 characters, and the request ID must be valid',
    '请求标识已被使用，请重新提问。': 'This request ID was already used. Please ask again',
    '导师还在回答，请稍候。': 'The tutor is still answering. Please wait',
    '已有训练请求正在处理，请稍候。': 'A practice request is already in progress. Please wait',
    '已有提问正在处理，请稍候再试。': 'A question is already in progress. Please try again shortly',
    '旧请求已被新请求接替，请刷新记录。': 'A newer request took over from this one. Please reload the history',
    # class_service.py
    '邀请码输错太多次了，请 {n} 分钟后再试': 'Too many wrong invite codes. Please try again in {1} {1|minute|minutes}',
    '请输入老师给你的 6 位邀请码': 'Please enter the 6-character invite code from your teacher',
    '没有找到这个邀请码，请核对后再输入': 'No class has this invite code. Please check it and try again',
    '这个班级已经停用，不能再加入': 'This class is closed and cannot be joined',
    '你是这个班的老师，不用加入；在首页「我的班级」里看全班汇总': 'You are the teacher of this class, so you do not need to join. See the class summary in “My class” on the home page',
    '老师账号不能加入班级。想以学生身份体验，请另外注册一个学生账号': 'Teacher accounts cannot join a class. To try it as a student, please sign up for a separate student account',
    '你现在没有加入班级': 'You are not in a class right now',
    '没有找到这个班级': 'Class not found',
    '班级名写 2–30 个字': 'A class name must be 2–30 characters',
    # coach_service.py
    '该测评已提交，请重新建立起点': 'This test was already submitted. Please take the placement check again',
    '起点检查不存在或已提交': 'Placement check not found or already submitted',
    '请求标识已用于其他消息': 'This request ID was already used for another message',
    # core_words.py
    '页码不正确。': 'Page number is not valid',
    '请检查搜索词、等级或练习筛选。': 'Please check the search word, level or practice filter',
    # corpus_service.py
    '每天最多提交 5 条语料反馈': 'You can send up to 5 content reports a day',
    # easy_reading.py
    '请选择难度感受': 'Please choose how hard it felt',
    '阅读时间不正确': 'Reading time is not valid',
    # exam_service.py
    '没有这个考试': 'No such exam',
    '这份练习已经交过或已过期，重新开始一份吧': 'This practice was already handed in or has expired. Please start a new one',
    # exam_sprint.py
    '考试日期的格式不对': 'The exam date is in the wrong format',
    '考试日期要在今天以后、三年以内': 'The exam date must be after today and within 3 years',
    '请先回答几个问题，设好学习目标和水平': 'Please answer a few questions first to set your goal and level',
    '没有这个题型': 'No such question type',
    '没有这一组': 'No such set',
    # feedback_service.py
    '请写几句发生了什么（至少 {n} 个字）': 'Please write a few lines about what happened (at least {1} {1|character|characters})',
    '说明请控制在 {n} 字以内': 'Please keep it to {1} characters or fewer',
    '今天收到的反馈太多了，请明天再试': 'We have had too much feedback today. Please try again tomorrow',
    '今天已经提交了 {n} 条，谢谢！明天再来吧': 'You have sent {1} {1|report|reports} today, thank you. Please come back tomorrow',
    '今天已经提交了 {n} 条，谢谢！登录后可以再提交': 'You have sent {1} {1|report|reports} today, thank you. Sign in to send more',
    # field_service.py
    '报错条数不对': 'Wrong number of error reports',
    # foundation_service.py
    '进度已同步到最新步骤': 'Your progress was updated to the latest step',
    # grammar_bank.py
    '没有这组语法点': 'No such set of grammar points',
    '没有这一类': 'No such category',
    # growth_service.py
    '已有进行中的阶段；如需调整，请明确选择替换计划': 'A stage is already in progress. To change it, choose to replace the plan',
    # ielts_speaking.py
    '没有这个问题': 'No such question',
    '没有这个话题': 'No such topic',
    '先回答至少一个问题': 'Answer at least one question first',
    '回答记录格式不正确': 'The answer record is in the wrong format',
    '没有这张话题卡': 'No such cue card',
    'Part 2 要说一段话：打字的话至少写 20 个英文词': 'Part 2 is a short talk. If you type, write at least 20 English words',
    '不认识的步骤': 'Unknown step',
    # import_service.py
    '文章需要 200–8000 个字符': 'A text must be 200–8000 characters',
    '这看起来不是英文文章': 'This does not look like an English text',
    '至少需要 3 个句子': 'It needs at least 3 sentences',
    '最多保存 {n} 篇，先删掉几篇旧的': 'You can keep up to {1} {1|text|texts}. Delete a few old ones first',
    '文章不存在': 'Text not found',
    # lab_service.py
    '请求标识已用于其他内容': 'This request ID was already used for something else',
    '正在处理，请稍候再刷新记录': 'Still working on it. Please reload the history in a moment',
    'AI 暂未开启，请先使用内置材料训练': 'AI is not available yet. Please practice with the built-in texts for now',
    '已有 AI 请求正在处理，请稍候': 'An AI request is already in progress. Please wait',
    '旧请求已被新的处理接替，请刷新记录。': 'A newer request took over from this one. Please reload the history',
    '语音分析尚未启用，请先升级网关或使用文字反馈': 'Voice analysis is not on yet. Upgrade the gateway, or use text feedback',
    '材料与回答合计过长，请缩短回答': 'The text and your answer are too long together. Please shorten your answer',
    '训练接口不存在': 'Practice route not found',
    '保存标识已用于其他内容': 'This save ID was already used for something else',
    '词汇本已满 500 项，请先整理': 'Your word list is full at 500 items. Please clear some out first',
    '词汇不存在': 'Word not found',
    # learning_service.py
    '练习内容需为 1–750 字符': 'Your practice answer must be 1–750 characters',
    '反馈记录与练习不匹配': 'The feedback does not match this practice',
    '保存标识不正确': 'Save ID is not valid',
    '保存标识已经使用': 'This save ID was already used',
    # meeting_service.py
    '先写一句英文再提交，例如 Photos pending. 最多可输入 1200 个字符。': 'Write a sentence in English before you submit, for example “Photos pending.” You can type up to 1200 characters',
    '请刷新页面后重试。': 'Please reload the page and try again',
    '这次请求已保存，请刷新后再提交新答案。': 'This request was already saved. Please reload before you submit a new answer',
    '这个任务目前无法提交，请打开今日学习查看下一步。': 'This task cannot be submitted right now. Please open Today to see the next step',
    '练习记录不完整，请返回答案页再试一次。': 'The practice record is incomplete. Please go back to the answer page and try again',
    '此练习已保存，请返回答案页。': 'This practice is already saved. Please go back to the answer page',
    '请按今日学习里的安排完成这项练习。': 'Please do this practice as planned in Today',
    '该练习需要登录。': 'Sign in to do this practice',
    # next_service.py
    '参数不正确': 'Something in the request is not right',
    '请先设置学习目标和水平': 'Please set your goal and level first',
    '请选择水平': 'Please choose a level',
    '声音不正确': 'No such voice',
    '选项不正确': 'That option is not valid',
    '每周目标是 1 到 7 天': 'The weekly goal is 1 to 7 days',
    '连载不存在': 'Series not found',
    '题目或选项不正确': 'The question or option is not valid',
    '请收藏英文单词、短语或句子': 'Please save an English word, phrase or sentence',
    '记录不存在': 'Record not found',
    '请用英文写至少一个短句': 'Please write at least one short sentence in English',
    'AI 听录音暂未开启，可以先用「对比回放」自己听': 'AI listening is not available yet. For now, use “Compare” to listen to yourself',
    '句子不存在': 'Sentence not found',
    '只能讲解材料里的句子': 'Only sentences from the text can be explained',
    '材料或难度不正确': 'The text or difficulty is not valid',
    '没有这一章': 'No such chapter',
    '只能查英文单词': 'You can only look up English words',
    '未知的入口': 'Unknown entry point',
    '这一项马上就开，先学今天这篇吧': "This is coming soon. Study today's text first",
    # output_service.py
    'AI 听录音暂未开启，可以先打字': 'AI listening is not available yet. You can type for now',
    '请用英文写至少 {n} 个词': 'Please write at least {1} {1|word|words} in English',
    '对话太长了，先结束这一轮吧': 'The dialogue is too long. Please end this round',
    '对话记录格式不正确': 'The dialogue record is in the wrong format',
    '短文需要 40–450 个英文词': 'The essay must be 40–450 English words',
    '这一句太短，换一句吧': 'This sentence is too short. Try another one',
    '翻译内容不完整': 'The translation is incomplete',
    '先取中文原句': 'Get the Chinese sentence first',
    '只能练发音入门里的词，或词典里的单词': 'You can only practice words from Pronunciation basics or the dictionary',
    # pilot_service.py
    '这道题已经提交过，结果不会改变。': 'This question was already submitted. The result will not change',
    '现在不是这道题的步骤，请刷新。': 'This is not the step for this question. Please reload',
    '这一步不能跳过。': 'This step cannot be skipped',
    '这道题现在不能看提示': 'Hints are not available for this question right now',
    '这道题没有提示': 'This question has no hint',
    '这次练习已经结束': 'This practice has ended',
    '这一步不能这样操作，请刷新。': 'That cannot be done at this step. Please reload',
    '先完成新通知验证，再结束本次听力。': 'Finish the new-notice check before you end this listening',
    # progress_service.py
    '设置不正确': 'That setting is not valid',
    '这个退订链接不完整，请从邮件里重新打开': 'This unsubscribe link is incomplete. Please open it again from the email',
    '这个退订链接已经失效（账号可能已经注销）': 'This unsubscribe link no longer works (the account may have been deleted)',
    # relisten_service.py
    '听懂了多少？选一项就好': 'How much did you understand? Just pick one',
    # skills_service.py
    '记录格式不正确': 'The record is in the wrong format',
    # teacher_service.py
    '试错太多次了，请 {n} 分钟后再打开链接': 'Too many wrong tries. Please open the link again in {1} {1|minute|minutes}',
    '这个老师注册链接不对。请把语流发给你的链接完整地复制到浏览器里打开。': 'This teacher sign-up link is not right. Please copy the whole link Flow sent you into your browser',
    '只有老师账号能建班。老师账号要用语流发的老师注册链接注册。': 'Only teacher accounts can create classes. A teacher account is signed up with a teacher sign-up link from Flow',
    '一个老师账号最多同时有 {n} 个在用的班级。需要更多，请联系语流。': 'A teacher account can have up to {1} active {1|class|classes} at a time. For more, please contact Flow',
    # tour_service.py
    '参数不对': 'Something in the request is not right',
    # tts_service.py
    '服务器朗读没有开启': 'Server voice is not on',
    '句子太多了': 'Too many sentences',
    '这段文字不在这篇文章里': 'This passage is not in this text',
    '这段文字不能朗读': 'This passage cannot be read aloud',
    '登录后可以用 AI 朗读': 'Sign in to use the AI voice',
    '今天导入文章的 AI 朗读用完了，明天再试；先用浏览器的声音': "Today's AI voice for your own texts is used up. Try again tomorrow; using the browser's voice for now",
    '今天的 AI 用量已满，北京时间早上 8 点恢复；先用浏览器的声音': "Today's AI use is full. It comes back at 8 a.m. Beijing time; using the browser's voice for now",
    '你的 AI 功能暂停中，先用浏览器的声音': "Your AI features are paused. Using the browser's voice for now",
    '今天用 AI 朗读的人多，导入的文章先用浏览器的声音': "Many people are using the AI voice today. Your own texts use the browser's voice for now",
    '今天的 AI 朗读用完了，先用浏览器的声音': "Today's AI voice is used up. Using the browser's voice for now",
    'AI 朗读暂时不能用，先用浏览器的声音': "The AI voice is not available right now. Using the browser's voice for now",
    'AI 朗读暂时没有生成出来': 'The AI voice could not be made this time',
    # two_lines.py
    '要带上这两句': 'Both lines are needed',
    '这两句不在这篇材料里': 'These two lines are not in this text',
    '句子序号不正确': 'Sentence number is not valid',
    '问题不正确': 'That question is not valid',
    # vocab_service.py
    '评分不正确': 'That rating is not valid',
    '这一张已经不能撤销了': 'This card can no longer be undone',
    '一次可以多学 {n}–{n} 个': 'You can learn {1}–{2} extra words at a time',
    '先选一本词书': 'Choose a word book first',
    '已经有 {n} 个新词没学，先学完它们吧': 'You have {1} new {1|word|words} not learned yet. Learn {1|it|them} first',
    '请选择词书': 'Please choose a word book',
    '每天新词可以是 {n}–{n} 个；记住率请从选项里选': 'New words a day can be {1}–{2}; pick the recall rate from the options',
    '单词每天的分钟数请从选项里选': 'Pick the daily minutes for words from the options',
    '测试结果不完整': 'The test results are incomplete',
    '内容太长了，一次最多导入约 500 个词': 'Too long. You can import about 500 words at a time',
    '没有识别到英文单词或短语，请每行一个': 'No English words or phrases found. Please put one on each line',
    '这一条已经没有了': 'This item is no longer there',
    '一次最多加 30 个词': 'You can add up to 30 words at a time',
    '请选今天或明天的一个时间': 'Please pick a time today or tomorrow',
    '提醒时间不正确': 'Reminder time is not valid',
    '先在账号设置里绑定邮箱，才能收到提醒邮件；也可以用「加到手机日历」': 'Add your email in account settings to get reminder emails. Or use “Add to phone calendar”',
    # next_service /api/next/zh (看中文 under an English AI explanation, 语流 B7)
    '一次最多 {n} 段': 'Up to {1} at a time',
    '今天「看中文」已经用了很多次，明天再看吧': "You've used “Show Chinese” a lot today. Try again tomorrow",
    '这会儿翻不出中文，稍后再试一次。': "Couldn't get the Chinese just now. Please try again shortly",
    # ai_quota.PAUSED after 语流 B7 #468 (问题反馈 under 我的 → 帮助)
    '你的 AI 功能暂停中；学材料、背单词和做题照常可以用。有疑问请在「我的 → 帮助 → 问题反馈」里说。':
        'Your AI features are paused. Texts, words and exercises still work. Questions? Me → Help → Feedback',
}
