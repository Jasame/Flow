"""题型专练 (考试冲刺, exam_sprint.py): practice on single question types of each exam, two types per exam, about
twenty items per type.

Every passage, question and option here was written for 语流. None is taken or adapted from a past paper, a test-prep
book or any other source: they follow each exam's question type and difficulty only, and the page says so. Every answer
rests on the text: matching and TRUE/FALSE items quote their sentence (evidence), gap-fill and choice items name the
clue in their explanation (why). tests/test_exam_sprint.py checks that every quoted sentence is in its text, that every
answer is one of its options, that bank answers are used once, and that each text has as many gaps as items.

Written form (turned into the served form by _build at import):
  cloze     text with {1}…{n}; items ('right|wrong|wrong|wrong', why)              (options shuffled per item, fixed seed)
  choice    items ('prompt with ____', 'right|wrong|wrong|wrong', why)
  bank      text with {1}…{n}; bank [options, more than the gaps]; items ('right option', why); sort=True keeps the bank
            in alphabetical order (选词填空), otherwise it is shuffled
  match     paras [A, B, …]; items ('statement', 'C', 'evidence in paragraph C')   (a paragraph can be the answer twice)
  headings  paras; bank [headings, more than the paragraphs]; items ('right heading', 'evidence'), one per paragraph
  tfng      text; items ('statement', 'T' | 'F' | 'NG', 'evidence' ('' for NG), note)
  proof     items ('line', 'wrong word', 'fix' ('' = delete it), why), one error per line
"""
import random

HOW = {
    'cloze': '先通读全文抓大意，再逐个空看前后搭配和上下文逻辑；选完把整段连起来再读一遍。',
    'dialog': '先看空后面那句话：对方怎么回答，往往就能反推出空里该说什么。选项比空多两个，用不上的是干扰项。',
    'seven': '先读空前空后的句子，找代词、连接词和重复出现的词；7 个选项只用 5 个，每个只用一次。',
    'banked': '先判断每个空要什么词性（名词、动词、形容词、副词）和形式，再按意思和搭配选；15 个词只用 10 个，每个只用一次。',
    'match': '先读题目划出关键词，再到段落里找意思相同、换了说法的句子；有的段落选两次，有的一次也不选。',
    'newtype': '先读全文把握结构，再看每个空和前后文的关系；7 个选项只用 5 个，每个只用一次。',
    'choice': '每题先看考的是语法结构还是词语搭配，再排除；做完看解析，弄清楚别的选项为什么不对。',
    'proof': '每行有一处错误：有的词用错了，有的词多余。点出错的那个词；正式考试还要写出改法，这里交卷后会给出改法。',
    'tfng': '和原文一致选 TRUE，和原文矛盾选 FALSE，原文没提到选 NOT GIVEN。不要用常识判断，只看原文。',
    'headings': '先读每段的第一两句抓主旨，再选最能概括全段的标题；标题比段落多，有几个用不上。',
}
TF = ('T', 'F', 'NG')


def _shuffled(xs, seed):
    out = list(xs)
    random.Random(seed).shuffle(out)
    return out


def _build(exam, tid, title, kind, how, sets):
    out = []
    for k, s in enumerate(sets):
        sid = f'{tid}-{k + 1}'
        seed = f'{exam}:{sid}'
        x = {'id': sid, 'title': s.get('title', '')}
        if kind in ('cloze', 'choice'):
            if kind == 'cloze':
                x['text'] = s['text']
            x['items'] = []
            for i, it in enumerate(s['items']):
                prompt, opts, why = (('',) + tuple(it)) if kind == 'cloze' else it
                o = opts.split('|')
                right = o[0]
                o = _shuffled(o, f'{seed}:{i}')
                x['items'].append({'prompt': prompt, 'options': o, 'answer': o.index(right), 'why': why})
        elif kind == 'bank':
            bank = sorted(s['bank'], key=str.lower) if s.get('sort') else _shuffled(s['bank'], seed)
            x.update(text=s['text'], bank=bank, items=[{'answer': bank.index(a), 'why': why} for a, why in s['items']])
        elif kind == 'match':
            x['paras'] = s['paras']
            x['items'] = [{'prompt': p, 'answer': 'ABCDEFGHIJ'.index(l), 'evidence': ev, 'why': f'见 {l} 段：“{ev}”'} for p, l, ev in s['items']]
        elif kind == 'headings':
            bank = _shuffled(s['bank'], seed)
            x.update(paras=s['paras'], bank=bank,
                     items=[{'answer': bank.index(h), 'evidence': ev, 'why': f'这一段讲的是：“{ev}”'} for h, ev in s['items']])
        elif kind == 'tfng':
            x['text'] = s['text']
            x['items'] = [{'prompt': p, 'answer': TF.index(a), 'evidence': ev,
                           'why': (f'原文：“{ev}”' + (f'{note}' if note else '')) if ev else note} for p, a, ev, note in s['items']]
        elif kind == 'proof':
            x['lines'] = [line for line, *_ in s['items']]
            x['items'] = [{'line': i, 'wrong': w, 'fix': f, 'why': why} for i, (line, w, f, why) in enumerate(s['items'])]
        out.append(x)
    return {'id': tid, 'title': title, 'kind': kind, 'how': how, 'sets': out}


# ============================================================ 中考 (A2)

ZK_CLOZE = [
    {'title': 'The Lost Key', 'text': '''Last Friday, Tom got home from school at five. He looked in his bag for his key, but it was not {1}. He felt worried because his parents were still at {2}. He sat down on the steps and tried to {3} where he had left it. Then he remembered: he had {4} it out of his bag in the library to find a pen.

Tom ran back to school as {5} as he could. The library was about to close, but Mrs Li, the librarian, was still {6}. "Are you looking for this?" she asked with a {7}, and held up a small key. Tom was so {8} that he thanked her again and again. On the way home, he did not put the key in his bag. He held it {9} in his hand. From that day on, he always {10} his bag before he left a room.''',
     'items': [
         ('there|ready|true|open', '他在包里找钥匙却没找到，钥匙“不在那里”：not there。'),
         ('work|home|school|table', '他着急是因为父母还“在上班”，没人能给他开门；如果父母 at home 就不用着急了。'),
         ('remember|forget|explain|imagine', '坐下来“努力回想”放在哪儿了，下一句 Then he remembered 正好呼应。'),
         ('taken|put|given|sent', 'take sth out of ... 从……里拿出来：为了找笔，把钥匙从包里拿了出来。'),
         ('fast|slowly|late|little', 'as fast as he could 尽可能快；图书馆快关门了，所以要跑得快。'),
         ('there|away|asleep|outside', '图书馆快关门，但管理员“还在”，后文她才能把钥匙递给汤姆。'),
         ('smile|cry|shout|sigh', '帮人找回东西，友好地“笑着”问：with a smile。'),
         ('happy|sad|angry|tired', '找回了钥匙，一遍又一遍道谢，说明他非常“高兴”。'),
         ('tightly|lightly|kindly|loudly', '刚丢过钥匙，怕再丢，所以“紧紧地”握在手里。'),
         ('checked|forgot|lost|opened', '吸取了教训：离开房间前总要“检查”一下包。forgot、lost 与吸取教训相反。'),
     ]},
    {'title': "A Breakfast for Mum", 'text': '''Lily wanted to give her mother a surprise on Mother's Day. She decided to {1} breakfast by herself. She got up very {2}, at six o'clock, when everyone else was still sleeping. She went into the kitchen {3}, because she didn't want to wake anyone up.

First, she {4} two eggs and some milk from the fridge. Then she tried to make an omelette, but it was much {5} than she had thought. The first one was burnt, and the second one {6} apart in the pan. Lily almost gave up.

Just then, her father came in. Instead of {7} the omelette for her, he showed her how to turn the heat down. The third omelette looked much {8}. When her mother came down, she saw the table with eggs, bread and a card that said "I love you, Mum." She {9} Lily a big hug. Lily learned that a gift does not need to be perfect; what {10} most is the love behind it.''',
     'items': [
         ('make|buy|eat|order', 'by herself 自己一个人，后文她在厨房煎蛋，所以是自己“做”早餐。'),
         ('early|late|slowly|quietly', '六点钟、别人都还在睡，说明她起得很“早”。'),
         ('quietly|loudly|happily|angrily', '不想吵醒别人，所以“轻轻地”走进厨房。'),
         ('took|put|sent|threw', 'from the fridge 从冰箱里“拿出”鸡蛋和牛奶。'),
         ('harder|easier|cheaper|shorter', '后文第一个煎糊了、第二个散了，说明比想象的“难”。'),
         ('fell|gave|put|took', 'fall apart 散开、碎掉，和前面的 burnt 一样是失败。'),
         ('making|eating|selling|throwing', 'Instead of ... 爸爸没有“替她做”，而是教她把火调小。'),
         ('better|worse|older|smaller', '爸爸教了方法，第三个煎蛋看起来“好多了”。'),
         ('gave|told|asked|showed', 'give sb a hug 拥抱某人，固定搭配。'),
         ('matters|costs|happens|changes', 'what matters most 最重要的是……：礼物不必完美，最重要的是心意。'),
     ]},
]

ZK_DIALOG = [
    {'title': 'At the Library', 'text': '''A: Good morning. Can I help you?
B: Yes, please. {1}
A: Sure. Do you have a library card?
B: {2} I'm new at this school.
A: No problem. You can get one at that desk. It's free.
B: Great. How many books can I borrow at a time?
A: {3} And you can keep them for two weeks.
B: {4}
A: You can renew them online, or come back and ask us.
B: Thank you very much.
A: {5}''',
     'bank': ["I'd like to borrow some books.", "No, I don't.", 'Three at a time.', 'What if I need them for longer?', "You're welcome.",
              'How much does the card cost?', "It's on the second floor."],
     'items': [
         ("I'd like to borrow some books.", '对方问能帮什么忙，B 说明来意；后面又问借书证、能借几本，所以是来借书。'),
         ("No, I don't.", '回答 Do you have ...? 用 Yes/No；后面说“我是新来的”“可以去那边办”，说明没有借书证。'),
         ('Three at a time.', '回答 How many books ...? 要说数量。'),
         ('What if I need them for longer?', '对方回答“可以网上续借”，说明 B 问的是想借更久怎么办。'),
         ("You're welcome.", '回应对方的 Thank you very much。'),
     ]},
    {'title': 'A Plan for Saturday', 'text': '''A: Hi, Mike. This is Jenny. {1}
B: Nothing special. Why?
A: Some of us are going to plant trees in the park on Saturday morning. {2}
B: Sounds great! What time shall we meet?
A: {3}
B: That's a bit early, but OK. What should I bring?
A: {4} The park will give us the tools.
B: All right. {5}
A: See you then.''',
     'bank': ['What are you going to do this Saturday?', 'Would you like to come with us?', "Let's meet at the park gate at 7:30.",
              'Just some water and a hat.', 'See you on Saturday.', "I'm sorry, I can't.", 'We went there by bike.'],
     'items': [
         ('What are you going to do this Saturday?', 'B 回答“没什么特别的，怎么了？”，说明 A 问的是周六有什么安排。'),
         ('Would you like to come with us?', 'B 回答 Sounds great!，说明 A 在邀请他一起去。'),
         ("Let's meet at the park gate at 7:30.", 'B 问几点见面，又说“有点早”，所以 A 给出了时间和地点。'),
         ('Just some water and a hat.', 'B 问要带什么，A 后面说工具公园会给，所以只要带水和帽子。'),
         ('See you on Saturday.', 'A 回答 See you then.，B 说的是“周六见”。'),
     ]},
    {'title': 'In a Clothes Shop', 'text': '''A: Can I help you?
B: Yes. {1}
A: What size do you wear?
B: {2}
A: Here you are. What about this blue one?
B: {3} Do you have it in another colour?
A: Yes, we have a white one.
B: Oh, I like the white one. {4}
A: It's 80 yuan.
B: OK, I'll take it.
A: {5}''',
     'bank': ["I'm looking for a T-shirt.", 'Medium, I think.', "It's nice, but I don't like the colour.", 'How much is it?',
              'Please pay at the front desk.', "I'm just looking.", "It's too expensive."],
     'items': [
         ("I'm looking for a T-shirt.", 'B 先说 Yes，再说要买什么；后文的 this blue one、it 都指一件衣服。I\'m just looking 和 Yes 矛盾。'),
         ('Medium, I think.', '回答 What size ...? 要说尺码。'),
         ("It's nice, but I don't like the colour.", '空后 B 问有没有别的颜色，说明不喜欢这个颜色。'),
         ('How much is it?', '对方回答“80 元”，B 问的是价格。'),
         ('Please pay at the front desk.', 'B 说“我买了”，店员告诉他去哪儿付钱。'),
     ]},
    {'title': 'Before the Test', 'text': '''A: You look tired, Wang Fang. {1}
B: I'm fine. I just didn't sleep well last night.
A: {2}
B: I was worried about tomorrow's English test.
A: Don't worry. You have worked hard. {3}
B: Thanks. But I still can't remember some of the new words.
A: {4} We can read them together after school.
B: That's very kind of you. {5}
A: You're welcome. What are friends for?''',
     'bank': ['Are you all right?', "Why couldn't you sleep?", "I'm sure you'll do well.", 'Let me help you.', 'Thank you so much.',
              "I'm afraid I can't.", 'How often do you exercise?'],
     'items': [
         ('Are you all right?', 'B 回答 I\'m fine，说明 A 问的是“你还好吗”。'),
         ("Why couldn't you sleep?", 'B 回答“我在担心明天的考试”，是在说原因，所以 A 问的是为什么睡不好。'),
         ("I'm sure you'll do well.", 'A 在安慰她：别担心，你很努力，一定会考好。'),
         ('Let me help you.', '空后 A 说放学后一起读单词，是在提出帮忙。'),
         ('Thank you so much.', 'A 回答 You\'re welcome，B 是在道谢。'),
     ]},
]

# ============================================================ 高考 (B1)

GK_SEVEN = [
    {'title': 'How to Make Small Talk', 'text': '''Many people find it hard to start a conversation with someone they don't know. {1} The good news is that small talk is a skill, and like any skill, it gets easier with practice. Here are some tips.

Ask open questions. A question like "Do you like the weather?" can be answered with "yes" or "no", and then the talk stops. {2} Questions like "What brings you here today?" give the other person something to talk about.

Listen more than you speak. {3} Nod, look at the speaker and ask a follow-up question about what they have just said. People enjoy talking to someone who is really interested in them.

Find common ground. If you are at a friend's party, you can ask how they know the host. {4} Once you find something you share, the conversation usually flows naturally.

Don't worry about awkward silences. A short pause is normal in any conversation. {5} You can use it to think of your next question, or simply smile and wait.''',
     'bank': ["They may worry about saying the wrong thing or having nothing to say.", 'Instead, try questions that begin with "what", "how" or "why".',
              'Good listeners show that they are paying attention.', 'If you are at a sports event, you can talk about the game.',
              'It does not mean the other person is bored.', 'Most people prefer to talk about the weather.',
              'Remember to talk about yourself as much as possible.'],
     'items': [
         ("They may worry about saying the wrong thing or having nothing to say.", '空前说很多人觉得和陌生人开口难，这句说明原因；空后 The good news is ... 转到好消息。'),
         ('Instead, try questions that begin with "what", "how" or "why".', '空前说只能回答 yes/no 的问题会让谈话中断，空后举例 What brings you here today?，正是 what 开头的问题。'),
         ('Good listeners show that they are paying attention.', '本段主题是多听少说，空后讲点头、看着对方、追问，都是“表现出在认真听”。'),
         ('If you are at a sports event, you can talk about the game.', '本段讲找共同点，空前举朋友聚会的例子，这句再举体育赛事的例子，句式一致。'),
         ('It does not mean the other person is bored.', '空前说短暂停顿很正常，这句接着说停顿不代表对方无聊；空后讲怎么利用停顿。'),
     ]},
    {'title': 'Keep a Learning Diary', 'text': '''Many students spend hours studying, but few stop to think about how they study. A learning diary can help. {1}

A learning diary is simple. At the end of each day, write down what you learned and how you learned it. {2} Just a few sentences are enough.

The diary helps you notice what works. For example, you may find that you remember new words better when you use them in a sentence. {3}

It also shows you your problems. If the same mistake appears in your diary again and again, you know where you need more practice. {4}

Finally, a diary keeps you going. On days when you feel you are making no progress, read your old entries. {5} That can give you the energy to keep working.''',
     'bank': ['It is a notebook where you record and think about your own learning.', "You don't need to write a lot.",
              'Then you can use that method more often.', 'Without the diary, you might not have noticed the pattern.',
              'You will be surprised by how much you have learned.', "Most teachers check their students' diaries every week.",
              'A good diary should be at least two pages long.'],
     'items': [
         ('It is a notebook where you record and think about your own learning.', '空前刚提到学习日记，这句解释它是什么；下一段 A learning diary is simple 接着讲。'),
         ("You don't need to write a lot.", '空后 Just a few sentences are enough 与“不用写很多”呼应；“至少两页”与之矛盾。'),
         ('Then you can use that method more often.', '空前举例发现某个方法有效，这句顺着说“那就多用这个方法”。'),
         ('Without the diary, you might not have noticed the pattern.', '空前说同一个错误反复出现，这句说没有日记可能注意不到这个规律。'),
         ('You will be surprised by how much you have learned.', '空前说觉得没进步时读读旧日记，空后 That can give you the energy，这句正是读后的感受。'),
     ]},
    {'title': 'Cycling to School', 'text': '''In many cities, more and more teenagers are cycling to school. {1}

First, cycling is good for your health. Riding for twenty minutes a day is a simple way to get exercise without going to the gym. {2}

Second, it saves time in busy cities. {3} A bike, however, can often go through small streets and arrive on time.

Of course, safety comes first. {4} Wear a helmet, follow the traffic rules and never use your phone while riding.

{5} If your school is too far away, you can ride to a bus stop and take the bus for the rest of the way.''',
     'bank': ['There are several good reasons for this.', 'It also helps you feel more awake in class.',
              'During rush hour, cars and buses are often stuck in traffic.', 'Before you set off, make sure your bike is in good condition.',
              'Cycling does not have to be all or nothing.', 'Buses are the safest way to travel.',
              'Many parents drive their children to school every day.'],
     'items': [
         ('There are several good reasons for this.', '下文用 First、Second 列举原因，这句总起。'),
         ('It also helps you feel more awake in class.', '本段讲骑车对身体好，also 再补充一个好处：上课更清醒。'),
         ('During rush hour, cars and buses are often stuck in traffic.', '空后 A bike, however, can ... 和它对比：汽车公交堵车，自行车却能准时到。'),
         ('Before you set off, make sure your bike is in good condition.', '本段讲安全，出发前检查车况和空后的戴头盔、守规则同属安全措施。'),
         ('Cycling does not have to be all or nothing.', '空后说学校太远可以先骑到车站再坐公交，就是“不必全程都骑车”。'),
     ]},
    {'title': 'Learning to Say No', 'text': '''Do you find it hard to say no? {1} Many people agree to things they don't really want to do, simply because they don't want to upset others.

However, saying yes to everything has a cost. {2} You may end up tired, stressed and unable to do your own work well.

Saying no politely is a skill you can learn. {3} For example, "Thanks for asking me, but I can't help this weekend."

You don't always have to give a long explanation. {4} A short, honest reason is usually enough.

{5} When you protect your time, you can say yes with real energy to the things that matter most.''',
     'bank': ['If so, you are not alone.', 'Your time and energy are limited.', 'Start by thanking the person, then give a clear answer.',
              'Too many reasons can sound like excuses.', 'In the end, saying no can actually help you say yes.',
              'Most people say no too often.', 'You should always help your friends, whatever happens.'],
     'items': [
         ('If so, you are not alone.', '空前是问句“你觉得拒绝很难吗”，空后说很多人都这样，这句承上启下。'),
         ('Your time and energy are limited.', '空前说什么都答应“有代价”，空后说会累、会做不好自己的事，原因是时间精力有限。'),
         ('Start by thanking the person, then give a clear answer.', '空后的例子 Thanks for asking me, but I can\'t ... 正是先道谢、再明确回答。'),
         ('Too many reasons can sound like excuses.', '空前说不必长篇解释，空后说简短诚实的理由就够了，这句说明原因。'),
         ('In the end, saying no can actually help you say yes.', '空后说保护好时间，才能全力对重要的事说 yes，这句是全文总结。'),
     ]},
]

GK_CLOZE = [
    {'title': 'The Old Piano', 'text': '''When I was twelve, my parents bought an old piano from a neighbour who was moving away. It was {1}, with a few keys that made no sound at all. I begged them to {2} it, but they said we could not afford a new one.

So I started to {3} on it every day after school. At first I hated it. The broken keys made my songs sound {4}. But slowly I learned to play around them, choosing songs that did not need those notes.

Two years later, our school held a music {5}. I decided to take part. On the day, I found that the piano on the stage was a brand-new one. For the first time, every key {6}. I was so surprised that I almost {7} my place in the song.

I didn't win first prize, but a teacher came up to me afterwards. "You play with great {8}," she said. "How did you learn to be so careful?" I smiled and told her about our old piano.

Now I understand that the piano's {9} taught me more than a perfect one could have. Sometimes the {10} we face are the very things that help us grow.''',
     'items': [
         ('damaged|expensive|modern|beautiful', '有几个键按下去不出声，说明钢琴“有损坏”。'),
         ('replace|clean|sell|play', '后文说买不起新的，所以“我”求父母“换”一台。'),
         ('practise|sleep|write|sit', '后文“我”学会绕开坏键弹奏，还参加了音乐比赛，说明每天都在“练”。'),
         ('strange|perfect|soft|famous', '坏键不出声，弹出来的曲子听着“怪”。'),
         ('competition|lesson|class|shop', '后文 take part、didn\'t win first prize，说明是音乐“比赛”。'),
         ('worked|broke|disappeared|hurt', '新钢琴“每个键都能响”，第一次如此，与旧钢琴对比。'),
         ('lost|found|kept|saved', 'lose one\'s place 找不到弹到哪儿了：太惊讶，差点弹乱。'),
         ('care|speed|noise|anger', '老师接着问 How did you learn to be so careful?，与 with great care 呼应。'),
         ('problems|price|colour|size', '与 a perfect one 对比：正是旧钢琴的“毛病”教会了“我”更多。'),
         ('difficulties|gifts|friends|rules', 'face difficulties 面对困难；全文主旨是困难让人成长。'),
     ]},
    {'title': 'The Bus Driver', 'text': '''Every morning, Mr Chen drove the number 12 bus through the busy streets of our town. Most passengers {1} him without a word, their eyes on their phones. But Mr Chen always said "Good morning" to everyone who got on.

One cold winter day, an old woman got on the bus with a heavy bag. She {2} for her money but could not find it. The passengers behind her began to {3}. Mr Chen simply waved her in. "Pay me next time," he said {4}.

A week later, the woman came back with the money and a box of homemade cakes. She told Mr Chen that on that day she had been on her way to the {5} to visit her sick husband. "Your kindness made a hard day {6}," she said.

The story {7} quickly. A passenger who had seen everything wrote about it online, and soon the whole town knew. People started to {8} Mr Chen's greeting. Some even brought him hot tea on cold mornings.

Mr Chen was {9} by all the attention. "I only did a small thing," he said. But for many people in our town, that small thing was a {10} that kindness is still everywhere.''',
     'items': [
         ('passed|helped|called|followed', '乘客们眼睛盯着手机，一言不发地从他身边“走过”。'),
         ('searched|paid|asked|waited', 'search for 寻找；后文 could not find it 说明在“找”钱。'),
         ('complain|sing|dance|sleep', '老人找不到钱耽误了时间，后面的乘客开始“抱怨”。'),
         ('kindly|angrily|loudly|sadly', '让她先上车、下次再付，说明他说得很“和善”。'),
         ('hospital|cinema|market|airport', '去看望生病的丈夫，所以是去“医院”。'),
         ('easier|longer|worse|colder', '你的好意让难熬的一天变得“好过些”，与 hard 相对。'),
         ('spread|ended|changed|stopped', '后文“很快全镇都知道了”，说明故事“传开了”。'),
         ('return|ignore|forget|refuse', '以前乘客对他的问候不理不睬，现在开始“回应”他的问候，还给他送热茶。'),
         ('surprised|annoyed|bored|frightened', '他说“我只是做了件小事”，说明他对大家的关注感到“意外”。'),
         ('reminder|secret|mistake|reason', 'a reminder that ... 提醒人们：善意依然无处不在。'),
     ]},
]

# ============================================================ 四级 (B1)

CET4_BANKED = [
    {'title': 'Sleep and Memory', 'sort': True, 'text': '''Scientists have long known that sleep is important for health, but recent studies show it also plays a key {1} in learning. When we sleep, the brain does not simply rest. Instead, it {2} the information we took in during the day, deciding what to keep and what to throw away.

In one experiment, students learned a list of new words in the evening. Half of them slept normally, while the others stayed awake all night. The next day, the students who had slept {3} far more words. Even a short nap in the afternoon produced a {4} improvement.

These findings have practical {5} for students. Staying up late to study before an exam may seem like a good idea, but it can actually {6} your performance. Without enough sleep, the brain struggles to {7} new memories, so much of what you studied may be lost.

Experts {8} that students get between seven and nine hours of sleep each night. They also suggest reviewing difficult material shortly before going to bed, since the brain seems to give {9} to what it processed last. In short, a good night's sleep is not a waste of study time; it is an {10} part of learning itself.''',
     'bank': ['role', 'sorts', 'recalled', 'noticeable', 'implications', 'harm', 'store', 'recommend', 'priority', 'essential',
              'rarely', 'ignore', 'mostly', 'expensive', 'attempted'],
     'items': [
         ('role', 'play a key role in ... 在……中起关键作用；空前是形容词 key，要名词。'),
         ('sorts', '主语 it 是单数，要动词第三人称单数；后文 deciding what to keep and what to throw away 正是“整理、分类”。'),
         ('recalled', '与 had slept 并列叙述过去的实验结果，要过去式；“回忆起”更多单词才说明睡眠帮助记忆。'),
         ('noticeable', '冠词是 a（不是 an），后接 improvement，要辅音开头的形容词：明显的改善。'),
         ('implications', 'have practical implications for ... 对……有实际意义；空前是形容词，要名词复数。'),
         ('harm', 'can actually 后接动词原形；熬夜反而会“损害”考试表现。'),
         ('store', 'struggles to 后接动词原形；睡不够大脑难以“储存”新记忆，所以学的会丢。'),
         ('recommend', '主语 Experts 是复数，that 从句用动词原形 get，是 recommend that sb (should) do 的结构。'),
         ('priority', 'give priority to ... 优先处理……；大脑优先处理最后处理过的内容。'),
         ('essential', '冠词是 an，要元音开头的形容词；睡眠是学习“必不可少”的一部分。'),
     ]},
    {'title': 'The Problem with Returns', 'sort': True, 'text': '''Online shopping has changed the way we buy things. With a few clicks, we can order almost anything and have it {1} to our door. However, this convenience has created a hidden problem: returns.

Because shoppers cannot touch or try on products before buying, many order several sizes or colours and send back the ones they do not want. In some countries, as many as one in three clothing items bought online is {2}.

Returns are {3} for companies. Each returned item must be checked, cleaned, {4} and put back on the shelf. Some items cannot be sold again at all and end up being thrown away, which is bad for the {5}.

To deal with this, some companies have started to {6} customers for returns, while others use technology to help shoppers choose the right size. Virtual fitting rooms, for example, allow customers to see how clothes would look on a body {7} to their own.

Shoppers can also help. Reading reviews {8}, checking size charts and thinking twice before ordering can {9} the number of returns. After all, the most {10} product is the one that never has to make a second journey.''',
     'bank': ['delivered', 'returned', 'costly', 'repackaged', 'environment', 'charge', 'similar', 'carefully', 'reduce', 'sustainable',
              'fortunately', 'increase', 'generous', 'borrowed', 'complaint'],
     'items': [
         ('delivered', 'have sth done 让某事被做：把东西“送”到家门口，要过去分词。'),
         ('returned', '全文讲退货，每三件网购衣服就有一件被“退回”，is 后接过去分词表被动。'),
         ('costly', 'are 后接形容词；后文列出检查、清洗、重新包装等步骤，说明退货“代价高”。'),
         ('repackaged', '与 checked、cleaned 并列，都是过去分词：被检查、清洗、重新包装。'),
         ('environment', 'be bad for the environment 对环境不好；被扔掉的商品造成浪费。'),
         ('charge', 'charge sb for sth 向某人收……的费用；与后文用技术帮顾客选对尺码，都是减少退货的办法。'),
         ('similar', 'similar to ... 与……相似：看衣服穿在和自己身材相近的身体上的效果。'),
         ('carefully', '修饰动名词短语 Reading reviews，要副词：认真读评价。'),
         ('reduce', 'can 后接动词原形；认真读评价、看尺码表能“减少”退货。increase 意思相反。'),
         ('sustainable', 'the most 后接形容词；不用“二次旅程”的商品最“环保、可持续”。'),
     ]},
]

CET4_MATCH = [
    {'title': 'Why Do We Put Things Off?', 'paras': [
        'Almost everyone puts things off from time to time. A student waits until the night before to start an essay; a worker leaves an important email unanswered for days. Researchers estimate that around one in five adults procrastinates so often that it affects their health, money or relationships.',
        'For a long time, procrastination was seen as a problem of time management. People were told to make better schedules and use planners. But psychologists now believe this view misses the point. Most procrastinators know exactly how much time they have; the problem lies elsewhere.',
        'According to recent research, procrastination is mainly about managing feelings. When a task makes us feel anxious, bored or unsure of ourselves, putting it off gives us quick relief. The bad feeling goes away for a moment, which is why the habit is so hard to break.',
        'Unfortunately, the relief does not last. The task is still there, and now there is less time to do it. Many procrastinators report feeling guilty and stressed, which makes the task seem even more unpleasant. In this way, a cycle begins: the worse we feel, the more we delay.',
        'Perfectionism can make things worse. People who believe their work must be flawless often fear starting at all, because any first attempt will fall short of their high standards. For them, delaying the task protects them from facing a result that is less than perfect.',
        'One effective strategy is to make the first step very small. Instead of planning to "write the report", a person might decide to "open the file and write one sentence". Once people begin, they often find the task is less difficult than they had imagined, and they keep going.',
        'Being kind to yourself also helps. In one study, students who forgave themselves for procrastinating before a first exam delayed less before the next one. Blaming yourself, by contrast, simply adds more negative feelings, the very thing that causes procrastination in the first place.',
        'Finally, it helps to change your surroundings. Putting your phone in another room, or working in a library instead of your bedroom, removes easy escapes. When distractions are harder to reach, starting the task becomes the easiest option.'],
     'items': [
         ('Taking a tiny first step can make a task feel easier than expected.', 'F', 'they often find the task is less difficult than they had imagined'),
         ('Some people delay tasks because they are afraid their work will not be perfect.', 'E', 'often fear starting at all, because any first attempt will fall short of their high standards'),
         ('Procrastination used to be treated as a matter of poor planning.', 'B', 'procrastination was seen as a problem of time management'),
         ('Delaying a task gives people a short break from unpleasant feelings.', 'C', 'putting it off gives us quick relief'),
         ('Students who did not blame themselves procrastinated less later.', 'G', 'students who forgave themselves for procrastinating before a first exam delayed less before the next one'),
         ('About twenty percent of adults procrastinate in a way that causes real problems.', 'A', 'around one in five adults procrastinates so often that it affects their health, money or relationships'),
         ('Feeling bad about delaying can lead to even more delay.', 'D', 'the worse we feel, the more we delay'),
         ('Keeping distractions out of reach can make it easier to begin.', 'H', 'When distractions are harder to reach, starting the task becomes the easiest option.'),
         ('Most people who procrastinate are well aware of their deadlines.', 'B', 'Most procrastinators know exactly how much time they have'),
         ('Criticising yourself adds to the very feelings that lead to procrastination.', 'G', 'Blaming yourself, by contrast, simply adds more negative feelings'),
     ]},
    {'title': 'The Return of Reading Aloud', 'paras': [
        'Reading aloud was once the normal way to enjoy a book. Before printed books became cheap, families often gathered in the evening while one person read to the others. Silent reading only became common for most people in the last few hundred years.',
        'Today, most adults read silently, and reading aloud is usually linked with young children. Parents read bedtime stories, and teachers read to classes, but the practice tends to stop once children can read on their own, often around the age of eight.',
        'Researchers say this may be a mistake. Studies show that children continue to benefit from being read to long after they can read by themselves. Listening to a skilled reader exposes them to words and sentence patterns that are more advanced than those they could read alone.',
        'Reading aloud also helps adults. In one experiment, people remembered more of a list of words when they read it aloud than when they read it silently. Scientists call this the "production effect": saying something makes it more distinct in memory.',
        'For language learners, the benefits are especially clear. Reading a text aloud forces learners to pay attention to every word, including small ones they might skip when reading silently. It also helps them practise pronunciation and the rhythm of the language.',
        'There are social benefits, too. Book clubs in which members take turns reading to each other have become popular in several cities. Members say that sharing a story out loud creates a sense of connection that reading alone cannot provide.',
        'Some care homes have started reading programmes for older residents. Volunteers visit once a week to read short stories and poems. Staff report that residents who join the sessions seem calmer and talk more with each other afterwards.',
        'Of course, reading aloud is slower than reading silently, and it is not practical for every situation. But experts suggest that adding even ten minutes a day can bring real benefits, whether you read to a child, a friend or simply to yourself.'],
     'items': [
         ('Saying words out loud can help people remember them better.', 'D', 'people remembered more of a list of words when they read it aloud than when they read it silently'),
         ('Many parents stop reading to their children once the children can read independently.', 'B', 'the practice tends to stop once children can read on their own'),
         ('Reading aloud makes learners notice words they might otherwise miss.', 'E', 'including small ones they might skip when reading silently'),
         ('Older people who take part in reading sessions appear more relaxed.', 'G', 'residents who join the sessions seem calmer'),
         ('Hearing a good reader introduces children to more difficult language.', 'C', 'exposes them to words and sentence patterns that are more advanced than those they could read alone'),
         ('Reading aloud takes more time than reading silently.', 'H', 'reading aloud is slower than reading silently'),
         ('In the past, reading was often a shared family activity.', 'A', 'families often gathered in the evening while one person read to the others'),
         ('Reading to others can make people feel closer to each other.', 'F', 'sharing a story out loud creates a sense of connection'),
         ('A short daily habit of reading aloud is said to be worthwhile.', 'H', 'adding even ten minutes a day can bring real benefits'),
         ('Language learners can improve their pronunciation by reading aloud.', 'E', 'It also helps them practise pronunciation and the rhythm of the language.'),
     ]},
]

# ============================================================ 六级 (B2)

CET6_BANKED = [
    {'title': 'The Hidden Cost of Free Apps', 'sort': True, 'text': '''Most of the apps on our phones cost nothing to download. Yet as the saying goes, if you are not paying for the product, you are the product. Free apps {1} make money by collecting data about their users and selling advertising based on it.

This business model is not {2} harmful. Targeted ads can be useful, showing people products they might genuinely want. The trouble is that few users understand how much information they are giving away. Privacy policies are often long and full of legal {3}, so most people accept them without reading a word.

The data collected can be surprisingly {4}. By tracking where you go, what you search for and how long you look at certain posts, companies can build a detailed {5} of your habits, interests and even your mood. Critics argue that such information could be used to {6} people's choices in ways they do not notice.

Governments have begun to respond. New laws in several regions require companies to explain clearly what data they collect and to obtain users' {7} before sharing it. Some apps now offer a paid version without ads or tracking, giving users a real {8}.

Ultimately, however, protecting privacy also depends on users themselves. Checking app permissions, deleting apps you no longer use and thinking before you click "agree" are small habits that can {9} reduce your digital footprint. Being {10} about what we share is the first step towards taking back control.''',
     'bank': ['typically', 'inherently', 'jargon', 'revealing', 'profile', 'manipulate', 'consent', 'alternative', 'significantly', 'cautious',
              'affordable', 'transparency', 'reluctantly', 'compensate', 'eliminate'],
     'items': [
         ('typically', '放在主语和谓语 make money 之间，要副词：免费应用“通常”靠收集数据赚钱。'),
         ('inherently', 'not inherently harmful 本身并不有害；空后说定向广告也可能有用，是让步。'),
         ('jargon', 'legal jargon 法律术语；所以大多数人一个字不读就点了同意。'),
         ('revealing', 'can be 后接形容词；后文说能据此画出你的习惯、兴趣甚至情绪，说明数据“透露很多”。'),
         ('profile', 'a detailed profile of ... 一幅关于……的详细画像；冠词 a 和形容词 detailed 后要名词。'),
         ('manipulate', 'be used to do；in ways they do not notice 在不知不觉中“操纵”人们的选择。'),
         ('consent', "obtain users' consent 征得用户同意，后文 before sharing it。"),
         ('alternative', 'a real alternative 真正的另一种选择：可以付费换取无广告、无追踪。'),
         ('significantly', '修饰动词 reduce，要副词：“大大”减少数字足迹。'),
         ('cautious', 'be cautious about ... 对……谨慎；Being 后要形容词。'),
     ]},
    {'title': 'What Failed Experiments Teach', 'sort': True, 'text': '''Science is often presented as a smooth march from one discovery to the next. In reality, most experiments fail. Results turn out to be {1}, equipment breaks down, and ideas that seemed brilliant prove to be wrong. Yet these failures are rarely published, which creates a {2} picture of how research actually works.

Some researchers argue that this silence is costly. When failed experiments are not reported, other scientists may {3} the same mistakes, wasting years of effort and large amounts of {4}. A negative result, showing that something does not work, can be just as {5} as a positive one, because it tells others which paths to avoid.

There are also deeper problems. Because journals tend to favour exciting findings, researchers may feel {6} to present their results in the most positive light. In extreme cases, this can lead to data being selectively reported, which {7} the reliability of the whole field.

To {8} this, a growing number of journals now welcome studies with negative results, and some funders require researchers to register their plans before an experiment begins. This makes it harder to change the question after seeing the answer.

Such changes reflect a broader shift in attitude. Failure, once seen as something to hide, is increasingly {9} as a normal and necessary part of discovery. As one scientist put it, an experiment that fails is still a success, as long as we report it {10} and learn something from it.''',
     'bank': ['inconclusive', 'misleading', 'repeat', 'funding', 'valuable', 'pressured', 'undermines', 'counter', 'recognised', 'honestly',
              'deliberately', 'celebrate', 'accurate', 'abandon', 'rapidly'],
     'items': [
         ('inconclusive', 'turn out to be + 形容词；与“设备坏了”“想法被证明是错的”并列，指实验结果“没有定论”。'),
         ('misleading', '冠词是 a，要辅音开头的形容词：失败不发表，给人一幅“误导性的”科研图景。'),
         ('repeat', 'may 后接动词原形；失败不被报告，别的科学家可能“重复”同样的错误。'),
         ('funding', 'large amounts of 后接不可数名词：浪费多年的努力和大量“经费”。'),
         ('valuable', 'just as ... as 中间用形容词；后文说它告诉别人哪些路不用走，所以同样“有价值”。'),
         ('pressured', 'feel pressured to do 感到有压力去做；期刊偏爱激动人心的发现。'),
         ('undermines', '主语是前面整件事（which），要第三人称单数：选择性报告数据会“削弱”整个领域的可靠性。'),
         ('counter', 'To 后接动词原形：为了“应对、抵消”这个问题，期刊开始接受负面结果。'),
         ('recognised', 'is increasingly 后接过去分词表被动：失败越来越被“视为”正常的一部分。'),
         ('honestly', '修饰 report it，要副词；只要“如实”报告失败并从中学到东西，就仍是成功。'),
     ]},
]

CET6_MATCH = [
    {'title': 'The Four-Day Week', 'paras': [
        'For most of the twentieth century, the five-day, forty-hour week was treated as a fixed feature of working life. It had been won by labour movements and was widely seen as a fair balance between work and rest. Few people seriously questioned whether it could be shortened further.',
        'In recent years, however, a series of trials has put that assumption to the test. Companies in several countries have experimented with a four-day week, in which employees work around thirty-two hours for the same pay. The largest of these trials involved more than sixty firms and nearly three thousand workers over six months.',
        'The results attracted wide attention. Most participating companies reported that productivity stayed the same or even rose, while employees described lower levels of stress and burnout. At the end of the trial, the vast majority of firms chose to continue with the shorter week, and several made the change permanent.',
        'Supporters argue that these outcomes are not surprising. They point out that much of a typical working day is lost to unnecessary meetings, constant interruptions and tasks of little value. When time is limited, they say, teams are forced to cut out such waste and focus on what genuinely matters.',
        'Critics, however, warn against drawing broad conclusions. The companies that volunteered for the trials were mostly small office-based businesses that were already open to new ideas. Whether the model would work in hospitals, factories or schools, where work cannot simply be done faster, remains an open question.',
        'There are also concerns about hidden costs. Some employees in the trials reported that their work had become more intense, with fewer breaks and greater pressure to finish everything in four days. For them, the extra day off came at the price of a more exhausting working week.',
        'Economists add that the effects may change over time. Early enthusiasm can boost performance in the short term, a pattern sometimes called the "novelty effect". Only longer studies will show whether productivity gains survive once the shorter week becomes ordinary.',
        'Despite these doubts, interest continues to grow. Several governments are funding their own pilot programmes, and surveys suggest that a shorter week is now one of the benefits job seekers value most. Whatever the final verdict, the debate has forced many organisations to rethink how working time is used.'],
     'items': [
         ('Workers in the trials said they felt less stressed.', 'C', 'employees described lower levels of stress and burnout'),
         ('The firms that joined the trials may not represent all kinds of workplaces.', 'E', 'The companies that volunteered for the trials were mostly small office-based businesses that were already open to new ideas.'),
         ('A lot of working time is wasted on meetings and interruptions.', 'D', 'much of a typical working day is lost to unnecessary meetings, constant interruptions and tasks of little value'),
         ('Improvements seen at the start of a change may not last.', 'G', 'Early enthusiasm can boost performance in the short term'),
         ('The five-day week was long considered a reasonable arrangement.', 'A', 'was widely seen as a fair balance between work and rest'),
         ('Some employees found their four working days more tiring than before.', 'F', 'the extra day off came at the price of a more exhausting working week'),
         ('Most companies decided to keep the shorter week after the trial ended.', 'C', 'the vast majority of firms chose to continue with the shorter week'),
         ('Job seekers increasingly see a shorter week as an attractive benefit.', 'H', 'a shorter week is now one of the benefits job seekers value most'),
         ('In the trials, staff worked fewer hours without losing any pay.', 'B', 'employees work around thirty-two hours for the same pay'),
         ('It is unclear whether the model suits jobs where work cannot be sped up.', 'E', 'where work cannot simply be done faster, remains an open question'),
     ]},
    {'title': 'Trees in the City', 'paras': [
        "City planners once treated trees mainly as decoration. They were planted along avenues and in parks to make streets look pleasant, but they were rarely considered part of a city's essential infrastructure, like roads, pipes or power lines.",
        'That view is changing rapidly. A growing body of research shows that urban trees provide services with real economic value. One study of a large American city estimated that its trees saved tens of millions of dollars a year by reducing energy use, cleaning the air and absorbing rainwater.',
        'Cooling is perhaps the most important of these services. Streets lined with trees can be several degrees cooler in summer than streets without them, because leaves provide shade and release water vapour. As heatwaves become more frequent, this effect could save lives, particularly among elderly residents.',
        'Trees also help manage water. During heavy rain, their roots and the soil around them absorb water that would otherwise rush into drains. This reduces the risk of flooding and lowers the cost of building ever larger drainage systems.',
        'The benefits extend to mental health. Several studies have found that people living near green spaces report lower levels of anxiety and depression. Even a view of trees from a window has been linked to faster recovery among hospital patients.',
        'Yet the distribution of trees is often unequal. In many cities, wealthier neighbourhoods have far more tree cover than poorer ones. Residents of the least green areas therefore suffer more from heat and pollution, while having fewer resources to cope with them.',
        'Planting trees is not as simple as it sounds. Young trees need regular watering and protection for several years, and many die before they mature. Choosing the wrong species can also cause problems, as some trees damage pavements with their roots or trigger allergies.',
        'For these reasons, experts argue that cities need long-term strategies rather than one-off planting campaigns. Successful programmes involve local communities in caring for trees, and treat the urban forest as a living system that must be maintained, just like any other public asset.'],
     'items': [
         ('Trees were not traditionally regarded as basic city infrastructure.', 'A', "they were rarely considered part of a city's essential infrastructure"),
         ('Poorer areas tend to have fewer trees than richer ones.', 'F', 'wealthier neighbourhoods have far more tree cover than poorer ones'),
         ('Trees can reduce the danger of floods.', 'D', 'This reduces the risk of flooding'),
         ('Seeing trees may help sick people get better more quickly.', 'E', 'Even a view of trees from a window has been linked to faster recovery among hospital patients.'),
         ('Many newly planted trees do not survive to maturity.', 'G', 'many die before they mature'),
         ('Local residents should take part in looking after trees.', 'H', 'Successful programmes involve local communities in caring for trees'),
         ("The money saved by a city's trees has been calculated.", 'B', 'estimated that its trees saved tens of millions of dollars a year'),
         ('Shade from trees could protect older people during hot weather.', 'C', 'this effect could save lives, particularly among elderly residents'),
         ('Some kinds of trees can harm pavements.', 'G', 'some trees damage pavements with their roots'),
         ('People in the least green areas are less able to deal with heat and pollution.', 'F', 'while having fewer resources to cope with them'),
     ]},
]

# ============================================================ 考研 (C1)

KY_CLOZE = [
    {'title': 'The Attention Economy', 'text': '''In an age of endless information, attention has become one of the scarcest resources. Technology companies compete fiercely for it, designing products that are {1} to keep users scrolling for as long as possible. Notifications, autoplay and infinite feeds are not accidental features; they are carefully engineered to {2} our natural curiosity.

The consequences are only beginning to be understood. Some researchers argue that constant switching between tasks {3} our ability to concentrate deeply. Others are more cautious, noting that the evidence is still {4} and that people have always worried about new media, from novels to television.

{5} the debate, few would deny that many people feel their time online is not entirely under their control. Surveys {6} show that users wish they spent less time on their phones, yet find it difficult to {7}.

Some have called for stricter regulation, {8} as limits on features designed to be addictive. Others believe the solution lies in education, helping people to understand how these products work so that they can use them more {9}. Most likely, both approaches will be needed. What is clear is that attention, once lost, is not easily {10}.''',
     'items': [
         ('intended|reluctant|unlikely|forbidden', 'be intended to do 旨在：科技公司争夺注意力，产品就是“为了”让人一直刷。'),
         ('exploit|suppress|ignore|question', '“不是偶然的功能，而是精心设计的”，目的是“利用”人的好奇心；suppress、ignore 与争夺注意力矛盾。'),
         ('weakens|sharpens|measures|explains', '下一句 Others are more cautious 是对前一观点的保留，前一观点应是负面的：频繁切换“削弱”专注力。'),
         ('limited|overwhelming|conclusive|abundant', '持谨慎态度的人会说证据“还有限”；conclusive、overwhelming 与“谨慎”相反。'),
         ('Regardless of|Because of|In addition to|Instead of', '让步：“不管争论如何”，很少有人否认……'),
         ('consistently|rarely|hardly|seldom', '与 few would deny 一致：调查“一再”显示人们希望少用手机；rarely 等与之矛盾。'),
         ('cut back|catch up|give in|show off', 'wish they spent less time ... yet find it difficult to cut back 想少用却难以“减少”。'),
         ('such|so|as|even', 'such as 举例：比如限制让人上瘾的功能。'),
         ('deliberately|carelessly|frequently|secretly', '了解产品的运作方式，是为了更“有意识地”使用它们。'),
         ('regained|wasted|shared|divided', 'once lost, is not easily regained 一旦失去就不容易“找回”，lost 与 regained 对应。'),
     ]},
    {'title': 'Rethinking Expertise', 'text': '''For much of history, expertise was {1} with long years of training. A doctor, a lawyer or an engineer earned authority by mastering a body of knowledge that ordinary people could not easily {2}. The internet has challenged this arrangement. Information that once {3} only in specialist libraries is now available to anyone with a phone.

Some observers welcome this change, arguing that it gives ordinary citizens the power to question authorities who were once beyond {4}. Patients, for instance, now arrive at appointments having already researched their symptoms, and some doctors say this leads to more {5} conversations.

{6}, access to information is not the same as understanding. Experts do not simply know more facts; they know how to {7} evidence, recognise patterns and judge which sources can be trusted. Without these skills, a person searching online may find {8} that confirms what they already believe, rather than what is true.

The challenge, then, is not to {9} expertise but to rebuild trust in it. This may require experts to explain their reasoning more openly and to admit uncertainty when it exists. Paradoxically, acknowledging the limits of knowledge may be the best way to {10} its authority.''',
     'items': [
         ('associated|compared|replaced|confused', 'be associated with 与……联系在一起：专业知识历来和多年训练联系在一起。'),
         ('access|afford|avoid|accept', '下一句说这些信息现在人人都能看到，可见过去普通人难以“获取”。'),
         ('existed|failed|improved|mattered', '信息过去“只存在于”专业图书馆，现在用手机就能看到。'),
         ('question|repair|measure|use', 'beyond question 不容置疑；前面 the power to question 呼应：过去不容置疑的权威，现在可以质疑了。'),
         ('balanced|hostile|brief|silent', '本段是欢迎这种变化的观点，所以医生说对话更“平衡”了；hostile 与“欢迎”相反。'),
         ('However|Therefore|Similarly|Moreover', '上段讲好处，本段说获取信息不等于理解，是转折。'),
         ('weigh|ignore|hide|invent', 'weigh evidence 权衡证据，与“识别规律、判断来源是否可信”并列。'),
         ('evidence|nothing|anyone|silence', '没有这些能力，人们可能只找到“证实”自己原有看法的证据，而不是真相。'),
         ('reject|defend|teach|sell', 'not ... but ...：问题不是“抛弃”专业知识，而是重建对它的信任。'),
         ('strengthen|weaken|ignore|share', 'Paradoxically 看似矛盾：承认知识有限，反而是“增强”其权威的最好办法。'),
     ]},
]

KY_NEW = [
    {'title': 'Reading an Academic Paper', 'text': '''Many students find academic papers intimidating. The language is dense, the arguments are complex, and a single article can run to thirty pages. Yet reading papers efficiently is a skill that can be learned. The following strategies can help.

{1} The abstract summarises the research question, method and main findings in a few hundred words. Reading it first tells you whether the paper is relevant to your needs, which can save hours.

{2} Instead, read the introduction and the conclusion before the middle sections. Together, they show what the authors set out to do and what they claim to have found, giving you a map for the rest of the paper.

{3} Tables and figures often present the core results more clearly than the text. Ask yourself what each one shows and whether it supports the authors' claims.

{4} Note any assumptions the authors make, any limitations they admit, and any questions they leave unanswered. A paper is an argument, not a collection of facts, and you are entitled to judge how convincing it is.

{5} Writing a short summary of the paper in your own words (what was studied, how, and what was found) is the best test of whether you have really understood it. If you cannot write it, go back and read the relevant sections again.''',
     'bank': ['Start with the abstract.', "Don't read from beginning to end.", 'Look closely at the data.', 'Read critically.',
              'Finally, summarise what you have read.', 'Read every reference in the bibliography.', 'Ask your teacher to explain the paper to you.'],
     'items': [
         ('Start with the abstract.', '本段讲摘要是什么、为什么先读它，空处是本段的小标题。'),
         ("Don't read from beginning to end.", '空后 Instead, read the introduction and the conclusion before the middle sections，Instead 说明前面是“不要从头读到尾”。'),
         ('Look closely at the data.', '本段讲表格和图表呈现核心结果，要看它们是否支持作者的结论。'),
         ('Read critically.', '本段讲注意作者的假设和局限，判断论证是否有说服力，就是批判性阅读。'),
         ('Finally, summarise what you have read.', '最后一段讲用自己的话写摘要来检验是否读懂，Finally 表示最后一条。'),
     ]},
    {'title': 'How the Weekend Began', 'text': '''The weekend seems like a natural part of life, but it is a relatively recent invention. {1}

In many traditional societies, work followed the seasons rather than the calendar. Farmers worked long hours during planting and harvest and rested when the weather made work impossible. {2}

The industrial revolution changed this. Factories ran on fixed schedules, and workers were expected to be present six days a week, often for more than twelve hours a day. {3}

In nineteenth-century Britain, many workers simply did not turn up on Mondays, a habit known as "Saint Monday". Factory owners eventually offered a half-day off on Saturday in exchange for reliable attendance on Monday. {4}

The full two-day weekend spread in the twentieth century. In the 1920s, some American manufacturers introduced a five-day week, partly in the belief that workers with more free time would buy more goods. {5} By the middle of the century, the Saturday-Sunday weekend had become standard in much of the world.''',
     'bank': ['For most of human history, there was no fixed period of rest at the end of each week.',
              'Religious holidays, rather than a regular weekly break, provided most of their days off.',
              'Unsurprisingly, workers looked for ways to take time back.', 'This compromise was the first step towards the modern weekend.',
              'Other employers followed, and laws later limited the working week.', 'Farmers were the first to demand a two-day weekend.',
              'Today, many people work on Saturdays and Sundays as well.'],
     'items': [
         ('For most of human history, there was no fixed period of rest at the end of each week.', '空前说周末是较新的发明，这句接着说人类历史上大部分时间没有固定的周末。'),
         ('Religious holidays, rather than a regular weekly break, provided most of their days off.', '本段讲传统社会按季节而不是日历干活，这句补充他们休息靠宗教节日。'),
         ('Unsurprisingly, workers looked for ways to take time back.', '空前说工厂要求一周六天、每天十二小时以上，下一段讲工人周一干脆不来上班，这句承上启下。'),
         ('This compromise was the first step towards the modern weekend.', '空前讲工厂主用周六半天假换周一按时上班，This compromise 指的就是这个交换。'),
         ('Other employers followed, and laws later limited the working week.', '空前说一些美国厂商实行五天工作制，空后说到世纪中叶已成标准，中间是“别的雇主跟进、法律限制工时”。'),
     ]},
    {'title': 'Two Languages, No Confusion', 'text': '''Parents raising children with two languages are sometimes told that they are making a mistake. {1} Decades of research, however, suggest that these fears are largely unfounded.

It is true that bilingual children sometimes mix their languages, using a word from one in a sentence of the other. {2} Bilingual adults do the same thing, often deliberately, and children's mixing follows grammatical rules rather than being random.

Another common worry is that learning two languages slows development. {3} But when both languages are counted together, bilingual children know as many words as their monolingual peers, and they reach major milestones, such as first words and first sentences, at the same ages.

{4} Some studies have found that bilingual children are better at switching between tasks and ignoring irrelevant information, perhaps because they constantly manage two language systems. These findings are still debated, and the size of the advantage may be smaller than once claimed.

What matters most is not whether a child hears one language or two, but how much rich, meaningful input they receive. {5} Parents should therefore use the language in which they feel most comfortable and expressive.''',
     'bank': ['Two languages, they are warned, will confuse the child and delay speech.',
              'This is not a sign of confusion, but a normal part of bilingual development.',
              'In each single language, a bilingual child may know fewer words than a monolingual child.',
              'There may even be some cognitive benefits.', 'Children learn best from caregivers who speak to them warmly and often.',
              'Most bilingual children eventually forget one of their languages.',
              'Experts therefore recommend that parents choose only one language.'],
     'items': [
         ('Two languages, they are warned, will confuse the child and delay speech.', '空前说有人告诉父母这样做是错的，这句具体说出他们的担心；空后 these fears 指的就是这些担心。'),
         ('This is not a sign of confusion, but a normal part of bilingual development.', '空前承认孩子会混用两种语言，空后说成年人也这样，而且混用有规律，这句是转折：混用不代表混乱。'),
         ('In each single language, a bilingual child may know fewer words than a monolingual child.', '空后 But when both languages are counted together ... 与“只算一种语言时词汇量较少”构成对比。'),
         ('There may even be some cognitive benefits.', '空后说双语儿童更擅长切换任务、忽略无关信息，正是“认知上的好处”。'),
         ('Children learn best from caregivers who speak to them warmly and often.', '空前说最重要的是输入的多少和质量，空后 therefore 说父母用自己最自在的语言，这句是中间的理由。'),
     ]},
    {'title': 'The Habit Loop', 'text': '''Every day, we perform hundreds of actions without thinking about them: brushing our teeth, locking the door, checking our phones. {1} Understanding how they work can help us build good ones and break bad ones.

Psychologists describe habits as a loop with three parts. {2} The routine is the behaviour itself, and the reward is the benefit we get from it, which teaches the brain that the loop is worth remembering.

{3} When a behaviour is repeated in the same context, control gradually shifts to parts of the brain that operate automatically. This frees the conscious mind for other tasks, which is why habits are so efficient, and so hard to change.

Because the cue triggers the routine automatically, willpower alone is often not enough to break a bad habit. {4} Someone who snacks while watching television, for example, might keep healthy food within reach instead of crisps.

Building a new habit takes time. {5} Missing a single day does not seem to matter much; what counts is returning to the routine consistently until it becomes automatic.''',
     'bank': ['These automatic behaviours are habits, and they shape much of our lives.', 'The cue is the trigger that tells the brain to start the behaviour.',
              'Repetition is what turns an action into a habit.', 'A more effective approach is to change the cue or replace the routine.',
              'One study found that it took participants an average of about two months.', 'Most habits are formed in a single day.',
              'Rewards, however, have little effect on behaviour.'],
     'items': [
         ('These automatic behaviours are habits, and they shape much of our lives.', '空前列举不假思索的动作，这句点明它们就是习惯；空后 they 指习惯。'),
         ('The cue is the trigger that tells the brain to start the behaviour.', '空前说习惯循环有三部分，空后讲了 routine 和 reward，缺的是第一部分 cue。'),
         ('Repetition is what turns an action into a habit.', '空后说同一情境下反复做，控制权会转到自动运行的脑区，这句是本段主旨。'),
         ('A more effective approach is to change the cue or replace the routine.', '空前说光靠意志力不够，空后举例把健康食品放在手边，就是换掉触发物或行为。'),
         ('One study found that it took participants an average of about two months.', '空前说养成新习惯需要时间，这句用研究给出具体时长。'),
     ]},
]

# ============================================================ 专四 (B2)

TEM4_CLOZE = [
    {'title': 'The Art of Apologising', 'text': '''Saying sorry seems simple, yet many apologies fail. A common mistake is to {1} the apology with an excuse: "I'm sorry I was late, but the traffic was terrible." The word "but" tends to {2} everything that came before it, and the listener hears only the excuse.

An effective apology, {3} contrast, begins by naming the specific mistake. "I'm sorry I kept you waiting for forty minutes" shows that the speaker understands what went wrong. It should also {4} the effect on the other person: "I know you had to rush to the meeting because of me."

Next comes responsibility. People often {5} phrases such as "mistakes were made", which avoid saying who made them. A sincere apology uses "I" and does not shift the {6} onto circumstances or other people.

Finally, a good apology looks {7}. Offering to put things right, or explaining how you will avoid the same mistake, shows that your words are more than a {8} formality.

Research suggests that a well-made apology can do more than repair a single relationship. It can also {9} trust, because it shows that the person apologising is willing to admit faults. {10}, it is one of the most useful social skills we can learn.''',
     'items': [
         ('follow|precede|compare|share', 'follow A with B 在 A 之后接 B：例句先道歉、后找借口；precede 是“在前”，与例句顺序相反。'),
         ('cancel|repeat|support|explain', '后文说听的人只听见了借口，所以 but 会“抵消”前面的道歉。'),
         ('by|at|on|for', 'by contrast 相比之下，固定搭配；与上段失败的道歉对比。'),
         ('acknowledge|deny|hide|delay', '例句“我知道你因为我不得不赶去开会”，是在“承认”对对方造成的影响。'),
         ('hide behind|look into|stand for|run out of', '“错误已经发生”这类说法回避了是谁犯的错，人们借此推脱：hide behind 以……为挡箭牌。'),
         ('blame|cost|light|truth', 'shift the blame onto ... 把责任推给……'),
         ('forward|back|down|away', '后文讲提出弥补、说明以后如何避免，都是“向前看”。'),
         ('mere|serious|legal|rare', 'more than a mere formality 不只是走形式。'),
         ('rebuild|lose|test|break', '好的道歉能修复关系，也能“重建”信任，because 后说明它显示了认错的意愿。'),
         ('In short|However|Instead|Otherwise', '最后一句总结全文：In short 总之。'),
     ]},
    {'title': 'Silence in Conversation', 'text': '''How long can a silence last before it becomes uncomfortable? The answer {1} on where you are. Studies of conversation suggest that in some cultures, a pause of more than a second or so feels awkward, and speakers rush to {2} it. In others, longer silences are common and carry no negative {3}.

In Finland and Japan, for example, silence is often seen as a sign of {4}. Pausing before answering shows that you are thinking carefully about what the other person has said. Speaking too quickly, by {5}, may suggest that you were not really listening.

Such differences can cause misunderstandings when people from different backgrounds meet. A speaker who is {6} to short pauses may interpret a long silence as disagreement or boredom, and fill it with more talk. The other person, meanwhile, may feel {7} and wonder why they are never given a chance to speak.

Being aware of these patterns can make intercultural communication {8}. It helps to remember that silence is not {9} empty; it may be full of thought, respect or simply comfort in another person's company. Learning to {10} silence, rather than fear it, is part of learning to communicate across cultures.''',
     'items': [
         ('depends|insists|takes|lives', 'depend on 取决于：答案取决于你在哪里，下文讲不同文化。'),
         ('fill|keep|enjoy|hear', '停顿让人尴尬，说话人急着“填补”它；下文 fill it with more talk 呼应。'),
         ('meaning|sound|price|reason', 'carry no negative meaning 不带负面含义。'),
         ('respect|weakness|anger|failure', '后文说停顿表示你在认真想对方的话，是“尊重”；末段 full of thought, respect 呼应。'),
         ('contrast|chance|heart|mistake', 'by contrast 相反：说得太快反而显得没认真听。'),
         ('used|close|kind|new', 'be used to ... 习惯于：习惯短停顿的人会把长沉默理解为不同意或无聊。'),
         ('interrupted|welcomed|praised|relaxed', '对方一直插话填满沉默，另一方会觉得“被打断”，总没有机会说话。'),
         ('smoother|harder|shorter|louder', '了解这些差异能让跨文化交流更“顺畅”。'),
         ('necessarily|hardly|rarely|seldom', 'not necessarily 不一定：沉默不一定是空洞的。hardly 等与 not 连用构成双重否定。'),
         ('appreciate|avoid|break|explain', 'rather than fear it 与之相对：学会“欣赏”沉默，而不是害怕它。'),
     ]},
]

TEM4_CHOICE = [
    {'title': '第一组', 'items': [
        ('Hardly ____ the station when the train began to move.', 'had we reached|we had reached|did we reach|we reached',
         'Hardly ... when ... 一……就……：hardly 放句首要部分倒装，且前半句用过去完成时。'),
        ('It is essential that every student ____ the safety rules before using the lab.', 'follow|follows|will follow|followed',
         'It is essential that ... 从句用 (should) + 动词原形。'),
        ('The manager, together with his assistants, ____ expected to arrive this afternoon.', 'is|are|were|have been',
         'together with ... 不影响主语的数，谓语跟 The manager 一致，用单数。'),
        ('I would have called you yesterday if I ____ your number.', 'had had|had|have had|would have',
         '与过去事实相反的虚拟条件句：从句用过去完成时，主句用 would have done。'),
        ('____ from the top of the hill, the town looks like a painting.', 'Seen|Seeing|To see|Having seen',
         '小镇是“被看”的，用过去分词 Seen 作状语。'),
        ('She is one of the few students who ____ passed the exam with full marks.', 'have|has|is|was',
         '定语从句修饰 students（复数），谓语用复数 have；was passed 是被动，意思不对。'),
        ('The new policy will ____ effect from next Monday.', 'take|make|have|put', 'take effect 生效，固定搭配。'),
        ('We must ____ the possibility that the data are wrong.', 'allow for|make up|put off|give in', 'allow for 考虑到、把……考虑在内。'),
        ('His explanation was so ____ that nobody could understand it.', 'vague|precise|clear|simple', '没人能听懂，说明解释“含糊”。'),
        ('Not until he lost his job ____ how important it was to him.', 'did he realise|he realised|he did realise|had he realised',
         'Not until 放句首，主句部分倒装；“意识到”发生在失业之时，用一般过去时。'),
    ]},
    {'title': '第二组', 'items': [
        ('The meeting ____ by the time we got there.', 'had already finished|already finished|has already finished|was already finishing',
         'by the time + 一般过去时，主句用过去完成时：我们到之前会议已经结束。'),
        ('It was not until midnight ____ the last guest left.', 'that|when|before|since', 'It was not until ... that ... 强调句型。'),
        ('____ how busy she is, she still finds time to read every day.', 'No matter|Whatever|Although|Unless',
         'no matter how + 形容词 无论多么……，引导让步状语。'),
        ('The book is well worth ____.', 'reading|to read|being read|to be read', 'be worth doing 值得做，用主动形式表被动意义。'),
        ("I'd rather you ____ anything about it to her for now.", "didn't say|don't say|won't say|haven't said",
         'would rather + 从句，用过去时表示对现在或将来的愿望。'),
        ('Little ____ that his decision would change the future of the company.', 'did he know|he knew|he did know|knew he',
         'Little 是否定意义的词，放句首要部分倒装。'),
        ('The doctor advised him to ____ smoking.', 'give up|give in|give off|give out', 'give up 戒掉；give in 让步，give off 散发，give out 分发。'),
        ('The two sisters are so ____ that people often mix them up.', 'alike|like|likely|liking', 'alike 相像的，作表语；like 是介词，后面要接宾语。'),
        ('Please ____ me when you arrive at the airport.', 'notify|notice|note|nominate', 'notify sb 通知某人；notice 是注意到。'),
        ('The film was ____ boring that many people left halfway through.', 'so|such|too|very', 'so + 形容词 + that ...；such 后接名词。'),
    ]},
]

# ============================================================ 专八 (C1)

TEM8_CHOICE = [
    {'title': '第一组', 'items': [
        ("The committee's report was ____ criticised for ignoring the views of local residents.", 'roundly|roughly|readily|rarely',
         'roundly criticised 受到严厉批评，固定搭配；roughly 是“大约”。'),
        ('Had it not been for her timely help, the project ____.', 'would have failed|would fail|had failed|failed',
         '省略 if 的虚拟倒装（If it had not been for ...），与过去事实相反，主句用 would have done。'),
        ('The evidence, ____ convincing, was not enough to secure a conviction.', 'while|despite|since|unless',
         'while 引导让步状语“虽然有说服力”，省略了 it was；despite 是介词，不能接形容词。'),
        ('His remarks were deliberately ____, leaving the audience unsure of his real position.', 'ambiguous|explicit|concise|offensive',
         '听众弄不清他的真实立场，说明话说得“模棱两可”。'),
        ('The government is under pressure to ____ the rising cost of housing.', 'address|attend|deal|cope',
         'address 处理、应对，及物动词直接接宾语；attend、deal、cope 都要加介词。'),
        ('So little ____ about the disease that doctors could do nothing.', 'was known|known was|was it known|it was known',
         'So little 放句首，部分倒装；句子本身是被动语态 little was known，倒装后为 So little was known。'),
        ('It is high time that we ____ action to protect the wetlands.', 'took|take|will take|have taken',
         'It is high time that ... 从句用过去时，表示早该做了。'),
        ("The novelist's later works are ____ by a growing sense of loss.", 'pervaded|persuaded|perceived|performed',
         'pervade 弥漫、贯穿：后期作品充满失落感。'),
        ('Few people, ____ the experts, predicted the crisis.', 'least of all|much more|still more|above all',
         'least of all 尤其不：几乎没人预见到危机，专家更没有。用在否定意义的句子里。'),
        ('The proposal was rejected on the ____ that it would cost too much.', 'grounds|bases|reasons|causes',
         'on the grounds that ... 以……为理由，固定搭配。'),
    ]},
    {'title': '第二组', 'items': [
        ('She has a remarkable ____ for languages, picking up new ones with ease.', 'aptitude|attitude|altitude|appetite',
         'aptitude for ... 在……方面的天资；后文“轻松学会新语言”说的是能力。'),
        ('Not a single word ____ during the entire meeting.', 'did he say|he said|said he|he did say',
         'Not a single ... 否定词组放句首，部分倒装。'),
        ('The two theories, ____ different in their assumptions, lead to similar conclusions.', 'though|for|as if|once',
         'though 引导省略的让步状语（though they are different），与后面“结论相似”转折。'),
        ("The minister refused to ____ to the protesters' demands.", 'yield|resist|reject|oppose',
         'yield to 屈服于；resist、reject、oppose 都是及物动词，不接 to。'),
        ('The scandal has seriously ____ public confidence in the bank.', 'undermined|underlined|undertaken|underestimated',
         'undermine confidence 削弱信心。'),
        ('____ permitting, the ceremony will be held outdoors.', 'Weather|The weather is|If weather|Weather is',
         'Weather permitting 天气允许的话，独立主格结构，固定说法。'),
        ('He is not so much a teacher ____ a friend to his students.', 'as|than|but|like', 'not so much A as B 与其说是 A，不如说是 B。'),
        ("The results were ____ with those of earlier studies, which strengthened the researchers' confidence.",
         'consistent|constant|considerate|continual', 'be consistent with ... 与……一致；一致才会增强信心。'),
        ('____ in 1990, the museum now attracts a million visitors a year.', 'Founded|Founding|Having founded|To found',
         '博物馆是“被建立”的，用过去分词 Founded 作状语。'),
        ('There is no ____ in arguing with him; he never changes his mind.', 'point|reason|way|cause',
         'There is no point in doing ... 做……没有意义。'),
    ]},
]

TEM8_PROOF = [
    {'title': 'Learning a Language as an Adult', 'items': [
        ('It is widely believed that children learn languages more easy than adults.', 'easy', 'easily', '修饰动词 learn 要用副词：more easily。'),
        ('While this is true for pronunciation, adults have several advantage of their own.', 'advantage', 'advantages', 'several 后接可数名词复数。'),
        ('Adults can draw on what they already know about grammar, that helps them', 'that', 'which', '非限制性定语从句（前有逗号）不能用 that，要用 which。'),
        ('understand new structures quickly. They also tend to be more discipline,', 'discipline', 'disciplined', 'be more + 形容词：disciplined 自律的；discipline 是名词或动词。'),
        ('setting clear goals and study regularly. What adults often lack is not', 'study', 'studying', '与 setting 并列作伴随状语，要用 studying。'),
        ('ability but time. Busy with work and family, many give up after only a little months.', 'little', 'few', 'months 是可数名词复数，用 a few；a little 修饰不可数名词。'),
        ('Research suggests that success depends less on age than in the amount', 'in', 'on', 'depend less on A than on B，两个 on 对应。'),
        ('of practice. An adult who studies for an hour every day will usually makes', 'makes', 'make', '情态动词 will 后接动词原形。'),
        ('faster progress than a child who attends a weekly class. The key is to making learning', 'making', 'make', 'be to do 作表语，to 后接动词原形 make。'),
        ('part of daily life, rather than treat it as an occasionally hobby.', 'occasionally', 'occasional', '修饰名词 hobby 要用形容词 occasional。'),
    ]},
    {'title': 'Handwriting in a Digital Age', 'items': [
        ('In an age of keyboards and touchscreens, handwriting may seem old-fashion.', 'old-fashion', 'old-fashioned', '形容词是 old-fashioned（过时的）。'),
        ('Many schools now spend fewer time teaching it, and some adults rarely', 'fewer', 'less', 'time 在这里不可数，用 less；fewer 修饰可数名词复数。'),
        ('pick up a pen at all. Yet researchers have found what writing by hand has benefits', 'what', 'that', 'found 后的宾语从句结构完整、不缺成分，用 that。'),
        ('that typing cannot easily replaced. When students take notes by hand, they', 'replaced', 'replace', '情态动词 cannot 后接动词原形；replace 的宾语是前面的 benefits。'),
        ('cannot write down every word, so they have to listen careful and decide', 'careful', 'carefully', '修饰动词 listen 要用副词 carefully。'),
        ('what is important. This process of selecting and summarising help them', 'help', 'helps', '主语是 This process（单数），谓语用 helps。'),
        ('understand the material more deeply. In one study, students who took handwriting notes', 'handwriting', 'handwritten', '修饰 notes 用过去分词形容词 handwritten（手写的）。'),
        ('performed better on questions requiring understanding than that who typed.', 'that', 'those', '指代前面的 students（复数），用 those who ...。'),
        ('Handwriting also appears to help young children learn to read, because form each letter', 'form', 'forming', 'because 引导的从句需要主语，动名词 forming each letter 作主语。'),
        ('helps them remember its shape. None of this means we should abandon technology; it simply suggest that the pen still deserves a place.', 'suggest', 'suggests', '主语 it 是第三人称单数，谓语用 suggests。'),
    ]},
]

# ============================================================ 雅思 (B2)

IELTS_TFNG = [
    {'title': "The Honeybee's Dance", 'text': '''Honeybees live in colonies that can contain tens of thousands of individuals. To feed the colony, worker bees must find flowers that may be several kilometres from the hive. Remarkably, a bee that discovers a good source of food can tell its nestmates exactly where to find it, using a behaviour known as the waggle dance.

The dance was first decoded in the 1940s by the Austrian scientist Karl von Frisch, who later shared a Nobel Prize for his work. He observed that a returning forager runs in a straight line while shaking its body from side to side, then loops back and repeats the movement. The direction of the straight run indicates the direction of the food relative to the sun. The length of time the bee spends waggling indicates the distance: the longer the waggle, the farther away the food.

Other bees follow the dancer closely, picking up both the information and the scent of the flowers on its body. They then leave the hive and fly directly towards the food source. Experiments have shown that most bees recruited in this way find the food, although some need several attempts.

The dance is not used for every trip. When food is very close to the hive, bees perform a simpler "round dance", which tells others that food is nearby but gives no information about direction.

Scientists continue to study the waggle dance. Recent research suggests that young bees are not born knowing how to dance accurately; their dances become more precise as they gain experience by watching older bees.''',
     'items': [
         ('A honeybee colony may include more than ten thousand bees.', 'T', 'colonies that can contain tens of thousands of individuals', ''),
         ('Karl von Frisch received a Nobel Prize for this work on his own.', 'F', 'who later shared a Nobel Prize for his work', ' shared 是与人共享，不是独自获得。'),
         ('The direction of the waggle run shows other bees which way to fly in relation to the sun.', 'T', 'The direction of the straight run indicates the direction of the food relative to the sun.', ''),
         ('A shorter waggle means that the food is farther from the hive.', 'F', 'the longer the waggle, the farther away the food', ' 摆动越长食物越远，题目说反了。'),
         ('Bees prefer flowers with a strong scent.', 'NG', '', '原文只说跟随的蜜蜂会闻到舞者身上的花香，没有说蜜蜂偏爱香味浓的花。'),
         ('The round dance tells other bees which direction to fly.', 'F', 'gives no information about direction', ''),
         ('Older bees dance more often than young bees.', 'NG', '', '原文只说年轻蜜蜂的舞蹈随着经验变得更准确，没有比较跳舞的次数。'),
     ]},
    {'title': 'A Short History of the Umbrella', 'text': '''Umbrellas have a surprisingly long history. The earliest known examples appear in art from ancient Egypt, Assyria and China, where they were used mainly to provide shade from the sun rather than protection from rain. In many of these societies, umbrellas were a symbol of status, and only kings, nobles or religious leaders were allowed to be shaded by one.

Waterproof umbrellas are believed to have been developed in China, where paper umbrellas were coated with oil or wax to keep out the rain. The idea spread slowly westwards. In Europe, umbrellas were used for shade in Italy and France by the sixteenth century, but they were widely regarded as an accessory for women.

In England, the traveller Jonas Hanway is often credited with making the umbrella acceptable for men. In the 1750s he began carrying one in the streets of London, and for years he was laughed at by passers-by. Coach drivers, who earned money by carrying people through the rain, were particularly hostile, as they saw the umbrella as a threat to their business.

By the time Hanway died in 1786, however, umbrellas had become a common sight. Early models were heavy, with frames made of wood or whalebone. In 1852, Samuel Fox introduced a design with a steel frame, which was lighter and stronger, and versions of his design are still in use today.''',
     'items': [
         ('In ancient times, umbrellas were mainly used to keep off the rain.', 'F', 'they were used mainly to provide shade from the sun rather than protection from rain', ''),
         ('Ordinary people in some ancient societies were not allowed to use umbrellas.', 'T', 'only kings, nobles or religious leaders were allowed to be shaded by one', ''),
         ('Chinese paper umbrellas were made waterproof with oil or wax.', 'T', 'paper umbrellas were coated with oil or wax to keep out the rain', ''),
         ('Umbrellas reached Italy before they reached France.', 'NG', '', '原文只说到十六世纪意大利和法国都已经用伞遮阳，没说哪个国家先有。'),
         ('Jonas Hanway was the first man in England to carry an umbrella.', 'NG', '', '原文说他“常被认为让男人打伞变得可以接受”，没有说他是第一个打伞的男人。'),
         ('Coach drivers welcomed the umbrella.', 'F', 'were particularly hostile', ' 马车夫对伞非常敌视，因为伞威胁到他们的生意。'),
         ("Samuel Fox's steel frame made umbrellas lighter.", 'T', 'a design with a steel frame, which was lighter and stronger', ''),
     ]},
    {'title': 'How Animals Sleep', 'text': '''All animals that have been carefully studied appear to sleep in some form, but the way they do so varies enormously. Giraffes in the wild may sleep for less than two hours a day, often in short naps of a few minutes, while some bats sleep for up to twenty hours.

Body size offers part of the explanation. Large plant-eating animals need to spend much of their day feeding, and they are also at risk from predators, so long periods of deep sleep would be dangerous. Small animals, by contrast, use energy quickly and may save energy by sleeping for longer.

Some animals have found remarkable ways to sleep without losing awareness. Dolphins, which must regularly swim to the surface to breathe, can rest one half of the brain at a time while the other half stays alert. Some birds do the same during long flights across oceans, sleeping for only a few seconds at a time.

Scientists are still debating why sleep is necessary at all. One theory is that sleep allows the brain to remove waste products that build up during waking hours. Another is that it helps to strengthen memories. These explanations are not mutually exclusive, and sleep may serve several purposes.

What is clear is that sleep loss has serious effects. In laboratory studies, rats that were prevented from sleeping for long periods became ill. Humans who are short of sleep show poorer concentration, slower reactions and a greater risk of accidents.''',
     'items': [
         ('Wild giraffes may sleep for under two hours in a day.', 'T', 'Giraffes in the wild may sleep for less than two hours a day', ''),
         ('Large plant-eaters sleep deeply for long periods to save energy.', 'F', 'so long periods of deep sleep would be dangerous', ''),
         ('Small animals generally live longer than large ones.', 'NG', '', '原文说小动物用能量快、可能睡得更久，没有提到寿命。'),
         ('Dolphins can keep part of their brain awake while resting.', 'T', 'can rest one half of the brain at a time while the other half stays alert', ''),
         ('Birds sleep for several hours at a time during long flights.', 'F', 'sleeping for only a few seconds at a time', ''),
         ('Scientists agree on a single reason why sleep is needed.', 'F', 'Scientists are still debating why sleep is necessary at all.', ''),
         ('Rats that had been kept awake recovered quickly once they were allowed to sleep.', 'NG', '', '原文只说长期不让睡觉的老鼠生病了，没有说让它们睡觉以后的情况。'),
     ]},
]

IELTS_HEADINGS = [
    {'title': 'Coffee: From Plant to Cup', 'paras': [
        'Coffee grows best in a narrow band around the equator, sometimes called the "bean belt". The plants need steady temperatures, regular rainfall and, for the finest varieties, high altitudes. Frost can destroy a crop overnight, which is why coffee is rarely grown far from the tropics.',
        'Although we speak of coffee "beans", they are in fact the seeds of a red fruit known as a cherry. On many small farms the cherries are still picked by hand, because they do not all ripen at the same time. Pickers may return to the same plant several times during a harvest.',
        'Once picked, the fruit must be removed from the seeds. In the "dry" method, cherries are spread out in the sun for several weeks before the dried fruit is stripped away. In the "wet" method, the fruit is removed by machine and the seeds are left to ferment in water. Each method gives the coffee a different flavour.',
        'Green coffee seeds have almost none of the taste or aroma we associate with coffee. These develop only during roasting, when the seeds are heated to around 200°C. Within minutes, hundreds of chemical reactions take place, and the seeds turn brown and release their familiar smell.',
        'Despite the high prices paid in cafés, most coffee farmers earn very little. A large share of the final price goes to traders, roasters and retailers. Fair-trade schemes try to address this by guaranteeing farmers a minimum price, though critics question how much difference they make.',
        'Climate change poses a growing threat to the industry. Rising temperatures and changing rainfall patterns are already reducing yields in some regions, and one study predicts that the area suitable for growing coffee could halve by 2050.',
        'In response, scientists are searching for new varieties that can survive in hotter conditions. Some are studying wild coffee species from African forests, many of which have never been grown commercially, in the hope that their genes will help protect the crop.'],
     'bank': ['Where coffee can be grown', 'A fruit that ripens unevenly', 'Two ways of separating seed from fruit', 'How heat creates flavour',
              'An unfair share of the profits', 'A shrinking area for cultivation', 'Looking to the wild for solutions',
              'The health benefits of coffee', 'How coffee spread around the world', 'The rise of coffee shop culture'],
     'items': [
         ('Where coffee can be grown', 'Coffee grows best in a narrow band around the equator'),
         ('A fruit that ripens unevenly', 'because they do not all ripen at the same time'),
         ('Two ways of separating seed from fruit', 'Once picked, the fruit must be removed from the seeds.'),
         ('How heat creates flavour', 'These develop only during roasting'),
         ('An unfair share of the profits', 'most coffee farmers earn very little'),
         ('A shrinking area for cultivation', 'the area suitable for growing coffee could halve by 2050'),
         ('Looking to the wild for solutions', 'Some are studying wild coffee species from African forests'),
     ]},
    {'title': 'Why We Laugh', 'paras': [
        'Laughter is often thought of as a response to jokes, but research suggests that this is only a small part of the story. When scientists recorded people\'s everyday conversations, they found that most laughter followed ordinary remarks such as "See you later" or "I know", rather than anything particularly funny.',
        'Laughter appears to be much older than language. Chimpanzees, gorillas and other great apes produce a breathy panting sound when they are tickled or playing, and researchers believe human laughter evolved from this kind of play signal millions of years ago.',
        'One of the main functions of laughter seems to be social. People are around thirty times more likely to laugh when they are with others than when they are alone. Laughing together signals friendliness and helps to build and maintain relationships.',
        'Laughter is also highly contagious. Simply hearing someone laugh activates areas of the brain involved in movement, preparing us to join in. This may explain why television comedies have long used recorded laughter to encourage viewers to laugh along.',
        'There is some evidence that laughter benefits the body. Studies have found that a good laugh can increase tolerance of pain, possibly by triggering the release of the brain\'s natural painkillers. However, many claims about the health effects of laughter are based on small studies and should be treated with caution.',
        'Not all laughter is the same. Listeners can usually tell the difference between genuine, spontaneous laughter and laughter that is produced deliberately to be polite. Genuine laughter tends to be longer, higher in pitch and harder to control.',
        'Finally, what people laugh at differs between cultures and changes over time. Humour often depends on shared knowledge and values, which is why jokes are notoriously difficult to translate and why comedy from the past can seem puzzling today.'],
     'bank': ['Laughter without jokes', 'Roots in animal play', 'A way of bonding with others', 'Why laughter spreads', 'Possible effects on pain',
              'Real and polite laughter', 'Humour varies across societies and eras', 'Why some people never laugh', 'The best jokes of all time',
              'Laughter as a cure for serious illness'],
     'items': [
         ('Laughter without jokes', 'most laughter followed ordinary remarks'),
         ('Roots in animal play', 'human laughter evolved from this kind of play signal'),
         ('A way of bonding with others', 'Laughing together signals friendliness and helps to build and maintain relationships.'),
         ('Why laughter spreads', 'Laughter is also highly contagious.'),
         ('Possible effects on pain', 'a good laugh can increase tolerance of pain'),
         ('Real and polite laughter', 'Listeners can usually tell the difference between genuine, spontaneous laughter and laughter that is produced deliberately to be polite.'),
         ('Humour varies across societies and eras', 'what people laugh at differs between cultures and changes over time'),
     ]},
    {'title': 'Saving a Language', 'paras': [
        'Of the roughly seven thousand languages spoken in the world today, linguists estimate that around forty per cent are endangered. Many have only a few hundred speakers, most of them elderly, and some could disappear within a generation.',
        'Languages usually decline when parents stop passing them on to their children. This often happens because another language offers better access to education and jobs. Over time, young people may come to see the old language as a sign of poverty or backwardness.',
        'The loss is not only cultural. Each language contains knowledge built up over centuries, including names for local plants and animals and ways of describing the environment that may not exist in any other language. When a language disappears, much of this knowledge can be lost with it.',
        'Yet decline is not always permanent. Hebrew, which had not been used as an everyday spoken language for centuries, was revived in the late nineteenth and twentieth centuries and is now spoken by millions of people. Welsh and Maori have also seen their numbers of speakers grow after long periods of decline.',
        'Successful revival programmes tend to have certain features in common. One of the most effective is the "language nest", in which young children spend their days with fluent speakers, often elderly members of the community, hearing and using only the endangered language.',
        'Technology is increasingly playing a part. Recordings, online dictionaries and mobile apps allow learners to hear fluent speakers even when none live nearby. However, experts stress that technology cannot replace a community of people who actually use the language in daily life.'],
     'bank': ['A widespread threat', 'Why families stop using a language', 'More than words are lost', 'Languages that came back',
              'Learning from elders in early childhood', 'Useful tools, but no substitute for speakers', 'How languages first began',
              "The world's most widely spoken languages", 'Laws against minority languages'],
     'items': [
         ('A widespread threat', 'around forty per cent are endangered'),
         ('Why families stop using a language', 'Languages usually decline when parents stop passing them on to their children.'),
         ('More than words are lost', 'Each language contains knowledge built up over centuries'),
         ('Languages that came back', 'was revived in the late nineteenth and twentieth centuries'),
         ('Learning from elders in early childhood', 'young children spend their days with fluent speakers, often elderly members of the community'),
         ('Useful tools, but no substitute for speakers', 'technology cannot replace a community of people who actually use the language in daily life'),
     ]},
]

# ============================================================ every exam, two types each

_RAW = {
    'zk': [('cloze', '完形填空', 'cloze', 'cloze', ZK_CLOZE), ('dialog', '补全对话', 'bank', 'dialog', ZK_DIALOG)],
    'gk': [('seven', '七选五', 'bank', 'seven', GK_SEVEN), ('cloze', '完形填空', 'cloze', 'cloze', GK_CLOZE)],
    'cet4': [('banked', '选词填空', 'bank', 'banked', CET4_BANKED), ('match', '段落匹配', 'match', 'match', CET4_MATCH)],
    'cet6': [('banked', '选词填空', 'bank', 'banked', CET6_BANKED), ('match', '段落匹配', 'match', 'match', CET6_MATCH)],
    'ky': [('cloze', '完形填空', 'cloze', 'cloze', KY_CLOZE), ('newtype', '新题型（七选五）', 'bank', 'newtype', KY_NEW)],
    'tem4': [('cloze', '完形填空', 'cloze', 'cloze', TEM4_CLOZE), ('choice', '语法与词汇', 'choice', 'choice', TEM4_CHOICE)],
    'tem8': [('proof', '改错', 'proof', 'proof', TEM8_PROOF), ('choice', '语言知识', 'choice', 'choice', TEM8_CHOICE)],
    'ielts': [('tfng', 'True / False / Not Given', 'tfng', 'tfng', IELTS_TFNG), ('headings', '段落标题匹配', 'headings', 'headings', IELTS_HEADINGS)],
}
TYPES = {exam: [_build(exam, tid, title, kind, HOW[how], sets) for tid, title, kind, how, sets in types] for exam, types in _RAW.items()}
