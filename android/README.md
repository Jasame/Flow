# 语流 Android App

原生外壳加关键功能原生，和 iOS 版（`ios/`，语流 C1）做法一样：Kotlin 写的外壳里用 WebView 打开网站，网站一改，App 里马上就是新的；整篇朗读、录音、复习提醒改用安卓原生来做。网页通过 `window.FlowApp` 调用这些原生功能，两个平台共用一套约定。

| | 内测版 | 正式版 |
|---|---|---|
| 显示名 | 语流内测 | 语流 |
| 包名 | `cn.flowlang.app.beta` | `cn.flowlang.app` |
| 打开的网站 | https://flow.jasa.hk | https://flowlang.cn |
| Gradle flavor | `beta` | `prod` |

两个包名不同，可以同时装在一台手机上。Android 8.0（API 26）以上都能装，targetSdk 37（Android 17）。

## 构建和安装

要用 JDK 21 和 Android SDK。在这台 Mac 上已经用 Homebrew 装好：

```bash
brew install openjdk@21 && brew install --cask android-commandlinetools
sdkmanager "platform-tools" "platforms;android-37.0" "build-tools;37.0.0" "emulator" "system-images;android-37.0;google_apis;arm64-v8a"
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
```

`android/local.properties` 里写上 `sdk.dir=<ANDROID_HOME>`（这个文件不进仓库）。然后：

```bash
cd android
./gradlew assembleBetaDebug                      # 内测版调试包：app/build/outputs/apk/beta/debug/
./gradlew testBetaDebugUnitTest                  # 单元测试（JVM，不要模拟器）
./gradlew connectedBetaDebugAndroidTest          # 界面测试：先开一个模拟器或接上手机
adb install -r app/build/outputs/apk/beta/debug/app-beta-debug.apk
```

模拟器：`avdmanager create avd -n flow37 -k "system-images;android-37.0;google_apis;arm64-v8a" -d pixel_8`，然后：

```bash
emulator -avd flow37 -no-window -no-audio      # 测试时一律不出声（工作约定第 9 条）；原生播放照样能测
```

调试包可以用 Chrome 的 `chrome://inspect` 看网页（正式签名的包关掉了）。

## 发 APK

两个 flavor 用两把签名钥匙（用户 2026-11-25 选的）。两把的别名都是 `flow`。

| | 内测版「语流内测」 | 正式版「语流」 |
|---|---|---|
| 钥匙 | `~/.flow-android/flow-beta.jks` | `~/.flow-android/flow-release.jks` |
| 密码 | macOS 钥匙串 `flow-android-beta` | macOS 钥匙串 `flow-android-release` |
| 另外一份 | GitHub environment `android-beta-signing` 的 Secrets：`FLOW_BETA_KEYSTORE`（base64）、`FLOW_BETA_KS_PW`。这个 environment 只给 main 用，PR 里的代码拿不到 | 没有，只在主人的 Mac 上 |
| 证书 SHA-256 | `C2:22:FE:38:31:FD:BC:17:49:7F:7D:9C:78:28:7B:8A:4C:D6:12:BF:53:BB:08:2A:12:85:E7:7E:BD:BA:BF:13` | `76:88:9C:6F:7E:E0:C6:C6:72:84:4B:05:17:91:9C:33:FB:6D:86:40:D2:EF:22:6A:47:20:AF:2B:12:82:89:27` |
| 谁来打包 | 每次合进 main（只改 `android/` 时），CI 自动打包 | 主人在 Mac 上跑 `tools/release-apk.sh prod` |

- **内测包**：在 GitHub 的 Actions →「Android」里找最新一次 main 的 run，下载 artifact `flow-beta-apk`（zip 里就是 APK），留 30 天。
  - versionCode 是 100 加上 run 的编号，每个新包都能直接覆盖上一个。
  - 本机也能打：`tools/release-apk.sh beta`。本机打的 versionCode 是 `gradle.properties` 里的 `flow.versionCode`，比 CI 打的（100 加 run 编号）小，装不上去覆盖手机上 CI 的包：要么先卸载，要么设 `FLOW_VERSION_CODE`，让它比手机上的大。
- **正式包**：`tools/release-apk.sh prod` → `dist/flow-<版本>.apk`。发之前先把 `gradle.properties` 里的 `flow.versionCode` 加 1，versionCode 更大的包才能覆盖旧的。
- 脚本从钥匙串里取密码，交给 `apksigner`；CI 上从 Secrets 取。Gradle 碰不到密码，仓库里也没有。
- **两把钥匙都要备份**（加密 U 盘、密码管理器都行），密码也要一起备份。丢了以后，新版本就不能覆盖安装：每个人都得先卸载再装，App 里的登录也要重新登。
- 怎么装到手机上，见 [INSTALL-zh.md](INSTALL-zh.md)。
- **公开下载**：正式包放在 `https://flowlang.cn/download/flow-android-<版本>.apk`，由语流 A1 上传，并在 `latest.json` 里写上安卓这一项（见下面「新版本」）。每出一版，把文件、SHA-256、证书指纹和一两句「这一版改了什么」交给 A1；A1 放出去之前问用户。
- 两类事要先问用户：
  - 改 `tools/release-apk.sh`、签名、Secrets 或 `.github/workflows/android.yml` 的 PR，合并之前（`docs/releases.md` 2026-11-25 11:15 的规矩）；
  - 把 APK 发给试用的同学、或者放到别的地方之前。这件事也要提前告诉语流 B6，由它把指南里 App 的权限说明放上去。

CI（`.github/workflows/android.yml`，语流 A2）：
- 每个改 `android/` 或 `native/`（三个 App 共用的 FlowApp 包装，会打进 App）的 PR 都跑 `assembleBetaDebug testBetaDebugUnitTest lintBetaDebug`（`native/` 从 A2 的 #193 起）。
- main 上另外由 job `beta-apk` 打签名的内测包。它绑定 environment `android-beta-signing`，只在 main 上跑，PR 拿不到钥匙，也不放到 MSI 自托管机器上。
  - 先在一个看不到钥匙的步骤里构建（Gradle 和它的插件都碰不到钥匙）；
  - 再在只有 zipalign 和 apksigner 的那一步签名（`FLOW_APK_PREBUILT=1`）；
  - 钥匙文件用 trap 删掉，签名失败也会删。

## 外壳做了什么（`MainActivity`）

- **登录**：用 WebView 自己的 cookie（`flow_session`，30 天），离开页面时写进磁盘，关掉 App 再打开还是登录状态。
- **返回键和返回手势**：先关网页上开着的弹层（sheet），再回到上一页；已经是第一页时，App 退到后台（正在播的文章继续播）。网页可以在 `flowapp:back` 事件里 `preventDefault()`，自己处理返回。
- **外链**：别的网站、`mailto:`、`tel:` 用系统浏览器或对应的 App 打开。只有本站在 App 里打开。
- **刘海、状态栏、导航栏、键盘**：页面夹在它们中间，周围用网页自己的颜色（浅 `#FBFAF6`，深 `#101412`）。深色模式切换时不用重新加载，页面和状态栏一起变。键盘弹出时，页面缩到键盘上面。
- **User-Agent** 末尾加 `FlowAndroid/<版本>`，例如 `… Mobile Safari/537.36 FlowAndroid/1.0.1`。
- **「加到手机日历」**（`reminder.ics` 链接）：App 先问用「App 通知」还是「系统日历」。
  - 选 App 通知：按链接排上每天复习（`?hour=`）、约好的一次（`?at=`）或「每天的学习」（`?kind=plan&hour=&minutes=`，不用登录）。
  - 选系统日历：打开手机日历的新建日程页，内容已经填好，不需要日历权限。
- 反馈里的「添加截图」可以从相册选图片。网页出不来时显示「网络连不上 · 重试」。系统回收网页进程以后，App 自己重新打开网页。

## 网页和 App 之间的桥（`bridge/`、`assets/flowapp-android.js`、共用的 `native/flowapp.js`）

约定是 iOS、安卓、桌面共用的 `docs/native-bridge.md`（语流 C1 牵头），安卓的实现写在它最后一节「各平台实现 · 安卓」。网页只调 `window.FlowApp`，不判断是哪个平台；平台不同的说法用 `FlowApp.platform`（这里是 `'android'`）。

**传输方式**：

- App 在网页脚本运行之前放好 `window.FlowApp`（`WebViewCompat.addDocumentStartJavaScript`），只放在本站的源上。
  - `window.FlowApp` 由三个 App 共用的 `native/flowapp.js` 做出来。打包时 Gradle 把仓库的 `native/` 加进 assets，原样放进 App，不要在安卓里改它；要改先跟语流 C1 说，三个 App 一起改。
  - 它前面是安卓自己的 `assets/flowapp-android.js`：传输（`window.__flowAppTransport`，包装用完就删掉），返回键 `_back`，系统朗读补丁，测试静音。
- 消息走 `WebViewCompat.addWebMessageListener` 的 `flowNative` 通道：网页发 `{id, cmd, args}`，App 回 `{id, ok, result | error}`，事件用 `{ev, detail}` 发过来。
- App 只认本站主框架发来的消息。手机上的 WebView 太旧、缺这两个功能时，App 什么都不加，网页就按普通浏览器的方式运行。

| 调用 | 安卓的做法 |
|---|---|
| `FlowApp.v` / `app` / `build` / `beta` / `platform` / `features` / `has(k)` / `call(cmd, args)` | `1`、App 版本、构建（CI 的提交前 7 位，本机是 `dev`）、是不是内测版、`'android'`；能力有 `audio`、`rec`、`notify`、`speech`。`call('hello')` → `{v, app, build, platform, features}`；`call('app.visible')` 让 App 把正在放的状态再发一次 |
| `FlowApp.on(type, fn)` → 取消订阅的函数；`off` | 同时发 `window` 事件 `flowapp:<type>` |
| `audio.play(o)` / `pause()` / `resume()` / `stop()` / `step(±1)` / `seek(i)` / `set({rate, rep, gap})` / `state()` / `progress(key)` | 见下面「原生声音」。这些都返回当前状态 `{ok, key, state, i, n, t, title, rate}`；`resume()` 的返回值网页用来判断要不要从头再放 |
| `rec.permission()` / `ask()` / `start({max, format})` / `stop()` / `cancel()` | 见下面「录音」 |
| `notify.permission()` / `ask()` / `sync(r)` / `pending()` / `off()` / `settings()` | 见下面「复习提醒」。内测版还有测试用的 `call('notify.test', 计数)` |
| `speechSynthesis` | 见下面「浏览器的声音」 |
| 返回键 | 先在 `window` 上发可以取消的 `flowapp:back`；网页没处理时，关掉开着的 sheet，再回到上一页 |

## 原生声音（`audio/`）

整篇朗读（「听」的播放全文、「读」的伴读）由 App 来放，用 Media3 的 ExoPlayer 加 `MediaSessionService`。**要网页调用 `FlowApp.audio` 才会用上**：网页这边是 #152，2026-11-25 时还没合，正式版网页还是自己放，所以现在没有锁屏控制。对外说「锁屏能控制」之前，先确认线上的网页脚本里真的调用了 `FlowApp.audio`。

- 锁屏和通知栏显示标题和「AI 朗读 · 第 3 / 20 句」，可以播放、暂停、上一句、下一句。耳机按钮、蓝牙按钮也能用。
  - 「AI 朗读」是按《人工智能生成合成内容标识办法》加的显式标识：语流的朗读都是合成声音（Kokoro 录音、CosyVoice、手机自带的声音）。音频文件里的隐式标识由服务器写入。
- 来电、闹钟、导航语音这类短暂打断时暂停，打断结束后自己接着放。别的 App 开始放声音时暂停，不会自己接着放。拔下耳机时暂停。
- 播放引擎（`FlowAudio`）在 App 里自己跑，网页在后台被挂起也不影响，下一句由 App 接上。
- **事件**：
  - `audio` `{key, state, i, n, t, title, rate, why, fail}`：状态变了、换到下一句时都发。页面回到前台、重新加载以后，再发一次当前状态（`why = state`）。
  - `audio-tick` `{key, i, t, at, rate}`：页面在前台时每秒 4 次。网页用 `t + (现在 − at) × rate`，让词的高亮在两次 tick 之间也能走。
  - `audio-made` `{key, i, url}`：App 新生成了一句的地址，网页把它记进 SV 地址簿，同一句不再生成第二次。
- **有录音**（`src` 加 `sentences: [[s, e], …]`）：
  - 一个文件从头放到尾，或者按句放（`loop`：复读 `rep` 遍，`gap[i]` 是第 i 句每读完一遍以后停的毫秒数，整篇最后一句之后不停）。
  - 本站的文件出错时，换到 `alt`（网页给的媒体域名线路），位置不变。两条线路都失败时暂停（`why = error`），点继续从停下的那一秒重新加载。
  - 登录 cookie 只发给本站，不发给媒体域名。
- **没有录音**（`items: [{text, url}]` 加 `voice`、`pack`；旧的 `texts` 也认）：
  - 网页已经知道的地址直接放；不知道的，一句一句请求 `POST /api/next/tts`，用网页传来的 `csrf`，以登录学员的身份，同时先准备后面两句。
  - 某一句生成不出来时，用手机自带的声音读这一句，`fail: {code, server}` 说明原因。提示的那句话由网页的 `SV.why` 来写，App 不自己写。
  - 服务器说今天的额度用完了（`cap`）或功能没开（`off`）以后，这篇剩下的句子不再去问服务器。（没同意「数据存放在香港」的账号，`/api/next/tts` 按游客回答，不会回 `storage`。）
- 播过的文件存进 150 MB 的缓存，重复听不再下载。
- 读到哪儿也由 App 记一份（`progress(key)` → `{i, t, at}`，30 天、最多 100 篇），App 被关掉以后还能接着读。读完了留一个 `{ended: true, at}`，给错过结束事件的页面看。

## 录音（`rec/`）

- 16 kHz 单声道。`wav` 是 16 位 PCM（每秒 32 KB），和网页的 FLOW_SAY_WAV 格式相同；`m4a` 是 AAC。
  - 超过 40 秒默认用 m4a：网页 `MIC.payload` 最多收 1.4 MB，40 秒的 WAV 是 1,280,044 字节。
- `start()` 返回 `{ok, format, max}`。
- `stop()` 返回 `{ok: true, mime_type, data(base64), ms, bytes, cut}`，和网页 `MIC.payload(blob)` 的格式一样；同一段录音只给一次。没有录到时返回 `{ok: false, why: 'none'}`。
- 还在等麦克风权限时就调了 `stop()` 或 `cancel()`，这次录音就不再开始，`start()` 返回 `why: 'cancelled'`。
- 录音时，正在放的整篇先暂停（`why = other`），别的 App 的声音也暂时停下。
- 来电或者 App 退到后台时，录音提前结束：已经录到的部分保留，`rec` 事件会报 `cut`。安卓只允许前台的 App 用麦克风。
- 麦克风权限第一次由系统弹窗询问（网页会先说明为什么要用）。用户拒绝过一次以后，再要用时 App 先说明用途：「语流要用麦克风录下你说的英语（跟读、口语对话、发音练习），只在你点录音的那几秒打开，录音只用来给你批改。」被彻底拒绝以后，App 给出「去设置」按钮。
- 没接桥的页面照旧用 `getUserMedia`：手机已经允许 App 用麦克风时，本站直接可以用。

## 复习提醒（`notify/`）

- 学员点「到点用 App 通知提醒」（`notify.ask()`）之后才打开提醒。Android 13 以上，系统还会单独弹窗问能不能发通知。
  - Android 12 以下系统不问通知权限，所以 App 自己记一个「已打开」。`permission()` 在学员打开之前返回 `undetermined`。
- 规则和 iOS 的 `ReminderPlan` 一样（`Planner`，单元测试用的是 iOS 的同一组例子），和服务器发邮件的规矩也一样：
  - 时间按北京时间，排今后 14 天。
  - 每天 `hour:00`，只在有词要复习的日子提醒：
    - 今天：看现在还剩多少，超出当天份额的也算；
    - 后面几天：看 forecast 累计到那天（没复习的词第二天还在），再加上词书没背完时每天的新词；
    - forecast 以后：有词就提醒。
  - `once`（「这次什么时候复习」）：
    - 在它之前不排每天的那条；
    - 到点那天有词才提醒，提醒过的那天不再排每天那条；
    - 到点没词：这个时间作废，当天到了每天的钟点照常提醒（有词才提醒）。
  - 「每天的学习」（`reminder.ics?kind=plan`，在 App 里选了通知）：每天那个钟点提醒今天的学习，打开 `#/`，不用登录。同一时刻的复习提醒就不再单独发。
- `sync(r)`：`r` 是网页的 `reminder`，可以带上 `forecast`、`app`。`sync(null)` 或 `off()` 关掉 App 的提醒。`pending()` → `[{id, at, title, body}]`。
- App 打开、回到前台、切到后台时，都用登录 cookie 拿一次 `/api/next/vocab` 重新排，所以复习完的日子会被撤掉。退出登录以后不再提醒复习单词，「每天的学习」照常。重启手机、改时间或时区以后，提醒会重新排上。
- 点通知：复习打开 `#/review`，今天的学习打开 `#/`。
- 账号还没给网站要的同意时，`/api/next/vocab` 回 403，什么提醒都不排，「今天的学习」也不排；网站对这样的账号也不发提醒。钟点留着，同意以后下一次拉到 vocab 就会自己排回来。
  - 缺哪一项同意，网站都回 code `storage`（这样只认 `storage` 的 1.0.1、1.0.2 也会暂停），另用 `need` 说明是哪一项：`storage` 是「数据存放在香港」，`terms` 是当前版本的《用户协议》和《隐私和数据》。协议一改版，所有人都会被再问一次，所以 `terms` 会不定期出现（B6，2026-11-25）。
  - 从 1.0.3 起，任何 403 都暂停提醒，不管 code 是什么，以后再加别的同意也一样。
  - 「App 通知」那句话先看 `need`，没有再看 `code`，说清楚要先同意什么（`Planner.consentNeeded`、`Planner.pausedLine`）；同意页由网页显示，App 不做界面。
  - 朗读不受影响：账号没同意时，服务器把 `/api/next/tts` 当游客的请求来回答（POST 先核对同意），不回 403。
- **精确闹钟**：Android 12 和 13 默认允许，提醒准点到。Android 14 起，新装的 App 默认不允许，只有学员在「闹钟和提醒」里打开才行。没有这个权限时，用 10 分钟的时间窗，提醒最多晚 10 分钟左右。权限一打开，App 自动改成准点（模拟器上测过）。我们不用 `USE_EXACT_ALARM`：它是给闹钟类 App 用的，以后上 Google Play 会被拒。

## 浏览器的声音（`speech/`）

安卓 WebView 自带的 `speechSynthesis` 背后没有声音（安卓微信也一样），App 把它换成手机自己的 TextToSpeech，网页不用改。照约定第 7 节：

- 每句先发 `start`，再发 `end`；`cancel()` 打断的那句发 `error`（`interrupted` 或 `canceled`），不发 `end`；
- `speaking`、`pending` 照实反映状态；`boundary` 带 `charIndex`；
- 语音引擎在 App 一打开时就初始化好，第一句也能在 2.5 秒内开始；
- 不支持句子中间暂停（TextToSpeech 做不到）。
- `getVoices()` 只给手机上已经装好的英语声音。英音（en-GB）要看手机的语音引擎有没有装：
  - 谷歌语音引擎默认只装美音，英音要在「设置 → 系统 → 语言 → 文字转语音」里下载；
  - 没有英音时，网页照它原来的做法，选第一个英语声音。

## 测试不出声

工作约定第 9 条，也是 `docs/native-bridge.md` 第 9 节：

- 模拟器用 `-no-audio` 启动。
- App 有一个静音开关 `Mute`。打开以后：
  - 整篇朗读和手机自带的声音音量为 0；
  - 网页的 `<audio>` 静音，Web Audio 接一个音量为 0 的节点；
  - 提醒不响铃。
- 界面测试默认打开这个开关。手动打开的方法：在调试包或内测包上运行 `adb shell am start -n cn.flowlang.app.beta/cn.flowlang.app.MainActivity --ez flow.mute true`。
- 判断有没有在放，靠状态和事件，不靠听。

## 新版本（`update/`，只有正式版「语流」）

从 1.0.2 起，App 自己看有没有新版本，有就提示，用户点了才下载、才装。直接装的 APK 没法悄悄自动更新：手机每次都要用户点一下「更新」，提示里照实这么说。要完全自动，得等上应用商店。

- **什么时候看**：App 启动时，以及每天第一次回到前台时（`MainActivity.onStart` → `Updater.onStart`）。没连上网就下次再看。
- **看哪里**：`https://flowlang.cn/download/latest.json` 里的 `android` 一项，由 A1 写：
  `{"version": "1.0.2", "code": 3, "file": "flow-android-1.0.2.apk", "size": …, "sha256": "…", "cert": "76:88:…", "date": "…", "notes": "这一版改了什么"}`。
  - 有 `code`（versionCode）就比 versionCode，没有就比版本号；`notes` 是提示里「这一版改了什么」，没有就不写（也认 `changes` 数组）。
  - 只在比自己新时提示：「有新版本 x.y.z」，下面是 `notes`，按钮「下载」「稍后」。点「稍后」（或返回键），同一个版本当天不再提示；第二天再提示，更新的版本当天也会提示。
- **下载和核对**：下到 App 自己的缓存目录（`cache/update/`），边下边算 SHA-256；大小或 SHA-256 和 `latest.json` 对不上就删掉、不装，提示重新下载。对上了，再从安装包里读一遍：包名是不是 `cn.flowlang.app`、versionCode 是不是比现在的大、签名证书是不是和手机上这个一样。哪一样不对都不装。
- **安装**：交给手机自己的安装程序（`PackageInstaller` 会话，`USER_ACTION_REQUIRED`）。手机会弹「要更新此应用吗？」，用户点「更新」才装；装好后旧版本被替换，App 会关掉，再点开就是新的。
  - 要 `REQUEST_INSTALL_PACKAGES`，只写在 `src/prod/AndroidManifest.xml` 里，内测版没有。安卓要求用户在设置里给语流打开「安装未知应用」：第一次在 App 里装新版本时，先用 App 自己的话说明为什么要，再打开那一页（开关叫「允许从此来源安装应用」）。不打开就装不了，App 会给出下载页 `flowlang.cn/download`。
  - 装的结果由不导出的 `InstallReceiver` 收，只认自己这次的会话。
- **手机上存的**：SharedPreferences `flow-update`：上次看新版本的日期、点了「稍后」的版本和日期。下载的安装包交给安装程序后就删。看新版本时不带登录 cookie，只发普通的请求和 User-Agent。
- **测试**：先 `adb reverse tcp:18765 tcp:18765`，再用 `--es flow.update_url http://127.0.0.1:18765/latest.json` 打开调试包，就指到这台 Mac 上的测试服务器（只有调试包认这个参数；调试包的网络设置只对 `127.0.0.1` 放开 http）。不用 `10.0.2.2`：目标是 Android 17 的 App 默认连不了局域网地址。正式包只看 flowlang.cn，只用 https。
- 1.0.1 及更早的版本没有这个功能，要用户自己到下载页下载新版本覆盖安装一次。

## 权限和隐私

| 权限 | 为什么要 |
|---|---|
| `INTERNET` | 打开网站 |
| `RECORD_AUDIO` | 跟读、口语对话、发音练习；App 自己从不打开，只在网页要录音时打开 |
| `POST_NOTIFICATIONS` | 复习提醒（Android 13 以上要单独问） |
| `FOREGROUND_SERVICE`、`FOREGROUND_SERVICE_MEDIA_PLAYBACK`、`WAKE_LOCK` | 锁屏以后整篇朗读还能继续（网页调用原生朗读以后才用到，见上面「原生声音」） |
| `RECEIVE_BOOT_COMPLETED` | 重启手机以后把提醒排回去 |
| `SCHEDULE_EXACT_ALARM` | 提醒准点（手机允许时） |
| `ACCESS_NETWORK_STATE` | 由 Media3（ExoPlayer）带进来，用来看网络类型；不弹窗 |
| `REQUEST_INSTALL_PACKAGES`（只有正式版） | 在 App 里装新版本；要用户自己在设置里打开「安装未知应用」，第一次在 App 里装新版本时才问（见上面「新版本」） |

- 不加任何第三方 SDK，不做统计和跟踪。用到的库只有 AndroidX、Media3、kotlinx-coroutines。
- WebView 的使用统计和 Safe Browsing 网址检查都关掉了，App 不会因为 WebView 给 Google 发数据。
- 不备份到云端（`allowBackup=false`）：登录 cookie 和手机上存的东西不会被带到别的手机上。
- App 只连本站和媒体域名，只用 https。看新版本时读 `flowlang.cn/download/latest.json`，下载安装包，都不带登录 cookie。

## 测试

- 单元测试（`src/test`，JVM，CI 上可以跑），共 32 个：
  - 句子定位、上一句和下一句的规则、复读（`Sentences`，和网页 `NAR`、`LONG` 的规则一致）；
  - 提醒排期（`Planner`，用 iOS 的同一组例子）；
  - WAV 文件头；
  - `.ics` 解析；
  - 新版本：`latest.json` 的读法、版本比较、什么时候看、「稍后」当天不再提示（`UpdateInfo`、`UpdateGate`）。
- 新版本的整个流程在模拟器上手动测过（调试包，见上面「新版本」里的测试办法）：提示、「稍后」、下载和核对、「安装未知应用」的说明和设置页、系统的「要更新此应用吗？」、装好后是新版本；SHA-256 不对、签名不对、没打开权限、在确认页点「取消」，都不装。
- 界面测试（`src/androidTest`，模拟器或真机，打开内测版，以游客身份，不出声），共 7 个：
  - 打开网站，桥和 `FlowApp` 的字段都在，UA 正确；
  - 登录页；
  - 播放一篇有录音的文章，下一句、暂停、记住读到哪儿；
  - 通知栏里的暂停和下一句，网页收到 `why = remote`；
  - 麦克风权限弹窗，录 2 秒 WAV，同一段录音只给一次；
  - 打开提醒，用 `notify.test` 按给定计数排两周，`pending()`，再关掉；
  - 服务器给不出的句子由手机自带的声音读，`audio` 事件带 `fail`。
- 截图在共享笔记 `android-shots/`。

## 以后

- **上应用商店**：
  - Google Play：要一次性 25 美元的开发者账号；还要填数据安全表，以及隐私政策网址；个人账号第一次上架前，要先找一批测试者做一轮封闭测试（人数和天数以当时的规定为准）。
  - 国内应用商店（华为、小米、OPPO、vivo、应用宝）：要软件著作权、App 备案（工信部）、隐私政策和权限说明；有的商店只收企业开发者；华为还要单独适配鸿蒙。现在先不办。
- 纯血鸿蒙（HarmonyOS NEXT）装不了 APK，要单独做鸿蒙版。
- App Links（点 flowlang.cn 的链接直接进 App）：要在网站上放 `/.well-known/assetlinks.json`。
- 推送：国内没有统一的推送服务，复习提醒用本地通知，不需要推送。
