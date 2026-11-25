# 语流 App 和网页之间的桥（FlowApp v1）

iOS（语流 C1）、安卓（语流 C2）、桌面 Windows 和 macOS（语流 C3）共用这一份约定。网页只认一个入口 `window.FlowApp`，
命令、事件、字段、错误码只在这里写一次；各平台怎么实现写在最后一节。

- 约定由语流 C1（iOS）牵头改；各平台的小节由各自的会话写（会话名对照见共享笔记 session-names.md）。要改共用部分，先在 PR 里提，三边同意再合。
- 网页一侧用桥的地方：声音和录音（语流 B3，01-audio-offline.js、70-learner.js），提醒（语流 B2，50-words.js），
  App 外壳的样子（语流 B5，04-home-app.js）。

## 1. 网页怎么知道自己在 App 里

- **功能一律看 `window.FlowApp`**：App 在网页自己的脚本之前放好它（document start，只在本站的主框架里）。
  先判断 `window.FlowApp && FlowApp.has('<能力>')`，没有就照网页原来的做法。Safari、主屏 App、微信、电脑浏览器都不受影响。
- **User-Agent 末尾**：`FlowiOS/<版本>`、`FlowAndroid/<版本>`、`FlowDesktop/<版本> (Windows)` 或 `(macOS)`。
  UA 只用来决定外壳的样子（04-home-app.js：返回按钮、不显示「添加到桌面」），写成 `/Flow(iOS|Android|Desktop)\//`。不要靠 UA 判断能力。
- `FlowApp.platform`：`'ios'` | `'android'` | `'windows'` | `'macos'`。说法跟着平台走，比如通知、麦克风权限去哪里打开：

| platform | 通知 | 麦克风 |
|---|---|---|
| ios | 「设置 → 语流 → 通知」 | 「设置 → 语流 → 麦克风」 |
| android | 「设置 → 应用 → 语流 → 通知」 | 「设置 → 应用 → 语流 → 权限 → 麦克风」 |
| windows | 「设置 → 系统 → 通知」 | 「设置 → 隐私和安全性 → 麦克风」 |
| macos | 「系统设置 → 通知」 | 「系统设置 → 隐私与安全性 → 麦克风」 |

- 其他字段：`FlowApp.v`（桥的版本，现在 1）、`FlowApp.app`（App 版本）、`FlowApp.build`、`FlowApp.beta`（打开的是内测版）。

## 2. 共同的形状

- 调用：`FlowApp.<块>.<命令>(参数)` 返回 Promise。预料之中的失败（没权限、正在录音……）照常 resolve，结果里 `ok: false` 加 `why`；
  只有传输出错、不在本站、命令不存在时才 reject。
  - 网页一律 `await`（或 `.then`）以后再用结果，不能直接拿返回值比较（`FlowApp.notify.permission() === 'granted'` 在每个 App 里都是 false）。
    测试里假的 FlowApp 也要返回 Promise，和真的一样。
- 事件：`FlowApp.on(type, fn)` 返回退订函数，`FlowApp.off(type, fn)` 也行；同时在 `window` 上发 `flowapp:<type>` 事件（detail 同参数）。
- 能力 `FlowApp.has(名字)`：

| 能力 | 意思 | iOS | 安卓 | 桌面 |
|---|---|---|---|---|
| `audio` | 整篇朗读交给 App 放（锁屏、来电、后台） | 有 | 有 | 没有 |
| `rec` | 录音由 App 录 | 有 | 有 | 没有（网页 getUserMedia） |
| `notify` | 复习提醒用本地通知 | 有 | 有 | 有 |
| `media` | 网页自己放声音，App 把 navigator.mediaSession 交给系统（媒体键、「正在播放」） | 没有 | 没有 | 有 |
| `speech` | App 替网页补上 speechSynthesis（浏览器声音） | 没有 | 有 | 没有 |

- 一个 App 在回到前台、网页重新加载以后，会把正在放的状态再发一次（`audio` 事件），网页不用猜。网页可见时也可以调 `FlowApp.call('app.visible')` 让它重发。
- `FlowApp.call('hello')` → `{v, app, build, platform, features}`。
- 安卓的返回键：App 先在 `window` 上发可以取消的 `flowapp:back` 事件，网页 `preventDefault()` 就算处理了；没人处理时 App 关掉开着的 sheet，再回到上一页。iOS、桌面没有这个键，不发。

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
- 安卓：打包时从 `native/` 复制进 assets（语流 C2）。桌面：要不要用，由语流 C3 定。
- 静音开关、安卓的 speechSynthesis、桌面的 mediaSession 这些各平台自己的东西，不放进这个文件。
- 改这个文件就是三个 App 一起改：PR 里说明，iOS 的单元测试要过，安卓、桌面再各自打包试一次。

## 3. 整篇朗读 `audio`

听的「播放全文」、读的「伴读」（网页的 LONG）。短声音（单词、例句、单句、AI 回复）还在网页里放，不走桥。

### 命令

`play(o)` → `{ok: true, state}` 或 `{ok: false, why, message?}`。o：

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
`state()` → `{key, state, i, n, t, title, rate}`、`progress(key)` → `{i, t, at}`、读完了是 `{ended: true, at}`，没有记录是 null（`at` 是毫秒时间戳）。

### 事件

- `audio`：`{key, state, i, n, t, why, fail}`
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
- 来电、Siri 打断：暂停（why = interrupted）；系统说可以接着放，就自己接着放。耳机拔了暂停。
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

网页照常自己放声音，App 盯着 navigator.mediaSession 交给系统（Windows SMTC、macOS「正在播放」），媒体键再回调网页登记的动作。网页的 MS 层要守住：

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
  iOS 启动参数 `-FlowMuteAudio YES`；安卓、桌面写在各自小节。浏览器自动化用 `--mute-audio`。真要听声音的测试先问用户。
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
  - UA 末尾是 `FlowAndroid/<版本>`；返回键先发 `flowapp:back`（第 2 节）；别的网站、`mailto:`、`tel:` 交给系统打开；
  - 深色和浅色切换不重新加载；键盘弹出时整个 WebView 变矮，网页里 visualViewport 看不到键盘；
  - WebView 的使用统计和 Safe Browsing 关掉，不做云备份。
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
    - 重启手机、改时间或时区、App 升级以后都重排。
  - `pending()` 返回 App 自己记下的列表，因为 AlarmManager 不能查。
  - App 打开（onStart）和切后台（onStop）时，用 WebView 的 cookie 拿 `/api/next/vocab` 重排：10 分钟内不重复拿，`sync` 和 `ask` 时一定拿。
  - `reminder.ics` 链接：App 先问「App 通知」还是「系统日历」。系统日历打开日历 App 的新建日程页（CalendarContract 的 ACTION_INSERT），不要日历权限。
  - 内测版有 `call('notify.test', 计数)`。
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

Tauri 2，一套代码出 Windows（WebView2）和 macOS（WKWebView）；说明在 `desktop/README.md`。

- 注入：`initialization_script`，document start；脚本开头先对 `location.origin`，不是本站就什么都不挂。文件 `desktop/src-tauri/src/bridge.js`。
  `FlowApp` 冻结；`build` 是构建的提交（CI 的 GITHUB_SHA 前 7 位，本机构建是 `"dev"`）。
- 传输：网页 → App 用 Tauri 的 invoke（`window.__TAURI_INTERNALS__`，网页不要直接用）。
  只有本站两个 origin 能调，而且只能调 `media_update`、`notify_*`、`smoke_report` 这几条（`capabilities/site.json`，每条命令各有权限）。
  App → 网页：`webview.eval("FlowApp._media(action)")` 和 `FlowApp._emit(type, detail)`。别的网站、`.ics`、`mailto:` 交给系统打开，从不在窗口里加载。
- media：bridge.js 包住 `navigator.mediaSession`（metadata、setActionHandler、playbackState）和 `HTMLMediaElement.play`，用来拿位置和时长（≥ 20 秒才给系统时间轴）。
  原生用 souvlaki 交给 Windows SMTC、macOS MPNowPlayingInfoCenter / MPRemoteCommandCenter。按键对应的动作：
  - 播放/暂停键：按 playbackState 选 pause 或 play；
  - 上一首、下一首：previoustrack、nexttrack；
  - 网页没登记的动作：不做任何事。
  
  WebView2 关掉 HardwareMediaKeyHandling，免得网页和 App 同时响应一次按键。
- notify：规则照第 5 节，和 iOS `ReminderPlan` 一一对应（`desktop/src-tauri/src/schedule.rs`，单元测试有对应的例子）。
  - 数据：bridge.js 在页面里 `fetch('/api/next/vocab')`，带页面的 cookie，把整份交给 App。时机：App 打开、回到前台（最多 30 分钟一次）、网页调 `sync(r)`，以及每 3 小时一次（窗口一直开着、或藏在 Dock 或托盘里时）。这一步在桥里跑，不靠网页自己的代码，所以页面显示什么都照样跑。
  - 401 = 退出登录，撤掉单词提醒。403 且 code 是 `'storage'`（「数据存放在香港」还没同意）：撤掉全部提醒，开关和钟点留着；同意以后，下一次重排时提醒自己回来。
  - macOS：UNCalendarNotificationTrigger。
  - Windows：ScheduledToastNotification。AUMID 就是 bundle id，安装程序放在开始菜单快捷方式上；点通知走 `flowlang://review` 或 `flowlang://open`（内测版是 `flowlang-beta://`），App 没开也能打开。
  - App 关着时，提醒由系统按时弹出。
  - permission() 照第 5 节说的，是 App 的提醒开没开：系统允许并且开着是 `'granted'`，没开或关了是 `'undetermined'`，系统里关了是 `'denied'`。Windows 在第一次弹通知之前读不到系统设置，这时只看开关；ask() 不弹框。
  - 「每天的计划」（plan）：字段保留了；桌面的 `.ics` 链接还是交给系统日历。
- 不做：`audio`、`rec`、`speech`。桌面网页本来就能放声音、getUserMedia，麦克风只给本站。
- 静音开关：环境变量 `FLOW_MUTE=1`。冒烟测试 `--smoke-test=<file>` 一律静音：网页的 `<audio>` 静音，Web Audio 接一个音量为 0 的节点，speechSynthesis 音量 0，通知不带声音。
- 测试：
  - Rust 单元测试；
  - `--smoke-test=<file>` 在页面里检查第 1–2 节的形状，`desktop/tools/check_smoke.py` 判定；
  - CI `.github/workflows/desktop.yml` 在 windows-latest（装好 NSIS 安装包后）和 macos-latest 上各跑一次。Windows 上加了 `FLOW_SMOKE_NOTIFY=1`，真的排提醒、弹一条测试通知，之后清掉；冒烟测试从不改学员的设置。
