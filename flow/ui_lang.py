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
}
