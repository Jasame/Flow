"""Words Chinese speakers mix up: 50 groups, each with how to tell them apart and three practice questions.

Most of these pairs share one Chinese word (借 = borrow / lend, 看 = look / see / watch, 说 = say / tell / speak /
talk), so the Chinese gives no help and the English has to be learnt as a contrast. All content is original.
Each question: (sentence with ____, options, index of the answer, Chinese explanation).
"""
import random

# id -> (level, words shown as the group's name, how to tell them apart, [(sentence, options, answer, why)])
GROUPS = {
    'borrow-lend': ('A2', ['borrow', 'lend'], 'borrow 是“借进来”（从别人那里拿），lend 是“借出去”（给别人）。',
        [('Can I ____ your umbrella? It\'s raining.', ['borrow', 'lend'], 0, '我从你那里拿：borrow。'),
         ('Could you ____ me ten yuan until tomorrow?', ['borrow', 'lend'], 1, 'lend sb sth：借给某人。'),
         ('She ____ me her notes before the exam.', ['borrowed', 'lent'], 1, '她给我：lend 的过去式 lent。')]),
    'say-tell': ('A2', ['say', 'tell', 'speak', 'talk'], 'say 后接说的内容；tell 后先接人（tell sb sth）；speak 说语言或正式发言；talk 是交谈（talk to / about）。',
        [('Can you ____ me the way to the station?', ['say', 'tell', 'speak', 'talk'], 1, 'tell 后面直接接人：tell me。'),
         ('He ____ that he would be late.', ['said', 'told', 'spoke', 'talked'], 0, 'say (that) + 内容，后面没有人。'),
         ('How many languages can you ____?', ['say', 'tell', 'speak', 'talk'], 2, '说某种语言用 speak。')]),
    'look-see-watch': ('A2', ['look', 'see', 'watch'], 'look 是主动去看（look at）；see 是看见、看到结果；watch 是盯着看会动的东西（电视、比赛）。',
        [('____ at this photo! Isn\'t it beautiful?', ['Look', 'See', 'Watch'], 0, '主动把目光投向：look at。'),
         ('We ____ a football match on TV last night.', ['looked', 'saw', 'watched'], 2, '看比赛、电视这种在动的东西：watch。'),
         ('I didn\'t ____ him at the party. Was he there?', ['look', 'see', 'watch'], 1, '“看见、注意到”：see。')]),
    'bring-take': ('A2', ['bring', 'take'], 'bring 是“带来”（朝说话人这边）；take 是“带走”（离开说话人这边）。',
        [('Please ____ your homework to class tomorrow.', ['bring', 'take'], 0, '带到这里来（课堂）：bring。'),
         ('Can you ____ these books back to the library for me?', ['bring', 'take'], 1, '从这里带到别处（图书馆）：take。'),
         ('Can you ____ me a glass of water?', ['bring', 'take'], 0, '拿过来给我：bring。')]),
    'hear-listen': ('A2', ['hear', 'listen'], 'hear 是听见（不一定有意）；listen 是主动去听，后面接 to。',
        [('Did you ____ that noise outside?', ['hear', 'listen'], 0, '听见了某个声音：hear。'),
         ('I like to ____ to music on the bus.', ['hear', 'listen'], 1, '主动去听：listen to。'),
         ('Please ____ carefully. I\'ll only say it once.', ['hear', 'listen'], 1, '提醒对方认真听：listen。')]),
    'fun-funny': ('A2', ['fun', 'funny'], 'fun 是“好玩、有乐趣”；funny 是“好笑、滑稽”（也可指“奇怪”）。',
        [('The party was really ____. We danced all night.', ['fun', 'funny'], 0, '玩得开心：fun。'),
         ('He told a ____ story and everyone laughed.', ['fun', 'funny'], 1, '让人发笑：funny。'),
         ('Learning to cook can be a lot of ____.', ['fun', 'funny'], 0, 'a lot of fun：很有乐趣。')]),
    'win-beat': ('A2', ['win', 'beat'], 'win 后接比赛、奖项（win a game / a prize）；beat 后接对手（beat the other team）。',
        [('Our team ____ the match 3–1.', ['won', 'beat'], 0, '赢得比赛：win a match。'),
         ('China ____ Japan in the final.', ['won', 'beat'], 1, '打败对手：beat sb。'),
         ('She hopes to ____ first prize this year.', ['win', 'beat'], 0, '获得奖项：win a prize。')]),
    'job-work': ('A2', ['job', 'work'], 'job 是可数名词（a job，一份工作）；work 作“工作”时不可数，不说 a work。',
        [('She found a new ____ in Shanghai.', ['job', 'work'], 0, '一份工作：a job。'),
         ('He\'s looking for ____ as a teacher.', ['job', 'work'], 1, 'job 可数，前面要有 a；不加冠词的“工作”用 work。'),
         ('What time do you finish ____?', ['job', 'work'], 1, 'finish work：下班。')]),
    'learn-study': ('A2', ['learn', 'study'], 'study 是“学习、研读”（过程）；learn 是“学会”（结果），也常用于学技能。',
        [('I ____ English for three hours last night.', ['learned', 'studied'], 1, '花时间学习这个过程：study。'),
         ('She ____ to swim when she was six.', ['learned', 'studied'], 0, '学会一项技能：learn to do。'),
         ('He is ____ law at university.', ['learning', 'studying'], 1, '在大学修某个专业：study。')]),
    'house-home': ('A2', ['house', 'home'], 'house 是房子（建筑）；home 是家（住的地方、有归属感），go home 前不加 to。',
        [('The ____ is built of red brick.', ['house', 'home'], 0, '建筑本身：house。'),
         ('It\'s late. Let\'s go ____.', ['to home', 'home'], 1, 'go home 不加 to。'),
         ('Make yourself at ____.', ['house', 'home'], 1, 'at home：像在家里一样。')]),
    'housework-homework': ('A2', ['housework', 'homework'], 'housework 是家务；homework 是家庭作业。两个都不可数。',
        [('My dad does most of the ____: cooking, cleaning and washing.', ['housework', 'homework'], 0, '做饭打扫：housework。'),
         ('The teacher gave us a lot of ____ today.', ['housework', 'homework'], 1, '老师布置的作业：homework。'),
         ('Have you finished your maths ____?', ['housework', 'homework'], 1, '数学作业：homework。')]),
    'tall-high': ('A2', ['tall', 'high'], 'tall 多指人、树、楼等又高又细、从地面往上长的东西；high 指离地面的高度或高处的东西（high shelf、high mountain）。',
        [('My brother is very ____; he\'s almost two metres.', ['tall', 'high'], 0, '人的身高：tall。'),
         ('The plane was flying very ____.', ['tall', 'high'], 1, '离地面很高：high。'),
         ('The shelf is too ____ for me to reach.', ['tall', 'high'], 1, '离地面高的位置：high。')]),
    'alone-lonely': ('B1', ['alone', 'lonely'], 'alone 是客观上“一个人”；lonely 是主观上“孤单、寂寞”。',
        [('She lives ____, but she has lots of friends.', ['alone', 'lonely'], 0, '一个人住（不代表孤单）：alone。'),
         ('He felt ____ in the new city.', ['alone', 'lonely'], 1, '感到孤单：lonely。'),
         ('Can you leave me ____ for a minute?', ['alone', 'lonely'], 0, 'leave sb alone：让某人独处。')]),
    'hard-hardly': ('B1', ['hard', 'hardly'], 'hard 作副词是“努力地、使劲地”；hardly 是“几乎不”，意思完全不同。',
        [('She works very ____ every day.', ['hard', 'hardly'], 0, '努力工作：work hard。'),
         ('I could ____ hear him; the music was too loud.', ['hard', 'hardly'], 1, '几乎听不见：hardly。'),
         ('It\'s raining ____. Take an umbrella.', ['hard', 'hardly'], 0, '雨下得很大：rain hard。')]),
    'late-lately': ('B1', ['late', 'lately'], 'late 是“晚、迟”；lately 是“最近”（常和完成时连用）。',
        [('I got up ____ and missed the bus.', ['late', 'lately'], 0, '起得晚：late。'),
         ('Have you seen any good films ____?', ['late', 'lately'], 1, '最近：lately。'),
         ('The train arrived ten minutes ____.', ['late', 'lately'], 0, '晚到：late。')]),
    'arrive-reach': ('B1', ['arrive', 'reach', 'get'], 'arrive 后面要加 in / at；reach 直接接地点；get 后接 to。',
        [('We ____ in Beijing at midnight.', ['arrived', 'reached', 'got'], 0, 'arrive in + 城市。'),
         ('They finally ____ the top of the mountain.', ['arrived', 'reached', 'got'], 1, 'reach 直接接地点，不加介词。'),
         ('How do I ____ to the airport from here?', ['arrive', 'reach', 'get'], 2, 'get to + 地点。')]),
    'cost-spend': ('B1', ['cost', 'spend', 'take', 'pay'], '物 cost 人钱；人 spend 钱 / 时间 on 物或 doing；事 takes 人时间；人 pay 钱 for 物。',
        [('This jacket ____ me 300 yuan.', ['cost', 'spent', 'took', 'paid'], 0, '东西作主语：cost。'),
         ('I ____ two hours doing my homework.', ['cost', 'spent', 'took', 'paid'], 1, '人花时间做某事：spend … doing。'),
         ('It ____ me twenty minutes to walk to school.', ['cost', 'spent', 'took', 'paid'], 2, 'It takes sb time to do。')]),
    'wear-put-on': ('B1', ['wear', 'put on', 'dress'], 'wear 是穿着（状态）；put on 是穿上（动作）；dress 后接人（dress the baby）或 get dressed。',
        [('He ____ a black suit at the wedding yesterday.', ['wore', 'put on', 'dressed'], 0, '穿着的状态：wear 的过去式 wore。'),
         ('It\'s cold outside. ____ your coat.', ['Wear', 'Put on', 'Dress'], 1, '穿上这个动作：put on。'),
         ('Hurry up and get ____; we\'re late.', ['wearing', 'put on', 'dressed'], 2, 'get dressed：穿好衣服。')]),
    'trip-travel': ('B1', ['trip', 'travel'], 'trip 是一次出行（可数名词，a trip）；travel 多作动词，作名词时泛指旅行（不可数，不说 a travel）。',
        [('We went on a school ____ to the museum.', ['trip', 'travel'], 0, '一次出行：a trip。'),
         ('I love ____ — I\'ve been to ten countries.', ['trip', 'travel'], 1, '泛指旅行：travel。'),
         ('Have a nice ____!', ['trip', 'travel'], 0, '祝一路顺风：Have a nice trip，不说 a travel。')]),
    'remember-remind': ('B1', ['remember', 'remind'], 'remember 是自己记得；remind 是提醒别人（remind sb to do / of sth）。',
        [('Please ____ me to call my mother tonight.', ['remember', 'remind'], 1, '让别人提醒：remind sb to do。'),
         ('I can\'t ____ where I put my keys.', ['remember', 'remind'], 0, '自己想起：remember。'),
         ('This song ____ me of my school days.', ['remembers', 'reminds'], 1, 'remind sb of sth：使想起。')]),
    'steal-rob': ('B1', ['steal', 'rob'], 'steal 后接被偷的东西（steal money）；rob 后接被抢的人或地方（rob a bank / rob sb of sth）。',
        [('Someone ____ my bike last night.', ['stole', 'robbed'], 0, '偷东西：steal sth。'),
         ('Two men ____ the bank and ran away.', ['stole', 'robbed'], 1, '抢银行：rob a place。'),
         ('He was ____ of his wallet on the train.', ['stolen', 'robbed'], 1, 'rob sb of sth：被抢走某物。')]),
    'advice-advise': ('B1', ['advice', 'advise'], 'advice 是名词（不可数）；advise 是动词，读音和拼写都不同。',
        [('Can you give me some ____ about learning English?', ['advice', 'advise'], 0, 'some 后接名词：advice。'),
         ('The doctor ____ me to rest for a week.', ['adviced', 'advised'], 1, '动词 advise 的过去式。'),
         ('That\'s a good piece of ____.', ['advice', 'advise'], 0, 'a piece of advice。')]),
    'especially-specially': ('B1', ['especially', 'specially'], 'especially 是“尤其、特别是”（在几个里面突出一个）；specially 是“专门、特意”。',
        [('I love fruit, ____ mangoes.', ['especially', 'specially'], 0, '尤其是：especially。'),
         ('This cake was made ____ for your birthday.', ['especially', 'specially'], 1, '特意为……做：specially。'),
         ('It\'s cold here, ____ in January.', ['especially', 'specially'], 0, '特别是一月：especially。')]),
    'during-for': ('B1', ['during', 'for'], 'during 回答“什么时候”（在某段时间里）；for 回答“多长时间”（for two hours）。',
        [('I fell asleep ____ the film.', ['during', 'for'], 0, '在电影放映期间：during。'),
         ('We waited ____ two hours.', ['during', 'for'], 1, '持续多久：for。'),
         ('The phone rang ____ dinner.', ['during', 'for'], 0, '在吃饭期间的某个时刻：during。')]),
    'ago-before': ('B1', ['ago', 'before'], 'ago 以“现在”为起点往前算（two years ago，用过去时）；before 以过去某个时间为起点，或单独表示“以前”。',
        [('I moved to Shanghai three years ____.', ['ago', 'before'], 0, '从现在往前三年：ago。'),
         ('She had left two days ____ I arrived.', ['ago', 'before'], 1, '在过去某事之前：before。'),
         ('Have you been here ____?', ['ago', 'before'], 1, '单独用“以前”：before。')]),
    'other-another': ('B1', ['other', 'another', 'others'], 'another 是“另一个”（后接单数）；other 后接复数名词或 the other；others 是代词，后面不接名词。',
        [('Can I have ____ cup of tea?', ['other', 'another', 'others'], 1, '再一个：another + 单数名词。'),
         ('Some people like coffee; ____ prefer tea.', ['other', 'another', 'others'], 2, '代词“别的人”：others。'),
         ('I have two sisters. One is a doctor and the ____ is a teacher.', ['other', 'another', 'others'], 0, '两者中的另一个：the other。')]),
    'expect-hope-wait': ('B1', ['expect', 'hope', 'wait'], 'expect 是预计、料到（认为会发生）；hope 是希望（想要发生）；wait 是等待（wait for）。',
        [('I ____ you have a good time in Japan!', ['expect', 'hope', 'wait'], 1, '祝愿、希望：hope。'),
         ('We\'re ____ for the bus.', ['expecting', 'hoping', 'waiting'], 2, '等车：wait for。'),
         ('The meeting is ____ to finish at five.', ['expected', 'hoped', 'waited'], 0, '预计：be expected to。')]),
    'beside-besides': ('B1', ['beside', 'besides'], 'beside 是“在……旁边”；besides 是“除了……还有”或“而且”。',
        [('Come and sit ____ me.', ['beside', 'besides'], 0, '在旁边：beside。'),
         ('____ English, she also speaks French.', ['Beside', 'Besides'], 1, '除了……还：besides。'),
         ('I\'m too tired to go out. ____, it\'s raining.', ['Beside', 'Besides'], 1, '而且：besides。')]),
    'lose-loose': ('B1', ['lose', 'loose'], 'lose 是动词“丢失、输”；loose 是形容词“松的”，多一个 o。',
        [('Don\'t ____ your ticket.', ['lose', 'loose'], 0, '丢失：lose。'),
         ('These trousers are too ____; I need a belt.', ['lose', 'loose'], 1, '松的：loose。'),
         ('If we ____ this game, we\'re out.', ['lose', 'loose'], 0, '输掉：lose。')]),
    'quite-quiet': ('B1', ['quite', 'quiet'], 'quite 是副词“相当”；quiet 是形容词“安静的”。',
        [('The library is very ____.', ['quite', 'quiet'], 1, '安静：quiet。'),
         ('The film was ____ good.', ['quite', 'quiet'], 0, '相当好：quite good。'),
         ('Please be ____; the baby is sleeping.', ['quite', 'quiet'], 1, '保持安静：be quiet。')]),
    'than-then': ('B1', ['than', 'then'], 'than 用于比较（taller than）；then 表示“然后、那时”。',
        [('She is older ____ me.', ['than', 'then'], 0, '比较：than。'),
         ('First, boil the water. ____, add the noodles.', ['Than', 'Then'], 1, '然后：then。'),
         ('I was living in Wuhan ____.', ['than', 'then'], 1, '那时：then。')]),
    'its-it-s': ('B1', ["its", "it's"], "its 是“它的”（物主代词）；it's = it is / it has。",
        [('The dog wagged ____ tail.', ["its", "it's"], 0, '它的尾巴：its。'),
         ('____ raining again.', ["Its", "It's"], 1, 'It is raining：It\'s。'),
         ('____ been a long day.', ["Its", "It's"], 1, 'It has been：It\'s。')]),
    'everyday-every-day': ('B1', ['everyday', 'every day'], 'everyday 是形容词“日常的”（放在名词前）；every day 是“每天”（作状语）。',
        [('I go running ____.', ['everyday', 'every day'], 1, '每天：every day。'),
         ('Smartphones are part of ____ life.', ['everyday', 'every day'], 0, '日常的生活：everyday life。'),
         ('She wears her ____ clothes to the office.', ['everyday', 'every day'], 0, '平常穿的衣服：everyday clothes。')]),
    'maybe-may-be': ('B1', ['maybe', 'may be'], 'maybe 是副词“也许”（常在句首）；may be 是情态动词 + be，作谓语。',
        [('____ we should leave now.', ['Maybe', 'May be'], 0, '句首的“也许”：maybe。'),
         ('He ____ at home; I\'m not sure.', ['maybe', 'may be'], 1, '作谓语：may be。'),
         ('"Are you coming?" "____."', ['Maybe', 'May be'], 0, '单独回答“也许吧”：Maybe。')]),
    'already-yet-still': ('B1', ['already', 'yet', 'still'], 'already 是“已经”（多用于肯定句）；yet 是“还（没）/ 已经……了吗”（否定和疑问）；still 是“仍然”。',
        [('Have you finished ____?', ['already', 'yet', 'still'], 1, '疑问句末尾：yet。'),
         ('I\'ve ____ seen this film twice.', ['already', 'yet', 'still'], 0, '肯定句“已经”：already。'),
         ('It\'s ten o\'clock and he\'s ____ in bed.', ['already', 'yet', 'still'], 2, '仍然：still。')]),
    'make-do': ('B1', ['make', 'do'], 'make 多指创造、做出结果（make a cake / a mistake / a decision）；do 多指做事、完成任务（do homework / the dishes / your best）。',
        [('Everyone ____ mistakes when they learn a language.', ['makes', 'does'], 0, 'make a mistake。'),
         ('Could you ____ me a favour?', ['make', 'do'], 1, 'do sb a favour。'),
         ('We need to ____ a decision by Friday.', ['make', 'do'], 0, 'make a decision。')]),
    'sometimes-some-time': ('B1', ['sometimes', 'some time'], 'sometimes 是“有时”（频率）；some time 是“一段时间”。',
        [('I ____ go to work by bike.', ['sometimes', 'some time'], 0, '有时：sometimes。'),
         ('It will take ____ to get used to the new job.', ['sometimes', 'some time'], 1, '一段时间：some time。'),
         ('We ____ eat out on Fridays.', ['sometimes', 'some time'], 0, '频率“有时”：sometimes。')]),
    'scenery-view': ('B1', ['scenery', 'view'], 'scenery 是不可数名词，指整体的自然风景；view 是可数的“视野、从某处看到的景色”。',
        [('The ____ in Guilin is beautiful.', ['scenery', 'sceneries'], 0, 'scenery 不可数，没有复数。'),
         ('Our room has a great ____ of the sea.', ['scenery', 'view'], 1, '从房间看出去的景：a view of。'),
         ('We stopped to enjoy the ____ from the top of the hill.', ['scenery', 'view'], 1, '从山顶看到的景：the view from。')]),
    'raise-rise': ('B2', ['raise', 'rise'], 'raise 是及物动词，后接宾语（raise your hand / prices）；rise 是不及物动词，自己上升（prices rise）。',
        [('If you know the answer, ____ your hand.', ['raise', 'rise'], 0, '举手：raise 后接宾语。'),
         ('House prices ____ sharply last year.', ['raised', 'rose'], 1, '价格自己上涨：rise 的过去式 rose。'),
         ('The company decided to ____ salaries by 5%.', ['raise', 'rise'], 0, '提高工资：raise salaries。')]),
    'affect-effect': ('B2', ['affect', 'effect'], 'affect 通常是动词“影响”；effect 通常是名词“影响、效果”（have an effect on）。',
        [('Lack of sleep can ____ your memory.', ['affect', 'effect'], 0, '动词“影响”：affect。'),
         ('The new rule had a big ____ on small shops.', ['affect', 'effect'], 1, 'have an effect on：名词。'),
         ('The medicine took ____ after an hour.', ['affect', 'effect'], 1, 'take effect：生效。')]),
    'lie-lay': ('B2', ['lie', 'lay'], 'lie（lay, lain）是“躺、位于”，不及物；lay（laid, laid）是“放置、下蛋”，后接宾语。',
        [('I\'m going to ____ down for a while.', ['lie', 'lay'], 0, '躺下：lie down。'),
         ('Please ____ the books on the table.', ['lie', 'lay'], 1, '放置某物：lay sth。'),
         ('Yesterday she ____ in bed all day with a fever.', ['lay', 'laid'], 0, 'lie 的过去式是 lay。')]),
    'sensible-sensitive': ('B2', ['sensible', 'sensitive'], 'sensible 是“明智的、合理的”；sensitive 是“敏感的、体贴的”。',
        [('Saving some money every month is a ____ idea.', ['sensible', 'sensitive'], 0, '明智的：sensible。'),
         ('She is very ____ to criticism.', ['sensible', 'sensitive'], 1, '对批评敏感：sensitive to。'),
         ('This cream is good for ____ skin.', ['sensible', 'sensitive'], 1, '敏感肌肤：sensitive skin。')]),
    'economic-economical': ('B2', ['economic', 'economical'], 'economic 是“经济（学）的”；economical 是“节约的、省钱的”。',
        [('The country is facing ____ problems.', ['economic', 'economical'], 0, '经济方面的：economic。'),
         ('Buying in bulk is more ____.', ['economic', 'economical'], 1, '省钱：economical。'),
         ('This small car is very ____ on fuel.', ['economic', 'economical'], 1, '省油：economical。')]),
    'chance-opportunity': ('B2', ['chance', 'opportunity', 'possibility'], 'opportunity 是有利的“机会”；possibility 是“可能性”；chance 两种意思都有，口语更常用。',
        [('This job is a great ____ to learn new skills.', ['opportunity', 'possibility'], 0, '有利的机会：opportunity。'),
         ('Is there any ____ that the flight will be delayed?', ['opportunity', 'possibility'], 1, '可能性：possibility。'),
         ('There\'s a good ____ it will rain this afternoon.', ['chance', 'opportunity'], 0, '可能性（口语）：chance。')]),
    'accept-except': ('B2', ['accept', 'except'], 'accept 是动词“接受”；except 是介词“除了（不包括）”。',
        [('She ____ the job offer immediately.', ['accepted', 'excepted'], 0, '接受：accept。'),
         ('Everyone came ____ Tom.', ['accept', 'except'], 1, '除了汤姆（他没来）：except。'),
         ('We\'re open every day ____ Monday.', ['accept', 'except'], 1, '除了周一：except。')]),
    'shade-shadow': ('B2', ['shade', 'shadow'], 'shade 是阴凉处（挡住阳光的地方，不可数）；shadow 是影子（有形状）。中文都可能说成“阴影”。',
        [('Let\'s sit in the ____ of that tree.', ['shade', 'shadow'], 0, '树下的阴凉处：shade。'),
         ('In the evening, the tree cast a long ____ on the grass.', ['shade', 'shadow'], 1, '有形状的影子：shadow。'),
         ('It\'s 35 degrees in the ____.', ['shade', 'shadow'], 0, '在阴凉处：in the shade。')]),
    'damage-hurt': ('B2', ['damage', 'hurt'], 'damage 指东西受损；hurt 指人受伤，也可以指伤感情。',
        [('The storm ____ many houses.', ['damaged', 'hurt'], 0, '房子受损：damage。'),
         ('I fell off my bike and ____ my arm.', ['damaged', 'hurt'], 1, '人受伤：hurt。'),
         ('What you said really ____ my feelings.', ['damaged', 'hurt'], 1, '伤感情：hurt。')]),
    'fit-suit-match': ('B2', ['fit', 'suit', 'match'], 'fit 指尺寸合适；suit 指适合某人（颜色、风格）或时间方便；match 指两样东西相配。',
        [('These shoes don\'t ____ me; they\'re too small.', ['fit', 'suit', 'match'], 0, '尺寸：fit。'),
         ('Red really ____ you.', ['fits', 'suits', 'matches'], 1, '颜色适合某人：suit。'),
         ('Your bag ____ your coat perfectly.', ['fits', 'suits', 'matches'], 2, '两样东西相配：match。')]),
    'reason-cause': ('B2', ['reason', 'cause'], 'cause 是直接造成结果的“原因”（the cause of the fire）；reason 是解释、理由（the reason for / why）。',
        [('Police are trying to find the ____ of the fire.', ['reason', 'cause'], 1, '造成火灾的原因：cause of。'),
         ('What\'s the ____ for your decision?', ['reason', 'cause'], 0, '做决定的理由：reason for。'),
         ('There\'s no ____ to be worried.', ['reason', 'cause'], 0, '没有理由：no reason to。')]),
    'effective-efficient': ('B2', ['effective', 'efficient'], 'effective 是“有效的”（达到目的）；efficient 是“高效的”（省时省力）。',
        [('This medicine is very ____ against headaches.', ['effective', 'efficient'], 0, '有效果：effective。'),
         ('She is an ____ worker; she never wastes time.', ['effective', 'efficient'], 1, '高效：efficient。'),
         ('LED lights are more energy-____.', ['effective', 'efficient'], 1, '节能：energy-efficient。')]),
    'refuse-deny': ('B2', ['refuse', 'deny'], 'refuse 是拒绝做（refuse to do）；deny 是否认（deny doing / deny that）。中文都可能说成“拒绝”。',
        [('He ____ to answer my question.', ['refused', 'denied'], 0, '拒绝做：refuse to do。'),
         ('She ____ taking the money.', ['refused', 'denied'], 1, '否认做过：deny doing。'),
         ('The manager ____ that he had known about the problem.', ['refused', 'denied'], 1, '否认某个说法：deny that。')]),
    'principal-principle': ('C1', ['principal', 'principle'], 'principal 是“校长；主要的”；principle 是“原则、原理”。',
        [('The school ____ gave a speech.', ['principal', 'principle'], 0, '校长：principal。'),
         ('It\'s against my ____ to lie.', ['principals', 'principles'], 1, '原则：principle。'),
         ('The ____ reason for the delay was the weather.', ['principal', 'principle'], 0, '主要的：principal。')]),
    'historic-historical': ('C1', ['historic', 'historical'], 'historic 是“有历史意义的、重大的”；historical 是“历史（上）的、和历史有关的”。',
        [('The moon landing was a ____ moment.', ['historic', 'historical'], 0, '具有历史意义：historic。'),
         ('She writes ____ novels set in the Tang dynasty.', ['historic', 'historical'], 1, '以历史为题材：historical。'),
         ('The library keeps ____ records of the city.', ['historic', 'historical'], 1, '历史上的记录：historical。')]),
}


# Past forms and plurals the dictionary keeps as words of their own (said, raised, borrowed): mapped back to the
# group word, so the look-up sheet finds the group from the form a reader actually taps.
IRREGULAR = {'lent': 'lend', 'said': 'say', 'told': 'tell', 'spoke': 'speak', 'spoken': 'speak', 'saw': 'see', 'seen': 'see',
             'brought': 'bring', 'took': 'take', 'taken': 'take', 'heard': 'hear', 'won': 'win', 'beaten': 'beat', 'learnt': 'learn',
             'stole': 'steal', 'stolen': 'steal', 'wore': 'wear', 'worn': 'wear', 'lost': 'lose', 'lain': 'lie', 'laid': 'lay',
             'rose': 'rise', 'risen': 'rise', 'made': 'make', 'did': 'do', 'done': 'do', 'spent': 'spend', 'paid': 'pay', 'got': 'get',
             'gotten': 'get', 'lay': 'lay'}


def _forms(word):
    """word plus the regular forms that lead back to it: -s, -es, -ed, -d, -ing, -ied / -ies, doubled consonants."""
    w = word.lower()
    out = {w, w + 's', w + 'es', w + 'ed', w + 'd', w + 'ing', w + 'er', w + 'ly'}
    if w.endswith('e'):
        out |= {w[:-1] + 'ing'}
    if w.endswith('y') and len(w) > 2 and w[-2] not in 'aeiou':
        out |= {w[:-1] + 'ied', w[:-1] + 'ies'}
    if len(w) >= 3 and w[-1] not in 'aeiouwxy' and w[-2] in 'aeiou' and w[-3] not in 'aeiou':
        out |= {w + w[-1] + 'ed', w + w[-1] + 'ing'}
    return out


_FORM = {}
for _gid, _g in GROUPS.items():
    for _w in _g[1]:
        for _f in _forms(_w):
            _FORM.setdefault(_f, set()).add(_gid)
for _f, _base in IRREGULAR.items():
    _FORM.setdefault(_f, set()).update(gid for gid, g in GROUPS.items() if _base in [x.lower() for x in g[1]])


def group_of(word):
    """The groups a word belongs to (any of its forms), for the look-up sheet."""
    w = (word or '').lower()
    return [{'id': gid, 'words': GROUPS[gid][1], 'how': GROUPS[gid][2], 'level': GROUPS[gid][0]} for gid in sorted(_FORM.get(w, ()))]


def listing(level=None):
    order = ('A2', 'B1', 'B2', 'C1')
    return [{'id': gid, 'level': g[0], 'words': g[1], 'how': g[2], 'n': len(g[3])}
            for gid, g in sorted(GROUPS.items(), key=lambda kv: (order.index(kv[1][0]), kv[0]))]


def _item(gid, i, rnd):
    sent, opts, ans, why = GROUPS[gid][3][i]
    order = list(range(len(opts)))
    rnd.shuffle(order)
    return {'id': f'{gid}:{i}', 'group': gid, 'prompt': sent, 'options': [opts[k] for k in order], 'answer': order.index(ans), 'explanation': why}


def round_of(groups, seed=None, per=3):
    """An interleaved round over one or more groups (answers included: this is practice, checked on the page)."""
    rnd = random.Random(seed)
    items = [_item(g, i, rnd) for g in groups if g in GROUPS for i in range(min(per, len(GROUPS[g][3])))]
    rnd.shuffle(items)
    return items


def variant(gid, k):
    """Another question of the same group for a word mistake in review, in turn."""
    if gid not in GROUPS:
        return None
    n = len(GROUPS[gid][3])
    it = _item(gid, k % n, random.Random(k * 7 + n))
    return {**it, 'kind': 'word'}


# ---------------------------------------------------------------- the learner's practice

def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS next_word_practice(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), '
              'item TEXT NOT NULL, grp TEXT NOT NULL, correct INTEGER NOT NULL, created REAL NOT NULL)')


def progress(c, uid):
    """group -> {'right', 'tries'} for the groups the learner has practised."""
    out = {}
    if uid:
        for r in c.execute('SELECT grp, SUM(correct) r, COUNT(*) n FROM next_word_practice WHERE user_id=? GROUP BY grp', (uid,)):
            out[r['grp']] = {'right': r['r'], 'tries': r['n']}
    return out


def answer(c, uid, data):
    """Record one answer (checked on the page). A miss makes a review card for the group, which comes back on another
    of its questions each time and leaves after two right in a row."""
    import time
    item = data.get('item') if isinstance(data.get('item'), str) else ''
    gid, _, idx = item.partition(':')
    if gid not in GROUPS or not idx.isdigit() or int(idx) >= len(GROUPS[gid][3]) or type(data.get('correct')) is not bool:
        return {'error': '题目不存在'}, 400
    if not uid:
        return {'saved': False}, 200
    c.execute('INSERT INTO next_word_practice(user_id,item,grp,correct,created) VALUES(?,?,?,?,?)', (uid, item, gid, int(data['correct']), time.time()))
    if not data['correct'] and data.get('from') != 'review':
        level, words, how, _ = GROUPS[gid]
        __import__('skills_service').add_mistake(c, uid, 'question', ' / '.join(words), 'wq:' + gid, how, '', 'vocabulary',
                                                 extra={'group': gid, 'item': int(idx)}, commit=False)
    c.commit()
    return {'saved': True}, 200
