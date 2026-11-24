# 精选材料 · 每周生产流程

内容线从 2026-11 起，每周给每个级别（A2、B1、B2、C1）各加 7 篇精选，每周 28 篇。C1 和 B2 先补（C1 用得最快：每天 45 分钟的学员每天学 2 篇）。

写作规范见同目录的 `SPEC.md`，新材料按 v5.1 写。这份文档只讲每周怎么做。

## 0. 原则

- **AI 辅助编写**：初稿由 AI（Claude）在会话里写，同一个会话自查并改。
  - 材料上标 `"ai": "AI 辅助编写"`；
  - **绝不标「人工审校」**：用户只抽查，不逐篇审，没有人工审校的记录。
- **学习效果第一**：宁可少一篇，不要凑数；同一个话题不同级别也只写一次（校验器会提示标题相近的材料）。
- **事实**：
  - 只写稳定的常识。存疑的句子删掉，不要留着等人查。
  - `references` 只放真的打开核实过的页面，并写核实日期；
  - 名句只用已进入公有领域的，写进 `quotes`。
- **不抄、不改写**任何已有文章、书、歌词和影视台词。写影视文化，谈手法、行业和观众体验，例子用虚构的片子。

## 1. 选题（约 10 分钟）

```bash
python3 tools/corpus_validate.py --gaps
```

- 按级别列出目的、体裁、话题各有多少篇，先补少的。
- 目的 `purposes` 对应学习目的：
  - 新闻评论、影视文化 → 看懂影视新闻
  - 职场 → 工作
  - 校园生活、日常生活 → 留学
  - 说明、议论 → 考试
- 一周 7 篇的大致搭配：
  - 2 篇新闻评论或议论；
  - 1 篇影视文化；
  - 1 篇职场；
  - 1 篇校园；
  - 1 篇说明文；
  - 1 篇故事、对话或邮件。
- 话题 `theme` 照常在 6 个里轮换。
- 每周从 36 个 graded 旧故事里挑 2–3 个，改写成精选，算进这 7 篇：
  - 用新 id，13 句以上，带导读、表达、3–4 道题；
  - 不是把原文扩写一遍，而是用同一个情境重新写一篇。
- 列出本周题目，和已有标题比一遍。

## 2. 写（AI）

- 文件名：`<theme>.<CEFR>.<n>.json`，`n` 接着已有的往下编。**不要改动已经发布的文件里的材料**；要补题见第 6 节。
- 每篇的字段照 `SPEC.md`。v5.1 必须有：
  - `spec: "5.1"`、`ai`、`purposes`；
  - 至少 13 句；
  - 3–4 道题，每道标 `type`，主旨、推断、词义至少各一道；
  - 中文导读 `summary_zh`、英文标题、4–6 个表达、学完任务 `task`。
- 题目选项的正确答案位置要分散，干扰项要合理，不能一眼排除。

## 3. 自动检查（几秒）

```bash
python3 tools/corpus_validate.py flow/corpus_data/v5/<本周的文件>.json
```

- 零错误才能往下走。
- 警告逐条看：词数、平均句长、低频词比例偏离级别时，改用词或补句子；「标题很像」时，确认不是同一个话题，是的话换题。
- 再跑一遍全库校验：`python3 tools/corpus_validate.py`，最后一行应是 `0 个错误`。

## 4. 自查（AI 逐篇通读）

- 读一遍正文：语气自然吗？有没有事实拿不准的句子？有就删。
- 每道题：答案唯一吗？`evidence` 真的支持它吗？
- 听写句（`dictation_index`）长短合适吗？加了句子以后序号有没有错位？

## 5. 录音（约 10 分钟）

只录新篇。4 种声音都用 Kokoro，在本机合成，网站上叫「AI 朗读（自然人声）」。

```bash
uv run --with kokoro-onnx --with soundfile python tools/gen_audio.py flow ~/Flow-media/kokoro-models ~/Flow-media/tts/audio 4 <本周的 id …>
```

- 先备份：`cp ~/Flow-media/tts/audio/index.json ~/Flow-media/tts/audio/index.before-<批次>.json`。
- 生成脚本会重建 `index.json`，盖住所有已录的材料。
- 旧材料（简版：graded-*、graph-* 和最早的分话题短文）用 `--old` 一次录完，`--all` 是全部；id 规则见 `next_service.NARRATION_ID`。
- 在 zsh 里用变量传 id 时，要写成 `${=IDS}`，否则不会按空格拆开。
- 核对每篇 4 个声音的 `.json` 里，句子数和 `sentences(body)` 一样。
- 母本在 `~/Flow-media`，不要放在 /tmp。

**上线**：
- **有 R2 之后**：`python3 tools/push_media.py ~/Flow-media/tts/audio --verify https://media.flowlang.cn`，提交 manifest，发版。
- **R2 之前**：做一个手工包，照第 1 批的 `narration-content1`（在共享笔记 `content-batch1-audio/`），经宝塔放到香港运行。装之前要用户点头。
  - 脚本核对 sha；
  - 文件已存在就拒绝；
  - 先备份 `index.json`，只追加；
  - 在 8090 和 8092 上各检查一个新文件。

## 6. 给已发布的材料补题

线上的库里，材料只写一次（`lab_packs` 是 INSERT OR IGNORE），所以改文件本身到不了线上。

- `content_v50.sync()` 每次启动时，把**只追加**的修改同步进库：
  - 正文、标题、来源、级别都没变；
  - 原来的题一字不改、位置不变，排在最前；
  - 后面可以加题，也可以给题标 `type`，其他字段可以增补。
- 其余修改都不会同步，要换新 id。
- 学习者的作答按题号保存，所以**前 2 道题绝不能动**。
- 补题顺序：C1、B2 → B1 → A2。

## 7. 发出去

1. **改发布清单**：新文件同时加进 `tools/release-files.txt` 和 `flow/upgrade.sh` 的 corpus 列表（`tests/test_release.py` 和 `flow/tests/test_package.py` 会查）。
2. **跑测试**：
   - `cd flow && python3 -m unittest discover -s tests`；
   - 根目录 `python3 -m unittest discover -s tests`；
   - `tools/ui_test.py <out>`。
3. **同步指南**：学习者看得到的变化（比如数量、题型、热点话题）要同步改 `flow/public/guide/guide.md`，并用 `env -u FLOW_PUBLIC_URL python3 tools/build_guide.py` 重建 PDF。
4. **开 PR**：每批一个 PR 进 main，开自动合并。PR 里附**抽查清单**：
   - 4 篇，每级 1 篇；
   - 每篇看正文、导读、题和答案依据，再听 30 秒录音；
   - 用户每周约 30 分钟。
5. **通知**：PR 号告诉语流 1（发内测版）和语流 2（合并、发正式版）。正式版只在用户说「发正式版」后才发。

## 8. 每周花的时间（参考）

| 谁 | 做什么 | 时间 |
|---|---|---|
| AI | 选题、写 28 篇、自查、校验、录音、开 PR | 一个会话 |
| 用户 | 抽查 4 篇 + 听录音，在内测版点开看一眼 | 约 35 分钟 |
| 用户 | 同意装录音包、说「发正式版」 | 两句话 |
