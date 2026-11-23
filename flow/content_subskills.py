"""Per-subskill teaching pages. Each page teaches exactly one subskill.

The topic page keeps the overview; a subskill page never borrows another subskill's body.
Every entry is original teaching text awaiting human language review (see REVIEW_STATUS).
Guided practice is learning support and never counts as independent evidence; verification
uses the published question bank for the same subskill id.
"""
import hashlib,json,re

VERSION='2026-11-07.1'
REVIEW_STATUS='draft-needs-language-review'

def _p(goal,steps,contrast,pitfalls,guided,clue,extension=None):
 return {'goal':goal,'steps':steps,'contrast':contrast,'pitfalls':pitfalls,'guided':guided,'clue':clue,'extension':extension}

PAGES={
'tense-present':_p('区分习惯或事实（一般现在时）与说话这一刻正在发生的动作（现在进行时）。',
 ['先找时间线索：every day、usually、often 指向习惯；now、Look!、at the moment 指向此刻。','习惯与事实用一般现在时；主语是 he / she / it 时，动词加 -s 或 -es：She walks to school every day.','此刻正在发生用 am / is / are + doing：She is walking to school now.'],
 [('She walks to school every day.','每天的习惯'),('She is walking to school now.','说话这一刻正在走'),('Water boils at 100°C.','一般事实，用一般现在时')],
 [('She walk to school every day.','She walks to school every day.','he / she / it 作主语时，一般现在时的动词加 -s。'),('She walking now.','She is walking now.','进行时不能缺少 be 动词。'),('I am knowing the answer.','I know the answer.','know、like、want 等表示状态的动词通常不用进行时。')],
 {'prompt':'Please be quiet. The baby ____ now.','options':['sleeps','is sleeping','slept','has slept'],'answer':1,'scaffold':'now 提醒你“说话这一刻正在发生”。','explanation':'now 表示此刻正在发生，用现在进行时 is sleeping。'},
 '先找时间线索：是习惯（every day、usually），还是此刻（now、Look!）？'),
'tense-past':_p('用一般过去时讲已经结束的完整事件，用过去进行时讲过去某一刻正在进行的动作。',
 ['yesterday、last week、in 2020 等指向已经结束的过去时间。','一般过去时讲完整事件：I read a book last night.','过去进行时（was / were + doing）讲过去某一刻正在进行：At eight last night, I was reading.','两者常一起出现：长动作作背景用过去进行时，插入的短动作用一般过去时：I was reading when he called.'],
 [('I read a book last night.','完整事件：昨晚读了一本书'),('At eight last night, I was reading.','昨晚八点那一刻正在读'),('I was reading when he called.','读书是背景，打电话是插入的短动作')],
 [('When he called, I read a book.','When he called, I was reading a book.','电话打来时，读书正在进行，用过去进行时更准确。'),('They was having dinner.','They were having dinner.','they 搭配 were。'),('I have seen him yesterday.','I saw him yesterday.','yesterday 是明确的过去时间，用一般过去时。')],
 {'prompt':'At 9 p.m. yesterday, we ____ TV.','options':['watch','are watching','were watching','have watched'],'answer':2,'scaffold':'“昨天晚上九点”是过去的一个时刻，那时正在做什么？','explanation':'过去某一时刻正在进行，用过去进行时 were watching。'},
 '这件事是在过去完整发生，还是在过去某一刻正在进行？'),
'tense-perfect':_p('用现在完成时把过去的动作和现在连起来：持续到现在、到目前为止，或对现在有影响。',
 ['现在完成时的形式：have / has + 过去分词。','since + 起点、for + 一段时间，常表示从过去持续到现在：She has worked here for two years.','so far、already、yet、ever 常表示“到目前为止”。','句中有明确的过去时间（yesterday、in 2020、last week）时，用一般过去时，不用现在完成时。'],
 [('We moved to Shanghai in 2019.','2019 年搬来：明确的过去时间'),('We have been in Shanghai since 2019.','从 2019 年一直到现在'),('He has played the guitar for ten years.','for 加一段时间，持续到现在')],
 [('I have finished it yesterday.','I finished it yesterday.','yesterday 是明确的过去时间。'),('He is ill since Monday.','He has been ill since Monday.','since 表示持续到现在，用现在完成时。'),('He has went home.','He has gone home.','完成时用过去分词 gone。')],
 {'prompt':'We ____ in this city for five years.','options':['live','lived','have lived','are living'],'answer':2,'scaffold':'for five years 把过去和现在连在一起。','explanation':'从五年前一直住到现在，用现在完成时 have lived。'},
 '有没有 since、for、so far 这类“连到现在”的线索？还是有明确的过去时间？','拓展 · 过去完成时：过去某个时间点之前已经发生的动作，用 had + 过去分词：By the time we arrived, the show had begun.'),
'clause-relative':_p('根据先行词（人、物、地点、时间）和从句缺少的成分，选择 who、which、that、where、when 或 whose。',
 ['先找被修饰的名词（先行词），判断它是人、物、地点还是时间。','再看从句缺什么：缺主语或宾语用 who / which / that；缺地点状语用 where，缺时间状语用 when；表示“……的”用 whose。','把关系词还原进从句检查：the man who works here → he works here。'],
 [('This is the park where we played as children.','从句 we played 已完整，缺“在那里”，用 where'),('This is the place that we visited.','visited 缺宾语，用 that / which'),('I have a friend whose sister is a nurse.','表示“朋友的姐姐”，用 whose')],
 [('This is the street which I parked.','This is the street where I parked.','park 在这里不需要宾语，缺的是地点状语。'),('The man which helped me was kind.','The man who helped me was kind.','先行词是人，用 who。'),('I know a girl who her father is a pilot.','I know a girl whose father is a pilot.','表示所属关系用 whose。')],
 {'prompt':'The bag ____ I bought yesterday is blue.','options':['who','where','that','when'],'answer':2,'scaffold':'bought 后面缺什么？买的“东西”。','explanation':'先行词 bag 是物，从句 bought 缺宾语，用 that（也可用 which）。'},
 '先行词是人、物还是地点？把从句单独拿出来，它缺主语、宾语，还是缺地点或时间？'),
'clause-noun':_p('在宾语从句等名词性从句里使用陈述语序，并按意思选择 that、whether / if 或 wh- 词。',
 ['名词性从句在句中充当主语、宾语或表语，整个从句相当于一个名词。','从句用陈述语序，主语在前、谓语在后：Do you know where the museum is?（不是 where is the museum）','连接词由意思决定：陈述事实用 that，“是否”用 whether / if，问具体信息用 what、where、when、why、how。'],
 [('Where is the museum?','直接问句：疑问语序'),('Do you know where the museum is?','宾语从句：陈述语序'),('I wonder whether she is ready.','表示“是否”，用 whether')],
 [('Can you tell me where is the station?','Can you tell me where the station is?','宾语从句要用陈述语序。'),("I don't know that he will come or not.","I don't know whether he will come or not.",'表示“是否”用 whether，不用 that。'),('What he said it was true.','What he said was true.','what 已在从句里作宾语，主句不再重复 it。')],
 {'prompt':'Could you tell me when ____?','options':['does the class start','the class starts','did the class start','starts the class'],'answer':1,'scaffold':'放在 tell me 后面的是从句，不是直接问句。','explanation':'宾语从句用陈述语序：when the class starts。'},
 '这是直接问句，还是放在 know、tell、wonder 后面的从句？从句用陈述语序。'),
'clause-adverb':_p('根据两部分的逻辑关系（原因、让步、时间等）选择连接词，并区分连词和介词。',
 ['先判断两件事是什么关系：原因（because、since）、让步（although、though）、时间（when、while、after）。','连词后面接完整分句（有主语和谓语）；because of、despite、during 是介词，后面接名词短语。','although 已经表示“虽然”，同一句里不再加 but。'],
 [('Although it was cold, we went out.','让步：虽然冷，还是出门了'),('Because the bus was late, we took a taxi.','原因：因为公交晚了，所以打车'),('Despite the cold, we went out.','despite 是介词，后接名词短语')],
 [('Although it rained, but we played.','Although it rained, we played.','although 和 but 不同时使用。'),('Because of it was late, we left.','Because it was late, we left.','because of 后接名词，完整分句用 because。'),('Despite it was late, we kept talking.','Although it was late, we kept talking.','despite 后不接完整分句。')],
 {'prompt':'____ he was tired, he finished the report.','options':['Despite','Because of','Although','During'],'answer':2,'scaffold':'“累”和“完成报告”是什么关系？空后面是完整分句吗？','explanation':'虽然累还是完成了，是让步关系；后接完整分句，用 Although。'},
 '两部分是什么关系：原因、让步还是时间？后面是完整分句还是名词短语？','拓展 · 时间状语从句：when、as soon as、after 等引导的从句说将来时，用一般现在时：I will text you when I arrive.'),
'conditional-real':_p('用 if + 一般现在时、主句 will + 动词原形，表达将来真实可能的条件和结果；讲一般规律时两部分都用一般现在时。',
 ['真实条件说的是确实可能发生的情况。','将来可能：If it snows tonight, we will stay in.（从句用一般现在时，不用 will）','一般规律或事实：If you mix blue and yellow, you get green.（两部分都用一般现在时）'],
 [('If you practise, you will improve.','将来可能的结果'),('If you mix blue and yellow, you get green.','一般规律'),('If she calls, I will tell her.','calls 指将来，但从句用一般现在时')],
 [('If it will snow tonight, we will stay in.','If it snows tonight, we will stay in.','真实条件从句用一般现在时表示将来。'),('If you will press this button, the door opens.','If you press this button, the door opens.','一般规律两部分都用一般现在时。'),('If he come, we will start.','If he comes, we will start.','he 作主语，一般现在时动词加 -s。')],
 {'prompt':'If we ____ early, we will get good seats.','options':['arrive','will arrive','arrived','had arrived'],'answer':0,'scaffold':'这是可能发生的将来情况；if 从句里不用 will。','explanation':'真实将来条件，从句用一般现在时 arrive。'},
 '这是可能发生的真实情况吗？if 从句里用一般现在时，不用 will。'),
'conditional-unless':_p('理解 unless = if ... not；unless 从句用一般现在时表示将来，并避免双重否定。',
 ['unless 意思是“除非、如果不”：Unless you hurry, you will be late. = If you do not hurry, you will be late.','unless 从句和 if 真实条件一样，用一般现在时表示将来。','unless 本身含有否定，从句一般不再加 not。'],
 [('Unless you hurry, you will be late.','如果不快点，就会迟到'),('If you do not hurry, you will be late.','同样的意思，用 if ... not'),('You cannot enter unless you have a ticket.','有票才能进')],
 [("Unless you don't hurry, you will be late.",'Unless you hurry, you will be late.',"unless 已含否定，不再加 don't。"),('Unless it will snow, we will drive.','Unless it snows, we will drive.','unless 从句用一般现在时。')],
 {'prompt':"I won't go ____ you come with me.",'options':['if','unless','because','although'],'answer':1,'scaffold':'把空换成 if ... not 读一遍：如果你不来，我就不去。','explanation':'“除非你和我一起，否则我不去”，用 unless。'},
 '把 unless 换成 if ... not 读一遍，意思通吗？'),
'conditional-modal':_p('在真实条件句的主句里使用 can、may、should 或祈使句，表达能力、可能、建议或指令。',
 ['真实条件句的主句不一定用 will。','表示许可或能力用 can，可能用 may / might，建议用 should：If you finish your homework, you can watch TV.','给出指令或建议时，主句可以是祈使句（以动词原形开头）：If you feel tired, take a break.'],
 [('If it is sunny, we can have lunch outside.','can：可以在外面吃午饭'),('If it rains, we may stay inside.','may：可能留在室内'),('If you feel tired, take a break.','祈使句：直接建议')],
 [('If you see Tom, telling him to wait.','If you see Tom, tell him to wait.','祈使句用动词原形。'),('If you are free, you can to join us.','If you are free, you can join us.','情态动词后接动词原形，不加 to。')],
 {'prompt':'If you have any questions, ____ your teacher.','options':['asking','ask','asked','to ask'],'answer':1,'scaffold':'主句在给建议，用什么句型？','explanation':'主句是祈使句，用动词原形 ask。'},
 '主句想表达能力、可能、建议，还是直接给出指令？情态动词和祈使句都接动词原形。'),
'subjunctive-now':_p('用 if + 一般过去时（be 常用 were）、主句 would / could / might + 动词原形，表达和现在事实相反或不太可能的假设。',
 ['先判断是不是“和现在事实不符”的假设：If I had time ...（其实现在没时间）。','从句用一般过去时；be 动词在正式表达中常用 were：If he were here, ...','主句用 would / could / might + 动词原形：I would travel.'],
 [('If I have time, I will travel.','真实条件：有可能有时间'),('If I had time, I would travel.','与现在事实相反：现在没时间'),('If I lived near the sea, I would swim every day.','与现在事实相反：其实不住海边')],
 [('If I had time, I will travel.','If I had time, I would travel.','与现在事实相反，主句用 would。'),('If I would have time, I would travel.','If I had time, I would travel.','if 从句里不用 would。'),('If she was here, she would help.','If she were here, she would help.','正式表达多用 were；口语中 was 也常见。')],
 {'prompt':'If she ____ more free time, she would learn the piano.','options':['has','had','will have','has had'],'answer':1,'scaffold':'她现在其实没有更多空闲时间。','explanation':'与现在事实相反，从句用一般过去时 had。'},
 '这件事和现在的事实相符吗？不相符时，if 从句的时态往过去“退一步”。','拓展 · I wish + 过去式：表达对现在的愿望与事实相反：I wish I had a bike.'),
'subjunctive-past':_p('用 if + had done、主句 would have done，表达和过去事实相反的假设。',
 ['先确认说的是过去，而且实际情况相反：If I had taken a taxi ...（其实没打车）。','从句用过去完成时：had + 过去分词。','主句用 would / could / might have + 过去分词：I would have arrived on time.'],
 [('If I had time, I would help.','与现在事实相反'),('If I had had time, I would have come.','与过去事实相反'),('If she had asked, I would have told her.','过去没问，所以没告诉她')],
 [('If I had taken a taxi, I would arrive on time.','If I had taken a taxi, I would have arrived on time.','结果也在过去，用 would have done。'),('If I would have known, I would have come.','If I had known, I would have come.','if 从句不用 would have。')],
 {'prompt':'If they ____ the map, they would not have got lost.','options':['check','checked','had checked','would check'],'answer':2,'scaffold':'迷路已经发生了，假设的是过去。','explanation':'与过去事实相反，从句用 had checked。'},
 '假设的是过去的事吗？过去的反事实：从句 had done，主句 would have done。','拓展 · 隐含条件：without、but for 也能引出与过去事实相反的假设：Without the map, we would have got lost.'),
'subjunctive-mixed':_p('当条件和结果发生在不同时间时，分别判断两部分的时间，例如过去的条件影响现在的结果。',
 ['把条件和结果分开看：条件发生在什么时候？结果说的是什么时候？','过去的条件 → 现在的结果：If I had studied medicine, I would be a doctor now.（从句 had done，主句 would do）','句中的 now、today 等词常提示结果在现在。'],
 [('If I had studied medicine, I would have become a doctor.','条件和结果都在过去'),('If I had studied medicine, I would be a doctor now.','过去的条件，现在的结果'),('If I had brought an umbrella, I would be dry now.','过去没带伞，现在淋湿了')],
 [('If I had studied medicine, I would have been a doctor now.','If I had studied medicine, I would be a doctor now.','now 说明结果在现在，用 would do。'),('If I took the job last year, I would live in London now.','If I had taken the job last year, I would live in London now.','条件在 last year，已经过去，用 had done。')],
 {'prompt':'If he had saved more money, he ____ a car now.','options':['would have','would have had','will have','has'],'answer':0,'scaffold':'存钱在过去，“有车”说的是 now。','explanation':'过去的条件影响现在的结果，主句用 would have（would + 动词原形 have）。'},
 '条件在什么时候？结果在什么时候？看看句末有没有 now。'),
'nonfinite-infinitive':_p('在 hope、decide、want 等动词后使用 to do，并用 to do 表达目的。',
 ['有些动词后面固定接 to do：hope、decide、want、plan、agree、refuse。','to do 可以表示目的“为了……”：I went to the shop to buy milk.','不确定时，把它当作搭配来记，并在例句里检查。'],
 [('We hope to visit Japan.','hope + to do'),('I went to the shop to buy milk.','to do 表示目的'),('He decided to stay.','decide + to do')],
 [('I want going home.','I want to go home.','want 后接 to do。'),('I went there for buy milk.','I went there to buy milk.','表示目的用 to do。'),('She decided to stayed.','She decided to stay.','to 后面接动词原形。')],
 {'prompt':'They plan ____ a new library next year.','options':['open','opening','to open','opened'],'answer':2,'scaffold':'plan 后面习惯接哪种形式？','explanation':'plan 后接不定式 to open。'},
 '前面的动词后面习惯接 to do 吗？或者这里在说“为了做某事”？'),
'nonfinite-gerund':_p('在介词后，以及 enjoy、avoid、finish 等动词后，使用 doing。',
 ['介词（in、at、of、about、without 等）后面接名词或 doing：He is good at swimming.','enjoy、avoid、finish、mind、keep 后面接 doing。','look forward to 中的 to 是介词，后面接 doing。'],
 [('He is good at swimming.','介词 at + doing'),('They enjoy cooking.','enjoy + doing'),('We look forward to meeting the team.','to 是介词，接 doing')],
 [('I enjoy to swim.','I enjoy swimming.','enjoy 后接 doing。'),('She left without say goodbye.','She left without saying goodbye.','介词 without 后接 doing。'),('I look forward to visit you.','I look forward to visiting you.','这里的 to 是介词。')],
 {'prompt':'He left without ____ a word.','options':['say','to say','saying','said'],'answer':2,'scaffold':'空前面的 without 是什么词性？','explanation':'介词 without 后接动名词 saying。'},
 '空前面是介词，还是 enjoy、avoid 这类后接 doing 的动词？'),
'nonfinite-participle':_p('用现在分词（doing）表示主动或正在进行，用过去分词（done）表示被动或已完成，来修饰名词。',
 ['先找被修饰的名词，再问：它是动作的发出者，还是承受者？','发出者（主动）用 doing：the man waiting at the door（男人在等）。','承受者（被动）用 done：the lost key（钥匙被弄丢）。'],
 [('the man waiting at the door','男人主动在等'),('a door painted last week','门是上周被刷的'),('a boring film / a bored audience','电影令人无聊；观众感到无聊')],
 [('The car parking outside is mine.','The car parked outside is mine.','车是被停放的，用过去分词。'),('I am boring in this class.','I am bored in this class.','“我感到无聊”用 bored。')],
 {'prompt':'The photos ____ in this book are beautiful.','options':['showing','shown','show','to showing'],'answer':1,'scaffold':'照片是“展示”这个动作的发出者，还是被展示？','explanation':'照片被展示，是被动关系，用过去分词 shown。'},
 '被修饰的名词是动作的发出者还是承受者？'),
'agreement-head':_p('先忽略 of 短语等修饰成分，找到主语中心词，再决定谓语用单数还是复数。',
 ['先把修饰成分（of ...、with ...、介词短语、从句）暂时遮住。','剩下的中心词决定谓语：The price of the books is high. → The price is high。','离谓语最近的名词不一定是主语。'],
 [('The price of the books is high.','中心词 price 是单数'),('The books on the shelf are new.','中心词 books 是复数'),('The students in my class are friendly.','中心词 students 是复数')],
 [('The bag of apples are heavy.','The bag of apples is heavy.','中心词是 bag。'),('The teacher with her students are here.','The teacher with her students is here.','with 短语不改变主语的数。')],
 {'prompt':'The keys to the door ____ on the table.','options':['is','are','was','has'],'answer':1,'scaffold':'遮住 to the door，主语是哪个词？','explanation':'中心词 keys 是复数，用 are。'},
 '去掉 of 短语等修饰成分，真正的主语是哪个词？','拓展 · 整体与不可数：表示整体的距离、时间、金额（Two hours is enough.）和 news、information 等不可数名词，谓语用单数。'),
'agreement-each':_p('each、every、everyone、everybody、nobody 等作主语时，谓语用单数。',
 ['each、every 强调“每一个”；everyone、somebody、nobody 等不定代词按单数处理。','Each of the students ... 中主语是 each，谓语仍用单数。','every 修饰并列主语时也用单数：Every boy and girl has a book.'],
 [('Everyone has a chance.','everyone 按单数'),('Each of the rooms has a window.','each 作主语，用单数'),('All of the students have books.','all 修饰复数名词，用复数')],
 [('Everyone like music.','Everyone likes music.','everyone 按单数处理。'),('Each of them have a key.','Each of them has a key.','主语是 each。')],
 {'prompt':'Nobody ____ the answer.','options':['know','knows','are knowing','have known'],'answer':1,'scaffold':'nobody 按单数还是复数处理？','explanation':'nobody 作主语，谓语用单数 knows。'},
 '主语是 each、every-、-one、-body 这类词吗？它们按单数处理。'),
'agreement-either':_p('either ... or、neither ... nor、not only ... but also 连接两个主语时，谓语与离它最近的主语一致。',
 ['找到被连接的两个主语，看哪一个离谓语最近。','谓语与较近的那个一致：Either the teacher or the students are coming.','both ... and 连接两个主语时，谓语用复数，不按就近原则。'],
 [('Either the teacher or the students are coming.','靠近谓语的 students 是复数'),('Either the children or their mother is at home.','靠近谓语的 mother 是单数'),('Both the teacher and the students are coming.','both ... and 用复数')],
 [('Neither my friends nor my brother are here.','Neither my friends nor my brother is here.','较近的 brother 是单数。'),('Both Tom and Amy is late.','Both Tom and Amy are late.','both ... and 用复数。')],
 {'prompt':'Neither the manager nor the workers ____ happy with the plan.','options':['is','are','was','has'],'answer':1,'scaffold':'谓语离哪个主语更近？','explanation':'就近的 workers 是复数，用 are。'},
 '谓语离哪一个主语更近？那个主语是单数还是复数？（both ... and 除外）'),
}

# the 26 further points (grammar_more.py) use the same page format
PAGES.update(__import__('grammar_more').PAGES_MORE)

def page(node_id):
 """Full teaching page for one subskill, or an explicit pending state. Never another node's text."""
 p=PAGES.get(node_id)
 if not p:return {'status':'pending','note':'这个细项的完整讲解还在编写，先看下面的简短说明和验证题。'}
 out={k:(list(map(list,v)) if k in ('contrast','pitfalls') else v) for k,v in p.items()}
 out.update(node=node_id,status='ready',version=VERSION,review=REVIEW_STATUS,fingerprint=fingerprint(node_id))
 return out

def fingerprint(node_id):
 return hashlib.sha256(json.dumps(PAGES.get(node_id),sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]

def norm(text):
 return ' '.join(re.findall(r"[a-z0-9']+",text.lower().replace('’',"'")))

def audit(c):
 """Structural self-check across all subskills. Semantic accuracy still needs a human reviewer."""
 out=[]
 for r in c.execute('SELECT id,title FROM subskills ORDER BY rowid').fetchall():
  p=PAGES.get(r['id']);issues=[]
  if not p:issues.append('缺少细项讲解')
  else:
   g=p['guided']
   if not 0<=g['answer']<len(g['options']):issues.append('引导练习答案越界')
   if len(set(g['options']))!=len(g['options']):issues.append('引导练习选项重复')
   if len(p['contrast'])<2:issues.append('对比例句不足两组')
   if not p['pitfalls']:issues.append('缺少易错点')
   text=norm(json.dumps(p,ensure_ascii=False))
   for q in c.execute("SELECT prompt,options,answer FROM questions WHERE node=? AND status='published'",(r['id'],)):
    full=norm(q[0].replace('____',json.loads(q[1])[q[2]]))
    pattern=r'\s*\S{0,40}\s*'.join(re.escape(part) for part in (norm(x) for x in q[0].split('____')) if part)
    if full in text:issues.append('讲解直接包含验证题及答案：'+q[0])
    elif pattern and len(pattern)>20 and re.search(pattern,text):issues.append('讲解与验证题题干相同：'+q[0])
  published=c.execute("SELECT COUNT(*) FROM questions WHERE node=? AND status='published'",(r['id'],)).fetchone()[0]
  if published<2:issues.append('已发布验证题少于2道')
  out.append({'node':r['id'],'title':r['title'],'published_questions':published,'issues':issues,'review':REVIEW_STATUS})
 return out
