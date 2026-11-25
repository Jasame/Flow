# 语流 Android App

原生外壳加关键功能原生，和 iOS 版（`ios/`，语流 20）做法一样：Kotlin 写的外壳里用 WebView 打开网站，网站一改，App 里马上就是新的；整篇朗读、录音、复习提醒改用安卓原生来做。网页通过 `window.FlowApp` 调用这些原生功能，两个平台共用一套约定。

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

## 发 APK（给自己和内测的人装）

```bash
tools/release-apk.sh both     # → dist/flow-beta-<版本>.apk 和 dist/flow-<版本>.apk
```

- 每发一个新 APK，先把 `gradle.properties` 里的 `flow.versionCode` 加 1。只有 versionCode 更大，手机才会把它当成升级。
- 签名用主人 Mac 上的 `~/.flow-android/flow-release.jks`（别名 `flow`）。它的密码在 macOS 钥匙串里，条目名是 `flow-android-release`。脚本从钥匙串里取密码，再交给 `apksigner`；Gradle 碰不到密码，仓库里也没有。
- **这个 keystore 要备份**（加密 U 盘、密码管理器都行），密码也要一起备份。丢了以后，新版本就不能覆盖安装了：每个人都得先卸载再装，App 里的登录也要重新登。证书指纹是 SHA-256 `76:88:9C:6F:7E:E0:C6:C6:72:84:4B:05:17:91:9C:33:FB:6D:86:40:D2:EF:22:6A:47:20:AF:2B:12:82:89:27`。
- 怎么装到手机上，见 [INSTALL-zh.md](INSTALL-zh.md)。
- 改 `tools/release-apk.sh` 或别的签名相关内容的 PR，合并前要先问用户（`docs/releases.md` 2026-11-25 11:15 的规矩）。把 APK 发给试用的同学之前，也要先问用户，并提前告诉语流 03，由它把指南里 App 的权限说明放上去。

CI（Linux）上跑 `./gradlew assembleBetaDebug testBetaDebugUnitTest`，不需要签名：release 包不签名，`release-apk.sh` 只在主人的 Mac 上跑。

## 外壳做了什么（`MainActivity`）

- **登录**：用 WebView 自己的 cookie（`flow_session`，30 天），离开页面时写进磁盘，关掉 App 再打开还是登录状态。
- **返回键和返回手势**：先关网页上开着的弹层（sheet），再回到上一页；已经是第一页时，App 退到后台（正在播的文章继续播）。网页可以在 `flowapp:back` 事件里 `preventDefault()`，自己处理返回。
- **外链**：别的网站、`mailto:`、`tel:` 用系统浏览器或对应的 App 打开。只有本站在 App 里打开。
- **刘海、状态栏、导航栏、键盘**：页面夹在它们中间，周围用网页自己的颜色（浅 `#FBFAF6`，深 `#101412`）。深色模式切换时不用重新加载，页面和状态栏一起变。键盘弹出时，页面缩到键盘上面。
- **User-Agent** 末尾加 `FlowAndroid/<版本>`，例如 `… Mobile Safari/537.36 FlowAndroid/1.0.0`。
- **「加到手机日历」**（`reminder.ics` 链接）：App 先问用「App 通知」还是「系统日历」。选系统日历，就打开手机日历的新建日程页，内容已经填好，不需要日历权限。
- 反馈里的「添加截图」可以从相册选图片。网页出不来时显示「网络连不上 · 重试」。系统回收网页进程以后，App 自己重新打开网页。

## 网页和 App 之间的桥（`bridge/`、`assets/flowapp.js`）

约定和 iOS 共用（以 `ios/README.md`「网页和 App 之间的桥」为准，共用的 `docs/native-bridge.md` 由语流 20 整理）。网页只调 `window.FlowApp`，不判断是哪个平台；平台不同的文字用 `FlowApp.platform`（这里是 `'android'`）。

**传输方式**：

- App 在网页脚本运行之前放好 `window.FlowApp`（`WebViewCompat.addDocumentStartJavaScript`），只放在本站的源上。
- 消息走 `WebViewCompat.addWebMessageListener` 的 `flowNative` 通道：网页发 `{id, cmd, args}`，App 回 `{id, ok, result | error}`，事件用 `{ev, detail}` 发过来。
- App 只认本站主框架发来的消息。手机上的 WebView 太旧、缺这两个功能时，App 什么都不加，网页就按普通浏览器的方式运行。

| 调用 | 安卓的做法 |
|---|---|
| `FlowApp.v` / `app` / `platform` / `has(k)` | `1`、App 版本、`'android'`；`has`：`audio`、`rec`、`notify`、`speech` |
| `FlowApp.on(type, fn)` → 取消订阅的函数；`off` | 同时发 `window` 事件 `flowapp:<type>` |
| `audio.play(o)` / `pause()` / `resume()` / `stop()` / `step(±1)` / `seek(i)` / `set({rep, gap, rate})` / `state()` / `progress(key)` | 见下面「原生声音」。`resume()` 返回当前状态（`key`、`state`、`i`），网页靠它判断要不要从头再放 |
| `rec.permission()` / `ask()` / `start({max, format})` / `stop()` / `cancel()` | 见下面「录音」 |
| `notify.permission()` / `ask()` / `sync(r)` / `off()` / `settings()` | 见下面「复习提醒」。`off()`、`settings()` 是安卓多出来的 |
| `speechSynthesis` | 安卓 WebView 自带的 `speechSynthesis` 背后没有声音（安卓微信也一样），App 把它换成手机自己的 TextToSpeech。接口和事件跟浏览器一样（`start`、带 `charIndex` 的 `boundary`、`end`、`error`），网页不用改。不支持句子中间暂停 |

## 原生声音（`audio/`）

整篇朗读（「听」的播放全文、「读」的伴读）由 App 来放，用 Media3 的 ExoPlayer 加 `MediaSessionService`：

- 锁屏和通知栏显示「标题 · 第 3 / 20 句」，可以播放、暂停、上一句、下一句。耳机按钮、蓝牙按钮也能用。
- 来电、闹钟、导航语音这类短暂打断时暂停，打断结束后自己接着放。别的 App 开始放声音时暂停，不会自己接着放。拔下耳机时暂停。
- 播放引擎（`FlowAudio`）在 App 里自己跑，网页在后台被挂起也不影响，下一句由 App 接上。
- `audio` 事件 `{key, state, i, t, note, why, title, n}`：状态变了、换到下一句时发；页面回到前台、重新加载以后，再发一次当前状态。`audio-tick` 事件 `{key, i, t, at, rate}`：页面在前台时每秒 4 次，网页用 `t + (现在 − at) × rate` 让词的高亮在两次 tick 之间也能走。
- **有录音**（`src` 加 `sentences: [[s, e], …]`）：一个文件从头放到尾，或者按句放（`loop`：复读 `rep` 遍，句后停 `gap` 毫秒）。本站的文件出错时，换到 `alt`（网页给的媒体域名线路），位置不变。登录 cookie 只发给本站，不发给媒体域名。
- **没有录音**（`texts` 加 `voice`、`pack`）：一句一句请求 `POST /api/next/tts`，用网页传来的 `csrf`，以登录学员的身份；同时先准备后面两句。某一句生成不出来时，用手机自带的声音读这一句，`note` 里说明原因。服务器说今天的额度用完了（`cap`）或功能没开（`off`）以后，这篇剩下的句子不再去问服务器。
- 播过的文件存进 150 MB 的缓存，重复听不再下载。读到哪儿也由 App 记一份（30 天、最多 100 篇），App 被关掉以后还能接着读。

## 录音（`rec/`）

- 16 kHz 单声道。`wav` 是 16 位 PCM（每秒 32 KB），和网页的 FLOW_SAY_WAV 格式相同；`m4a` 是 AAC。超过 45 秒默认用 m4a，因为服务器最多收 1.5 MB。
- `stop()` 返回 `{ok, mime_type, data(base64), ms}`，和网页 `MIC.payload(blob)` 的格式一样。
- 录音时，正在放的整篇先暂停（`why = other`），别的 App 的声音也暂时停下。
- 来电或者 App 退到后台时，录音提前结束：已经录到的部分保留，`rec` 事件会报 `cut`。安卓只允许前台的 App 用麦克风。
- 麦克风权限第一次由系统弹窗询问（网页会先说明为什么要用）。用户拒绝过一次以后，再要用时 App 先说明用途：「语流要用麦克风录下你说的英语（跟读、口语对话、发音练习），只在你点录音的那几秒打开，录音只用来给你批改。」被彻底拒绝以后，App 给出「去设置」按钮。
- 没接桥的页面照旧用 `getUserMedia`：手机已经允许 App 用麦克风时，本站直接可以用。

## 复习提醒（`notify/`）

- 学员点「到点用 App 通知提醒」（`notify.ask()`）之后才打开提醒。Android 13 以上，系统还会单独弹窗问能不能发通知。
- `sync(r)`：`r` 是 `/api/next/vocab` 返回的 `reminder`，可以带上 `forecast`。规则和服务器发邮件一样（`Planner`，有单元测试）：
  - 今后 7 天，每天 `hour:00` 提醒一次；`forecast` 显示那天没有词要复习，就不提醒。
  - `once`（学员约好的一次，语流 11 的 `remindOnce()`）替掉在它之前的每日提醒，`once` 当天也不再有每日那条。
- App 打开、回到前台时，自己用登录 cookie 拿一次 `/api/next/vocab`，重新排。退出登录以后，提醒全部取消。重启手机、改时间或时区以后，提醒会重新排上。
- 点通知打开 `#/review`。
- **精确闹钟**：Android 12 和 13 默认允许，提醒准点到。Android 14 起，新装的 App 默认不允许，只有学员在「闹钟和提醒」里打开才行。没有这个权限时，用 10 分钟的时间窗，提醒最多晚 10 分钟左右。权限一打开，App 自动改成准点（模拟器上测过）。我们不用 `USE_EXACT_ALARM`：它是给闹钟类 App 用的，以后上 Google Play 会被拒。

## 权限和隐私

| 权限 | 为什么要 |
|---|---|
| `INTERNET` | 打开网站 |
| `RECORD_AUDIO` | 跟读、口语对话、发音练习；只在录音的那几秒打开 |
| `POST_NOTIFICATIONS` | 复习提醒（Android 13 以上要单独问） |
| `FOREGROUND_SERVICE`、`FOREGROUND_SERVICE_MEDIA_PLAYBACK`、`WAKE_LOCK` | 锁屏以后整篇朗读还能继续 |
| `RECEIVE_BOOT_COMPLETED` | 重启手机以后把提醒排回去 |
| `SCHEDULE_EXACT_ALARM` | 提醒准点（手机允许时） |
| `ACCESS_NETWORK_STATE` | 由 Media3（ExoPlayer）带进来，用来看网络类型；不弹窗 |

- 不加任何第三方 SDK，不做统计和跟踪。用到的库只有 AndroidX、Media3、kotlinx-coroutines。
- WebView 的使用统计和 Safe Browsing 网址检查都关掉了，App 不会因为 WebView 给 Google 发数据。
- 不备份到云端（`allowBackup=false`）：登录 cookie 和手机上存的东西不会被带到别的手机上。
- App 只连本站和媒体域名，只用 https。

## 测试

- 单元测试（`src/test`，JVM，CI 上可以跑）：
  - 句子定位、上一句和下一句的规则、复读（`Sentences`，和网页 `NAR`、`LONG` 的规则一致）；
  - 提醒排期（`Planner`）；
  - WAV 文件头；
  - `.ics` 解析。
- 界面测试（`src/androidTest`，模拟器或真机，打开内测版，以游客身份）：
  - 打开网站，桥已就位，UA 正确；
  - 登录页；
  - 播放一篇有录音的文章，下一句、暂停、记住读到哪儿；
  - 通知栏里的暂停和下一句，网页收到 `why = remote`；
  - 麦克风权限弹窗，录 2 秒 WAV；
  - 打开提醒、排期，再关掉。
- 截图在共享笔记 `android-shots/`。

## 以后

- **上应用商店**：
  - Google Play：要一次性 25 美元的开发者账号；还要填数据安全表，以及隐私政策网址；个人账号第一次上架前，要先找一批测试者做一轮封闭测试（人数和天数以当时的规定为准）。
  - 国内应用商店（华为、小米、OPPO、vivo、应用宝）：要软件著作权、App 备案（工信部）、隐私政策和权限说明；有的商店只收企业开发者；华为还要单独适配鸿蒙。现在先不办。
- 纯血鸿蒙（HarmonyOS NEXT）装不了 APK，要单独做鸿蒙版。
- App Links（点 flowlang.cn 的链接直接进 App）：要在网站上放 `/.well-known/assetlinks.json`。
- 推送：国内没有统一的推送服务，复习提醒用本地通知，不需要推送。
