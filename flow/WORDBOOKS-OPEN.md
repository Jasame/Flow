# 开放许可词书：中考、高考、学术英语、商务英语

`corpus_data/wordbooks-open.json` 收了四本词书，词表都来自公开许可的数据，由 `tools/build_open_wordbooks.py` 生成。

| id | 书名 | 分组 | 来源 | 许可 | 顺序 | 词数 |
|---|---|---|---|---|---|---|
| `zk` | 中考词汇 | 中学英语 | ECDICT 标签 `zk` | MIT | 词频 | 1580 |
| `gk` | 高考词汇 | 中学英语 | ECDICT 标签 `gk`，加上 `zk` 的词 | MIT | 词频 | 3647 |
| `nawl` | 学术英语 | 学术与职场 | New Academic Word List 1.2 | CC BY-SA 4.0 | 词频 | 946 |
| `bsl` | 商务英语 | 学术与职场 | Business Service List 1.2 | CC BY-SA 4.0 | 原表排名 | 1721 |

## 文件格式

```json
{"notice": "来源与许可",
 "books": {"zk": {"title": "中考词汇", "group": "中学英语", "blurb": "一句话简介", "basis": "来源与许可（中文，1–2 句）",
                  "words": ["the", "be", "..."]}, "...": {}}}
```

`words` 是小写词形（norm），按学习顺序排列，不重复。每个词都在 `next_service.dictionary()` 里，有中文释义，
而且通过 `vocab_service.book_words()` 的同一套筛选：只含字母和连字符、至少两个字母、词典词头不是大写开头。
“词频”指词典里的 `rank`，和考试词书排序用的是同一个值。

## 来源、版本与许可

**ECDICT**（https://github.com/skywind3000/ECDICT ），MIT 许可，Copyright (c) 2025 Linwei，全文见
`corpus_data/ECDICT-LICENSE.txt`。用的是提交 `39cfb9672c0906b63569e0453c2e6abfb9ab182a`（2026-11-02，即
`SOURCE-CORPUS.md` 里的 39cfb96）的文件：

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `ecdict.csv` | 66,009,548 字节 | `d1ecbdf9ee2b920afb6f430ca6b6bb9f559588cf0dff86e04bd255f9390843cc` |
| `wordroot.txt` | 370,702 字节 | `4b400dc5980e4a362fa12c7a49b326bb621c4e6bebd5f37146fbdcbe9db6bb6e` |

`ecdict.csv` 的 `tag` 列里，`zk` 是中考（1603 个词条），`gk` 是高考（3677 个）。

**NGSL Project**（https://www.newgeneralservicelist.com/ ，Dr. Charles Browne 等），两张表都以
Creative Commons Attribution-ShareAlike 4.0 International（CC BY-SA 4.0，https://creativecommons.org/licenses/by-sa/4.0/ ）
许可发布。网站上的原话：

- “New Academic Word List by Browne, C., Culligan, B., and Phillips, J. is licensed under a Creative Commons Attribution-ShareAlike 4.0 International License.”
- “Business Service List by Browne, C. and Culligan, B., is licensed under a Creative Commons Attribution-ShareAlike 4.0 International License.”

| 文件（网站上的名称） | 大小 | SHA-256 | 用途 |
|---|---|---|---|
| `NAWL_1.2_alphabetized_description.txt`（NAWL 1.2 alphabetized，957 词） | 10,340 字节 | `88a99099e10010ea40992cca4a5119102d05a0f2888ee5d43d4c8b4afd597fef` | 学术英语的词表 |
| `NAWL_1.2_lemmatized_for_teaching.csv` | 23,608 字节 | `1790b0fa22c5815ebf5a9a15c9363c03a6e906c77bf217f99033734f1459137b` | 词典补词（`--keep`） |
| `BSL_1.20_stats.csv`（BSL 1.2 list with basic statistics，1744 词） | 59,643 字节 | `45055265eb4e74c65f5d26edabbc1a0da38c45bbb924cd9bd01fd391b74ff157` | 商务英语的词表和排名 |
| `BSL_1.20_lemmatized_for_teaching.csv` | 43,830 字节 | `0073a91b4186dc0bba0960f2ed9486bd117177403f4e0ac9f3738474f2b2a3c9` | 词典补词（`--keep`） |

下载页：https://www.newgeneralservicelist.com/new-academic-word-list 和
https://www.newgeneralservicelist.com/business-service-list （2026-11-24 下载；文件 2023 年 4 月上传）。

**CC BY-SA 的要求**：署名（作者、表名、许可链接、注明改动）和相同方式共享。`corpus_data/NGSL-LICENSE.txt`
写了署名、许可链接和语流做的改动；改编后的学术英语、商务英语词表（`nawl`、`bsl` 两本）同样以 CC BY-SA 4.0
许可发布。JSON 的 `notice` 和每本书的 `basis` 也写明了来源和许可。词书显示的中文释义来自 ECDICT，不来自 NGSL。
NAWL/BSL 只决定“收哪些词”；`ecdict-flow.json` 和 `dictionary-flow.json` 里只有 ECDICT 的词条。

## 处理规则

- 中考：ECDICT 里带 `zk` 标签的词。高考：带 `gk` 标签的词，加上带 `zk` 的词（ECDICT 的 `gk` 漏了 49 个中考词，
  如 body、energy、warn、exam；高考要求本来包含初中词汇）。
- 学术英语：NAWL 1.2 的 957 个词头。NAWL 官方文件是按字母排的（排名只在另一个网站的统计表里），所以按词频排。
- 商务英语：BSL 1.2 的 1744 个词头，按表里的 `BSL Rank` 排（第 1 名是 mister，这是原表的结果）。
- 词形先转小写；少数词形在语流词典里没有单独词条（词典把复数、-ed/-ing/-er 形式并到原形），按释义逐个核对后
  对应到合适的词条（`ALIASES`，如 socks → sock、onwards → onward、headquarter → headquarters、
  unauthorize → unauthorized、organiser → organizer、drier → dryer）。原形意思不同的（goods/good、means/mean、
  latest/late、chips/chip、shaver/shave）不对应，直接不收。
- NAWL 自己标为前缀的 anti、ex、micro、multi、neo、non、pre、semi、sub、trans 不收（BSL 里也有其中九个）。
- 其余查不到合适词条的词不收，见下表。

## 没有收录的词

| 书 | 列表词数 | 收录 | 未收录 | 原因 |
|---|---|---|---|---|
| 中考 | 1603 | 1580 | 23 | 词典词头大写或词典里没有的专名缩写 17（American、Chinese、English、Christmas、TV、T-shirt、Canada、February 等）；不是单个词 5（a、I、ice cream、Mr.、Ms.）；没有词条 1（vcd） |
| 高考 | 3726 | 3647 | 71 | 专名缩写 54（同上，加上国名、民族、宗教、节日和 Antarctic）；不是单个词 7（a、F、I、ice cream、Mr.、Ms.、no.）；没有词条 10（are、does、goods、means、latest、chips、sharpener、shaver、cance、vcd） |
| 学术英语 | 957 | 946 | 11 | 前缀 10；没有词条 1（goods） |
| 商务英语 | 1744 | 1721 | 23 | 前缀 9；没有词条 14（goods、amortization、deliverable、macroeconomics、maximization、tranche、annualize、capita、graphics、prepayment、pensioner、reinvestment、annum、flotation） |

还能补回来的：goods、means、latest、chips、shaver、sharpener、pensioner、graphics 在 `ecdict-flow.json` 里有词条，
但 `next_service.build_dictionary()` 把它们当成 good、mean 等的变形跳过了；amortization、tranche 等在 ECDICT 里只有
`[经]` 这类专业释义，`_ec_meaning()` 会去掉。这两处改了词典以后，重跑本页的命令就会收进来。

另外，ECDICT 只以大写形式收录的一些专名（London、China、Monday、January 等）在语流词典里是小写词头，
所以通过筛选进了中考、高考词书（中考 28 个、高考 39 个），雅思等考试词书里本来也有；显示时是小写。

## 小写词头

参考词表把一些常用词写成大写（Supreme、Congress、Internet、Polish），`book_words()` 因此把它们挡在所有词书外。
`build_ecdict_subset.py` 在 `ecdict-flow.json` 里写一个 `lower` 列表，`next_service.build_dictionary()` 对列表里的词用小写词头。
入选条件：ECDICT 给这个词的词条本身是小写，并且带考试标签或 Oxford 3000 标记（语流显示的正是这条的释义）；
或者在人工核对过的 `COMMON` 里（ECDICT 只有大写的 Polish 一条，但它也收了 polish“擦亮”）。专名不变：ECDICT 里
专名的小写重复条目（vietnamese、saudi）没有标签，缩写（PhD、CEO）不止一个大写字母，`KEEP_CAPITAL` 里是有标签但实际
写成大写的 Antarctic、Bible。

改成小写的 13 个：arctic、catholic、congress、democrat、internet、madame、philharmonic、polish、republican、senate、
supreme、thanksgiving、united。词典里只有这 13 个词的 `word` 变了，释义等其他字段不变；它们因此进了频率词书
（core +8、mid +1、high +3、ext +1）和考试词书（四级 +6、六级 +8、考研 +10、雅思 +7、托福 +7、GRE +4），其余词不变。

## 词典扩充

`tools/build_ecdict_subset.py` 现在多保留两种词：带 `zk`、`gk` 标签的词，和 `--keep` 词表里的词头（这里传入 NAWL、BSL
的 lemmatized for teaching 文件）。原有词条一个不少、内容不变（只是 `tags` 里多了 zk/gk，另加上面的 `lower` 列表）；新加的词如果 ECDICT
只有大写词头（Canada、February），仍然不收，和以前一样。

| 文件 | 之前 | 之后 |
|---|---|---|
| `ecdict-flow.json` | 21,401 词，2,314,210 字节 | 21,551 词（+150），2,353,226 字节 |
| `dictionary-flow.json` | 20,954 词，2,409,825 字节 | 21,067 词（+113），2,445,309 字节 |
| `wordroots-flow.json` | 4,127 词，337,547 字节 | 4,140 词（+13），338,465 字节 |

新加的 150 个 ECDICT 词条里，19 个是已有词的变形（socks、scores、shaver……），`build_dictionary()` 照旧把它们并到原形；
18 个在 ECDICT 里只有 `[经]`、`[网络]` 这类释义（amortization、tranche……），`_ec_meaning()` 去掉后为空。所以词典多
113 个词（true、dollar、colour、favourite、dumpling、debit、deflation、receivable、lessee、yuan……）。
频率词书和考试词书（四级到 GRE）逐词核对过：新增的词条没有改变它们，变化只来自上面 13 个小写词头。

## 重建

下载的文件放在仓库外的空目录里，当数据读，不运行其中任何东西；Python 用 `-I`。

```bash
E=<ECDICT 目录>; N=<NGSL 目录>
python3 -I tools/build_ecdict_subset.py "$E/ecdict.csv" flow "$E/wordroot.txt" \
    --keep "$N/NAWL_1.2_lemmatized_for_teaching.csv" --keep "$N/BSL_1.20_lemmatized_for_teaching.csv"
python3 tools/build_dictionary.py
python3 -I tools/build_open_wordbooks.py "$E/ecdict.csv" "$N/NAWL_1.2_alphabetized_description.txt" "$N/BSL_1.20_stats.csv"
(cd flow && python3 -m unittest tests.test_wordbooks_open tests.test_next -v)
```

`build_open_wordbooks.py` 只用标准库，同样的输入得到同样的字节，并打印每本书没收的词和原因。改了
`meaning-fixes.json` 或词典其他来源以后，先跑 `build_dictionary.py`，再跑这一步，确认词数没有意外变化。
测试 `tests/test_wordbooks_open.py` 检查格式、不重复、每个词都在词典里有中文释义、学习顺序、许可说明，以及文件
已列入 `tools/release-files.txt` 和 `upgrade.sh`。
