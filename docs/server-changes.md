# Flow 服务器和配置的变动

发布（tag）以外，对服务器、设置文件、AI 网关、GitHub 仓库设置做的改动都记在这里。发布本身在 [releases.md](releases.md)。

规矩：

- **不写任何密钥、密码、邮箱地址、IP。** 只写改了哪个文件的哪一项、为什么、谁做的、备份在哪、怎么撤回。
- 服务器按地区叫：**香港**（Flow 两个站、AI 网关）、**杭州**（xmc.hk 后台、jasa.hk 等）。
- 时间是北京时间。备份和日志默认在香港的 `/root/claude-ops/`。
- 每次动服务器以前先备份；改完要从服务本身验证（真的发一次请求，或者看那个进程的环境和挂载），只从外面看不算。
- **`/etc/flow.env`、`/etc/flow-beta.env` 只按行撤回**（语流 2 定的）：这两个文件好几个会话一起改。撤回一律写成
  「删除或改回 XXX 那一行，然后重启 flow-beta / flow」，不要把整份备份拷回去，否则会冲掉别人后来的改动。
  下面写的「备份」是改之前的那一份，只用来对照。nginx 配置也一样：只改回那一项。
- 证书、宝塔、杭州面板和其他项目的维护记在杭州的 ops-log.md，这里只记跟 Flow 有关的。
- 以后每改一次就在最上面加一条。

两个站的设置文件：语流（flowlang.cn）是 `/etc/flow.env` 和 `flow.service`；内测版（flow.jasa.hk）是 `/etc/flow-beta.env` 和
`flow-beta.service`。两个站读同一个声音目录 `/www/wwwroot/flow/audio`。

## 还没做完、在等的

| 事情 | 现在 | 等什么 |
| --- | --- | --- |
| Gemini 中转站并发从 2 改成 6（#68） | 代码已合（11-24 22:49），中转站上还是 2 | 用户在 Google Cloud Shell 里执行 `flow-gateway/set_slots.sh 6`（步骤在 #68 和 flow-gateway 的说明里）。上线后语流 12 对比前后的 503/504 和等待时间 |
| 语流的发音（说一句）恢复 | 13:05 停用 Gemini 以后，语流的发音先暂停（回 403）；内测版已改走 Omni；对话、复述、雅思口语、跟读两个站都走 Qwen-Omni | 今晚换成百炼语音识别（`flow-audio-asr-flash`），随 #175 和 21:00 的正式版一起上，到时问用户；页面上的提示也要跟着改 |
| 数据库副本只留 14 天（#58） | r27 已带上正式版；内测版只列不删 | 语流上最早的副本是 11-23 的，约 12-07 起开始真正删除（语流 2 记着） |
| 发信的后续 | 两个站 11-25 都已改用 flowlang.cn 发信 | DMARC 从 p=none 改成 quarantine（报告干净一段时间后，先问用户）；隐私说明要不要写明发信服务商（用户待定）；网易邮箱和 iCloud 的「重发走备用」还没实测 |
| 上传用过的整包 `/root/claude-ops/flow-audio-packs.tar`（112 MB） | 还在，内容已装好 | 可以删，删以前问一下 |
| 杭州 ops-log 补一条：jasa.hk 介绍页换视频 | 内容写好了，在 `flow-promo/site2/OPS-LOG-ENTRY.md` | 用户自己补（会话建 root 任务被权限检查拦了） |
| 例句还差 89 个词；偏敏感的例句要复核 | 两次补全写进 16,308 条，抽查 41 条里 1 条偏敏感 | 语流 11：#114（不嘲笑、不带刻板印象的复核）合进去以后一起补，花费不到 ¥0.5 |

## 2026-11-25

### 13:10 · AI 网关：给 #175 加两个模型名

- **改了什么**：网关数据库的 models 表加了两个名字，都加进了 flow 这把钥匙的允许列表：
  - `flow-text-qwen-plus` → aliyun 上游的 qwen-plus；
  - `flow-audio-asr-flash` → aliyun 上游的 qwen3-asr-flash。
  
  这两个名字是给 #175（备用改成 qwen-plus、发音换百炼语音识别）准备的，还没有哪个站在用。
- **谁、为什么**：语流 12。用户在选项卡上选了「可以（推荐）」。
- **备份**：`/root/claude-ops/api.sqlite3.before-aliases-20261125-131036`（数据库里有 key，root 600，不外传）。
- **撤回**：`DELETE FROM models WHERE alias IN ('flow-text-qwen-plus','flow-audio-asr-flash');`，再从 flow 钥匙的允许列表里去掉这两个名字。

### 13:05 · 两个站：学员请求不再走 Gemini

- **为什么**：合规。用户在语流 1 选了「换成国内已备案模型（推荐）」。语流 23 的结论是：Gemini 在国内没有生成式 AI 备案，
  学员录音发过去又算个人信息出境。Gemini 只留给内部开发和评测。
- **改了什么**：在香港的 AI 网关里。网关数据库是 `/www/xmc-api/data/api.sqlite3`，每次请求都现读，所以不用重启 xmc-api。改了三处：
  - tokens 表里 name='flow' 这把钥匙（两个站共用）的 allowed_models，从不限改成只列 `flow-*` 的模型名
    （flow-audio-*、flow-batch-*、flow-eval-*、flow-search-*、flow-text、flow-text-ds-flash、flow-text-qwen-plus、flow-tts）。
    这样语流再要 `gemini-3.8-flash` 就回 403。别的钥匙不受影响。
  - model_fallbacks 表：`flow-text-ds-flash` → gemini-flow 这条备用线路关了（enabled=0）。
  - models 表：`flow-text` 原来指 gemini-flow 上的 gemini-3.8-flash，改指 aliyun 上的 deepseek-v4.1-flash。两个站的
    `FLOW_TEXT_AI_MODEL=flow-text` 不用改。
  - 内测版：`/etc/flow-beta.env` 第 50 行 `FLOW_AUDIO_ROUTES` 末尾加 `,next-say=flow-audio-omni-flash`，重启 flow-beta，
    确认运行中的进程已经用上，所以内测版的发音改走 Omni。
  - 语流的设置文件没动。语流的发音（next-say）走的是 Gemini，所以现在回 403，等于暂停；页面上的提示还是 r28、r30 的旧说法。
  - 热点检索这次没改：它走主模型 Gemini 加搜索，所以跟着一起停了。热点本身已经由 #171 暂停。
- **谁**：语流 12，用户在语流 12 的选项卡里同意。问的是「现在就停掉学员那边的 Gemini……发音打分怎么办？」，
  用户选了「内测版改 Omni，正式版暂停（推荐）」。
- **核对**：主模型 Gemini 回 403；`flow-text` 由 deepseek-v4.1-flash 回答。正式版 r30 的完整自检里，发音两项和一次语音对话的转写
  回了 403（见 releases.md 的 r30），和预想的一样。
- **备份**（香港，root 600，数据库里有 key，不外传）：`/root/claude-ops/api.sqlite3.before-nogemini-20261125-130550`，
  `/root/claude-ops/flow-beta.env.bak-say-20261125-130550`；日志 `/root/claude-ops/nogemini-20261125.log`。
  网关说明书第 6.5 节和变更记录都同步了，运维记录 13:24 写过。
- **撤回**：撤回会让学员重新用上 Gemini，和合规决定相反，要用户点头才做。在香港对网关数据库用 sqlite3 执行：
  - `UPDATE tokens SET allowed_models='null' WHERE name='flow';`
  - `UPDATE model_fallbacks SET enabled=1 WHERE alias='flow-text-ds-flash' AND upstream_id=(SELECT id FROM upstreams WHERE name='gemini-flow');`
  - `UPDATE models SET upstream_id=(SELECT id FROM upstreams WHERE name='gemini-flow'), target='gemini-3.8-flash' WHERE alias='flow-text';`
  - 内测版：`sed -i '/^FLOW_AUDIO_ROUTES=/ s/,next-say=flow-audio-omni-flash//' /etc/flow-beta.env && systemctl restart flow-beta`
    （只动这一行）。

### 10:27 · AI 网关：不再为已经离开的调用方试备用线路

- **改了什么**：xmc-api 的 `control_plane.py`（patch_nobackup）：调用方已经断开的请求，不再去试备用线路。
  起因是内测版 b30 自检里「导入补题」失败：10:00:36 那次 next-enrich 发给百炼 DeepSeek，600 秒没回。Flow 85 秒就放弃了，
  网关等满 600 秒以后又去问备用的 Gemini，答案没人收。Flow 这边同时有 #130（文字请求 45 秒没回就换）。
- **谁**：语流 12。用户：「测好就装」。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-nobackup-20261125-102756`。
- **撤回**：把这份备份换回去，重启 xmc-api。前提是之后没人再改过这个文件，换之前先对一下。

### 10:20 · AI 网关：客户端断开后放掉位子

- **改了什么**：xmc-api 的 `control_plane.py`（patch_disconnect）：客户端已经断开，或者流交出去 30 秒还没开始，网关就放掉它占的
  并发位子，并照常记账（记成 499）。起因同上（b30 的导入补题）。上游读超时还是 600 秒，以后再定。
- **谁**：语流 12。用户：「测好就装」。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-disconnect-20261125-102016`。
- **撤回**：把这份备份换回去，重启 xmc-api。它在 10:27 那次之前，要撤就两次一起按顺序撤。

### 09:46 · 杭州：jasa.hk 的 Flow 介绍页换成「一分钟看懂语流」

- **改了什么**：09:45:58–09:46:04 通过杭州的宝塔面板，换了 jasa.hk 五个 `/projects/flow/` 页面的视频块：
  - 中文标题「一分钟看懂语流」，另外四种语言是「Flow in about a minute」，配 13 句英文旁白；
  - 新文件 `flow-film-h.mp4`、`flow-film-v.mp4` 和两张封面（`?v=20261125`），旧的 flow-45 文件没动。
  
  09:46:34 清了全站缓存。jasa.hk 在杭州服务器上，不是 Flow 的两个站。
- **谁**：语流 17（宣传资料）。
- **对外**：更新日志 `2026-11-25-flow-film-2` 走 jasa.hk 后台的「草稿 → 发布」，用户看过全文，回答「就这样」。
- **备份**：杭州 `/www/backup/jasa-flow-film2-20261125/`。
- **撤回**：把备份换回去，再清一次缓存。
- **没做完**：杭州 ops-log 的详细条目没写进去。要建一次性 root 任务，被语流 17 的权限检查拦下了；内容在
  `flow-promo/site2/OPS-LOG-ENTRY.md`，等用户自己补（见上表）。

### 08:47 · 语流：朗读改成 22050 采样率

- **改了什么**：`/etc/flow.env` 第 49 行加 `FLOW_TTS_SAMPLE_RATE=22050`，然后重启 flow。
- **谁、为什么**：语流 2。内测版 08:15 起已经是 22050，文件小约 20%，速度不变。用户听了两个试听链接，说「听不出，改」。
- **备份**：`/root/claude-ops/flow.env.bak-ttsrate-20261125-084700`（只用来对照）。
- **核对**：进程读到的是 22050；用服务自己的环境合成了一句（0.95 秒，43.6 KB），外网取得到（200）。
  第 39–42 行（朗读、Omni）和发信备用那几行都没动。
- **影响**：昨晚按 24000 预生成的那批不再用了，要按 22050 重新生成一次，约 ¥1.5。
- **撤回**：删除 `FLOW_TTS_SAMPLE_RATE` 那一行，然后重启 flow：
  `sed -i '/^FLOW_TTS_SAMPLE_RATE=/d' /etc/flow.env && systemctl restart flow`。

### 08:35 · 香港：告警邮件脚本跟着换发信

- **改了什么**：`/usr/local/sbin/xmc-hz-watch`（香港，杭州出问题时给用户发告警）：
  - 按 UTF-8 读配置；
  - EHLO 报 flowlang.cn；
  - 告警先走飞书（`FLOW_SMTP_FALLBACK_*`），失败再走阿里云。告警是发给用户自己的，所以先走用户自己的邮箱。
  
  `--check` 两条通道都能登录。
- **谁**：语流 16，用户同意（08:32，告警优先走飞书）。
- **备份**：`/root/claude-ops/xmc-hz-watch.bak-20261125-mail`。这个脚本只有这一个改动来源，可以整份拷回去再跑 `--check`。
- **要记住**：杭州 `/www/xmc-status/ops` 里的镜像比香港在用的旧，归语流 2 同步。

### 08:34 · 两个站：内容线第 2 批的朗读包

- **改了什么**：装 narration-content2，224 个文件，`audio/index.json` 294 条（原来 266）。两个站读同一个声音目录，装一次两个站都有：
  语流（8090）和内测版（8092）取文件都回 206。
- **谁、为什么**：语流 2。用户：「装」。包是语流 14 做的，经本机中转、用 Chrome 里的宝塔面板分块传上香港，4 个文件的 sha 都核对过。
- **备份**：`/root/claude-ops/backup-narration-content2-20261125-083434`。
- **撤回**：用 `/root/claude-ops/narration-content2.log` 末尾的撤销命令。

### 08:33 · 语流：系统邮件改用 flowlang.cn 发（阿里云邮件推送）

- **改了什么**：`/etc/flow.env` 按键改行：`FLOW_SMTP_*` 改成阿里云邮件推送（465 端口），发件人「语流 Flow」（mail.flowlang.cn
  子域名，不收回信）；另加 `FLOW_SMTP_FALLBACK_*` 指向原来的飞书邮箱，作备用；然后重启 flow。08:33:47 起生效。
  发信规则是 r28 带上的 #93 和 #85：
  - 所有邮件先走阿里云，当场发不出去就换飞书再发一次；
  - 验证码类邮件 10 分钟内重发时，那一封先走飞书；
  - 每周进度和背词提醒不先走飞书；
  - EHLO 报站点域名。
- **谁、为什么**：语流 16。内测版从 00:37 起先用了一晚上。用户 08:32 同意切正式版（SMTP 密码用脚本从内测版配置复制，没人经手）。
- **备份**：`/root/claude-ops/flow.env.bak-20261125-mail`（只用来对照）。
- **核对**：08:34 往 Gmail 发了一封，进了收件箱，SPF、DKIM、DMARC 都 pass，邮件里是新版式，`Received: from flowlang.cn`。
- **撤回**：`python3 /root/claude-ops/mail-sender-undo-prod.py --dry-run` 看要改哪几行，确认后去掉 `--dry-run` 再跑，然后重启 flow。
  它只把 `FLOW_SMTP_HOST/PORT/USER/PASSWORD/FROM` 改回旧值，删掉 `FLOW_SMTP_FALLBACK_*`，别的行不碰。

### 08:3x · 语流：每日 AI 预算定成 ¥5（后台设置）

- **改了什么**：xmc.hk/flow 的 AI 页，每日预算从 ¥6 改成 ¥5，只改了每日那一项。
- **谁、为什么**：语流 1，用后台的接口改的。补例句那天临时调到 ¥6，补完以后定下来。用户：「定成 5 元」。
  当天已经花了 ¥6.10，超过 ¥5，所以批量任务当天不再跑，第二天照常。
- **撤回**：同一页改回原来的数。预算经过：01:54 设成 ¥3（语流 2）→ 08:1x 临时 ¥6 → 08:3x ¥5。

### 08:30 · 内测版：去掉手工加的写权限 drop-in

- **改了什么**：`/etc/systemd/system/flow-beta.service.d/70-tts-write.conf` 移到
  `/root/claude-ops/backup-flow-beta-dropin-20261125-083059/`（不是直接删），`daemon-reload`，重启 flow-beta。
  部署自己装的 `61-flow-tts.conf` 还在（`ReadWritePaths=-/www/wwwroot/flow/audio/tts`），所以这一份是多余的。
- **谁**：语流 2。用户：「删」。
- **核对**：沙箱里写得进去；用服务自己的环境真的合成了一句（47 个字，1.1 秒，40 KB），外网取得到（200）。
- **撤回**：把文件 mv 回 `flow-beta.service.d/`，`daemon-reload`，重启 flow-beta。

### 08:25 · 语流：跟读也改走 Qwen-Omni

- **改了什么**：`/etc/flow.env` 第 41 行 `FLOW_AUDIO_ROUTES` 的末尾加上 `,next-shadow=flow-audio-omni-flash`，然后重启 flow。
- **谁、为什么**：语流 2。用户：「切，先内测版再正式版」，内测版 08:22 先切过、先测过。
- **备份**：`/root/claude-ops/flow.env.bak-shadow-20261125-082524`（只用来对照）。
- **核对**：完整 e2e 154 项过 153，跟读 3.6 秒，走的是 Omni。没过的一项是一次语音对话 Omni 没给出「听到了什么」，偶发，已转给语流 12。
- **撤回**：只把跟读改回去：`sed -i '/^FLOW_AUDIO_ROUTES=/ s/,next-shadow=flow-audio-omni-flash$//' /etc/flow.env`，然后重启 flow。
- **打分抽查**（语流 9，在内测版用临时学员，测完清理了）：同一句读成 4 种，每种 2 次，8 次都由 qwen3.8-omni-flash 回答，每次 3.5–7.9 秒。
  - 读对：85、92 分；
  - 读错 3 个词：78、75 分；
  - 漏读：76、75 分；
  - 只读一半：72 分。
  
  转写逐字正确，读得差的比读对的低 10–20 分；同一段录音打两次分会差几分。有 4 次把 noise-cancelling 里连字符的差别
  当成了问题，#116 改提示词修这个。结论：跟读留在 Omni。

### 08:22 · 内测版：跟读也改走 Qwen-Omni

- **改了什么**：`/etc/flow-beta.env` 第 50 行 `FLOW_AUDIO_ROUTES` 加上 `next-shadow`，然后重启 flow-beta。
- **谁、为什么**：语流 2。用户：「切，先内测版再正式版」。
- **备份**：`/root/claude-ops/flow-beta.env.bak-shadow-20261125-082249`（只用来对照）。核对：153/153。
- **撤回**：把 `FLOW_AUDIO_ROUTES` 那一行末尾的 `,next-shadow=…` 删掉，然后重启 flow-beta。

### 08:20 · 语流：对话、复述、雅思口语的录音改走 Qwen-Omni，超时 40 秒

- **改了什么**：在 `/etc/flow.env` 末尾加两行，然后重启 flow：
  - 第 41 行 `FLOW_AUDIO_ROUTES=next-dialog=flow-audio-omni-flash,next-retell=flow-audio-omni-flash,next-ielts=flow-audio-omni-flash`；
  - 第 42 行 `FLOW_AUDIO_TIMEOUT=40`（录音交给 AI 时最多等 40 秒）。
- **谁、为什么**：语流 2，跟 r28 一起。#88 的开关，Gemini 中转站在录音上常常要等很久，甚至 504。
  用户：「发，并开 Omni」「改成 40 秒」。
- **备份**：`/root/claude-ops/flow.env.bak-omni-20261125-082038`（只用来对照）。
- **核对**：完整 e2e 154/154；对话 3.0 秒、复述 12.7 秒，走的是 Omni。发音（说一句，next-say）照旧走 Gemini，等语流 9 的保护代码。
- **撤回**：删除 `FLOW_AUDIO_ROUTES` 那一行（录音都回到 Gemini）或 `FLOW_AUDIO_TIMEOUT` 那一行（超时回到代码里的默认值），然后重启 flow。

### 08:15 · 语流：例句预生成补全（02:10 和 08:15 两次，数据库写入）

- **改了什么**：在语流的数据库里给没有例句的词补例句，两次一共 1,027 次请求、写入 16,308 条、花了 ¥5.43。
  - 02:10 那次：12 路并发，写入 11,212 条（含 80 条试跑），¥2.82。全站当天的花费到了每日预算 ¥3，脚本自己停了。
  - 08:15–08:18 那次：写入 5,096 条，¥2.61，到了临时调高的 ¥6 又自己停了。
  - 剩 89 个词，不到 ¥0.1，下次顺手补。
- **怎么跑的**：`fill_examples.py`（#98，多路并发）以 www 身份用 `systemd-run` 跑，只给这个进程设
  `FLOW_AI_ROUTES=next-examples=flow-batch-ds-flash`，走用户学生账号上的 DeepSeek，网站本身的设置没动。
  日志在 `/root/claude-ops/fill-examples-prod-1125*`。
- **谁、为什么**：语流 11（单词）。用户：「都开始」（费用超过 ¥5 就停，08:00 前停）、「直接调用 deepseek 可以高并发」、「现在补」。
- **抽查**：41 条合格，1 条偏敏感（mad：「那个疯子整天自言自语」）。用户选了「加，并重写这类例句」，
  也就是 #114：例句不嘲笑、不带刻板印象，复核一遍。
- **撤回**：例句在 `next_word_examples` 表里，按这两次的写入时间删掉对应的行即可；具体条件问语流 11。

### 08:15 · 内测版：朗读的采样率 22050

- **改了什么**：`/etc/flow-beta.env` 第 51 行加 `FLOW_TTS_SAMPLE_RATE=22050`，然后重启 flow-beta。
- **谁**：语流 2。用户：「可以，试一下」。
- **备份**：`/root/claude-ops/flow-beta.env.bak-ttsrate-20261125-081549`（只用来对照）。
- **撤回**：删除 `FLOW_TTS_SAMPLE_RATE` 那一行，然后重启 flow-beta。
- **比较**（语流 9 做的）：文件小 19.7%（658.5 → 528.8 KB），合成和下载的速度基本不变。11-24 晚上那次 13 秒的下载只是存储偶尔卡了一下。
  内测版保持 22050；语流 08:47 也改了（用户试听后说「听不出，改」，见那一条）。

### 08:1x · 语流：每日 AI 预算临时 ¥3 → ¥6（后台设置）

- **改了什么**：xmc.hk/flow 的 AI 页，把每日预算从 ¥3 调到 ¥6，只为当天把例句补完。凌晨那次补全在 ¥3 处自己停了。
- **谁、为什么**：语流 2。用户：「现在补」（在语流 1、语流 11 那边），「调到 6 元」（在语流 2）。
- **撤回**：同一页改回 ¥3。08:3x 已定成 ¥5（上一条）。

### 08:14 · AI 网关：按用途分道限流，总并发 20 → 64

- **改了什么**：xmc-api 的 `control_plane.py` 加了按用途分道的限流，配置在 `/www/xmc-api/limits.json`：
  - 总并发从 20 提到 64；
  - 批量和评测最多 16 个，不会占满学员用的位置；
  - 排队最多等 5 秒；
  - gemini-flow（Gemini 中转站）最多 2 个，和中转站自己的并发位一样。
- **谁、为什么**：语流 12 装的，用户在语流 12 那边点了「Yes, install」。起因是批量补例句和评测要多开并发，又不能挤到学员。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-lanes-20261125-081455`。
- **撤回**：只调数字就改 `/www/xmc-api/limits.json`，然后重启 xmc-api。要连分道一起去掉，就拷回 before-lanes 这份再重启。
  这份是装分道前最新的一份，语音转发和检索接口都还在里面。前提是之后没人再改过 `control_plane.py`，拷之前先对一下。

### 02:08 · 内测版：对话、复述、雅思口语的录音改走 Qwen-Omni

- **改了什么**：`/etc/flow-beta.env` 第 50 行加 `FLOW_AUDIO_ROUTES`（对话、复述、雅思口语三项，指向网关上的 `flow-audio-omni-flash`），然后重启 flow-beta。
- **谁**：语流 2。用户：「可以，切过去」。
- **备份**：`/root/claude-ops/flow-beta.env.bak-omni-20261125-020854`（只用来对照）。
- **撤回**：删除 `FLOW_AUDIO_ROUTES` 那一行，然后重启 flow-beta。

### 01:54 · 语流：文字 AI 改走百炼 DeepSeek（后台设置）

- **改了什么**：xmc.hk/flow 的 AI 页，用管理员账号改：
  - 「所有任务都用这个」选 `flow-text-ds-flash`，14 个文字任务全部改过去；
  - 每日预算 ¥3；
  - 百炼折扣 1.0（学生券按标价扣）；
  - 每晚的小评测保持打开。
  
  都记进了后台的操作记录。没有改 `/etc/flow.env`。
- **谁、为什么**：语流 2，跟 r27 一起，按用户的「发，都按推荐」。内测版 11-24 22:25 已经先切过，评测和内测版都没问题。
- **核对**：01:57 在正式版跑了一轮轻量 e2e，147/147：12 次 AI 调用都是 route=`flow-text-ds-flash`、served=deepseek-v4.1-flash，
  每次 1.3–5.0 秒，没有走备用，整轮 29.5 秒。之前同类任务走 Gemini，一次要 4.6–13.3 秒。录音那条路不受影响，还是 Gemini。
- **撤回**：同一页把「所有任务都用这个」选回 Gemini 3.8 Flash（`flow-text`），预算改回 0，折扣改回 0.65。

### 01:50 · 语流：打开服务器朗读

- **改了什么**：在 `/etc/flow.env` 末尾加了两行（第 39–40 行），`FLOW_TTS_MODEL=flow-tts` 和 `FLOW_TTS_DAILY_CHARS=30000`
  （全站每天最多合成 3 万字），然后重启 flow。
- **谁、为什么**：语流 2，跟 r27 一起，按用户的「发，都按推荐」。内测版 11-24 23:31 已经先开过。
- **改之前**：r27 已经装好 `flow.service.d/61-flow-tts.conf`。在 flow 自己的沙箱里以 www 身份写 `audio/tts`，重启前后各试一次，都写得进去。
  这次没有像内测版那样踩到沙箱的坑。
- **备份**：`/root/claude-ops/flow.env.bak-tts-20261125-015021`（只用来对照）。
- **撤回**：删除 `FLOW_TTS_MODEL` 和 `FLOW_TTS_DAILY_CHARS` 那两行，然后重启 flow：
  `sed -i '/^FLOW_TTS_MODEL=/d;/^FLOW_TTS_DAILY_CHARS=/d' /etc/flow.env && systemctl restart flow`。页面会退回浏览器的声音。
- **核对**：
  - 用服务自己的环境在沙箱里真的合成了一句固定句：78 个字，1.7 秒，108 KB；外网取得到（200，audio/mpeg）。
  - 游客请求已经存下的句子回 200，没存的回 404 code=guest，和设计一样。
  - `/api/session` 返回 tts=true。
- **要记住**：两个站共用 `audio/tts`，同一句话、同一个声音、同一个模型只合成一次。

### 00:47 · 内测版：服务器朗读每天的总字数上限

- **改了什么**：`/etc/flow-beta.env` 加了 `FLOW_TTS_DAILY_CHARS`（全站每天最多合成多少字，#69 的开关之一）。
- **谁**：语流 2。数值、原因和备份以语流 2 在香港 `/root/claude-ops/ops-notes.log` 里的记录为准，这里还没核对。
- **撤回**：删除 `FLOW_TTS_DAILY_CHARS` 那一行，然后重启 flow-beta（不设时用代码里的默认值）。

### 00:37 · 内测版：系统邮件改用 flowlang.cn 发（阿里云邮件推送）

- **改了什么**：Cloudflare 上给 `mail.flowlang.cn` 加了 MX、SPF、DKIM 和 DMARC（p=none），只在 mail 子域名下，根域名 flowlang.cn
  留着以后收信用。`/etc/flow-beta.env` 的 `FLOW_SMTP_*` 改成阿里云邮件推送（465 端口），发件人「语流 Flow」，不收回信；
  另加 `FLOW_SMTP_FALLBACK_*` 指向原来的飞书邮箱，作备用。
- **谁、为什么**：语流 16。原来两个站都用用户自己的 jasa.hk 飞书邮箱发（免费版每天 100 封、50 个外部收件人）。用户选了
  「阿里云邮件推送」，同意「验证通过就切」内测版；用户定的规矩是优先用 flowlang.cn 发，被拒收再改用原来的飞书邮箱。
- **备份**：`/root/claude-ops/flow-beta.env.bak-20261125-mail`。
- **撤回**：删除 `FLOW_SMTP_FALLBACK_*` 那几行，把 `FLOW_SMTP_*` 那几行改回原来的飞书邮箱设置，然后重启 flow-beta。
  `/root/claude-ops/mail-sender-undo-beta.py` 就是按行做这件事（先 `--dry-run` 看它要改哪几行）。
- **测试**：Gmail、QQ、jasa.hk 进收件箱；Outlook 进垃圾箱；iCloud 第二封被退回（554，只在阿里云的发送详情里看得到）。
  网易没测。08:29–08:30 在内测版 b24 上验证了「10 分钟内重发走备用」：首发走阿里云、重发走飞书，两封都进了 Gmail 收件箱。
  语流 08:33 也切过去了（见那一条）。

### 00:05 · AI 网关：加联网检索接口和 4 个评测用模型名

- **改了什么**：xmc-api 的 `control_plane.py` 加 `POST /v1/search/completions`；控制台加模型名 `flow-search-ds-flash`、
  `flow-search-qwen-plus`、`flow-eval-asr-flash`、`flow-eval-omni-flash`（都在用户个人学生账号那个上游，评测用）。
- **谁、为什么**：语流 12，评测今日热点改走百炼检索、情景对话改走百炼语音。用户：「现在装」「同意，跑吧」。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-search-20261125-000546`。重启网关约 1 秒。
- **撤回**：控制台删掉这 4 个名字；要连接口一起去掉，拷回这份备份（它是装检索前的最新一份，语音转发还在里面），然后重启 xmc-api。
- **影响学员吗**：不影响。两个站都没设 `FLOW_SEARCH_AI_MODEL`（#74 的开关），热点还是 Gemini 检索。

## 2026-11-24

### 23:46 · 内测版：systemd 沙箱里开声音目录的写权限

- **改了什么**：新建 `/etc/systemd/system/flow-beta.service.d/70-tts-write.conf`（`[Service]` 里
  `ReadWritePaths=/www/wwwroot/flow/audio/tts`），`daemon-reload`，重启 flow-beta。
- **为什么**：23:31 打开服务器朗读后，语流 9 发现声音存不下来：flow-beta 跑在 `ProtectSystem=strict` 的沙箱里，只能写自己的
  data 目录，写 `audio/tts` 得到 EROFS。结果网关每次照样收费，文件没存，页面退回浏览器的声音。23:31 那次检查是在服务外面以
  www 身份跑的，所以没发现。
- **谁**：语流 2。用户：「可以，加上」。
- **验证**：在 flow-beta 进程的挂载空间里（`nsenter -t <PID> -m runuser -u www`）写了测试文件；语流 9 用临时学员走了 5 次
  `/api/next/tts`，都是 200、都存下了 mp3，网关记录对得上。
- **撤回**：删掉这个文件，`daemon-reload`，重启 flow-beta。
- **之后**：#75（11-24 23:55 合并）让每次部署自己建 `audio/tts`（www:www）并装 `$SVC.service.d/61-flow-tts.conf`
  （`ReadWritePaths=-<audio>/tts`），内测版 b11 起有，语流 r27 起有。手工的 70 在 11-25 08:30 去掉了（见那一条）。

### 23:31 · 内测版：打开服务器朗读（CosyVoice）

- **改了什么**：`/etc/flow-beta.env` 第 42 行加 `FLOW_TTS_MODEL=flow-tts`，重启 flow-beta；新建 `/www/wwwroot/flow/audio/tts`
  （www:www 755，原来的 audio 目录是 root:root 755，www 写不进）。`/etc/flow.env` 没动。
- **谁、为什么**：语流 2，#69 的服务器朗读默认关着，要设这一项才开。用户：「可以，打开」（之前在语流 1 说过「直接打开」）。
- **备份**：`/root/claude-ops/flow-beta.env.bak-tts-20261124-233048`。
- **撤回**：删除 `FLOW_TTS_MODEL` 那一行，然后重启 flow-beta。页面会自己退回浏览器的声音。
- **出过的问题**：沙箱不让写，23:46 修好（上一条）。
- **要记住**：两个站共用 `audio/tts`。文件名由声音和句子算出来；#76 起文件名里还带上模型、上游声音和格式。哪天两个站用不同的
  朗读模型，文件名会自己分开。

### 23:14 · AI 网关：加语音转发 `flow-tts`

- **改了什么**：xmc-api 的 `control_plane.py` 加 `POST /v1/audio/speech`；控制台加模型 `flow-tts`（id 12）→ aliyun 上游的
  `cosyvoice-v3-flash`。只认 4 个声音（loongabby_v3、loongandy_v3、loongemily_v3、loongeric_v3），一次最多 1500 字。
  用量记在网关的 usage 表（endpoint 记 `/v1/audio/speech`，顺带修了原来所有请求都记成 chat 的问题）。
- **谁、为什么**：语流 12，让 Flow 不用自己拿百炼的 key 就能合成声音。用户：「同意加通道」，装的时候「Yes, install now」。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-tts-20261124-231452`。重启网关约 1 秒（所有走网关的请求会断一两秒）。
- **撤回**：控制台删模型 `flow-tts`，Flow 就不会再调到它。要连接口一起去掉，只删 `control_plane.py` 里语音转发那一段，然后重启
  xmc-api。不要直接拷回 before-tts 那份备份：11-25 00:05 又在同一个文件上装了检索接口，整份拷回会把它一起撤掉。
- **验证**：装后 7 次聊天请求都是 200；公网不带 key 回 401；第一次真合成是 23:31 内测版那次（56 个字，1.5 秒）。

### 22:49 · Gemini 中转站并发可设（#68，代码已合，没上线）

- **改了什么**：`flow-gateway/gateway.py` 的并发从固定 2 改成读 `GATEWAY_SLOTS`（1–32，默认 6），`/health` 显示 slots；
  `flow-gateway/set_slots.sh` 在中转站那台 Google Cloud 机器上备份、只改 SLOTS 那一行和环境文件、重启、查 `/health`，失败自动恢复。
- **为什么**：11-24 21:45–22:30 中转站排队，平均 10–21 秒、最长约 59 秒，22:08 一次 503、22:28 一次 504（见 releases.md r26）。
  用户：「好，你来改」。
- **谁**：语流 2 写代码；**上线要用户自己在 Google Cloud Shell 里执行**（那台机器只有用户的 Google 账号能登）。
- **撤回**：`set_slots.sh 2`，或者恢复它留下的备份。如果出现 429，往下调。

### 22:46 · GitHub：内测版跟着 main 自动发布

- **改了什么**：#66 的 `.github/workflows/beta.yml` 生效：main 的 CI 通过后自动发内测版（轻量自检，每次最多 1 个 AI 请求）。
  开关是仓库变量 `BETA_AUTO`：不设 = 开。
- **谁**：语流 15 写；用户：「打开自动跟随」。第一次自动发布是 23:26 的 b9。
- **暂停 / 恢复**：`gh variable set BETA_AUTO --body off -R Jasame/Flow` / `gh variable delete BETA_AUTO -R Jasame/Flow`。

### 22:25 · 内测版：文字 AI 切到百炼 DeepSeek

- **改了什么**：`/etc/flow-beta.env` 第 41 行加 `FLOW_AI_ROUTES='{"*": "flow-text-ds-flash"}'`，重启 flow-beta。
  单引号是必须的：systemd 读 EnvironmentFile 时会把不带引号的 JSON 拆坏，变成无效值，被悄悄忽略。#64 以后也可以写成
  `FLOW_AI_ROUTES=flow-text-ds-flash`，写错了会记日志、后台红字提示。
- **谁、为什么**：语流 2，用脚本 `/root/claude-ops/beta-ai-routes.sh`（日志 `beta-ai-routes.log`）。语流 12 的评测里 DeepSeek 和
  Gemini 一样 48/48，等待从约 5 秒降到约 2 秒，费用约 1/4。用户：「可以，b6 后切」（b6 没带 #48，挪到 b7 之后），
  再早用户定过「都用 DeepSeek」。
- **备份**：`/root/claude-ops/flow-beta.env.bak-20261124-222514`。`/etc/flow.env` 没动。
- **验证**：进程环境里读得到；b8 自检里所有文字任务都是 route=model=`flow-text-ds-flash`，实际回答的是 deepseek-v4.1-flash，
  每次 1.7–4.8 秒。录音那条路不走这个设置，还是 Gemini。
- **撤回**：删除 `FLOW_AI_ROUTES` 那一行，然后重启 flow-beta。

### 22:11 · 内测版：测试账号 duet-tester

- **改了什么**：内测版的数据库里建了账号 `duet-tester`（没有邮箱，初始密码随机），用户用一次性重设链接（24 小时）自己设密码，
  谁都不知道密码。
- **谁、为什么**：语流 1，给 Claude Duet 测试用。记在 `/root/claude-ops/ops-notes.log`。
- **撤回**：后台删掉这个账号。

### 晚上 · AI 网关：DeepSeek 和评测用的模型名

- **改了什么**：控制台加 `flow-eval-qwen37-plus`、`flow-eval-ds-flash`、`flow-eval-qwen-plus`、`flow-eval-qwen37-flash`、
  `flow-eval-qwen38-flash`（评测用，都指向用户个人学生账号那个上游 aliyun，不配备用）；用户定了「都用 DeepSeek」以后，又加了
  `flow-text-ds-flash`（学员用，aliyun 上的 deepseek-v4.1-flash，Gemini 作备用）和 `flow-batch-ds-flash`（例句预生成，不配备用）。
  上游 aliyun 的 key 是用户自己在网关控制台填的。
- **谁**：语流 12。用户：「扣的是学生券，可以跑全量评测了」；全量评测 18:54–19:05 在香港跑（报告
  `/root/claude-ops/ai-eval-report-20261124-1854-*.json`）。
- **撤回**：控制台删掉这些名字。Flow 问不到时会退回 `flow-text`（Gemini）。

### 18:41 · 两个站：连载录音包

- **改了什么**：装 narration-serials：《新学期》B1 和《灯塔日志》C1 各 6 集，96 个文件、16 MB，`audio/index.json` 254 → 266 条。
  之前这两部连载在正式版上一直没有录音，微信里完全没声音。
- **谁**：语流 2。用户：「可以，装」（选项卡：现在装）。
- **备份**：`/root/claude-ops/backup-narration-serials-20261124-184140`。撤回命令在 `/root/claude-ops/` 下这个包的 .log 里。

### 18:30 · 两个站：三个录音包

- **改了什么**：
  - words-b：122 个单词发音（b000、b001 两个拼合文件）。语流在 r26 以前只认旧编号，这 122 个词会退回浏览器声音；内测版直接能用。
  - narration-content1：内容线第 1 批 14 篇 × 4 种声音，112 个文件、21 MB，`index.json` 240 → 254 条。
  - narration-old：154 篇简版 × 4 种声音，1232 个文件、89 MB，只写 `audio/index-old.json`（0 → 154），不碰 `index.json`，
    要 #54 以后的代码才读。
- **谁**：语流 2。用户：「可以，b5 后装」「你来传」。
- **备份**：`/root/claude-ops/backup-words-b-20261124-1830*`、`backup-narration-content1-20261124-1830*`、
  `backup-narration-old-20261124-1830*`。每个包只新增、装前核对 sha，撤回命令在对应的 .log 里。
- **要记住**：两个站读同一个声音目录，装一次两个站同时有。录音不走发布，要这样单独装；母本在 `~/Flow-media`（Mac）。

### 13:40 前后 · 语流：后台只有用户是管理员

- **改了什么**：`/etc/flow.env` 加 `FLOW_ADMIN_EMAILS`（只有用户自己登录后台用的那个邮箱，这里不写），重启 flow。
  从此只有用户是「管理员」，其他能进后台的人「只看数据」。没设这一项时所有人都是管理员。
- **谁**：语流 2，按用户 11-24 中午的决定（先确认后台右上角认得出用户的邮箱，再设）。
- **备份**：`/root/claude-ops/flow.env.bak-*`。
- **撤回**：删除 `FLOW_ADMIN_EMAILS` 那一行，然后重启 flow。

### 13:40 前后 · 杭州状态页分开查两个站

- **改了什么**：杭州 `/www/xmc-status/generate.py`：`flow` 查 flowlang.cn，`flowBeta` 查 flow.jasa.hk，各自告警
  （xmc-status 提交 3bddb33，工作台 5.5.3）。
- **谁**：词书会话（语流 1）。备份在 `generate.py.bak.*`；`/www/xmc-status` 是 git 仓库，可以按提交撤回。

### 09:21 · 香港 nginx：请求大小上限 24 KB → 3 MB

- **改了什么**：nginx `location /` 的 `client_max_body_size` 从 24k 改成 3m。之前超过 24 KB 的请求（口语录音、问题反馈的截图）
  都会被拦（413），正式版的口语练习会坏。Flow 自己按路径限制大小（一般 20 KB，作文和导入 40 KB，录音 2.2 MB，反馈 2.9 MB）。
- **谁**：语流 2。用户同意（r21 发布以前）。
- **备份**：`/root/claude-ops/nginx-body-20261124-092110.conf`（只用来对照）。
- **撤回**：把 `client_max_body_size` 那一行改回 24k，`nginx -t` 通过后 reload。

### 02:13 · 香港：分成正式版和内测版两个站

- **改了什么**：新建内测版实例 `flow-beta.service`（端口 8092，代码 `/www/wwwroot/flow-beta`，设置 `/etc/flow-beta.env`，
  `FLOW_CHANNEL=beta`，自己的数据库，没有后台端口，声音读语流的目录），自动部署 `flow-autodeploy-beta.timer` 读 b<N>；
  nginx 按域名分流（`vhost/nginx/0-flow-channel.conf` 里的 map：flow.jasa.hk → 8092，其他 → 8090）；
  语流的 `FLOW_PUBLIC_URL` 改成 https://flowlang.cn。
- **谁、为什么**：语流 2，用 `tools/beta_setup.py`。用户定的：flowlang.cn 做正式版，flow.jasa.hk 做内测版，「独立数据（推荐）」，
  待发布的版本先上内测版。
- **备份**：`/root/claude-ops/beta-setup-*`。
- **撤回**：`python3 /root/claude-ops/beta_setup.py --undo`：停掉内测版和它的自动部署，去掉分流的 map，flow.jasa.hk 回到语流。
  要注意两点：它会把 02:13 备份的 nginx 文件整份拷回去，09:21 改的请求大小上限（3m）也会跟着回到 24k，所以跑完要把
  `client_max_body_size` 那一行再改回 3m；它不动 `/etc/flow.env`，要的话手工改回 `FLOW_PUBLIC_URL` 那一行，然后重启 flow。

## 2026-11-23

### 22:47 · 语流：AI 改走香港本机的网关，文字用 flow-text

- **改了什么**：`/etc/flow.env` 设 `FLOW_AI_URL=http://127.0.0.1:9000/v1/chat/completions`（香港本机的 xmc-api，少绕一圈
  Cloudflare）和 `FLOW_TEXT_AI_MODEL=flow-text`，重启 flow。`ai_check.py` 4/4（要用 root 跑，它自己读 `/etc/flow.env`）。
- **谁**：服务器会话（现在的语流 1）。用户：「r20 后改」。
- **备份**：`/etc/flow.env.bak-20261123-2247`。
- **撤回**：把 `FLOW_AI_URL` 那一行改回 `https://api.xmc.hk/v1/chat/completions`，删除 `FLOW_TEXT_AI_MODEL` 那一行，然后重启 flow。
- **要记住**：网关或 Flow 换到别的机器时，`FLOW_AI_URL` 要改回 `https://api.xmc.hk/v1/chat/completions`（杭州 RECOVERY.md 写了）。

### 21:54 · 香港：删掉存在服务器上的一份 Gemini key

- **改了什么**：`/etc/xmc-api/gemini.key` 用 `shred -u` 删掉（那个 key 在香港用不了，AI Studio 不对香港开放）。
- **谁**：语流 1。用户：「删掉」。那个 key 曾贴在对话里，作废和重新生成要用户自己在 AI Studio 做。

### 20:59 · AI 网关：建模型名 flow-text

- **改了什么**：控制台建 `flow-text`（id 4）：上游 gemini-flow（Gemini 中转站）→ gemini-3.8-flash，不配备用。Flow 的网站 key
  可以用所有模型。
- **谁**：语流 1，r18 会话要的（Flow 的文字功能用）。用户同意。
- **撤回**：删掉或停用 `flow-text`，Flow 退回主模型。

### 19:35 · AI 网关从杭州搬到香港

- **改了什么**：xmc-api 在香港跑（`xmc-api.service`，`/www/xmc-api`），api.xmc.hk 指向香港的隧道；杭州的 xmc-api 停用，
  杭州隧道里 api.xmc.hk 那条留作回退。
- **谁**：语流 1（当时的服务器会话）。用户：「你来部署」。
- **出过的问题**：19:15 第一次搬，Gemini 中转站不认香港的 IP，约 2 分钟 AI 全是 502，自动回滚；把香港加进中转站白名单后再搬。
- **撤回**：步骤在杭州 `/www/xmc-status/RECOVERY.md`。

### 16:47 · Flow 从杭州搬到香港

- **改了什么**：Flow（当时只有 flow.jasa.hk 一个站）搬到香港服务器，切换时中断约 17 秒；自动部署、每日材料、备份都在香港。
  r18 是杭州上的最后一个版本，r19 起在香港。
- **谁**：语流 1（当时的服务器会话）。用户 11-23 下午买好香港服务器后说开始迁移；之后定了「杭州做冷备」。
- **撤回**：杭州的 Flow 停用但代码和数据都留着做冷备。切回去的步骤在杭州 RECOVERY.md「香港坏了：Flow 在杭州冷备」
  （1–4 步在沙箱里演练过，5–8 步没演练）。
