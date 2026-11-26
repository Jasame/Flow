# 语流 iOS App（内测）

原生外壳＋关键功能原生：SwiftUI 外壳里用 WKWebView 打开网站，网页一改 App 就跟着变；网页在 iPhone 上做不好的几件事由 App 原生来做：

| 原生做的事 | 为什么 | 代码 |
|---|---|---|
| 整篇朗读（听的「播放全文」、读的「伴读」） | 锁屏、来电、切到别的 App 时网页的声音会停，停了不能接着读 | `Flow/Audio/` |
| 录音（跟读、口语、发音、雅思） | 16 kHz 单声道 WAV，录完马上把声音还给扬声器 | `Flow/Record/` |
| 复习提醒（本地通知） | 网页只能靠邮件和日历 | `Flow/Remind/` |
| 登录保持、外链、下载、网页自己的弹窗 | WKWebView 默认不处理 | `Flow/Web/` |

最低 iOS 17，iPhone 和 iPad。不用任何第三方 SDK，不做跟踪，App 里没有任何密钥。

## 两个配置

| 配置 | 打开 | Bundle ID | 名字 | 图标 | 用在哪 |
|---|---|---|---|---|---|
| **Beta** | https://flow.jasa.hk（内测版） | `cn.flowlang.app.beta` | 语流内测 | 橙色底 `AppIcon-Beta` | 模拟器、UI 测试、免费账号装到自己手机、内测版的 TestFlight |
| **Release** | https://flowlang.cn（正式版） | `cn.flowlang.app` | 语流 | 绿色底 `AppIcon` | TestFlight 外部测试、App Store |

Bundle ID 用户 2026-11-25 已确认：正式版 `cn.flowlang.app`、内测版 `cn.flowlang.app.beta`（两个能同时装）。

两个 scheme：`Flow-Beta`（运行、测试、归档都用 Beta）和 `Flow-Release`（运行、归档用 Release）。网址、名字、Bundle ID、图标（`FLOW_APP_ICON`）在 `Config/Beta.xcconfig`、`Config/Release.xcconfig`。
内测版的图标是同一个声波 logo，底色从 #1f9d55 换成 #e8590c（用户 2026-11-25 选的「A · 橙色底」，网页、安卓、桌面的内测版一样），主屏上一眼分得开；`python3 ios/tools/make_app_icon.py --beta` 画它，只编进内测版。
自己的签名设置（开发团队、免费账号用的 Bundle ID）放在 `Config/Local.xcconfig`，这个文件不提交（见下面「装到自己的 iPhone」）。

## 构建和测试

需要 Xcode 27（项目用了「文件夹同步」，Xcode 16 以上能打开）。

```bash
open ios/Flow.xcodeproj
```

命令行：

```bash
cd ios
xcodebuild -project Flow.xcodeproj -scheme Flow-Beta -destination 'platform=iOS Simulator,name=iPhone 17e' build
xcodebuild -project Flow.xcodeproj -scheme Flow-Beta -destination 'platform=iOS Simulator,name=iPhone 17e' test
xcodebuild -project Flow.xcodeproj -scheme Flow-Beta -destination 'platform=iOS Simulator,name=iPad mini (A17 Pro)' test
```

- `FlowTests`（单元测试，不联网）：录音的 WAV、提醒排期的规矩（和服务器发邮件的规矩一样）、网页传来的播放参数、桥的 JSON。
- `FlowUITests`（要联网，打开内测版）：打开、登录页、App 播放一篇文章（暂停、继续、下一句、切到主屏幕后接着放）、控制中心、麦克风权限弹窗和 16 kHz WAV、复习提醒排期。截图在结果里：
  `xcrun xcresulttool export attachments --path <结果.xcresult> --output-path <文件夹>`
- 模拟器里测不了的（只有真机能测）：锁屏界面上的按钮（模拟器的控制中心没有「正在播放」）、来电打断后接着放、静音键、听筒还是扬声器。
- **测试不出声**（用户 2026-11-25：后台运行的应用不要播放系统声音）：启动参数 `-FlowMuteAudio YES` 让 App 的播放器和 iPhone 自带声音音量为 0，网页自己的 `<audio>`、Web Audio、朗读也静音，靠状态和事件判断有没有在放。UI 测试默认带上；自己用 simctl 启动时也加：`xcrun simctl launch booted cn.flowlang.app.beta -FlowMuteAudio YES`。真要听声音的测试先问用户。

### 用本地测试服务器试网页那一侧

Beta 版可以用环境变量 `FLOW_START_URL` 打开别的地址（Release 版不认）。本地测试服务器的地址（`localhost`）也在 App 允许的域名里：

```bash
python3 tools/ui_server.py 8771 /tmp/flow-ui-state &
SIMCTL_CHILD_FLOW_START_URL=http://localhost:8771 xcrun simctl launch booted cn.flowlang.app.beta
```

`FLOW_BRIDGE_TEST=1` 打开一页只有按钮的「桥测试」页（UI 测试用它）。Beta 版的网页可以用 Safari 的「开发」菜单检查，`tools/ios_sim_check.py` 那一套 Web Inspector 的办法在 App 里也能用（bundle id 换成 `cn.flowlang.app.beta`）。

## 网页和 App 之间的桥

App 在网页自己的脚本之前放好 `window.FlowApp`（只在本站的主框架里），User-Agent 末尾是 `FlowiOS/<版本>`。`FlowApp.platform` 是 `'ios'`；桌面版（语流 C3）用同一个 v1，`platform` 是 `'windows'` / `'macos'`，`has('audio')`、`has('rec')` 为 false。网页一律先判断 `window.FlowApp && FlowApp.has('audio' | 'rec' | 'notify')`，没有就照旧（Safari、主屏 App、微信都不受影响）。

- 网页 → App：`window.webkit.messageHandlers.flow.postMessage({cmd, args})`，返回 Promise。下面的 `FlowApp.xxx()` 都是它的包装。
- 包装是三个 App 共用的 `native/flowapp.js`（约定 docs/native-bridge.md 第 2 节）：Xcode 项目的 Shared 组直接引用它，构建时打进 App；iOS 自己只在前面加几行传输（`Bridge.transport`）。改它要跑 FlowTests（`testTheSharedWrapper`）。
- App → 网页：`FlowApp.on(type, fn)`，同时在 `window` 上发 `flowapp:<type>` 事件。
- 只接受本站主框架发来的消息（`Bridge.swift` 检查来源）。

### 整篇朗读 `FlowApp.audio`

`play(o)` → `{ok, state}`。o：

| 字段 | 意思 |
|---|---|
| `key` | `'listen:<id>'` / `'read:<id>'`，就是网页 PROG 的 key |
| `title` | 锁屏、控制中心显示「AI 朗读 · 标题」，第二行「语流 · 第 N / M 句」（《人工智能生成合成内容标识办法》：合成的声音在播放的地方写明） |
| `src` + `sentences` | 有录音：`src` 是相对本站的地址，`sentences` 是 `[[开始秒, 结束秒], …]`；`alt` 可选，另一条线路 |
| `texts` + `voice` + `pack` | 没有录音：App 自己调 `POST /api/next/tts`（带登录 cookie 和 `csrf`）一句一句读，先做后面两句；服务器给不了的那一句用 iPhone 自带的声音，原因放在 `note` |
| `from` / `at` | 从第几句 / 第几秒开始 |
| `loop`、`rep`、`gap` | 复读：一句一句放、每句几遍（0 = 一直）、每句前停多少毫秒（数字或每句一个） |
| `rate` | 语速 0.5–2 |

还有 `pause()`、`resume()`、`stop()`（记住读到哪）、`step(±1)`、`seek(i)`、`set({rep, gap, rate})`、`state()`、`progress(key)`。

事件 `audio`：`{key, state, i, n, t, note, why}`，state 是 `waiting`（录音还在加载、句子还在生成）/ `playing` / `paused` / `idle`；why 是 `user`、`remote`（锁屏、耳机按钮）、`interrupted`（来电、Siri、闹钟）、`route`（拔耳机）、`other`（别的声音或录音开始）、`ended`、`error`。
事件 `audio-tick`：`{key, i, t, at, rate}`，页面在前台时每秒 4 次，网页用 `NAR.locate(t)` 点亮句子和词。

规矩和网页的 LONG 一样：录音一口气放完（复读时一句一句）；暂停后录音从停下的那一秒接着放，服务器声音从那一句开头再读；来电结束、iOS 说可以接着放时自动接着放；拔耳机暂停；放完清掉进度。

### 录音 `FlowApp.rec`

`permission()`、`ask()`（只问一次系统权限）、`start({max, format})`、`stop()` → `{ok, mime_type, data, ms, bytes, cut}`、`cancel()`；事件 `rec`：`recording` / `done`（到 max 自己停）/ `cut`（来电打断，录到的部分还在）。
`format`：`wav`（默认，16 kHz 16 位单声道 PCM，44 字节文件头）或 `m4a`（AAC 16 kHz）；max 超过 40 秒默认用 m4a（WAV 每秒 32 KB，网页 `MIC.payload` 的上限是 1.4 MB，服务器 1.5 MB）。`stop()` 里的 `mime_type`、`data` 和网页 `MIC.payload(blob)` 一样；上传只能带这两项（服务器 `audio_validation` 要求正好是 `{mime_type, data}`），`ms`、`bytes`、`cut` 是给网页看的。
网页还没接桥的地方照旧用 getUserMedia；App 对本站自动同意，不会每次打开都再问一次（系统的麦克风权限照样要用户点一次「允许」）。

### 复习提醒 `FlowApp.notify`

`permission()`、`ask()`、`sync(r)`（r 是 `/api/next/vocab` 里的 `reminder`，可带 `app: false` 关掉 App 的提醒）、`pending()`、`off()`、`settings()`。
`permission()` 说的是 App 的提醒开没开（和安卓一样）：iOS 允许并且学员开着是 `'granted'`，没打开过或点了「关闭」是 `'undetermined'`，iOS 设置里关了是 `'denied'`；
`ask()` 为 true 就重新打开（iOS 的问题只问一次）。
App 打开、回到前台、切到后台、以及 iOS 每天叫醒它几次时，会用登录 cookie 拿一次 `/api/next/vocab`，排今后两周的通知：

- 时间按北京时间（和邮件、网页的 .ics 一样，服务器的 next_service.TZ）；
- 每天提醒的那个钟点，只在有词要复习的日子（今天看现在还剩多少，包括超出当天份额的；后面看服务器的 forecast 累计到那天——没复习的词第二天还在——加上词书没学完时每天的新词；再往后有词就提醒）；App 每次打开、切到后台都会重排，复习完的日子就撤掉；
- 「这次什么时候复习」（`once`）：在它之前不排每天的那条；到点那天有词才提醒，提醒过的那天不再排每天那条；过了回到每天——和服务器发邮件的规矩一样；
- 网页里「加到手机日历」的链接在 App 里会先问「用 App 通知提醒 / 加到系统日历」；选了「我的 → 每天提醒」那条，就每天在那个钟点提醒今天的学习（这条不用登录）。
- 点通知打开复习页（`#/review`）或今日（`#/`），App 没在运行时也一样。退出登录以后不再提醒复习单词。
- 账号还没同意「数据存放在香港」时（老账号回答之前、选了不同意而暂停的账号；网站对登录后的请求一律回 403，code `storage`）：和网站一样什么提醒都不排，今天的学习那条也不排；钟点留着，同意以后下次刷新自己排回来。朗读不一样：`/api/next/tts` 对这种账号按游客回答（存好的句子照给，新合成的拿不到），App 照游客的做法，拿不到的句子用 iPhone 自带的声音。

### 主题色

网页「我的 → 外观」可以选松绿（默认）或靛蓝（#282，html 的 `data-accent`）。App 用一段脚本看着它，变了就发 `app.accent`，App 自己画的对话框按钮、下拉刷新、出错页的「再试一次」跟着换色；logo、启动图、「AI 朗读」标识不变。上次的选择记在本机，下次打开先用它。

## iOS 专属功能（我的 → 设置 → iOS 专属功能）

用户 2026-11-25 要的「对 iOS 27 的特性做特殊优化，可以选择开启与关闭」（方案在共享笔记 ios-27-features.md，按组做）。网页「我的 → 设置」最后一行
在 `FlowApp.has('settings')` 时出现（语流 B9），点了调 `FlowApp.call('app.settings')`，App 盖上一页原生的 SwiftUI 设置（`Flow/Features/`）。
开关只存在这台手机上（UserDefaults `feature.<id>`），系统版本不够的不显示。第一组「锁屏听读」：

| 开关 | 默认 | 做什么 | 代码 |
|---|---|---|---|
| 锁屏上的学习按钮（iOS 27） | 开 | 锁屏、灵动岛、控制中心上除了播放暂停、上一句下一句，还能调语速 0.75× / 1× / 1.25×、单句循环、退回 5 秒 | `Audio/LockScreen27.swift`（NowPlaying 框架的 MediaSession） |
| 来电以后接着放 | 开 | 来电、Siri、闹钟以后系统说可以就接着放（iOS 27 用新的 resumptionRecommendation）；关了就停在那里 | `LongPlayer.resumption` |
| 离线朗读包 | 关 | 连着 Wi-Fi 时把今天要学的 3 篇录音存到手机上（和网页「存到手机」同样三篇），没网时 App 也能放；7 天删，关掉全删 | `Audio/Packs.swift` |
| 复习时的轻触震动（第二组） | 开 | 网页调 `app.haptic`（复习打分、做题答对答错）时手机轻轻一震 | `Features/Haptics.swift` |
| 省电时少做事（第二组） | 开 | 低电量模式或 iOS 27 提示省资源时：朗读少提前做一句、离线包不在前台下、网页少预载（`frugal`） | `Features/Frugal.swift` |
| 复习进度的实时活动（第三组） | 关 | 复习单词时锁屏和灵动岛上显示「12 / 30」（网页调 `activity.review`） | `Features/ReviewActivities.swift`、`FlowWidgets/ReviewActivityWidget.swift` |
| 在系统搜索里找生词（第四组） | 关 | 学员自己的单词和表达进 iPhone 的搜索，点了打开 `#/cards/find/<词>`（B2 的 `/api/next/cards/index`） | `Features/WordSearch.swift` |
| 快捷指令和 Siri（第四组） | 开 | 「语流开始复习」「语流还有多少词要复习」「用语流打开今天这篇」；关了 Siri 就说在哪里打开 | `Features/Intents.swift` |

- 模拟器的控制中心没有「正在播放」，锁屏按钮在测试里通过桥测试页的「锁屏 1.25× / 锁屏单句循环 / 锁屏退回 5 秒」按（Beta 才有的 `audio.remote`），真的锁屏要在手机上看。
- 没网时这篇的录音 App 里又没存：`play` 回 `why: 'offline'`，网页自己放它存的那份（以前 App 会报「录音没加载出来」）。
- 第二组的外观部分不设开关、跟着系统走：App 自己画的出错页在 iOS 26 起用系统的玻璃按钮；设置页本来就是系统的样子。
- 第三组「不打开 App 也能学」：小组件和控制中心按钮不设开关（学员自己加、自己删就是开关），设置页那一组下面写了怎么加。
  - 工程里多了一个扩展 `FlowWidgets`（WidgetKit：「今天」小组件、实时活动、控制中心按钮）和一个两边共用的文件夹 `Common/`（`TodayCard`：小组件显示的数字、App 自己的链接）。
  - App Group 是 `group.$(FLOW_BUNDLE_ID)`（`Config/Shared.xcconfig`），免费签名的 `.me` 也有自己的一个；链接的 scheme：正式版 `yuliu`，内测版 `yuliu-beta`。
  - 小组件的数字由 App 写：回到前台和后台刷新提醒时（`WidgetsFeed`，今日好句和今天这篇最多半小时问一次 `/api/next/home`）。
  - 截图用：内测版启动参数 `-FlowWidgetSample YES` 写一份样例数字（不会被真的覆盖）。
- 第四组「Siri 和专注模式」：App Intents 写在 App 里（`Features/Intents.swift`，没有新扩展，免费签名也能用）。
  - Siri 的说法是中文的（开发语言 zh-Hans），`\(.applicationName)` 在正式版是「语流」、内测版是「语流内测」。说出数字的那一句要解锁手机。
  - 专注模式过滤 `ReminderFocusFilter` 不设开关：学员在系统设置里给某个专注模式加上才起作用。通知带 `filterCriteria`（`review` / `plan`），系统按它过滤。
  - 红线：不用 `IndexedEntity`（Apple Intelligence 的语义索引）、助手模式（AssistantSchemas）和 model delegation。
  - 在系统搜索里找生词（第 7 项，默认关）：B2 的接口带 `?v=`，没变就不重建索引；截图用内测版启动参数 `-FlowWordSearchSample YES` 放三个样例词。
  - 钥匙串：没签名的模拟器包（`CODE_SIGNING_ALLOWED=NO`，CI 也是）根本用不了钥匙串（-34018），所以 `CookieKeychainTests` 在那里自动跳过；要真测就用签名的包跑（`CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM=`）。
  - 模拟器上的坑：没签名的包（`CODE_SIGNING_ALLOWED=NO`）装到放了语流控制中心按钮的模拟器时，系统的 AppIntentsLiveEntityService 会崩，连带 FlowWidgets 崩（WidgetKit「Can't create CHSIntentReference」）；签名的包（`CODE_SIGN_IDENTITY=-`）不会，真机也不会。测试跑着时别往放了按钮的模拟器装没签名的包：XCTest 会把这次崩记到正在跑的那个测试头上。

## 隐私

- `Flow/PrivacyInfo.xcprivacy`：不跟踪、没有跟踪域名；收集的数据只为 App 功能：邮箱和用户名（账号）、录音（批改用，不留存）、学员自己写的内容、问题反馈和截图；页面出错和打开快慢的记录不带账号；用到的「需要说明理由」的 API：UserDefaults（CA92.1，只读写 App 自己的设置）、文件时间（C617.1，删掉 App 自己缓存里 7 天前的朗读文件）。
- 权限：麦克风（只在点录音的几秒打开；切出 App 时录音就停）、相机（只在问题反馈里选「拍照」时）、通知（复习提醒，可以随时在系统设置里关）。日历不需要权限（用系统自带的添加界面）。
- 登录 cookie 在 WebKit 自己的存储里，另外在钥匙串里存一份（只在这台设备，不进备份），防止刚登录就被关掉时丢失；退出登录时一起删掉。删掉 App 再装上时，第一次打开会先清掉钥匙串里的那份，不会登进上一个人的账号。
- 网页允许的域名（`WKAppBoundDomains`）只有本站：服务工作线程、JS 桥、cookie 都只在本站有效，别的网站一律用系统浏览器打开。
- 学员的数据存放在香港的服务器上：注册时单独勾选同意，老账号打开时先补一个同意，不同意的账号暂停、30 天后删除（网站一侧，语流 B6）。App 里打开的就是网站，所以 App 不用另外问；App 自己也不另存学习数据，本机只有登录 cookie（钥匙串里一份：`flow_session` 和「切换账号」记住的其他账号 `flow_more`，网站清掉了就删）、提醒的排期和朗读缓存。切换账号、退出登录时（`account.changed`），上一个账号的提醒、小组件数字、实时活动、朗读进度和系统搜索里的生词马上清掉。
- 「iOS 专属功能」：开关状态只在本机。小组件的数字（今天要复习几个词、新词、分钟数、今天这篇的标题、今日好句）存在 App 和小组件共用的 App Group 里，只在这台手机上，每次刷新覆盖，没登录时不写任何人的词。「离线朗读包」开了才有：今天要学的几篇文章的录音（网站公开的朗读文件，不含个人数据），存在 App 的缓存目录（Library/Caches/packs，不进 iCloud 备份，空间不够时系统可能先清），存满 7 天删，关掉开关全删；只用 Wi-Fi 下载。
- 在系统搜索里找生词（开了才有）：你的单词和表达、释义第一段，存在这台手机的系统搜索索引里，不上传；退出登录、关掉开关就删。
- Siri：问「语流还有多少词要复习」时，App 把提醒用的那几个数（复习几个、新词几个、几分钟）交给 Siri 读出来，别的不给；另外两句只打开页面。专注模式的过滤选择存在系统设置里，App 不存。

## 装到自己的 iPhone（免费账号，7 天有效）

给用户看的分步说明在 [INSTALL.zh.md](INSTALL.zh.md)。要点：

1. Xcode → 设置 → Apple 账户，登录自己的 Apple ID（用户自己登录）。
2. 运行 `sh ios/tools/personal-team.sh <缩写>`：把 Xcode 里已登录的 Personal Team 和 `cn.flowlang.app.beta.<缩写>` 写进 `Config/Local.xcconfig`（不提交）。
   不在 Xcode 的 Signing 界面里改，是为了不改动项目文件（以后 `git pull` 不冲突），也免得免费账号占用以后付费账号要用的 `cn.flowlang.app.beta`。这个文件只给 Beta 换 Bundle ID，Release 永远是 `cn.flowlang.app`；免费账号只用 `Flow-Beta`。
3. 数据线连手机，手机上打开「开发者模式」，选手机，运行。第一次要在手机「设置 → 通用 → VPN 与设备管理」里信任自己的开发者证书。
4. 7 天后 App 打不开了，连上电脑再运行一次就好。

## 以后：TestFlight 和 App Store

开发者账号（Apple Developer Program，每年 99 美元，个人或公司，要实名）办好以后：

1. App Store Connect 里新建 App：Bundle ID `cn.flowlang.app`（正式版）；要给自己测内测版，再建一个 `cn.flowlang.app.beta`。
2. Xcode 里 Team 换成付费团队，scheme 选 `Flow-Release`（或 `Flow-Beta`）→ Product → Archive → Distribute App → App Store Connect。
3. TestFlight：先「内部测试」（自己和团队成员，不用审核）；顺了再开「外部测试」给试用同学（第一次要过 Beta 审核，最多 1 万人，用公开链接邀请）。
4. 上 App Store 前要准备：隐私政策网址（用操作指南的隐私一章 https://flowlang.cn/#/guide/privacy；语流 B6 在外部测试前把「语流 iPhone App（内测）」一节放进去，文字已审好，在共享笔记 area-console-classes.md）、App 隐私问卷（和 PrivacyInfo.xcprivacy 一致）、截图、年龄分级（有未满 14 岁的学员，见网站的隐私章节）、审核用的测试账号。凡是问到数据存在哪里的地方（隐私政策、App 备案、以后别的表），都写「存放在香港」，和网站那个单独同意一致；Apple 的隐私问卷本身只问收集哪些数据、关不关联账号、跟不跟踪。
5. **App Store 中国区要先办 App 备案**（ICP 备案主体名下，在云服务商那里提交 App 名称、Bundle ID、签名公钥信息），拿到备案号填进 App Store Connect 才能在中国区上架。现在不用办，上架前再办。备案一般通过境内的接入服务商办，服务器在香港时能不能办、怎么办，要先问清楚，和「数据要不要迁回境内」一起定。

只有开发者账号办好以后才能做的：TestFlight（内部和外部）、App Store 上架、超过 7 天的真机安装、给试用同学装、推送通知（现在的提醒是本地通知，不需要推送）。

## 还没做的

- 网页一侧接桥：已在 main（#152 整篇朗读交给 App，#164 录音用 App，#299 句子地址和系统声音的说法）。
- 锁屏上改的语速、单句循环，网页的「语速」「复读」按钮还不跟着变（`audio` 事件已经带 `rate`、`rep`、`loop`，网页一侧由语流 B3 接）。
- 「本机快速检查（离线）」：草稿 #376，等 D2、用户和真机。
- 网页一侧：复习页的震动（语流 B2，分支 review-split：翻面 select，评分按结果 success / tap / warning，不用 error）、PRELOAD.frugal() 算上 App 的 `frugal`（语流 B3）。
- 安卓的 `haptic`、`frugal`：语流 C2 已想好做法（performHapticFeedback；PowerManager.isPowerSaveMode），等用户排优先级。
- 复习提醒：网页一侧已在 main（#139「到点用 App 通知提醒」和 `FlowApp.notify.sync()`，#149 按 `FlowApp.platform` 换说法）。
- 04-home-app.js 认 `FlowiOS`：已在 main（语流 B5，0f6fc09：App 里也有返回按钮；键盘和深浅色交给 App）。
- 操作指南「隐私和数据」一章加 App 用到的权限：语流 B6 已审好文字，TestFlight 外部测试前由它放进 guide.md（先告诉它一声）。
