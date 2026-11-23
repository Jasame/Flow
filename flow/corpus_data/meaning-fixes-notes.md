# 释义修订记录（meaning-fixes.json）

`meaning-fixes.json` 里的释义是人工逐条写的，覆盖 ECDICT（MIT）给词卡和查词用的释义
（`next_service.build_dictionary()` 最后一步）。改完要运行 `python3 tools/build_dictionary.py` 重建
`dictionary-flow.json`，测试和 `deploy.sh` 都会检查它是否最新。

## 检查命令

```bash
python3 tools/audit_meanings.py                     # 各类问题的数量，按词书分（core mid high cet4 cet6 ky）
python3 tools/audit_meanings.py --without-fixes     # 假设没有 meaning-fixes.json 时的数量（修订前）
python3 tools/audit_meanings.py --list noun-first --book mid   # 列出被标记的词，词频高的在前
python3 tools/audit_meanings.py --min-rank 0        # 连最常用的 150 个词也算上（基础词书默认跳过它们）
```

检查项是启发式的，只用来找候选词，最后都要人看：`artefact`（\r、反斜杠、方括号、`vt.vi.` 这类残留）、
`domain-tag`（[计] [医] 等领域标签）、`letter-abbr`（字母、缩写义排在前面）、`tech-sense`（混进日常词的计算机术语，
如 handle 的「句柄」）、`no-pos`（某一行没有词性，卡片上每个「；」单独成行）、`noun-first`（参考词表认为主要词性不是名词，
却把名词排在第一；人工审过的词不再计入）、`rare-first`（首义带〔古〕〔俚〕等标记）、`long`（超过 90 字或一个词性下超过 8 个义项）、
`duplicate`（同一行义项重复、同一词性出现两次）、`no-phonetic`（没有音标）。

## 2026-11 这一轮

先审学习者真正在背的六本词书（core、mid、high、cet4、cet6、ky，按词频从高到低），新增 1528 条（原有 84 条未改动，共 1612 条）：

- 基础词书（rank 150–2000）逐词看了一遍，改了 881 条；最常用的 150 个词（查词时最常碰到）改了 49 条；
  进阶词书 306 条、高阶和只在四六级、考研词书里的词 281 条，只修被标记且确实误导的；
  另有 11 条是做专四、专八词表时发现的（browser 只有「吃嫩叶的动物」、prom、pence 等），不在这六本词书里。
- 主要问题和改法：
  - 词性顺序：ECDICT 习惯把名词放第一，start 首先显示「n. 惊起」、keep「n. 生计」、can「vt. 装罐」。改为最常用的词性在前。
  - 罕见或错误的首义：natural「n. 白痴」、mere「n. 小湖」、tidy「n. 椅子的背罩」、stale「n. 尿」、kill「小河」、
    must「未发酵葡萄汁」、hardly「刚刚」、customer 只有「消费者」、sorry 没有「抱歉」。
  - 混进来的 DOS 命令说明和计算机术语：choice、sort、copy、find、exit、cat、aim 后面整句的命令说明，
    handle「句柄」、form「表单」、break「分隔符」、leader「前导字符」、register「寄存器」。
  - 残留：[计] 等领域标签、`vt.vi.`、`n.荒野` 缺空格、「pass的过去分词」这种没词性的行。
  - 太长：turn、cut、play 等一个词性下十几个义项，压到 3–7 个日常义项。
- 写法（和原有 84 条一致）：`词性. 义项, 义项；词性. 义项`；词性用 n. v. adj. adv. prep. conj. pron. aux. int. num. art. abbr.，
  及物与不及物合并写 v.；搭配和说明放全角括号里（「（be able to）」「（读 /led/）」）；词形说明单独一行
  「（lose 的过去式和过去分词）」；不用半角分号（前端遇到 ; 也会换行）。只参考 ECDICT（MIT）和常识自行撰写，
  没有抄任何商业词典或词典 App。

修订前后（rank > 150 的 8354 个词，修订前包含原有 84 条）：

| 问题 | 全部 | core | mid | high | cet4 | cet6 | ky |
|---|---|---|---|---|---|---|---|
| 被标记的词 | 1119 → 262 | 304 → 18 | 367 → 66 | 249 → 80 | 631 → 132 | 785 → 198 | 769 → 183 |
| artefact | 16 → 0 | 1 → 0 | 1 → 0 | 8 → 0 | 3 → 0 | 8 → 0 | 2 → 0 |
| domain-tag | 9 → 0 | 1 → 0 | 1 → 0 | 7 → 0 | 2 → 0 | 2 → 0 | 1 → 0 |
| tech-sense | 16 → 0 | 10 → 0 | 4 → 0 | 2 → 0 | 9 → 0 | 10 → 0 | 10 → 0 |
| no-pos | 76 → 0 | 13 → 0 | 20 → 0 | 32 → 0 | 15 → 0 | 21 → 0 | 17 → 0 |
| long | 142 → 0 | 67 → 0 | 41 → 0 | 20 → 0 | 80 → 0 | 89 → 0 | 79 → 0 |
| duplicate | 35 → 1 | 19 → 0 | 7 → 0 | 7 → 1 | 21 → 0 | 26 → 1 | 27 → 1 |
| noun-first | 896 → 247 | 236 → 18 | 308 → 64 | 188 → 78 | 538 → 126 | 672 → 190 | 677 → 181 |

## 还没做的

- `noun-first` 剩 247 个：多数是名词本来就常用、排第一也合理的词（delay、sigh、chat、fax），
  以及低频的高阶和六级、考研词；值得以后再看一遍高阶词书。
- `no-phonetic` 11 个（theatre、firework、cosy、waggon 等英式拼写或 ECDICT 拼错的词，如 reservior）：
  meaning-fixes.json 只管释义，补音标需要给 `build_dictionary()` 加一个字段，这一轮没动代码。
- `letter-abbr` 剩 3 个是正确的（alpha 本来就是希腊字母，ie 是 i.e.，etc）；`duplicate` 剩的是原有条目 commute 的「v. 减刑」，保留。
- adv（精通）、ext（拓展）、ielts、toefl、gre 词书没有审。
- 首字母大写的词条：supreme、polish、internet、congress 在词典里存成 Supreme、Polish、Internet、Congress，
  `book_words()` 跳过大写词条，所以这几个四级词不在任何词书里。释义已经修了（查词能用上），
  词条大小写要在重建 ECDICT 子集时改。
