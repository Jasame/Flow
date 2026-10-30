TOPICS = [
('tense','时态与时间','建立时间与动作之间的联系。','先辨认时间线索，再判断动作是习惯、正在进行还是已经完成。','She has lived here since 2020.','since 表示从过去延续到现在，常与现在完成时搭配。',[]),
('clause','从句与句子结构','看懂句子的主干和修饰关系。','先找主句，再判断从句承担名词、形容词还是副词的作用。','The book that you lent me is useful.','that 引导定语从句，修饰 the book。',[]),
('conditional','条件句','区分真实条件与假设情景。','真实的将来条件句通常用 if + 一般现在时，主句用 will + 动词原形。','If it rains tomorrow, we will stay home.','条件从句用 rains 表示将来条件。',['tense','clause']),
('subjunctive','虚拟语气','表达与事实不同的假设。','与现在事实相反：if + 过去式，主句 would + 动词原形；与过去事实相反：if + had done，主句 would have done。','If I were you, I would take a break.','这里表达与现在事实相反的假设。',['conditional']),
('nonfinite','非谓语动词','理解 to do、doing 与 done。','结合动词搭配和主动被动关系选择形式；介词后通常接动名词。','She enjoys reading in the evening.','enjoy 后接动名词作宾语。',['clause']),
('agreement','主谓一致','让谓语与真正的主语一致。','识别主语中心词，不让介词短语等修饰成分干扰判断。','The list of names is on the desk.','主语中心词是单数 list，谓语用 is。',['clause'])]
QUESTIONS = [
('tense','She ____ here since 2020.',['lives','has lived','lived','is living'],1,'since 2020 表示从过去延续到现在，应使用现在完成时。'),
('tense','Look! The children ____ in the garden.',['play','played','are playing','have played'],2,'Look 提示眼下正在发生的动作，使用现在进行时。'),
('clause','The book ____ you lent me is useful.',['who','that','where','when'],1,'先行词 book 指物，关系词在定语从句中作宾语，可用 that。'),
('clause','I do not know ____ she will arrive.',['which','whose','when','what'],2,'这里询问到达时间，when 引导宾语从句。'),
('conditional','If it ____ tomorrow, we will stay home.',['rains','will rain','rained','had rained'],0,'真实将来条件句中，if 从句用一般现在时表示将来。'),
('conditional','You will miss the bus unless you ____ now.',['left','leave','will leave','had left'],1,'unless 引导真实将来条件，从句使用一般现在时。'),
('subjunctive','If I ____ you, I would take a break.',['am','will be','were','have been'],2,'与现在事实相反的假设中，be 动词在正式表达中通常用 were。'),
('subjunctive','If she had studied harder, she ____ the exam.',['passes','will pass','would pass','would have passed'],3,'与过去事实相反：if + had done，主句使用 would have done。'),
('nonfinite','She enjoys ____ in the evening.',['read','to read','reading','reads'],2,'enjoy 后接动名词 reading 作宾语。'),
('nonfinite','He decided ____ abroad.',['study','studying','studied','to study'],3,'decide 后接 to do，表示决定做某事。'),
('agreement','The list of names ____ on the desk.',['are','is','were','have been'],1,'主语中心词 list 是单数，of names 不改变主语的数。'),
('agreement','Each of the students ____ a notebook.',['have','has','are having','were having'],1,'each 作主语中心词时按单数处理，使用 has。')]
