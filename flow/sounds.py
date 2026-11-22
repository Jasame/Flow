"""发音入门: sounds Chinese learners often merge, practised as minimal pairs (listen and tell apart, then say).

Each set has a short Chinese explanation of how to make the two sounds, and word pairs that differ only
in that sound. Words play with Flow's pre-generated pronunciations when they exist (browser voice otherwise).
"""
SETS = [
    {'id': 'i-long-short', 'title': '/iː/ 和 /ɪ/', 'sounds': ['iː', 'ɪ'],
     'tip': '/iː/ 嘴角向两边拉开、拖长，像微笑着说"衣——"；/ɪ/ 短而放松，嘴巴半开，舌头稍低，不是短一点的"衣"。',
     'pairs': [('sheep', 'ship'), ('leave', 'live'), ('seat', 'sit'), ('feel', 'fill'), ('beat', 'bit'), ('heat', 'hit')]},
    {'id': 'ae-e', 'title': '/æ/ 和 /e/', 'sounds': ['æ', 'e'],
     'tip': '/æ/ 嘴张得很大，下巴往下掉，舌尖抵下齿，介于"啊"和"哎"之间；/e/ 嘴只半开，像短促的"哎"。',
     'pairs': [('bad', 'bed'), ('man', 'men'), ('sad', 'said'), ('pan', 'pen'), ('had', 'head'), ('sat', 'set')]},
    {'id': 'u-long-short', 'title': '/uː/ 和 /ʊ/', 'sounds': ['uː', 'ʊ'],
     'tip': '/uː/ 双唇收圆、往前突，拖长；/ʊ/ 嘴唇放松、只微微收圆，短促，像轻轻的"乌"。',
     'pairs': [('fool', 'full'), ('pool', 'pull'), ('suit', 'soot'), ('stewed', 'stood')]},
    {'id': 'th-s', 'title': '/θ/ 和 /s/', 'sounds': ['θ', 's'],
     'tip': '/θ/ 舌尖轻轻放在上下齿之间，往外送气，舌头要看得见；/s/ 舌尖在齿后，不伸出来。别把 think 读成 sink。',
     'pairs': [('think', 'sink'), ('thick', 'sick'), ('thing', 'sing'), ('mouth', 'mouse'), ('path', 'pass'), ('faith', 'face')]},
    {'id': 'th-z', 'title': '/ð/ 和 /z/、/d/', 'sounds': ['ð', 'z'],
     'tip': '/ð/ 和 /θ/ 舌位一样，但声带振动（摸喉咙有震感）；不要读成 /z/ 或 /d/。',
     'pairs': [('then', 'den'), ('they', 'day'), ('breathe', 'breeze'), ('those', 'doze'), ('though', 'dough'), ('clothe', 'close')]},
    {'id': 'v-w', 'title': '/v/ 和 /w/', 'sounds': ['v', 'w'],
     'tip': '/v/ 上齿轻咬下唇，振动着送气；/w/ 双唇收圆再迅速张开，牙齿不碰嘴唇。',
     'pairs': [('vest', 'west'), ('vine', 'wine'), ('verse', 'worse'), ('veil', 'whale'), ('vet', 'wet'), ('vow', 'wow')]},
    {'id': 'l-r', 'title': '/l/ 和 /r/', 'sounds': ['l', 'r'],
     'tip': '/l/ 舌尖顶住上齿龈；/r/ 舌尖往后卷但不碰任何地方，双唇略收圆。',
     'pairs': [('light', 'right'), ('lead', 'read'), ('long', 'wrong'), ('collect', 'correct'), ('glass', 'grass'), ('fly', 'fry')]},
    {'id': 'n-l', 'title': '/n/ 和 /l/', 'sounds': ['n', 'l'],
     'tip': '/n/ 气流从鼻子出来，捏住鼻子就发不出；/l/ 气流从舌头两侧出来，捏住鼻子照样能发。南方方言区特别容易混。',
     'pairs': [('night', 'light'), ('knock', 'lock'), ('nine', 'line'), ('snow', 'slow'), ('know', 'low'), ('need', 'lead')]},
    {'id': 'final-voicing', 'title': '词尾的清浊辅音', 'sounds': ['d', 't'],
     'tip': '词尾的浊辅音（/d/ /b/ /g/ /z/）要轻轻带出来，前面的元音也会更长；不要都读成清音，更不要在后面加"呃"。',
     'pairs': [('bed', 'bet'), ('cab', 'cap'), ('bag', 'back'), ('rise', 'rice'), ('prize', 'price'), ('card', 'cart')]},
    {'id': 'sh-s', 'title': '/ʃ/ 和 /s/', 'sounds': ['ʃ', 's'],
     'tip': '/ʃ/ 双唇前突收圆，舌面抬高，像"嘘"；/s/ 嘴角平，舌尖靠近齿龈，像"丝"。',
     'pairs': [('she', 'see'), ('ship', 'sip'), ('shoe', 'sue'), ('sheet', 'seat'), ('shine', 'sign'), ('mesh', 'mess')]},
    {'id': 'ar-schwa', 'title': '/ɑː/ 和 /ʌ/', 'sounds': ['ɑː', 'ʌ'],
     'tip': '/ɑː/ 嘴张大、舌头放低往后，拖长，像"啊——"；/ʌ/ 短促、嘴半开，像轻轻的"阿"。',
     'pairs': [('heart', 'hut'), ('cart', 'cut'), ('march', 'much'), ('calm', 'come'), ('barn', 'bun'), ('dark', 'duck')]},
    {'id': 'ending-n-ng', 'title': '/n/ 和 /ŋ/ 结尾', 'sounds': ['n', 'ŋ'],
     'tip': '/n/ 结尾舌尖顶上齿龈；/ŋ/ 结尾舌根抬起贴软腭，舌尖不动，声音从鼻子出来，像"嗯"。',
     'pairs': [('thin', 'thing'), ('win', 'wing'), ('ran', 'rang'), ('sin', 'sing'), ('ban', 'bang'), ('kin', 'king')]},
]
_WORDS = {w: s for s in SETS for pair in s['pairs'] for w in pair}
_PARTNER = {w: pair[1 - k] for s in SETS for pair in s['pairs'] for k, w in enumerate(pair)}
LISTEN = {  # what to listen for when telling the pair apart
    'i-long-short': '重点听元音的长短：长音拖得更久，嘴角更开。', 'ae-e': '重点听嘴张得多大：/æ/ 更开、更像"啊"。',
    'u-long-short': '重点听元音的长短和嘴唇圆不圆。', 'ar-schwa': '重点听元音长短：/ɑː/ 更长、更靠后。',
    'th-s': '重点听开头或结尾的辅音：/θ/ 是舌尖在齿间漏出的气声，/s/ 是清脆的"丝"。',
    'th-z': '重点听开头的辅音：/ð/ 带振动又有点"漏气"，/d/ 是干脆的爆破，/z/ 是嗡嗡的摩擦。',
    'v-w': '重点听开头：/v/ 有齿唇摩擦的嗡声，/w/ 是圆唇滑过去的声音。', 'l-r': '重点听开头：/r/ 带圆唇和卷舌的色彩，/l/ 更清亮。',
    'n-l': '重点听有没有鼻音：/n/ 带鼻腔共鸣。', 'final-voicing': '重点听词尾前的元音：后面是浊辅音时，元音明显更长。',
    'sh-s': '重点听摩擦声：/ʃ/ 更低沉、更"嘘"，/s/ 更尖。', 'ending-n-ng': '重点听结尾：/ŋ/ 像带鼻音的"嗯"，/n/ 收得更靠前。',
}


def focus_of(word):
    """The sound being practised for a word from the sets, e.g. '/θ/ 和 /s/'."""
    s = _WORDS.get((word or '').lower())
    return f"{s['title']}" if s else ''


def partner_of(word):
    """The other word of its minimal pair (think -> sink), or ''."""
    return _PARTNER.get((word or '').lower(), '')


def listing():
    import vocab_service as vs
    import next_service as nx
    out = []
    for s in SETS:
        pairs = [[{'word': w, 'audio': vs.word_audio(w), 'phonetic': (nx.dictionary().get(w) or {}).get('phonetic', '')} for w in pair] for pair in s['pairs']]
        out.append({'id': s['id'], 'title': s['title'], 'tip': s['tip'], 'listen': LISTEN.get(s['id'], ''), 'pairs': pairs})
    return {'sets': out}
