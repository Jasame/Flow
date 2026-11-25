# 语流 Flow 桌面版（Windows + macOS）

Tauri 2 做的「原生外壳 + 关键功能原生」：窗口里就是网站（正式版 https://flowlang.cn ，内测版 https://flow.jasa.hk ），
原生只补浏览器标签页做不好的几件事。和 iOS（`ios/`，语流 C1）、安卓（语流 C2）共用同一个网页接口 `window.FlowApp`（v1）。

| | Windows | macOS |
|---|---|---|
| 网页引擎 | 系统自带的 WebView2（Win 10/11 都有，没有时安装包会自动装） | 系统自带的 WKWebView |
| 安装包 | NSIS `语流_<版本>_x64-setup.exe`，装在当前用户下，不要管理员 | `语流.app` / `.dmg`，Apple 芯片和 Intel 通用 |
| 系统媒体控制 | SMTC（音量浮层、锁屏）+ 键盘媒体键 | 控制中心「正在播放」+ 键盘媒体键（F7 F8 F9） |
| 复习提醒 | 系统定时通知（App 关着也会到） | 系统定时通知（App 关着也会到） |
| 开关在哪 | 任务栏右下角托盘图标的菜单 | 菜单栏「语流」菜单 |
| 签名 | 还没有（会出 SmartScreen 提示） | 还没有 Apple 开发者账号（ad-hoc 签名，第一次要在「隐私与安全性」里放行） |

给用户看的安装说明：[INSTALL-zh.md](INSTALL-zh.md)。

## 两个配置

- **Release**（`src-tauri/tauri.conf.json`）：「语流」，`cn.flowlang.app`（和 iOS 正式版同一个），打开正式版，链接协议 `flowlang://`。
- **Beta**（叠加 `src-tauri/tauri.beta.conf.json`）：「语流内测」，`cn.flowlang.app.beta`（和 iOS 内测版同一个），打开内测版，`flowlang-beta://`。

开哪个网站由 bundle identifier 决定（`src-tauri/src/site.rs`），两个可以同时装。

## 原生做了什么

| 功能 | 怎么做 | 代码 |
|---|---|---|
| 系统媒体控制、媒体键 | 网页照常自己放声音；注入的脚本盯住网页的 `navigator.mediaSession`（`MS.claim` 设的标题、登记的动作、播放/暂停），交给系统显示；按键回来时调网页登记的动作（play / pause / previoustrack / nexttrack / stop），进度还是网页管。系统播放器的副标题写「AI 朗读」（语流的朗读都是合成声音，按《人工智能生成合成内容标识办法》显式标出） | `bridge.js`、`media.rs`（souvlaki：SMTC / MPNowPlayingInfoCenter） |
| 复习提醒 | 规则和 iOS（`ReminderPlan.swift`）、共用约定 `docs/native-bridge.md` §5 一样：北京时间，今后 14 天每天 hour:00，只在有词的日子（今天看还剩多少，含 later；以后看 forecast 累计到那天，加词书没背完时每天的新词）；「这次什么时候复习」之前不排每天那条，那天有词才提醒，提醒过的那天不再排。数据是整份 `/api/next/vocab`，在页面里用页面的登录去拿：App 打开、回到前台（最多半小时一次）、网页调 `sync(r)` 时。交给系统定时，App 关着也会到。退出登录（401）就撤掉 | `schedule.rs`、`notify/`（macOS UserNotifications，Windows 定时 toast） |
| 点提醒 | 打开 App 到「复习」页（macOS 走通知回调，Windows 走 `flowlang://review`） | `notify/`、`site.rs` |
| 开机自启 | 可选，默认关；开机启动时不弹窗口 | `tauri-plugin-autostart` |
| 窗口 | 记住大小、位置、是否最大化；macOS 关窗口留在 Dock（⌘Q 退出），Windows 关窗口就退出，可选「关窗口后留在托盘」 | `tauri-plugin-window-state`、`lib.rs` |
| 链接 | 本站页面在窗口里；别的网站、邮件链接、日历文件（`.ics`）交给系统；`target=_blank` 同样处理 | `links.rs` |
| 登录 | 系统网页引擎自己的 cookie 存储，关掉再开还是登录状态 | （默认行为） |
| 麦克风 | 只给本站页面（跟读、口语、发音）；摄像头、定位一律拒绝 | `lib.rs` `on_permission_request` |
| User-Agent | 末尾 `FlowDesktop/<版本> (Windows)` 或 `(macOS)` | `ua.rs` |
| 菜单 | macOS：语流 / 编辑（⌘C ⌘V 要靠它）/ 显示（后退 ⌘[、前进 ⌘]、重新载入 ⌘R、缩放）/ 窗口 / 帮助；Windows：托盘菜单 | `menu.rs` |
| 自动更新 | 0.1.1 起：正式版启动时查新版本，后台下载、退出时装上；只装用户私钥签过名的（见下） | `updater.rs`、`tools/make_update.py` |

## 网页接口 `window.FlowApp`（桌面这边）

三个平台共用的约定在 `docs/native-bridge.md`（语流 C1 牵头）。网页一律先判断 `window.FlowApp && FlowApp.has(...)`。桌面这边：

```
FlowApp.v / app / build / beta   1、App 版本、构建的提交（CI 的 GITHUB_SHA 前 7 位，本机是 "dev"）、是不是内测版
FlowApp.platform   "windows" | "macos"（iOS 是 "ios"，安卓 "android"）
FlowApp.has(k)     'notify' → true，'media' → true，'audio' / 'rec' / 'speech' → false（桌面网页自己放、自己录）
FlowApp.call('hello')        → {v, app, build, platform, features}；call('app.visible') 把媒体状态再发一次
FlowApp.notify.permission()  → 'granted' | 'denied' | 'undetermined' | 'provisional'
FlowApp.notify.ask()         → true / false（macOS 第一次弹系统框；Windows 不问，看「设置 → 通知」）
FlowApp.notify.sync(r)       r 不为空：照整份 /api/next/vocab 重排；null 或 {app: false}：关掉 App 的提醒
FlowApp.notify.pending()     → [{id, at, title, body}]（系统里排着的）
FlowApp.on(type, fn) → 退订函数；off(type, fn)；同时发 window 事件 flowapp:<type>
```

只在本站注入（`location.origin` 对得上才挂），`FlowApp` 冻结不可改。Tauri 的 IPC 只对两个站点的页面开放，且只能调这几条命令
（`capabilities/site.json`，命令各有权限）。

## 本机开发

要 Rust（rustup，stable）和 Node 22。

```bash
cd desktop
npm ci
npm test                 # Rust 单元测试（日程规则、链接、UA、媒体键、设置……）
npm run dev:beta         # 开内测版（调试版有开发者工具：右键 → 检查元素）
npm run build:beta       # 打 Beta 安装包；npm run build 打 Release
```

调试版可以指向本机服务器：`FLOW_DESKTOP_SITE=http://127.0.0.1:8090/ npm run dev`（正式构建忽略这个变量）。
`FLOW_DESKTOP_THEME=light`（或 `dark`）让窗口和网页用浅色（深色），不管系统怎么设，截图用（只在调试版有效）。
`FLOW_DESKTOP_LOG=1` 在终端打印日志（只打到 stderr，不写文件、不上传）。

**测试时不出声**：`FLOW_MUTE=1`（冒烟测试总是这样）。网页的 `<audio>` 静音、Web Audio 走一个音量为 0 的节点、浏览器朗读音量 0，
通知不带提示音；播放、事件、系统媒体控制照常，只是听不见。要真的放出声音的测试，先问用户。

### 冒烟测试

```bash
<app 可执行文件> --smoke-test=/tmp/smoke.json && python3 tools/check_smoke.py /tmp/smoke.json
```

打开网站，在页面里检查 `FlowApp`、UA、通知权限、mediaSession 接到原生，写报告后退出（90 秒没报告退出码 2）。
CI（`.github/workflows/desktop.yml`）在 windows-latest 上装好 NSIS 安装包再跑一次，在 macos-latest 上跑 .app，截图和安装包都在 run 的 artifacts 里（留 14 天）。

### 出安装包

- **内测包（Beta）**：每次合进 main（改到 `desktop/` 时）自动构建，在那次 Desktop run 的 artifacts 里，留 14 天，用户自己随时可以下载装。
- **正式包（Release）**：用户同意分发某个版本以后，在 GitHub 的 Actions → Desktop → Run workflow，分支选 main（就是那个提交），
  channel 选 `release`。产物留 90 天。分发的就是这一次构建。
- 产物只在 Actions 里：不自动传到 GitHub Releases 或任何地方。发给试用同学、放到公开的地方、开自动更新的通道，都要先问用户。

图标：`python3 tools/make_icon.py` 画 1024 的圆角方块（和网站同一个 logo），再 `npx tauri icon src-tauri/app-icon.png -o src-tauri/icons`（删掉生成的 android/、ios/）。

## Linux（2026-11-25 开工，方案和用户的选择见共享笔记 linux-desktop-plan.md）

- **包**：AppImage（所有发行版通用，能自动更新，打包了放声音用的 GStreamer）和 deb（Ubuntu 22.04+ / Debian 12+ / 深度 / 统信 UOS / 麒麟，
  依赖 `gstreamer1.0-plugins-good gstreamer1.0-libav`）。x86_64。rpm 以后再说。
- **网页引擎**：系统的 WebKitGTK 4.1。App 会打开麦克风（WebKitGTK 默认关着），录音能不能用要真机实测。
- **系统媒体控制**：走 MPRIS（GNOME、KDE 的媒体控件、键盘媒体键），名字是 `org.mpris.MediaPlayer2.<bundle id>`。
- **提醒**：Linux 没有系统替 App 定时弹通知的接口，所以**只在 App 开着时提醒**。App 自己计时，到点弹 freedesktop 通知，点通知打开复习页。
  Linux 上「关窗口后留在托盘」默认打开，再配合「开机时启动」，就等于一直开着。
  GNOME 没有托盘区（要装 AppIndicator 扩展）；关掉窗口后再从应用菜单打开一次，窗口就会回来。
- **自动更新**：只有 AppImage 会自己换新版。deb 每次更新都要管理员密码（pkexec），所以 deb 只发一条「有新版本，到下载页下载」的通知。
  latest.json 里多一项 `linux-x86_64`，指向签过名的 AppImage（`make_update.py prepare --appimage … --deb …`）。
- **构建**：GitHub 的 ubuntu-22.04 机器（desktop.yml 的 linux job，由 A2 配，要用户同意），冒烟测试在 xvfb 和 dbus-run-session 里跑。
- **真机测试**：请有 Linux 电脑的同学按共享笔记 linux-desktop-test.md 试。

## 签名（现在都没有，只记在这里）

- **macOS**：正式分发要 Apple 开发者账号（和 iOS 共用一个，用户还没有）。在那之前是 ad-hoc 签名的 .app，下载后第一次打开要到
  「系统设置 → 隐私与安全性」点「仍要打开」（INSTALL-zh.md）。有账号以后：Developer ID Application 证书 + 公证（notarize），
  在 `tauri.conf.json` 的 `bundle.macOS.signingIdentity` 填证书名，CI 里用 `APPLE_CERTIFICATE`、`APPLE_ID` 等 secrets。
- **Windows**：没有代码签名证书时，下载运行会出现 SmartScreen「Windows 已保护你的电脑」，内测可以接受（INSTALL-zh.md）。
  以后买 OV/EV 证书或用 Azure Trusted Signing，再在 `bundle.windows` 里配。

## 自动更新（0.1.1 起，正式版）

用户 2026-11-25 选的：打开自动更新，私钥只放用户本机。

- **怎么更新**：正式版「语流」打开后大约 20 秒，去查 `https://flowlang.cn/desktop/latest.json`。服务器只看到网络地址，不带账号。
  - 有新版本：在后台下载，**关掉语流（⌘Q / 退出）时装上**，下次打开就是新版。菜单「检查更新…」可以马上装，装完自己重启。
  - 内测版和冒烟测试从不检查。
- **只装签了名的**：更新包要用用户的私钥签名，App 里存着公钥（`tauri.conf.json` 的 `plugins.updater.pubkey`），签名对不上的一律不装。
  - 私钥在用户 Mac 上的 `~/.tauri/flow-updater.key`，有密码，**不进仓库、笔记和 GitHub**，C3 也不碰。
  - **私钥丢了，已经装好的 App 就再也收不到更新**，只能让大家重新下载安装，所以请用户自己备份私钥和密码（比如放进密码管理器）。
- **从 0.1.0 升上来**：0.1.0 里没有更新功能，要到下载页手动装一次 0.1.1，之后才会自动更新。
- **Mac 上**：App 要放在「应用程序」里才能自己替换自己；直接从 dmg 或「下载」文件夹里打开的，系统会把它放到只读的临时位置，更新装不上，下次打开还是旧版。

### 发一个新版本

1. 改版本号：`src-tauri/tauri.conf.json`、`src-tauri/Cargo.toml`、`package.json` 三处一致，PR 合进 main（Desktop 两个检查要绿）。
2. 出正式包：GitHub → Actions → Desktop → Run workflow，分支选 main，channel 选 `release`。把这次 run 的两个 artifact 下下来。
3. 准备文件：
   `python3 tools/make_update.py prepare --version <v> --dmg <语流_…_universal.dmg> --setup <语流_…_x64-setup.exe> --out <目录>`
   会生成三个文件：`flow-mac-<v>.dmg`、`flow-mac-<v>.app.tar.gz`（Mac 更新用的）、`flow-windows-<v>-setup.exe`（Windows 下载和更新共用）。
4. **用户自己签名**：在自己的终端里跑脚本打印的两条 `npx tauri signer sign -f ~/.tauri/flow-updater.key …`，每条要输一次私钥密码，会生成 `.sig`。
5. 生成清单：`python3 tools/make_update.py manifest --version <v> --dir <目录> --notes "这一版改了什么"`，得到 `latest.json` 和 `SHA256SUMS.txt`。
6. 交给 A1：
   - 三个安装包放到 `https://flowlang.cn/download/`；
   - `latest.json` 放到 `https://flowlang.cn/desktop/latest.json`；
   - sha256 和签名也交给 A1，按 A5 的建议同时发到 GitHub Release。
   
   A1 上传、核对后改下载页的 latest.json。**清单一放上去，所有装了 0.1.1 及以后的 App 就会开始更新**，所以这一步之前先问用户。

### 本机试更新（不用真私钥）

用一把临时测试密钥：`npx tauri signer generate -w <临时目录>/test.key --ci -p test`。然后用 `--config` 覆盖 `pubkey`、
`endpoints`（指向本机 `http://127.0.0.1:8765/latest.json`）和 `dangerousInsecureTransportProtocol: true`，先出一个旧版本号的 App、一个新版本号的更新包。
用测试密钥签名，起 `python3 -m http.server` 当服务器，打开旧版 → 等它下好 → 退出 → 看 Info.plist 的版本号变了没有。

注意两点：
- App 的路径里不能有符号链接（macOS 的 `/var` 就是，要用 `/private/var/...`），不然更新功能不启动；
- Mac 的打包必须不带 `._` 文件（`make_update.py` 用的是 `COPYFILE_DISABLE=1 tar --no-mac-metadata`），不然装不上。

2026-11-25 这样测过 0.1.1 → 0.1.2：下好、退出时装上；换一把密钥签的更新会被拒绝（「签名不是用这把公钥对应的私钥签的」）。

## 隐私

不加任何第三方 SDK，不做统计和跟踪。App 自己只存两样东西在本机：窗口位置（`.window-state.json`）和几个开关（`settings.json`，
在系统的 App 配置目录）。正式版启动时会连 flowlang.cn 查有没有新版本，只看到网络地址，不带账号。网页的数据、登录 cookie 在系统网页引擎的存储里，和浏览器里用网站一样。提醒由系统在本机定时，
不经过任何推送服务。指南「隐私和数据」一章有给学员看的说明。

## 还没做 / 以后

- macOS 签名和公证、Windows 代码签名（等账号和证书）。
- 在用户的 MSI（Windows 11 测试机）上实际用一遍：媒体键、SMTC 浮层、提醒通知点开到复习页。
- 网页侧的小改动（归各区域）：桌面 App 里也显示「返回」按钮（04-home-app.js，语流 B5），「添加到桌面」在 App 里隐藏，
  「已存到手机」「在这台 iPhone 上」这类文案按 `FlowApp.platform` 说（语流 B5 / 11）。
