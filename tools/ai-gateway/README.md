# 文字模型切换厂商（xmc-api，api.xmc.hk）

目标：Flow 的文字请求（批改、讲解、出题、对话）可以在 DeepSeek、通义千问、Gemini 之间随时切换，只在 xmc-api 的控制台里改，Flow 不用改代码、不用重启。

```
Flow（香港）── 文字请求，模型名 flow-text ──▶ api.xmc.hk（xmc-api，香港）──▶ DeepSeek / 千问 / Gemini（控制台决定）
           └─ 录音、联网检索，主模型 ──────────▶ api.xmc.hk ──▶ gemini-flow（照旧）
flow-text 出错或被停用时，Flow 自动改用主模型，学生看不到报错。
```

- xmc-api 从 2026-11-23 起和 Flow 在同一台香港服务器上。Flow 现在仍然通过 `https://api.xmc.hk` 调用它，不用改。
- 发 r20 以后（那一版允许 Flow 用本机 http 调网关），香港的 `FLOW_AI_URL` 可以改成 `http://127.0.0.1:9000/v1/chat/completions`，不再绕 Cloudflare。这一步发 r20 时再做。
- Gemini 上游仍然经 `ai.flowlang.cn` 中转（GCP 新加坡）。Google AI Studio 的 Gemini API 不对香港开放，中转站只当备用。

## 为什么这样设计

- **xmc-api 本来就是多厂商网关**：有「上游」「模型」「密钥」「用量」「请求日志」，控制台在 https://xmc.hk/api-admin/。Flow 现在就通过它调用 Gemini（`FLOW_AI_URL=https://api.xmc.hk/…`）。不需要另外搭网关。
- **Flow 只认一个模型名 `flow-text`**：它背后是哪一家，由控制台里的这个模型指向哪个上游决定。
- **两层兜底**：
  - 网关先按顺序试 `flow-text` 的备用线路（见下面「备用线路」）；
  - 全都不通时，Flow 改用主模型。只有请求本身有问题（太大、格式不对）才不重试。
- **钥匙不用复制**：只写 `FLOW_TEXT_AI_MODEL=flow-text` 一行时，Flow 用的就是现在调用 Gemini 的同一个网关地址和同一把 `flow` 密钥。

注意：xmc-api 的说明书里写着「不要改现有 API 网关的配置和上游，除非用户明确要求」。下面每一步都只是新增，不改已有的上游和模型；由你本人在控制台里操作，或者明确交给 Claude 做。

## 一次性设置

### 1. 在 xmc-api 加上游（你来做，密钥只填在控制台里）

打开 https://xmc.hk/api-admin/ →「上游连接」→「添加上游」，各加一个：

| 名称 | 地址（base_url） | 密钥 |
| --- | --- | --- |
| `deepseek` | `https://api.deepseek.com/v1` | DeepSeek 开放平台的 API Key |
| `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云百炼的 API Key |

- 建好后各点一次「测试连接」。
- Gemini 不用新加：现有的上游 `gemini-flow` 就是 Gemini（走 Vertex AI）。

### 2. 加模型 `flow-text`（你来做，或者明确交给 Claude 做）

**一定要先做这一步，再做第 3 步。** 网关现在只有 `gemini-3.8-flash`、`gemini-3.8-flash-pro`、`qwen-local-256k` 这几个模型名。没有 `flow-text` 就先在 Flow 里打开它的话，网关每次都回「未知模型」（404），Flow 每次都回退到主模型，每个文字请求白白多绕一圈。

「模型与倍率」→「添加模型」：

- 名称：`flow-text`
- 主线路：先指向现在的 Gemini，也就是上游 `gemini-flow`、实际模型 `gemini-3.8-flash`。这样打开以后，学生得到的回答和现在一样，只是多了切换的余地。
- 倍率：按需要设置（默认 1 倍）。倍率只影响网关里的用量统计和额度扣减。

### 2b. 给 `flow-text` 加备用线路（第 1 步的密钥有了以后）

打开 https://xmc.hk/api-admin/fallbacks.html，给 `flow-text` 按顺序加备用线路，例如：

1. 上游 `deepseek`，实际模型 `deepseek-chat`；
2. 上游 `qwen`，实际模型 `qwen-plus`。

实际模型名以各平台当前提供的为准。想让 DeepSeek 当主力，就按下面「日常：切换厂商」把主线路换成 `deepseek`，再把 Gemini 放进备用线路。

`flow` 这把密钥的权限是「全部模型」，新加的 `flow-text` 自动包含在内，不用改密钥。可以在「调用文档」里选 `flow` 密钥，看模型列表里有没有 `flow-text`。

### 3. 让 Flow 用它（需要 Flow r20 或之后的版本）

在香港服务器的 `/etc/flow.env` 里加一行（这一行不是密钥，可以交给 Claude 或迁移会话做）：

```
FLOW_TEXT_AI_MODEL=flow-text
```

然后重启 Flow：

```
systemctl restart flow
```

不要动 `FLOW_AI_URL`、`FLOW_AI_KEY`、`FLOW_AI_MODEL`。

### 4. 验收

在服务器上运行。`python3` 换成 Flow 服务用的那个 python，`systemctl cat flow` 里 `ExecStart` 那一行写着它的路径：

```
cd /www/wwwroot/flow && python3 ai_check.py
```

- 「文字模型（flow-text）」这一项要通过。它直接调用 flow-text，不会回退到主模型，所以能看出 flow-text 自己通不通。
- 其他几项的 `"service"` 应该显示「文字服务」。如果显示「主服务」，说明 flow-text 没回答，Flow 回退到了主模型。
- 在 xmc-api 的「请求日志」里能看到 `flow-text` 的调用，上游是主线路的那一家。

## 备用线路（xmc-api 已支持，2026-11-23 起）

- 同一个模型名先走自己的主线路。连不上、超时，或者上游返回 401/403/408/409/429/5xx 时，网关按顺序试备用线路。
- 400（请求本身有问题）原样返回，不换线路。
- 管理页：https://xmc.hk/api-admin/fallbacks.html。也可以用接口：`GET/POST /api-admin/api/fallbacks`，`PATCH/DELETE /api-admin/api/fallbacks/{id}`。
- 数据存在网关的 `model_fallbacks` 表里。现在所有模型都还没有配备用线路。

## 按任务选模型：阿里云百炼或 Gemini（2026-11-24 起，ai_routes.py）

用户定了用**阿里云百炼**：一个 key 就能调通义千问各档，以及百炼上的 DeepSeek、Kimi、GLM 等，走 OpenAI 兼容接口（compatible-mode）。有两个百炼账号：

- **企业账号**（协议价，六七折）：正式版和内测版学员的调用都走它。网关上游 `bailian`。
- **站长个人的学生账号**（一张 300 元「云工开物」券，领取后一年内有效，只能抵扣学生用券中心「大模型服务」里列出的模型）：跑研发和批量的活，包括 ai_eval 对比、每晚小评测、例句预生成、语音模型试验。网关上游 `bailian-dev`。**学生账号上跑哪些模型，以站长在学生用券中心看到的那份列表为准**，不在列表里的模型券抵不了。

网关里的模型名按用途分三种前缀，Flow 自己会挑：

```
学员（企业账号）  flow-text            → Gemini 3.8 Flash（现在的，备用：bailian / qwen-plus）
                  flow-text-qwen37-plus → bailian / qwen3.7-plus（批改、讲解、改写的主力候选）
                  flow-text-ds-flash    → bailian / deepseek-v4.1-flash（主力候选）
                  flow-text-qwen-plus   → bailian / qwen-plus（便宜的对照组）
                  flow-text-qwen37-flash→ bailian / qwen3.7-flash（量大、要求低：例句、翻译原句、对话）
                  flow-text-qwen38-flash→ bailian / qwen3.8-flash（对话不够自然时换它）
评测（学生账号）  flow-eval-<同名>      → bailian-dev / 同一个实际模型
批量（学生账号）  flow-batch-<同名>     → bailian-dev / 同一个实际模型
百炼的每条都配 Gemini 备用；都不通时，Flow 再换主模型 gemini-3.8-flash；录音、联网检索一直走主模型。
```

- 后台给某个任务选了 `flow-text-qwen37-plus`：学员的请求问它（企业账号）。`ai_eval.py` 和每晚小评测问 `flow-eval-qwen37-plus`，例句预生成问 `flow-batch-qwen37-plus`，这两个都走学生账号。网关里没有对应的 eval / batch 名字时，退回学员用的那个名字（企业账号）。评测报告里的 `asked` 会写明实际问了哪些名字。
- 学员的任务都还在 `flow-text`（Gemini）时，例句预生成也可以先用学生账号：网关里建一个不带后缀的 `flow-batch`（指向 `bailian-dev` 上评测选出的便宜模型），例句预生成就问它；ai_eval 的 `flow-eval` 同理。没有这个名字就照旧问 `flow-text`。
- **学生券用完或过期后**：在网关里把 `flow-eval-*`、`flow-batch-*` 改指 `bailian` 上游（删了重建，或者直接删掉，让 Flow 退回 `flow-text-*`）。Flow 代码不用动。
- 这些都是候选，评测后不用的可以删。max 档、Kimi、deepseek-v4-pro 贵 5–20 倍，这几类任务用不上，不加。

网关里要加的东西（两把百炼 API Key 都由站长本人在百炼控制台生成、填进网关，别人不经手；阿里云 AccessKey 也不用给任何人）：

| 在哪里 | 加什么 |
| --- | --- |
| 上游连接 | `bailian`（企业账号的 key）、`bailian-dev`（学生账号的 key），地址见下面「地域」，各点一次「测试连接」 |
| 模型与倍率 | 上图的 `flow-text-*` 指向 `bailian`；需要的 `flow-eval-*`、`flow-batch-*` 指向 `bailian-dev`，实际模型同名 |
| 备用线路 | 每个百炼名字的备用：`gemini-flow` / `gemini-3.8-flash`；`flow-text` 的备用：`bailian` / `qwen-plus` |

- **地域**：百炼的 key 按地域分，不能混用。阿里云中国站（华北2 北京）的兼容地址是 `https://dashscope.aliyuncs.com/compatible-mode/v1`。官方建议改用工作空间域名 `https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`：2026-09-30 起新功能只上工作空间域名，WorkspaceId 在百炼控制台看。国际站是新加坡 `dashscope-intl.aliyuncs.com`，另外还有中国香港地域。两个账号各按自己的地域填。网关会在 base_url 后面接 `/chat/completions`，所以地址填到 `/v1` 为止。
- 每个任务问哪个模型名，在 xmc.hk/flow →「AI 用量、费用和质量」里选。下拉框列的是网关里的 `flow-text`、`flow-text-*`：Flow 用自己的密钥问 `GET /v1/models`。改了马上生效，记进操作记录。服务器上的默认值写在 `FLOW_AI_ROUTES` 里（例如 `{"*": "flow-text-qwen37-plus"}`）。两样都没有时，全部走 `flow-text`，和以前一样。**正式版上换模型之前先问过站长。**
- Flow 每个文字请求都带 `"enable_thinking": false`。qwen-plus、qwen-flash 默认就不思考；百炼上的 DeepSeek 和 qwen3.5 以后的型号默认会思考，又慢，又多花输出 token。走百炼的 JSON 任务还带 `response_format: {"type": "json_object"}`：百炼要求提示词里有 JSON 字样，Flow 的提示词都有。Gemini 中转站会忽略这两个字段。思考默认全关；哪个批改任务效果不够，再单独给它试开（要改 Flow 代码里的 `extra_body`）。
- 费用：后台按官方标价 × 平台折扣算。百炼默认按 0.65 折，后台可以改；单价也可以改，还可以加模型。学生账号上跑的（每晚小评测、例句预生成）也按这个价估，实际由学生券抵扣，券还剩多少要到百炼控制台看。
- 缓存：百炼的隐式缓存命中按输入价的 20% 算，但要 1024 token 以上才可能命中。Flow 提示词里每次相同的开头只有 500–750 token，整条提示词也大多不到 1000，所以基本吃不到。qwen-turbo 已经不在价格表里了。
- **换模型之前先考试**：在香港用内测版代码的一份副本，对每个候选跑 `python3 ai_eval.py --env-file /etc/flow-beta.env --route flow-text-qwen37-plus --output …`（走学生账号上的 `flow-eval-qwen37-plus`），用 `--route flow-text` 跑一遍 Gemini 作对照。比较通过数和报告里的 `usage`（token、命中缓存、估算费用）。哪个任务某个模型没过，那个任务就不换给它。
- 后台每晚 2–5 点自动跑一次小评测（`ai_eval.py --quick`，约 17 次调用，走 `flow-eval-*`），结果画在同一页上。

## 日常：切换厂商

在「模型与倍率」和「备用线路」里操作，改完立即生效，Flow 不用动：

- **某一家临时出问题**：不用管。网关会按顺序换到备用线路，都不通时 Flow 回退到主模型。

- **换主力**：删除 `flow-text`，再添加一个同名的 `flow-text`，上游和实际模型改成另一家，然后把备用线路重新加上。例如：
  - 千问：上游 `bailian`，实际模型 `qwen-plus`（以百炼控制台为准）；
  - Gemini：上游 `gemini-flow`，实际模型和 Flow 主模型相同。
  删除到重新添加的这一两分钟里，Flow 会自动用主模型，学生不受影响。
- **临时全部改回 Gemini**：把 `flow-text` 停用就行，Flow 的文字请求会全部走主模型。要恢复时再启用。
- **每次切换后**：跑一遍 `ai_check.py`。不同模型守 JSON 格式的程度不一样，换了主力后，前一两天留意 Flow 的批改是否正常。

## 回退

- 删掉 `/etc/flow.env` 里的 `FLOW_TEXT_AI_MODEL` 那一行，再重启 Flow：所有请求回到主模型，和以前完全一样。
- 或者只在控制台停用 `flow-text`，效果相同，不用碰服务器。

## 以后可以再做（要改 xmc-api 代码，等你明确要求再做）

- 控制台里直接「改指向」，不用删除再添加。现在模型只能改倍率和停用、启用。

## 参考

- xmc-api 的代码是 `gateway.py` 和 `control_plane.py`，数据在 `api.sqlite3`。2026-11-23 随迁移从杭州搬到了香港，现在的位置和恢复步骤见杭州服务器上的 `/www/xmc-status/README.md` 和 `RECOVERY.md`。
- 运维说明见 xmc-ui 项目的 `AGENT-MANUAL.md` 第 6.5 节。
