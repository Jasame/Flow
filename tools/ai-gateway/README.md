# AI 网关（api.xmc.hk）上线清单

目标：Flow 只认一个入口。用哪家模型、坏了切谁，都在网关后台里改，Flow 不用改代码、不用重启。

```
Flow 后台 ──文字请求──▶ 网关 127.0.0.1:3000（New API）──▶ DeepSeek / 千问 / Gemini …（后台排优先级，可随时切换）
        └─录音、联网检索──▶ Vertex Gemini（照旧直连，不经过网关）
后台管理页面：https://api.xmc.hk（Cloudflare Access 保护，只给自己人用）
```

- 网关用开源的 New API（github.com/QuantumNous/new-api，AGPL-3.0），版本固定为 `v1.0.0-rc.49`。只部署一个容器，数据存在 SQLite 里。
- Flow 走本机地址调用网关，不绕公网，也不经过 Cloudflare。公网上只开放管理后台，模型接口 `/v1` 对外是关闭的。
- 各家的 API 密钥只存在网关里（`/opt/ai-gateway/data/`）。Flow 只拿一个网关令牌。
- 需要 Flow r19 或之后的版本：从这个版本起，Flow 允许用 http 访问本机地址；对其他地址仍然只允许 https。

下面标「你来做」的步骤涉及密码、密钥或账号，必须由你本人操作；其余步骤可以交给 Claude 做。

## 0. 前提

- 新服务器迁移完成，Flow 在新服务器上正常运行。
- 宝塔里已安装 Docker（「软件商店」→「Docker」）。

## 1. 启动网关（root，在服务器上）

```bash
bash tools/ai-gateway/setup.sh
```

这个脚本会：

- 建好 `/opt/ai-gateway`；
- 生成会话密钥 `.env`（权限 600，不会显示出来）；
- 拉取固定版本的镜像并启动；
- 确认 `http://127.0.0.1:3000/api/status` 正常。

可以重复运行，已有的数据和密钥都会保留。3000 端口被占用时，脚本会停下来并提示换端口。

## 2. 域名、HTTPS、访问保护

1. **Cloudflare DNS（你来做，或授权 Claude 做）**：添加 `api.xmc.hk`，A 记录指向新服务器 IP，开橙云代理。
2. **宝塔建站**：
   1. 添加站点 `api.xmc.hk`（不建数据库、不建 FTP），申请或部署 SSL 证书。
   2. 打开站点「配置文件」，按 `nginx-api.xmc.hk.conf` 修改：
      - 删掉宝塔默认带的两段静态文件规则（`gif|jpg…` 和 `js|css`），否则后台页面打不开；
      - 把默认的 `location /` 换成文件里的两段：第一段关闭 `/v1` 等模型接口，第二段反向代理到 127.0.0.1:3000。
   3. 保存，并确认 nginx 配置检查通过。
3. **Cloudflare Access（你来做）**：在 Zero Trust → Access → Applications 里给 `api.xmc.hk` 加一个应用，用和 xmc.hk/flow 相同的策略，只允许你们自己的邮箱。

## 3. 初始化后台（你来做）

1. 打开 https://api.xmc.hk，通过 Cloudflare Access 登录。
2. 按初始化向导创建管理员账号，用强密码，存进密码管理器。
3. 在「系统设置 / 运营设置」里（名称以后台显示为准）：
   - 失败重试次数设为 2：一家出错时，自动换下一个优先级的渠道再试；
   - 打开「自动禁用失败渠道」：连续出错的渠道会被暂停，恢复后在后台手动启用。

## 4. 添加渠道（你来做，密钥只填在这里）

每家模型建一个渠道。三家的「模型」都填同一个名字 `flow-text`，再用「模型重定向」指到各家真实的模型名：

| 渠道名 | 类型 | 模型 | 模型重定向 | 优先级 |
| --- | --- | --- | --- | --- |
| DeepSeek | DeepSeek | `flow-text` | `{"flow-text": "deepseek-chat"}` | 30 |
| 通义千问 | 阿里云百炼 | `flow-text` | `{"flow-text": "qwen-plus"}` | 20 |
| Gemini | Vertex AI | `flow-text` | `{"flow-text": "<和 Flow 现在用的同一个 Gemini 模型>"}` | 10 |

- **优先级**：数字越大越先用。最大的一家出错，就按数字从大到小往下试；同一优先级里按「权重」分配流量。
- **测试**：每个渠道建好后点一次「测试」。
- **Gemini 渠道只能用「Vertex AI」类型**：
  - 香港可以直接用 Vertex AI，Flow 现在就是这样连的；但 AI Studio 的 Gemini API（填 AI Studio API Key 的那种）在香港不开放，不要选那个类型。
  - 密钥填服务账号 JSON。建议在 Google Cloud 控制台新建一个只有 Vertex AI User 权限的服务账号，不要复用 Flow 服务器上的凭据文件，也不要把 JSON 发到聊天里。
  - 部署地区填 `global`，和 Flow 现在一样。
- **这些模型名是建议**，以各家控制台当前提供的为准。

## 5. 价格和令牌（你来做）

1. **定价**：在「模型定价 / 倍率」里给 `flow-text` 设一个价格，按 DeepSeek 的价格填即可。这只用于后台统计和报销对账；不设的话，调用可能被拒绝，提示模型没有定价。
2. **新建令牌**：
   - 名称写 `flow`，额度设为无限；
   - 「模型限制」只勾 `flow-text`；
   - IP 限制先不填：模型接口本来就只对本机开放。
3. **复制令牌**：只在下一步用一次，不要发到聊天里。

## 6. 接入 Flow（你来做）

在 `/etc/flow.env` 里加三行，令牌那一行由你本人填写：

```
FLOW_TEXT_AI_URL=http://127.0.0.1:3000/v1/chat/completions
FLOW_TEXT_AI_MODEL=flow-text
FLOW_TEXT_AI_KEY=<第 5 步的令牌>
```

然后重启 Flow：

```bash
systemctl restart flow
```

接入后的行为：

- **只有文字请求会走网关**：批改、讲解、出题、对话都是文字请求；录音和联网检索照旧直连 Vertex。
- **网关不可用时会自动回退**：网关停了或返回错误，Flow 会自动改用 Vertex，学生不会看到报错。

## 7. 验收

```bash
python3 /opt/ai-gateway/check_gateway.py --public https://api.xmc.hk
```

```bash
cd /www/wwwroot/flow && <Flow 用的 python> ai_check.py
```

`check_gateway.py` 会检查以下几项，最后应该显示「全部通过」：

- 网关在运行，令牌有效，令牌能用 `flow-text`；
- 普通调用有回答，并显示实际回答的模型和用时；
- 流式输出正常；
- 按要求只回 JSON；
- `/v1` 不对公网开放。

`ai_check.py` 的每一项里，`"service"` 应该显示「文字服务」。

最后在后台「日志」里能看到 `flow-text` 的调用记录，以及实际走的是哪个渠道。也可以在线上跑一遍 Flow 的端到端测试。

## 日常：切换厂商

- **换主力**：在后台「渠道」里改优先级，或者停用某个渠道。改完立即生效，不用重启 Flow。
- **加一家新厂商**：新建一个渠道，「模型」写 `flow-text`，用「模型重定向」指向这家的真实模型名，再设好优先级。
- **每次切换后**：跑一遍 `check_gateway.py`。不同模型守 JSON 格式的程度不一样；主力换成新模型后，前一两天留意 Flow 的批改是否正常。

## 回退

- **临时关掉网关**：删掉 `/etc/flow.env` 里那三行，然后 `systemctl restart flow`。Flow 就只用 Vertex，和接入网关前完全一样。
- **网关出故障时**：不用急。Flow 会自动回退到 Vertex，有空再排查：

  ```bash
  cd /opt/ai-gateway && docker compose logs --tail 100
  ```

## 升级

1. 先备份数据：

   ```bash
   cp -a /opt/ai-gateway/data /opt/ai-gateway/data.bak-$(date +%F)
   ```

2. 把 `docker-compose.yml` 里的版本号改成新的。只选发布满两周、发布说明里没有破坏性改动的版本。
3. 重启并验收：

   ```bash
   bash tools/ai-gateway/setup.sh
   ```

   ```bash
   python3 /opt/ai-gateway/check_gateway.py
   ```

## 备份与迁移

- `/opt/ai-gateway/data/` 里存着各家的密钥和调用记录，要当密码一样保管：
  - 只在服务器之间直接传，不经过聊天，也不用网盘；
  - 要加进服务器的定期备份。
- `/opt/ai-gateway/.env` 是会话密钥。丢了重新生成就行，只是所有人要重新登录后台。

## 还没有验证的部分

- 这套配置在本地只对一个模拟的网关跑过，测的是检查脚本和配置文件，没有在真正的 New API 上跑过（本机没有 Docker）。
- 第 1 步做完后，需要在服务器上实际验收一遍。
- 香港服务器连 Vertex AI 已经确认没问题：切换前在香港跑的线上测试 152 项全部通过，其中包括真实的 AI 调用。
