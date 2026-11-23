"""Flow output practice: retell, role-play dialogue, essays, translation and pronunciation checks.

All of it is built around one material, so speaking and writing reuse what was just read and heard.
Each call is one AI job (shared daily quota). Results feed the learner model: a skill event for the
ability profile, and corrections into the mistake book.
"""
import json
import re
import time

import next_service as nx
import skills_service as sk

LEVEL_NOTE = {'A2': '学习者是入门水平，反馈用简单中文，示范用最常见的词和短句。', 'B1': '学习者是中级水平，反馈用中文，示范句清楚自然。',
              'B2': '学习者是中高级水平，关注搭配、语气和衔接。', 'C1': '学习者是高级水平，关注措辞精确、语域和行文层次。'}
FIX = '{"from":"学习者原文片段","to":"改后片段","why":"简短中文原因","node":"相关语法节点 id 或 null"}'


def _material(c, uid, data):
    row = nx._pack_row(c, uid, str(data.get('pack', '')))
    if not row:
        return None, None
    p = json.loads(row['content'])
    level = (nx.profile(c, uid) or {}).get('level') or nx.cefr(p)
    return p, level


def _ai(c, uid, data, kind, pack, skill, spec, system, user, convert, audio=None):
    from lab_service import run_job
    from chat_service import request_model
    msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
    return run_job(c, uid, str(data.get('request_id', '')), kind, pack, skill, spec,
                   (lambda: request_model(msgs, audio=audio)) if audio else (lambda: request_model(msgs)), convert, mark_replay=True)


def _clean(v, lo=0, hi=600):
    from lab_service import text
    return text(v if isinstance(v, str) else '', lo, hi)


def _fixes(raw, valid):
    out = []
    for ch in (raw or [])[:6]:
        if isinstance(ch, dict) and isinstance(ch.get('to'), str) and ch['to'].strip():
            out.append({'from': _clean(ch.get('from') or '—', 1, 200), 'to': _clean(ch['to'], 1, 200), 'why': _clean(ch.get('why') or '—', 1, 300),
                        'node': ch.get('node') if ch.get('node') in valid else None})
    return out


def _audio_or_text(data, min_words=3, max_chars=2500):
    """(text, audio, error): learners may type or speak."""
    from lab_service import audio_enabled
    from audio_validation import validate_audio
    audio = data.get('audio')
    if audio is not None:
        if not audio_enabled():
            return None, None, ({'error': 'AI 听录音暂未开启，可以先打字'}, 503)
        validate_audio(audio)
        return '', audio, None
    text = data.get('text')
    if not isinstance(text, str) or len(nx.WORD.findall(text)) < min_words or len(text) > max_chars:
        return None, None, ({'error': f'请用英文写至少 {min_words} 个词'}, 400)
    return text.strip(), None, None


# ---------- retell ----------

def retell(c, uid, data):
    p, level = _material(c, uid, data)
    if not p:
        return {'error': '材料不存在'}, 404
    text, audio, err = _audio_or_text(data, 8)
    if err:
        return err
    valid = set(nx.nodes_meta(c))
    exprs = [e['text'] for e in p.get('expressions', [])][:6]
    system = ('你是英语老师，学习者刚读完一篇材料，正在用自己的话复述。' + LEVEL_NOTE.get(level, '') +
              '先从原文里提炼 4–6 个要点，再判断复述讲到了哪些、漏了哪些；表扬用上的原文表达；改出最影响理解的语言错误（最多 4 条）；'
              '最后给一段同等水平、80–120 词的示范复述。不要编造原文没有的内容。只输出 JSON。')
    user = ('原文：\n' + p['body'] + '\n\n原文里的地道表达：' + ('、'.join(exprs) or '无') + '\n可用语法节点：' + nx._node_list(c) +
            ('\n\n学习者的复述（录音，请先忠实转写，听不清写 [听不清]）。' if audio else '\n\n学习者的复述：\n' + text) +
            '\n\n输出 JSON：{' + ('"transcript":"转写",' if audio else '') +
            '"points":[{"point":"中文要点","covered":true}],"used":["学习者用上的原文表达"],"fixes":[' + FIX + '],'
            '"comment":"一两句中文总评，先说优点","model":"示范复述（英文）"}')

    def convert(raw):
        if not isinstance(raw, dict) or not isinstance(raw.get('points'), list):
            raise ValueError('bad')
        pts = [{'point': _clean(x.get('point'), 1, 200), 'covered': bool(x.get('covered'))} for x in raw['points'][:8] if isinstance(x, dict) and x.get('point')]
        if not pts:
            raise ValueError('no points')
        return {'transcript': _clean(raw.get('transcript') or '', 0, 2500) if audio else text, 'points': pts,
                'used': [_clean(u, 1, 120) for u in (raw.get('used') or [])[:6] if isinstance(u, str) and u.strip()],
                'fixes': _fixes(raw.get('fixes'), valid), 'comment': _clean(raw.get('comment') or '', 0, 400), 'model': _clean(raw.get('model') or '', 0, 1500)}

    spec = {'pack': p['id'], 'text': text, 'audio': bool(audio)}
    result, status = _ai(c, uid, data, 'next-retell', p['id'], 'speaking' if audio else 'writing', spec, system, user, convert, audio)
    if status == 200:
        r = result['result']
        r['score'] = round(sum(x['covered'] for x in r['points']) / len(r['points']) * (1 - 0.06 * min(4, len(r['fixes']))), 2)
    if status == 200 and not result.get('replayed'):
        r = result['result']
        sk.log(c, uid, 'speaking' if audio else 'writing', 'retell', r['score'], nx.cefr(p), p['id'], commit=False)
        sk.mistakes_from_changes(c, uid, r['fixes'], r['transcript'], 'speaking' if audio else 'writing', p['id'])
    return result, status


# ---------- role-play dialogue ----------

def dialog(c, uid, data):
    """Role-play around the material's speaking task, or a scene of the speaking route (data['scenario']).
    The client keeps the history; each call is one AI turn."""
    sc = __import__('scenarios').pack(data.get('scenario')) if isinstance(data.get('scenario'), str) else None
    if sc:
        p, level = sc, (nx.profile(c, uid) or {}).get('level') or sc['cefr']
    else:
        p, level = _material(c, uid, data)
    if not p:
        return {'error': '材料不存在'}, 404
    hist = data.get('history') or []
    if not isinstance(hist, list) or len(hist) > 16:
        return {'error': '对话太长了，先结束这一轮吧'}, 400
    turns = []
    for h in hist:
        if not isinstance(h, dict) or h.get('role') not in ('ai', 'me') or not isinstance(h.get('text'), str) or len(h['text']) > 500:
            return {'error': '对话记录格式不正确'}, 400
        turns.append(f"{'AI' if h['role'] == 'ai' else '学习者'}：{h['text']}")
    end = bool(data.get('end'))
    text, audio = '', None
    if hist and not end:
        text, audio, err = _audio_or_text(data, 1, 500)
        if err:
            return err
    valid = set(nx.nodes_meta(c))
    task = p.get('speaking') or f"围绕「{p['title']}」这个话题聊一聊"
    system = ('你在和一位中国英语学习者做情景对话练习。' + LEVEL_NOTE.get(level, '') + '你扮演情景里的另一方，说话自然、简短（1–3 句），'
              '用学习者水平能听懂的英语，适时追问让对方多说。不要替学习者回答。只输出 JSON。')
    scene = (f"情景：{p['title']}（{p['title_en']}）\n{p['body']}\n口语任务：{task}" if sc else
             f"材料：{p['title']}\n材料内容：{p['body'][:1500]}\n口语任务：{task}")
    if not hist:
        user = scene + '\n\n开始对话：先用一句中文说明情景和你扮演的角色，再用英文说第一句。输出 JSON：{"scene":"中文情景说明","role":"你扮演的角色（中文）","reply":"你的第一句英文"}'
    elif end:
        user = (scene + '\n\n对话记录：\n' + '\n'.join(turns) + '\n\n对话结束。请总结学习者这轮的表现。输出 JSON：'
                '{"summary":"两三句中文总评，先说优点","good":["学习者说得好的英文句子"],"fixes":[' + FIX + '],'
                '"expressions":[{"text":"值得学的英文表达","meaning":"中文"}],"score":0.0到1.0之间的数字}')
    else:
        user = (scene + '\n\n对话记录：\n' + '\n'.join(turns) +
                ('\n学习者刚才说了一句话（录音，先忠实转写）。' if audio else '\n学习者刚说：' + text) +
                '\n\n接着对话。输出 JSON：{' + ('"heard":"转写",' if audio else '') +
                '"reply":"你的下一句英文","correction":{"original":"学习者原话里有问题的部分","better":"更自然的说法","why":"中文原因"} 或 null,'
                '"hint":"给学习者的一句中文提示：下一句可以怎么接"}')

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        if not hist:
            return {'scene': _clean(raw.get('scene'), 1, 300), 'role': _clean(raw.get('role') or '', 0, 60), 'reply': _clean(raw.get('reply'), 1, 400)}
        if end:
            return {'summary': _clean(raw.get('summary'), 1, 500), 'good': [_clean(g, 1, 300) for g in (raw.get('good') or [])[:3] if isinstance(g, str) and g],
                    'fixes': _fixes(raw.get('fixes'), valid),
                    'expressions': [{'text': _clean(e.get('text'), 1, 120), 'meaning': _clean(e.get('meaning') or '', 0, 120)}
                                    for e in (raw.get('expressions') or [])[:4] if isinstance(e, dict) and e.get('text')],
                    'score': max(0.0, min(1.0, float(raw.get('score') or 0)))}
        corr = raw.get('correction')
        corr = {'original': _clean(corr.get('original') or '', 0, 300), 'better': _clean(corr.get('better'), 1, 300), 'why': _clean(corr.get('why') or '', 0, 300)} \
            if isinstance(corr, dict) and corr.get('better') else None
        return {'heard': _clean(raw.get('heard') or '', 0, 500) if audio else text, 'reply': _clean(raw.get('reply'), 1, 400),
                'correction': corr, 'hint': _clean(raw.get('hint') or '', 0, 200)}

    spec = {'pack': p['id'], 'turns': len(hist), 'text': text, 'end': end, 'audio': bool(audio), 'last': hist[-1]['text'] if hist else ''}
    result, status = _ai(c, uid, data, 'next-dialog', p['id'], 'speaking', spec, system, user, convert, audio)
    if status == 200 and end and not result.get('replayed'):
        r = result['result']
        sk.log(c, uid, 'speaking', 'dialog', r['score'], nx.cefr(p), p['id'], commit=False)
        sk.mistakes_from_changes(c, uid, r['fixes'], '', 'speaking', p['id'])
    return result, status


# ---------- essay ----------

def essay(c, uid, data):
    p, level = _material(c, uid, data)
    if not p:
        return {'error': '材料不存在'}, 404
    text = data.get('text')
    if not isinstance(text, str) or not 40 <= len(nx.WORD.findall(text)) <= 450:
        return {'error': '短文需要 40–450 个英文词'}, 400
    text = text.strip()
    valid = set(nx.nodes_meta(c))
    goal = (nx.profile(c, uid) or {}).get('goal')
    task = p.get('writing') or f"围绕「{p['title']}」写一段你自己的看法或经历"
    system = ('你是英语写作老师，按 CEFR 能力描述批改一篇短文。' + LEVEL_NOTE.get(level, '') +
              ('学习者在备考，评语可以联系考试写作的评分要求，但不要给出任何官方分数。' if goal == 'exam' else '') +
              '四个维度各打 1–5 分：内容切题（content）、结构衔接（organization）、语言准确（accuracy）、词汇句式丰富（range）。'
              '指出最重要的修改（最多 6 条），把两句改得更好，再写一段同主题的示范段落（不超过 120 词）。不要编造学习者没写的内容。只输出 JSON。')
    user = ('写作任务：' + task + '\n可用语法节点：' + nx._node_list(c) + '\n\n学习者的短文：\n' + text +
            '\n\n输出 JSON：{"scores":{"content":1-5,"organization":1-5,"accuracy":1-5,"range":1-5},"level":"A2|B1|B2|C1（这篇体现的水平）",'
            '"comment":"两三句中文总评，先说优点","paragraphs":[{"para":1,"note":"这一段的中文点评"}],"fixes":[' + FIX + '],'
            '"better":[{"from":"原句","to":"更好的写法","why":"中文"}],"model":"示范段落（英文）"}')

    def convert(raw):
        s = raw.get('scores') if isinstance(raw, dict) else None
        if not isinstance(s, dict):
            raise ValueError('bad')
        scores = {k: max(1, min(5, int(s.get(k) or 1))) for k in ('content', 'organization', 'accuracy', 'range')}
        return {'scores': scores, 'level': raw.get('level') if raw.get('level') in sk.LEVELS else None, 'comment': _clean(raw.get('comment'), 1, 500),
                'paragraphs': [{'para': int(x.get('para') or i + 1), 'note': _clean(x.get('note'), 1, 300)} for i, x in enumerate((raw.get('paragraphs') or [])[:6])
                               if isinstance(x, dict) and x.get('note')],
                'fixes': _fixes(raw.get('fixes'), valid), 'better': _fixes(raw.get('better'), valid)[:2], 'model': _clean(raw.get('model') or '', 0, 1200)}

    result, status = _ai(c, uid, data, 'next-essay', p['id'], 'writing', {'pack': p['id'], 'text': text}, system, user, convert)
    if status == 200:
        r = result['result']
        r['score'] = round(sum(r['scores'].values()) / 20, 2)
    if status == 200 and not result.get('replayed'):
        r = result['result']
        sk.log(c, uid, 'writing', 'essay', r['score'], r['level'] or nx.cefr(p), p['id'], commit=False)
        sk.mistakes_from_changes(c, uid, r['fixes'], text[:600], 'writing', p['id'], limit=4)
    return result, status


# ---------- translation ----------

def _sentence(p, i):
    sents = nx.sentences(p['body'])
    if not isinstance(i, int) or not 0 <= i < len(sents):
        return None
    return re.sub(r'^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+', '', sents[i])


def translate_source(c, uid, data):
    """The Chinese of one sentence, for Chinese → English practice. One AI call per sentence, cached for everyone."""
    p, level = _material(c, uid, data)
    if not p:
        return {'error': '材料不存在'}, 404
    en = _sentence(p, data.get('i'))
    if not en or len(nx.WORD.findall(en)) < 5:
        return {'error': '这一句太短，换一句吧'}, 400
    row = c.execute('SELECT zh FROM next_translations WHERE pack=? AND sentence=?', (p['id'], en)).fetchone()
    if row:
        return {'zh': row['zh'], 'cached': True}, 200
    system = '你是专业翻译。把英文句子译成自然、地道、忠实的中文，不加解释。只输出 JSON。'
    user = '英文：' + en + '\n\n输出 JSON：{"zh":"中文译文"}'
    result, status = _ai(c, uid, data, 'next-transsrc', p['id'], 'translation', {'pack': p['id'], 'sentence': en}, system, user,
                         lambda raw: {'zh': _clean((raw or {}).get('zh'), 1, 600)})
    if status == 200:
        c.execute('INSERT OR IGNORE INTO next_translations VALUES(?,?,?,?)', (p['id'], en, result['result']['zh'], time.time()))
        c.commit()
        return {'zh': result['result']['zh'], 'cached': False, 'remaining': result.get('remaining')}, 200
    return result, status


def translate(c, uid, data):
    p, level = _material(c, uid, data)
    if not p:
        return {'error': '材料不存在'}, 404
    en = _sentence(p, data.get('i'))
    direction = data.get('direction')
    text = data.get('text')
    if not en or direction not in ('zh2en', 'en2zh') or not isinstance(text, str) or not 2 <= len(text.strip()) <= 800:
        return {'error': '翻译内容不完整'}, 400
    text = text.strip()
    valid = set(nx.nodes_meta(c))
    if direction == 'zh2en':
        zh = (c.execute('SELECT zh FROM next_translations WHERE pack=? AND sentence=?', (p['id'], en)).fetchone() or {'zh': ''})['zh']
        if not zh:
            return {'error': '先取中文原句'}, 400
        task = f'中文原句：{zh}\n参考英文（原文）：{en}\n学习者的英文译文：{text}'
    else:
        task = f'英文原句：{en}\n学习者的中文译文：{text}'
    system = ('你是翻译老师。' + LEVEL_NOTE.get(level, '') + '评价学习者的译文：意思是否准确完整、表达是否自然。参考译文只是一种说法，'
              '意思对、表达自然的不同译法也算对。只输出 JSON。')
    user = (task + '\n可用语法节点：' + nx._node_list(c) + '\n\n输出 JSON：{"score":0.0到1.0,"accuracy":"中文：意思准确吗，漏译或误译了什么",'
            '"fluency":"中文：表达是否自然","fixes":[' + FIX + '],"reference":"' + ('一个自然的英文译法' if direction == 'zh2en' else '一个自然的中文译法') + '"}')

    def convert(raw):
        if not isinstance(raw, dict) or raw.get('score') is None:
            raise ValueError('bad')
        return {'score': max(0.0, min(1.0, float(raw['score']))), 'accuracy': _clean(raw.get('accuracy') or '', 0, 400),
                'fluency': _clean(raw.get('fluency') or '', 0, 400), 'fixes': _fixes(raw.get('fixes'), valid) if direction == 'zh2en' else [],
                'reference': _clean(raw.get('reference') or '', 0, 800), 'original': en}

    result, status = _ai(c, uid, data, 'next-translate', p['id'], 'translation', {'pack': p['id'], 'sentence': en, 'direction': direction, 'text': text},
                         system, user, convert)
    if status == 200 and not result.get('replayed'):
        r = result['result']
        sk.log(c, uid, 'translation', 'translate', r['score'], nx.cefr(p), p['id'], commit=False)
        sk.mistakes_from_changes(c, uid, r['fixes'], text, 'translation', p['id'], limit=2)
    return result, status


# ---------- pronunciation ----------

def say(c, uid, data):
    """One word or short phrase read aloud: did the target sound come through?"""
    import sounds
    from lab_service import audio_enabled
    from audio_validation import validate_audio
    if not audio_enabled():
        return {'error': 'AI 听录音暂未开启，可以先用「对比回放」自己听'}, 503
    target = data.get('text') if isinstance(data.get('text'), str) else ''
    focus, partner = sounds.focus_of(target), sounds.partner_of(target)
    if not focus and not (nx.WORD.fullmatch(target) and nx.lookup(target)):
        return {'error': '只能练发音入门里的词，或词典里的单词'}, 400
    raw_audio = validate_audio(data.get('audio'))
    system = ('你是英语语音老师，正在听中国学习者读一个英文词。先写出你实际听到的发音像哪个词；再判断目标音发得对不对。'
              '标准是"母语者能不能听成目标词"，不是完美口音：口音、音色、录音质量都不算错；'
              '只有目标音明显读成了别的音（比如读成了对比词）才判为 false，拿不准时判 true。不要打分。只输出 JSON。')
    user = (f'目标词：{target}' + (f'\n要练的音：{focus}' if focus else '') + (f'\n最容易读成：{partner}（要分清的对比词）' if partner else '') +
            '\n\n输出 JSON：{"heard":"听起来像哪个英文词","ok":true或false,"note":"中文：哪里对、哪里不对","tip":"中文：舌位、口型或气流怎么调整"}')

    def convert(raw):
        if not isinstance(raw, dict) or not isinstance(raw.get('ok'), bool):
            raise ValueError('bad')
        return {'heard': _clean(raw.get('heard') or '', 0, 80), 'ok': raw['ok'], 'note': _clean(raw.get('note') or '', 0, 300), 'tip': _clean(raw.get('tip') or '', 0, 300)}

    import hashlib
    result, status = _ai(c, uid, data, 'next-say', 'sounds', 'speaking', {'text': target, 'audio_sha256': hashlib.sha256(raw_audio).hexdigest()},
                         system, user, convert, data.get('audio'))
    if status == 200 and not result.get('replayed'):
        r = result['result']
        key = 'say:' + target.lower()[:60]
        # Judging one short word from a phone recording is not reliable enough to file a mistake on one verdict:
        # a miss asks for another try; a second miss in a row on the same word (within a week) makes the card.
        last = c.execute("SELECT score FROM next_skill_events WHERE user_id=? AND kind='say' AND pack=? AND created>? ORDER BY id DESC LIMIT 1",
                         (uid, key, time.time() - 7 * 86400)).fetchone()
        sk.log(c, uid, 'pronunciation', 'say', 1.0 if r['ok'] else 0.0, pack=key, commit=False)
        r['confirmed'] = not r['ok'] and last is not None and last['score'] == 0
        if r['confirmed']:
            sk.add_mistake(c, uid, 'sound', target, 'sound:' + target.lower(), r['tip'] or r['note'], '', 'pronunciation', extra={'focus': focus}, commit=False)
        c.commit()
    return result, status


# ---------- routing ----------

AI_PATHS = ('/api/next/retell', '/api/next/dialog', '/api/next/essay', '/api/next/translate/source', '/api/next/translate', '/api/next/say')


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS next_translations(pack TEXT NOT NULL, sentence TEXT NOT NULL, zh TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(pack, sentence))')
    c.commit()


def post(c, uid, path, data):
    routes = {'/api/next/retell': retell, '/api/next/dialog': dialog, '/api/next/essay': essay,
              '/api/next/translate/source': translate_source, '/api/next/translate': translate, '/api/next/say': say}
    fn = routes.get(path)
    return fn(c, uid, data) if fn else None
