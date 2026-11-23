"""The speaking route: twelve role-play scenes from A2 to C1, the situations Chinese learners most need to handle.

Each scene is played with the AI through the existing dialogue endpoint (output_service.dialog with a scenario id):
the AI takes the other part, corrects one thing at a time, and sums up at the end. A scene counts as done once a
dialogue on it has been finished and summed up. All content is original.
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


def pack(sid):
    """A scene in the shape the dialogue code expects of a material."""
    s = SCENES.get(sid or '')
    if not s:
        return None
    level, title, title_en, ai, me, brief, scene, goals, useful = s
    body = (f'Scene: {scene}\nThe AI plays: {ai}. The learner plays: {me}.\nThe learner\'s goals: ' + '；'.join(goals) +
            '\nUseful expressions: ' + '; '.join(u[0] for u in useful))
    return {'id': 'scene-' + sid, 'title': title, 'title_en': title_en, 'body': body, 'cefr': level, 'level': level,
            'speaking': f'情景对话：{title}。你扮演{me}，AI 扮演{ai}。目标：' + '；'.join(goals)}


def listing(c, uid, level=None):
    done = {r[0][6:] for r in c.execute("SELECT DISTINCT pack FROM next_skill_events WHERE user_id=? AND kind='dialog' AND pack LIKE 'scene-%'", (uid,))} if uid else set()
    items = [{'id': k, 'level': s[0], 'title': s[1], 'title_en': s[2], 'ai': s[3], 'me': s[4], 'brief': s[5], 'goals': s[7],
              'useful': [{'text': u[0], 'meaning': u[1]} for u in s[8]], 'done': k in done}
             for k, s in sorted(SCENES.items(), key=lambda kv: ORDER.index(kv[1][0]))]
    lv = level if level in ORDER else 'B1'
    # next: the first scene not done at the learner's level, then the levels around it
    ranked = sorted((x for x in items if not x['done']), key=lambda x: (abs(ORDER.index(x['level']) - ORDER.index(lv)), ORDER.index(x['level'])))
    return {'items': items, 'next': ranked[0]['id'] if ranked else None, 'done': len(done & set(SCENES)), 'total': len(SCENES)}
