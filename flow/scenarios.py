"""The speaking route: twelve role-play scenes from A2 to C1, the situations Chinese learners most need to handle.

Each scene is played with the AI through the existing dialogue endpoint (output_service.dialog with a scenario id):
the AI takes the other part, corrects one thing at a time, and sums up at the end. A scene counts as done once a
dialogue on it has been finished and summed up. All content is original.

Rounds (r28): a scene practised before comes back. Round 2 adds one harder requirement (CHALLENGE); from round 3 the
roles alternate: odd rounds swap them (the learner plays the shop assistant, the landlord…, with SWAP's goals), even
rounds bring back the challenge. Once every scene has been done, 「下一个」 (and the plan's speaking step) is a scene
practised at least REPEAT_DAYS ago, the one that went least well first, so speaking never drops out of the plan.
A round is a day on which the scene was finished.
"""

# id -> level, title, English title, AI's part, learner's part, brief (Chinese), scene for the AI (English), goals, useful expressions
SCENES = {
    'cafe-order': ('A2', '在咖啡店点单', 'Ordering at a café', '咖啡店店员', '顾客',
                   '你走进一家咖啡店，想点一杯热饮和一份吃的。店员会问你要什么尺寸、在这儿喝还是带走。',
                   'A small café. The barista greets the customer, takes the order, asks about size, milk and whether it is for here or to go, and tells the price.',
                   ['点一杯饮料，说清大小和要不要加奶', '加点一样吃的', '说清在店里吃还是带走，并付款'],
                   [('Could I have a …, please?', '我能要一杯……吗？'), ('For here, please. / To go, please.', '在这儿吃 / 带走'),
                    ('Can I pay by card?', '可以刷卡吗？'), ('That\'s all, thanks.', '就这些，谢谢')]),
    'ask-way': ('A2', '问路', 'Asking the way', '路人', '问路的游客',
                '你在一座陌生的城市，想去火车站。拦住一位路人问路，确认怎么走、要多久。',
                'A busy street in a city centre. A friendly local is asked the way to the railway station: about ten minutes on foot, straight on, left at the bank, past a park.',
                ['礼貌地打招呼并说明要去哪', '听懂路线，并复述确认', '问要走多久，最后道谢'],
                [('Excuse me, could you tell me how to get to …?', '打扰一下，请问……怎么走？'), ('Is it far from here?', '离这儿远吗？'),
                 ('So I go straight on and turn left at …?', '所以我直走，在……左转？'), ('Thanks for your help.', '谢谢你的帮助')]),
    'hotel-check-in': ('A2', '酒店入住', 'Checking in at a hotel', '前台接待', '住客',
                       '你预订了两晚的酒店，现在去前台办理入住。顺便问问早餐时间和 Wi-Fi。',
                       'A hotel reception desk in the evening. The receptionist checks the booking (two nights), asks for a passport, explains breakfast times and the Wi-Fi password, and gives the room key.',
                       ['说明你有预订、报上名字', '问早餐时间和 Wi-Fi', '确认退房时间'],
                       [('I have a reservation under the name …', '我用……的名字预订了'), ('What time is breakfast?', '早餐几点？'),
                        ('What\'s the Wi-Fi password?', 'Wi-Fi 密码是多少？'), ('What time do I need to check out?', '几点退房？')]),
    'see-doctor': ('A2', '看医生', 'At the doctor\'s', '医生', '病人',
                   '你感冒三天了，嗓子疼、有点发烧，去社区诊所看医生。说清症状和持续多久。',
                   'A general practitioner\'s room. The doctor asks about symptoms, how long they have lasted, allergies, and gives simple advice and a prescription.',
                   ['说清哪里不舒服、持续多久', '回答过敏和用药的问题', '问清药怎么吃、多久能好'],
                   [('I\'ve had a sore throat for three days.', '我嗓子疼了三天了'), ('I\'ve got a slight fever.', '我有点发烧'),
                    ('I\'m not allergic to anything.', '我没有什么过敏'), ('How often should I take it?', '这个药多久吃一次？')]),
    'flat-viewing': ('B1', '看房租房', 'Viewing a flat', '房东', '想租房的人',
                     '你在看一套出租公寓。问清房租包含什么、押金多少、能住多久，再决定要不要租。',
                     'A small furnished flat near a university. The landlord shows it, answers questions about rent, bills, deposit, contract length and neighbours, and asks a few questions about the tenant.',
                     ['问房租包不包括水电网', '问押金和合同期限', '提出一个顾虑并商量'],
                     [('Does the rent include bills?', '房租包括水电费吗？'), ('How much is the deposit?', '押金多少？'),
                      ('Would it be possible to …?', '有没有可能……？'), ('I\'d like to think about it.', '我想考虑一下')]),
    'return-item': ('B1', '退换货', 'Returning a faulty item', '店员', '顾客',
                    '你上周买的耳机一只耳朵没声音。带着小票去店里，说明问题，要求换货或退款。',
                    'An electronics shop. The shop assistant listens to the complaint about headphones bought last week (one side has no sound), checks the receipt, and offers a repair, an exchange or a refund with some conditions.',
                    ['说清买了什么、什么时候买的、出了什么问题', '说明你想要换货还是退款', '对店员的方案礼貌地回应'],
                    [('I bought these last week, but …', '我上周买的，但是……'), ('One side doesn\'t work.', '有一边不响'),
                     ('I\'d prefer a refund, if possible.', '如果可以，我更想退款'), ('Here\'s the receipt.', '这是小票')]),
    'group-project': ('B1', '小组作业分工', 'Dividing up a group project', '组员', '组员',
                      '你和一位同学要合作完成一个课程报告。商量谁负责哪部分、什么时候碰头、截止日期前怎么检查。',
                      'Two university classmates plan a group presentation due in two weeks. The classmate has opinions about who does the research and the slides, and is busy on Wednesdays.',
                      ['提出分工建议', '协调见面时间', '约定检查进度的方式'],
                      [('How about I take care of …?', '要不……我来负责？'), ('Does Thursday work for you?', '周四你方便吗？'),
                       ('Let\'s check in on Friday.', '我们周五碰一下进度'), ('That sounds fair.', '这样挺公平的')]),
    'phone-booking': ('B1', '电话预约', 'Booking by phone', '餐厅接待', '订位的人',
                      '你打电话给一家餐厅，为周六晚上六个人订位。有人不吃辣，还想要安静一点的位置。',
                      'A restaurant phone line. The host takes a booking for six on Saturday evening, says 7 pm is full but 6:30 or 8 is free, notes dietary needs, and asks for a phone number.',
                      ['说清人数、日期和时间', '提出特殊要求', '确认预订信息'],
                      [('I\'d like to book a table for six.', '我想订六个人的位子'), ('Is 7 o\'clock available?', '七点有位吗？'),
                       ('One of us doesn\'t eat spicy food.', '我们有人不吃辣'), ('Could you confirm that for me?', '能帮我确认一下吗？')]),
    'job-interview': ('B2', '求职面试', 'A job interview', '面试官', '求职者',
                      '你在面试一个市场助理的职位。介绍自己的经历，回答“你最大的缺点是什么”，最后问面试官一个问题。',
                      'An interview for a marketing assistant role at a mid-sized company. The interviewer asks about experience, a difficult situation, a weakness, and invites the candidate\'s questions.',
                      ['用一个具体例子介绍经历', '回答缺点问题，并说怎么改进', '问一个有质量的问题'],
                      [('In my last internship, I was responsible for …', '在上一份实习里我负责……'), ('One thing I\'m working on is …', '我正在改进的一点是……'),
                       ('What does a typical day look like?', '这个岗位平常一天是什么样的？'), ('That\'s a good question.', '这是个好问题')]),
    'disagree-meeting': ('B2', '会上提出不同意见', 'Disagreeing in a meeting', '同事', '同事',
                         '开会时同事提议把产品发布提前两周。你认为测试时间不够，要礼貌地提出不同意见，并给出替代方案。',
                         'A team meeting. A colleague proposes launching a product two weeks early to beat a competitor. The learner thinks testing would be rushed. The colleague pushes back but is open to a compromise.',
                         ['先肯定对方的出发点', '说清你的顾虑和理由', '提出一个折中方案'],
                         [('I see where you\'re coming from, but …', '我理解你的出发点，但是……'), ('My concern is that …', '我担心的是……'),
                          ('What if we …?', '如果我们……怎么样？'), ('Could we meet halfway?', '我们能各让一步吗？')]),
    'landlord-repair': ('B2', '和房东协商修理', 'Getting a repair done', '房东', '租客',
                        '你的公寓暖气坏了一周，你已经发过两次消息。现在打电话给房东，要求尽快修好，并商量这几天的补偿。',
                        'A phone call. The tenant\'s heating has been broken for a week after two messages. The landlord is apologetic but says the engineer is busy; he can be persuaded to send someone sooner and offer something for the inconvenience.',
                        ['说清问题和已经等了多久', '坚定但礼貌地要求时间', '商量合理的补偿'],
                        [('I\'m afraid the heating still isn\'t working.', '恐怕暖气还是没修好'), ('It\'s been a week now.', '已经一周了'),
                         ('Would it be possible to send someone by …?', '能在……之前派人来吗？'), ('I think that\'s reasonable.', '我觉得这样合理')]),
    'presentation-qa': ('C1', '汇报后的答疑', 'Q&A after a presentation', '听众（部门主管）', '汇报人',
                        '你刚汇报完一个用户调研项目。主管提出尖锐的问题：样本够不够、结论是不是太乐观。你要有理有据地回应，承认局限。',
                        'After a presentation of user research (20 interviews, a survey of 300 people) recommending a redesign. A sceptical department head asks about sample size, bias and cost, and wants a clear next step.',
                        ['先复述并确认对方的问题', '用数据回应，同时承认局限', '给出明确的下一步建议'],
                        [('That\'s a fair point.', '这一点说得有道理'), ('To be clear, what we found was …', '准确地说，我们发现的是……'),
                         ('One limitation is …', '一个局限是……'), ('I\'d suggest we start with a small pilot.', '我建议先小范围试点')]),
}
ORDER = ('A2', 'B1', 'B2', 'C1')
REPEAT_DAYS = 14

# round 2 (and later even rounds): one more thing to do, in Chinese, as the learner sees it
CHALLENGE = {
    'cafe-order': '问店员一个关于菜单的问题，比如有没有不含奶的饮品',
    'ask-way': '路线听完以后，用自己的话完整复述一遍再确认',
    'hotel-check-in': '提一个额外的请求，比如换一间安静的房间或者寄存行李',
    'see-doctor': '说清症状是怎么开始的、哪个时候最难受',
    'flat-viewing': '主动问房东一个问题，并且说出你最在意的一点',
    'return-item': '店员先给的方案你不满意，礼貌地说明理由，再争取一次',
    'group-project': '用上 2 个连接词（because、so、but……）说清你为什么这样分工',
    'phone-booking': '最后用一句话把订位信息完整复述一遍',
    'job-interview': '每个回答都举一个具体的例子',
    'disagree-meeting': '先复述对方的提议，再说你的方案，并说出一个可以量化的理由',
    'landlord-repair': '把你的要求说成一个具体的期限，并提一个对方也能接受的折中',
    'presentation-qa': '每个回答都先用一句话直接回答，再补充数据或理由',
}
# odd rounds from 3: the learner takes the AI's part; these are the learner's goals then
SWAP = {
    'cafe-order': ['问顾客想喝什么、要多大杯', '推荐一样吃的', '问清在店里吃还是带走，说出价格'],
    'ask-way': ['听懂对方要去哪', '用 straight on、turn left 这样的说法指路', '说清大概要走多久'],
    'hotel-check-in': ['确认预订和入住几晚', '说明早餐时间和 Wi-Fi', '交代退房时间'],
    'see-doctor': ['问清哪里不舒服、多久了', '问有没有过敏', '给出简单的建议和吃药方法'],
    'flat-viewing': ['介绍房子的优点', '回答房租、押金和合同期限', '问对方一两个关于入住的问题'],
    'return-item': ['问清买了什么、什么问题', '查看小票', '给出维修、换货或退款的方案'],
    'group-project': ['提出你想负责的部分', '说出你哪天没空', '同意一个检查进度的时间'],
    'phone-booking': ['问清人数、日期和时间', '说明七点已满，提供别的时间', '记下特殊要求并要电话号码'],
    'job-interview': ['请对方介绍经历', '问一个难处理的情况', '邀请对方提问并回答'],
    'disagree-meeting': ['提议把发布提前两周', '说出提前的好处', '对方提出顾虑时，讨论一个折中'],
    'landlord-repair': ['先道歉并说明维修工很忙', '被说服后给出一个更早的时间', '提出一点补偿'],
    'presentation-qa': ['追问样本够不够、有没有偏差', '问成本', '要求一个明确的下一步'],
}


def mode_of(round_no):
    """'first' (round 1), 'challenge' (even rounds) or 'swap' (odd rounds from 3)."""
    return 'first' if round_no <= 1 else 'challenge' if round_no % 2 == 0 else 'swap'


def pack(sid, mode='first'):
    """A scene in the shape the dialogue code expects of a material; mode 'challenge' adds round 2's requirement,
    'swap' gives the learner the other part (and its goals)."""
    s = SCENES.get(sid or '')
    if not s:
        return None
    level, title, title_en, ai, me, brief, scene, goals, useful = s
    if mode == 'swap':
        ai, me, goals = me, ai, SWAP[sid]
    body = (f'Scene: {scene}\nThe AI plays: {ai}. The learner plays: {me}.\nThe learner\'s goals: ' + '；'.join(goals) +
            ('' if mode == 'swap' else '\nUseful expressions: ' + '; '.join(u[0] for u in useful)))
    task = f'情景对话：{title}。你扮演{me}，AI 扮演{ai}。目标：' + '；'.join(goals)
    if mode == 'swap':
        body += '\nThis round the roles are swapped: the learner plays the part the AI usually plays. Ask and answer as that character would.'
    if mode == 'challenge':
        body += '\nThis round the learner has one extra requirement (in Chinese): ' + CHALLENGE[sid]
        task += '。这一轮多一条要求：' + CHALLENGE[sid]
    return {'id': 'scene-' + sid, 'title': title, 'title_en': title_en, 'body': body, 'cefr': level, 'level': level,
            'speaking': task, 'mode': mode if mode in ('challenge', 'swap') else 'first', 'challenge': CHALLENGE[sid] if mode == 'challenge' else ''}


def _history(c, uid):
    """{scene id: {'rounds': days it was finished, 'last': when, 'score': the last round's score}}."""
    import datetime, next_service as nx
    out = {}
    if not uid:
        return out
    for pk, score, t in c.execute("SELECT pack, score, created FROM next_skill_events WHERE user_id=? AND kind='dialog' AND pack LIKE 'scene-%' "
                                  "ORDER BY created", (uid,)):
        h = out.setdefault(pk[6:], {'days': set(), 'last': 0, 'score': None})
        h['days'].add(datetime.datetime.fromtimestamp(t, nx.TZ).date()); h['last'] = t; h['score'] = score
    return {k: {'rounds': len(v['days']), 'last': v['last'], 'score': v['score']} for k, v in out.items()}


def mode_for(c, uid, sid):
    """The mode of this learner's next round of a scene (see mode_of)."""
    return mode_of(_history(c, uid).get(sid, {'rounds': 0})['rounds'] + 1)


def pace(heard, corrected):
    """How the AI should pitch its next line, from the learner's answer: 'easier' when it was very short or short with
    a mistake, 'harder' when it was long and needed no correction, else 'same'. The same rule is in the AI's prompt."""
    import next_service as nx
    n = len(nx.WORD.findall(heard or ''))
    return 'easier' if n < PACE_SHORT or (corrected and n < PACE_MID) else 'harder' if n >= PACE_LONG and not corrected else 'same'


PACE_SHORT, PACE_MID, PACE_LONG = 4, 8, 10  # words in the learner's answer


def listing(c, uid, level=None, now=None):
    import time
    now = now or time.time()
    hist = _history(c, uid)
    items = []
    for k, s in sorted(SCENES.items(), key=lambda kv: ORDER.index(kv[1][0])):
        h = hist.get(k, {'rounds': 0, 'last': 0, 'score': None})
        mode = mode_of(h['rounds'] + 1)
        items.append({'id': k, 'level': s[0], 'title': s[1], 'title_en': s[2], 'ai': s[3], 'me': s[4], 'brief': s[5], 'goals': s[7],
                      'useful': [{'text': u[0], 'meaning': u[1]} for u in s[8]], 'done': h['rounds'] > 0, 'rounds': h['rounds'],
                      'round': h['rounds'] + 1, 'mode': mode, 'challenge': CHALLENGE[k] if mode == 'challenge' else '',
                      'swap_goals': SWAP[k] if mode == 'swap' else []})
    lv = level if level in ORDER else 'B1'
    near = lambda x: (abs(ORDER.index(x['level']) - ORDER.index(lv)), ORDER.index(x['level']))
    # next: the first scene not done at the learner's level, then the levels around it; once all are done, a scene
    # practised REPEAT_DAYS or more ago (the one that went least well first), else the one practised longest ago
    fresh = sorted((x for x in items if not x['done']), key=near)
    if fresh:
        nxt = fresh[0]['id']
    else:
        rested = [x for x in items if hist[x['id']]['last'] <= now - REPEAT_DAYS * 86400]
        nxt = (min(rested, key=lambda x: (hist[x['id']]['score'] if hist[x['id']]['score'] is not None else 1, near(x)))['id'] if rested
               else min(items, key=lambda x: hist[x['id']]['last'])['id'])
    done = sum(1 for x in items if x['done'])
    return {'items': items, 'next': nxt, 'done': done, 'total': len(SCENES), 'round_two': done == len(SCENES)}
