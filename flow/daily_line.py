"""今日好句 (r27): one English sentence at the top of 今日, with its meaning in Chinese and where it comes from.

Days take turns (China time): a public-domain line one day, the same for everyone; a sentence from one of 语流's own
featured texts the next, at the learner's level, from a text they have not studied yet, linked to it.

Public-domain lines: only works first published before 1929, written in English (no translations, whose wording may
still be protected), by authors who died long ago, each with author, work and year, quoted word for word (a part of
the original; a speech tag such as "the King said" is left out, and " / " marks a line break in verse). No film or
television lines (语流's writing rules), and no "famous sayings" whose source cannot be shown. The Chinese is 语流's
own, or the usual rendering of a famous phrase.
"""
import datetime, hashlib, json, re

import next_service as nx

# id, English, Chinese, author (Chinese · English), work (Chinese 《》 · original), year, level
QUOTES = [
    ('frost-through', 'The best way out is always through.', '走出困境最好的办法，永远是穿过它。',
     '罗伯特·弗罗斯特 Robert Frost', '《仆人的仆人》A Servant to Servants', '1914', 'A2'),
    ('frost-road', 'I took the one less traveled by, / And that has made all the difference.', '我选了人迹更少的那一条，从此一切都不一样了。',
     '罗伯特·弗罗斯特 Robert Frost', '《未选择的路》The Road Not Taken', '1916', 'B1'),
    ('frost-miles', 'The woods are lovely, dark and deep, / But I have promises to keep, / And miles to go before I sleep.',
     '树林可爱、幽暗而深邃，但我还有诺言要遵守，睡前还有很长的路要赶。', '罗伯特·弗罗斯特 Robert Frost', '《雪夜林边停留》Stopping by Woods on a Snowy Evening', '1923', 'B1'),
    ('frost-fences', 'Good fences make good neighbors.', '篱笆扎得牢，邻居处得好。', '罗伯特·弗罗斯特 Robert Frost', '《修墙》Mending Wall', '1914', 'A2'),
    ('hamlet-question', 'To be, or not to be: that is the question.', '活下去，还是不活：这才是问题所在。',
     '威廉·莎士比亚 William Shakespeare', '《哈姆雷特》Hamlet', '约 1600', 'B1'),
    ('hamlet-true', 'This above all: to thine own self be true.', '最要紧的是：对自己要忠实。（thine = your）',
     '威廉·莎士比亚 William Shakespeare', '《哈姆雷特》Hamlet', '约 1600', 'B2'),
    ('hamlet-may-be', 'We know what we are, but know not what we may be.', '我们知道自己现在是什么样，却不知道将来会成为什么样。',
     '威廉·莎士比亚 William Shakespeare', '《哈姆雷特》Hamlet', '约 1600', 'B1'),
    ('hamlet-thinking', 'There is nothing either good or bad, but thinking makes it so.', '事情本无好坏，是想法让它变成了好或坏。',
     '威廉·莎士比亚 William Shakespeare', '《哈姆雷特》Hamlet', '约 1600', 'B2'),
    ('stage', "All the world's a stage, / And all the men and women merely players.", '整个世界是一座舞台，所有的男男女女不过是演员。',
     '威廉·莎士比亚 William Shakespeare', '《皆大欢喜》As You Like It', '约 1599', 'B1'),
    ('true-love', 'The course of true love never did run smooth.', '真爱之路从来都不平坦。',
     '威廉·莎士比亚 William Shakespeare', '《仲夏夜之梦》A Midsummer Night\'s Dream', '约 1595', 'B1'),
    ('greatness', 'Some are born great, some achieve greatness, and some have greatness thrust upon \'em.',
     '有人生来伟大，有人靠努力成就伟大，也有人被伟大硬推到身上。（\'em = them）', '威廉·莎士比亚 William Shakespeare', '《第十二夜》Twelfth Night', '约 1601', 'B2'),
    ('two-cities', 'It was the best of times, it was the worst of times.', '那是最好的时代，也是最坏的时代。',
     '查尔斯·狄更斯 Charles Dickens', '《双城记》A Tale of Two Cities', '1859', 'A2'),
    ('evidence', "Take nothing on its looks; take everything on evidence. There's no better rule.", '别看表面，一切凭证据。没有比这更好的规矩了。',
     '查尔斯·狄更斯 Charles Dickens', '《远大前程》Great Expectations', '1861', 'B1'),
    ('reading', 'I declare after all there is no enjoyment like reading!', '说到底，没有什么乐趣比得上读书！',
     '简·奥斯汀 Jane Austen', '《傲慢与偏见》Pride and Prejudice', '1813', 'B1'),
    ('truth-universal', 'It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.',
     '凡是有钱的单身汉，总想娶位太太，这已经成了一条举世公认的真理。', '简·奥斯汀 Jane Austen', '《傲慢与偏见》Pride and Prejudice', '1813', 'B2'),
    ('home-comfort', 'There is nothing like staying at home for real comfort.', '要说真正舒服，什么都比不上待在家里。',
     '简·奥斯汀 Jane Austen', '《爱玛》Emma', '1815', 'A2'),
    ('no-bird', 'I am no bird; and no net ensnares me: I am a free human being with an independent will.',
     '我不是鸟，也没有网能困住我：我是一个有独立意志的自由的人。', '夏洛蒂·勃朗特 Charlotte Brontë', '《简·爱》Jane Eyre', '1847', 'B2'),
    ('married-him', 'Reader, I married him.', '读者啊，我嫁给了他。', '夏洛蒂·勃朗特 Charlotte Brontë', '《简·爱》Jane Eyre', '1847', 'A2'),
    ('souls', 'Whatever our souls are made of, his and mine are the same.', '不管我们的灵魂是什么做的，他的和我的是一样的。',
     '艾米莉·勃朗特 Emily Brontë', '《呼啸山庄》Wuthering Heights', '1847', 'B1'),
    ('less-difficult', 'What do we live for, if it is not to make life less difficult to each other?', '我们活着，如果不是为了让彼此的日子好过一点，又是为了什么呢？',
     '乔治·艾略特 George Eliot', '《米德尔马契》Middlemarch', '1872', 'B2'),
    ('storms', "I'm not afraid of storms, for I'm learning how to sail my ship.", '我不怕风暴，因为我正在学着驾驶自己的船。',
     '路易莎·梅·奥尔科特 Louisa May Alcott', '《小妇人》Little Women', '1869', 'B1'),
    ('new-day', "Isn't it nice to think that tomorrow is a new day with no mistakes in it yet?", '想想明天是全新的一天，还一个错都没犯，是不是很好？',
     '露西·莫德·蒙哥马利 L. M. Montgomery', '《绿山墙的安妮》Anne of Green Gables', '1908', 'B1'),
    ('garden', 'If you look the right way, you can see that the whole world is a garden.', '只要换个角度看，你会发现整个世界都是一座花园。',
     '弗朗西丝·霍奇森·伯内特 Frances Hodgson Burnett', '《秘密花园》The Secret Garden', '1911', 'A2'),
    ('grow-up', 'All children, except one, grow up.', '所有的孩子都会长大，只有一个例外。',
     '詹姆斯·巴里 J. M. Barrie', '《彼得和温迪》Peter and Wendy', '1911', 'A2'),
    ('begin', 'Begin at the beginning, and go on till you come to the end: then stop.', '从头开始，一直讲到结尾，然后停下。',
     '刘易斯·卡罗尔 Lewis Carroll', '《爱丽丝梦游仙境》Alice\'s Adventures in Wonderland', '1865', 'A2'),
    ('curiouser', 'Curiouser and curiouser!', '越来越奇怪了！（爱丽丝一激动，把 more curious 说成了 curiouser）',
     '刘易斯·卡罗尔 Lewis Carroll', '《爱丽丝梦游仙境》Alice\'s Adventures in Wonderland', '1865', 'A2'),
    ('impossible', "Why, sometimes I've believed as many as six impossible things before breakfast.", '哎呀，我有时候早饭前就相信了多达六件不可能的事。',
     '刘易斯·卡罗尔 Lewis Carroll', '《爱丽丝镜中奇遇》Through the Looking-Glass', '1871', 'B1'),
    ('courage', 'Courage is resistance to fear, mastery of fear—not absence of fear.', '勇气是抵抗恐惧、驾驭恐惧，而不是没有恐惧。',
     '马克·吐温 Mark Twain', '《傻瓜威尔逊》Pudd\'nhead Wilson', '1894', 'B2'),
    ('travel-hopefully', 'To travel hopefully is a better thing than to arrive, and the true success is to labour.', '满怀希望地赶路，比到达终点更好；真正的成功在于努力本身。',
     '罗伯特·路易斯·史蒂文森 Robert Louis Stevenson', '《黄金国》El Dorado', '1881', 'B2'),
    ('multitudes', 'I am large, I contain multitudes.', '我很辽阔，我包容万千。', '沃尔特·惠特曼 Walt Whitman', '《自我之歌》Song of Myself', '1892', 'B1'),
    ('hope-feathers', 'Hope is the thing with feathers / That perches in the soul.', '希望是长着羽毛的东西，栖息在灵魂里。',
     '艾米莉·狄金森 Emily Dickinson', '《希望是长着羽毛的东西》Hope Is the Thing with Feathers', '1891', 'B1'),
    ('beauty', 'A thing of beauty is a joy for ever.', '美的事物是永恒的喜悦。', '约翰·济慈 John Keats', '《恩底弥翁》Endymion', '1818', 'A2'),
    ('well-done', 'Well done is better than well said.', '做得好胜过说得好。', '本杰明·富兰克林 Benjamin Franklin', '《穷理查年鉴》Poor Richard\'s Almanack', '1737', 'A2'),
    ('lost-time', 'Lost time is never found again.', '失去的时间再也找不回来。', '本杰明·富兰克林 Benjamin Franklin', '《穷理查年鉴》Poor Richard\'s Almanack', '1748', 'A2'),
    ('early-to-bed', 'Early to bed and early to rise, makes a man healthy, wealthy, and wise.', '早睡早起，让人健康、富有又聪明。',
     '本杰明·富兰克林 Benjamin Franklin', '《穷理查年鉴》Poor Richard\'s Almanack', '1735', 'A2'),
    ('enthusiasm', 'Nothing great was ever achieved without enthusiasm.', '没有热情，就成就不了任何伟大的事。',
     '拉尔夫·沃尔多·爱默生 Ralph Waldo Emerson', '《论圆》Circles', '1841', 'B1'),
    ('trust-thyself', 'Trust thyself: every heart vibrates to that iron string.', '相信你自己：每颗心都随着这根铁弦振动。（thyself = yourself）',
     '拉尔夫·沃尔多·爱默生 Ralph Waldo Emerson', '《论自助》Self-Reliance', '1841', 'B2'),
    ('deliberately', 'I went to the woods because I wished to live deliberately.', '我走进森林，是因为我想从容不迫、清醒地生活。',
     '亨利·戴维·梭罗 Henry David Thoreau', '《瓦尔登湖》Walden', '1854', 'B1'),
    ('by-the-people', 'Government of the people, by the people, for the people, shall not perish from the earth.', '民有、民治、民享的政府将永世长存。',
     '亚伯拉罕·林肯 Abraham Lincoln', '《葛底斯堡演说》Gettysburg Address', '1863', 'B2'),
    ('optimism', 'Optimism is the faith that leads to achievement.', '乐观是引向成就的信念。', '海伦·凯勒 Helen Keller', '《乐观》Optimism', '1903', 'B1'),
    ('stars', 'We are all in the gutter, but some of us are looking at the stars.', '我们都身在阴沟里，但仍有人仰望星空。',
     '奥斯卡·王尔德 Oscar Wilde', '《温德米尔夫人的扇子》Lady Windermere\'s Fan', '1892', 'B1'),
    ('pure-simple', 'The truth is rarely pure and never simple.', '真相很少纯粹，也从不简单。', '奥斯卡·王尔德 Oscar Wilde', '《不可儿戏》The Importance of Being Earnest', '1895', 'B1'),
]
BY_ID = {q[0]: q for q in QUOTES}
WORDS = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _quote(q):
    qid, en, zh, who, work, year, level = q
    return {'kind': 'quote', 'id': 'q:' + qid, 'label': '公版名句', 'en': en, 'say': en.replace(' / ', ', '), 'zh': zh,
            'source': f'{who}，{work}，{year}' + ('' if year.startswith('约') else ' 年'), 'level': level}


def quote(qid):
    q = BY_ID.get(qid)
    return _quote(q) if q else None


def _day(now=None):
    return datetime.datetime.fromtimestamp(now, nx.TZ).date() if now else datetime.datetime.now(nx.TZ).date()


def _text_line(c, uid, level, day, skip=()):
    """A sentence from one of 语流's featured texts at this level that the learner has not studied (nor today's
    plan article), with the expression it teaches: the same for everyone at that level and day, unless studied."""
    done = nx._done(c, uid) if uid else {}
    picks = []
    for r, p in nx._public_packs(c, level):
        # not news (unreviewed), imports, serial episodes (read in order) or what the learner has studied
        if r['origin'] in ('daily', 'import') or not nx.featured(p) or p.get('series') or p['id'] in skip or 'check' in done.get(p['id'], set()):
            continue
        picks.append(p)
    if not picks:
        return None
    picks.sort(key=lambda p: hashlib.sha256(f"{day}|{level}|{p['id']}".encode()).hexdigest())
    for p in picks[:12]:
        sents = nx.sentences(p.get('body', ''))
        for x in p.get('expressions', []):
            t = (x.get('text') or '').strip()
            if not t or not x.get('meaning'):
                continue
            k = next((k for k, s in enumerate(sents) if t.lower() in s.lower()), None)
            # a whole sentence of 6 to 22 words (it sits above the plan): not a dialogue label, nor the greeting of a letter
            if k is None or not 6 <= len(WORDS.findall(sents[k])) <= 22 or ':' in sents[k][:14] or re.match(r'(Hi|Hello|Dear|Hey)\b', sents[k]):
                continue
            audio = nx.audio_index()
            return {'kind': 'text', 'id': f"m:{p['id']}:{k}", 'label': '语流文章', 'en': sents[k], 'say': sents[k],
                    'zh': f"「{t}」：{x['meaning']}", 'note': x.get('note') or '', 'expression': t, 'meaning': x['meaning'],
                    'source': f"出自《{p['title']}》 · {nx.cefr(p)}", 'pack': p['id'], 'i': k, 'title': p['title'], 'level': nx.cefr(p),
                    'audio': audio[1] if p['id'] in audio[0] else 0, 'href': f"#/m/{p['id']}/read"}
    return None


def today(c, uid, level, now=None, skip=()):
    """今日好句: a public-domain line on even days, a sentence from a 语流 text on odd days (China time)."""
    day = _day(now)
    n = day.toordinal()
    line = None
    if n % 2:
        line = _text_line(c, uid, level, day.isoformat(), skip)
    if not line:
        line = _quote(QUOTES[(n // 2) % len(QUOTES)])
    line['day'] = day.isoformat()
    return line


def sentence_of(data):
    """The sentence a 跟读 of a public-domain line is checked against, by its id (data['quote']); None for anything
    else (a text's sentence goes the usual way, by pack and index)."""
    q = BY_ID.get(str(data.get('quote') or ''))
    return q[1].replace(' / ', ', ') if q else None
