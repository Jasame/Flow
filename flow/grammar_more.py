"""Grammar beyond the first 18 subskills: 26 more teaching points in 13 topics, A2 to C1.

Each point has the same parts as content_subskills.PAGES (goal, steps, contrast, pitfalls, a guided exercise and a
clue) and four verification questions for the published question bank, so the classic site, the Flow knowledge graph,
the AI writing coach (which tags problems with these ids) and the evidence model all see them. install() adds the
topics, subskills, questions and graph nodes once (migration 'grammar-2.0').

examples() finds sentences in a material that show a point, with conservative patterns: a sentence is only tagged
when the form is unambiguous (had + past participle, ", which", so … that). Points that appear in almost every
sentence (articles, plain prepositions) are tagged only by their clearest forms. The text says "读到过" (met), never
"learned": exposure is all a match can show.

All teaching text here is original and awaits human language review, like content_subskills.
"""
import json
import re

TOPICS_MORE = [
    # id, title, summary, lesson, example, explanation, prerequisite topics (the classic topics table)
    ('voice', '被动语态', '动作的承受者作主语时怎么说。', '被动语态 = be + 过去分词；时态体现在 be 上。', 'The bridge was built in 1990.', 'was built 是一般过去时的被动。', ['tense']),
    ('modal', '情态动词', '能力、义务、建议与推测。', '情态动词后接动词原形；谈过去的推测或后悔用“情态动词 + have done”。', 'You should have asked first.', 'should have done 表示本该做却没做。', ['tense']),
    ('determiner', '冠词与数量', '名词前面放什么词。', '先判断名词可数还是不可数、泛指还是特指，再选冠词和数量词。', 'I need some advice about the job.', 'advice 不可数，用 some，不说 an advice。', []),
    ('compare', '比较', '比较两者或更多。', '两者用比较级 + than，多者用 the + 最高级，程度相同用 as … as。', 'This is the most useful app I have.', '在多个之中比较，用最高级。', []),
    ('link', '连接与衔接', '把句子连成有逻辑的段落。', '先判断逻辑（转折、因果、目的），再看后面接句子还是名词。', 'Despite the rain, the match went ahead.', 'despite 后接名词。', ['clause']),
    ('prep', '介词', '时间、地点与固定搭配。', '时间地点按“点、面或某天、空间或时段”选 at、on、in；固定搭配整体记。', 'She is good at explaining things.', 'good at + doing。', []),
    ('emphasis', '强调与倒装', '突出重点的高级句式。', '用强调句突出某个成分，用倒装加强否定或限制的语气。', 'Not only did he apologise, but he also paid for the damage.', 'Not only 放在句首时要倒装。', ['clause']),
]

# Flow's order of the 13 topics on the knowledge graph (next_service.TOPICS)
TOPIC_ORDER = [('tense', '时态'), ('voice', '被动语态'), ('modal', '情态动词'), ('clause', '从句'), ('conditional', '条件'),
               ('subjunctive', '虚拟'), ('nonfinite', '非谓语'), ('agreement', '主谓一致'), ('determiner', '冠词与数量'),
               ('compare', '比较'), ('link', '连接与衔接'), ('prep', '介词'), ('emphasis', '强调与倒装')]


def _n(id, topic, title, prereq, level, lesson, example, goal, steps, contrast, pitfalls, guided, clue, questions, note):
    return {'id': id, 'topic': topic, 'title': title, 'prereq': prereq, 'level': level, 'lesson': lesson, 'example': example,
            'page': {'goal': goal, 'steps': steps, 'contrast': contrast, 'pitfalls': pitfalls, 'guided': guided, 'clue': clue, 'extension': None},
            'questions': questions, 'note': note}


def _g(prompt, options, answer, scaffold, explanation):
    return {'prompt': prompt, 'options': options, 'answer': answer, 'scaffold': scaffold, 'explanation': explanation}


NODES_MORE = [
    # ---------------- tense ----------------
    _n('tense-future', 'tense', '将来的几种说法', 'tense-present', 'A2',
       '临时决定、预测用 will；早有打算或有迹象用 be going to；安排好的事常用现在进行时。', "Look at those clouds. It's going to rain.",
       '根据“临时决定、早有打算、已经安排、眼前迹象”选对将来的说法。',
       ['说话时临时做的决定、承诺、提议用 will：The phone is ringing. I’ll get it.',
        '之前已经打算好的事用 be going to：I’m going to study abroad next year.',
        '眼前有迹象表明马上会发生，也用 be going to：Watch out! You’re going to fall.',
        '已经约好、安排好的事（时间、地点、对象都定了）常用现在进行时：I’m meeting Anna at six.'],
       [('I’ll help you with that bag.', '临时提出帮忙'), ('I’m going to paint my room this weekend.', '早有的打算'), ('We’re flying to Shanghai on Friday.', '机票已订，安排好了')],
       [('I will to call you later.', 'I will call you later.', 'will 后直接接动词原形，不加 to。'),
        ('When I will arrive, I’ll text you.', 'When I arrive, I’ll text you.', 'when、if、as soon as 引导的时间或条件从句里，用一般现在时表示将来。'),
        ('Look at the sky! It will rain.', 'Look at the sky! It’s going to rain.', '有眼前的迹象作依据时，用 be going to 更自然。')],
       _g('"I’ve lost my key." "Don’t worry, I ____ you mine."', ['lend', 'will lend', 'am lending', 'lent'], 1, '这是说话时临时提出的帮助。', '临时决定、主动提出帮忙，用 will lend。'),
       '这件事是现在临时决定的、早就打算好的，还是已经安排好的？',
       [("I've already bought the paint. I ____ the kitchen this weekend.", ['will paint', 'am going to paint', 'paint', 'painted'], 1, '已经买好油漆，说明早有打算，用 be going to。'),
        ('We ____ dinner with our clients at seven tonight; the table is booked.', ['have', 'are having', 'will have had', 'had'], 1, '时间、对象都已安排好，用现在进行时表示将来的安排。'),
        ('As soon as she ____, we will start the meeting.', ['will arrive', 'arrives', 'arrived', 'is going to arrive'], 1, 'as soon as 引导时间状语从句，用一般现在时表示将来。'),
        ('"It\'s hot in here." "OK, I ____ the window."', ['open', 'will open', 'opened', 'have opened'], 1, '说话时临时决定，用 will open。')],
       'will / be going to 表示将来'),
    _n('tense-past-perfect', 'tense', '过去完成时', 'tense-perfect', 'B1',
       '讲过去的两件事时，用 had done 标出更早发生的那一件。', 'When we got to the station, the train had already left.',
       '在讲述过去时，用过去完成时交代“更早”的事，让先后顺序清楚。',
       ['形式：had + 过去分词，所有主语都用 had。',
        '先找“过去的参照点”：When we arrived…、By the time…、before…',
        '比参照点更早发生的动作用 had done：By the time I woke up, everyone had gone out.',
        '按发生顺序讲两件事时，两个一般过去时就够了：I finished my work and went home.'],
       [('When I arrived, she left.', '我到了，她才走（先后紧接）'), ('When I arrived, she had left.', '我到的时候她已经走了'), ('I realised I had forgotten my phone.', '忘带手机发生在意识到之前')],
       [('I had visited Beijing last year.', 'I visited Beijing last year.', '只讲一件过去的事、没有更早的参照，用一般过去时即可。'),
        ('By the time we arrived, the film already started.', 'By the time we arrived, the film had already started.', 'by the time 提示“在那之前已经”，用 had started。'),
        ('She told me she has finished.', 'She told me she had finished.', '主句是过去时，从句里更早完成的事用 had finished。')],
       _g('When the firefighters arrived, the fire ____ out.', ['already went', 'has already gone', 'had already gone', 'goes'], 2, '消防员到达是过去的参照点，火是在那之前就熄灭的。', '比过去参照点更早发生，用过去完成时 had already gone。'),
       '有没有一个过去的参照时间？这件事比它更早吗？',
       [("I couldn't get into the flat because I ____ my keys at the office.", ['left', 'had left', 'have left', 'was leaving'], 1, '把钥匙落在办公室发生在“进不去”之前，用 had left。'),
        ('By the time the doctor came, the patient ____ better.', ['already felt', 'has already felt', 'had already felt', 'feels'], 2, 'by the time 引出过去的参照点，在那之前已经好转，用 had felt。'),
        ('She ____ in Paris for five years before she moved to Berlin.', ['lives', 'has lived', 'had lived', 'is living'], 2, 'before she moved 是过去参照点，在那之前住了五年，用 had lived。'),
        ('He was nervous because he ____ on a plane before.', ['never was', 'had never been', 'has never been', 'never is'], 1, '紧张发生在过去，在那之前从没坐过飞机，用 had never been。')],
       'had + 过去分词：比过去某个时间更早'),
    _n('tense-perfect-continuous', 'tense', '现在完成进行时', 'tense-perfect', 'B2',
       'have been doing 强调动作从过去一直持续到现在，或刚停下、留下了痕迹。', "I've been waiting for an hour.",
       '区分强调“结果或数量”的现在完成时和强调“持续过程”的现在完成进行时。',
       ['形式：have / has been + doing。',
        '强调持续了多久（for、since、how long、all day）：She has been studying since breakfast.',
        '解释眼前的痕迹：Your eyes are red. Have you been crying?',
        '说完成了多少用现在完成时：I’ve read 50 pages.',
        'know、believe、own 等表示状态的动词不用进行体：I’ve known her for years.'],
       [('I have been writing emails all morning.', '强调整个上午一直在写'), ('I have written ten emails this morning.', '强调完成的数量'), ('The streets are wet. It has been raining.', '刚停，留下了痕迹')],
       [('I have been knowing him since 2019.', 'I have known him since 2019.', 'know 是状态动词，不用进行体。'),
        ('I have been reading three books this month.', 'I have read three books this month.', '说完成了多少本，用现在完成时。'),
        ('How long are you learning English?', 'How long have you been learning English?', '问“到现在为止持续多久”，用现在完成进行时。')],
       _g('You look tired. ____ all night?', ['Did you work', 'Have you been working', 'Are you working', 'Had you worked'], 1, '看到“累”这个痕迹，问的是刚才一直在做什么。', '用现在完成进行时解释眼前的痕迹。'),
       '强调持续的过程，还是完成的结果或数量？',
       [("They ____ about the plan for two hours and still haven't agreed.", ['argue', 'have been arguing', 'argued', 'had argued'], 1, 'for two hours 且仍在争论，用现在完成进行时。'),
        ('She ____ four reports since Monday.', ['has been writing', 'has written', 'is writing', 'writes'], 1, '说完成的数量（四份），用现在完成时。'),
        ('"Why are your hands so dirty?" "I ____ in the garden."', ['have been working', 'work', 'will work', 'had worked'], 0, '解释眼前的痕迹，用现在完成进行时。'),
        ('I ____ Maria since we were at school.', ['have been knowing', 'have known', 'know', 'am knowing'], 1, 'know 是状态动词，不用进行体，用 have known。')],
       'have / has been + doing：一直持续到现在'),
    # ---------------- voice ----------------
    _n('voice-basic', 'voice', '被动语态的构成与使用', 'tense-present', 'A2',
       '主语是动作的承受者时用 be + 过去分词；不知道、不重要或不必说是谁做的时候常用被动。', 'English is spoken in many countries.',
       '判断主语是动作的执行者还是承受者，选对主动或被动。',
       ['被动语态 = be + 过去分词，be 随时态和主语变化：is made、was made、are made。',
        '主语是动作的承受者时用被动：The window was broken.（窗户被打破）',
        '执行者不清楚或不重要时省略；需要说明时用 by：The song was written by a student.',
        'happen、arrive、disappear 等不及物动词没有被动：The accident happened at night.'],
       [('The chef cooks the meals.', '主动：厨师做饭'), ('The meals are cooked by the chef.', '被动：饭由厨师做'), ('The museum was opened in 1990.', '只关心开馆时间，不说是谁')],
       [('The accident was happened at night.', 'The accident happened at night.', 'happen 是不及物动词，没有被动。'),
        ('This bridge built in 1990.', 'This bridge was built in 1990.', '被动不能缺 be 动词。'),
        ('The letter was wrote by Tom.', 'The letter was written by Tom.', '被动用过去分词 written，不用过去式。')],
       _g('Paper ____ from wood.', ['makes', 'is made', 'made', 'is making'], 1, '纸是被制造的，而且这是一般事实。', '主语是承受者且是一般事实，用一般现在时的被动 is made。'),
       '主语是在做这个动作，还是被做？',
       [('Thousands of cars ____ in this factory every year.', ['produce', 'are produced', 'produced', 'are producing'], 1, '汽车是被生产的，用 are produced。'),
        ('My phone ____ last night, so I have to buy a new one.', ['stole', 'was stolen', 'was stealing', 'has stolen'], 1, '手机是被偷的，昨晚发生，用 was stolen。'),
        ('What ____ at the meeting yesterday?', ['was happened', 'happened', 'was happen', 'is happened'], 1, 'happen 是不及物动词，没有被动。'),
        ('The windows ____ every Monday.', ['clean', 'are cleaned', 'cleaned', 'are cleaning'], 1, '窗户是被擦的，每周一次，用 are cleaned。')],
       'be + 过去分词：主语是动作的承受者'),
    _n('voice-tenses', 'voice', '各种时态里的被动', 'voice-basic', 'B1',
       '被动的时态由 be 体现：has been done、is being done、will be done、must be done。', 'The road is being repaired.',
       '在完成时、进行时、将来时和情态动词中正确构成被动。',
       ['现在完成时的被动：have / has been + done：All the tickets have been sold.',
        '进行时的被动：am / is / are / was / were being + done：The room is being cleaned.',
        '将来和情态动词的被动：will / can / must / should + be + done：The work must be finished today.',
        '先确定时态，再把 be 放进这个时态，最后接过去分词。'],
       [('They are repairing the road.', '主动进行时'), ('The road is being repaired.', '被动进行时'), ('The results will be announced next week.', '将来的被动')],
       [('The house is building now.', 'The house is being built now.', '房子是被建造，被动进行时是 is being built。'),
        ('The report must finish by Friday.', 'The report must be finished by Friday.', '报告是被完成的，情态动词后用 be done。'),
        ('All the cake has eaten.', 'All the cake has been eaten.', '现在完成时的被动要有 been。')],
       _g('Don’t sit there! The bench ____.', ['is painting', 'is being painted', 'has painted', 'paints'], 1, '长椅正在“被”刷漆。', '此刻正在进行的被动用 is being painted。'),
       '先定时态，再看主语是不是动作的承受者。',
       [('This novel ____ into more than 30 languages so far.', ['has translated', 'has been translated', 'is translating', 'translated'], 1, 'so far 用现在完成时，小说是被翻译的。'),
        ('The new hospital ____ next year.', ['will build', 'will be built', 'is built', 'builds'], 1, '医院是被建造的，明年，用 will be built。'),
        ('Phones ____ during the exam.', ['must not use', 'must not be used', 'must not using', 'not must be used'], 1, '手机是被使用的，情态动词后用 be used。'),
        ('When I got there, the patient ____ by two doctors.', ['was examining', 'was being examined', 'is examined', 'has examined'], 1, '过去某时正在被检查，用 was being examined。')],
       '完成、进行、将来或情态动词里的被动'),
    _n('voice-causative', 'voice', 'have / get something done', 'voice-tenses', 'B2',
       'have / get + 宾语 + 过去分词：请别人替你做某事，或某事发生在自己身上。', 'I had my hair cut yesterday.',
       '用 have / get something done 说“请别人替你做”和“遭遇某事”。',
       ['结构：have / get + 物 + 过去分词：We’re having the kitchen painted.',
        '意思是别人替你做，不是你自己做：I cut my hair（自己剪）≠ I had my hair cut（理发师剪）。',
        '也可以表示不好的遭遇：He had his bike stolen.',
        'get 更口语；have 可以用在各种时态里：I need to get my eyes tested.'],
       [('I repaired my car.', '我自己修的'), ('I had my car repaired.', '找人修的'), ('She had her bag stolen on the train.', '包被偷了（遭遇）')],
       [('I had cut my hair yesterday.', 'I had my hair cut yesterday.', '宾语要放在 have 和过去分词之间。'),
        ('We are having our house paint.', 'We are having our house painted.', '宾语后用过去分词。'),
        ('I must get checked my eyes.', 'I must get my eyes checked.', '结构是 get + 宾语 + done。')],
       _g('My watch is broken. I need to ____.', ['repair it', 'have it repaired', 'have repaired it', 'have it repair'], 1, '是请别人修：宾语放中间，后面用过去分词。', 'have it repaired：请别人把手表修好。'),
       '是自己做，还是请别人做、或发生在自己身上？宾语放在哪里？',
       [('We ____ a new air conditioner installed next week.', ['are having', 'are installing', 'have', 'are had'], 0, '请人来装，结构是 have + 物 + installed。'),
        ('She got her photo ____ for the new passport.', ['take', 'taking', 'taken', 'to take'], 2, 'get + 宾语 + 过去分词。'),
        ('Which sentence means that a mechanic fixed the car?', ['I fixed my car.', 'I had my car fixed.', 'I had fixed my car.', 'My car fixed.'], 1, 'had my car fixed：请别人修。'),
        ('He ____ his wallet stolen while he was travelling.', ['had', 'made', 'let', 'did'], 0, 'have + 宾语 + done 也可以表示不好的遭遇。')],
       'have / get + 宾语 + 过去分词：请人做或遭遇'),
    # ---------------- modal ----------------
    _n('modal-ability', 'modal', '能力与许可', None, 'A2',
       'can / could 表示能力和许可；要用在 will、have 等后面时，用 be able to。', "I can swim now, but I couldn't swim when I was five.",
       '表达能力、许可和请求，选对 can、could、be able to、may。',
       ['现在的能力用 can；过去一般的能力用 could：She could read when she was four.',
        '过去某一次“设法做成了”用 was / were able to：The fire was big, but everyone was able to escape.',
        '将来和完成时里用 be able to：I’ll be able to help tomorrow.',
        '请求和许可：Can I…? 比较随意；Could I…? / May I…? 更礼貌。'],
       [('I can’t come today.', '现在不能来'), ('I won’t be able to come tomorrow.', '将来不能，用 be able to'), ('Could you close the door, please?', '礼貌的请求')],
       [('I will can help you.', 'I will be able to help you.', '两个情态动词不能连用，用 be able to。'),
        ('She can speaks French.', 'She can speak French.', '情态动词后接动词原形。'),
        ('He cans swim.', 'He can swim.', '情态动词没有第三人称单数的变化。')],
       _g('I haven’t ____ sleep well since I moved here.', ['can', 'could', 'been able to', 'be able'], 2, 'haven’t 后面需要过去分词形式。', '完成时里用 been able to。'),
       '是现在、过去还是将来？是能力还是请求？',
       [('Next year, the baby ____ walk.', ['can', 'will be able to', 'could', 'is able'], 1, '将来的能力用 will be able to。'),
        ('____ I borrow your pen, please?', ['Must', 'May', 'Should', 'Need'], 1, '礼貌地请求许可用 May I…?'),
        ('When he was young, he ____ climb trees very fast.', ['can', 'could', 'is able to', 'will be able to'], 1, '过去一般的能力用 could。'),
        ('The exam was hard, but I ____ answer every question in time.', ['could', 'was able to', 'can', 'am able'], 1, '过去某一次设法做成，用 was able to。')],
       'can / could / be able to：能力或许可'),
    _n('modal-obligation', 'modal', '必须、禁止、不必与建议', 'modal-ability', 'A2',
       'must / have to 表示必须；mustn’t 是禁止，don’t have to 是不必；should 是建议。', "You mustn't park here, but you don't have to pay.",
       '分清必须、禁止、不必和建议。',
       ['must：说话人认为必须；have to：规定或客观情况要求：I have to wear a uniform at work.',
        'mustn’t = 不允许、禁止：You mustn’t smoke here.',
        'don’t have to / don’t need to = 没必要，做不做都可以。',
        'should / ought to 用来提建议：You should see a doctor.',
        '过去的“必须”用 had to（must 没有过去式）。'],
       [('You mustn’t tell anyone.', '禁止告诉别人'), ('You don’t have to tell anyone.', '不告诉也可以'), ('You should tell someone.', '建议告诉')],
       [('Yesterday I must work late.', 'Yesterday I had to work late.', 'must 没有过去式，用 had to。'),
        ('You mustn’t come if you are busy.', 'You don’t have to come if you are busy.', '“不必来”用 don’t have to，mustn’t 是禁止。'),
        ('You should to rest.', 'You should rest.', 'should 后直接接动词原形。')],
       _g('It’s Saturday tomorrow, so I ____ get up early.', ['mustn’t', 'don’t have to', 'shouldn’t to', 'haven’t'], 1, '周六不是“禁止早起”，而是“没必要”。', '不必用 don’t have to。'),
       '是必须、禁止、不必，还是建议？',
       [("You ____ touch that wire. It's dangerous!", ["don't have to", "mustn't", "needn't", "don't need"], 1, '危险，禁止触碰，用 mustn’t。'),
        ('The meeting was cancelled, so we ____ prepare the slides.', ["didn't have to", "mustn't", 'had to', 'must'], 0, '会议取消，所以不必准备，过去用 didn’t have to。'),
        ('Last year she ____ take the bus to work because her car broke down.', ['must', 'had to', 'has to', 'must have'], 1, '过去的“必须”用 had to。'),
        ('You look pale. You ____ go home and rest.', ['should', "mustn't", "don't have to", 'had to'], 0, '给建议用 should。')],
       'must / have to / should：义务或建议'),
    _n('modal-deduction', 'modal', '对现在的推测', 'modal-obligation', 'B1',
       'must be 几乎肯定是；might / may / could be 可能是；can’t be 不可能是。', "She's not answering. She must be busy.",
       '根据证据的强弱，用合适的情态动词推测现在的情况。',
       ['证据很强、几乎肯定：must + 动词原形：He’s been working all day; he must be tired.',
        '有可能但不确定：might / may / could：She might be in the library.',
        '几乎肯定不是：can’t / couldn’t：That can’t be Tom. He’s in London.',
        '推测正在进行的事：must / might be doing：They must be having dinner.'],
       [('The lights are on. They must be at home.', '很有把握'), ('They might be at home.', '不确定'), ('They can’t be at home; their car is gone.', '几乎肯定不在')],
       [('He mustn’t be hungry; he just ate.', 'He can’t be hungry; he just ate.', '否定的推测用 can’t，mustn’t 是禁止。'),
        ('She must is tired.', 'She must be tired.', '情态动词后用动词原形 be。'),
        ('Maybe he can be at work.', 'He might be at work.', '肯定句里表示“可能”用 might、may 或 could。')],
       _g('Someone is knocking. It ____ the delivery; I ordered a parcel this morning.', ['can’t be', 'must be', 'mustn’t be', 'couldn’t be'], 1, '早上刚下单，证据很强。', '很有把握的推测用 must be。'),
       '证据有多强？是肯定、可能，还是不可能？',
       [("That ____ be Anna's car. She sold it last month.", ['must', "can't", 'might', 'should'], 1, '车已经卖了，几乎肯定不是，用 can’t。'),
        ("I'm not sure where Leo is. He ____ be at the gym.", ['must', "can't", 'might', "mustn't"], 2, '不确定，用 might。'),
        ("You've been travelling for 20 hours. You ____ be exhausted.", ["can't", 'must', "mustn't", "needn't"], 1, '证据很强，几乎肯定，用 must。'),
        ('Listen! The neighbours ____ a party.', ['must have', 'must be having', "can't have", 'might has'], 1, '推测此刻正在进行，用 must be doing。')],
       'must / might / can’t be：对现在的推测'),
    _n('modal-past', 'modal', '对过去的推测与后悔', 'modal-deduction', 'B2',
       '情态动词 + have done 谈过去：must have done 一定做了，can’t have done 不可能做了，should have done 本该做却没做。', 'You should have told me earlier.',
       '用“情态动词 + have done”推测过去，或表达后悔、批评。',
       ['对过去的肯定推测：must have done：The ground is wet; it must have rained.',
        '对过去的否定推测：can’t / couldn’t have done：She can’t have seen me.',
        '对过去的可能：might / may / could have done：I might have left it on the bus.',
        '本该做而没做：should have done；本不该做却做了：shouldn’t have done。',
        '本来可以但没做：could have done：You could have asked for help.'],
       [('He must have missed the train.', '推测他错过了火车'), ('He should have left earlier.', '批评：本该早点出门'), ('He could have taken a taxi.', '本来可以打车，但没打')],
       [('She must have went home.', 'She must have gone home.', 'have 后用过去分词。'),
        ('He mustn’t have seen us.', 'He can’t have seen us.', '对过去的否定推测用 can’t have done。'),
        ('I should studied harder.', 'I should have studied harder.', '后悔过去的事用 should have done。')],
       _g('I can’t find my umbrella. I ____ it at the restaurant.', ['might leave', 'might have left', 'should leave', 'can’t have leave'], 1, '推测的是过去发生的事，而且不确定。', '对过去的不确定推测用 might have left。'),
       '说的是过去的事吗？是推测、后悔，还是批评？',
       [('The window is broken. Someone ____ it with a ball.', ['must hit', 'must have hit', 'should have hit', "can't have hit"], 1, '对过去的肯定推测用 must have done。'),
        ('I failed the test. I ____ more.', ['should have revised', 'must have revised', 'can have revised', 'should revise'], 0, '后悔过去没做，用 should have done。'),
        ('She ____ the email; she was on holiday with no internet.', ["can't have read", 'must have read', 'should have read', 'might read'], 0, '对过去的否定推测用 can’t have done。'),
        ('Why did you walk home in the rain? You ____ me; I would have picked you up.', ['could have called', 'must have called', "can't have called", 'should call'], 0, '本来可以却没做，用 could have done。')],
       '情态动词 + have done：对过去的推测或遗憾'),
    # ---------------- clause ----------------
    _n('clause-nondefining', 'clause', '非限制性定语从句', 'clause-relative', 'B2',
       '用逗号隔开的 which / who 从句只是补充信息，去掉后句子照样成立；不能用 that。', 'My sister, who lives in Hangzhou, is a nurse.',
       '分清“限定是哪一个”的定语从句和“顺便补充”的非限制性定语从句。',
       ['非限制性定语从句用逗号和主句隔开；去掉它，主句意思不变。',
        '指人用 who，指物用 which；不能用 that，也不能省略关系词。',
        'which 还可以指前面整句话：He passed the exam, which surprised everyone.',
        '先行词已经是独一无二的（专有名词、my mother）时，只能用非限制性从句。'],
       [('The students who passed the test got a certificate.', '只有通过的那些学生拿到证书'), ('The students, who passed the test, got a certificate.', '学生都通过了，也都拿到证书'), ('She missed the bus, which made her late.', 'which 指前面整件事')],
       [('My father, that works in a bank, is retiring.', 'My father, who works in a bank, is retiring.', '非限制性定语从句不能用 that。'),
        ('Beijing which is the capital of China is huge.', 'Beijing, which is the capital of China, is huge.', '专有名词后的补充信息要用逗号隔开。'),
        ('He won the prize, it surprised us.', 'He won the prize, which surprised us.', '两个句子不能只靠逗号连接；用 which 指代前一句。')],
       _g('The Great Wall, ____ is thousands of kilometres long, attracts millions of visitors.', ['that', 'which', 'where', 'what'], 1, '有逗号隔开，先行词是物。', '非限制性定语从句指物用 which，不能用 that。'),
       '有没有逗号？去掉这部分，主句还成立吗？',
       [('Our manager, ____ has worked here for 20 years, is leaving.', ['that', 'who', 'which', 'whom'], 1, '逗号隔开，指人且作主语，用 who。'),
        ('The train was cancelled, ____ meant we had to take a taxi.', ['that', 'what', 'which', 'it'], 2, 'which 指代前面整件事，非限制性从句不用 that。'),
        ('I gave the book to Tom, ____ had asked to borrow it.', ['which', 'that', 'who', 'whose'], 2, '指人，逗号隔开，用 who。'),
        ('Which sentence says that ALL her friends live abroad?', ['Her friends who live abroad call her often.', 'Her friends, who live abroad, call her often.', 'Her friends that live abroad call her often.', 'Her friends living abroad call her often.'], 1, '加逗号的非限制性从句是对“她所有朋友”的补充说明。')],
       ', which / , who：补充说明，去掉也成立'),
    _n('clause-reported', 'clause', '间接引语', 'clause-noun', 'B1',
       '转述别人的话时，引述动词是过去时，从句的时态、人称和时间地点词通常往后退一步。', 'She said (that) she was tired.',
       '把直接引语改成间接引语时，调整好时态、人称和语序。',
       ['引述动词是过去时（said、told）时，从句时态常后移：am → was，will → would，have done → had done。',
        '人称和时间地点词跟着换：I → he / she，today → that day，tomorrow → the next day，here → there。',
        'told 后面要接人：She told me…；said 后面不直接接人：She said (to me)…',
        '转述疑问句用 if / whether 或疑问词，并用陈述语序：He asked where I lived.',
        '内容到现在仍然成立时可以不后移：He said the earth goes round the sun.'],
       [('"I’m busy," Tom said.', '直接引语'), ('Tom said he was busy.', '间接引语，时态后移'), ('She asked me if I could help.', '转述一般疑问句用 if')],
       [('He said me that he was late.', 'He told me that he was late.', 'say 后不直接接人；要接人用 tell。'),
        ('She asked me where did I live.', 'She asked me where I lived.', '转述的疑问句用陈述语序。'),
        ('He said he will call me tomorrow.', 'He said he would call me the next day.', '引述动词是过去时，will 后移为 would，tomorrow 改为 the next day。')],
       _g('"I will finish it tomorrow," she said. → She said she ____ it the next day.', ['will finish', 'would finish', 'finishes', 'had finish'], 1, '引述动词 said 是过去时，will 要往后退一步。', 'will 在间接引语里后移为 would。'),
       '引述动词是不是过去时？从句的时态、人称、时间词跟着调整了吗？',
       [('"I am working from home," Lisa said. → Lisa said she ____ from home.', ['is working', 'was working', 'has worked', 'works'], 1, 'am working 后移为 was working。'),
        ('He asked me ____.', ['where was the station', 'where the station was', 'where is the station', 'the station was where'], 1, '转述的疑问句用陈述语序。'),
        ('My teacher ____ me that my essay was too long.', ['said', 'told', 'spoke', 'talked'], 1, '后面直接接人，用 told。'),
        ('"Have you finished?" she asked. → She asked ____ finished.', ['have I', 'if I had', 'that I have', 'did I'], 1, '一般疑问句用 if 转述，时态后移，陈述语序。')],
       '转述别人的话：时态和人称往后退'),
    # ---------------- subjunctive ----------------
    _n('subjunctive-wish', 'subjunctive', 'wish、if only 与 it’s time', 'subjunctive-now', 'B2',
       'wish / if only 后面的时态往过去退一步，表示和事实相反的愿望。', 'I wish I knew the answer.',
       '用 wish、if only、it’s time 表达和事实不同的愿望或建议。',
       ['对现在的愿望：wish + 过去式（be 常用 were）：I wish I were taller.',
        '对过去的遗憾：wish + had done：I wish I had studied harder.',
        '希望别人改变（常带不满）：wish + 主语 + would do：I wish you would stop talking.',
        'It’s (high) time + 主语 + 过去式：It’s time we left.'],
       [('I wish I had more time.', '现在时间不够'), ('I wish I had taken the job.', '过去没接受，现在后悔'), ('I hope I get the job.', 'hope 说有可能的事，不用虚拟')],
       [('I wish I can speak French.', 'I wish I could speak French.', 'wish 表示现在不能实现的愿望，can 退为 could。'),
        ('I wish I didn’t eat so much last night.', 'I wish I hadn’t eaten so much last night.', '对过去的遗憾用 had done。'),
        ('I wish you will pass the exam.', 'I hope you pass the exam.', '对有可能实现的好事用 hope，不用 wish。')],
       _g('It’s raining again. I wish it ____ so much here.', ['doesn’t rain', 'didn’t rain', 'won’t rain', 'hasn’t rained'], 1, '这是对现在情况的相反愿望。', 'wish 表达对现在的相反愿望，用过去式 didn’t rain。'),
       '愿望是关于现在、过去，还是希望别人改变？',
       [('I missed the concert. If only I ____ the tickets earlier!', ['booked', 'had booked', 'would book', 'book'], 1, '对过去的遗憾用 had done。'),
        ("It's late. It's time we ____ home.", ['go', 'went', 'will go', 'have gone'], 1, "it's time + 主语 + 过去式。"),
        ('She wishes she ____ closer to her office; the commute takes two hours.', ['lives', 'lived', 'will live', 'has lived'], 1, '对现在的相反愿望用过去式。'),
        ('I ____ you enjoy your trip to Japan next month!', ['wish', 'hope', 'would rather', 'if only'], 1, '对将来可能的好事用 hope。')],
       'wish / if only：和事实相反的愿望'),
    # ---------------- nonfinite ----------------
    _n('nonfinite-clause', 'nonfinite', '分词作状语', 'nonfinite-participle', 'B2',
       '用 doing、done、having done 开头的短语代替时间或原因从句；它的逻辑主语必须是主句的主语。', 'Feeling tired, she went to bed early.',
       '读懂并写对分词状语，避免“垂悬分词”。',
       ['分词短语的逻辑主语就是主句主语：Walking home, I met an old friend.（是“我”在走路）',
        '主动、同时发生用 doing；被动用 done：Seen from the hill, the city looks small.',
        '先完成、再做另一件事用 having done：Having finished the report, he went for lunch.',
        '否定把 not 放在分词前面：Not knowing what to say, she kept quiet.'],
       [('Opening the door, I saw a cat.', '我开门（主动、同时）'), ('Built in 1900, the bridge is still in use.', '桥被建造（被动）'), ('Having lost my key, I had to wait outside.', '先丢了钥匙，然后在外面等')],
       [('Walking into the room, the lights went out.', 'As I walked into the room, the lights went out.', '灯不会走进房间，分词的逻辑主语必须是主句主语。'),
        ('Writing in 1850, the novel is still popular.', 'Written in 1850, the novel is still popular.', '小说是“被写”的，用过去分词。'),
        ('Not knew the answer, he guessed.', 'Not knowing the answer, he guessed.', '分词状语用 doing，否定的 not 放在前面。')],
       _g('____ the email, she closed her laptop.', ['Sent', 'Having sent', 'Being sent', 'To have sent'], 1, '先发完邮件，再合上电脑；发邮件的是她。', '先完成的主动动作用 having done。'),
       '分词的动作是谁做的？是主动还是被动，同时还是先后？',
       [('____ by the noise, the baby started to cry.', ['Waking', 'Woken', 'Having woken', 'To wake'], 1, '婴儿是被吵醒的，用过去分词。'),
        ('____ the map carefully, we found the shortest route.', ['Studied', 'Studying', 'To be studied', 'Being studied'], 1, '“我们”主动研究地图，用 doing。'),
        ('Which sentence is correct?', ['Running for the bus, my bag fell off.', 'Running for the bus, I dropped my bag.', 'Run for the bus, I dropped my bag.', 'Ran for the bus, I dropped my bag.'], 1, '跑着赶车的是“我”，分词的逻辑主语和主句主语一致。'),
        ('____ what to do, he asked his teacher for advice.', ['Not knowing', 'Knowing not', 'Not known', 'No knowing'], 0, '否定的分词状语：Not + doing。')],
       '分词短语作状语：主语和主句一致'),
    # ---------------- determiner ----------------
    _n('det-article', 'determiner', 'a / an 与 the', None, 'A2',
       '第一次提到、泛指“一个”用 a / an；双方都知道是哪一个、独一无二或再次提到时用 the。', 'I bought a book. The book is about space.',
       '根据“对方知不知道你指的是哪一个”选 a / an 还是 the。',
       ['可数名词单数第一次出现、对方不知道是哪一个：a / an：I saw a dog in the park.',
        '再次提到、上下文已经确定、独一无二：the：The dog was very friendly. / the sun。',
        'a 还是 an 看读音而不是字母：an hour，an MBA，a university，a one-way ticket。',
        '序数词、最高级和 only 前面用 the：the first time，the best idea。'],
       [('Can you open a window?', '随便哪扇都行'), ('Can you open the window?', '指我们都知道的那扇'), ('She is an honest person.', 'honest 以元音音素开头，用 an')],
       [('She is engineer.', 'She is an engineer.', '可数名词单数前要有冠词；说职业用 a / an。'),
        ('It was a best day of my life.', 'It was the best day of my life.', '最高级前用 the。'),
        ('I waited for a hour.', 'I waited for an hour.', 'hour 的 h 不发音，以元音音素开头，用 an。')],
       _g('I had ____ interview yesterday. ____ interview went well.', ['a / The', 'an / The', 'an / An', 'the / A'], 1, 'interview 以元音音素开头；第二次提到时已经确定是哪一次。', '第一次 an interview，第二次 the interview。'),
       '对方知道你指的是哪一个吗？名词以什么音开头？',
       [('My sister works at ____ university in Wuhan.', ['a', 'an', 'the', '/'], 0, 'university 以 /j/ 音开头，用 a；第一次提到。'),
        ('This is ____ only photo I have of my grandfather.', ['a', 'an', 'the', '/'], 2, 'only 前用 the。'),
        ('There is ____ cat in our garden. ____ cat is black.', ['a / A', 'the / A', 'a / The', 'the / The'], 2, '第一次 a cat，再次提到 the cat。'),
        ('He wants to be ____ actor.', ['a', 'an', 'the', '/'], 1, 'actor 以元音音素开头，说职业用 an。')],
       'a / an 与 the：泛指还是特指'),
    _n('det-zero', 'determiner', '零冠词与泛指', 'det-article', 'B1',
       '泛指一类事物时，复数名词和不可数名词前不加冠词；特指时才用 the。', 'Dogs are loyal. The dogs next door bark all night.',
       '分清“泛指一类”和“特指这一些”，不多加也不漏加 the。',
       ['泛指一类：复数或不可数名词不用冠词：Music helps me relax. / Children need sleep.',
        '特指（有修饰语限定或上下文已确定）：用 the：The music in this café is too loud.',
        '三餐、球类、学科、语言前一般不加冠词：have lunch，play football，study history。',
        '一些固定说法不加冠词：go to school / bed / work，by bus，at home。'],
       [('Life is short.', '泛指“人生”'), ('The life of a doctor is busy.', '特指“医生的生活”'), ('I go to bed at eleven.', '固定说法，不加冠词')],
       [('The money is not everything.', 'Money is not everything.', '泛指的不可数名词不加 the。'),
        ('I like the cats.', 'I like cats.', '泛指一类动物用复数，不加 the。'),
        ('We have the dinner at seven.', 'We have dinner at seven.', '三餐前一般不加冠词。')],
       _g('____ water is essential for ____ life.', ['The / the', '/ / /', 'A / the', 'The / /'], 1, '这里泛指水和生命，不是特定的某杯水。', '泛指的不可数名词前不加冠词。'),
       '是在说一整类事物，还是特定的那些？',
       [('____ smartphones have changed the way we live.', ['The', 'A', 'An', '/'], 3, '泛指一类事物的复数名词不加冠词。'),
        ('Could you pass me ____ salt, please?', ['/', 'a', 'the', 'an'], 2, '餐桌上双方都知道的那瓶盐，特指用 the。'),
        ('She plays ____ piano, and her brother plays ____ basketball.', ['the / /', '/ / the', 'the / the', 'a / a'], 0, '乐器前常用 the，球类前不加冠词。'),
        ('I usually go to ____ work by ____ bus.', ['the / the', '/ / /', 'a / a', 'the / /'], 1, 'go to work、by bus 是固定说法，不加冠词。')],
       '泛指一类时不加冠词'),
    _n('det-quantity', 'determiner', '可数、不可数与数量词', None, 'A2',
       'many、few、a few 修饰可数名词；much、little、a little 修饰不可数名词；a few / a little 是“有一些”，few / little 是“几乎没有”。', 'I have a few friends here, but little free time.',
       '判断名词可数还是不可数，并选对 many、much、few、little 等数量词。',
       ['不可数名词没有复数、不和 a 连用：advice，information，furniture，homework，news。',
        '可数复数用 many、(a) few、a number of；不可数用 much、(a) little、an amount of。',
        'a lot of、lots of、some、any 两种都能用。',
        'a few / a little 偏肯定（有一些）；few / little 偏否定（几乎没有）。'],
       [('She has a few close friends.', '有几个，不算少'), ('She has few close friends.', '几乎没有'), ('Can you give me some advice?', 'advice 不可数，不说 an advice')],
       [('He gave me many useful informations.', 'He gave me a lot of useful information.', 'information 不可数，没有复数，不用 many。'),
        ('How much people came?', 'How many people came?', 'people 是可数复数，用 many。'),
        ('I bought two furnitures.', 'I bought two pieces of furniture.', 'furniture 不可数，用 pieces of 计数。')],
       _g('Hurry up! We don’t have ____ time.', ['many', 'much', 'few', 'a few'], 1, 'time 在这里指时间，不可数，而且是否定句。', '不可数名词的否定句用 much。'),
       '这个名词能不能数？说话人觉得多还是少？',
       [("There isn't ____ milk left in the fridge.", ['many', 'much', 'a few', 'few'], 1, 'milk 不可数，否定句用 much。'),
        ('Very ____ students knew the answer, so the teacher explained it again.', ['little', 'few', 'much', 'a little'], 1, 'students 可数，“几乎没有”用 few。'),
        ('Let me give you ____ advice: start early.', ['an', 'a piece of', 'many', 'a few'], 1, 'advice 不可数，用 a piece of 计数。'),
        ('I still have ____ money, so I can buy you a coffee.', ['a little', 'a few', 'few', 'many'], 0, 'money 不可数，“还有一些”用 a little。')],
       '数量词：可数还是不可数、多还是少'),
    # ---------------- compare ----------------
    _n('compare-basic', 'compare', '比较级与最高级', None, 'A2',
       '两者比较用比较级 + than；三者及以上用 the + 最高级 + in / of。', "This phone is cheaper than that one, but it isn't the best.",
       '写对比较级和最高级，并知道什么时候用 than、the、in / of。',
       ['单音节词加 -er / -est：cheap → cheaper → the cheapest；重读闭音节单辅音结尾要双写：big → bigger。',
        '多音节词用 more / most：more expensive，the most interesting。',
        '不规则变化：good → better → best，bad → worse → worst，far → further / farther。',
        '范围用 in（地点、集体）或 of（同类）：the tallest in my class，the best of the three。'],
       [('Tom is taller than Sam.', '两人比较'), ('Tom is the tallest in the team.', '在一群人里最高'), ('This test was more difficult than the last one.', '多音节词用 more')],
       [('This is more cheaper.', 'This is cheaper.', '加了 -er 就不能再用 more。'),
        ('She is the most tall girl in class.', 'She is the tallest girl in class.', '单音节词用 -est。'),
        ('My English is more good now.', 'My English is better now.', 'good 的比较级是 better。')],
       _g('Of all the hotels we saw, this one is ____.', ['cheaper', 'the cheapest', 'more cheap', 'cheapest than'], 1, 'of all the hotels 说明是在多个之中比较。', '三者以上比较用 the + 最高级。'),
       '是在两者之间比，还是在一群里比？这个词有几个音节？',
       [('Today is ____ than yesterday.', ['hot', 'hotter', 'hottest', 'more hot'], 1, '两天比较用比较级，hot 双写 t。'),
        ('It was ____ film I have ever seen.', ['the worse', 'the worst', 'worse', 'the baddest'], 1, 'bad 的最高级是 the worst。'),
        ('Learning a language is ____ than I expected.', ['difficulter', 'more difficult', 'most difficult', 'the more difficult'], 1, '多音节词用 more。'),
        ('Mount Everest is the highest mountain ____ the world.', ['of', 'in', 'than', 'at'], 1, '在某个范围（地点）里最高，用 in。')],
       '比较级 than 与 the + 最高级'),
    _n('compare-pattern', 'compare', '比较的常用结构', 'compare-basic', 'B1',
       'as … as 表示相同；not as … as 表示不如；the + 比较级 …, the + 比较级 … 表示越…越…；倍数 + as … as。', 'The more you practise, the more confident you become.',
       '用常见的比较结构表达相同、不如、越来越和倍数。',
       ['程度相同：as + 原级 + as：He is as tall as his father.',
        '不如：not as / so + 原级 + as：This café isn’t as busy as that one.',
        '越…越…：The + 比较级 + 主语 + 谓语, the + 比较级 + 主语 + 谓语：The earlier we leave, the less traffic there will be.',
        '越来越：比较级 + and + 比较级：It’s getting colder and colder. / more and more popular。',
        '倍数：three times as big as，或 three times bigger than。'],
       [('My bag is as heavy as yours.', '一样重'), ('My bag isn’t as heavy as yours.', '没你的重'), ('The harder he worked, the more he earned.', '越…越…')],
       [('She is as taller as her sister.', 'She is as tall as her sister.', 'as … as 中间用原级。'),
        ('The more I read, I understand more.', 'The more I read, the more I understand.', '两部分都要用 the + 比较级开头。'),
        ('It is becoming more and more expensiver.', 'It is becoming more and more expensive.', 'more and more 后接原级。')],
       _g('The new office is ____ the old one.', ['twice as large as', 'twice larger as', 'as twice large as', 'twice as larger than'], 0, '倍数放在 as … as 前面，中间用原级。', '倍数 + as + 原级 + as。'),
       '是在说一样、不如、越来越，还是倍数？',
       [('The ____ you start, the sooner you will finish.', ['early', 'earlier', 'earliest', 'more early'], 1, 'the + 比较级 …, the + 比较级 …'),
        ("This year's exam wasn't ____ last year's.", ['as hard as', 'harder as', 'as harder than', 'hard than'], 0, 'not as + 原级 + as：不如。'),
        ('Online shopping is becoming ____ popular.', ['more and more', 'most and most', 'much and much', 'the more'], 0, '越来越 + 多音节词：more and more + 原级。'),
        ('Your room is ____ mine.', ['three times as big as', 'as three times big as', 'three times as bigger', 'big three times than'], 0, '倍数 + as + 原级 + as。')],
       'as … as、the more … the more 等比较结构'),
    # ---------------- link ----------------
    _n('link-contrast', 'link', '转折与让步', 'clause-adverb', 'B1',
       'although / though 后接句子；despite / in spite of 后接名词或 doing；however 是副词，前后用句号或分号隔开。', 'Although it was raining, we went out. Despite the rain, we went out.',
       '用 although、despite、however、but 正确连接转折关系。',
       ['although / even though + 完整句子：Although he was tired, he kept working.',
        'despite / in spite of + 名词或 doing：Despite being tired, he kept working.',
        'however 连接两个句子：…late. However, she still came.（也可以放在句中，用逗号隔开）',
        'although 和 but 不能在同一个句子里同时用。'],
       [('Although the hotel was expensive, we stayed there.', 'although + 句子'), ('Despite the high price, we stayed there.', 'despite + 名词'), ('The hotel was expensive. However, we stayed there.', 'however 连接两句')],
       [('Although it was late, but she called me.', 'Although it was late, she called me.', 'although 和 but 不能同时用。'),
        ('Despite it was raining, we played.', 'Despite the rain, we played.', 'despite 后不能接完整的句子。'),
        ('He studied hard, however he failed.', 'He studied hard; however, he failed.', 'however 是副词，不能像 but 那样只用逗号连接两个句子。')],
       _g('____ having little money, they were very happy.', ['Although', 'Despite', 'However', 'But'], 1, '后面是 having…（动名词），不是完整的句子。', 'despite + doing。'),
       '后面跟的是完整的句子，还是名词或 doing？',
       [('____ the traffic was heavy, we arrived on time.', ['Despite', 'Although', 'In spite of', 'However'], 1, '后面是完整的句子，用 although。'),
        ('She went to work ____ feeling ill.', ['although', 'despite', 'however', 'but'], 1, '后面是 feeling（doing），用 despite。'),
        ('The plan sounds good. ____, it will be expensive.', ['Although', 'Despite', 'However', 'Even though'], 2, '句首连接两个独立的句子，用 However。'),
        ('Which sentence is correct?', ['Although he tried, but he failed.', 'Despite he tried, he failed.', 'Although he tried, he failed.', 'However he tried, but he failed.'], 2, 'although + 句子，而且不再用 but。')],
       'although / despite / however：转折'),
    _n('link-cause', 'link', '原因与结果', None, 'A2',
       'because + 句子；because of / due to + 名词；so 引出结果；therefore、as a result 连接两个句子。', 'The flight was cancelled because of the storm, so we stayed another night.',
       '用合适的连接词表达原因和结果。',
       ['because / as / since + 完整句子表示原因：We stayed in because it was cold.',
        'because of / due to + 名词：The game was delayed because of the rain.',
        'so + 结果（句子）：It was cold, so we stayed in.',
        'therefore / as a result 在正式写作里连接两个句子：…late. As a result, we missed the bus.',
        'because 和 so 不能在同一个句子里同时用。'],
       [('I was late because the bus broke down.', 'because + 句子'), ('I was late because of the bus.', 'because of + 名词'), ('The bus broke down, so I was late.', 'so 引出结果')],
       [('Because it was cold, so we stayed home.', 'Because it was cold, we stayed home.', 'because 和 so 只能用一个。'),
        ('He was absent because of he was ill.', 'He was absent because he was ill.', 'because of 后接名词；接句子用 because。'),
        ('The road was closed due to it snowed.', 'The road was closed due to the snow.', 'due to 后接名词。')],
       _g('The match was cancelled ____ the heavy rain.', ['because', 'so', 'because of', 'therefore'], 2, '后面是名词短语，不是句子。', 'because of + 名词。'),
       '后面是句子还是名词？表示原因还是结果？',
       [("I didn't sleep well, ____ I feel tired now.", ['because', 'so', 'because of', 'due to'], 1, '引出结果用 so。'),
        ('Many flights were delayed ____ the fog.', ['because', 'due to', 'so', 'as'], 1, '后面是名词，用 due to。'),
        ('She got the job ____ she had a lot of experience.', ['because of', 'because', 'so', 'therefore'], 1, '后面是完整的句子，用 because。'),
        ('Prices rose sharply. ____, fewer people travelled abroad.', ['Because', 'Because of', 'As a result', 'Due to'], 2, '句首连接两个句子、引出结果，用 As a result。')],
       'because / because of / so：原因和结果'),
    _n('link-purpose', 'link', '目的与“如此…以至于”', 'link-cause', 'B1',
       'to / in order to + 动词原形 和 so that + 句子 表示目的；so + 形容词 + that 和 such + 名词 + that 表示结果。', 'She spoke slowly so that everyone could understand.',
       '区分表示目的和表示结果的结构，并用对 so … that 和 such … that。',
       ['目的（为了）：to / in order to / so as to + 动词原形：I got up early in order to catch the train.',
        '目的后面是一个句子时：so that + 主语 + can / could / will：Speak louder so that we can hear you.',
        '结果（如此…以至于）：so + 形容词 / 副词 + that：It was so cold that the lake froze.',
        'such + (a / an) + 形容词 + 名词 + that：It was such a cold day that the lake froze.'],
       [('He saved money to buy a car.', '目的：为了买车'), ('He saved money so that he could buy a car.', '目的，后面接句子'), ('He saved so much money that he bought a car.', '结果：存了很多钱，于是买了车')],
       [('It was such cold that we stayed in.', 'It was so cold that we stayed in.', 'so + 形容词；such + 名词短语。'),
        ('It was so a good film that I watched it twice.', 'It was such a good film that I watched it twice.', '带名词的用 such a …'),
        ('I study hard for pass the exam.', 'I study hard to pass the exam.', '表示目的用 to do，不用 for + 动词原形。')],
       _g('She wrote the address down ____ she wouldn’t forget it.', ['so that', 'such that', 'in order to', 'so as'], 0, '后面跟的是完整的句子 she wouldn’t forget it。', '目的后面接句子用 so that。'),
       '表达目的还是结果？后面接动词原形、句子，还是名词？',
       [("The box was ____ heavy that I couldn't lift it.", ['such', 'so', 'very', 'too'], 1, 'so + 形容词 + that。'),
        ('It was ____ interesting book that I finished it in one night.', ['so', 'such an', 'so an', 'such'], 1, 'such + an + 形容词 + 名词 + that。'),
        ('We left early ____ miss the rush hour.', ['so that', 'in order not to', 'such that', 'for not'], 1, '目的的否定：in order not to + 动词原形。'),
        ('Turn the music down ____ the baby can sleep.', ['so that', 'such that', 'in order to', 'so as to'], 0, '后面是句子，用 so that。')],
       'so that / in order to / so … that：目的与结果'),
    # ---------------- prep ----------------
    _n('prep-time-place', 'prep', 'in、on、at：时间与地点', None, 'A2',
       '时间：at 时刻、on 某一天、in 较长时段；地点：at 一个点、on 表面、in 空间。', 'The meeting is at 3 p.m. on Monday in Room 5.',
       '用 in、on、at 准确表达时间和地点。',
       ['时间：at + 时刻或节点（at 7:30，at night）；on + 某一天（on Friday，on 1 May，on my birthday）；in + 月份、年份、季节、上午下午（in July，in 2025，in the morning）。',
        '地点：at + 一个点或场所（at the bus stop，at work）；on + 表面或楼层（on the wall，on the second floor）；in + 封闭空间、城市国家（in the box，in Shanghai）。',
        'this、next、last、every 前面不加介词：I’ll see you next Monday.'],
       [('in the morning', '上午这一段时间'), ('on Monday morning', '具体某一天的上午，用 on'), ('at the station / in the station', '在车站这个点 / 在车站建筑里面')],
       [('I was born in 5 May.', 'I was born on 5 May.', '具体日期用 on。'),
        ('See you on next week.', 'See you next week.', 'next、last、this 前不加介词。'),
        ('She lives at Beijing.', 'She lives in Beijing.', '城市用 in。')],
       _g('The shop opens ____ 9 a.m. ____ Saturdays.', ['at / on', 'in / at', 'on / in', 'at / in'], 0, '9 a.m. 是一个时刻；Saturdays 是具体的日子。', '时刻用 at，星期用 on。'),
       '是一个点、一个面或某一天，还是一个空间或一段较长的时间？',
       [('We usually go skiing ____ winter.', ['at', 'on', 'in', '/'], 2, '季节用 in。'),
        ('My flat is ____ the third floor.', ['in', 'at', 'on', 'to'], 2, '楼层用 on。'),
        ("Let's meet ____ the entrance of the museum.", ['at', 'in', 'on', 'to'], 0, '入口是一个点，用 at。'),
        ('He started his new job ____ 2023.', ['at', 'on', 'in', '/'], 2, '年份用 in。')],
       'at / on / in：时间和地点'),
    _n('prep-pattern', 'prep', '动词、形容词与介词的搭配', 'prep-time-place', 'B1',
       '很多动词和形容词后面接固定的介词，要整体记：depend on，interested in，good at，responsible for；介词后的动词用 doing。', 'She is interested in starting her own business.',
       '记住高频的“词 + 介词”搭配，并在介词后正确使用 doing。',
       ['动词 + 介词：depend on，focus on，apply for，belong to，deal with，consist of，succeed in。',
        '形容词 + 介词：good at，interested in，afraid of，proud of，responsible for，similar to，different from。',
        '介词后面接名词或动名词：I’m tired of waiting. / Thank you for coming.',
        'look forward to、be used to 里的 to 是介词，后面接 doing。'],
       [('She is good at maths.', 'good at：擅长'), ('She is good for the team.', 'good for：对团队有好处，意思不同'), ('I’m looking forward to seeing you.', 'to 是介词，接 seeing')],
       [('It depends of the weather.', 'It depends on the weather.', 'depend 搭配 on。'),
        ('He is interested on history.', 'He is interested in history.', 'interested 搭配 in。'),
        ('I look forward to hear from you.', 'I look forward to hearing from you.', 'look forward to 的 to 是介词，接 doing。')],
       _g('Who is responsible ____ this project?', ['of', 'for', 'to', 'with'], 1, 'responsible 后面接固定的介词。', 'be responsible for：对…负责。'),
       '这个词习惯和哪个介词连用？介词后面的动词用 doing 了吗？',
       [('She is very proud ____ her son.', ['for', 'of', 'with', 'about'], 1, 'be proud of：为…骄傲。'),
        ('Thank you for ____ me with my homework.', ['help', 'to help', 'helping', 'helped'], 2, '介词 for 后接 doing。'),
        ('This sauce is similar ____ the one my mother makes.', ['with', 'to', 'as', 'from'], 1, 'be similar to：和…相似。'),
        ('He applied ____ a job at the bank.', ['to', 'for', 'on', 'at'], 1, 'apply for a job：申请工作。')],
       '固定搭配：词 + 介词'),
    # ---------------- emphasis ----------------
    _n('emph-cleft', 'emphasis', '强调句', 'clause-relative', 'B2',
       'It is / was + 被强调部分 + that / who + 其余部分，突出句子的某一个成分；What … is / was … 突出后面的内容。', 'It was Lisa who solved the problem.',
       '用强调句和 What 开头的句子突出你最想强调的信息。',
       ['It is / was + 强调部分 + that（强调人时也可以用 who）+ 句子其余部分：It was in 2019 that we first met.',
        '检验：去掉 It is / was 和 that，剩下的部分能组成完整的句子，就是强调句。',
        '时态：原句是过去时就用 It was，现在时用 It is。',
        'What + 从句 + is / was + 强调内容：What I need is a long holiday.'],
       [('Tom broke the vase.', '普通陈述'), ('It was Tom who broke the vase.', '强调是汤姆，不是别人'), ('What surprised me was his honesty.', '强调让人惊讶的是他的诚实')],
       [('It was in the park where I lost my keys.', 'It was in the park that I lost my keys.', '强调句用 that 连接，不用 where。'),
        ('It is yesterday that I met her.', 'It was yesterday that I met her.', '强调过去的事用 It was。'),
        ('What I want it is some rest.', 'What I want is some rest.', 'What 从句已经作主语，不再加 it。')],
       _g('It was not until midnight ____ he finished the report.', ['when', 'that', 'which', 'then'], 1, '这是 It was … that 的强调句，强调 not until midnight。', '强调句的连接词用 that。'),
       '去掉 It is / was … that，剩下的还能组成完整的句子吗？',
       [('It was the price ____ made me change my mind.', ['what', 'that', 'where', 'it'], 1, '强调句：It was + 强调部分 + that。'),
        ('____ I like most about this city is the food.', ['That', 'What', 'Which', 'It'], 1, 'What 从句作主语，强调后面的 the food。'),
        ('It was at this café ____ they first met.', ['where', 'that', 'which', 'when'], 1, '强调地点状语时连接词仍用 that。'),
        ('Which sentence puts the focus on WHEN the meeting happened?', ['The meeting happened on Monday.', 'It was on Monday that the meeting happened.', 'What happened on Monday was the meeting.', 'The meeting, which happened on Monday, was long.'], 1, 'It was + on Monday + that … 强调时间。')],
       'It is / was … that、What … is：强调'),
    _n('emph-inversion', 'emphasis', '否定词提前的倒装', 'emph-cleft', 'C1',
       'never、rarely、not only、no sooner、only then 等否定或限制词放在句首时，主句用疑问句语序（助动词提前）。', 'Never have I seen such a beautiful sunset.',
       '在正式写作和演讲中用倒装加强语气，并写对助动词的位置。',
       ['可以提前的否定或限制词：Never，Rarely，Seldom，Hardly，Little，Not only，Not until，Only when / then / after。',
        '主句用“助动词 + 主语 + 动词”：Rarely do we see snow here. / Not only did she win, but she also broke the record.',
        '没有助动词时加 do / does / did：Seldom does he complain.',
        'Not until / Only when 倒装的是后面的主句：Not until I got home did I notice the hole.',
        'No sooner had … than …；Hardly had … when …：No sooner had I sat down than the phone rang.'],
       [('I have never seen such a mess.', '正常语序'), ('Never have I seen such a mess.', '倒装，语气更强'), ('Only then did I understand.', 'only then 后助动词提前')],
       [('Never I have seen it.', 'Never have I seen it.', '否定词提前后，助动词放在主语前面。'),
        ('Not only she sings, but she also dances.', 'Not only does she sing, but she also dances.', 'Not only 放在句首要倒装，加 does。'),
        ('Not until he left I realised the truth.', 'Not until he left did I realise the truth.', '倒装发生在主句。')],
       _g('Rarely ____ such a generous offer.', ['we receive', 'do we receive', 'we do receive', 'receive we'], 1, 'Rarely 在句首，主句要用疑问句语序。', 'Rarely + do + 主语 + 动词原形。'),
       '句首是不是否定或限制词？后面的主句把助动词提前了吗？',
       [('Seldom ____ so many people at the beach in winter.', ['we see', 'do we see', 'we do see', 'saw we'], 1, 'Seldom 在句首，助动词 do 提前。'),
        ('No sooner ____ the house than it started to rain.', ['we had left', 'had we left', 'we left', 'did we left'], 1, 'No sooner had + 主语 + done … than …'),
        ('Not until the results came out ____ how well she had done.', ['she realised', 'did she realise', 'she did realise', 'realised she'], 1, 'Not until 从句后，主句倒装。'),
        ('Only after the meeting ____ the decision.', ['I understood', 'did I understand', 'I did understand', 'understood I'], 1, 'Only after … 放句首，主句倒装。')],
       '否定或限制词放句首，助动词提前'),
]

# which of the new points a level should be building now (added to next_service.LEVEL_NODES)
LEVEL_MORE = {
    'A2': ('tense-future', 'voice-basic', 'modal-ability', 'modal-obligation', 'det-article', 'det-quantity', 'compare-basic', 'link-cause', 'prep-time-place'),
    'B1': ('tense-future', 'tense-past-perfect', 'clause-reported', 'voice-basic', 'voice-tenses', 'modal-obligation', 'modal-deduction', 'det-zero',
           'compare-pattern', 'link-contrast', 'link-cause', 'link-purpose', 'prep-pattern'),
    'B2': ('tense-perfect-continuous', 'clause-nondefining', 'subjunctive-wish', 'nonfinite-clause', 'voice-tenses', 'voice-causative', 'modal-deduction',
           'modal-past', 'link-contrast', 'link-purpose', 'prep-pattern', 'emph-cleft'),
    'C1': ('subjunctive-wish', 'nonfinite-clause', 'modal-past', 'voice-causative', 'clause-nondefining', 'tense-perfect-continuous', 'emph-cleft', 'emph-inversion'),
}
# the original 18 points each level builds at B2 and C1 (A2 and B1 are in next_service)
LEVEL_BASE = {
    'B2': ('clause-noun', 'clause-adverb', 'conditional-modal', 'subjunctive-now', 'subjunctive-past', 'nonfinite-gerund', 'nonfinite-participle', 'agreement-each', 'agreement-either'),
    'C1': ('subjunctive-past', 'subjunctive-mixed', 'nonfinite-participle', 'agreement-either', 'clause-noun'),
}

BY_ID = {n['id']: n for n in NODES_MORE}
PAGES_MORE = {n['id']: n['page'] for n in NODES_MORE}


def install(c):
    """Add the topics, subskills, verification questions and graph nodes once."""
    if c.execute("SELECT 1 FROM migrations WHERE version='grammar-2.0'").fetchone():
        return
    for t in TOPICS_MORE:
        c.execute('INSERT OR IGNORE INTO topics VALUES(?,?,?,?,?,?,?)', (*t[:6], json.dumps(t[6], ensure_ascii=False)))
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for n in NODES_MORE:
        c.execute('INSERT OR IGNORE INTO subskills VALUES(?,?,?,?,?,?)', (n['id'], n['topic'], n['title'], n['prereq'], n['lesson'], n['example']))
        for prompt, options, answer, explanation in n['questions']:
            if c.execute('SELECT 1 FROM questions WHERE node=? AND prompt=?', (n['id'], prompt)).fetchone():
                continue
            c.execute("INSERT INTO questions(topic,prompt,options,answer,explanation,node,status,difficulty) VALUES(?,?,?,?,?,?,'published',?)",
                      (n['topic'], prompt, json.dumps(options, ensure_ascii=False), answer, explanation, n['id'], 'easy' if n['level'] == 'A2' else 'hard' if n['level'] in ('B2', 'C1') else 'medium'))
        if 'kg_nodes' in tables:
            c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,NULL,?)', (n['id'], 'grammar', n['title'], n['id']))
        if 'kg_edges' in tables and n['prereq']:
            c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)', (n['prereq'], n['id'], 'prerequisite', 'curriculum'))
    c.execute("INSERT INTO migrations VALUES('grammar-2.0')")


# ---------------------------------------------------------------- finding the points in a material

IRREGULAR_PP = set('''arisen awoken been borne beaten become begun bent bet bitten bled blown broken bred brought built burnt burst bought
cast caught chosen clung come cost crept cut dealt dug done drawn dreamt drunk driven eaten fallen fed felt fought found fled flown forbidden
forgotten forgiven frozen got gotten given gone ground grown hung had heard hidden hit held hurt kept knelt known laid led leant learnt left lent
let lain lit lost made meant met mistaken overcome overtaken paid proven put quit read ridden rung risen run said seen sought sold sent set sewn
shaken shed shone shot shown shrunk shut sung sunk sat slept slid spoken spent spilt spun spread sprung stood stolen stuck stung struck sworn
swept swum swung taken taught torn told thought thrown understood undertaken upset woken worn woven wept won wound withdrawn written born'''.split())
# -ed words that are usually adjectives after "be" (she is interested), not passives
ADJ_ED = set('''interested excited tired bored worried surprised pleased scared frightened married crowded supposed used related concerned
satisfied disappointed embarrassed amazed annoyed confused determined qualified experienced talented aged retired relaxed stressed shocked
delighted exhausted fascinated frustrated impressed motivated organised organized complicated detailed advanced balanced skilled naked
wicked sacred beloved learned ashamed armed rugged ragged crooked'''.split())


def _pp(w):
    w = w.lower()
    return w in IRREGULAR_PP or (len(w) > 4 and w.endswith('ed') and w not in ADJ_ED and w not in ('need', 'speed', 'seed', 'feed', 'bleed', 'proceed', 'exceed', 'succeed', 'indeed', 'hundred', 'kindred'))


_BE = r"(?:am|is|are|was|were)"
_MODAL = r"(?:will|would|can|could|must|should|may|might)"
_W = r"[A-Za-z]+"
# a participle-shaped word, so a pattern looks for the participle itself rather than settling on the first word
_PP = r"(?:[a-z]{2,}ed|" + "|".join(sorted(IRREGULAR_PP, key=len, reverse=True)) + r")"
PATTERNS = {
    'tense-future': [r"\b(?:will|won't|'ll)\s+(?:not\s+)?(?:\w+ly\s+)?(?!be\b|have\b)[a-z]{2,}\b", r"\b(?:am|is|are|'m|'s|'re)\s+(?:not\s+)?going\s+to\s+[a-z]+\b"],
    'tense-past-perfect': [r"\bhad\s+(?:not\s+|never\s+|already\s+|just\s+|recently\s+|always\s+)?(?P<pp>" + _PP + r")\b"],
    'tense-perfect-continuous': [r"\b(?:has|have|'ve)\s+(?:not\s+|never\s+|just\s+|always\s+)?been\s+[a-z]+ing\b"],
    'voice-basic': [r"\b" + _BE + r"\s+(?:not\s+|also\s+|often\s+|usually\s+|still\s+|now\s+|widely\s+|then\s+)?(?P<pp>" + _PP + r")\b(?!\s+to\b)"],
    'voice-tenses': [r"\b(?:has|have|had)\s+(?:not\s+|already\s+|just\s+)?been\s+(?P<pp>" + _PP + r")\b", r"\b" + _BE + r"\s+being\s+(?P<pp>" + _PP + r")\b",
                     r"\b" + _MODAL + r"\s+(?:not\s+|also\s+)?be\s+(?P<pp>" + _PP + r")\b"],
    'voice-causative': [r"\b(?:have|has|had|having|get|gets|got|getting)\s+(?:my|your|his|her|its|our|their|it|them)\s+(?:\w+\s+){0,2}?(?P<pp>" + _PP + r")\b(?=\s|[,.;!?]|$)"],
    'modal-ability': [r"\b(?:can|can't|cannot|could|couldn't)\s+(?!be\b|have\b)[a-z]+\b", r"\b(?:be|been|am|is|are|was|were|will be)\s+(?:not\s+)?able\s+to\b"],
    'modal-obligation': [r"\b(?:have to|has to|had to|ought to|needn't|mustn't)\b", r"\bmust\s+(?!be\b|have\b)[a-z]+\b", r"\bshould(?:n't)?\s+(?!be\b|have\b)[a-z]+\b"],
    'modal-deduction': [r"\b(?:must|might|may|can't|cannot|couldn't)\s+(?:not\s+)?be\s+(?P<nx>" + _W + r")\b"],
    'modal-past': [r"\b(?:must|might|may|could|couldn't|can't|should|shouldn't)\s+(?:not\s+)?have\s+(?P<pp>" + _PP + r")\b"],
    'clause-nondefining': [r",\s+(?:who|which|whose|whom)\b"],
    'clause-reported': [r"\b(?:said|explained|admitted|claimed|replied|reported|announced|insisted|promised|added|suggested|agreed)\s+(?:that\s+)?(?:he|she|they|it|we|I|there)\s+(?:was|were|had|would|could|might|should)\b",
                        r"\b(?:told|asked|warned|reminded|informed)\s+(?:me|him|her|us|them|\w+)\s+(?:that|if|whether|where|when|why|how|what)\b", r"\basked\s+(?:if|whether)\b"],
    'subjunctive-wish': [r"\b(?:wish|wishes|wished|if only)\s+(?:I|you|he|she|we|they|it|there|\w+)\s+(?:were|had|could|would|knew|was|did|didn't|hadn't)\b",
                         r"\b(?:it's|it is)\s+(?:high\s+|about\s+)?time\s+(?:we|you|they|I|he|she)\s+[a-z]+ed\b"],
    'nonfinite-clause': [r"^(?:Having\s+[a-z]+|Not\s+[a-z]+ing|(?P<ing>[A-Z][a-z]+ing)\b)[^,.;:!?]{2,70},\s*(?:I|we|you|he|she|they|it|the|a|an|this|these|those|my|our|his|her|their|[A-Z][a-z]+)\b",
                         r"^(?P<ed>[A-Z][a-z]+(?:ed|en))\s+(?:by|in|from|with|as|on|at|for)\b[^,.;:!?]{2,70},\s*(?:the|a|an|this|these|those|it|they|he|she|we|I|my|our|his|her|their|[A-Z][a-z]+)\b"],
    'det-article': [r"\ban\s+(?:hour|honest|honour|honor|heir|MBA|FBI|SUV|NGO|MP3|X-ray|hourly)\b", r"\ba\s+(?:university|uniform|unique|useful|user|unit|union|European|one-|once-)\w*",
                    r"\bthe\s+(?:only|same|first|second|third|last|next)\s+[a-z]+"],
    'det-quantity': [r"\b(?:a few|a little|a number of|plenty of|a great deal of|fewer|several|how many|how much|too many|too much|so many|not many|not much)\s+[a-z]+"],
    'compare-basic': [r"\b(?!(?:rather|other|whether|neither|either|over|under|after|never|ever|together|number|water|order|matter|letter|paper|power|weather|answer|member)\b)[a-z]+er\s+than\b",
                      r"\b(?:more|less)\s+[a-z]+\s+than\b", r"\bthe\s+(?:most|least)\s+[a-z]+", r"\bthe\s+(?:best|worst|biggest|largest|smallest|highest|lowest|longest|oldest|youngest|fastest|easiest|hardest|cheapest|closest|greatest)\b"],
    'compare-pattern': [r"\b(?:as|so)\s+(?!well\b|soon\b|long\b|far\b|if\b|though\b|to\b|a\b|the\b|for\b|of\b|it\b)[a-z]+\s+as\b", r"\bthe\s+(?:more|less|[a-z]+er)\b[^.;]{1,80},\s*the\s+(?:more|less|[a-z]+er)\b",
                        r"\bmore and more\b", r"\b([a-z]+er) and \1\b", r"\b(?:twice|half|three times|four times|five times|ten times)\s+(?:as|more|bigger|larger|faster|higher)\b"],
    'link-contrast': [r"\b(?:although|even though|despite|in spite of|however|whereas|nevertheless|nonetheless)\b"],
    'link-cause': [r"\b(?:because of|because|due to|as a result|therefore|thanks to|owing to|consequently)\b", r",\s*so\s+(?!that\b|far\b|much\b|many\b|on\b)(?:I|we|you|he|she|they|it|the|there|my|our|his|her|their)\b"],
    'link-purpose': [r"\b(?:so that|in order to|in order not to|so as to|so as not to)\b", r"\bso\s+[a-z]+\s+that\b", r"\bsuch\s+(?:a\s+|an\s+)?[a-z]+(?:\s+[a-z]+)?\s+that\b"],
    'prep-time-place': [r"\b(?:at\s+(?:\d{1,2}(?::\d\d)?\s*(?:a\.m\.|p\.m\.|am\b|pm\b|o'clock)|night|noon|midnight|dawn)|on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|(?:\d{1,2}\s+)?(?:January|February|March|April|June|July|August|September|October|November|December)\b|(?:my|his|her|their|our|your)\s+birthday|the\s+(?:first|second|third|fourth|fifth|top|ground)\s+floor)|in\s+(?:January|February|March|April|June|July|August|September|October|November|December|(?:19|20)\d\d|the\s+(?:morning|afternoon|evening)|spring|summer|autumn|winter))\b"],
    'prep-pattern': [r"\b(?:depend(?:s|ed|ing)?|rel(?:y|ies|ied|ying)|focus(?:es|ed|ing)?|insist(?:s|ed|ing)?|concentrat(?:e|es|ed|ing))\s+on\b",
                     r"\b(?:interested|involved|succeed(?:s|ed)?|result(?:s|ed)?|specialis(?:e|es|ed)|specializ(?:e|es|ed))\s+in\b",
                     r"\b(?:good|bad|better|best|great|terrible|skilled)\s+at\b", r"\b(?:afraid|proud|aware|capable|tired|scared|fond|full|ashamed|jealous)\s+of\b",
                     r"\b(?:responsible|famous|known|ready|grateful|apply|applied|applies|apologi[sz]e[sd]?)\s+for\b", r"\b(?:similar|addicted|belong(?:s|ed)?|look(?:ing|ed)?\s+forward)\s+to\b", r"\b(?:be|is|am|are|was|were|get|gets|got|getting|become|became)\s+(?:used|accustomed)\s+to\s+[a-z]+(?:ing)?\b",
                     r"\b(?:deal(?:s|t|ing)?|cope|copes|coped|familiar|satisfied|pleased|disappointed)\s+with\b", r"\b(?:different|suffer(?:s|ed|ing)?|recover(?:s|ed|ing)?)\s+from\b", r"\b(?:worried|anxious|excited|upset|curious)\s+about\b",
                     r"\bconsist(?:s|ed)?\s+of\b"],
    'emph-cleft': [r"^What\s+[^,.;]{2,50}?\s+(?:is|was)\s+", r"\bIt\s+(?:is|was)\s+not\s+until\b[^.;]{1,60}?\bthat\b", r"\bIt\s+(?:is|was)\s+(?:only\s+)?(?:in|at|on|during|because|only|precisely|exactly|this|these|those)\b[^.;,]{1,50}?\bthat\b"],
    'emph-inversion': [r"^(?:Never|Rarely|Seldom|Hardly|Scarcely|Little|Nowhere|Not only|No sooner|Under no circumstances|At no time|In no way|Not once|Only (?:then|later|now|recently|once)|(?:Not until|Only (?:when|after|if|by|in|through))\b[^,]{1,60},?)\s+(?:have|has|had|do|does|did|is|are|was|were|can|could|will|would|should|must|may|might)\s+(?:I|we|you|he|she|they|it|the|there|this|[A-Z][a-z]+)\b"],
}
_COMPILED = {k: [re.compile(p, re.I if k not in ('nonfinite-clause', 'emph-inversion', 'emph-cleft', 'det-article') else 0) for p in v] for k, v in PATTERNS.items()}
ING_STOP = set('''during nothing something anything everything morning evening spring king thing ring building wedding ceiling according including
regarding concerning following considering depending notwithstanding pending sterling darling herring shilling pudding meeting earring'''.split())


def _ok(node, m):
    g = m.groupdict()
    if g.get('pp') is not None and not _pp(g['pp']):
        return False
    if node == 'voice-basic' and g['pp'].lower() in ('been', 'got', 'gotten', 'gone', 'come', 'become', 'had', 'used'):
        return False  # is gone / was used to: not the passive this point teaches
    if node == 'modal-deduction' and g.get('nx') is not None and _pp(g['nx']):
        return False  # must be done = passive, not a guess
    if g.get('ing') is not None and g['ing'].lower() in ING_STOP:
        return False
    if g.get('ed') is not None and not _pp(g['ed']):
        return False
    return True


def find(sentence):
    """The new points a sentence shows."""
    out = []
    for node, pats in _COMPILED.items():
        for p in pats:
            if any(_ok(node, m) for m in p.finditer(sentence)):
                out.append(node)
                break
    # a passive in a perfect / progressive / modal form is that point, not the plain one
    if 'voice-tenses' in out and 'voice-basic' in out and not re.search(r"\b" + _BE + r"\s+(?!being\b)\w+", re.sub(r"\b" + _BE + r"\s+being\b", '', sentence), re.I):
        out.remove('voice-basic')
    return out


SENT = re.compile(r"[^.!?]+[.!?]+[\"”’']?|[^.!?]+$")


def sentences(text):
    return [s.strip() for s in SENT.findall(text or '') if len(s.split()) >= 4]


def examples(body, limit=3):
    """{node: [sentence, …]} for one material's English text: at most `limit` sentences per point, shortest first."""
    out = {}
    for s in sentences(body):
        if len(s) > 260:
            continue
        for n in find(s):
            out.setdefault(n, []).append(s)
    return {n: sorted(v, key=len)[:limit] for n, v in out.items()}
