"""corpus_data/meaning-fixes.json: the senses reviewed by hand that override ECDICT on word cards and in look-ups."""
import json, re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import next_service as nx, vocab_service as vs

FIXES = json.loads((ROOT / 'corpus_data' / 'meaning-fixes.json').read_text(encoding='utf-8'))['words']
POS = {'n', 'v', 'vt', 'vi', 'adj', 'adv', 'prep', 'conj', 'pron', 'int', 'interj', 'num', 'art', 'aux', 'abbr'}
# one 「；」 part: a part of speech and its senses ("v. 意思是, 意味着"), or a note in full-width brackets first
# ("（find 的过去式）", "（minutes）会议记录"); the card shows each part on its own line
PART = re.compile(r'^(?:([a-z]+)\. (\S.*)|（[^（）]+）.*)$')


class MeaningFixFormatTests(unittest.TestCase):
    def test_every_fix_is_a_dictionary_word(self):
        d = nx.dictionary()
        self.assertEqual([w for w in FIXES if w not in d], [])

    def test_every_fix_is_shown(self):
        """dictionary-flow.json is built with the fixes (tools/build_dictionary.py), so the card shows exactly them."""
        d = nx.dictionary()
        self.assertEqual([w for w, m in FIXES.items() if d[w]['meaning'] != m], [])

    def test_every_fix_has_parts_of_speech_and_clean_text(self):
        bad = []
        for w, m in FIXES.items():
            parts = [PART.match(p) for p in m.split('；')]
            tags = [p.group(1) for p in parts if p and p.group(1)]
            ok = all(parts) and bool(tags) and all(t in POS for t in tags)
            # no ASCII ';' (the card breaks the line there too), no stray \r, backslashes, domain tags or ASCII brackets
            ok = ok and not re.search(r'[;\r\n\t\\\[\]【】()]', m) and m.count('（') == m.count('）')
            ok = ok and not re.search(r',(?! )|, ,|，，|,$', m) and len(m) <= 160
            if not ok:
                bad.append((w, m))
        self.assertEqual(bad, [])

    def test_no_sense_repeats_within_a_part(self):
        bad = []
        for w, m in FIXES.items():
            for p in m.split('；'):
                senses = [s.strip() for s in re.sub(r'^[a-z]+\. ', '', p).split(', ') if s.strip()]
                if len(senses) != len(set(senses)):
                    bad.append((w, p))
        self.assertEqual(bad, [])


class KnownBadMeaningTests(unittest.TestCase):
    """Common words whose ECDICT entry put a rare, technical or wrong sense first (before→after in the notes)."""

    def meaning(self, word):
        return nx.dictionary()[word]['meaning']

    def test_main_sense_and_part_of_speech_come_first(self):
        for word, start in {
            'start': 'v. 开始',      # was n. 惊起
            'keep': 'v. 保持',       # was n. 生计
            'must': 'aux. 必须',     # was n. 必须, 未发酵葡萄汁
            'kill': 'v. 杀死',       # was n. 杀, 杀戮, 小河
            'lot': 'n. 许多',        # was n. 运气, 签, 抽签
            'natural': 'adj. 自然的',  # was n. 白痴
            'hardly': 'adv. 几乎不',  # was adv. 刚刚
            'mere': 'adj. 仅仅的',    # was n. 小湖, 池塘
            'tidy': 'adj. 整洁的',    # was n. 椅子的背罩
            'sorry': 'adj. 抱歉的',   # 抱歉 was missing
            'customer': 'n. 顾客',    # was n. 消费者
            'implement': 'v. 实施',   # was n. 工具
            'sink': 'v. 下沉',        # was n. 藏垢的场所
        }.items():
            self.assertTrue(self.meaning(word).startswith(start), (word, self.meaning(word)))

    def test_computing_junk_and_domain_tags_are_gone(self):
        for word, junk in {'choice': '批处理', 'cat': '计算机', 'aim': '异步接口', 'sort': '标准输出', 'exit': '命令处理器',
                           'online': '[计]', 'leader': '前导字符', 'handle': '句柄', 'form': '表单', 'stale': '尿', 'mute': '排泄'}.items():
            self.assertNotIn(junk, self.meaning(word), word)

    def test_inflection_notes_read_as_notes(self):
        self.assertIn('（lose 的过去式和过去分词）', self.meaning('lost'))
        self.assertIn('（drink 的过去分词）', self.meaning('drunk'))  # ECDICT: drink的过去式

    def test_look_up_and_brief_meaning_use_the_fix(self):
        self.assertEqual(vs.brief_meaning(nx.lookup('started')['meaning']), 'v. 开始, 启动, 出发')
        self.assertTrue(nx.lookup('hardly')['meaning'].startswith('adv. 几乎不'))


class HeadwordAndPhoneticTests(unittest.TestCase):
    """ECDICT's misspelt headwords fold into the right spelling, ^ reads as ɡ, and -ing words are said with -ing."""

    def test_misspelt_headwords_and_broken_transcriptions(self):
        import vocab_service as vs
        d = nx.dictionary()
        self.assertNotIn('reservior', d); self.assertIn('cet4', d['reservoir']['tags'])  # 四级 has the right spelling
        self.assertIn('reservoir', {w for _, w in vs.book_words()['cet4']})
        self.assertNotIn('saut', d); self.assertIn('sauté', d['saute']['meaning'])
        self.assertFalse([w for w, e in d.items() if '^' in (e.get('phonetic') or '')])
        for w in ('changing', 'buying', 'generating', 'spraying'):
            self.assertIn('ɪŋ', d[w]['phonetic'], w)


class StudyBookAuditTests(unittest.TestCase):
    """tools/audit_meanings.py: no mechanical problem left in the books learners study most."""

    def test_no_artefacts_tags_or_missing_parts_of_speech(self):
        tool = ROOT.parent / 'tools' / 'audit_meanings.py'
        if not tool.exists():
            self.skipTest('tools/ is not part of this checkout')
        sys.path.insert(0, str(tool.parent))
        import audit_meanings
        left = [(w, sorted(c & {'artefact', 'domain-tag', 'no-pos'}), m) for _, w, m, _, c, _ in audit_meanings.audit()
                if c & {'artefact', 'domain-tag', 'no-pos'}]
        self.assertEqual(left, [])


if __name__ == '__main__':
    unittest.main()
