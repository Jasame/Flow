# Flow Corpus v5 · 写作规范

Flow 正式版语料库。每篇是一份完整的学习材料：原创英文正文 + 理解题 + 词汇 + 地道表达 + 语法知识点（挂到知识图谱）+ 输出任务。
读者是中文母语的英语学习者，从入门（A2）到高级（C1）。目标是**让人愿意读完，并且读完真的会用上几个表达**。

## 文件

- 每个文件是一个 JSON 数组，路径 `flow/corpus_data/v5/<theme>.<cefr>.json`，例如 `science.B2.json`；后续批次用 `<theme>.<cefr>.<n>.json`（如 `science.B2.2.json`），不要改动已有文件。
- 写完每个文件立刻运行校验，**零错误才算完成**；警告要逐条看，能改就改：

```bash
python3 tools/corpus_validate.py flow/corpus_data/v5/science.B2.json
```

## 单篇结构

```json
{
  "id": "v5-science-b2-noise-cancelling",
  "title": "降噪耳机为什么能“消音”",
  "title_en": "How Noise-Cancelling Headphones Fight Sound with Sound",
  "summary_zh": "一两句中文概括，告诉读者这篇讲什么、读完能得到什么。",
  "level": "B2",
  "cefr": "B2",
  "theme": "science",
  "genre": "explainer",
  "body": "英文正文……",
  "questions": [
    {"prompt": "…?", "options": ["…", "…", "…", "…"], "answer": 2, "evidence": "正文中原样出现的一句或半句"},
    {"prompt": "…?", "options": ["…", "…", "…", "…"], "answer": 0, "evidence": "…"}
  ],
  "dictation_index": 3,
  "vocabulary": [{"term": "cancel out", "meaning": "抵消", "example": "The two waves cancel out."}],
  "expressions": [{"text": "fight fire with fire", "meaning": "以其人之道还治其人之身", "note": "口语常用，带一点幽默"}],
  "grammar": ["clause-relative", "nonfinite-participle"],
  "knowledge": [{"node": "clause-relative", "quote": "正文中原样出现的句子", "explanation": "一两句中文，讲清这句为什么这样写，读者能直接模仿。"}],
  "speaking": "中文口语任务：具体、能在 1 分钟内完成。",
  "writing": "中文写作任务：具体、给出字数。",
  "task": {"prompt": "中文：仿照/用上……写一两句和你自己有关的话。", "model": "正文中的一句示范句"},
  "tags": ["科技原理", "日常科学"],
  "source": "Flow 编辑部原创"
}
```

### 字段规则（校验器会检查）

| 字段 | 规则 |
|---|---|
| `id` | `v5-<theme>-<cefr 小写>-<英文短 slug>`，全库唯一 |
| `level` | 系统兼容级别：A2 / B1 / B2。**C1 材料填 `"B2"`**，真实难度写在 `cefr` |
| `cefr` | A2 / B1 / B2 / C1，必须与文件名一致 |
| `theme` | campus / travel / life / work / culture / science 之一，与文件名一致 |
| `genre` | article / story / dialogue / explainer / opinion / interview / email / guide 之一 |
| `body` | 一段（不分段），3–30 句，≤ 2600 字符。词数：A2 90–140 · B1 140–210 · B2 210–300 · C1 280–380 |
| `questions` | **恰好 2 道**，各 4 个不重复选项；`evidence` 必须是正文的原样子串。一道考主旨或推断，一道考细节或语境词义；干扰项要合理，不能一眼排除 |
| `dictation_index` | 正文第几句（从 0 数）适合听写：长度适中、有可学的结构 |
| `vocabulary` | 3–5 个，`term` 以相同词形出现在正文，`example` 是新造的句子且包含 `term` |
| `expressions` | 4–6 个**地道搭配/短语**（不是单词），`text` 原样出现在正文；`note` 说明语气或用法 |
| `grammar` / `knowledge` | 1–3 个语法节点，用下面 18 个 id 或 `grammar_more.py` 里的 26 个（共 44 个）；每个 `knowledge.quote` 是正文原样子串，且确实用到该语法 |
| `series`（可选） | 连载：`{"id", "title", "title_en", "blurb", "part", "of"}`。同一 `id` 的各集按 `part` 排序；首页一次只推荐下一集，考试练习不选连载 |
| `task.model` | 正文原样子串，适合仿写 |

### 18 个基础语法节点（知识图谱；另有 26 个见 `flow/grammar_more.py`）

tense-present 一般现在与进行时 · tense-past 过去时与过去进行时 · tense-perfect 完成时与时间线索 ·
clause-relative 定语从句关系词 · clause-noun 名词性从句 · clause-adverb 状语从句 ·
conditional-real 真实条件 · conditional-unless unless 与条件连接 · conditional-modal 条件句中的情态表达 ·
subjunctive-now 与现在事实相反 · subjunctive-past 与过去事实相反 · subjunctive-mixed 错综时间条件 ·
nonfinite-infinitive 不定式与目的 · nonfinite-gerund 动名词与搭配 · nonfinite-participle 分词与主动被动 ·
agreement-head 主语中心词 · agreement-each 不定代词与单数 · agreement-either 就近一致与并列主语

A2 只用前几类（时态、简单从句、真实条件、不定式）；B2/C1 应该覆盖虚拟、分词、错综条件等。

## 内容要求

1. **原创。** 不得复制、改写或拼贴任何已有文章、书籍、歌词、影视台词。
2. **事实可靠。** 不写具体统计数字、年份、价格、研究结论，除非是广为人知且稳定的常识（水在 100°C 沸腾）。不写真实在世人物，不写时事新闻。科学类讲清楚原理，不夸大。
3. **有意思。** 有具体的人、场景、冲突或一个“原来如此”的点。避免教材腔（“Tom is a student. He likes apples.”）。对话体要像真人说话，有省略、有语气词。
4. **难度真实。**
   - A2：高频词、短句（平均 ≤ 12 词），具体日常；
   - B1：常见搭配，长短句结合，少量从句；
   - B2：抽象一点的话题，从句、被动、分词，有观点有论证；
   - C1：高质量媒体/随笔风格，措辞精确、有层次、有让步与转折，多样句式。
5. **对中国学习者有用。** 表达挑真正能迁移到自己生活里的（"push back on a deadline"、"I'm not sure that adds up"），中文释义准确、口语化。
6. **安全。** 不涉及政治、宗教争议、医疗/法律/投资具体建议、暴力、歧视。

## 不要做

- 不要把 `C1` 写进 `level`（用 `cefr`）。
- 不要在 `evidence` / `quote` / `expressions.text` / `task.model` 里改动原文的任何一个字符（包括引号和标点）。
- 不要为凑数写相似的文章；同一主题内 slug 和话题都不能重复。
