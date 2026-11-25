# 内测版发布记录（自动追加）

每次发布后由 `tools/changelog.py record` 追加一段：装了哪个提交、新合并的 PR 和改到的区域、发布时的自检结果。
整理过的总账（正式版带学员能看到的变化和用户的原话）在 main 的 `docs/releases.md`。

### b12 · 2026-11-25 00:33
- main `928ab52`，构建 `b036799`
- 新合并的 PR（自 b11 起）：
  - #76 服务器朗读：文件名里加上模型、上游声音和格式（听和说）
  - #79 主屏 App 外壳：每页有返回、让开灵动岛和底部横条、键盘不挡输入框、回到前台换新版本（今日和计划、开局和考试、操作指南、发版和构建）
- 自检：DEPLOYED，装了 8 个文件（0 个新的）；轻量 e2e 147/149，没过：b1: dialog end gives feedback；db: no AI job failed，服务器报错 1

### b13 · 2026-11-25 01:11
- main `548415a`，构建 `f22b005`
- 新合并的 PR（自 b12 起）：
  - #80 flow-pull.sh：FLOW_AUDIO_DIR 带引号也能正确读出（发版和构建）
  - #78 iPhone 上的短音频改走 Web Audio：从第一个音开始放，灵动岛不再一下一下地弹；长文朗读接上锁屏控制（单词、听和说、今日和计划、操作指南、发版和构建）
  - #81 录音：麦克风只在录音时开着，录完切回扬声器；第一次录音前先说明（听和说、操作指南）
  - #71 邮件统一版式（A 简洁卡片）；验证码邮件让 iPhone、Mac 和密码管理器能认出来（后台和班级、AI、操作指南）
  - #82 后台 AI 费用加「AI 朗读（声音）」：按字符计价，算进每日预算（AI）
  - #73 每周进度邮件换成统一邮件版式（A 简洁卡片）（今日和计划）
- 自检：DEPLOYED，装了 13 个文件（2 个新的）；轻量 e2e 149/149，服务器报错 0

### b14 · 2026-11-25 01:52
- main `f184935`，构建 `5ca2b75`
- 新合并的 PR（自 b13 起）：
  - #85 邮件：EHLO 用站点域名，不用机器名（后台和班级）
  - #87 口语第 1 步：AI 像真人说话、角色声音、声音接力、说完就显示进度（听和说、开局和考试、操作指南）
  - #72 背词提醒邮件换成统一版式（A 简洁卡片，接在 #71 后面）（单词）
  - #89 ai_eval 加情景对话两类题：说一句的回复和纠错、对话结束的总结（AI、内容）
  - #88 录音可以按任务走百炼 Qwen-Omni，Gemini 作备用；默认不开（FLOW_AUDIO_ROUTES）（AI、操作指南）
  - #84 iPhone 读音：设置里可切「自动 / 兼容模式」，兼容模式把单词压到 0.95 秒以下（垫 0.2 秒、切词尾安静）（听和说、今日和计划、后台和班级、操作指南）
- 自检：DEPLOYED，装了 17 个文件（0 个新的）；轻量 e2e 147/149，没过：a2: AI rewrite of an A2 sentence；db: no AI job failed，服务器报错 1（02:10 从 Actions 日志补记）

### b15 · 2026-11-25 02:01
- main `71b90c4`，构建 `16ec821`
- 新合并的 PR（自 b14 起）：
  - #92 CI：main 上的 Tests 不再被下一次合并取消；不碰网站和界面测试的 PR 跳过 UI 分片（发版和构建）
  - #94 deploy.sh：REQUEST 里的分支名，main 包含这个提交时就写 main（发版和构建）
  - #97 测试：班级试用人次测试在北京时间 0–1 点不再挂（测试）
  - #96 工作约定：各会话可以自己给自己的 PR 开自动合并（发版和构建）
  - #95 单词读音方式在主屏 App 里也能切：「连续」/「标准」，「标准」的垫音 0.1–0.3 秒（听和说、后台和班级、操作指南）
  - #93 邮件：备用发信通道（被拒收就用 i@jasa.hk，优先 flowlang）（后台和班级、操作指南）
- 自检：DEPLOYED，装了 6 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0

### b16 · 2026-11-25 02:29
- main `66317da`，构建 `2475df5`
- 新合并的 PR（自 b15 起）：
  - #98 例句预生成：并发请求（--workers）、限流退避、--max-yuan 封顶（单词）
  - #90 AI 评分：DeepSeek 换了写法也收得下；收不下时再问一次、再交给 Gemini（听和说、AI）
  - #83 发布总账：每一次发布都记下来，内测版自动续写（发版和构建）
- 自检：DEPLOYED，装了 9 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45460031555

### b17 · 2026-11-25 02:39
- main `d286f7d`，构建 `2db224d`
- 新合并的 PR（自 b16 起）：
  - #99 整篇伴读换新声音：没有录音的文章按句子用 AI 朗读；导入文章的声音只给本人（听和说、后台和班级、操作指南）
  - #91 认识语流：首屏下加「一分钟看懂语流」动画（操作指南）
  - #101 操作指南页头只写日期（更新于 2026-11-25），不写网站版本号（操作指南）
- 自检：DEPLOYED，装了 29 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45461668045

### b18 · 2026-11-25 02:50
- main `1d31d69`，构建 `c8112d3`
- 新合并的 PR（自 b17 起）：
  - #102 ai_eval 能看出「模型没写总评」；录音交给 Gemini 时的超时可以配置（AI）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45463322724

### b19 · 2026-11-25 03:01
- main `3613895`，构建 `ec7da43`
- 新合并的 PR（自 b18 起）：
  - #103 内容线第 2 批：28 篇新精选 + A2 补到 4 道题（内容、操作指南）
- 自检：DEPLOYED，装了 39 个文件（22 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45465456013

### b20 · 2026-11-25 03:11
- main `4f6f438`，构建 `236f6e0`
- 新合并的 PR（自 b19 起）：
  - #106 tools/ios_sim_check.py：iPhone 清单在 iOS 模拟器里自动跑（发版和构建）
  - #105 r28 第 3 段：单词按每天时间封顶、回归补积压、词书背完推荐下一本（单词、开局和考试、操作指南）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45467345146

### b21 · 2026-11-25 03:20
- main `6d88b35`，构建 `14413ea`
- 新合并的 PR（自 b20 起）：
  - #107 r28 第 6 段：每周学习天数（默认按目的 + 周一建议调低）（今日和计划、后台和班级、操作指南）
- 自检：DEPLOYED，装了 6 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45469043615

### b22 · 2026-11-25 03:30
- main `a771fdd`，构建 `a5508a2`
- 新合并的 PR（自 b21 起）：
  - #109 主屏 App：键盘不再挡住对话/导入的按钮；切深色浅色后状态栏跟着变（开局和考试）
- 自检：DEPLOYED，装了 4 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45470855664

### b23 · 2026-11-25 03:41
- main `da3a81e`，构建 `ade1e38`
- 新合并的 PR（自 b22 起）：
  - #111 r28 第 6 段：「选方向和目标」页加「一周大概能学几天？」（开局和考试、操作指南）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 149/149，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45472606652

### b24 · 2026-11-25 03:50
- main `7a61d03`，构建 `7aacbde`
- 新合并的 PR（自 b23 起）：
  - #104 r28 第 1 段：按时间打包今日计划（今日和计划、开局和考试、后台和班级、操作指南）
- 自检：DEPLOYED，装了 12 个文件（1 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45474204709

### b25 · 2026-11-25 08:46
- main `967d787`，构建 `d832816`
- 新合并的 PR（自 b24 起）：
  - #113 发音：通义千问 Omni 的单词判断只作参考，不进错题本（单词、听和说、AI、操作指南）
- 自检：DEPLOYED，装了 6 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45520540948

### b26 · 2026-11-25 08:55
- main `1db9b7a`，构建 `50e03e2`
- 新合并的 PR（自 b25 起）：
  - #114 例句：不嘲笑、不带刻板印象；--review 复查旧例句并重写（单词）
- 自检：DEPLOYED，装了 4 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45521706643

### b27 · 2026-11-25 09:17
- main `f499b43`，构建 `166cb8c`
- 新合并的 PR（自 b26 起）：
  - #115 总账：正式版 r28 和当天的服务器设置（发版和构建）
  - #117 narration_pack：打包不带 Mac 扩展属性（--no-xattrs）（内容）
  - #116 跟读：拼写和连字符的差别不算问题（测试）
  - #108 r28 第 5 段：今日按学习目的挑第一篇，热点按水平给（今日和计划、操作指南）
  - #119 总账：语流朗读改成 22050 采样率（发版和构建）
- 自检：DEPLOYED，装了 6 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45524460741

### b28 · 2026-11-25 09:37
- main `fa14842`，构建 `d6bb088`
- 新合并的 PR（自 b27 起）：
  - #100 对话结尾补的摘要放成常量 SUMMARY_FILLER（测试）
- 自检：DEPLOYED，装了 3 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45526953849

### b29 · 2026-11-25 09:48
- main `1e26ad4`，构建 `bf9a3fb`
- 新合并的 PR（自 b28 起）：
  - #124 测试：并发的例句测试不依赖调用顺序（测试）
  - #122 隐私和数据：写明发信服务商（阿里云邮件推送为主，飞书备用）（操作指南）
  - #126 今日计划：超时那句放到按钮下面（修 main 的 ui phone-360）（今日和计划、操作指南）
- 自检：DEPLOYED，装了 4 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45528251944

### b30 · 2026-11-25 09:59
- main `f3ec33b`，构建 `2d0bc20`
- 新合并的 PR（自 b29 起）：
  - #120 跟读：只有录音里确实漏读或读错的词进错题本（听和说、操作指南）
  - #123 指南「交给哪家 AI」：对话、复述、雅思、跟读走 Omni（两个站都已切换），发音留在 Gemini；补上 CosyVoice 朗读（操作指南）
- 自检：DEPLOYED，装了 7 个文件（0 个新的）；轻量 e2e 145/147，没过：exam: AI adds questions/expressions to the import；db: no AI job failed，服务器报错 1
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45529545580

### b31 · 2026-11-25 10:08
- main `4127190`，构建 `15b4c60`
- 新合并的 PR（自 b30 起）：
  - #118 跟读和发音：shadow_eval.py（Omni 和 Gemini 听同一批录音比分数）；指南写上跟读、发音内测版改用 Omni（听和说、AI、内容、发版和构建）
- 自检：DEPLOYED，装了 7 个文件（2 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45530765949

### b32 · 2026-11-25 10:18
- main `7b7fe8c`，构建 `0c54902`
- 新合并的 PR（自 b31 起）：
  - #127 主屏 App：老师账号的首页显示 logo，返回按钮的文字跟着标签栏（开局和考试）
- 自检：DEPLOYED，装了 3 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45531882162

### b33 · 2026-11-25 10:28
- main `c0862db`，构建 `6bde788`
- 新合并的 PR（自 b32 起）：
  - #121 老师模式：一次性老师注册链接、老师首页建班、操作指南新增「老师」一章（开局和考试、后台和班级、操作指南）
- 自检：DEPLOYED，装了 14 个文件（1 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45533105876

### b34 · 2026-11-25 10:37
- main `fdd7197`，构建 `39d16ba`
- 新合并的 PR（自 b33 起）：
  - #110 r28 第 4 段：每天一份「考试小练」，整套阅读篇数按每天的时间（开局和考试、操作指南）
  - #112 r28 第 2 段：回归模式（欢迎回来）（今日和计划、操作指南）
  - #128 MSI 测试机：Tests 的分片可以跑在用户的 MSI 上，离线或太忙时自动退回 GitHub 的机器（默认不启用）（发版和构建）
  - #130 文字模型（百炼 DeepSeek）45 秒没回就交给 Gemini（FLOW_TEXT_TIMEOUT）（AI）
- 自检：ABORT_FETCH
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45534199497

### b35 · 2026-11-25 10:46
- main `187b90d`，构建 `938e5d7`
- 新合并的 PR（自 b34 起）：
  - #131 总账：jasa.hk 的 Flow 介绍页换成一分钟动画（发版和构建）
  - #86 发布状态的自检汇总带上失败原因（每项 ≤160 字），Actions 日志里直接能看到（发版和构建）
- 自检：DEPLOYED，装了 10 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45535216633

### b36 · 2026-11-25 10:57
- main `7343be8`，构建 `f893e07`
- 新合并的 PR（自 b35 起）：
  - #129 朗读：没有录音也用自然人声，不再悄悄换成机器声；长内容可以暂停、继续，并记住进度（单词、听和说、开局和考试、操作指南）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45536452349

### b37 · 2026-11-25 11:07
- main `59d700f`，构建 `24d4e24`
- 新合并的 PR（自 b36 起）：
  - #132 部署取文件清单：按提交编号 404 时改用构建标签再取（b34 被挡住的修复）（发版和构建）
- 自检：DEPLOYED，装了 2 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45537709058

### b38 · 2026-11-25 11:17
- main `9a8a0d4`，构建 `ade39db`
- 新合并的 PR（自 b37 起）：
  - #133 总账：正式版 r29 和内测版 b25–b35（发版和构建）
- 自检：DEPLOYED，装了 2 个文件（0 个新的）；轻量 e2e 147/148，没过：guard: 60 concurrent reads all 200 (0.8s)，服务器报错 1
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45538844045

### b39 · 2026-11-25 11:27
- main `81d44fd`，构建 `a00db23`
- 新合并的 PR（自 b38 起）：
  - #134 能力测评听力按句用自然人声读；考试结果里没认出的词用单词录音（开局和考试、操作指南）
  - #137 changelog.py：自动记录里写上自检失败的原因（发版和构建）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45539927938

### b40 · 2026-11-25 11:35
- main `70fbcdc`，构建 `82577bc`
- 新合并的 PR（自 b39 起）：
  - #138 App 外壳：iOS App（FlowiOS）里也当主屏 App，键盘交给 App（开局和考试、后台和班级）
- 自检：DEPLOYED，装了 3 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45540971829

### b41 · 2026-11-25 11:45
- main `20e57d4`，构建 `38cd16c`
- 新合并的 PR（自 b40 起）：
  - #139 单词：「认识」默认放右边（可在「我的」里换）；复习提醒可以只改下一次的时间（单词、今日和计划、开局和考试、后台和班级、操作指南、发版和构建）
  - #141 工作约定：用户 11:15 定的新协作规则（发版和构建）
- 自检：DEPLOYED，装了 8 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45542031763

### b42 · 2026-11-25 11:56
- main `307d234`，构建 `c28f6f9`
- 新合并的 PR（自 b41 起）：
  - #142 自检汇总带上 5xx 的接口（方法、路由、状态码），并发读取那项写出状态码（发版和构建）
- 自检：DEPLOYED，装了 2 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45543213099

### b43 · 2026-11-25 12:07
- main `8640943`，构建 `df51b7e`
- 新合并的 PR（自 b42 起）：
  - #144 add_mistake：同一个错同时记两次不再 500（INSERT … ON CONFLICT）（今日和计划）
  - #145 单词卡：同一个词同时存两次不再 500（检查和插入合成一条 upsert）（测试）
  - #146 工作约定：后台运行的程序不出声（发版和构建）
- 自检：DEPLOYED，装了 4 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45544409605

### b44 · 2026-11-25 12:21
- main `bbbdee8`，构建 `7bc3a0d`
- 新合并的 PR（自 b43 起）：
  - #149 复习提醒：App 里的通知说法按平台（iPhone、手机、Windows、Mac）（单词）
- 自检：DEPLOYED，装了 3 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45546043447

### b45 · 2026-11-25 12:33
- main `edacfbf`，构建 `3af2136`
- 新合并的 PR（自 b44 起）：
  - #150 CI：只改原生 App（ios/、android/、desktop/）的 PR 跳过网站测试和 UI（发版和构建）
- 自检：DEPLOYED，装了 2 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45547470440

### b46 · 2026-11-25 12:46
- main `5676f87`，构建 `1f5fa07`
- 新合并的 PR（自 b45 起）：
  - #151 tools：自动化打开的浏览器一律静音（工作约定第 9 条）（操作指南）
  - #153 App 外壳：桌面版（FlowDesktop）和有 window.FlowApp 的 App 也当主屏 App（开局和考试、后台和班级）
- 自检：DEPLOYED，装了 3 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45548768285

### b47 · 2026-11-25 13:00
- main `9875a69`，构建 `6f8879b`
- 新合并的 PR（自 b46 起）：
  - #156 ios_sim_check：朗读统一的自动测法，测试全程静音（网站其他）
  - #157 撤回 #151（浏览器静音），由语流 15 的 #154 统一做（操作指南）
- 自检：DEPLOYED，装了 2 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45550440215

### b48 · 2026-11-25 13:24
- main `cb72d6c`，构建 `d343412`
- 新合并的 PR（自 b47 起）：
  - #148 桌面版（Windows + macOS，Tauri 2）第一版（发版和构建）
  - #161 安卓 App：原生外壳加原生朗读、录音和复习提醒（android/）（网站其他）
  - #158 「AI 生成」标识组件：aiTag() / aiMark(note) 和统一样式（开局和考试、AI、发版和构建）
- 自检：DEPLOYED，装了 4 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45553004599

### b49 · 2026-11-25 13:46
- main `ec25af7`，构建 `c0afd83`
- 新合并的 PR（自 b48 起）：
  - #154 测试和截图工具启动的浏览器不发出声音（tools/quiet.py 的 silent()）（操作指南、发版和构建）
  - #167 安卓：模拟器测试一律静音，改签名的 PR 先问用户（只改 android/README.md）（网站其他）
  - #169 桌面版：bundle id 和 iOS 对齐（cn.flowlang.app / cn.flowlang.app.beta）（网站其他）
  - #140 单词读音：放不出来时先说原因，再用浏览器的声音读（听和说）
  - #143 单词：同一个学员同时开两次首页不再 500（新词插入可重复执行）（单词）
  - #166 桌面版：按共用约定对齐提醒规则和 FlowApp（docs/native-bridge.md）（网站其他）
  - #159 浏览器声音被 iOS 吞掉时不再「一下子读完」或卡住：重读一次，还不行就停在那句并写明原因（听和说、操作指南）
  - #168 复习提醒：App 通知开着时写「已开启」（安卓可关闭）；日历时长认 45、60 分钟（单词）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45555532132

### b50 · 2026-11-25 14:15
- main `59815d8`，构建 `9d74e73`
- 新合并的 PR（自 b49 起）：
  - #163 总账：App 安装包和宣传物料两节（发版和构建）
  - #165 AI 写的内容都标上「AI 生成」（13 处），加测试防止以后漏标（单词、听和说、今日和计划、开局和考试、操作指南）
  - #174 【等用户同意】CI：安卓 App 的构建、单元测试和 lint（.github/workflows/android.yml）（发版和构建）
  - #172 安卓 App 跟上共用约定 #162：items、audio-made、fail、提醒新规则、测试静音（只改 android/）（网站其他）
  - #160 内容页标「AI 生成」：文章页、卡片、连载、轻松读（今日和计划、内容、操作指南）
- 自检：DEPLOYED，装了 8 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45558630630

### b51 · 2026-11-25 14:48
- main `e935f04`，构建 `4695056`
- 新合并的 PR（自 b50 起）：
  - #170 App 外壳：网页因键盘变矮时把输入框和按钮滚进视野；App 里的内测版不弹「去正式版」（开局和考试）
  - #178 安卓：内测版用单独的签名钥匙，main 上 CI 自动打签名的内测包（用户已同意）（发版和构建）
  - #176 「AI 朗读」标识组件 aiVoice()（合成的声音用）（开局和考试）
  - #179 隐私：数据存放在香港的单独同意（注册单独勾选、老账号补一次、不同意就暂停、30 天后删除）（单词、今日和计划、开局和考试、后台和班级、操作指南）
  - #182 桌面版提醒：permission() 照约定；没同意数据存放（403 storage）时不排提醒（网站其他）
  - #187 安卓：账号没同意「数据存放在香港」时不排任何提醒（只改 android/）（网站其他）
  - #173 iOS App 内测版：原生外壳＋关键功能原生（ios/，附 iOS 的 CI）（发版和构建）
  - #162 App 桥约定：iOS、安卓、桌面共用一份（docs/native-bridge.md）（发版和构建）
  - #171 今日热点暂停：不再生成，已有的新闻热点留库不显示（听和说、今日和计划、内容、操作指南）
- 自检：DEPLOYED，装了 20 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45561792875

### b52 · 2026-11-25 15:02
- main `d544773`，构建 `3225817`
- 新合并的 PR（自 b51 起）：
  - #186 复习提醒：App 的「已开启」等异步的 permission() 再画（单词）
  - #188 起点小测、语法点页、混合练习标上「AI 生成」（开局和考试）
  - #181 总账：正式版 r30、内测版 b36–b48、Gemini 停用（发版和构建）
  - #189 打开文章就点播放全文时，新到的「今日」不再把正在读的全文停掉（开局和考试）
  - #190 单词和例句读音旁边标「AI 朗读」（单词、操作指南）
  - #191 三个 App 共用一份 FlowApp 包装：native/flowapp.js（iOS 先用上）（发版和构建）
- 自检：DEPLOYED，装了 5 个文件（0 个新的）；轻量 e2e 148/148，服务器报错 0
- 发布：GitHub Actions，https://github.com/Jasame/Flow/actions/runs/45564903144
