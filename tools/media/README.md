# 音频双线路：香港服务器优先，Cloudflare R2 作备份和总仓库

```
             上传（tools/push_media.py，在 Mac 上跑）
本地音频 ──────────────────────────────▶ R2 桶 flow-media（总仓库）
                                           │  media.flowlang.cn（Cloudflare）
                                           ▼
香港服务器 ◀── 第一次有人要某个文件时，自己去 R2 取一次、核对、存下（flow/media.py）
   │
   ▼
学生的手机 ── 先从香港放（国内最快）；香港出问题时，自动改从 media.flowlang.cn 放
```

- **不用再手工往服务器上传音频**。新音频上传到 R2，再发一次版，服务器第一次被要到这个文件时，会自己取回来。
- **R2 是第二条线路**。香港服务器宕机、太慢或带宽被占满时，页面自动改从 R2 播放，学生不用做任何事。
- **零成本**：R2 免费额度是每月 10 GB 存储和 1000 万次读取，下载流量不收费。现在全部音频约 0.48 GB（2,435 个文件）。

## 一次性设置（你来做，大约 30 分钟）

### 1. 开通 R2，建桶

1. 打开 Cloudflare 控制台 → 左侧「R2 对象存储」。第一次使用要绑定一张信用卡或 PayPal，免费额度内不扣费。
2. 「创建存储桶」，名字填 `flow-media`，位置选「自动」。

### 2. 绑定域名

1. 进入桶 `flow-media` →「设置」→「自定义域」→「连接域」，填 `media.flowlang.cn`。flowlang.cn 要在同一个 Cloudflare 账号里，Cloudflare 会自动加好 DNS 记录（橙色云朵）。
2. **不要**打开 `r2.dev` 公共地址：那个地址限速，国内也常打不开。
3. 建议再加一条缓存规则，让音频留在 Cloudflare 的节点上，不用每次回 R2：
   - 「缓存」→「Cache Rules」→「创建规则」；
   - 条件选「主机名 等于 `media.flowlang.cn`」；
   - 操作选「符合缓存条件」，边缘 TTL 选「使用缓存控制标头」。

### 3. 设置跨域（CORS）

桶 `flow-media` →「设置」→「CORS 策略」→「编辑」，粘贴：

```json
[
  {
    "AllowedOrigins": ["https://flow.jasa.hk", "https://flowlang.cn", "https://www.flowlang.cn"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges"],
    "MaxAgeSeconds": 86400
  }
]
```

页面从 R2 读逐词时间文件时需要这一条。音频本身没有它也能播放。

### 4. 建一个只能写这个桶的密钥

1. R2 页面 →「管理 R2 API 令牌」→「创建 API 令牌」。
2. 权限选「对象读和写」，「指定存储桶」只勾 `flow-media`。
3. 在你的 Mac 上新建文件 `~/.config/flow/r2.env`，权限设成 600，写入下面四行。这个文件不要提交、不要发到聊天里：

```
R2_ACCOUNT_ID=<账户 ID，在 R2 页面右侧>
R2_BUCKET=flow-media
R2_ACCESS_KEY_ID=<访问密钥 ID>
R2_SECRET_ACCESS_KEY=<机密访问密钥>
```

## 上传和启用（Claude 可以做）

1. **上传**：在仓库根目录运行下面这条命令。第一次会上传全部 2,435 个文件、约 0.48 GB，之后只传新增和改过的。最后会检查几个文件能不能从 `media.flowlang.cn` 正常取到，以及跨域设置对不对。

```
python3 tools/push_media.py <本地音频目录> --verify https://media.flowlang.cn
```

2. **提交并发版**：把生成的 `flow/corpus_data/media-manifest.json` 提交，并加进 `tools/release-files.txt` 和 `flow/upgrade.sh` 的 corpus 列表，然后合并、发版。
3. **在香港服务器上启用**：在 `/etc/flow.env` 里加一行，然后重启 Flow（`systemctl restart flow`）：

```
FLOW_MEDIA_BASE=https://media.flowlang.cn
```

4. **确认 Flow 能写音频目录**：确认运行 Flow 的系统用户能写入 `/www/wwwroot/flow/audio`。看 `systemctl show -p User flow` 和 `ls -ld /www/wwwroot/flow/audio`。不能写的话，服务器取不回新音频，页面会直接从 R2 放，也能用，只是慢一些。

## 验收

1. 打开一篇以前没有真人朗读的材料，例如连载 B1「A New Term」第 1 集，点「播放全文」，听到的应该是真人朗读，不是浏览器的声音。
2. 在服务器上看 `/www/wwwroot/flow/audio/us-f/` 里出现了这篇的 `.m4a` 和 `.json`。
3. 浏览器开发者工具的 Network 里，音频来自 flow.jasa.hk（第一条线路）。

## 日常

- **新材料**：本地用 `tools/gen_audio.py` 生成朗读，再运行 `push_media.py`，最后提交 manifest 并发版。服务器上什么都不用做。
- **单词发音**：同上，用 `tools/gen_word_audio.py` 生成。

## 回退

- 删掉 `/etc/flow.env` 里的 `FLOW_MEDIA_BASE`，再重启 Flow。服务器只用本机已有的音频，页面也不再用第二条线路，和以前完全一样。
- R2 里的文件不会因此丢失，随时可以重新启用。

## 注意

- 国内经 Cloudflare 访问 `media.flowlang.cn`，晚高峰可能比较慢。所以它只做第二条线路；主线路始终是香港。
- 文件名不带版本号，网址后面会带上内容指纹（`?v=…`）。同名文件重新生成后，网址也跟着变，不会读到旧缓存。
- `tools/push_media.py` 只用 Python 标准库，不需要安装别的东西。它从不打印密钥。
