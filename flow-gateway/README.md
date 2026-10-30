网关2.2增加短时排队并在结束标志后结束上游读取。本轮真实Google连通性仍待生产配置实测。请以包内START-HERE.md为准。

网关 v2.1 新增真实 SSE 输出。升级顺序、实时验证与本轮验证边界见本包 START-HERE.md。旧部署记录不代表本轮已实测。

网关 v2.0 移除默认应用每日次数门槛，保留使用量统计、认证、白名单、并发、音频与联网检索能力。必须与本包 START-HERE.md 配合升级；原密钥与证书保留。

本次 v0.8 网关增加 Google Search grounding 与来源元数据透传；音频、原密钥、模型、来源白名单、计数与证书继续保留。现有部署升级请以包根目录 START-HERE.md 和 flow/UPGRADE.md 为准。

本次网关 v0.6 增加受限音频输入。请配合网站包根目录 START-HERE.md 与 flow/UPGRADE.md，使用 upgrade.sh 升级现有网关。沿用原模型、密钥、Vertex 服务身份与计数；更新时保留白名单、证书和限流。

现有网站与网关升级到 v0.4，请优先阅读本包 `flow/UPGRADE.md`，使用 upgrade.sh 保留现有密钥。

# Flow Gemini 网关部署

历史部署记录（本轮未重新核实）：Google Cloud 项目 project-8c5a66f7-07f1-4ea9-af7；Debian 12 VM flow-ai-gateway，新加坡 asia-southeast1-b；已绑定专用服务账号并验证 gemini-3.8-flash 可调用。域名 ai.flowlang.cn 的 A 记录指向 136.85.98.179。阿里云 Flow 源站 IP 121.40.203.104。

## 1 安装网关

从 VM SSH 终端输入 exit 返回 Cloud Shell，上传 Flow-Gemini-Gateway.zip 到 Cloud Shell 主目录，然后执行：

```bash
unzip -o Flow-Gemini-Gateway.zip
gcloud compute scp --recurse flow-gateway flow-ai-gateway:~/ --project=project-8c5a66f7-07f1-4ea9-af7 --zone=asia-southeast1-b
gcloud compute ssh flow-ai-gateway --project=project-8c5a66f7-07f1-4ea9-af7 --zone=asia-southeast1-b --command='sudo bash ~/flow-gateway/install.sh'
```

每条命令确认成功后再执行下一条。若上传位置不同，将文件路径换成实际位置。脚本专用于此新建的 Debian 网关，不要在阿里云宝塔主机上运行 install.sh。

安装脚本：

- 将服务绑定到 127.0.0.1:8088，使用专用系统用户常驻运行。
- 使用已绑定的 Google 服务账号，通过 VM 元数据获取并缓存短期访问令牌，不导出 Google 长期凭据。
- 提供 /v1/chat/completions 的非流式纯文本兼容接口，固定上游模型，不接受任意上游 URL。
- 使用独立随机密钥认证；Nginx 只允许阿里云源站与本机调用模型接口。/health 可公开访问，用于网络与进程检查，不调用模型。
- 限制输入长度、输出令牌上限（最多 4096）、并发（2）和每日请求尝试次数（默认 100，UTC 日期），次数存入 SQLite，重启后保留。次数上限不是美元预算或整项目费用上限。
- 申请 ai.flowlang.cn 的 Let's Encrypt 证书并启用 certbot.timer。域名需已正确解析，80/443 防火墙需已放通；如有错误 AAAA 记录需纠正。
- 在 SSH 用户主目录生成 flow-gateway-client.env，权限 600；该文件包含网关密钥，应视为密码。

重复运行保留密钥、每日计数和 Certbot 已修改的站点文件。若需修改阿里云 IP，请修改 /etc/nginx/sites-available/flow-gateway 中的 allow 后检查并重载 Nginx。

## 2 检查从阿里云访问

在宝塔终端执行：

```bash
curl --fail --silent --show-error --connect-timeout 8 --max-time 15 https://ai.flowlang.cn/health
```

应返回 {"ok": true, "service": "flow-gateway"}。若不通，尚不能接入：检查 DNS、TLS 及阿里云到网关公网 IP 的网络。Google VM 内调用 Gemini 成功并不能保证阿里云到该 IP 连通。

## 3 私有传递连接配置

在 Cloud Shell 执行（不要打印连接文件的内容）：

```bash
gcloud compute scp flow-ai-gateway:~/flow-gateway-client.env ~/flow-gateway-client.env --project=project-8c5a66f7-07f1-4ea9-af7 --zone=asia-southeast1-b
```

用 Cloud Shell 的“下载文件”功能，下载主目录中的 flow-gateway-client.env，再通过自己的宝塔文件管理上传到 /root/flow-gateway-client.env。不要上传到网站公开目录，不要将内容、令牌或截图发送到聊天里。

将本压缩包中的 connect-flow.sh 同样上传到宝塔 /root/connect-flow.sh，然后在宝塔终端执行：

```bash
chmod 600 /root/flow-gateway-client.env
bash /root/connect-flow.sh /root/flow-gateway-client.env
```

连接脚本会先检查 HTTPS，再做一次真实 Gemini 短请求（消耗一次模型调用）。只有模型请求成功才会备份并更新 /etc/flow.env；将网站切换到兼容接口模式，覆盖旧 FLOW_AI_PROVIDER=vertex。网站无需再向 Google 获取令牌。

脚本将网站模型请求等待时间从 35 秒调整至 65 秒，再重启 Flow；不会更换网站的 systemd 解释器或 Nginx 配置。现有 Nginx proxy_read_timeout 建议至少 90 秒（此前提供的 flowlang.cn 配置已满足）。脚本会保留账号与数据库。

完成后打开 flowlang.cn → 学习中心 → 任意知识点 → 学习答疑。实际在网页提问并收到内容，才算网站端接通。/api/session 中 ai_enabled=true 仅代表配置存在，不代表上游一定可用。

确认后可自行清理 Cloud Shell 和本机下载目录的临时连接文件，服务器 /etc/flow.env 和 /etc/flow-gateway.env 中保留运行所需配置。

## 4 维护与限制

网关日志：sudo journalctl -u flow-gateway -n 50 --no-pager

重启：sudo systemctl restart flow-gateway

证书续签演练：sudo certbot renew --dry-run

客户端密钥轮换需同步更新 /etc/flow-gateway.env 和阿里云 /etc/flow.env，并重启两边服务。源站 IP 变化需同步调整 Nginx allow。VM 停止再启动可能更换临时公网 IP，长期运行前应将当前公网 IP 保留为区域静态地址，或在变化后更新 DNS。

网关仅保存日期和请求次数，不保存提示文本、模型回答或 Google 令牌日志。请求内容会传给 Google。不要把此独立网关开放成匿名公共 AI 服务。

已完成 4 项本地自动化测试：请求认证与兼容响应、输入与固定模型验证、每日额度并发一致性与持久化、元数据令牌缓存；安装脚本通过 shell 语法检查。无法代替你服务器上的安装、证书申请和网络验证。
