# Flow 服务器和配置的变动

发布（tag）以外，对服务器、设置文件、AI 网关、GitHub 仓库设置做的改动都记在这里。发布本身在 [releases.md](releases.md)。

规矩：

- **不写任何密钥、密码、邮箱地址、IP。** 只写改了哪个文件的哪一项、为什么、谁做的、备份在哪、怎么撤回。
- 服务器按地区叫：**香港**（Flow 两个站、AI 网关）、**杭州**（xmc.hk 后台、jasa.hk 等）。
- 时间是北京时间。备份和日志默认在香港的 `/root/claude-ops/`。
- 每次动服务器以前先备份；改完要从服务本身验证（真的发一次请求，或者看那个进程的环境和挂载），只从外面看不算。
- **`/etc/flow.env`、`/etc/flow-beta.env` 只按行撤回**：好几个会话都往这两个文件里加过行，整份恢复旧备份会把后来别人加的行一起抹掉。
  下面写的「备份」是改之前的那份，用来对照，不要整份拷回去。
- 证书、宝塔、杭州面板和其他项目的维护记在杭州的 ops-log.md，这里只记跟 Flow 有关的。
- 以后每改一次就在最上面加一条。

两个站的设置文件：语流（flowlang.cn）是 `/etc/flow.env` 和 `flow.service`；内测版（flow.jasa.hk）是 `/etc/flow-beta.env` 和
`flow-beta.service`。两个站读同一个声音目录 `/www/wwwroot/flow/audio`。

## 还没做完、在等的

| 事情 | 现在 | 等什么 |
| --- | --- | --- |
| Gemini 中转站并发从 2 改成 6（#68） | 代码已合（11-24 22:49），中转站上还是 2 | 用户在 Google Cloud Shell 里执行 `flow-gateway/set_slots.sh 6`（步骤在 #68 和 flow-gateway 的说明里）。上线后语流 12 对比前后的 503/504 和等待时间 |
| 语流切到百炼 DeepSeek | 内测版 11-24 22:25 已切；语流还是 Gemini | 下次「发正式版」时问用户：后台「所有任务都用这个」选 `flow-text-ds-flash`、百炼折扣 1.0、每日预算 3 元（或 `/etc/flow.env` 写 `FLOW_AI_ROUTES`） |
| 语流打开服务器朗读 | 内测版 11-24 23:31 已开；语流没开 | 下次发正式版会自动装 `flow.service.d/61-flow-tts.conf`；装上后在服务里证明写得进 `audio/tts`，用户同意后加 `FLOW_TTS_MODEL=flow-tts` |
| 删内测版手工加的 `70-tts-write.conf` | 还在 | b11 起每次部署自己装 `61-flow-tts.conf`，确认装上后找个没人用的时候删掉 70，`daemon-reload` 再重启 flow-beta |
| 数据库副本只留 14 天（#58） | 内测版只列不删；语流还没发 #58 | 第一次在语流上清理以前，先 `ops.py prune-deploy --channel prod --dry-run`，把清单给用户看，用户同意才删 |
| 语流的系统邮件改用 flowlang.cn 发 | 内测版 11-25 凌晨已切到阿里云邮件推送；语流还是用户的 jasa.hk 飞书邮箱 | 语流 3 的「被拒收就改走备用」代码和 #85（EHLO 用站点域名）上正式版以后，用户在语流 16 同意再切 `/etc/flow.env`（杭州的 xmc-hz-watch 也读这几行，要一起看） |
| 上传用过的整包 `/root/claude-ops/flow-audio-packs.tar`（112 MB） | 还在，内容已装好 | 可以删，删以前问一下 |

## 2026-11-25

### 凌晨 · 内测版：系统邮件改用 flowlang.cn 发（阿里云邮件推送）

- **改了什么**：Cloudflare 上给 `mail.flowlang.cn` 加了 MX、SPF、DKIM 和 DMARC（p=none），只在 mail 子域名下，根域名 flowlang.cn
  留着以后收信用。`/etc/flow-beta.env` 的 `FLOW_SMTP_*` 改成阿里云邮件推送（465 端口），发件人「语流 Flow」，不收回信；
  另加 `FLOW_SMTP_FALLBACK_*` 指向原来的飞书邮箱，作备用。
- **谁、为什么**：语流 16。原来两个站都用用户自己的 jasa.hk 飞书邮箱发（免费版每天 100 封、50 个外部收件人）。用户选了
  「阿里云邮件推送」，同意「验证通过就切」内测版；用户定的规矩是优先用 flowlang.cn 发，被拒收再改用原来的飞书邮箱。
- **备份**：`/root/claude-ops/flow-beta.env.bak-20261125-mail`。
- **撤回**：`/root/claude-ops/mail-sender-undo-beta.py`（先 `--dry-run`），按行改回去。
- **测试**：Gmail、QQ、jasa.hk 进收件箱；Outlook 进垃圾箱；iCloud 第二封被退回（554，只在阿里云的发送详情里看得到）。
  网易没测。语流的 `/etc/flow.env` 没动（见上表）。

### 00:47 · 内测版：服务器朗读每天的总字数上限

- **改了什么**：`/etc/flow-beta.env` 加了 `FLOW_TTS_DAILY_CHARS`（全站每天最多合成多少字，#69 的开关之一）。
- **谁**：语流 2。数值、原因和备份以语流 2 在香港 `/root/claude-ops/ops-notes.log` 里的记录为准，这里还没核对。
- **撤回**：删掉这一行，重启 flow-beta（不设时用代码里的默认值）。

### 00:05 · AI 网关：加联网检索接口和 4 个评测用模型名

- **改了什么**：xmc-api 的 `control_plane.py` 加 `POST /v1/search/completions`；控制台加模型名 `flow-search-ds-flash`、
  `flow-search-qwen-plus`、`flow-eval-asr-flash`、`flow-eval-omni-flash`（都在用户个人学生账号那个上游，评测用）。
- **谁、为什么**：语流 12，评测今日热点改走百炼检索、情景对话改走百炼语音。用户：「现在装」「同意，跑吧」。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-search-20261125-000546`。重启网关约 1 秒。
- **撤回**：恢复这个文件，重启 xmc-api；控制台删掉这 4 个名字。
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
  （`ReadWritePaths=-<audio>/tts`），内测版 b11 起有，语流下次发正式版时有。之后手工的 70 可以删（见上表）。

### 23:31 · 内测版：打开服务器朗读（CosyVoice）

- **改了什么**：`/etc/flow-beta.env` 第 42 行加 `FLOW_TTS_MODEL=flow-tts`，重启 flow-beta；新建 `/www/wwwroot/flow/audio/tts`
  （www:www 755，原来的 audio 目录是 root:root 755，www 写不进）。`/etc/flow.env` 没动。
- **谁、为什么**：语流 2，#69 的服务器朗读默认关着，要设这一项才开。用户：「可以，打开」（之前在语流 1 说过「直接打开」）。
- **备份**：`/root/claude-ops/flow-beta.env.bak-tts-20261124-233048`。
- **撤回**：删掉这一行，重启 flow-beta。页面会自己退回浏览器的声音。
- **出过的问题**：沙箱不让写，23:46 修好（上一条）。
- **要记住**：两个站共用 `audio/tts`。文件名由声音和句子算出来；#76 起文件名里还带上模型、上游声音和格式。哪天两个站用不同的
  朗读模型，文件名会自己分开。

### 23:14 · AI 网关：加语音转发 `flow-tts`

- **改了什么**：xmc-api 的 `control_plane.py` 加 `POST /v1/audio/speech`；控制台加模型 `flow-tts`（id 12）→ aliyun 上游的
  `cosyvoice-v3-flash`。只认 4 个声音（loongabby_v3、loongandy_v3、loongemily_v3、loongeric_v3），一次最多 1500 字。
  用量记在网关的 usage 表（endpoint 记 `/v1/audio/speech`，顺带修了原来所有请求都记成 chat 的问题）。
- **谁、为什么**：语流 12，让 Flow 不用自己拿百炼的 key 就能合成声音。用户：「同意加通道」，装的时候「Yes, install now」。
- **备份**：`/root/claude-ops/xmc-api-control_plane.py.before-tts-20261124-231452`。重启网关约 1 秒（所有走网关的请求会断一两秒）。
- **撤回**：恢复这个文件，重启 xmc-api；控制台删模型 `flow-tts`。
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
- **撤回**：删掉这一行，重启 flow-beta。

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
- **撤回**：删掉这一行，重启 flow。

### 13:40 前后 · 杭州状态页分开查两个站

- **改了什么**：杭州 `/www/xmc-status/generate.py`：`flow` 查 flowlang.cn，`flowBeta` 查 flow.jasa.hk，各自告警
  （xmc-status 提交 3bddb33，工作台 5.5.3）。
- **谁**：词书会话（语流 1）。备份在 `generate.py.bak.*`；`/www/xmc-status` 是 git 仓库，可以按提交撤回。

### 09:21 · 香港 nginx：请求大小上限 24 KB → 3 MB

- **改了什么**：nginx `location /` 的 `client_max_body_size` 从 24k 改成 3m。之前超过 24 KB 的请求（口语录音、问题反馈的截图）
  都会被拦（413），正式版的口语练习会坏。Flow 自己按路径限制大小（一般 20 KB，作文和导入 40 KB，录音 2.2 MB，反馈 2.9 MB）。
- **谁**：语流 2。用户同意（r21 发布以前）。
- **备份**：`/root/claude-ops/nginx-body-20261124-092110.conf`。撤回：恢复，`nginx -t` 后 reload。

### 02:13 · 香港：分成正式版和内测版两个站

- **改了什么**：新建内测版实例 `flow-beta.service`（端口 8092，代码 `/www/wwwroot/flow-beta`，设置 `/etc/flow-beta.env`，
  `FLOW_CHANNEL=beta`，自己的数据库，没有后台端口，声音读语流的目录），自动部署 `flow-autodeploy-beta.timer` 读 b<N>；
  nginx 按域名分流（`vhost/nginx/0-flow-channel.conf` 里的 map：flow.jasa.hk → 8092，其他 → 8090）；
  语流的 `FLOW_PUBLIC_URL` 改成 https://flowlang.cn。
- **谁、为什么**：语流 2，用 `tools/beta_setup.py`。用户定的：flowlang.cn 做正式版，flow.jasa.hk 做内测版，「独立数据（推荐）」，
  待发布的版本先上内测版。
- **备份**：`/root/claude-ops/beta-setup-*`。
- **撤回**：`python3 /root/claude-ops/beta_setup.py --undo`。

## 2026-11-23

### 22:47 · 语流：AI 改走香港本机的网关，文字用 flow-text

- **改了什么**：`/etc/flow.env` 设 `FLOW_AI_URL=http://127.0.0.1:9000/v1/chat/completions`（香港本机的 xmc-api，少绕一圈
  Cloudflare）和 `FLOW_TEXT_AI_MODEL=flow-text`，重启 flow。`ai_check.py` 4/4（要用 root 跑，它自己读 `/etc/flow.env`）。
- **谁**：服务器会话（现在的语流 1）。用户：「r20 后改」。
- **备份**：`/etc/flow.env.bak-20261123-2247`。
- **撤回**：把这两行改回去（`FLOW_AI_URL` 改回 `https://api.xmc.hk/v1/chat/completions`，删掉 `FLOW_TEXT_AI_MODEL`），重启 flow。
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
