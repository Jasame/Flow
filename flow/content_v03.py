"""Curated pilot expansion. Stable migration is applied once without replacing user content."""
EXTRA_QUESTIONS = [
('tense','By the time we arrived, the film ____.',['starts','has started','had started','will start'],2,'电影开始发生在我们到达之前，即过去的过去，使用过去完成时 had started。'),
('tense','My father usually ____ to work by bus.',['go','goes','is going','has gone'],1,'usually 表示习惯，一般现在时中单数主语 my father 对应 goes。'),
('tense','At eight o’clock last night, I ____ dinner.',['cook','am cooking','was cooking','have cooked'],2,'过去某个时刻正在进行的动作，用过去进行时 was cooking。'),
('tense','I ____ her three times last week.',['have called','call','called','had called'],2,'last week 是已经结束的过去时间，使用一般过去时 called。'),
('clause','This is the café ____ we first met.',['which','where','who','whose'],1,'从句 we first met 缺地点状语，where 相当于 at which。'),
('clause','The girl ____ brother is a doctor sits next to me.',['who','whom','whose','which'],2,'whose 表示所属关系，修饰 brother，意为那个哥哥是医生的女孩。'),
('clause','____ he said surprised everyone.',['That','What','Which','Whether'],1,'主语从句中 said 缺宾语，what 同时引导从句并充当宾语。'),
('clause','I will call you as soon as I ____ home.',['will get','got','get','had got'],2,'as soon as 引导将来时间状语从句，用一般现在时 get 表示将来。'),
('conditional','If you heat ice, it ____.',['melts','would melt','had melted','would have melted'],0,'表达一般规律的零条件句，条件和结果均可用一般现在时。'),
('conditional','We will go for a walk if the weather ____ fine.',['will be','is','was','had been'],1,'真实的将来条件句中，if 从句使用一般现在时 is。'),
('conditional','Unless you water this plant, it ____.',['died','had died','will die','would have died'],2,'unless 相当于 if not，此处主句表达可能的将来结果，用 will die。'),
('conditional','If you ____ any help tomorrow, please call me.',['need','will need','needed','had needed'],0,'条件从句用一般现在时 need，主句可以是祈使句。'),
('subjunctive','If I had more free time now, I ____ another language.',['learn','will learn','would learn','had learned'],2,'与现在事实相反，if + 过去式，主句 would + 动词原形。'),
('subjunctive','If they ____ earlier yesterday, they would have caught the train.',['leave','left','have left','had left'],3,'与过去事实相反，从句使用 had left，与 would have caught 对应。'),
('subjunctive','I wish I ____ the answer now.',['know','knew','have known','will know'],1,'wish 后表达与现在事实相反的愿望，用过去式 knew。'),
('subjunctive','Without your help yesterday, I ____ the task.',['cannot finish','will not finish','would not have finished','do not finish'],2,'without your help yesterday 隐含与过去事实相反的条件，主句用 would not have finished。'),
('nonfinite','Thank you for ____ me.',['help','to help','helping','helped'],2,'for 是介词，后面的动词用动名词 helping。'),
('nonfinite','The window ____ by the ball needs repairing.',['breaking','broke','broken','to break'],2,'window 与 break 为被动关系，用过去分词 broken 作后置定语。'),
('nonfinite','____ English well, she practises every day.',['Learn','To learn','Learned','Learns'],1,'不定式 To learn 作目的状语，表示为了学好英语。'),
('nonfinite','I look forward to ____ from you.',['hear','hearing','heard','be heard'],1,'look forward to 中 to 是介词，后接动名词 hearing。'),
('agreement','Neither of the two answers ____ correct.',['are','were','is','have been'],2,'此题采用正式书面语规则，neither of 作主语时使用单数谓语 is。'),
('agreement','Ten kilometres ____ a long distance to walk.',['are','is','were','have been'],1,'距离作为一个整体概念时按单数处理，用 is。'),
('agreement','The news ____ very encouraging.',['are','have been','were','is'],3,'news 虽以 s 结尾，但在此处是不可数名词，使用 is。'),
('agreement','Not only the students but also their teacher ____ ready.',['are','were','is','have been'],2,'not only ... but also 连接主语时，本题按就近一致原则，teacher 为单数，使用 is。')]
LESSONS={
 'tense': [('先画出时间线','定位时间线索：yesterday / last week 指向已结束的过去；now / Look! 指向当前动作；since / for 常提示持续到现在。'),('再判断动作状态','一般时描述习惯或事实，进行时描述某一时刻正在发生，完成时连接某个参照时间与此前动作。时间词是线索，仍需结合语境。'),('做一次对比','I lived here in 2020. 表示过去事实；I have lived here since 2020. 强调从过去持续到现在。')],
 'clause': [('先找主句','在长句里先圈出主句的主语和谓语，再看其余部分承担什么作用。不要仅按句子长度判断结构。'),('判断从句的角色','修饰名词的是定语从句，充当主语或宾语等名词成分的是名词性从句，表示时间或条件等的是状语从句。'),('检查从句缺什么','The café where we met 中缺地点状语；The café that we visited 中缺 visited 的宾语，因此关系词选择不同。')],
 'conditional': [('真实条件','If it rains tomorrow, we will stay home. 条件从句的一般现在时描述将来可能发生的事，主句表达结果。'),('一般规律','If you heat ice, it melts. 两部分使用一般现在时，描述条件与结果的一般关系。'),('unless 的含义','Unless you leave now, you will miss the bus. 可理解为 If you do not leave now ...；避免机械叠加否定。')],
 'subjunctive': [('与现在事实相反','If I were you, I would ask for help. if 从句用过去式，主句用 would / could / might + 动词原形，表达不同语气。'),('与过去事实相反','If she had left earlier, she would have arrived on time. 从句 had done，主句 would have done。先判断事实发生在哪个时间。'),('留意隐含条件','Without your help, I would have failed. 条件可能藏在 without / but for 等结构中。不要只依靠 if 这个词识别虚拟。')],
 'nonfinite': [('先看是否需要谓语','一个分句已经有谓语时，另一个动词可能需要非谓语形式；但并列谓语或新增从句是另外的结构。'),('再看搭配','enjoy doing、decide to do、look forward to doing 都需要按搭配判断。to 可能是不定式标记，也可能是介词。'),('判断主动被动','the boy standing there：boy 主动站立；the window broken by a ball：window 被打破。非谓语形式还受时间关系和搭配影响。')],
 'agreement': [('找真正的主语','The list of names is ... 中 list 是中心词；of names 是修饰成分，不决定谓语的数。'),('理解整体概念','Ten kilometres is a long distance. 距离、时间或金额被视为整体时，谓语通常按单数处理。'),('注意特殊结构','each、neither 等结构与 not only ... but also 等连接结构需单独判断。本试点按正式书面英语讲解，真实用法可能存在语体差异。')]
}
