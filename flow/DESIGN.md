# Flow 2.2 界面整合说明

以下为团队提供的共享设计规范，现已延伸到长期私教、图谱、AI词汇、学习证据与周报。新增页面的主题适配集中在 public/design-bridge.css；正文为不透明表面，玻璃仅用于导航与工具栏。保留浅色、深色、跟随系统、降低透明度和减少动态效果。

---
name: "语流 Flow"
description: "通透的 macOS 风格英语学习工作台；正文保持安静、清晰和可操作。"
colors:
  bg: "#f3f6f8"
  surface: "#fff"
  subtle: "#f0f2f5"
  hover: "#e9ecf0"
  sidebar: "rgba(237,242,247,.64)"
  chrome: "rgba(249,251,253,.68)"
  glass-edge: "rgba(255,255,255,.76)"
  text: "#24272e"
  muted: "#666d78"
  faint: "#626b76"
  line: "#e4e7ec"
  control: "#d3d8e0"
  accent: "#1767ce"
  accent-hover: "#105bb8"
  accent-soft: "#e9f1fc"
  positive: "#28734e"
  positive-soft: "#eaf5ee"
  negative: "#b4383e"
  negative-soft: "#fff0ef"
  reading-surface: "#f2f4f5"
  reading-text: "#354c5e"
  auth-surface: "#e9eef2"
  auth-text: "#273d4d"
  dark-bg: "#1c1d20"
  dark-surface: "#25262a"
  dark-subtle: "#2d2f34"
  dark-hover: "#383b42"
  dark-sidebar: "rgba(34,39,46,.68)"
  dark-chrome: "rgba(28,33,40,.72)"
  dark-glass-edge: "rgba(255,255,255,.08)"
  dark-text: "#f2f3f5"
  dark-muted: "#b0b6c0"
  dark-faint: "#a3abb7"
  dark-line: "#3a3c42"
  dark-control: "#50545e"
  dark-accent: "#76b0ff"
  dark-accent-hover: "#91c0ff"
  dark-accent-soft: "#25374f"
  dark-positive: "#8cd4ad"
  dark-positive-soft: "#233b2e"
  dark-negative: "#ff9c9c"
  dark-negative-soft: "#41282a"
typography:
  page:
    fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',sans-serif"
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-.65px"
  section:
    fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-.2px"
  body:
    fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',sans-serif"
    fontSize: "15px"
    lineHeight: 1.6
  control:
    fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',sans-serif"
    fontSize: "14px"
    fontWeight: 550
    lineHeight: 1.4
  secondary:
    fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',sans-serif"
    fontSize: "13px"
    lineHeight: 1.6
  caption:
    fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',sans-serif"
    fontSize: "12px"
  reading:
    fontFamily: "'New York',Georgia,'Times New Roman',serif"
    fontSize: "16px"
    lineHeight: 1.95
    letterSpacing: ".1px"
rounded:
  small: "4px"
  tag: "8px"
  control: "12px"
  inner: "14px"
  card: "18px"
  panel: "22px"
  dialog: "22px"
  pill: "999px"
spacing:
  space-1: "4px"
  space-2: "8px"
  space-3: "12px"
  space-4: "16px"
  space-5: "20px"
  space-6: "24px"
  space-7: "32px"
  space-8: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#fff"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-quiet:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "9px 11px"
  navigation:
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  tag:
    backgroundColor: "{colors.subtle}"
    textColor: "{colors.muted}"
    rounded: "{rounded.tag}"
    padding: "3px 7px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "24px"
  corpus-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.inner}"
    padding: "19px 20px 0"
  skill-segment:
    textColor: "{colors.muted}"
    rounded: "{rounded.tag}"
    padding: "7px 8px"
  command-dialog:
    backgroundColor: "{colors.chrome}"
    textColor: "{colors.text}"
    rounded: "{rounded.dialog}"
    width: "560px"
---

# Design System: 语流 Flow

## Overview

**Creative North Star: "通透的学习工作台"**

以 macOS 原生应用的秩序组织英语学习：导航与工具栏呈现轻盈的磨砂玻璃，阅读和作答落在不透明纸面上。通透来自低强度静态散射、玻璃边缘高光与克制的层次，而不是把所有内容变成半透明。

这份文档提取自 2026-10-19 已实现的前端，结合用户明确提出的“原生、通透、高级、有质感”和适当圆润的方向。它记录最终实现约定，不表示用户逐项批准了每个 token，也不构成 WCAG 认证或全功能验收声明。业务边界见 PROJECT_CONTEXT.md；本次没有 PRODUCT.md，不补造产品承诺。

**Key Characteristics:**

- 玻璃用于应用外壳与命令浮层，正文卡片保持实色。
- 系统字体、中性色和有限的功能蓝，圆角柔和但不膨胀。
- 今日、语料、复习、档案构成稳定导航；听说读写一次聚焦一项。
- 桌面工作台与手机抽屉共享同一视觉语言和可见状态。

实现来源：`Flow-v0.7-Upgrade(1)/flow/public/style.css`、`layout.css` 与 `app.js`。前置方向文档 `output/frontend-redesign/reports/REVIEW_BRIEF.md` 中旧字号、旧材质描述可能早于最终精修；发生冲突时以实现与本文件提取值为准。

## Colors

冷静的雾白与石墨中性色承托内容，系统感蓝色明确操作方向；浅深主题用相同语义映射，避免简单反色。

### Primary

- `accent`：主要按钮、链接、输入焦点和进度；悬停复用 `accent-hover`。
- `accent-soft`：低强度的选中辅助底色。侧栏当前页采用中性选中底，不把导航大面积涂蓝。
- 深色模式采用 `dark-accent`、`dark-accent-hover` 和 `dark-accent-soft`；主按钮文字在深色模式为实现中的深墨色（`#12233a`），浅色模式为白色。

### Neutral

- `bg` 是工作台底色，`surface` 是不透明卡片和纸面；`subtle` 用于分段背景与次级面板，`hover` 提供轻量响应。
- `sidebar`、`chrome` 与 `glass-edge` 共同定义通透外壳。浅深主题的透明度由各自 token 控制，不能将其替换成统一透明白。
- `text` 用于主要阅读；`muted` 用于说明；`faint` 用于辅助标注。`line` 分隔结构，`control` 划分可编辑边界。
- `reading-surface` / `reading-text` 与 `auth-surface` / `auth-text` 是实现中局部纸面与登录叙事色。深色局部纸面另有直接选择器覆写，不从浅色值推导深色值。

### Semantic states

- `positive` / `positive-soft` 表达正确与积极反馈；`negative` / `negative-soft` 表达错误、待核对与危险操作；深色语义使用对应 `dark-` token。
- 结果同时保留文字、图标或选择状态。禁用控件使用既有透明度（`.45`）、不可用光标与必要原因提示。

**The Functional Accent Rule.** 蓝色服务于操作与状态；品牌标记允许固定品牌蓝，普通图标默认跟随文字颜色。

## Typography

界面采用 frontmatter 的原生字体栈：优先设备系统字体，中文回退 PingFang SC，再回退 Helvetica Neue 与 sans-serif。不附带字体文件，不加载字体 CDN。阅读正文允许设备上的 New York，再回退 Georgia / Times New Roman，保持英文材料的阅读节奏；这是内容字体，界面仍使用原生无衬线。

### Hierarchy

| 角色 | 用途与当前实现 |
| --- | --- |
| `page` | 页面主标题；标准字重与行高取 frontmatter。今日页主标题局部为 29px，手机为 28px；其他手机页标题常为 25px。 |
| `section` | 卡片与区块标题；手机通用 h2 会收至 16px，训练纸标题保持 18px。 |
| `body` | 应用默认正文。数字使用 tabular-nums；较长学习内容保留宽松行高。 |
| `control` | 主要按钮、字段标签与导航；不要将它与 caption 混用。 |
| `secondary` | 次级说明、安静按钮、目录预览。 |
| `caption` | 元信息、状态标记、页脚。快捷键帽是局部 11px，不能反推为全局正文尺度。 |
| `reading` | 桌面英文阅读段落；手机实际为 17px，行高沿用阅读节奏。 |

**The Content First Rule.** 优先维持材料、题目和输入内容的阅读层级；不要为了视觉紧凑把辅助文字继续缩小。

## Layout

桌面以固定左侧栏、粘性工具栏与居中内容区构成工作台。默认侧栏宽（224px），工具栏最小高（62px），内容区最大宽（1200px）；默认页面内边距（36px 40px 28px）。内容使用前景纸面与留白，不依赖装饰性背景图片。基础间距从 frontmatter 的 `space-1` 至 `space-8` 取用；布局中也有实际观察到的 18px、28px 等局部间距，不强行归整为虚构比例。

训练区默认单列；检查器展开时桌面增加（285px）辅助列。语料目录按可用宽度从多列收为两列、一列。设置在宽屏使用说明与表单双区，窄屏先说明后控件。图谱保留可横向浏览的大画布，不压缩文字到不可读。

### Responsive behavior

| 条件 | 实现行为 |
| --- | --- |
| ≥1600px | 页面顶部留白增加；首页纸面预览更舒展。 |
| ≤1250px | 侧栏收至 208px，页面左右内边距 28px；目录两列。 |
| ≤1050px | 侧栏成为 244px 抽屉，主体取消左偏移；抽屉使用实色 surface 与遮罩。打开时正文 inert，Tab 在导航内循环，Escape / 遮罩关闭后归还触发焦点。 |
| ≤800px | 工具栏最小高 56px；训练检查器移到正文后，课程与导师按单区切换；设置单列。 |
| ≤600px | 工具栏最小高 54px，页面左右内边距 18px；首页和目录单列，隐藏首页辅助材料预览。通用卡片保留 card 圆角；命令浮层距视口两侧 12px。 |
| 粗指针 | 共享按钮、导航、摘要等交互目标至少 44px，图标按钮同时保证最小宽度；开关点击标签也扩大。 |
| ≤600px 输入 | `layout.css` 尾部的高优先级规则确保输入框、文本域、选择框为 16px，覆盖之前更紧凑的局部样式。 |

设备“降低透明度”、系统 reduced-transparency 或不支持 backdrop-filter 时，去掉背景散射，外壳恢复实色，浮层使用 surface；相关遮罩去掉模糊。此降级是视觉系统的一部分，应保持在共享规则之后。触屏 44px 目标和手机 16px 输入规则也放在响应样式末段，避免被局部控件规则覆盖。

## Elevation & Depth

通透是首要材料特征，层级仍然克制。body 的两层静态 radial-gradient 提供低强度环境散射，侧栏与工具栏通过玻璃底色、模糊（18px）、饱和度（1.15）和内侧高光形成边界。命令浮层沿用玻璃材质；正文卡片、阅读纸与表单保持不透明。桌面导航和工具栏的材料来自设备式应用外壳，不应在每一张卡片上重复。

### Shadow Vocabulary

- `glass-shadow`：外壳轻柔环境影，浅深主题不同；配合 `glass-edge` 的单像素高光。
- `shadow`：抽屉、提示等暂时浮层的结构分离。
- 命令浮层：内侧顶部高光加（`0 24px 90px #0003`）；登录窗口局部为（`0 24px 80px #20334b12`）。
- 分段选中项：轻微台阶影（`0 1px 3px #00000012`）。静态通用卡片以细边框分界，不添加大面积悬浮阴影。

以上完整阴影、散射与材料值仅放在 `.impeccable/design.json` 的 `extensions`；frontmatter 不扩展非法 token 组。

**The Opaque Paper Rule.** 阅读材料与作答表单必须落在实色纸面；玻璃用于外壳与浮层，降低透明度时整体仍有清晰边界。

动效服务于状态连续性：控件过渡（160ms）、侧栏过渡（220ms），缓动取 `ease-out`；页面轻量出现为 `.2s`，目录卡悬停仅抬升（2px）。开启设备减少动态效果或系统 reduced-motion 后移除动画、过渡与平滑滚动，状态文字和焦点继续显示。

## Shapes

圆润来自分层使用的 CSS border-radius，而不是所有元素都使用胶囊。小标记使用 small / tag，按钮和字段使用 control，纸内模块与目录卡使用 inner，主要内容卡使用 card，登录窄屏窗口与命令浮层使用 panel / dialog。各值见 frontmatter；当前实际控件（12px）、目录/设置容器（14px）、通用卡片（18px）、命令浮层（22px）。手机通用卡片也保持 card，不降回 inner。

分段控件外框在实现中为局部（9px），内部选中项使用 tag。头像与品牌标记使用 inner，开关使用 pill；桌面登录窗口是局部（22px）。这些是观察到的组合，并不要求新组件复制全部局部例外。

**The Web Approximation Rule.** 这些圆角是 Web 对原生柔和轮廓的近似；不要宣称它们实现了 Apple 私有 continuous shape 或原生系统组件。

## Components

### Buttons

紧凑、明确，有可见按下与聚焦反馈。主按钮使用 accent 与 control 圆角，最小高度（36px）；次按钮使用 surface 与 control 边界；安静按钮用于工具操作，最小高度（34px）。主按钮悬停切换 accent-hover，按下移动（1px）；全局键盘焦点为 accent 的（3px）外轮廓与（3px）偏移。手机与触屏按 Layout 的最终规则扩大。

### Inputs / Fields

字段使用实色 surface、control 边框与 control 圆角，内边距见 frontmatter，默认最小高度（38px）。聚焦时边框切换 accent，并出现（3px、18% accent）的外环。标签、辅助说明、错误消息分别占据稳定层级；错误与处理中提供文字，不伪装为成功。密码显示、搜索、选择框保留真实控件语义。

### Navigation

分组侧栏以图标、文字与当前页背景建立方向。普通图标采用 `currentColor`、24×24 viewBox、线宽（1.65）、圆端点与圆连接，常用显示尺寸（15–19px）；不引入图标字体或外部图标资源。当前页使用 `aria-current`；抽屉使用焦点管理和 inert。工具栏按钮拥有可读名称，保留跳到主要内容入口。

### Chips / Segmented controls

静态标签采用 subtle 底色与 muted 文字；待核对标签使用 negative-soft 和 negative。目录范围、练习方式和四技能切换使用分段控件：选中项是 surface 纸片与轻影、主要文字和 `aria-pressed`，未选中项保持安静。标签不应被误作可点击按钮；交互分段必须有焦点态。

### Cards / Containers

通用卡片为 surface、细 line 边框、card 圆角，桌面内边距（24px）。语料卡和设置面板使用 inner；语料卡悬停边框增强并抬升（2px），其主要动作仍是明确的文字按钮。训练纸展开检查器时保留正文宽度，手机将辅助工具移到后方并提供聚焦与返回入口。

### Theme / Comfort settings

浅色、深色和跟随系统三种外观均为设备偏好。选中模式采用 accent 边框、accent-soft 背景与 `aria-pressed`。降低透明度与减少动态效果使用有说明文字的开关，状态保存在当前设备；系统媒体查询也独立生效。

### Command palette

Cmd / Ctrl K 打开真实模态 dialog，宽度与圆角见 frontmatter。搜索面板支持页面与语料检索、上下键选择、Enter 打开、Escape 关闭和关闭后焦点归还；搜索输入与结果采用 combobox / listbox 关联语义。浮层内次级文字也使用 text 色，依字号和位置区分层级，以保证叠加遮罩后的可读性。玻璃材质在降级模式切换为实色；示例侧栏或命令样本只演示样式，不替代应用事件逻辑。

## Do's and Don'ts

### Do:

- Do 保持玻璃外壳与实色阅读纸的材料层次；需要通透时复用现有散射、高光和模糊。
- Do 复用系统字体与既有字号层级，让正文、辅助文字和控件保持可读。
- Do 使用实际训练、材料和学习记录；空态、错误、处理中和禁用态提供明确文字。
- Do 保留可见焦点、键盘入口、关闭后的焦点归还和设备舒适偏好。
- Do 在手机与触屏重新排布并扩大点击区域，而不是整体缩小桌面工作台。

### Don't:

- Don't 给阅读正文、作答区和内容卡片叠加透明背景或装饰模糊。
- Don't 把品牌蓝扩散到每一层背景，或仅靠红绿颜色表达结果。
- Don't 为模拟 SF 字体下载或托管 Apple 专有字体；使用设备原生字体和回退。
- Don't 把 Web border-radius 描述成 Apple 私有的连续曲率实现。
- Don't 用虚构统计、装饰图表或未经验证的服务成功状态填充页面。
