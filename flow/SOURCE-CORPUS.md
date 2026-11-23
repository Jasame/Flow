# yl.xlsx 接入机制与数据报告

读取来源：yl.xlsx / Sheet1，表头为词频排序、单词、音标、释义、例句、词性转换、同义转换。

原始20,200行归并为17,634个词形，额外重复来源2,566行全部保留。有例句1,589行，覆盖1,010个归并词形；有词性转换1,382行，有同义转换1,502行。来源哈希、原始字段和行号随每组词形保存于corpus_data/yl-reference.json。该JSON是系统发布数据，不是逐用户学习进度；运行时导入有索引的SQLite表。

发现的异常：5行词形包含数字或斜线，保留检索但暂不允许直接生成或采用。be/to的原表词性可能与常见用法不一致，标记核对。若重复来源的释义不同则展示多个版本，整体11个词形组带结构或特定核对提示；这不表示其他条目已全部校对。缺少例句不伪装成已有语料，不根据词频伪造A2/B1/B2等级。

## 数据流

- reference_terms：来源词形索引；reference_meta：来源与统计；reference_adoptions：当前用户选用的来源行、个人词卡和最近生成语料。
- GET /api/reference：英文前缀、中文释义搜索和有/无例句筛选，固定每页30项；GET /api/reference/entry：原始版本及当前用户采用状态。
- POST /api/reference/adopt：明确选用原表某行某例句；支持少量常见屈折形式检查，原句不改写。原表多义释义仍是来源释义，不宣称已拆为精确词典义项。
- POST /api/reference/generate：沿用lab.run_job、请求ID、缓存与错误重试，向Gemini提供有边界的词条数据作为数据而非指令。正文、目标词汇项和目标例句必须含目标词原形，否则不进入有效生成结果。
- 采用后建立private lexicon和vocab_enroll，接入现有自适应练习、复习、表达反馈及私教检索。词卡保留yl.xlsx行号、原表音标及词形/同义线索。
- 定向生成材料只属于当前用户，沿用完整lab流程与答题前隐藏答案。图谱创建词形—词义—材料—听说读写关系；若只有字面匹配则保留literal-match来源。原表的词形/同义线索保持待核对来源，未直接断言为公共语义关系。
- 新语料仍为AI候选，不绕过quality_service的推荐资格检查。可由用户直接练习，公共自动阶段推荐继续使用已审核/原创材料。

采用事务中词卡、审核日志、入队、来源绑定和连线同成同败。重复采用返回原词卡，生成新语料不覆盖旧词卡、学习状态或历史作品。账号切换清空扩展词库的个人采用缓存，过期异步响应不写回其他账号界面。

## 发布与复现

应用2.4；兼容原2.1核心schema，新增2.4-reference迁移。无新增Python依赖。upgrade.sh安装来源JSON和模块，首次启动幂等建表/导入。备份仍包含整个SQLite数据库，新增表随之备份。

构建脚本tools/build_reference.py只读XLSX的ZIP/XML，不修改表格、不运行公式、不依赖Excel软件。可用原Excel重新生成JSON并比较来源SHA256。上传文件不放入公开静态目录。

本版测试覆盖完整行数/归并、来源版本、分页/注入、屈折例句、私有采用、回滚、目标词生成、重试、继续丰富已有词与图谱关联。浏览器验证检索、采用、词卡来源回溯、图谱跳转和浅/深色；真实Gemini调用留给部署后验收。

发布验证：118项Python测试与11组Node界面测试通过；升级包独立初始化测试通过。

## ECDICT 释义与考试词表

参考词表大多只给一个词性的释义（例如 even 只有"偶数的"）。语流的查词和背单词改用 ECDICT（https://github.com/skywind3000/ECDICT ，MIT 许可，Copyright (c) 2025 Linwei，许可全文见 `corpus_data/ECDICT-LICENSE.txt`）的全部词性释义；音标和词频排名仍以参考词表为准。`tools/build_ecdict_subset.py` 从 ECDICT 的 `ecdict.csv`（提交 39cfb96）提取参考词表中的词和带考试标签（四级、六级、考研、雅思、托福、GRE）的词，写入 `corpus_data/ecdict-flow.json`，考试词书即由这些标签生成。专四、专八没有可用的公开词表，学习者可以自行导入。

中考、高考、学术英语（NAWL 1.2）、商务英语（BSL 1.2）四本词书在 `corpus_data/wordbooks-open.json`，由 `tools/build_open_wordbooks.py` 生成：中考、高考来自 ECDICT 的 `zk`、`gk` 标签（为此 `build_ecdict_subset.py` 也保留这两个标签的词，并用 `--keep` 保留 NAWL、BSL 的词）；NAWL、BSL 由 Browne 等以 CC BY-SA 4.0 许可发布，署名与改动见 `corpus_data/NGSL-LICENSE.txt`，语流改编后的这两本词表同样以 CC BY-SA 4.0 许可发布。来源版本、处理规则和重建命令见 `WORDBOOKS-OPEN.md`。
