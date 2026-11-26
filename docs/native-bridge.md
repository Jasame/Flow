# 语流 App 和网页之间的桥（FlowApp v1）

iOS（语流 C1）、安卓（语流 C2）、桌面 Windows、macOS 和 Linux（语流 C3）、鸿蒙（语流 C4）共用这一份约定。网页只认一个入口 `window.FlowApp`，
命令、事件、字段、错误码只在这里写一次；各平台怎么实现写在最后一节。

- 约定由语流 C1（iOS）牵头改；各平台的小节由各自的会话写（会话名对照见共享笔记 session-names.md）。要改共用部分，先在 PR 里提，各平台都同意再合。
- 网页一侧用桥的地方：声音和录音（语流 B3，01-audio-offline.js、70-learner.js），提醒（语流 B2，50-words.js），
  App 外壳的样子（语流 B5，04-home-app.js）。

## 1. 网页怎么知道自己在 App 里

- **功能一律看 `window.FlowApp`**：App 在网页自己的脚本之前放好它（document start，只在本站的主框架里）。
  先判断 `window.FlowApp && FlowApp.has('<能力>')`，没有就照网页原来的做法。Safari、主屏 App、微信、电脑浏览器都不受影响。
- **User-Agent 末尾**：`FlowiOS/<版本>`、`FlowAndroid/<版本>`、`FlowDesktop/<版本> (Windows)`、`(macOS)` 或 `(Linux)`、`FlowHarmony/<版本>`。
  UA 只用来决定外壳的样子（04-home-app.js：返回按钮、不显示「添加到桌面」），写成 `/Flow(iOS|Android|Desktop|Harmony)\//`（#318）。不要靠 UA 判断能力。
- `FlowApp.platform`：`'ios'` | `'android'` | `'windows'` | `'macos'` | `'linux'` | `'harmony'`。说法跟着平台走，比如通知、麦克风权限去哪里打开：

| platform | 通知 | 麦克风 |
|---|---|---|
| ios | 「设置 → 语流 → 通知」 | 「设置 → 语流 → 麦克风」 |
| android | 「设置 → 应用 → 语流 → 通知」 | 「设置 → 应用 → 语流 → 权限 → 麦克风」 |
| windows | 「设置 → 系统 → 通知」 | 「设置 → 隐私和安全性 → 麦克风」 |
| macos | 「系统设置 → 通知」 | 「系统设置 → 隐私与安全性 → 麦克风」 |
| linux | 「系统设置里的通知」 | 「系统设置 → 隐私 → 麦克风」 |
| harmony | 「设置 → 应用和元服务 → 语流 → 通知」 | 「设置 → 应用和元服务 → 语流 → 麦克风」 |

- linux 的说法：各个桌面叫法不一样，通知就笼统写；麦克风这一项是 GNOME 的，KDE 一般不用设。
- harmony 的说法：HarmonyOS 5.0.1 模拟器上核对过，App 自己那一页上「通知」「麦克风」就在第一屏。网页 70-learner.js 的 APP_MIC 还没有 harmony，会退回 iPhone 的说法，要补一项（B3）。

- 其他字段：`FlowApp.v`（桥的版本，现在 1）、`FlowApp.app`（App 版本）、`FlowApp.build`、`FlowApp.beta`（打开的是内测版）。

## 2. 共同的形状

- 调用：`FlowApp.<块>.<命令>(参数)` 返回 Promise。预料之中的失败（没权限、正在录音……）照常 resolve，结果里 `ok: false` 加 `why`；
  只有传输出错、不在本站、命令不存在时才 reject。
  - 网页一律 `await`（或 `.then`）以后再用结果，不能直接拿返回值比较（`FlowApp.notify.permission() === 'granted'` 在每个 App 里都是 false）。
    测试里假的 FlowApp 也要返回 Promise，和真的一样。
- 事件：`FlowApp.on(type, fn)` 返回退订函数，`FlowApp.off(type, fn)` 也行；同时在 `window` 上发 `flowapp:<type>` 事件（detail 同参数）。
- 能力 `FlowApp.has(名字)`：

| 能力 | 意思 | iOS | 安卓 | 桌面（Windows、macOS、Linux） | 鸿蒙 |
|---|---|---|---|---|---|
| `audio` | 整篇朗读交给 App 放（锁屏、来电、后台） | 有 | 有 | 没有 | 有 |
| `rec` | 录音由 App 录 | 有 | 有 | 没有（网页 getUserMedia） | 有 |
| `notify` | 复习提醒用本地通知 | 有 | 有 | 有 | 没有（等华为开通代理提醒，见第 10 节鸿蒙） |
| `media` | 网页自己放声音，App 把 navigator.mediaSession 交给系统（媒体键、「正在播放」） | 没有 | 没有 | 有（Linux 走 MPRIS） | 没有 |
| `speech` | App 替网页补上 speechSynthesis（浏览器声音） | 没有 | 有 | 没有 | 没有（不接系统的 Core Speech Kit） |
| `settings` | App 自己的「专属功能」设置页：「我的 → 设置」最后一行，点了调 `FlowApp.call('app.settings')` | 有 | 没有 | 没有 | 没有 |
| `haptic` | 让手机轻轻一震：`FlowApp.call('app.haptic', {kind})`（见下） | 有 | 没有 | 没有 | 没有 |
| `frugal` | 系统要省着用（低电量模式、iOS 27 的省资源提示）：网页少预载 | 有 | 没有 | 没有 | 没有 |
| `activity` | 复习进度显示在锁屏和灵动岛上（实时活动）：`activity.review` / `activity.end`（见下） | 有 | 没有 | 没有 | 没有 |
| `privacy` | 第一次打开时的同意和「基本模式」、撤回同意、权限管理页、APP 备案号（命令写在第 10 节安卓一节） | 没有 | 有 | 没有 | 有（和安卓同一套） |

- 一个 App 在回到前台、网页重新加载以后，会把正在放的状态再发一次（`audio` 事件），网页不用猜。网页可见时也可以调 `FlowApp.call('app.visible')` 让它重发。
- `FlowApp.call('hello')` → `{v, app, build, platform, features}`。
- `FlowApp.call('app.settings')` → `{ok}`：打开 App 自己的「专属功能」页（iOS：「iOS 专属功能」，原生页，开关只存在这台手机上）。`ok: false` 是现在打不开（App 在后台）。
  `FlowApp.call('app.features')` → `{<功能>: true/false}`：这台手机有哪几项、开没开（iOS 的 id：`lock-study` `smart-resume` `offline-packs` `haptics` `frugal` `review-activity` `siri` `word-search`）。网页现在不用它，留给以后按开关改说法。
- `FlowApp.call('app.haptic', {kind})` → `{ok}`：`kind` 是 `tap`（轻点：打分、选一个选项）、`select`（换了一个选择）、`success`（答对、认识）、`warning`（模糊、半对）、`error`（答错）。
  学员在 App 的设置里关了「复习时的轻触震动」就回 `ok: false`，什么都不做；网页不用自己判断开关，照常调。iOS 本来就没有 navigator.vibrate，网页在浏览器里不用补。
- `FlowApp.call('activity.review', {done, total})` → `{ok, why?}`：单词复习每评一张调一次，锁屏和灵动岛上显示「复习单词 done / total」；`FlowApp.call('activity.end', {done?, total?})` 复习完或离开复习页时调，最后的数字留一分钟再消失。学员在 App 设置里没打开「复习进度的实时活动」（默认关）时回 `{ok: false, why: 'off'}`，系统不让（关了实时活动、App 不在前台）回 `why: 'denied'`；网页照常调，不用自己判断。
- `FlowApp.call('app.frugal')` → `{on}`，变了发 `frugal` 事件 `{on}`（回到前台也会再看一次）。`on` 为 true 时网页少预载（PRELOAD.frugal() 也算它）：不提前存今天的文章、不预取下一篇。
  学员在 App 的设置里关了「省电时少做事」就一直是 false。
- 安卓的返回键、鸿蒙的侧滑返回：App 先在 `window` 上发可以取消的 `flowapp:back` 事件，网页 `preventDefault()` 就算处理了；没人处理时 App 关掉开着的 sheet，再回到上一页。iOS、桌面没有这个键，不发。

### 共用的包装 `native/flowapp.js`

上面这些（`FlowApp` 的字段、`has`、`call`、`on`/`off`/`_emit`、`audio`/`rec`/`notify` 三块、html 的 `flow-<platform>`、回到前台调 `app.visible`）
只写在一个文件里：`native/flowapp.js`。每个 App 原样放进网页，在它前面只放自己的几行传输：

```js
window.__flowAppTransport = {
  cfg: { v, app, build, beta, platform, features },  // App 自己的情况
  send(cmd, args),          // 一条命令交给 App，回答可以是值或 Promise（包装都变成 Promise）
  extend(FlowApp, call),    // 可以不给：本平台多出来的成员，在冻结之前加（安卓的 _back）
  ready(FlowApp),           // 可以不给：window.FlowApp 放好以后（安卓收端口的消息、发 hello）
};
```

- 包装读完就把 `__flowAppTransport` 从 window 上删掉；已经有 `window.FlowApp` 时什么都不做。
- iOS：传输是 `webkit.messageHandlers.flow.postMessage({cmd, args})`（Bridge.swift 的 `transport`），文件由 Xcode 项目的 Shared 组直接打进 App；
  单元测试在 JavaScriptCore 里跑这个文件（FlowTests 的 `testTheSharedWrapper`、`testTheIOSTransport`）。
- 安卓：打包时从 `native/` 复制进 assets（语流 C2）。鸿蒙：每次构建由 `harmony/entry/hvigorfile.ts` 复制进 rawfile（语流 C4）。桌面：要不要用，由语流 C3 定。
- 静音开关、安卓的 speechSynthesis、桌面的 mediaSession 这些各平台自己的东西，不放进这个文件。
- 改这个文件就是所有 App 一起改：PR 里说明，iOS 的单元测试要过，安卓、桌面、鸿蒙再各自打包试一次。

## 3. 整篇朗读 `audio`

听的「播放全文」、读的「伴读」（网页的 LONG）。短声音（单词、例句、单句、AI 回复）还在网页里放，不走桥。

### 命令

`play(o)` → `{ok: true, state}` 或 `{ok: false, why, message?}`。`ok: false` 时网页自己放（NATIVE.fail，和 Safari 一样）：
`why: 'session'` 是系统不给声音（正在通话）；`why: 'offline'` 是没网、这篇的录音 App 里又没存（iOS 的「离线朗读包」没开或还没存），网页从自己存的那份放（存到手机、sw.js）。o：

| 字段 | 意思 |
|---|---|
| `key` | `'listen:<id>'` / `'read:<id>'`（网页 PROG 的 key；`''` 不记进度） |
| `title` | 锁屏、通知栏显示的标题，带「AI 朗读」（见下面的规矩） |
| `src` + `sentences` (+ `alt`) | 有录音（Kokoro）：相对本站的地址、`[[开始秒, 结束秒], …]`；`alt` 是另一条线路，可选 |
| `items` + `voice` + `pack` | 没有录音：`[{text, url}]`，已经知道的地址网页直接给（SV 地址簿），不知道的 `url: null`，App 自己调 `POST /api/next/tts {text, voice, pack}` |
| `csrf` | 网页的 CSRF token（App 调 /api/next/tts 时带上） |
| `from` / `at` | 从第几句 / 第几秒开始 |
| `loop`、`rep`、`gap` | 复读：有录音时也一句一句放；每句几遍（0 = 一直重复）；`gap[i]` 是第 i 句**每次读完之后**停的毫秒数（「留时间跟说」，按刚读完的那句算；复读的每一遍之后都停，整篇最后一句之后不停）；也可以给一个数，每句一样 |
| `rate` | 语速 0.5–2 |

旧写法 `texts: [句子]` 等于 `items` 里 url 都是 null，App 照样认。

`pause()`、`resume()`、`stop()`（停下，进度留着）、`step(±1)`、`seek(i)`、`set({rate, rep, gap})`（播放中改语速、复读，立刻生效）、
`state()` → `{key, state, i, n, t, title, rate, rep, loop}`、`progress(key)` → `{i, t, at}`、读完了是 `{ended: true, at}`，没有记录是 null（`at` 是毫秒时间戳）。

### 事件

- `audio`：`{key, state, i, n, t, why, fail, rate, rep, loop}`
  - `rate`、`rep`、`loop`：App 现在用的语速和复读。一般就是网页给的；iOS 27 锁屏上可以改语速（0.75× / 1× / 1.25×）和「单句循环」（`rep: 0, loop: true`），改了以后下一个 `audio` 带过来（why = remote）。
    网页之后再调 `set({rate, rep, gap})`（学员在页面上改了），以网页的为准，锁屏的单句循环也就结束了。
  - `state`：`waiting`（录音还在加载、句子还在生成）、`playing`、`paused`、`idle`。
  - `why`：`user`（网页叫的）、`remote`（锁屏、耳机、车机）、`interrupted`（来电、Siri、闹钟）、`route`（耳机拔了）、`other`（别的声音或录音开始了）、
    `ended`（读完）、`error`（加载失败）、`state`（回到前台重发的）。
  - **每换一句都发一次 `audio`**，所以网页靠它就能更新当前句、高亮、自动滚动和播放条的「第 N 句」。
  - `fail`：这一句退回系统自带的声音时给 `{code, server}`。`code` 和网页的 SV 一样：`off` `cap` `import_cap` `busy` `guest` `store` `gateway` `offline` `net` `slow`；
    `server` 是服务器回的 error 原文。那句话由网页的 `SV.why(fail)` 写，全站一个说法，同一个原因只说一次。App 不自己写原因。
  - `off`、`cap`：这篇剩下的句子都用系统自带的声音，不再问服务器；别的原因只管这一句。
  - 还没同意「数据存放在香港」的账号：`/api/next/tts` 对游客也开放，所以不回 403 `storage`，按游客回答（存好的句子照给，新合成的是 `guest`）。
- `audio-tick`：`{key, i, t, at, rate}`，页面在前台时每秒 4 次。网页用 `NAR.locate(t)` 点亮词，两次之间按 `at` 和 `rate` 插值。
- `audio-made`：`{key, i, url}`，App 做出来的新句子地址，网页记进 SV 地址簿（同一句不做两次，Safari 里也能用）。

### 规矩（和网页的 LONG 一样）

- 暂停后继续：录音从停下的那一秒接着放；按句朗读从停下那一句的开头再读。
- 来电、Siri 打断：暂停（why = interrupted）；系统说可以接着放，就自己接着放（iOS 学员可以在「iOS 专属功能」里关掉「来电以后接着放」，关了就停在那里）。耳机拔了暂停。
- 别的声音或录音开始：网页先调 `pause()`（LONG.other），App 那边自己也会停（why = other）。
- 加载失败：暂停（why = error）；再点继续会重新加载，从停下的地方接着放。有 `alt` 时先换线路，接着从那一秒放。
- 进度：网页 PROG 和 App 各存一份。页面打开、回到前台时，网页读 `progress(key)`，和 PROG 比 `at`，用新的那份；新的那份是 `ended` 就清掉 PROG。
  `idle` 且 `why = ended`：两边都清（App 留一个 ended 记号，给错过这个事件的页面看）；其他的 `idle`：两边都记。
- 继续时 iOS 不给声音（正在通话、正在录音）：App 发 `audio` `{state: 'paused', why: 'interrupted'}`，网页照它显示。
- App 在放的时候，网页不 claim navigator.mediaSession（锁屏只有 App 一家）；播放条 MINI 照常显示，暂停、继续、✕ 走桥。
- App 自己画的播放信息（锁屏、控制中心、灵动岛、通知栏的「正在播放」）：标题或第二行写上「AI 朗读」。iOS 写在标题前（「AI 朗读 · 今日好句」，第几句放第二行），安卓写在第二行（「AI 朗读 · 第 n / N 句」）。
  《人工智能生成合成内容标识办法》要求合成的声音在播放的地方写明；语流现在没有真人录音，Kokoro 录音、CosyVoice、系统自带的声音都算（语流 B7）。
- 系统自带声音按 voice 挑英音（`uk-*`）、美音，语速跟 `rate`。

## 4. 录音 `rec`

- `permission()` → `'granted'` | `'denied'` | `'undetermined'`；`ask()` → true/false（系统的问题只问一次，要在点按里调）。
- `start({max, format})` → `{ok: true, format, max}` 或 `{ok: false, why, message}`，why：`denied` `busy` `error` `cancelled`。
  - `format`：`wav`（默认：16 kHz 单声道 16 位 PCM，44 字节文件头）或 `m4a`（AAC 16 kHz）。
  - **max 超过 40 秒默认用 m4a**：WAV 每秒 32 KB，网页 `MIC.payload` 的上限是 1.4 MB（服务器 1.5 MB），40 秒的 WAV 是 1,280,044 字节。
- `stop()` → `{ok: true, mime_type, data, ms, bytes, cut}` 或 `{ok: false, why: 'none'}`。`mime_type`、`data`（base64）和 `MIC.payload(blob)` 一样；
  **上传只带这两项**（服务器 audio_validation 要求正好是 `{mime_type, data}`），`ms`、`bytes`、`cut` 是给网页看的。
  录音还没开始（还在等权限）就 stop，这次录音不再开始。
- `cancel()`。事件 `rec`：`{state: 'recording' | 'done' | 'cut', ms}`：到 max 自己停是 done；来电打断、或者 App 切到后台是 cut（录到的部分还在，stop() 照样拿到）。
  麦克风只在学员看着 App 时开：切走就停，不会在后台接着录。
- App 里网页不切 navigator.audioSession（会话由 App 切）；第一次的说明卡不写「每次重新打开都会再问」。

## 5. 复习提醒 `notify`

- `permission()` → `'granted'` | `'denied'` | `'undetermined'` | `'provisional'`；`ask()` → true/false；`off()`：关掉 App 的提醒（等于 `sync({app: false})`）；`settings()`：打开系统里这个 App 的通知设置。
  - `permission()` 说的是 App 的提醒开没开，不只是系统给没给：系统允许并且学员开着是 `'granted'`；学员还没打开、或者点了「关闭」（`off()`）是 `'undetermined'`；
    系统里关了是 `'denied'`；`'provisional'` 只有 iOS 有。网页「已开启」那一行就看它是不是 `'granted'`。
  - `ask()` 为 true 就是学员打开了 App 的提醒，关过的也重新打开（系统的问题只问一次，后面直接给 true）。
- `sync(r)`：r 是 `/api/next/vocab` 的 `reminder`（`{hour, once, enabled, has_email}`）加上 `forecast`。`{app: false}` 或 `sync(null)`：关掉 App 的提醒。
  网页在改了提醒（每天的钟点、这次什么时候复习、取消这次）以后、学员点「到点用 App 通知提醒」以后调用。
- `pending()` → `[{id, at, title, body}]`。
- 规矩：
  - `enabled` 只管邮件，App 通知不看它：学员点了「到点用 App 通知提醒」（ask() 为 true）就排。
  - 时间按北京时间（和邮件、网页的 .ics 一样，next_service.TZ）。
  - 每天提醒的钟点，只在有词要复习的日子：今天看现在还剩多少（包括超出当天份额的 `later`）；后面几天看 forecast 累计到那天（没复习的词第二天还在），
    加上词书没背完时每天的新词；再往后有词就提醒。App 打开、回前台、切后台都重排，复习完的日子就撤掉。
  - 「这次什么时候复习」（once）：在它之前不排每天的那条；到点那天有词才提醒；提醒过的那天不再排每天那条；过了回到每天。
    到点没词：这个时间作废，当天到了每天的钟点照常（有词才提醒）。（服务器周日晚上发过每周进度邮件就不再发复习提醒邮件，App 的通知不跟这一条。）
  - 「我的 → 每天提醒」（`reminder.ics?kind=plan&hour=&minutes=`）选了 App 通知，就每天在那个钟点提醒今天的学习，不用登录。
  - 点通知：复习打开 `#/review`，今天的学习打开 `#/`；App 没在运行也一样。退出登录以后不再提醒复习单词。
  - 账号还没同意「数据存放在香港」（`/api/next/vocab` 回 403，code `storage`：老账号回答之前、选了不同意而暂停的账号）：和网站一样什么提醒都不排，
    今天的学习那条也不排。学员设的钟点留着，同意以后下次拿到 `/api/next/vocab` 就自己排回来。
    没同意当前版本《用户协议》的账号也一样：同样回 403 `storage`，另带字段 `need`（`'storage'` 或 `'terms'`，B6 #244）。协议或隐私说明改版以后会不定期出现，
    App 不用分开处理。
  - App 自己也会拿 `/api/next/vocab` 重排（iOS、安卓用 WebView 的 cookie；桌面在页面里 fetch 再 sync）。

## 6. 系统媒体控制 `media`（桌面）

网页照常自己放声音，App 盯着 navigator.mediaSession 交给系统（Windows SMTC、macOS「正在播放」、Linux MPRIS），媒体键再回调网页登记的动作。网页的 MS 层要守住：

- owner `'nar'` 和 `'long'` 登记 play、pause、stop、previoustrack、nexttrack（整篇用 'nar' 一口气放时才有上一句、下一句）；owner `'short'` 只登记 pause、stop。
- 暂停、继续时 playbackState 跟着变；放完或停下时 release：metadata 清空、状态 `'none'`。
- 上一句：已经放了 1.5 秒以上，先回到本句开头。

## 7. 浏览器声音 `speech`（安卓）

App 替网页补 speechSynthesis 时：每句先发 start 再发 end；cancel() 打断的那句发 error（`interrupted` 或 `canceled`），不发 end；
speaking、pending 照实；2.5 秒内一定发 start；getVoices() 有带 lang 的 en-US、en-GB；boundary 带 charIndex。

## 8. 安全

- 只接受本站（各平台配置里的站点）主框架发来的消息；别的网站在系统浏览器里打开。
- App 里不放任何密钥；不碰 Apple ID、Google 账号、证书和密码，签名由用户自己做。
- 网页给 App 的地址都相对本站；App 取 `/audio/own/…` 这些要登录的文件时带上 WebView 的 cookie。

## 9. 测试

- **测试不出声**（用户 2026-11-25）：每个平台都有静音开关，自动化测试默认打开，靠状态和事件判断：
  iOS 启动参数 `-FlowMuteAudio YES`；安卓、桌面、鸿蒙写在各自小节。浏览器自动化用 `--mute-audio`。真要听声音的测试先问用户。
- 网页一侧：`tools/ui_test.py` 用 add_init_script 放一个假的 FlowApp（记下收到的命令，按顺序发事件），测网页的适配；
  原来的组（listen-speak 等）照样全过，说明浏览器里没变。

## 10. 各平台实现

### iOS（语流 C1，`ios/`）

- 注入：WKUserScript，document start，只在主框架；Bridge.swift 的几行传输加上共用的 `native/flowapp.js`（第 2 节）。
- 主题色（网页 #282 的「我的 → 外观」）：另一段 WKUserScript（document end，主框架）看 `html[data-accent]`，变了就发 `app.accent`（只在 iOS 内部，
  不在 FlowApp 上）；App 自己画的地方（对话框按钮、下拉刷新、出错页的按钮）跟着换成松绿或靛蓝，logo 和启动图不变。
- 朗读：`items` 里已知的地址直接下载，`url: null` 的才问 `/api/next/tts`，问到的用 `audio-made` 告诉网页；退回系统声音时发 `fail {code, server}`
  （没网 `offline`、超时 `slow`、别的网络错误 `net`、没登录 `guest`，其余用服务器的 code），不自己写原因。
- 传输：`window.webkit.messageHandlers.flow.postMessage({cmd, args})`，WKScriptMessageHandlerWithReply 直接回 Promise；
  App → 网页：`evaluateJavaScript("FlowApp._emit(type, detail)")`。只认本站主框架（Bridge.swift 检查来源）。
- 「iOS 专属功能」（`app.settings`，原生 SwiftUI 页 FeaturesView；开关存在 UserDefaults `feature.<id>`，不上传；系统版本不够的不显示、算关）：
  - `lock-study` 锁屏上的学习按钮（iOS 27，默认开）：NowPlaying 框架的 MediaSession，除了播放、暂停、上一句、下一句，还有语速 0.75× / 1× / 1.25×、
    单句循环、退回 5 秒（整篇一口气放的录音退 5 秒；一句一句放的，这句从头再读）。用它时旧的 MPRemoteCommandCenter 按钮关掉，免得一个动作做两次。
  - `smart-resume` 来电以后接着放（默认开）：iOS 27 用 AVAudioSession 的 resumptionRecommendation，旧系统用 shouldResume；关了就不自己接着放。
  - `offline-packs` 离线朗读包（默认关）：开了以后，连着 Wi-Fi（不用流量、低数据模式也不下）时把今天要学的 3 篇（和网页「存到手机」挑的一样：
    今天这篇和今日的前两篇，学员的声音）的录音存进 Library/Caches/packs；App 回到前台最多 3 小时看一次，晚上充电时后台任务 `cn.flowlang.app.packs` 再看一次。
    放的时候地址（/audio/<声音>/<id>.mp4?v=<版本>）对得上就放手机上的那份。存满 7 天删，最多 9 个文件；关掉开关全删。
  - 没网而这篇录音 App 里没存：`play` 回 `{ok: false, why: 'offline'}`，网页自己放（第 3 节）。
  - `haptics` 复习时的轻触震动（默认开）：`app.haptic` 用 UIImpactFeedbackGenerator / UINotificationFeedbackGenerator，系统的「触感反馈」关了就感觉不到。
  - `frugal` 省电时少做事（默认开）：低电量模式或 `UIApplication.systemPrefersReducedResourceUsage`（iOS 27）时，服务器朗读只提前做 1 句（平时 2 句），
    离线朗读包不在前台下载（晚上充电时照常），网页收到 `frugal`。
  - App 自己画的出错页（「连不上语流」）在 iOS 26 起用系统的玻璃按钮，前面加一个说明原因的图标（没网 wifi.slash，别的 exclamationmark.icloud）。
  - 小组件（扩展 FlowWidgets，和 App 共用 App Group `group.<Bundle ID>`）：「今天」（主屏小、中，锁屏圆形、长条、一行）显示今天要复习几个词、新词、大约几分钟，中号的还有今日好句（带网站给的「公版名句」「语流文章」标注和出处）。小组件自己不上网：App 回到前台、后台刷新提醒时把数字写进 App Group。没登录不显示任何人的词。点一下用 App 自己的链接 `yuliu://open?path=%23/review`（内测版 `yuliu-beta`）打开复习；只认本站的 `#/` 页面。
  - 控制中心（iOS 18 起）：「开始复习」「今天的学习」两个按钮，打开 App 的复习页、今日页。
  - `review-activity` 复习进度的实时活动（默认关，锁屏上别人也看得到数字）：`activity.review` / `activity.end`，ActivityKit 本地更新，没有推送；App 重新启动时清掉上次留下的。
  - `siri` 快捷指令和 Siri（默认开）：App Intents 的三句话「语流开始复习」（打开 `#/review`）、「语流还有多少词要复习」（不打开 App，说出提醒用的那几个数；手机要解锁）、「用语流打开今天这篇」（今日「读」那篇的 `#/m/<id>`，没有就 `#/`）。快捷指令 App 里也有这三个。不用 Apple Intelligence 的实体索引和助手模式，学员的内容不交给 Siri 的大模型。网页不用改。
  - `word-search` 在系统搜索里找生词（默认关）：App 回到前台时问 `GET /api/next/cards/index?v=<上次的 v>`（语流 B2，#366），变了才重建 Core Spotlight 的本机索引（每张卡：词或表达、释义第一段）；学员在 iPhone 的搜索里点了，就打开 `#/cards/find/<encodeURIComponent(词)>`。没登录、没同意存放、关掉开关：索引清空。不用带大模型的搜索。网页不用改。
  - 专注模式过滤（不设开关，学员在系统设置里加）：「设置 → 专注模式 → 某个模式 → 添加过滤条件 → 语流」，选都提醒 / 只提醒复习单词 / 都不提醒。复习提醒和每天计划提醒的通知各带 `filterCriteria`（`review` / `plan`），过滤由系统做。
- **切换账号 `account.changed`**（第 5 节；切换、添加账号、退出登录、注销账号以后网页调）：回答之前先清掉上一个账号的东西，网页马上走开也算数：
  - 「在系统搜索里找生词」的索引马上清空（不管开关开没开）；正在拿上一个账号清单的那次重建作废，不会放回去；
  - 复习进度的实时活动结束；小组件的数字卡删掉（显示「打开语流 App…」直到新账号的数字到）；
  - 正在放的朗读停下，本机各篇的朗读进度清掉；
  - 上一个账号排好的提醒和通知中心里已经弹出的撤掉，忘掉它的「这次什么时候复习」；提醒开关和每天计划提醒是这台手机的，不跟账号走。
  - 回答 `{ok: true}` 以后在后台照「回到前台」那样按新账号重新取：提醒、小组件和 Siri 的数字、生词索引（开关开着才建）、离线朗读包。
  - 登录凭证仍在 WebView 的 cookie 里；App 在钥匙串里另存一份（只在这台设备，不进备份），`flow_session` 和 `flow_more` 都存，网站清掉了就删。App 不存用户名。
- WKAppBoundDomains 只有本站：服务工作线程、桥、cookie 只在本站有效。
- audio：AVPlayer，AVAudioSession `.playback` + `.spokenAudio` + 后台音频，MPNowPlayingInfoCenter / MPRemoteCommandCenter；系统声音 AVSpeechSynthesizer。
- rec：AVAudioRecorder；notify：UNUserNotificationCenter + BGAppRefreshTask。
- 静音开关：`-FlowMuteAudio YES`（AVPlayer.isMuted、朗读音量 0，网页的 `<audio>`、Web Audio、speechSynthesis 也静音）。

### 安卓（语流 C2，`android/`）

Kotlin，minSdk 26，targetSdk 37；说明在 `android/README.md`。flavor `beta`（cn.flowlang.app.beta，「语流内测」，flow.jasa.hk）和 `prod`（cn.flowlang.app，「语流」，flowlang.cn）。

- **注入**：`WebViewCompat.addDocumentStartJavaScript`，在 document start 注入，规则里只有本站的源。注入的是两个文件拼在一起：
  - 先是安卓自己的 `android/app/src/main/assets/flowapp-android.js`：`__flowAppTransport`（传输、`extend` 里加 `_back`、`ready` 里收端口消息和发 hello），再加上 speechSynthesis 和静音开关；
  - 后面是共用的 `native/flowapp.js`，原样放进去（打包时 Gradle 把 `native/` 加进 assets，第 2 节「共用的包装」）。
  - `build` 是 CI 的提交前 7 位（本机构建是 `"dev"`）；`beta` 看 flavor。
- **传输**：`WebViewCompat.addWebMessageListener` 的 `flowNative` 通道，不用 `addJavascriptInterface`。
  - 网页发 `postMessage(JSON {id, cmd, args})`，App 用 JavaScriptReplyProxy 回 `{id, ok, result | error}`。
  - App → 网页走同一个通道，发 `{ev, detail}`，flowapp-android.js 转给 `FlowApp._emit`（speech 的事件转给 speechSynthesis 那一段）。
  - 只认本站主框架（isMainFrame 加 origin 检查）。WebView 太旧、缺这两个功能时什么都不挂，网页照浏览器的做法。
- **外壳**：
  - 主题色：`assets/flowapp-android.js` 盯着 `<html data-accent>`，变了就发安卓自己的命令 `app.accent`（`{accent: 'green' | 'indigo'}`），App 自己画的对话框、提醒通知、进度条跟着变。网页不用做什么。
  - UA 末尾是 `FlowAndroid/<版本>`；返回键先发 `flowapp:back`（第 2 节）；别的网站、`mailto:`、`tel:` 交给系统打开；
  - 深色和浅色切换不重新加载；键盘弹出时整个 WebView 变矮，网页里 visualViewport 看不到键盘；
  - WebView 的使用统计和 Safe Browsing 关掉，不做云备份。
- **第一次打开**（1.0.4 起，为上国内应用商店，`android/README.md`「第一次打开」）：
  - App 先用自己的弹窗问《用户协议》《隐私和数据》。两章全文是打包时从 guide.md 生成的，回答以前不打开网页，也不联网。
  - 点「不同意」进入基本模式：不登录，不提醒，不录音。登录、注册的请求由 App 拦下，回 403 `{error, code: 'app-consent'}`，同时再问一次。
  - 能力 `privacy`（安卓和鸿蒙）。网页「我的 → 设置」可以用它来做：
    - `privacy.state()` → `{state: 'agreed' | 'basic', version, beian, store}`；`beian` 是 APP 备案号，空字符串就不显示；
    - `privacy.ask()`：在基本模式里再问一次；
    - `privacy.withdraw()`：撤回同意，App 先说明，再清掉手机上的东西，回到第一次打开的弹窗；
    - `privacy.permissions()` → `{mic, notify}`；
    - `privacy.settings({what: 'mic' | 'notify'})`：打开手机设置里对应的那一页。
  - 申请麦克风、通知权限时，页面顶上同时显示用途说明。
  - 开机接收器平时关着，打开了 App 提醒才打开。
- **audio**：Media3 ExoPlayer 加 MediaSessionService（前台服务，类型 mediaPlayback）。
  - 锁屏、通知栏、耳机和蓝牙按键：播放、暂停、上一句、下一句。SimpleBasePlayer 显示标题和「AI 朗读 · 第 n / N 句」（合成声音的显式标识）；句间停顿和正在生成的句子也显示成在放。
  - 音频焦点自己管：
    - 短暂失去（来电、闹钟、导航）：暂停，回来后自己接着放；
    - 彻底失去（别的 App 放声音）：暂停（why = other）；
    - `ACTION_AUDIO_BECOMING_NOISY`（拔耳机）：暂停（why = route）。
  - 系统自带的声音用 TextToSpeech，按 voice 挑 en-GB 或 en-US，语速跟 rate。
  - `fail.code`：手机没联网是 `offline`，其他网络错误是 `net`，超时 `slow`，其余用服务器回的 code。
  - 放过的文件存进 150 MB 缓存。
- **rec**：
  - AudioRecord 录 16 kHz 单声道 PCM（VOICE_RECOGNITION，没有就用 MIC），App 自己写 44 字节的 WAV 头；m4a 用 MediaRecorder（AAC，16 kHz，32 kbps）。
  - 录音时申请 AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE；失去焦点（来电）或者 App 切到后台（安卓只许前台用麦克风）就 cut。
  - 权限：第一次由系统弹窗问；拒绝过一次以后，再要用时 App 先说明用途；彻底拒绝以后给「去设置」。
  - 没接桥的页面照旧用 getUserMedia：系统已经允许麦克风时，App 对本站直接同意。
- **notify**：规则同第 5 节，`notify/Planner.kt` 照 iOS 的 ReminderPlan 写，单元测试用同一组例子。
  - Android 12 以下系统不问通知权限，所以「学员打开了 App 提醒」由 App 自己记，`ask()` 为 true 以后才排。
  - `permission()`：学员打开之前是 `'undetermined'`，打开了并且系统允许是 `'granted'`，系统里关了是 `'denied'`。
  - AlarmManager：
    - 能精确就用 `setExactAndAllowWhileIdle`；
    - Android 14 起新装的 App 默认没有精确闹钟权限（我们用 SCHEDULE_EXACT_ALARM，不用给闹钟类 App 的 USE_EXACT_ALARM），这时用 `setWindow` 的 10 分钟时间窗；
    - 用户在「闹钟和提醒」里打开权限以后，自动改成准点；
    - 重启手机、改时间或时区、App 升级以后都重排（开机这一项只在打开了 App 提醒时才有）。
  - `pending()` 返回 App 自己记下的列表，因为 AlarmManager 不能查。
  - App 打开（onStart）和切后台（onStop）时，用 WebView 的 cookie 拿 `/api/next/vocab` 重排：10 分钟内不重复拿，`sync` 和 `ask` 时一定拿。
  - `reminder.ics` 链接：App 先问「App 通知」还是「系统日历」。系统日历打开日历 App 的新建日程页（CalendarContract 的 ACTION_INSERT），不要日历权限。
  - 内测版有 `call('notify.test', 计数)`。
  - `account.changed`（1.0.5 起，第 5 节）：停掉朗读、清掉本机各篇的朗读进度；撤掉上一个账号的提醒和已经弹出的复习通知，忘掉它的钟点和 `once`，同意过的话马上按现在的账号拉 `/api/next/vocab` 重排；cookie 立刻写盘。App 提醒的开关和「每天的学习」跟手机走，不跟账号走。App 不存用户名。→ `{ok, scheduled}`。
- **speech**（第 7 节）：
  - 用 TextToSpeech 换掉 WebView 里没有声音的 speechSynthesis 和 SpeechSynthesisUtterance；引擎在 App 打开时就初始化好。
  - `getVoices()` 只给已经装好的英语声音。谷歌语音引擎默认只装美音，英音要用户在系统的「文字转语音」里下载；手机上没有英音时，网页按原来的做法选第一个英语声音。
- **静音开关**：`Mute`。
  - 界面测试在启动 App 之前打开；手动打开：`adb shell am start -n cn.flowlang.app.beta/cn.flowlang.app.MainActivity --ez flow.mute true`（调试包和内测包）。
  - 打开以后：ExoPlayer 和 TextToSpeech 音量为 0；网页的 `<audio>` 静音，Web Audio 接一个音量为 0 的节点；提醒不响铃。
  - 模拟器另外用 `-no-audio` 启动。
- **测试**：
  - 22 个 JUnit（Sentences、Planner、WAV、ics）；
  - 7 个界面测试（模拟器，内测版，游客，不出声）：桥的字段、登录页、播放、通知栏控制、麦克风弹窗和录音、`notify.test` 排期、退回系统声音时带 `fail`；
  - CI 是 `.github/workflows/android.yml`，跑构建、单元测试和 lint。

### 桌面（语流 C3，`desktop/`）

Tauri 2，一套代码出 Windows（WebView2）、macOS（WKWebView）和 Linux（系统的 WebKitGTK 4.1；AppImage 和 deb，x86_64）；说明在 `desktop/README.md`。

- 注入：`initialization_script`，document start；脚本开头先对 `location.origin`，不是本站就什么都不挂。文件 `desktop/src-tauri/src/bridge.js`。
  `FlowApp` 冻结；`build` 是构建的提交（CI 的 GITHUB_SHA 前 7 位，本机构建是 `"dev"`）。
- 传输：网页 → App 用 Tauri 的 invoke（`window.__TAURI_INTERNALS__`，网页不要直接用）。
  只有本站两个 origin 能调，而且只能调 `media_update`、`notify_*`、`smoke_report` 这几条（`capabilities/site.json`，每条命令各有权限）。
  App → 网页：`webview.eval("FlowApp._media(action)")` 和 `FlowApp._emit(type, detail)`。别的网站、`.ics`、`mailto:` 交给系统打开，从不在窗口里加载。
- media：bridge.js 包住 `navigator.mediaSession`（metadata、setActionHandler、playbackState）和 `HTMLMediaElement.play`，用来拿位置和时长（≥ 20 秒才给系统时间轴）。
  原生用 souvlaki 交给 Windows SMTC、macOS MPNowPlayingInfoCenter / MPRemoteCommandCenter、Linux MPRIS（D-Bus 名字 `org.mpris.MediaPlayer2.<bundle id>`）。按键对应的动作：
  - 播放/暂停键：按 playbackState 选 pause 或 play；
  - 上一首、下一首：previoustrack、nexttrack；
  - 网页没登记的动作：不做任何事。
  
  WebView2 关掉 HardwareMediaKeyHandling，免得网页和 App 同时响应一次按键。
- notify：规则照第 5 节，和 iOS `ReminderPlan` 一一对应（`desktop/src-tauri/src/schedule.rs`，单元测试有对应的例子）。
  - 数据：bridge.js 在页面里 `fetch('/api/next/vocab')`，带页面的 cookie，把整份交给 App。时机：App 打开、回到前台（最多 30 分钟一次）、网页调 `sync(r)`，以及每 3 小时一次（窗口一直开着、或藏在 Dock 或托盘里时）。这一步在桥里跑，不靠网页自己的代码，所以页面显示什么都照样跑。
  - 401 = 退出登录，撤掉单词提醒。403 且 code 是 `'storage'`（「数据存放在香港」还没同意）：撤掉全部提醒，开关和钟点留着；同意以后，下一次重排时提醒自己回来。
  - macOS：UNCalendarNotificationTrigger。
  - Windows：ScheduledToastNotification。AUMID 就是 bundle id，安装程序放在开始菜单快捷方式上；点通知走 `flowlang://review` 或 `flowlang://open`（内测版是 `flowlang-beta://`），App 没开也能打开。
  - Linux：系统没有替 App 定时弹通知的接口，App 自己计时，到点弹 freedesktop 通知（notify-rust），点通知打开复习页。所以**只在 App 开着时提醒**：
    Linux 上「关窗口后留在托盘」默认打开，再勾上「开机时启动」就等于一直开着；到点时没在运行（关机、睡眠）、迟了 10 分钟以上的那条不补。
  - Windows、macOS：App 关着时，提醒由系统按时弹出。
  - permission() 照第 5 节说的，是 App 的提醒开没开：系统允许并且开着是 `'granted'`，没开或关了是 `'undetermined'`，系统里关了是 `'denied'`。Windows 在第一次弹通知之前读不到系统设置，这时只看开关；ask() 不弹框。
    Linux 没有通知权限可问：桌面有通知服务（`org.freedesktop.Notifications`）就看开关，没有就是 `'denied'`。
  - 「每天的计划」（plan）：字段保留了；桌面的 `.ics` 链接还是交给系统日历。
  - `account.changed`（切换账号、添加账号、退出登录，第 5 节）：先撤掉上一个账号排好的提醒，和通知中心里已经弹出来的（Windows、macOS；Linux 的通知服务各管各的），
    忘掉它的「这次什么时候复习」，再马上按现在这个账号的 `/api/next/vocab` 重排；网页要是先走开了，下次打开或回到前台就排，不等 30 分钟。
    提醒开关是这台电脑的，不跟账号走。登录凭证全在 WebView 自己的 cookie 里（`flow_session`、`flow_more` 一样存），桥不读也不挑。
- 不做：`audio`、`rec`、`speech`。桌面网页本来就能放声音、getUserMedia，麦克风只给本站（WebKitGTK 默认关着 media stream，Linux 上 App 把它打开）。
  Linux 的网页引擎靠 GStreamer 解码：AAC 要 libav 插件，AppImage 自带，deb 依赖它；别的装法缺的话，网页对 AAC 放不了的情况改用 AI 朗读（B3）。
- 静音开关：环境变量 `FLOW_MUTE=1`。冒烟测试 `--smoke-test=<file>` 一律静音：网页的 `<audio>` 静音，Web Audio 接一个音量为 0 的节点，speechSynthesis 音量 0，通知不带声音。
- 测试：
  - Rust 单元测试；
  - `--smoke-test=<file>` 在页面里检查第 1–2 节的形状，`desktop/tools/check_smoke.py` 判定；
  - CI `.github/workflows/desktop.yml` 在 windows-latest（装好 NSIS 安装包后）、macos-latest 和 ubuntu-22.04（AppImage，xvfb + dbus-run-session，dunst 当通知服务）上各跑一次。
    Windows 和 Linux 上加了 `FLOW_SMOKE_NOTIFY=1`，真的排提醒、弹一条测试通知，之后清掉；冒烟测试从不改学员的设置。

### 鸿蒙（语流 C4，`harmony/`）

纯血鸿蒙（HarmonyOS 5.0 起，API 12）装不了安卓 APK，所以单独做。ArkTS 的 Stage 模型，一个 UIAbility 里一个 ArkWeb 的 Web 组件；说明在 `harmony/README.md`。
最低 5.0（compatibleSdkVersion 5.0.0(12)），所以网页要守住 Chromium M114（5.0–5.1 的 ArkWeb 内核；6.0 起是 M132），`tools/check_compat.py` 查。
product `default`（cn.flowlang.app.beta，「语流内测」，flow.jasa.hk）和 `prod`（cn.flowlang.app，「语流」，flowlang.cn）；名字分别放在 `AppScope/resources_beta|prod` 和 `entry/src/beta|prod`。

- **注入**：Web 组件的 `javaScriptOnDocumentStart`，规则里只有本站的源。注入的是两个文件拼在一起：
  - 先是鸿蒙自己的 `rawfile/flowapp-harmony.js`：`__flowAppTransport`（传输、`extend` 里加 `_back`、`ready` 里发 hello），再加上静音开关；
  - 后面是共用的 `native/flowapp.js`，原样放进去。
- **传输**：
  - 网页 → App：Web 组件的 `javaScriptProxy`，对象名 `flowNative`，只有一个方法 `post(json)`，`{id, cmd, args}`；
  - App → 网页：`runJavaScript` 调一个不可枚举的接收函数，名字每次启动 App 时随机生成，放在注入的配置里；回 `{id, ok, result | error}` 或事件 `{ev, detail}`。
  - App 只回答本站页面的消息（看 Web 组件当前的地址）。
- **外壳**：
  - UA 末尾是 `FlowHarmony/<版本>`；深色和浅色跟着手机（`WebDarkMode.Auto`），切换不用重新加载；
  - 键盘弹出时网页变矮（`RESIZE_CONTENT`），和安卓一样，visualViewport 看不到键盘；
  - 侧滑返回先发 `flowapp:back`（第 2 节）；别的网站、`mailto:`、下载交给系统打开；
  - 网页自己的 getUserMedia（没接桥的页面）只给本站，手机允许麦克风以后自动同意；
  - 「加到手机日历」（`/api/next/vocab/reminder.ics`）：App 拿到这个文件，解析第一个日程，用 Calendar Kit 的 `editEvent` 打开系统日历的「新建日程」页，内容都填好，学员自己点保存。不要日历权限，也不开浏览器。
- **audio**：AVPlayer，`STREAM_USAGE_AUDIOBOOK`。
  - AVSession 把标题和「AI 朗读 · 第 n / N 句」放到锁屏和控制中心，有播放、暂停、上一句、下一句；读完或停下时把会话撤掉，卡片跟着消失。
  - 后台播放靠长时任务 AUDIO_PLAYBACK。来电、别的 App 出声：系统说暂停就暂停（why = interrupted），说继续就接着放；拔耳机暂停（why = route）。
  - 语速只有固定几档（0.5、0.75、1、1.25、1.5、1.75、2），取最接近的一档。
  - **没有系统自带的声音**：鸿蒙的系统朗读是 Core Speech Kit，属于系统自带的 AI 能力，按规矩不接（不提供 `speech`）。
    服务器做不出某一句时，暂停（why = error）并带 `fail {code, server}`，由网页说明原因；点继续再问一次。
- **rec**：AudioCapturer 录 16 kHz 单声道 PCM，App 自己写 44 字节 WAV 头；m4a 用 AVRecorder（AAC，16 kHz，32 kbps）。
  - 来电或切到后台时停下（cut）；`ms` 按录到的声音算，不按墙上时间算。
  - 权限第一次由系统弹窗问；拒绝过以后，用 `requestPermissionOnSetting` 弹系统自己的开启框。
- **notify**：**暂不提供**（`has('notify')` 为 false）。
  - 原因：第三方 App 用后台代理提醒（reminderAgentManager），要华为按包名开通；没开通时 `publishReminder` 回 1700002，上限是 0。
  - 用户 2026-11-26 定了：先只用邮件和「加到手机日历」。
  - `notify/` 的排期（Planner，和 iOS、安卓同一套规则，最多排 28 条）已经写好，以后开通了在 FEATURES 里加回去就行。
- **第一次打开**（和安卓 1.0.4 同一套，`harmony/README.md`「第一次打开」）：
  - 回答以前没有 Web 组件，也不联网；两章全文打包时用安卓的 `android/tools/legal_docs.py` 从 guide.md 生成，在 App 自己的一层里打开（`blockNetwork`）。
  - 「不同意」再确认一次，进入基本模式：页面顶上一行说明和「同意」；登录、注册的请求由 `onInterceptRequest` 拦下，回 403 `{error, code: 'app-consent'}`，同时再问一次；录音（桥的 `rec` 和网页自己的 getUserMedia）先问同意。
  - 能力 `privacy` 的命令和安卓一样。`privacy.state().store` 是 true（鸿蒙只从华为的渠道装）；`privacy.settings({what: 'mic'})` 打开「设置 → 应用和元服务 → 语流」。
  - 撤回同意：停掉朗读和录音，清掉 cookie、网页存储、缓存、朗读进度和提醒，再回到第一次打开的弹窗。
- **切换账号 `account.changed`**（第 5 节；切到另一个账号、添加账号登录成功、退出登录、注销账号）：
  - 停掉朗读，清掉本机各篇的朗读进度（是上一个账号的）；
  - 按现在这个账号的 `/api/next/vocab` 重排提醒，403 `storage` 就不排（`notify` 还没开，所以眼下只是清空）；
  - 马上把 cookie 写进磁盘。`flow_session` 和 `flow_more` 都是 HttpOnly、带 Max-Age，ArkWeb 一样长期保存；切到后台时也写一次，免得刚登录或刚切换就划掉 App 时丢了；
  - App 不存用户名；「加到手机日历」用系统自己的新建日程页保存，App 里不留东西。
- **静音开关**：`hdc shell aa start -a EntryAbility -b cn.flowlang.app.beta --pb flow.mute true`（调试包和内测包）。打开以后：AVPlayer 音量 0，网页的 `<audio>` 静音，Web Audio 接一个音量为 0 的节点，speechSynthesis 不出声。
- **测试**：
  - 本地单元测试（hypium）：排期、句子、WAV、.ics 解析、第一次打开的规则；
  - HarmonyOS 5.0.1 模拟器上手动测过：桥、整篇朗读、锁屏卡片和按钮、录音、日历（2026-11-26，`harmony/README.md`）；第一次打开、基本模式、登录拦截、撤回同意（2026-11-26 中午）；
  - CI 现在不构建 `harmony/`。
