# 语流 App 和网页之间的桥（FlowApp v1）

iOS（语流 20）、安卓（语流 21）、桌面 Windows 和 macOS（语流 22）共用这一份约定。网页只认一个入口 `window.FlowApp`，
命令、事件、字段、错误码只在这里写一次；各平台怎么实现写在最后一节。

- 约定由语流 20 牵头改；各平台的小节由各自的会话写。要改共用部分，先在 PR 里提，三边同意再合。
- 网页一侧用桥的地方：声音和录音（语流 09，01-audio-offline.js、70-learner.js），提醒（语流 11，50-words.js），
  App 外壳的样子（语流 07，04-home-app.js）。

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

## 3. 整篇朗读 `audio`

听的「播放全文」、读的「伴读」（网页的 LONG）。短声音（单词、例句、单句、AI 回复）还在网页里放，不走桥。

### 命令

`play(o)` → `{ok: true, state}` 或 `{ok: false, why, message?}`。o：

| 字段 | 意思 |
|---|---|
| `key` | `'listen:<id>'` / `'read:<id>'`（网页 PROG 的 key；`''` 不记进度） |
| `title` | 锁屏、通知栏显示「语流 · 标题」 |
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

### iOS（语流 20，`ios/`）

- 注入：WKUserScript，document start，只在主框架；文件 `ios/Flow/Bridge/FlowBridge.js`（第 2 节的形状）。
- 传输：`window.webkit.messageHandlers.flow.postMessage({cmd, args})`，WKScriptMessageHandlerWithReply 直接回 Promise；
  App → 网页：`evaluateJavaScript("FlowApp._emit(type, detail)")`。只认本站主框架（Bridge.swift 检查来源）。
- WKAppBoundDomains 只有本站：服务工作线程、桥、cookie 只在本站有效。
- audio：AVPlayer，AVAudioSession `.playback` + `.spokenAudio` + 后台音频，MPNowPlayingInfoCenter / MPRemoteCommandCenter；系统声音 AVSpeechSynthesizer。
- rec：AVAudioRecorder；notify：UNUserNotificationCenter + BGAppRefreshTask。
- 静音开关：`-FlowMuteAudio YES`（AVPlayer.isMuted、朗读音量 0，网页的 `<audio>`、Web Audio、speechSynthesis 也静音）。

### 安卓（语流 21，`android/`）

（语流 21 写：传输 WebMessageListener、Media3、AudioRecord、通知和精确闹钟、静音开关。）

### 桌面（语流 22，`desktop/`）

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
  - 数据：bridge.js 在页面里 `fetch('/api/next/vocab')`，带页面的 cookie，把整份交给 App。时机：App 打开、回到前台（最多 30 分钟一次）、网页调 `sync(r)`。401 = 退出登录，撤掉单词提醒。
  - macOS：UNCalendarNotificationTrigger。
  - Windows：ScheduledToastNotification。AUMID 就是 bundle id，安装程序放在开始菜单快捷方式上；点通知走 `flowlang://review` 或 `flowlang://open`（内测版是 `flowlang-beta://`），App 没开也能打开。
  - App 关着时，提醒由系统按时弹出。
  - Windows 在第一次弹通知之前读不到设置，permission 返回 `'undetermined'`，不算拒绝；ask() 不弹框。
  - 「每天的计划」（plan）：字段保留了；桌面的 `.ics` 链接还是交给系统日历。
- 不做：`audio`、`rec`、`speech`。桌面网页本来就能放声音、getUserMedia，麦克风只给本站。
- 静音开关：环境变量 `FLOW_MUTE=1`。冒烟测试 `--smoke-test=<file>` 一律静音：网页的 `<audio>` 静音，Web Audio 接一个音量为 0 的节点，speechSynthesis 音量 0，通知不带声音。
- 测试：
  - Rust 单元测试；
  - `--smoke-test=<file>` 在页面里检查第 1–2 节的形状，`desktop/tools/check_smoke.py` 判定；
  - CI `.github/workflows/desktop.yml` 在 windows-latest（装好 NSIS 安装包后）和 macos-latest 上各跑一次。Windows 上加了 `FLOW_SMOKE_NOTIFY=1`，真的排提醒、弹一条测试通知，之后清掉；冒烟测试从不改学员的设置。
