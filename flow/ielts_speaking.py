"""雅思口语练习 in the speaking route: Part 1 (the examiner's everyday questions) and Part 2 (a cue card: one minute to
prepare, up to two minutes to speak), with feedback on the four IELTS speaking criteria.

All questions and cue cards are Flow's own, written in the style of the test; none is a real exam question. The bands
are the AI's estimate for practice, never an official score, and the page says so wherever a band is shown.

Part 1: the examiner asks a topic's questions in order and does not correct (as in the test). Each answer is one AI
call: what it heard (when spoken), a quiet 「这句可以更好」 the learner may open, and a short note on fluency and
pronunciation for the final feedback (the AI hears one answer at a time, so the notes carry what it heard).
Part 2: one recording of up to two minutes (or typed, then pronunciation is not judged) gets the feedback directly.
"""
import math

import next_service as nx
import skills_service as sk

CRITERIA = (('fc', '流利与连贯', 'Fluency and Coherence'), ('lr', '词汇', 'Lexical Resource'),
            ('gra', '语法', 'Grammatical Range and Accuracy'), ('p', '发音', 'Pronunciation'))
NOTICE = 'AI 估计，练习用，不是官方成绩。题目是语流原创的练习题，不是真题。'

# topic id -> (Chinese title, English title, the examiner's questions in order)
PART1 = {
    'study-work': ('学习还是工作', 'Work or studies', (
        'Let\'s talk about what you do. Do you work, or are you a student at the moment?',
        'What do you enjoy most about it?',
        'Is there anything about it you find difficult?',
        'What would you like to be doing in five years\' time?')),
    'hometown': ('家乡', 'Your hometown', (
        'Let\'s talk about your hometown. Where is it, and what is it like?',
        'How has it changed since you were a child?',
        'Is it a good place for young people to live? Why or why not?',
        'Would you like to live there in the future?')),
    'mornings': ('早晨', 'Mornings', (
        'Are you more of a morning person or an evening person?',
        'What is the first thing you usually do after you wake up?',
        'Did you get up earlier when you were at school?',
        'What would a perfect morning look like for you?')),
    'phones': ('手机和应用', 'Phones and apps', (
        'Roughly how much time do you spend on your phone each day?',
        'Which app do you use most, and what do you use it for?',
        'Have you deleted an app recently? Why?',
        'At what age do you think children should have their own phone?')),
    'food': ('吃饭和做饭', 'Food and cooking', (
        'Do you often cook for yourself?',
        'Which dish from your hometown would you recommend to a visitor?',
        'Do you prefer eating at home or eating out? Why?',
        'Has the way you eat changed in the last few years?')),
    'weather': ('天气', 'The weather', (
        'What is the weather usually like where you live?',
        'Which season do you like best, and why?',
        'Has the weather ever changed your plans?',
        'Do you check the weather forecast every day?')),
    'music': ('音乐', 'Music', (
        'What kind of music do you usually listen to?',
        'When do you listen to music most?',
        'Did you learn to play an instrument when you were a child?',
        'Is there a song that brings back a special memory for you?')),
    'getting-around': ('出行', 'Getting around', (
        'How do you usually get around your city?',
        'Do you enjoy walking? Where do you like to walk?',
        'What do you think of the public transport where you live?',
        'Would you like to own a car one day? Why or why not?')),
}

# card id -> (Chinese title, the task, the points to cover, the final point)
PART2 = {
    'skill': ('课外学会的一项技能', 'Describe a skill you learned outside school or work.',
              ('what the skill is', 'how and where you learned it', 'how long it took you to learn it'), 'and explain how this skill helps you in your life now.'),
    'place': ('喜欢待的一个地方', 'Describe a place in your town or city where you like to spend time.',
              ('where it is', 'how often you go there', 'what you usually do there'), 'and explain why you enjoy spending time there.'),
    'helped': ('帮助陌生人的一次经历', 'Describe a time when you helped someone you did not know.',
               ('when and where it happened', 'who the person was', 'what you did to help'), 'and explain how you felt afterwards.'),
    'object': ('一件舍不得放弃的东西', 'Describe something you own that you would find hard to give up.',
               ('what it is', 'how you got it', 'how often you use it'), 'and explain why it matters so much to you.'),
    'teacher': ('教会你重要一课的人', 'Describe a person who taught you something important.',
                ('who the person is', 'how you know them', 'what they taught you'), 'and explain why it was important to you.'),
    'journey': ('一次难忘的短途出行', 'Describe a short journey you remember well.',
                ('where you went', 'who you went with', 'what happened on the way'), 'and explain why you still remember it.'),
    'advice': ('一条后来很有用的建议', 'Describe a piece of advice you were given that turned out to be useful.',
               ('who gave it to you', 'when you were given it', 'what the advice was'), 'and explain how it helped you.'),
    'routine': ('想在日常作息里做的改变', 'Describe a change you would like to make to your daily routine.',
                ('what the change is', 'why you want to make it', 'how you would go about it'), 'and explain how your life might be different afterwards.'),
}
PREP_SECONDS, TALK_SECONDS = 60, 120


def pack_id(part, key):
    return f'ielts-p{part}-{key}'


def card_text(key):
    _, task, points, last = PART2[key]
    return task + '\nYou should say:\n' + '\n'.join('- ' + x for x in points) + '\n' + last


def band(v):
    """An estimate on the IELTS scale: 1–9 in half bands; None when missing. Read as a model writes it: 6.5, "6.5",
    "6.5分", "Band 6.5", "6.5/9"."""
    from lab_service import Shape, mnum
    try:
        f = mnum(v, 1.0, 9.0)
    except Shape:
        return None
    return max(1.0, min(9.0, round(f * 2) / 2))


def overall(bands):
    """The mean of the criteria given, rounded the way IELTS rounds the overall speaking band (.25 and .75 go up)."""
    xs = [b for b in bands.values() if b is not None]
    return math.floor(sum(xs) / len(xs) * 2 + 0.5) / 2 if xs else None


def cefr(b):
    """The CEFR level a band corresponds to, by the published IELTS–CEFR alignment (B1 4–5, B2 5.5–6.5, C1 7–8)."""
    return None if b is None else 'A2' if b < 4 else 'B1' if b < 5.5 else 'B2' if b < 7 else 'C1'


def listing(c, uid):
    last = {}
    if uid:
        for r in c.execute("SELECT pack, score, created FROM next_skill_events WHERE user_id=? AND kind='ielts' ORDER BY created", (uid,)):
            last[r['pack']] = round(r['score'] * 18) / 2  # the overall band was logged as band / 9
    p1 = [{'id': k, 'title': v[0], 'title_en': v[1], 'questions': list(v[2]), 'last': last.get(pack_id(1, k))} for k, v in PART1.items()]
    p2 = [{'id': k, 'title': v[0], 'task': v[1], 'points': list(v[2]), 'last_point': v[3], 'last': last.get(pack_id(2, k))} for k, v in PART2.items()]
    return {'part1': p1, 'part2': p2, 'criteria': [{'id': k, 'title': zh, 'en': en} for k, zh, en in CRITERIA],
            'notice': NOTICE, 'prep': PREP_SECONDS, 'talk': TALK_SECONDS, 'done': len(last)}


def for_ielts(c, uid, prof):
    """Is this learner heading for IELTS: studying abroad, or preparing for IELTS (the exam they set, or the IELTS
    word book)? Then the plan's speaking step is the next Part 1 topic instead of a role-play scene."""
    if prof.get('goal') == 'abroad' or prof.get('exam') == 'ielts':
        return True
    return prof.get('goal') == 'exam' and (__import__('vocab_service').plan(c, uid) or {}).get('book') == 'ielts'


def next_part1(c, uid):
    """The Part 1 topic to practise next: the first one not done yet; once all are done, the one done longest ago."""
    last = {r['pack']: r['t'] for r in c.execute("SELECT pack, MAX(created) t FROM next_skill_events WHERE user_id=? AND kind='ielts' "
                                                 "AND pack LIKE 'ielts-p1-%' GROUP BY pack", (uid,))}
    key = min(PART1, key=lambda k: (pack_id(1, k) in last, last.get(pack_id(1, k), 0)))
    return {'id': key, 'title': PART1[key][0], 'title_en': PART1[key][1], 'round': len(last) >= len(PART1)}


def _clean(v, lo=0, hi=600, code='text_empty', default=None):
    """A field a model wrote: cut when long, Shape(code) when missing (output_service._clean)."""
    from lab_service import mtext
    return mtext(v, lo, hi, code, default)


def _feedback(raw, spoken, valid):
    """The four criteria as given by the AI, checked; pronunciation only when something was heard."""
    from output_service import _fixes
    if not isinstance(raw, dict) or not isinstance(raw.get('bands'), dict):
        raise __import__('lab_service').Shape('bands_missing')
    bands = {k: band(raw['bands'].get(k)) for k, _, _ in CRITERIA}
    if not spoken:
        bands['p'] = None
    if sum(b is not None for k, b in bands.items() if k != 'p') < 3:
        raise __import__('lab_service').Shape('bands_missing')
    notes = raw.get('notes') if isinstance(raw.get('notes'), dict) else {}
    crit = []
    for k, zh, en in CRITERIA:
        n = notes.get(k) if isinstance(notes.get(k), dict) and bands[k] is not None else {}  # nothing heard: no notes on sounds
        crit.append({'id': k, 'title': zh, 'en': en, 'band': bands[k], 'good': _clean(n.get('good') or '', 0, 200), 'next': _clean(n.get('next') or '', 0, 200)})
    return {'overall': overall(bands), 'criteria': crit, 'summary': _clean(raw.get('summary') or '', 0, 400),
            'fixes': _fixes(raw.get('fixes'), valid)[:4], 'model': _clean(raw.get('model') or '', 0, 1600),
            'spoken': bool(spoken), 'notice': NOTICE}


SYSTEM_FEEDBACK = ('你是有经验的雅思口语考官，按雅思口语公开的四项评分标准估计一位中国学习者这次练习的表现：流利与连贯（fc，'
                   'Fluency and Coherence）、词汇（lr，Lexical Resource）、语法（gra，Grammatical Range and Accuracy）、发音（p，'
                   'Pronunciation）。这是练习，不是正式考试：每项给你估计的分数（1–9，可以用 .5），不要说这是官方成绩，也不要因为话题难易加减分。'
                   '口音本身不扣分，只看是否清楚、能否让人轻松听懂。每项写一句做得好的（good）和一句最该提高、具体能做的（next），都用中文。'
                   '改出最影响分数的语言错误（最多 4 条）。只评学习者实际说的内容，不要编造。只输出 JSON。')
FEEDBACK_JSON = ('"bands":{"fc":分数,"lr":分数,"gra":分数,"p":分数或 null},"notes":{"fc":{"good":"中文","next":"中文"},"lr":{…},"gra":{…},"p":{…}},'
                 '"summary":"两三句中文总评，先说优点","fixes":[' + '{"from":"学习者原话片段","to":"改后片段","why":"简短中文原因","node":null}' + ']')


def answer(c, uid, data):
    """Part 1, one answer: what was heard, a better way to say it (or null), and a note for the final feedback."""
    from output_service import _audio_or_text, _ai
    topic = data.get('topic')
    q = data.get('q')
    if topic not in PART1 or not isinstance(q, int) or not 0 <= q < len(PART1[topic][2]):
        return {'error': '没有这个问题'}, 404
    text, audio, err = _audio_or_text(data, 1, 600)
    if err:
        return err
    question = PART1[topic][2][q]
    system = ('你在陪一位中国学习者练雅思口语 Part 1。考官问了一个问题，学习者刚回答。' +
              ('先忠实转写录音里学习者说的英文，听不清的部分写 [听不清]，不要补全。' if audio else '') +
              '然后：better 是在学习者原意上更自然、更像 7 分的回答（英文，1–3 句，保留原意和内容，不要另编经历），why 用一句中文说明主要改了什么；'
              '回答已经很好就给 null。note 是留给最后评分用的简短中文记录：流利度、语法、用词' + ('、发音（只写有把握的）' if audio else '') +
              '各一两个具体观察。只输出 JSON。')
    user = ('考官的问题：' + question + ('\n\n学习者的回答是一段录音。' if audio else '\n\n学习者的回答：' + text) +
            '\n\n输出 JSON：{' + ('"heard":"转写",' if audio else '') + '"better":{"text":"更好的回答","why":"中文说明"} 或 null,"note":"不超过 100 字的中文记录"}')

    def convert(raw):
        if not isinstance(raw, dict):
            raise ValueError('bad')
        b = raw.get('better')
        better = {'text': _clean(b.get('text'), 1, 500), 'why': _clean(b.get('why') or '', 0, 200)} if isinstance(b, dict) and isinstance(b.get('text'), str) and nx.WORD.search(b['text']) else None
        return {'heard': _clean(raw.get('heard') or '', 0, 1200) if audio else text, 'better': better, 'note': _clean(raw.get('note') or '', 0, 240)}

    spec = {'part': 1, 'topic': topic, 'q': q, 'text': text, 'audio': bool(audio)}
    return _ai(c, uid, data, 'next-ielts', pack_id(1, topic), 'speaking', spec, system, user, convert, audio)


def part1_feedback(c, uid, data):
    from output_service import _ai
    topic = data.get('topic')
    if topic not in PART1:
        return {'error': '没有这个话题'}, 404
    qs = PART1[topic][2]
    ans = data.get('answers')
    if not isinstance(ans, list) or not 1 <= len(ans) <= len(qs):
        return {'error': '先回答至少一个问题'}, 400
    rows, spoken = [], False
    for a in ans:
        if not isinstance(a, dict) or not isinstance(a.get('q'), int) or not 0 <= a['q'] < len(qs) or not isinstance(a.get('text'), str) or not 1 <= len(a['text']) <= 1200:
            return {'error': '回答记录格式不正确'}, 400
        note = a.get('note') if isinstance(a.get('note'), str) else ''
        said = bool(a.get('spoken'))
        spoken = spoken or said
        rows.append(f"问题 {a['q'] + 1}：{qs[a['q']]}\n回答（{'录音的转写' if said else '打字'}）：{a['text']}\n听回答时的记录：{note[:240] or '无'}")
    valid = set(nx.nodes_meta(c))
    system = SYSTEM_FEEDBACK + ('发音只能根据录音判断：根据「听回答时的记录」里关于发音的观察给 p；' if spoken else '这次全部是打字作答，没有录音，p 填 null。') + \
        'Part 1 的回答不需要很长，但要直接回答并给出理由或例子。最后给一段示范回答（model，英文，针对其中最值得改进的一个问题，2–4 句）。'
    user = ('雅思口语 Part 1 · 话题：' + PART1[topic][1] + '\n\n' + '\n\n'.join(rows) +
            '\n\n输出 JSON：{' + FEEDBACK_JSON + ',"model":"示范回答（英文）","model_q":示范回答针对的问题序号（从 1 开始）}')

    def convert(raw):
        out = _feedback(raw, spoken, valid)
        mq = raw.get('model_q')
        out['model_q'] = qs[mq - 1] if isinstance(mq, int) and 1 <= mq <= len(qs) else ''
        out['answered'] = len(rows)
        return out

    spec = {'part': 1, 'topic': topic, 'answers': [[a['q'], a['text'], bool(a.get('spoken'))] for a in ans]}
    result, status = _ai(c, uid, data, 'next-ielts', pack_id(1, topic), 'speaking', spec, system, user, convert)
    return _record(c, uid, result, status, pack_id(1, topic))


def part2_talk(c, uid, data):
    from output_service import _audio_or_text, _ai
    card = data.get('card')
    if card not in PART2:
        return {'error': '没有这张话题卡'}, 404
    text, audio, err = _audio_or_text(data, 20, 3000)
    if err:
        if not data.get('audio') and isinstance(data.get('text'), str):
            return {'error': 'Part 2 要说一段话：打字的话至少写 20 个英文词'}, 400
        return err
    try:
        secs = max(0, min(TALK_SECONDS + 10, int(data.get('seconds') or 0)))
    except (TypeError, ValueError):
        secs = 0
    valid = set(nx.nodes_meta(c))
    spoken = bool(audio)
    long_turn = (f'学习者准备了 1 分钟，然后说了 {secs} 秒（要求 1–2 分钟，考官 2 分钟时会打断；明显不到 1 分钟、说不下去会影响流利与连贯）。'
                 if spoken else '学习者没有录音，是打字作答的（这时不评发音、不看时长）。')
    system = SYSTEM_FEEDBACK + ('先忠实转写录音（transcript），听不清的部分写 [听不清]，不要补全。' if spoken else '这次是打字作答，p 填 null。') + \
        '看学习者有没有覆盖话题卡上的要点、能不能连贯地展开。最后给一段同一张话题卡的示范回答（model，英文，约 180–220 词，7 分左右，用学习者学得会的说法）。'
    user = ('雅思口语 Part 2 · 话题卡：\n' + card_text(card) + '\n\n' + long_turn +
            ('' if spoken else '\n\n学习者的回答：\n' + text) +
            '\n\n输出 JSON：{' + ('"transcript":"转写",' if spoken else '') + FEEDBACK_JSON + ',"covered":[话题卡 4 个要点各有没有讲到，true/false],"model":"示范回答（英文）"}')

    def convert(raw):
        out = _feedback(raw, spoken, valid)
        out['transcript'] = _clean(raw.get('transcript') or '', 0, 3000) if spoken else text
        cov = raw.get('covered') if isinstance(raw.get('covered'), list) else []
        out['covered'] = [bool(x) for x in cov[:4]] if len(cov) >= 4 else None
        out['seconds'] = secs if spoken else None
        return out

    spec = {'part': 2, 'card': card, 'text': text, 'audio': spoken, 'seconds': secs}
    result, status = _ai(c, uid, data, 'next-ielts', pack_id(2, card), 'speaking', spec, system, user, convert, audio)
    return _record(c, uid, result, status, pack_id(2, card))


def _record(c, uid, result, status, pack):
    """A finished practice: one speaking event (the overall band / 9, at the CEFR level it corresponds to) and the
    corrections into the mistake book. Replays record nothing again."""
    if status != 200 or result.get('replayed'):
        return result, status
    r = result['result']
    if r.get('overall') is not None:
        sk.log(c, uid, 'speaking', 'ielts', r['overall'] / 9, cefr(r['overall']), pack, commit=False)
    sk.mistakes_from_changes(c, uid, r['fixes'], r.get('transcript') or '', 'speaking', pack)
    c.commit()
    return result, status


def post(c, uid, data):
    step = data.get('step')
    if step == 'answer':
        return answer(c, uid, data)
    if step == 'part1':
        return part1_feedback(c, uid, data)
    if step == 'part2':
        return part2_talk(c, uid, data)
    return {'error': '不认识的步骤'}, 400

