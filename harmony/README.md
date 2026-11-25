# 语流鸿蒙 App（HarmonyOS NEXT）

语流 C4。做法和 iOS 版（`ios/`）、安卓版（`android/`）一样：ArkTS 写外壳，里面用 ArkWeb 打开网站，网站一改，App 里马上就是新的；整篇朗读、录音、复习提醒用鸿蒙原生来做。网页通过 `window.FlowApp` 调用这些原生功能，几个平台共用一套约定，见 [docs/native-bridge.md](../docs/native-bridge.md)。方案和真机测试清单在共享笔记 `harmony-plan.md`、`harmony-test.md`。

纯血鸿蒙（HarmonyOS 5.0 及以上，API 12 起）装不了安卓 APK，所以要单独做这一版。

| | 内测版 | 正式版 |
|---|---|---|
| 显示名 | 语流内测 | 语流 |
| 包名（bundleName） | `cn.flowlang.app.beta` | `cn.flowlang.app` |
| 打开的网站 | https://flow.jasa.hk | https://flowlang.cn |
| product（build-profile.json5） | `default` | `prod` |

两个包名不同，可以同时装在一台手机上。最低 HarmonyOS 5.0（compatibleSdkVersion 5.0.0(12)），网页按 Chromium M114 的底线写（harmony-plan.md 第 1 节）。

## 原生做了什么

| 能力 | 做法 |
|---|---|
| `audio` 整篇朗读 | AVPlayer 播放；AVSession 让锁屏和控制中心显示标题和「AI 朗读 · 第 n / N 句」，有播放、暂停、上一句、下一句；长时任务 AUDIO_PLAYBACK 让锁屏以后接着读。来电时暂停，系统说可以继续时接着放；拔耳机暂停 |
| `rec` 录音 | AudioCapturer 录 16 kHz 单声道 WAV；超过 40 秒用 AVRecorder 录 m4a（AAC 16 kHz）。来电或切到后台时停下（cut），录到的部分还在 |
| 「加到手机日历」 | 网页里的 `/api/next/vocab/reminder.ics` 链接由 App 接下来处理：拿到这份 .ics，解析出第一个日程（`common/Ics.ets`），再用 Calendar Kit 的 `editEvent` 打开系统日历的「新建日程」页，标题、时间、准时提醒、每天重复都已填好，学员点保存。不要日历权限，也不开浏览器（2026-11-26 模拟器实测）。**用户 2026-11-26 选定：鸿蒙版先只用邮件和日历提醒** |
| `notify` 复习提醒 | **还没打开**（`has('notify')` 为 false），网页照浏览器的做法用邮件和「加到手机日历」。<br>原因：第三方 App 的后台代理提醒要华为按包名开通。开通之前 `publishReminder` 回 1700002，系统日志写 `ReminderControl … notification not allowed`，上限是 0（5.0.1 模拟器，2026-11-26 实测）。<br>代码已经写好（`notify/`：规则和 iOS、安卓一样，最多排 28 条），名额开通以后在 `Bridge.FEATURES` 里加回 `'notify'` |
| `speech` | **不做**。鸿蒙的系统朗读是 Core Speech Kit，属于系统自带的 AI 能力，按规矩不接。服务器的句子做不出来时，朗读暂停（why = error），`fail` 交给网页说明原因，点继续再试 |

## 外壳

- UA 末尾加 `FlowHarmony/<版本>`；`FlowApp.platform` 是 `'harmony'`。
- 深色模式跟着手机走（`WebDarkMode.Auto`），切换不用重新打开。
- 键盘弹出时网页变矮（`RESIZE_CONTENT`），和安卓 App 一样。
- 侧滑返回：先发 `flowapp:back`，再关掉开着的面板，然后回上一页，最后退到后台。
- 别的网站、下载链接、`mailto:` 交给系统打开。
- 没接桥的页面照旧用 getUserMedia 录音：只给本站，系统允许麦克风以后自动同意。

## 构建

要用 DevEco Studio（Apple 芯片的 Mac，带 HarmonyOS SDK 和模拟器）。用 DevEco 打开 `harmony/` 这个目录。每次构建时，`entry/hvigorfile.ts` 会把共用的 `native/flowapp.js` 复制进 `rawfile/`，这个副本不进 git。

命令行，用 DevEco 自带的工具（DevEco Studio 26.0.0，装在 /Applications）：

```bash
A=/Applications/DevEco-Studio.app/Contents
export JAVA_HOME=$A/jbr/Contents/Home DEVECO_SDK_HOME=$A/sdk
export PATH="$JAVA_HOME/bin:$A/tools/node/bin:$A/tools/ohpm/bin:$A/tools/hvigor/bin:$A/sdk/default/openharmony/toolchains:$PATH"
cd harmony && ohpm install                                                # 第一次：测试框架 hypium
hvigorw assembleHap --mode module -p product=default -p buildMode=debug   # 内测版调试包
hvigorw assembleHap --mode module -p product=prod -p buildMode=release    # 正式版
hvigorw test -p product=default -p module=entry@default -p isLocalTest=true -p buildMode=test   # 本地单元测试（不要模拟器）
```

单元测试的结果在 `entry/.test/default/intermediates/test/coverage_data/test_result.txt`（最后一行是总数）。没签名的包在 `entry/build/<product>/outputs/default/entry-default-unsigned.hap`；签好名以后用 `hdc install <hap>` 装到模拟器或手机上。

**测试时一律不出声**（docs/native-bridge.md §9）：
```bash
hdc shell aa start -a EntryAbility -b cn.flowlang.app.beta --pb flow.mute true
```
模拟器也要静音。用完就关掉模拟器和 DevEco，这台 Mac 内存紧。

## 模拟器（这台 Mac，2026-11-26）

- 镜像：HarmonyOS 5.0.1（API 13，M114 内核），2.36 GB，解压后放在 `~/.flow-harmony/emulator/images`，实例名 `flow501`，内存 4 GB。
- 只有 DevEco 的「国家/地区」是中国大陆时才能下载（`~/Library/Application Support/Huawei/DevEcoStudio26.0/options/country.region.xml`）。DevEco 默认跟着 macOS 的地区走。
- 启动时会再问一次协议，用户 2026-11-25 已经同意：
  ```bash
  echo y | $A/tools/emulator/Emulator -start flow501 -noWindow
  ```
- 用完一定要关掉：
  ```bash
  $A/tools/emulator/Emulator -stop flow501
  ```
- 截图：
  ```bash
  hdc shell snapshot_display -f /data/local/tmp/s.jpeg && hdc file recv /data/local/tmp/s.jpeg .
  ```
- 看网页：调试包开着 Web 调试。
  ```bash
  hdc fport tcp:9333 localabstract:webview_devtools_remote_<pid>
  ```
  然后打开 `http://127.0.0.1:9333/json`，用 DevTools 协议连上去。
- 2026-11-26 在模拟器上测过：
  - 整篇朗读：播放、下一句、暂停后从同一秒接着放、播到一句 1.5 秒以后按上一句先回本句开头、读完收到 `ended`、进度保存；
  - 锁屏：卡片写「标题 / AI 朗读 · 第 n / N 句」，锁屏时接着读；锁屏上的暂停、播放能用，网页收到 `why: remote`；停下后卡片会撤掉；
  - 通知和麦克风：系统弹窗里写的是「语流内测」，麦克风弹窗显示我们写的用途说明；
  - 录音：WAV 文件头正确，到时自动停，`rec` 先发 `recording` 再发 `done`。第一段声音约 0.3 秒后到。模拟器的虚拟麦克风偶尔会断流，`ms` 按实际录到的声音算，真机上还要再看。
- 2026-11-26 实测：UA 是 `Mozilla/5.0 (Phone; OpenHarmony 5.0) … Chrome/114.0.0.0 … ArkWeb/4.1.6.1 Mobile FlowHarmony/1.0.0`；FlowApp 的 platform 是 harmony，能力是 audio、rec、notify；MediaRecorder 支持 webm/opus；`speechSynthesis` 存在，但一个声音都没有。

## 签名

- 调试：DevEco「自动签名」，要用户自己登录华为开发者账号（个人、实名）。
  - 只连模拟器也行，DevEco 要先认到一台设备才能生成；
  - DevEco 会把签名配置写进 `build-profile.json5` 的 `signingConfigs`，路径指向 `~/.ohos/config`，口令是加密的。内测 product 还要加上 `"signingConfig": "default"`；
  - **这几行不要提交**：提交时只暂存去掉签名的版本。
- 调试包只能装在登记过 UDID 的手机上，有效期 1 年。查 UDID：`hdc shell bm get --udid`。
- 上架华为应用市场、邀请测试都要先在 AppGallery Connect 建应用。这些由用户自己做，发版和服务器归 A1。
