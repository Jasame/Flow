# 文字模型切换厂商（xmc-api，api.xmc.hk）

目标：Flow 的文字请求（批改、讲解、出题、对话）可以在 DeepSeek、通义千问、Gemini 之间随时切换，只在 xmc-api 的控制台里改，Flow 不用改代码、不用重启。

```
Flow（香港）── 文字请求，模型名 flow-text ──▶ api.xmc.hk（xmc-api，杭州）──▶ DeepSeek / 千问 / Gemini（控制台决定）
           └─ 录音、联网检索，主模型 ──────────▶ api.xmc.hk ──▶ gemini-flow（照旧）
flow-text 出错或被停用时，Flow 自动改用主模型，学生看不到报错。
```

## 为什么这样设计

- **xmc-api 本来就是多厂商网关**：有「上游」「模型」「密钥」「用量」「请求日志」，控制台在 https://xmc.hk/api-admin/。Flow 现在就通过它调用 Gemini（`FLOW_AI_URL=https://api.xmc.hk/…`）。不需要另外搭网关。
- **Flow 只认一个模型名 `flow-text`**：它背后是哪一家，由控制台里的这个模型指向哪个上游决定。
- **Flow 自己兜底**：`flow-text` 出错（上游挂了、被停用、被限流、密钥被拒），Flow 马上改用主模型。只有请求本身有问题（太大、格式不对）才不重试。
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

### 2. 加模型 `flow-text`（你来做）

「模型与倍率」→「添加模型」：

- 名称：`flow-text`
- 上游：`deepseek`
- 实际模型：`deepseek-chat`（以 DeepSeek 平台当前提供的为准）
- 倍率：按需要设置（默认 1 倍）。倍率只影响网关里的用量统计和额度扣减。

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
- 在 xmc-api 的「请求日志」里能看到 `flow-text` 的调用，上游是 `deepseek`。

## 日常：切换厂商

在「模型与倍率」里操作，改完立即生效，Flow 不用动：

- **换一家**：删除 `flow-text`，再添加一个同名的 `flow-text`，上游和实际模型改成另一家，例如：
  - 千问：上游 `qwen`，实际模型 `qwen-plus`（以百炼控制台为准）；
  - Gemini：上游 `gemini-flow`，实际模型和 Flow 主模型相同。
  删除到重新添加的这一两分钟里，Flow 会自动用主模型，学生不受影响。
- **临时全部改回 Gemini**：把 `flow-text` 停用就行，Flow 的文字请求会全部走主模型。要恢复时再启用。
- **每次切换后**：跑一遍 `ai_check.py`。不同模型守 JSON 格式的程度不一样，换了主力后，前一两天留意 Flow 的批改是否正常。

## 回退

- 删掉 `/etc/flow.env` 里的 `FLOW_TEXT_AI_MODEL` 那一行，再重启 Flow：所有请求回到主模型，和以前完全一样。
- 或者只在控制台停用 `flow-text`，效果相同，不用碰服务器。

## 以后可以再做（要改 xmc-api 代码，等你明确要求再做）

- 控制台里直接「改指向」，不用删除再添加。现在模型只能改倍率和停用、启用。
- 网关自己按顺序换上游（DeepSeek 不通就自动用千问）。现在由 Flow 回退到主模型兜底，暂时不需要。

## 参考

- xmc-api 的代码在杭州服务器 `/www/xmc-api/`（`gateway.py`、`control_plane.py`），数据在 `/www/xmc-api/data/api.sqlite3`。
- 运维说明见 xmc-ui 项目的 `AGENT-MANUAL.md` 第 6.5 节。
