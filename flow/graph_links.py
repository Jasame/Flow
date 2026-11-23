"""How the 44 grammar points connect, and why Chinese speakers trip on each.

Three kinds of link make the graph a network rather than a list:
- prerequisite (先学 → 接下来): from the curriculum (subskills.prereq);
- confusable (易混): pairs learners mix up, each with a one-line way to tell them apart and a mixed practice round;
- together (常一起出现): points that appear in the same materials most often, worked out from the corpus.

L1 notes (中文思维陷阱) say where the Chinese way of saying it leads English astray, with one Chinese sentence, the
typical wrong English and the right English. All content is original.
"""

# node -> (why Chinese speakers get it wrong, Chinese sentence, typical wrong English, right English)
L1 = {
    'tense-present': ('中文动词不随主语变化，也常省略“正在”，所以英语里第三人称单数的 -s 和进行时最容易漏。',
                      '他每天走路上班。', 'He walk to work every day.', 'He walks to work every day.'),
    'tense-past': ('中文靠“昨天”“了”表示过去，动词本身不变，于是英语动词忘了变过去式。',
                   '我昨天去了图书馆。', 'I go to the library yesterday.', 'I went to the library yesterday.'),
    'tense-perfect': ('中文“了”“过”既能对应过去时也能对应完成时；只要和现在有关（到现在为止、since、for），英语就要用完成时。',
                      '我在这儿住了五年了（现在还住）。', 'I live here for five years.', 'I have lived here for five years.'),
    'tense-future': ('中文“等我到了”里自然带着将来的意思，英语时间和条件从句却不用 will。',
                     '等我到了就给你发消息。', 'When I will arrive, I will text you.', "When I arrive, I'll text you."),
    'tense-past-perfect': ('中文很少标出“过去的过去”，讲故事时全用一般过去时，先后顺序就乱了。',
                           '我到车站时，火车已经开走了。', 'When I got to the station, the train left.', 'When I got to the station, the train had left.'),
    'tense-perfect-continuous': ('中文“一直在……”既能说持续也能说结果；英语说“持续多久”用 have been doing，说“完成了多少”用 have done。',
                                 '我写报告写了一上午，已经写完三份了。', 'I have been writing three reports this morning.',
                                 "I have been writing reports all morning, and I've finished three."),
    'voice-basic': ('中文常常不用“被”也是被动（“饭做好了”），英语主语是承受动作的一方时必须用 be + 过去分词。',
                    '这座桥是很多年前建的。', 'The bridge built many years ago.', 'The bridge was built many years ago.'),
    'voice-tenses': ('中文很少说“正在被”“已经被”，英语被动却要跟着时态变：is being done、has been done。',
                     '路正在修。', 'The road is repairing.', 'The road is being repaired.'),
    'voice-causative': ('中文“我剪了头发”不说明是谁剪的，英语直接说 I cut my hair 是自己动手剪；请别人做要用 have / get sth done。',
                        '我昨天去理发了。', 'I cut my hair yesterday.', 'I had my hair cut yesterday.'),
    'modal-ability': ('中文“能、会、可以”常混用；英语说过去某一次经过努力做成了，用 was able to，不用 could。',
                      '我找了半天，终于找到了钥匙。', 'I could finally find my keys.', 'I was finally able to find my keys.'),
    'modal-obligation': ('中文“不用”和“不准”只差一个字，英语 don\'t have to（不必）和 mustn\'t（禁止）意思却完全相反。',
                         '明天周日，你不用早起。', "You mustn't get up early tomorrow.", "You don't have to get up early tomorrow."),
    'modal-deduction': ('中文“不可能是”是推测，英语表示“不可能”用 can\'t，mustn\'t 是“禁止”。',
                        '那不可能是她，她在北京。', "That mustn't be her. She's in Beijing.", "That can't be her. She's in Beijing."),
    'modal-past': ('中文“本来应该”“肯定已经”后面动词不变，英语对过去的推测和后悔要用 情态动词 + have done。',
                   '你本来应该告诉我的。', 'You should tell me.', 'You should have told me.'),
    'clause-relative': ('中文修饰语放在名词前（“我昨天买的书”），英语定语从句放在名词后，还常多加一个代词。',
                        '我昨天买的那本书很有用。', 'The book I bought it yesterday is useful.', 'The book (that) I bought yesterday is useful.'),
    'clause-noun': ('中文疑问词放在原处就能嵌进句子（“你知道他住哪儿吗”），英语宾语从句要改成陈述语序。',
                    '你知道他住在哪儿吗？', 'Do you know where does he live?', 'Do you know where he lives?'),
    'clause-adverb': ('中文“因为……所以……”“虽然……但是……”成对出现，英语连词只用一个。',
                      '因为下雨，所以我们待在家里。', 'Because it rained, so we stayed at home.', 'Because it rained, we stayed at home.'),
    'clause-nondefining': ('中文没有“限制 / 非限制”的逗号区别；英语加逗号是补充说明，而且不能用 that。',
                           '我姐姐住在加拿大，下周来看我们。', 'My sister that lives in Canada is visiting us.', 'My sister, who lives in Canada, is visiting us.'),
    'clause-reported': ('中文转述别人的话，时态不用变；英语转述过去说的话，时态一般要往后退一步。',
                        '他说他会给我打电话。', 'He said he will call me.', 'He said he would call me.'),
    'conditional-real': ('中文“如果明天下雨”里的“会”容易被带进 if 从句；英语 if 从句用一般现在时表示将来。',
                         '如果明天下雨，我们就待在家。', 'If it will rain tomorrow, we will stay at home.', 'If it rains tomorrow, we will stay at home.'),
    'conditional-unless': ('“除非……否则……”中文常带否定词，英语 unless 本身就是 if not，后面不再加 not。',
                           '除非你道歉，否则她不会原谅你。', "Unless you don't apologise, she won't forgive you.", "Unless you apologise, she won't forgive you."),
    'conditional-modal': ('中文条件句的主句常省略情态词（“累了就先走”），英语要用 can、should、might 说清是可以、应该还是可能。',
                          '你要是累了，可以先走。', 'If you are tired, you leave first.', 'If you are tired, you can leave first.'),
    'subjunctive-now': ('中文“要是我有时间”动词不变，假设和真实条件看不出区别；英语与现在事实相反要“退一步”用过去式。',
                        '要是我有时间（可惜没有），我就学日语了。', 'If I have time, I will learn Japanese.', 'If I had time, I would learn Japanese.'),
    'subjunctive-past': ('中文“要是当时……就……了”靠语气，英语与过去事实相反要用 had done … would have done。',
                         '要是我早点出门，就赶上火车了。', 'If I left earlier, I would catch the train.', 'If I had left earlier, I would have caught the train.'),
    'subjunctive-mixed': ('中文一句话里可以自由混合时间，英语错综条件要分别看两半：过去的条件用 had done，现在的结果用 would do。',
                          '要是我当年学了开车，现在就不用挤公交了。', "If I learned to drive, I wouldn't have taken the bus now.",
                          "If I had learned to drive, I wouldn't be taking the bus now."),
    'subjunctive-wish': ('中文“希望”什么都能接，英语 wish 只接不太可能实现的愿望（用过去式），能实现的祝愿用 hope。',
                         '希望你旅途愉快。', 'I wish you enjoy your trip.', 'I hope you enjoy your trip.'),
    'nonfinite-infinitive': ('中文动词可以直接连用（“决定出国”“想去”），英语第二个动词前常要加 to。',
                             '他决定出国读书。', 'He decided study abroad.', 'He decided to study abroad.'),
    'nonfinite-gerund': ('中文动词直接当主语、宾语，英语要变成 doing；look forward to、be used to 里的 to 是介词，后面也接 doing。',
                         '我期待收到你的回信。', 'I look forward to hear from you.', 'I look forward to hearing from you.'),
    'nonfinite-participle': ('中文“无聊的”不分“让人无聊”和“感到无聊”，英语 boring（让人觉得）和 bored（人感到）要分清。',
                             '这部电影很无聊，我看得很无聊。', 'The film was bored and I was boring.', 'The film was boring and I was bored.'),
    'nonfinite-clause': ('中文前半句可以省略主语、后半句换人说；英语句首分词短语的逻辑主语必须是主句的主语。',
                         '我走进房间时，灯灭了。', 'Walking into the room, the lights went off.', 'As I walked into the room, the lights went off.'),
    'agreement-head': ('中文动词不随主语变；英语长主语里离谓语最近的名词常被误当成主语。',
                       '这些产品的质量很好。', 'The quality of these products are good.', 'The quality of these products is good.'),
    'agreement-each': ('中文“每个人”“大家”听上去是很多人，英语 everyone、each、every 作主语却要用单数。',
                       '每个学生都有一本笔记本。', 'Every student have a notebook.', 'Every student has a notebook.'),
    'agreement-either': ('中文“不是……就是……”不影响动词；英语 either…or、neither…nor 的谓语要跟最近的主语一致。',
                         '不是你去，就是他去。', 'Either you or he are going.', 'Either you or he is going.'),
    'det-article': ('中文没有冠词，最常见的是漏掉 a / the，或者第一次提到就用 the。',
                    '我在公园里看见一只狗。', 'I saw dog in park.', 'I saw a dog in the park.'),
    'det-zero': ('反过来，中文的“这个、那个”容易被套成 the；泛指一类、三餐、球类前面不加冠词。',
                 '我喜欢音乐。', 'I like the music.', 'I like music.'),
    'det-quantity': ('中文名词没有单复数、可数不可数之分；英语 advice、information、news 不可数，不能加 -s，也不能和 a、many 连用。',
                     '他给了我很多建议。', 'He gave me many advices.', 'He gave me a lot of advice.'),
    'compare-basic': ('中文“更”“最”放在形容词前面，英语短形容词要变形（bigger），不说 more big。',
                      '这个房间更大。', 'This room is more big.', 'This room is bigger.'),
    'compare-pattern': ('中文“越……越……”很灵活，英语要用固定结构 the + 比较级 …，the + 比较级 …。',
                        '你练得越多，就会越好。', 'More you practise, more better you become.', 'The more you practise, the better you become.'),
    'link-contrast': ('中文“虽然……但是……”成对出现，英语 although 和 but 只能留一个；despite 后面接名词，不接句子。',
                      '虽然他很努力，但还是失败了。', 'Although he tried hard, but he failed.', 'Although he tried hard, he failed.'),
    'link-cause': ('中文“因为”后面接什么都行；英语 because 接句子，because of 接名词。',
                   '因为大雾，航班延误了。', 'Because the fog, the flights were delayed.', 'Because of the fog, the flights were delayed.'),
    'link-purpose': ('中文“为了不……”否定词位置随意，英语要说 so as not to / in order not to，not 放在 to 前面。',
                     '为了不忘记，我把它写了下来。', 'I wrote it down for not forgetting it.', 'I wrote it down so as not to forget it.'),
    'prep-time-place': ('中文一个“在”就够了，英语要看是时间点、某一天还是一段时间、一个范围，分别用 at、on、in。',
                        '我们周一早上见。', "Let's meet in Monday morning.", "Let's meet on Monday morning."),
    'prep-pattern': ('中文“擅长数学”“依赖父母”不需要介词，英语有固定的介词搭配，要整块记。',
                     '她擅长数学。', 'She is good in maths.', 'She is good at maths.'),
    'emph-cleft': ('中文用“是……的”强调，直接套成 is … 是不行的，英语要用 It is / was … that …。',
                   '是价格让我改变了主意。', 'Is the price made me change my mind.', 'It was the price that made me change my mind.'),
    'emph-inversion': ('中文否定词放句首，语序不变；英语 never、seldom、not until 等放句首时，助动词要提前。',
                       '我从没见过这么美的日落。（强调）', 'Never I have seen such a beautiful sunset.', 'Never have I seen such a beautiful sunset.'),
}

# (a, b, how to tell them apart)
CONFUSABLE = [
    ('tense-past', 'tense-perfect', '有具体的过去时间（yesterday、in 2019）用过去时；和现在有关、没说具体时间用完成时。'),
    ('tense-perfect', 'tense-perfect-continuous', '说完成了多少、做了几次用 have done；说持续了多久、还在做用 have been doing。'),
    ('tense-past', 'tense-past-perfect', '两件过去的事，先发生的那件用 had done；只讲一件、按顺序讲用过去时就够了。'),
    ('tense-future', 'conditional-real', '主句说将来用 will；if、when 引导的从句里表示将来，用一般现在时。'),
    ('voice-basic', 'nonfinite-participle', 'was broken 是完整的被动谓语；a broken window 里 broken 只是修饰名词的分词。'),
    ('voice-basic', 'voice-causative', 'My car was repaired 只说车被修了；I had my car repaired 强调是我请人修的。'),
    ('modal-deduction', 'modal-obligation', 'must 推测“一定是”，否定推测用 can\'t；mustn\'t 永远是“禁止”。'),
    ('modal-past', 'subjunctive-past', 'should have done 是“本该做”（后悔、责备）；would have done 是“（假如……）就会做”。'),
    ('subjunctive-now', 'conditional-real', 'if I have time 是真的可能有时间；if I had time 是现在没有，只是假设。'),
    ('subjunctive-past', 'subjunctive-mixed', '条件和结果都在过去用 had done … would have done；结果落在现在用 would do。'),
    ('subjunctive-wish', 'subjunctive-now', 'wish 后面的从句和 if 假设一样“退一步”：现在用过去式，过去用 had done。'),
    ('clause-relative', 'clause-nondefining', '不加逗号是“限定是哪一个”；加逗号是“补充一句”，而且不能用 that。'),
    ('clause-relative', 'clause-noun', '前面有名词、从句修饰它，是定语从句；从句本身当主语、宾语，是名词性从句（what = the thing that）。'),
    ('clause-noun', 'clause-reported', '两者都用陈述语序；转述过去的话时，时态通常还要后退一步。'),
    ('emph-cleft', 'clause-relative', 'It was Tom that… 去掉 It was … that 句子仍然完整，是强调句；不完整就是定语从句。'),
    ('link-contrast', 'clause-adverb', 'although 后面接句子，despite / in spite of 接名词或 doing；however 是副词，不能连接两个句子。'),
    ('link-cause', 'clause-adverb', 'because 接句子，because of / due to 接名词；so 引出结果，不能和 because 同时用。'),
    ('nonfinite-infinitive', 'nonfinite-gerund', 'remember to do 是“记得要去做”，remember doing 是“记得做过”；stop、try、forget 也一样。'),
    ('nonfinite-participle', 'nonfinite-clause', '分词放在名词后修饰名词是定语；放在句首说明时间、原因，是状语，逻辑主语要和主句一致。'),
    ('det-article', 'det-zero', '第一次提到用 a，再提或大家都知道用 the；泛指一类、三餐、球类不加冠词。'),
    ('agreement-each', 'agreement-either', 'each、every、everyone 作主语一律单数；either…or、neither…nor 要看离动词最近的那个。'),
    ('compare-basic', 'compare-pattern', '两者比较用比较级，三者以上用最高级；越来越、越…越…有固定结构。'),
    ('link-purpose', 'nonfinite-infinitive', '表示目的时，to do、in order to do、so as to do 都可以；否定只能说 in order not to / so as not to。'),
    ('prep-pattern', 'nonfinite-gerund', '介词后面接动词，一律用 doing：good at cooking、interested in joining。'),
    ('conditional-unless', 'conditional-real', 'unless = if not，unless 后面不再用否定。'),
    ('emph-inversion', 'subjunctive-past', 'Had I known 是省略 if 的倒装条件句；Never have I seen 是否定词提前的倒装。'),
    ('tense-present', 'tense-perfect', '说现在的习惯和事实用一般现在时；从过去一直持续到现在（for、since）要用完成时：I have lived here for five years。'),
    ('voice-basic', 'voice-tenses', 'be 动词决定被动的时态：is done、was done、has been done、is being done、will be done。'),
    ('modal-ability', 'modal-deduction', 'could 说过去的能力（I could swim at five）是“会”；说现在的可能（It could rain）是推测。'),
    ('conditional-real', 'conditional-modal', '主句说“会怎样”用 will；说“可以、应该、可能”用 can、should、might，也可以直接用祈使句。'),
    ('agreement-head', 'agreement-each', '谓语看真正的中心词：the price of vegetables 看 price；each of the rooms 看 each，都用单数。'),
    ('det-article', 'det-quantity', '可数名词单数前要有 a / the；不可数名词（advice、water）前不能用 a，用 some、much、a piece of。'),
    ('prep-time-place', 'prep-pattern', '时间地点的 in / on / at 看是点、某一天还是范围；动词、形容词后的介词是固定搭配，要整块记。'),
]


def confusable(node):
    """[(other point, how to tell them apart)] for one point."""
    out = []
    for a, b, how in CONFUSABLE:
        if node == a:
            out.append((b, how))
        elif node == b:
            out.append((a, how))
    return out


def pair_note(a, b):
    return next((how for x, y, how in CONFUSABLE if {x, y} == {a, b}), None)


# Two curriculum prerequisites pointed the wrong way: A2 points (adverbial clauses, the infinitive) "needed" a B1 one
# (noun clauses). Learners follow the route in level order, so they now build on A2 points.
PREREQ_FIX = {'clause-adverb': ('clause-noun', 'clause-relative'), 'nonfinite-infinitive': ('clause-noun', 'tense-present')}


def install(c):
    """Migration graph-2.2: fix those prerequisites, and record the confusable pairs as graph edges."""
    if c.execute("SELECT 1 FROM migrations WHERE version='graph-2.2'").fetchone():
        return
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for node, (old, new) in PREREQ_FIX.items():
        c.execute('UPDATE subskills SET prereq=? WHERE id=? AND prereq=?', (new, node, old))
        if 'kg_edges' in tables:
            c.execute("DELETE FROM kg_edges WHERE source=? AND target=? AND relation='prerequisite'", (old, node))
            c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)', (new, node, 'prerequisite', 'curriculum'))
    if 'kg_edges' in tables:
        for a, b, _ in CONFUSABLE:
            c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)', (a, b, 'confusable', 'graph-links'))
    c.execute("INSERT INTO migrations VALUES('graph-2.2')")
