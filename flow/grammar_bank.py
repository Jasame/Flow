"""More verification questions per grammar point (10 for each of the 44), the spaced re-check schedule, and the
starting check that places a learner and lights the graph.

Why: with four questions per point, the second round was a memory test of the first, and once a point was
"verified" nothing ever asked about it again. Now a round draws 4 of 10 in random order with shuffled options,
and a point answered correctly comes back on a widening ladder (1, 3, 7, 21, 60 days); a miss sends it back to the
first rung. Every question here is original.
"""
import hashlib, json, random, time

DAY = 86400
LADDER = (1, 3, 7, 21, 60)  # days until the next check, per rung

# node -> [(prompt, options, answer, explanation)]
EXTRA = {
    # ---------------- tense ----------------
    'tense-present': [
        ('Water ____ at 100 degrees Celsius.', ['boil', 'boils', 'is boiling', 'boiled'], 1, '客观事实用一般现在时，主语 water 是第三人称单数，用 boils。'),
        ('Be quiet, please. The baby ____.', ['sleeps', 'is sleeping', 'slept', 'has slept'], 1, 'Be quiet 说明此刻正在发生，用现在进行时。'),
        ('I ____ the answer to this question.', ['know', 'am knowing', 'knowing', 'knows'], 0, 'know 是表示状态的动词，一般不用进行时。'),
        ('How often ____ to the gym?', ['you go', 'do you go', 'are you going', 'you are going'], 1, 'How often 问频率，一般现在时的疑问句要用 do 提前。'),
        ('This week I ____ from home because the office is being painted.', ['work', 'am working', 'works', 'worked'], 1, 'this week 指现阶段暂时的情况，用现在进行时。'),
        ("She ____ coffee; she only drinks tea.", ["doesn't drink", "don't drink", "isn't drinking", 'not drinks'], 0, '习惯的否定：第三人称单数用 doesn’t + 动词原形。'),
    ],
    'tense-past': [
        ('I ____ my grandparents last weekend.', ['visit', 'have visited', 'visited', 'was visiting'], 2, 'last weekend 是过去的具体时间，用一般过去时。'),
        ('While I ____ a shower, the phone rang.', ['took', 'was taking', 'take', 'have taken'], 1, '较长的动作正在进行时被短动作打断：长动作用过去进行时。'),
        ("She ____ to the party because she was ill.", ["didn't come", "didn't came", "wasn't come", "hasn't come"], 0, '一般过去时的否定：didn’t + 动词原形。'),
        ('When I came in, my roommates ____ cards and laughing loudly.', ['played', 'were playing', 'play', 'have played'], 1, '和 laughing 并列，描述我进门那一刻正在进行的动作，用过去进行时。'),
        ('He ____ in Shanghai from 2015 to 2019.', ['lives', 'has lived', 'lived', 'is living'], 2, '一段已经结束的过去时间，用一般过去时。'),
        ('We ____ the film yesterday, but it was boring.', ['saw', 'see', 'have seen', 'were seeing'], 0, 'yesterday 指过去，用一般过去时 saw。'),
    ],
    'tense-perfect': [
        ("Tom isn't here. He ____ to the bank.", ['has been', 'has gone', 'is gone', 'have gone'], 1, 'has gone to 表示去了还没回来；has been to 表示去过、已经回来。'),
        ('Have you ever ____ sushi?', ['eat', 'ate', 'eaten', 'eating'], 2, 'Have … ever 问经历，后接过去分词 eaten。'),
        ('I ____ my homework yet.', ["haven't finished", "hasn't finished", "don't finish", "am not finishing"], 0, 'yet 用在否定句里，常和现在完成时连用；主语是 I，用 haven’t。'),
        ('She has worked here ____ ten years.', ['since', 'for', 'ago', 'during'], 1, 'for 接一段时间，since 接时间起点。'),
        ('I ____ him since we left school.', ["didn't see", "haven't seen", "don't see", "wasn't seeing"], 1, 'since 表示从过去持续到现在，用现在完成时。'),
        ("We've just ____ lunch, so we aren't hungry.", ['have', 'had', 'having', 'has'], 1, 'have just + 过去分词，have 的过去分词是 had。'),
    ],
    'tense-future': [
        ('I think it ____ cold tomorrow, so take a coat.', ['is', 'will be', 'was', 'has been'], 1, 'I think 引出的个人预测，用 will。'),
        ('Look at that car! It ____ into the tree!', ['will crash', 'is going to crash', 'crashes', 'crashed'], 1, '眼前有迹象表明马上会发生，用 be going to。'),
        ("Tom and I ____ married in June; we've already booked the hotel.", ['get', 'are getting', 'got', 'will have got'], 1, '时间、地点都已安排好，用现在进行时表示将来。'),
        ("If you don't hurry, you ____ the train.", ['miss', 'will miss', 'missed', 'are missing'], 1, '真实条件句：从句一般现在时，主句 will + 动词原形。'),
        ('I promise I ____ tell anyone your secret.', ["won't", "don't", 'am not going', "didn't"], 0, '承诺用 will / won’t。am not going 后面缺 to。'),
        ('Call me when you ____ at the station.', ['will arrive', 'arrive', 'arrived', 'are going to arrive'], 1, 'when 引导的时间从句用一般现在时表示将来。'),
    ],
    'tense-past-perfect': [
        ('She recognised him at once because she ____ his photo online the week before.', ['sees', 'had seen', 'has seen', 'was seeing'], 1, '看照片发生在认出他之前，是“过去的过去”，用过去完成时。'),
        ("I ____ dinner when my friend called, so I said I wasn't hungry.", ['have had', 'had already had', 'was having', 'have'], 1, '朋友打电话之前已经吃过了，所以不饿，用过去完成时。'),
        ('By 2010, my parents ____ in the same house for thirty years.', ['lived', 'had lived', 'have lived', 'live'], 1, 'By + 过去时间：到那时为止持续的状态，用过去完成时。'),
        ('After she ____ her homework, she went out to play.', ['finishes', 'had finished', 'has finished', 'was finishing'], 1, '先完成作业再出去玩，先发生的动作用过去完成时。'),
        ("When I went back last summer, I didn't recognise the town. It ____ a lot since my previous visit.", ['changed', 'had changed', 'is changing', 'changes'], 1, '站在“去年夏天回去”那个过去的时间点，变化发生在那之前，用过去完成时 had changed。'),
        ('He told me he ____ the book twice.', ['reads', 'will read', 'had read', 'is reading'], 2, '转述时读书发生在“告诉我”之前，用过去完成时。'),
    ],
    'tense-perfect-continuous': [
        ("I ____ this book for three days, but I'm only on page 50.", ['have read', 'have been reading', 'read', 'had read'], 1, '动作从过去持续到现在、还没完成，用现在完成进行时。'),
        ('She ____ three cups of coffee this morning.', ['has been drinking', 'has drunk', 'drinks', 'is drinking'], 1, '强调已完成的数量（三杯），用现在完成时，不用进行时。'),
        ('How long ____ for the bus? You look frozen.', ['are you waiting', 'have you been waiting', 'do you wait', 'will you wait'], 1, 'How long 问到现在为止持续多久，用现在完成进行时。'),
        ('It ____ since this morning, and the roads are flooded.', ['has been raining', 'rains', 'is raining', 'had rained'], 0, 'since this morning：从早上一直下到现在，用现在完成进行时。'),
        ('I ____ for you for an hour! Where were you?', ['wait', 'have been waiting', 'waited', 'am waiting'], 1, '一直等到现在（还带着抱怨），用现在完成进行时。'),
        ('He ____ his car three times this year.', ['has been crashing', 'has crashed', 'crashes', 'had been crashing'], 1, '说次数（三次）用现在完成时。'),
    ],
    # ---------------- voice ----------------
    'voice-basic': [
        ('English ____ in many countries.', ['speaks', 'is spoken', 'is speaking', 'spoke'], 1, '英语“被说”，用被动 is spoken。'),
        ('The bridge ____ in 1937.', ['built', 'was built', 'is built', 'has built'], 1, '桥是“被建”的，发生在过去：was built。'),
        ('These photos ____ by my brother.', ['took', 'were taken', 'are taking', 'was taken'], 1, '照片是被拍的，主语是复数 photos，用 were taken。'),
        ('Tea ____ by hand on this farm.', ['picks', 'is picked', 'picked', 'is picking'], 1, '茶叶被人用手采摘，用一般现在时的被动 is picked。'),
        ('The letter ____ yesterday.', ["didn't send", "wasn't sent", "isn't sent", "didn't sent"], 1, '信“没有被寄出”，过去时的被动否定：wasn’t sent。'),
        ('The children ____ by their grandmother when their parents are at work.', ['look after', 'are looked after', 'looked after', 'are looking after'], 1, '孩子被照顾，短语动词的被动要保留介词：are looked after。'),
    ],
    'voice-tenses': [
        ('The road ____ at the moment, so we have to take another way.', ['is repairing', 'is being repaired', 'has repaired', 'repairs'], 1, '此刻正在被修：现在进行时的被动 is being repaired。'),
        ('All the tickets ____ by the time we got there.', ['sold', 'had been sold', 'have been sold', 'were selling'], 1, '我们到之前票已经被卖完：过去完成时的被动。'),
        ('Your order ____. You will receive it tomorrow.', ['has sent', 'has been sent', 'is sending', 'sent'], 1, '订单已经被寄出：现在完成时的被动 has been sent。'),
        ('The results ____ next Friday.', ['will announce', 'will be announced', 'announce', 'are announcing'], 1, '结果“将被公布”：will be announced。'),
        ('This work ____ finished before Friday.', ['must', 'must be', 'must have', 'must being'], 1, '情态动词的被动：must be + 过去分词。'),
        ('When I came back, my car ____.', ['had been moved', 'has been moved', 'was moving', 'moved'], 0, '我回来之前车已被挪走：过去完成时的被动。'),
    ],
    'voice-causative': [
        ("I'm going to ____ my hair cut tomorrow.", ['have', 'make', 'let', 'do'], 0, 'have something done：请别人替自己做（理发）。'),
        ('You should get your eyes ____.', ['test', 'tested', 'testing', 'to test'], 1, 'get something done：宾语后用过去分词。'),
        ('We had our house ____ last summer.', ['paint', 'painting', 'painted', 'to paint'], 2, 'have + 宾语 + 过去分词：房子是请人刷的。'),
        ('Which sentence means someone else repaired the roof for us?', ['We repaired the roof.', 'We had the roof repaired.', 'We had repaired the roof.', 'The roof repaired us.'], 1, 'had the roof repaired 是请人修；had repaired 是我们自己修好的过去完成时。'),
        ('She ____ her bag searched at the airport.', ['had', 'made', 'let', 'took'], 0, '经历了别人对自己做的事（包被搜查），也用 have something done。'),
        ('Where do you usually ____ your car serviced?', ['get', 'make', 'let', 'take'], 0, 'get something done：请人保养车。'),
    ],
    # ---------------- modal ----------------
    'modal-ability': [
        ('I ____ swim when I was five.', ['can', 'could', 'will be able', 'am able'], 1, '过去的能力用 could。'),
        ("Sorry, I ____ come to your party tomorrow. I have to work.", ["can't", "couldn't", "mustn't", "needn't"], 0, '现在说将来不能做某事，用 can’t。'),
        ('____ you help me with this box, please?', ['Could', 'Must', 'Should', 'Need'], 0, '礼貌地请求别人帮忙用 Could you…?'),
        ('Since he started lessons, he ____ play three songs on the guitar.', ['could', 'has been able to', 'can be', 'is able'], 1, 'can 没有完成时形式，现在完成时里用 has been able to。'),
        ("You ____ park here. It's a hospital entrance.", ["can't", "don't have to", "needn't", "couldn't"], 0, '不被允许：can’t。don’t have to / needn’t 是“不必”。'),
        ('After hours of searching, the firefighters ____ rescue the cat.', ['could', 'were able to', 'can', 'are able'], 1, '过去某一次经过努力做成了，用 was / were able to，不用 could。'),
    ],
    'modal-obligation': [
        ("You ____ wear a uniform at our school; it's a rule.", ['have to', "don't have to", "mustn't", "needn't"], 0, '规定要求的义务：have to。'),
        ("It's Sunday tomorrow, so I ____ get up early.", ["mustn't", "don't have to", 'have to', 'must'], 1, '星期天“不必”早起：don’t have to。mustn’t 是“禁止”。'),
        ('Students ____ use their phones during the test.', ["mustn't", "don't have to", "needn't", 'have to'], 0, '考试中禁止使用手机：mustn’t。'),
        ('You ____ bring food; lunch is provided.', ["needn't", "mustn't", 'must', 'have to'], 0, '提供午餐，所以“不必”带：needn’t。'),
        ("I think you ____ apologise to her. She's really upset.", ['ought to', "mustn't", "don't have to", "needn't"], 0, '给建议：ought to = should。'),
        ('Will we ____ show our passports at the border?', ['must', 'have to', 'should to', 'need'], 1, 'will 后面不能接 must，将来的义务用 will have to。'),
    ],
    'modal-deduction': [
        ('The lights are on. Someone ____ be at home.', ['must', "can't", "mustn't", "needn't"], 0, '有依据、几乎肯定的推测：must。'),
        ('She ____ be at work. I just saw her at the supermarket.', ['must', "can't", 'might', 'should'], 1, '有依据的否定推测（我刚看见她在超市）：can’t。'),
        ('Take an umbrella. It ____ rain later.', ['might', 'must', "can't", "needn't"], 0, '不确定的可能：might。'),
        ("You haven't eaten all day. You ____ be hungry.", ['must', "can't", 'might not', "needn't"], 0, '根据“一整天没吃饭”做出肯定的推测：must。'),
        ("I'm not sure, but the keys ____ be in the car.", ['could', 'must', "can't", 'should to'], 0, '不确定的可能：could / might / may。'),
        ('Which sentence shows the speaker is almost certain?', ['He might be ill.', 'He could be ill.', 'He must be ill.', 'He may be ill.'], 2, 'must 表示几乎肯定；might / could / may 只是可能。'),
    ],
    'modal-past': [
        ('The road is wet. It ____ during the night.', ['must rain', 'must have rained', "can't have rained", 'should have rained'], 1, '对过去的肯定推测：must have done。'),
        ('You ____ told me you were coming! I would have cooked more.', ['should have', 'must have', "can't have", 'would'], 0, '本该做却没做（带责备）：should have done。'),
        ('He ____ the bus; he arrived on time.', ['must have missed', "can't have missed", 'should have missed', 'might miss'], 1, '他准时到了，所以“不可能错过了车”：can’t have done。'),
        ("I'm not sure why she was late. She ____ stuck in traffic.", ['might have got', 'must get', "can't have got", 'should have got'], 0, '对过去不确定的推测：might have done。'),
        ('We ____ so much food. Half of it was thrown away.', ["shouldn't have bought", "mustn't have bought", "can't buy", "needn't buy"], 0, '做了不该做的事（买太多）：shouldn’t have done。'),
        ('You ____ about the exam. You passed easily.', ["needn't have worried", "mustn't have worried", "can't have worried", "didn't need worry"], 0, '做了其实没必要做的事：needn’t have done。'),
    ],
    # ---------------- clause ----------------
    'clause-relative': [
        ('The man ____ car was stolen called the police.', ['who', 'whose', 'which', 'whom'], 1, '“他的车”，表示所属关系用 whose。'),
        ('I lost the watch ____ my father gave me.', ['who', 'which', 'where', 'whose'], 1, '先行词是物（watch），在从句中作宾语，用 which / that。'),
        ('Do you remember the day ____ we first met?', ['which', 'when', 'who', 'what'], 1, '先行词是时间，在从句中作时间状语，用 when。'),
        ('She is the singer ____ everyone is talking about.', ['who', 'which', 'where', 'whose'], 0, '先行词是人，用 who / that（作介词 about 的宾语）。'),
        ('This is the reason ____ I came.', ['why', 'which', 'where', 'what'], 0, 'the reason 后表示原因的定语从句用 why。'),
    ],
    'clause-noun': [
        ('Can you tell me ____?', ['what time it is', 'what time is it', 'it is what time', 'what is time'], 0, '宾语从句用陈述语序：what time it is。'),
        ('____ we need more time is clear.', ['That', 'What', 'Which', 'If'], 0, '主语从句本身完整（we need more time），用 that 引导。'),
        ('____ he will join us is still unknown.', ['Whether', 'If', 'That', 'What'], 0, '句首的主语从句表示“是否”，只能用 whether，不用 if。'),
        ('The fact ____ she lied upset me.', ['that', 'what', 'which', 'whether'], 0, '同位语从句说明 fact 的内容，用 that。'),
        ('What surprised me was ____ he spoke Chinese so well.', ['that', 'what', 'which', 'if'], 0, '表语从句完整，用 that 引导。'),
        ('Do you know ____ this bag belongs to?', ['who', 'whose', 'which', 'what'], 0, '问“属于谁”：who … belongs to，陈述语序。'),
    ],
    'clause-adverb': [
        ("I'll wait here ____ you come back.", ['until', 'unless', 'although', 'so'], 0, '一直等到你回来：until。'),
        ("We didn't go out ____ it was raining.", ['because', 'although', 'unless', 'so that'], 0, '下雨是没出门的原因：because。'),
        ('Turn off the lights ____ you leave the room.', ['before', 'until', 'although', 'because of'], 0, '离开房间之前关灯：before。'),
        ('____ I was walking home, I saw an old friend.', ['While', 'During', 'Unless', 'Although'], 0, 'while 后接从句；during 后只能接名词。'),
        ('He spoke slowly ____ everyone could understand him.', ['so that', 'because', 'although', 'until'], 0, '目的状语从句：so that。'),
        ('____ you finish your homework, you can watch TV.', ['Once', 'Unless', 'Although', 'Because of'], 0, 'once = 一旦（做完）。'),
        ('I have known her ____ we were children.', ['since', 'for', 'when', 'until'], 0, '从小时候到现在：since + 过去的时间点或从句。'),
    ],
    'clause-nondefining': [
        ('My sister, ____ lives in Canada, is visiting us next week.', ['who', 'that', 'which', 'whom'], 0, '非限制性从句修饰人用 who，不能用 that。'),
        ('Beijing, ____ is the capital of China, has a long history.', ['which', 'that', 'where', 'what'], 0, '非限制性从句修饰物用 which，不能用 that；从句缺主语，不用 where。'),
        ('He failed the test, ____ surprised everyone.', ['which', 'that', 'what', 'who'], 0, 'which 指代前面整句话的内容。'),
        ('Mr Li, ____ son is in my class, is a doctor.', ['whose', 'who', 'which', 'that'], 0, '“他的儿子”，用 whose。'),
        ('We visited Hangzhou, ____ we spent three days by the lake.', ['where', 'which', 'that', 'when'], 0, '从句完整、表示地点，用 where。'),
        ('Which sentence is punctuated correctly?', ['My father who is a teacher, loves music.', 'My father, who is a teacher, loves music.', 'My father, that is a teacher, loves music.', 'My father who is a teacher loves, music.'], 1, '父亲只有一位，补充说明用非限制性从句：两边加逗号，不用 that。'),
    ],
    'clause-reported': [
        ('"I will call you tomorrow," he said. → He said he ____ me the next day.', ['will call', 'would call', 'calls', 'called'], 1, '转述时 will 后移为 would。'),
        ('"Where do you live?" she asked. → She asked me where ____.', ['do I live', 'I lived', 'did I live', 'lived I'], 1, '间接疑问句用陈述语序（主语在前）；转述时时态一般后移（情况现在仍成立时也可以不后移）。'),
        ('"Don\'t be late," the teacher said. → The teacher told us ____ late.', ['not to be', "don't be", 'to not being', 'not be'], 0, '转述否定命令：tell somebody not to do。'),
        ('"I have lost my phone," Tom said. → Tom said he ____ his phone.', ['has lost', 'had lost', 'was losing', 'loses'], 1, '现在完成时转述后移为过去完成时。'),
        ('She ____ that she was moving to Beijing.', ['said', 'told', 'spoke', 'asked'], 0, 'say (that)…；tell 后面必须先接人。'),
        ('"Can you swim?" he asked me. → He asked me ____ swim.', ['if I could', 'can I', 'that I could', 'could I'], 0, '一般疑问句转述用 if / whether + 陈述语序，can 后移为 could。'),
    ],
    # ---------------- conditional ----------------
    'conditional-real': [
        ('If you ____ hard, you will pass.', ['study', 'will study', 'studied', 'had studied'], 0, '真实条件：if 从句用一般现在时。'),
        ('If I see Tom, I ____ him your message.', ['give', 'will give', 'gave', 'would have given'], 1, '主句用 will + 动词原形。'),
        ('If you press this button, the machine ____.', ['stops', 'would stop', 'had stopped', 'stopping'], 0, '总是如此的规律，主句也可用一般现在时。'),
        ("If you don't hurry, you ____ late.", ['are', 'will be', 'were', 'would have been'], 1, '真实条件下的结果：will be。'),
    ],
    'conditional-unless': [
        ("Unless you ____ a ticket, you can't go in.", ['have', "don't have", 'will have', 'had'], 0, 'unless = if not，后面不再用否定，也用一般现在时表示将来。'),
        ("Which sentence means the same as \"If you don't apologise, she won't forgive you\"?", ["Unless you apologise, she won't forgive you.", "Unless you don't apologise, she won't forgive you.", "If you apologise, she won't forgive you.", "Unless she forgives you, you won't apologise."], 0, 'if you don’t apologise = unless you apologise。'),
        ("I'll lend you the money ____ you pay me back next week.", ['as long as', 'unless', 'even if', 'although'], 0, 'as long as = 只要（满足这个条件）。'),
        ("We'll go hiking tomorrow ____ it rains.", ['unless', 'if', 'as long as', 'provided'], 0, '除非下雨（下雨就不去）：unless。'),
        ('Take your phone ____ you get lost.', ['in case', 'unless', 'as long as', 'even if'], 0, 'in case = 以防万一。'),
        ("____ you leave now, you'll catch the last train.", ['Provided that', 'Unless', 'Even though', 'In case'], 0, 'provided that = 只要，引出条件。'),
    ],
    'conditional-modal': [
        ('If you feel ill, you ____ see a doctor.', ['should', 'would have', 'had', 'were'], 0, '条件句主句给建议：should。'),
        ('If you see Anna, ____ her I said hello.', ['tell', 'telling', 'told', 'to tell'], 0, '条件句的主句可以是祈使句，用动词原形开头。'),
        ('If it stops raining, we ____ go to the park.', ['might', 'would have', 'had', 'were'], 0, '主句表示可能：might + 动词原形。'),
        ('If you want to pass, you ____ work harder.', ['must', 'would have', 'had', 'were'], 0, '主句表示必须：must + 动词原形。'),
        ("If you're cold, I ____ close the window for you.", ['can', 'could have', 'had', 'was'], 0, '主句表示提议、能力：can + 动词原形。'),
        ('If you finish the test early, you ____ leave the room quietly.', ['may', 'would have', 'had', 'were'], 0, '主句表示许可：may + 动词原形。'),
        ("If they don't reply by Friday, we ____ have to call them.", ['will', 'would have', 'had', 'were'], 0, '将来的义务：will have to。'),
        ('If you ____ to come, just let me know.', ['want', 'will want', 'wanted', 'would want'], 0, '条件从句用一般现在时。'),
    ],
    # ---------------- subjunctive ----------------
    'subjunctive-now': [
        ('If I ____ a car, I would drive you home.', ['have', 'had', 'will have', 'have had'], 1, '与现在事实相反：if 从句用过去式 had。'),
        ('She would travel more if she ____ so busy.', ["isn't", "weren't", "won't be", "hasn't been"], 1, '与现在事实相反，be 动词常用 were / weren’t。'),
        ('If we lived near the sea, we ____ swimming every day.', ['go', 'will go', 'would go', 'went'], 2, '主句用 would + 动词原形。'),
        ('What would you do if you ____ a million dollars?', ['win', 'won', 'will win', 'have won'], 1, '假设的情况：从句用过去式。'),
        ('If I were taller, I ____ play basketball for the school team.', ['can', 'could', 'will', 'am able'], 1, '主句用 could + 动词原形表示假设中的能力。'),
    ],
    'subjunctive-past': [
        ('If I ____ about the party, I would have come.', ['know', 'knew', 'had known', 'have known'], 2, '与过去事实相反：if 从句用过去完成时。'),
        ('She would have caught the bus if she ____ up earlier.', ['got', 'had got', 'has got', 'would get'], 1, '与过去事实相反：从句用 had done。'),
        ("If it hadn't rained, we ____ a picnic.", ['have', 'will have', 'would have had', 'had had'], 2, '主句用 would have done。'),
        ('If you had asked me, I ____ you.', ['would have helped', 'will help', 'helped', 'had helped'], 0, '与过去事实相反的主句：would have helped。'),
        ('Which sentence talks about the past?', ['If I had money, I would buy it.', 'If I had had money, I would have bought it.', 'If I have money, I will buy it.', 'If I have money, I buy it.'], 1, 'had had … would have bought 是与过去事实相反；第一句是与现在事实相反。'),
    ],
    'subjunctive-mixed': [
        ('If I had learned to drive, I ____ the bus every day now.', ["wouldn't take", "wouldn't have taken", "won't take", "hadn't taken"], 0, '过去的条件（没学开车）→ 现在的结果（now），主句用 would + 动词原形。'),
        ('If he weren\'t so careless, he ____ his phone yesterday.', ["wouldn't lose", "wouldn't have lost", "won't lose", "didn't lose"], 1, '现在一贯的性格 → 过去的结果（yesterday），主句用 would have done。'),
        ('If they had booked earlier, they ____ on the plane now.', ['would be', 'would have been', 'will be', 'are'], 0, '过去没早订 → 现在不在飞机上：would be。'),
        ('If she spoke French, she ____ the job in Paris last year.', ['would get', 'would have got', 'will get', 'got'], 1, '现在不会法语 → 去年没得到那份工作：would have got。'),
        ("If you had taken my advice, you ____ in this mess now.", ["wouldn't be", "wouldn't have been", "won't be", "aren't"], 0, '过去没听建议 → 现在的麻烦：would be。'),
        ('If he ____ the train, he would be here by now.', ["didn't miss", "hadn't missed", "doesn't miss", "won't miss"], 1, '条件是过去的事（错过了火车），用 had done；结果是现在（by now）。'),
        ('Which sentence is about a past condition and a present result?', ['If I had saved money, I would be rich now.', 'If I saved money, I would be rich.', 'If I had saved money, I would have been rich then.', 'If I save money, I will be rich.'], 0, 'had saved（过去）+ would be … now（现在）是错综条件句。'),
        ("If I weren't afraid of heights, I ____ that mountain with you last weekend.", ['would climb', 'would have climbed', 'will climb', 'climbed'], 1, '现在怕高 → 上周末没去爬山：would have climbed。'),
    ],
    'subjunctive-wish': [
        ('I wish I ____ more time to read.', ['have', 'had', 'will have', 'am having'], 1, 'wish 表示现在不能实现的愿望，用过去式。'),
        ("I wish I ____ that. I'm sorry.", ["didn't say", "hadn't said", "don't say", "won't say"], 1, '对过去的后悔：wish + had done。'),
        ('If only it ____ raining! I want to go out.', ['stops', 'would stop', 'stopped', 'has stopped'], 1, '希望情况发生改变（带抱怨）：if only / wish + would do。'),
        ("It's high time the government ____ something about it.", ['does', 'did', 'will do', 'has done'], 1, "It's (high) time + 主语 + 过去式：早该做了。"),
        ("I'd rather you ____ smoke in here.", ["don't", "didn't", "won't", 'not'], 1, "would rather + 从句，用过去式表示现在或将来。"),
        ('She wishes she ____ to the party last night.', ['went', 'had gone', 'goes', 'would go'], 1, '对过去（last night）的遗憾：wish + had done。'),
    ],
    # ---------------- nonfinite ----------------
    'nonfinite-infinitive': [
        ('I want ____ a new phone.', ['buy', 'to buy', 'buying', 'bought'], 1, 'want 后接不定式 to do。'),
        ("It's easy ____ this game.", ['learn', 'to learn', 'learning', 'learned'], 1, "It's + 形容词 + to do。"),
        ('She went to the shop ____ some bread.', ['buy', 'to buy', 'buying', 'for buy'], 1, '表示目的用不定式 to buy。'),
        ('My parents let me ____ out late on Saturdays.', ['stay', 'to stay', 'staying', 'stayed'], 0, 'let + 宾语 + 不带 to 的动词原形。'),
        ('He asked me ____ the door.', ['close', 'to close', 'closing', 'closed'], 1, 'ask somebody to do something。'),
        ("I don't know what ____ next.", ['do', 'to do', 'doing', 'did'], 1, '疑问词 + 不定式：what to do。'),
    ],
    'nonfinite-gerund': [
        ('Would you mind ____ the window?', ['open', 'to open', 'opening', 'opened'], 2, 'mind 后接动名词。'),
        ('____ too much sugar is bad for you.', ['Eat', 'Eating', 'Ate', 'Eaten'], 1, '动名词短语作主语。'),
        ('He gave up ____ last year.', ['smoke', 'to smoke', 'smoking', 'smoked'], 2, 'give up 后接动名词。'),
        ('I remember ____ this film when I was a child.', ['see', 'to see', 'seeing', 'seen'], 2, 'remember doing：记得做过；remember to do：记得要去做。'),
        ("She's used to ____ up early.", ['get', 'getting', 'got', 'gets'], 1, 'be used to 中的 to 是介词，后接动名词。'),
    ],
    'nonfinite-participle': [
        ('The film was so ____ that I fell asleep.', ['bored', 'boring', 'bore', 'bores'], 1, '让人觉得无聊用 -ing（boring）；人感到无聊用 -ed（bored）。'),
        ('I was ____ by the news.', ['surprising', 'surprised', 'surprise', 'to surprise'], 1, '人“感到惊讶”用 surprised。'),
        ('Most of the people ____ to the party were students.', ['invited', 'inviting', 'invite', 'were invited'], 0, '人是“被邀请的”，过去分词作后置定语。'),
        ('Who is the man ____ to your father?', ['talks', 'talking', 'talked', 'is talking'], 1, '正在和你父亲说话的人：现在分词作后置定语。'),
        ('We found a wallet ____ on the street.', ['lying', 'lay', 'lain', 'lies'], 0, '钱包“躺在”街上，主动、正在的状态用 lying。'),
        ('Have you read the report ____ last week?', ['publishing', 'published', 'publish', 'to publish'], 1, '报告是“被发表的”，用过去分词。'),
        ("There's a ____ window in the kitchen; be careful.", ['breaking', 'broken', 'broke', 'break'], 1, '已经破了的窗户：过去分词作定语 broken。'),
    ],
    'nonfinite-clause': [
        ('____ from the top of the hill, the town looks beautiful.', ['Seeing', 'Seen', 'See', 'Having seen'], 1, '小镇是“被看”的，用过去分词 Seen。'),
        ('____ her homework, she went to bed.', ['Having finished', 'Finished', 'Being finished', 'To finish'], 0, '先完成作业再睡觉，先发生的主动动作用 Having done。'),
        ('____ in 1900, the building is now a museum.', ['Building', 'Built', 'Having built', 'To build'], 1, '建筑是“被建”的：Built in 1900。'),
        ('He sat by the window, ____ a book.', ['reading', 'read', 'to reading', 'was reading'], 0, '伴随状态，主动：现在分词 reading。'),
        ('____ tired, I went to bed early.', ['Feeling', 'Felt', 'To feel', 'Feel'], 0, '原因：我“感到”累，主动，用 Feeling。'),
        ('____ the right answer, he raised his hand.', ['Knowing', 'Known', 'Knew', 'Know'], 0, '他知道答案，主动，用现在分词 Knowing。'),
    ],
    # ---------------- agreement ----------------
    'agreement-head': [
        ('The students in my class ____ very friendly.', ['is', 'are', 'was', 'has been'], 1, '主语中心词是 students（复数），in my class 只是修饰。'),
        ('One of my friends ____ in Canada.', ['live', 'lives', 'living', 'are living'], 1, '中心词是 one，谓语用单数。'),
        ('The price of vegetables ____ gone up.', ['have', 'has', 'are', 'were'], 1, '中心词是 price（单数），不是 vegetables。'),
        ('Mathematics ____ my favourite subject.', ['is', 'are', 'were', 'have been'], 0, '学科名 mathematics 虽以 -s 结尾，但作单数。'),
        ('Three hours ____ not enough to finish this exam.', ['are', 'is', 'were', 'have'], 1, '时间、距离、金额作为一个整体看，谓语用单数。'),
    ],
    'agreement-each': [
        ('Every student ____ to bring a pen.', ['need', 'needs', 'are needing', 'have needed'], 1, 'every + 单数名词，谓语用单数。'),
        ('Somebody ____ left a bag in the classroom.', ['have', 'has', 'are', 'were'], 1, 'somebody 作单数。'),
        ('Each of the rooms ____ its own bathroom.', ['have', 'has', 'are having', 'were having'], 1, 'each of + 复数名词，谓语跟 each 用单数。'),
        ('None of the information ____ useful.', ['were', 'was', 'are', 'have been'], 1, 'none of + 不可数名词，谓语用单数。'),
        ('Everyone in the office ____ the news.', ['know', 'knows', 'are knowing', 'have known'], 1, 'everyone 作单数。'),
        ('Either of the dates ____ fine for me.', ['are', 'is', 'were', 'have been'], 1, 'either of + 复数名词作主语，谓语用单数。'),
    ],
    'agreement-either': [
        ('Neither my brother nor my parents ____ at home now.', ['is', 'are', 'was', 'has been'], 1, 'neither … nor … 就近一致：靠近谓语的是 parents。'),
        ('Either you or he ____ to go.', ['have', 'has', 'are', 'were'], 1, 'either … or … 就近一致：靠近谓语的是 he。'),
        ('Tom, as well as his friends, ____ coming tonight.', ['are', 'is', 'were', 'have'], 1, 'as well as 引出的部分不影响谓语，跟 Tom 一致。'),
        ('Bread and butter ____ my usual breakfast.', ['is', 'are', 'were', 'have'], 0, 'bread and butter 指一种食物（黄油面包），作单数。'),
        ('The teacher, together with her students, ____ planting trees.', ['are', 'is', 'were', 'have'], 1, 'together with 不影响谓语，跟 the teacher 一致。'),
        ('My friend and colleague, Mr Wang, ____ joining us.', ['are', 'is', 'were', 'have'], 1, '朋友和同事是同一个人（王先生），谓语用单数。'),
        ('Both the bus and the train ____ late this morning.', ['was', 'were', 'is', 'has'], 1, 'both … and … 连接两个主语，谓语用复数。'),
    ],
    # ---------------- determiner ----------------
    'det-article': [
        ('I saw ____ elephant at the zoo.', ['a', 'an', 'the', '/'], 1, 'elephant 以元音音素开头，用 an。'),
        ('____ sun rises in the east.', ['A', 'An', 'The', '/'], 2, '世上独一无二的事物用 the。'),
        ('She is ____ honest girl.', ['a', 'an', 'the', '/'], 1, 'honest 的 h 不发音，以元音音素开头，用 an。'),
        ('Can you close ____ door, please?', ['a', 'an', 'the', '/'], 2, '说话双方都知道是哪扇门，用 the。'),
        ("I'd like ____ cup of tea.", ['a', 'an', 'the', '/'], 0, 'cup 以辅音音素开头，第一次提到用 a。'),
        ('He goes to the gym three times ____ week.', ['a', 'an', 'the', '/'], 0, '“每…”用 a：three times a week。'),
    ],
    'det-zero': [
        ('We have ____ lunch at twelve.', ['a', 'the', '/', 'an'], 2, '一日三餐前一般不用冠词。'),
        ('He goes to school by ____ bike.', ['a', 'the', '/', 'an'], 2, 'by + 交通工具，中间不用冠词。'),
        ('____ music can help you relax.', ['The', 'A', '/', 'An'], 2, '泛指的不可数名词不用冠词。'),
        ("Let's play ____ football after school.", ['a', 'the', '/', 'an'], 2, '球类运动前不用冠词。'),
        ('____ Yangtze is the longest river in China.', ['The', 'A', '/', 'An'], 0, '江河名前用 the。'),
        ("I love ____ cats, but I'm allergic to them.", ['the', 'a', '/', 'an'], 2, '泛指一类事物用复数，不加冠词；the cats 是指特定的猫。'),
    ],
    'det-quantity': [
        ('How ____ apples do you want?', ['much', 'many', 'little', 'a little'], 1, 'apples 是可数名词复数，用 how many。'),
        ("There are ____ people in the park today; it's almost empty.", ['a few', 'few', 'many', 'much'], 1, 'few = 几乎没有，带否定意味，和 almost empty 一致。'),
        ('Can I have ____ water, please?', ['some', 'many', 'a few', 'few'], 0, '不可数名词 water；表示请求的疑问句里用 some。'),
        ("We don't have ____ time. Hurry up!", ['many', 'much', 'a few', 'few'], 1, 'time 不可数，否定句用 much。'),
        ('I need ____ information about the course.', ['an', 'some', 'many', 'a few'], 1, 'information 不可数，不能用 an / many / a few。'),
        ('She has ____ friends here, so she never feels lonely.', ['a few', 'few', 'a little', 'little'], 0, 'a few = 有几个（肯定意味）；friends 可数，不用 a little。'),
    ],
    # ---------------- compare ----------------
    'compare-basic': [
        ('My bag is ____ than yours.', ['heavy', 'heavier', 'heaviest', 'more heavy'], 1, '辅音 + y 结尾，变 y 为 i 加 -er：heavier。'),
        ('This is the ____ day of my life!', ['happy', 'happier', 'happiest', 'most happy'], 2, '最高级：the happiest。'),
        ('She runs ____ than her brother.', ['fast', 'faster', 'fastest', 'more fast'], 1, 'than 前用比较级：faster。'),
        ('Which is ____, a cat or a dog?', ['big', 'bigger', 'biggest', 'more big'], 1, '两者比较用比较级；重读闭音节双写 g：bigger。'),
        ('This book is ____ than that one.', ['good', 'better', 'best', 'gooder'], 1, 'good 的比较级是不规则的 better。'),
        ("It's the ____ expensive restaurant in town.", ['more', 'most', 'much', 'very'], 1, '多音节形容词的最高级：the most expensive。'),
    ],
    'compare-pattern': [
        ('He is not ____ tall as his father.', ['as', 'such', 'more', 'than'], 0, 'not as (so) … as：不如……那样。'),
        ('The more you practise, ____ you will become.', ['the better', 'better', 'the best', 'best'], 0, 'the + 比较级 …，the + 比较级 …：越……越……'),
        ('This room is ____ bigger than that one.', ['very', 'much', 'more', 'most'], 1, '修饰比较级用 much / far / a lot，不用 very。'),
        ('My phone is the same ____ yours.', ['as', 'like', 'than', 'with'], 0, 'the same as：和……一样。'),
        ('Prices are getting ____.', ['higher and higher', 'high and high', 'more high', 'the higher'], 0, '比较级 and 比较级：越来越……'),
        ("It's twice ____ as it was last year.", ['as expensive', 'more expensive', 'expensive', 'the most expensive'], 0, '倍数 + as … as：twice as expensive as。'),
    ],
    # ---------------- link ----------------
    'link-contrast': [
        ("____ he is rich, he isn't happy.", ['Although', 'Despite', 'However', 'Because'], 0, '后面是完整从句，用 although；despite 后接名词。'),
        ('____ the rain, we played football.', ['Although', 'In spite of', 'However', 'Even though'], 1, 'the rain 是名词短语，用 in spite of / despite。'),
        ('I like coffee, ____ my wife prefers tea.', ['whereas', 'despite', 'however', 'although of'], 0, 'whereas 连接两个对比的分句。however 不能直接用逗号连接两个句子。'),
        ('She is very clever. She is, ____, rather lazy.', ['however', 'although', 'despite', 'even though'], 0, 'however 是副词，可以插在句中，用逗号隔开。'),
        ("____ he tried hard, he couldn't open the door.", ['Even though', 'Despite', 'In spite of', 'However'], 0, '后面是完整从句，用 even though。'),
        ('Despite ____ tired, she kept working.', ['being', 'be', 'she was', 'to be'], 0, 'despite 是介词，后接动名词 being。'),
    ],
    'link-cause': [
        ('We stayed at home ____ the rain.', ['because', 'because of', 'so', 'as a result'], 1, 'the rain 是名词，用 because of。'),
        ('____ it was late, we took a taxi.', ['As', 'So', 'Because of', 'Therefore'], 0, 'as 引导原因从句，放在句首也可以。'),
        ('He missed the bus, ____ he was late for school.', ['so', 'because', 'because of', 'due to'], 0, '前因后果，用 so 引出结果。'),
        ('The match was cancelled ____ bad weather.', ['because', 'due to', 'so', 'therefore'], 1, 'bad weather 是名词短语，用 due to。'),
        ('She studied very hard. ____, she passed the exam.', ['Therefore', 'Because', 'Because of', 'Due to'], 0, '新句子开头引出结果，用副词 therefore。'),
        ('"Why were you late?" "____ my alarm didn\'t go off."', ['Because', 'So', 'Because of', 'Therefore'], 0, '回答 why 的问题用 because + 从句。'),
    ],
    'link-purpose': [
        ('She saved money ____ buy a new laptop.', ['in order to', 'so that', 'such that', 'for'], 0, '后面是动词原形，用 in order to。so that 后要接从句。'),
        ('Speak louder ____ everyone can hear you.', ['so that', 'in order to', 'such', 'so as'], 0, '后面是完整从句，用 so that。'),
        ('It was ____ a hot day that we went swimming.', ['so', 'such', 'very', 'too'], 1, 'such + a + 形容词 + 名词 + that。'),
        ('He was ____ tired that he fell asleep at once.', ['such', 'so', 'too', 'very'], 1, 'so + 形容词 + that。'),
        ('I wrote it down ____ forget it.', ['so as not to', 'so not to', 'in order not', 'so that not'], 0, '否定的目的：so as not to / in order not to + 动词原形。'),
        ('They are ____ kind people that everyone likes them.', ['so', 'such', 'so a', 'such a'], 1, 'such + 形容词 + 复数名词，复数前没有 a。'),
    ],
    # ---------------- prep ----------------
    'prep-time-place': [
        ('My birthday is ____ May 5th.', ['in', 'on', 'at', 'by'], 1, '具体某一天用 on。'),
        ('The shop opens ____ nine o’clock.', ['in', 'on', 'at', 'by'], 2, '钟点用 at。'),
        ("There's a picture ____ the wall.", ['in', 'on', 'at', 'to'], 1, '挂在墙面上用 on。'),
        ('We live ____ Beijing.', ['in', 'on', 'at', 'to'], 0, '城市、国家等较大的地方用 in。'),
        ("Let's meet ____ Monday morning.", ['in', 'on', 'at', 'by'], 1, '某一天的上午、下午用 on：on Monday morning。'),
        ("I'm waiting ____ the bus stop.", ['at', 'in', 'on', 'to'], 0, '在某个地点（站、门口）用 at。'),
    ],
    'prep-pattern': [
        ('My brother is really good ____ cooking.', ['at', 'in', 'on', 'for'], 0, 'be good at：擅长。'),
        ("I'm afraid ____ dogs.", ['of', 'from', 'with', 'about'], 0, 'be afraid of：害怕。'),
        ('Whether we go camping depends ____ how much time we have.', ['on', 'of', 'from', 'at'], 0, 'depend on：取决于。'),
        ('He apologised ____ being late.', ['for', 'of', 'about', 'to'], 0, 'apologise (to somebody) for something。'),
        ('Are you interested ____ joining our club?', ['in', 'on', 'at', 'for'], 0, 'be interested in doing。'),
        ('This bag belongs ____ my sister.', ['to', 'for', 'with', 'of'], 0, 'belong to：属于。'),
    ],
    # ---------------- emphasis ----------------
    'emph-cleft': [
        ('It was Tom ____ broke the window.', ['who', 'which', 'what', 'where'], 0, '强调句强调人可以用 who 或 that。'),
        ('It is not money ____ makes people happy.', ['that', 'what', 'which', 'where'], 0, '强调句 It is … that …，强调 not money。'),
        ('What we really need ____ more practice, not more tests.', ['is', 'are', 'was being', 'be'], 0, 'What 从句作主语，谓语用单数 is。'),
        ('It was in 2019 ____ I moved to Shanghai.', ['that', 'when', 'which', 'what'], 0, '强调时间状语时，强调句仍用 that，不用 when。'),
        ('All I want ____ some sleep.', ['is', 'are', 'were', 'be'], 0, 'All I want 作主语，谓语用单数 is。'),
        ('Which sentence emphasises WHO helped you?', ['My sister helped me.', 'It was my sister who helped me.', 'What my sister did was help me.', 'My sister, who helped me, is kind.'], 1, 'It was … who … 把“是谁”放在焦点上。'),
    ],
    'emph-inversion': [
        ('Never ____ such a beautiful sunset.', ['I have seen', 'have I seen', 'I saw', 'saw I'], 1, '否定词 never 放句首，助动词提前：have I seen。'),
        ('Hardly ____ down when the phone rang.', ['I had sat', 'had I sat', 'I sat', 'sat I'], 1, 'Hardly … when … 句首倒装：had I sat。'),
        ('Only then ____ the truth.', ['I realised', 'did I realise', 'I did realise', 'realised I'], 1, 'Only + 状语放句首，主句部分倒装：did I realise。'),
        ('Under no circumstances ____ leave the room.', ['you should', 'should you', 'you must', 'must not you'], 1, '否定短语 under no circumstances 放句首，情态动词提前。'),
        ('Not only ____ late, but he also forgot his books.', ['he was', 'was he', 'he is', 'did he be'], 1, 'Not only 放句首，前半句倒装：was he。'),
        ('Little ____ that she was being watched.', ['she knew', 'did she know', 'she did know', 'knew she'], 1, 'Little（几乎不）放句首表示否定，助动词提前：did she know。'),
    ],
}


def _shuffled(prompt, options, answer):
    """A fixed, prompt-seeded order for the stored options, so answers are not always in the same place."""
    rnd = random.Random(int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16))
    order = list(range(len(options)))
    rnd.shuffle(order)
    return [options[i] for i in order], order.index(answer)


def install(c):
    """Bring every grammar point to ten published questions (migration grammar-2.1)."""
    if c.execute("SELECT 1 FROM migrations WHERE version='grammar-2.1'").fetchone():
        return
    import next_service as nx
    for node, items in EXTRA.items():
        topic = c.execute('SELECT topic FROM subskills WHERE id=?', (node,)).fetchone()
        if not topic:
            continue
        level = nx.node_level(node)
        for prompt, options, answer, explanation in items:
            if c.execute('SELECT 1 FROM questions WHERE node=? AND prompt=?', (node, prompt)).fetchone():
                continue
            opts, ans = _shuffled(prompt, options, answer)
            c.execute("INSERT INTO questions(topic,prompt,options,answer,explanation,node,status,difficulty) VALUES(?,?,?,?,?,?,'published',?)",
                      (topic[0], prompt, json.dumps(opts, ensure_ascii=False), ans, explanation, node,
                       'easy' if level == 'A2' else 'hard' if level in ('B2', 'C1') else 'medium'))
    c.execute("INSERT INTO migrations VALUES('grammar-2.1')")


# ---------------------------------------------------------------- drawing questions

def draw(c, node, k=4, seed=None):
    """k published questions on a point in random order, each with its options shuffled. The client sends back the
    original option index (map[j]), so the stored answer never leaves the server."""
    rows = c.execute("SELECT id, prompt, options FROM questions WHERE node=? AND status='published'", (node,)).fetchall()
    rnd = random.Random(seed)
    rows = rnd.sample(rows, min(k, len(rows)))
    out = []
    for r in rows:
        opts = json.loads(r['options'])
        order = list(range(len(opts)))
        rnd.shuffle(order)
        out.append({'id': r['id'], 'prompt': r['prompt'], 'options': [opts[i] for i in order], 'map': order})
    return out


def variant(c, node, exclude, k):
    """Another question on the same point for a grammar mistake in review: the k-th of the others in turn, so the rule is
    what is practised, not the memory of one item."""
    rows = c.execute("SELECT id, prompt, options FROM questions WHERE node=? AND status='published' AND id!=? ORDER BY id", (node, exclude)).fetchall()
    if not rows:
        return None
    r = rows[k % len(rows)]
    opts = json.loads(r['options'])
    order = list(range(len(opts)))
    random.Random(r['id'] * 31 + k).shuffle(order)
    return {'id': r['id'], 'prompt': r['prompt'], 'options': [opts[i] for i in order], 'map': order}


# ---------------------------------------------------------------- mixed rounds

def _interleave(items, rnd):
    """Shuffle, then avoid two questions on the same point in a row where the mix allows it."""
    rnd.shuffle(items)
    for i in range(1, len(items)):
        if items[i]['node'] == items[i - 1]['node']:
            j = next((j for j in range(i + 1, len(items)) if items[j]['node'] != items[i - 1]['node']), None)
            if j is not None:
                items[i], items[j] = items[j], items[i]
    return items


def mix_nodes(c, uid, now=None):
    """The points today's mixed review is made of: flagged ones first, then those whose re-check has come."""
    import next_service as nx
    if not uid:
        return []
    states = nx.graph_states(c, uid)
    watch = [n for n, s in states.items() if s['status'] == 'watch']
    return watch + [n for n in due(c, uid, now) if n not in watch]


def mix(c, uid, pair=None, topic=None, level=None, seed=None):
    """An interleaved round of grammar questions across several points (questions on different points mixed together
    make the learner decide which rule applies, which is what using a language asks for).
    pair 'a,b': a confusable pair, three questions each; topic: one question on each point of a topic;
    otherwise today's review (flagged and due points), or, with none, practice on the learner's next points."""
    import next_service as nx, graph_links as GL
    rnd = random.Random(seed)
    meta = nx.nodes_meta(c)
    note, kind, left = None, 'due', 0
    if pair:
        nodes = [n for n in pair.split(',')[:2] if n in meta]
        if len(nodes) != 2:
            return {'error': '没有这组语法点'}, 404
        kind, per, note = 'pair', 3, GL.pair_note(*nodes)
    elif topic:
        nodes = [n for n, m in meta.items() if m['topic'] == topic]
        if not nodes:
            return {'error': '没有这一类'}, 404
        kind, per = 'topic', 1
    else:
        nodes = mix_nodes(c, uid)
        left = max(0, len(nodes) - 6)
        nodes = nodes[:6]
        if not nodes:  # nothing due: a practice round on the next points at the learner's level
            kind = 'practice'
            prof = nx.profile(c, uid) or {}
            lv = prof.get('level') or (level if level in nx.LEVELS else 'B1')
            states = nx.graph_states(c, uid)
            nodes = [n for n in nx.LEVEL_NODES.get(lv, ()) if n in meta and states[n]['status'] != 'solid']
            rnd.shuffle(nodes)
            nodes = nodes[:4]
        per = min(3, -(-4 // max(1, len(nodes))))  # at least four questions in a round
    items = []
    for n in nodes:
        for q in draw(c, n, per, rnd.random()):
            items.append({**q, 'node': n, 'node_title': meta[n]['title']})
    states = nx.graph_states(c, uid)
    return {'kind': kind, 'items': _interleave(items, rnd)[:8], 'note': note, 'left': left,
            'nodes': [{'id': n, 'title': meta[n]['title'], 'status': states[n]['status'], 'label': nx.STATUS_LABEL[states[n]['status']]} for n in nodes]}, 200


# ---------------------------------------------------------------- spaced re-checks

def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS next_grammar_review(user_id INTEGER NOT NULL REFERENCES users(id), node TEXT NOT NULL, '
              'step INTEGER NOT NULL DEFAULT 0, due REAL NOT NULL, last_day TEXT NOT NULL DEFAULT "", updated REAL NOT NULL, '
              'PRIMARY KEY(user_id, node))')


def _today(now):
    import next_service as nx
    import datetime
    return datetime.datetime.fromtimestamp(now, nx.TZ).date().isoformat()


def schedule(c, uid, node, correct, now=None, first=None):
    """Move a point on its ladder after one checked answer. A miss starts it again tomorrow. A correct answer on a
    point that is due (or new) moves it one rung up, at most once a day; extra practice before it is due changes nothing.
    first: days until the first check for a point that has no schedule yet (the starting check spreads them out)."""
    now = now or time.time()
    day = _today(now)
    r = c.execute('SELECT step, due, last_day FROM next_grammar_review WHERE user_id=? AND node=?', (uid, node)).fetchone()
    if not correct:
        step, due = 0, now + LADDER[0] * DAY
    elif r is None:
        step, due = 0, now + (first or LADDER[0]) * DAY
    elif r['due'] <= now and r['last_day'] != day:
        step = min(r['step'] + 1, len(LADDER) - 1)
        due = now + LADDER[step] * DAY
    else:
        return review_of(c, uid, node, now)
    c.execute('INSERT INTO next_grammar_review(user_id,node,step,due,last_day,updated) VALUES(?,?,?,?,?,?) '
              'ON CONFLICT(user_id,node) DO UPDATE SET step=excluded.step, due=excluded.due, last_day=excluded.last_day, updated=excluded.updated',
              (uid, node, step, due, day, now))
    return review_of(c, uid, node, now)


def review_of(c, uid, node, now=None):
    now = now or time.time()
    r = c.execute('SELECT step, due FROM next_grammar_review WHERE user_id=? AND node=?', (uid, node)).fetchone() if uid else None
    if not r:
        return None
    return {'step': r['step'], 'rungs': len(LADDER), 'due': r['due'], 'is_due': r['due'] <= now,
            'in_days': max(0, int((r['due'] - now + DAY - 1) // DAY))}


def due(c, uid, now=None):
    """Points whose re-check has come, oldest first."""
    now = now or time.time()
    return [r['node'] for r in c.execute('SELECT node FROM next_grammar_review WHERE user_id=? AND due<=? ORDER BY due', (uid, now))]


# ---------------------------------------------------------------- the starting check

BANDS = ('A2', 'B1', 'B2', 'C1')
PER_BAND = 4


def placement_items(c, seed=None):
    """Four points per level band, one question each, from different topics where possible; easier bands first."""
    import next_service as nx
    rnd = random.Random(seed)
    meta = nx.nodes_meta(c)
    out = []
    for band in BANDS:
        nodes = [n for n in meta if nx.node_level(n) == band]
        rnd.shuffle(nodes)
        picked, topics = [], set()
        for n in nodes:  # different topics first, then fill
            if meta[n]['topic'] not in topics:
                picked.append(n); topics.add(meta[n]['topic'])
            if len(picked) == PER_BAND:
                break
        picked += [n for n in nodes if n not in picked][:PER_BAND - len(picked)]
        # A band with fewer points than questions (C1 has two) asks more than one question on a point.
        want = {n: 0 for n in picked}
        for k in range(PER_BAND):
            want[picked[k % len(picked)]] += 1
        for n in picked:
            for q in draw(c, n, want[n], rnd.random()):
                out.append({**q, 'band': band, 'node': n})
    return {'bands': list(BANDS), 'per_band': PER_BAND, 'items': out,
            'note': '这是语法起点小测，帮你选一个合适的起点，不是正式的等级考试。'}


def place(scores):
    """The level to start at: the first band with half or fewer right (where learning should happen); one band lower
    when that band was mostly wrong; C1 when every band was mostly right."""
    for i, band in enumerate(BANDS):
        s = scores.get(band)
        if s is None:
            return BANDS[max(0, i - 1)]
        if s <= PER_BAND // 2:
            return band if s == PER_BAND // 2 or i == 0 else BANDS[i - 1]
    return BANDS[-1]


def placement_score(c, uid, data, now=None):
    """Grade the starting check. Signed in, answers at or below the placed level are evidence (a miss there is a real gap
    and marks the point to fix); misses above it are not, since those points are simply not learnt yet."""
    import next_service as nx
    import event_service as ev
    now = now or time.time()
    answers = data.get('answers')
    if not isinstance(answers, list) or not 1 <= len(answers) <= len(BANDS) * PER_BAND:
        return {'error': '答案格式不正确'}, 400
    graded, seen = [], set()
    for a in answers:
        if not isinstance(a, dict):
            return {'error': '答案格式不正确'}, 400
        qid, choice = a.get('question'), a.get('choice')
        if type(qid) is not int or qid in seen or not (choice is None or type(choice) is int):
            return {'error': '答案格式不正确'}, 400
        seen.add(qid)
        q = c.execute("SELECT id, node, prompt, options, answer, explanation FROM questions WHERE id=? AND status='published' AND node IS NOT NULL", (qid,)).fetchone()
        if not q:
            return {'error': '题目不存在'}, 400
        band = nx.node_level(q['node'])
        graded.append({'id': q['id'], 'node': q['node'], 'band': band, 'correct': choice == q['answer'], 'skipped': choice is None,
                       'answer': q['answer'], 'explanation': q['explanation']})
    scores, counts = {}, {}
    for g in graded:
        scores[g['band']] = scores.get(g['band'], 0) + int(g['correct'])
        counts[g['band']] = counts.get(g['band'], 0) + 1
    # The check is sent after each band of four. It is decided once a band in order is mostly wrong or all are done;
    # until then only "go on" is answered, and nothing is recorded.
    full = [b for b in BANDS if counts.get(b) == PER_BAND]
    decided = len(full) == len(BANDS) or any(scores[b] <= PER_BAND // 2 for b in full)
    if not decided and not data.get('final'):
        return {'done': False}, 200
    level = place(scores)
    meta = nx.nodes_meta(c)
    upto = BANDS.index(level)
    gaps = [g for g in graded if not g['correct'] and BANDS.index(g['band']) <= upto]
    known = [g for g in graded if g['correct']]
    if uid:
        day = _today(now)
        for i, g in enumerate(known):
            ev.record(c, uid, g['node'], f"next-place:{g['id']}:{day}", 'choice', str(g['id']), 'placement', True, 0, 'rule', {'via': 'placement'}, now)
            schedule(c, uid, g['node'], True, now, first=1 + i % 7)  # spread the first re-checks over a week
        for g in gaps:
            ev.record(c, uid, g['node'], f"next-place:{g['id']}:{day}", 'choice', str(g['id']), 'placement', False, 0, 'rule', {'via': 'placement'}, now)
            schedule(c, uid, g['node'], False, now)
        c.commit()
        ar = __import__('ability_radar')  # the starting check is the radar's grammar assessment
        ar.record(c, uid, 'grammar', ar.ladder_index({b: scores[b] / counts[b] for b in scores}), {'scores': scores})
    title = lambda n: meta.get(n, {}).get('title', n)
    return {'done': True, 'level': level, 'scores': [{'band': b, 'right': scores[b], 'of': sum(1 for g in graded if g['band'] == b)} for b in BANDS if b in scores],
            'gaps': [{'id': g['node'], 'title': title(g['node']), 'band': g['band']} for g in gaps],
            'known': [{'id': g['node'], 'title': title(g['node'])} for g in known],
            'results': [{'id': g['id'], 'correct': g['correct'], 'answer': g['answer'], 'explanation': g['explanation']} for g in graded],
            'saved': bool(uid)}, 200
