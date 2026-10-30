# Flow 接入 Google Cloud Gemini

本版新增 Vertex AI / Agent Platform 的 ADC 自动令牌刷新。不要把 gcloud 输出的一小时临时令牌长期填到 FLOW_AI_KEY，也不要把凭据文件上传到网页公开目录。

## 1 先确认计费

在 Google Cloud 中选择项目，将其关联到获得 $300 赠送额度的结算账号，启用 Vertex AI API（服务名 aiplatform.googleapis.com）。在模型控制台中确认当前账号、项目和区域可用的 Gemini 模型 ID。不要为抵扣这笔赠送额度改用 AI Studio 的 Gemini Developer API。

先发送一次短测试请求，再到结算报告确认实际调用服务及赠送额度抵扣；结算统计可能延迟。$300 新手额度通常自注册起 90 天有效。升级付费账号不会延长原有效期，并可能产生额度外费用。预算提醒不是强制停机或硬消费上限。

## 2 配置 ADC

截图提示组织策略不允许 API 密钥，应使用 ADC；不需要为了本项目放宽组织策略。

对于阿里云等外部服务器，长期部署优先使用工作负载身份联合（WIF），配置文件路径通过 GOOGLE_APPLICATION_CREDENTIALS 指定。若服务器暂时没有可用的外部身份提供方，可以先在可信本机使用 gcloud 交互式登录获得用户 ADC，验证试点接入；用户 ADC 是开发验证方案，稳定运行时应换成 WIF 或组织批准的服务身份。

本机安装 Google Cloud CLI 后，执行以下交互命令（请自行替换 PROJECT_ID）：

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID
```

登录身份需要该项目的 Vertex AI User 权限；设置 quota project 还需要 serviceusage.services.use 权限。用户 ADC 文件含刷新令牌，属于密钥。Linux/macOS 默认位于 ~/.config/gcloud/application_default_credentials.json；Windows 一般位于 %APPDATA%\gcloud\application_default_credentials.json。若组织禁止用户 ADC 或外部使用，请按组织批准的 WIF/服务身份流程，不要绕过策略。

将生成的 ADC 文件通过自己的宝塔文件管理或 SSH 安全传输到服务器 `/www/flow-secrets/adc.json`，不要发送到聊天中。服务器设置：

```bash
mkdir -p /www/flow-secrets
chown root:www /www/flow-secrets
chmod 750 /www/flow-secrets
chown www:www /www/flow-secrets/adc.json
chmod 600 /www/flow-secrets/adc.json
```

已经使用 WIF 的用户在此位置放置官方生成的联合身份配置文件，无需用户 ADC。程序通过 google-auth 读取 ADC 并自动刷新访问令牌。

## 3 安装可选依赖

使用与 flow.service 对应的 Python 建立虚拟环境：

```bash
cd /www/wwwroot/flow
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-vertex.txt
```

若缺少 venv 或 pip，先补齐对应 Python 的组件。将 flow.service 中的 ExecStart 修改为：

```
ExecStart=/www/wwwroot/flow/.venv/bin/python /www/wwwroot/flow/app.py
```

## 4 环境变量

在现有 `/etc/flow.env` 中增加或修改以下内容，不要覆盖原有运行端口与数据目录：

```ini
FLOW_AI_PROVIDER=vertex
GOOGLE_CLOUD_PROJECT=你的项目ID
GOOGLE_CLOUD_LOCATION=global
FLOW_AI_MODEL=google/控制台中可用的模型ID
GOOGLE_APPLICATION_CREDENTIALS=/www/flow-secrets/adc.json
```

项目 ID 是类似 my-project-123456 的唯一标识，不是 My First Project 这样的显示名称。区域需与模型支持范围匹配。此模式忽略 FLOW_AI_URL 和 FLOW_AI_KEY，使用 Google 官方 OpenAI 兼容接口和 ADC。API 认证刷新也需要服务器能够访问 Google OAuth 及模型端点。

如果之前已经安装 systemd 服务，修改 `/etc/systemd/system/flow.service` 的 ExecStart；只改源码目录的 service 不会更新已安装服务。

```bash
systemctl daemon-reload
systemctl restart flow
systemctl status flow --no-pager
```

## 5 验证和错误定位

登录 → 学习中心 → 选择知识点 → 学习答疑，先只问一句短问题。然后到 Cloud 控制台查看 API 请求、结算报告与额度抵扣情况。每日每账号 20 次上限保留，但这不是整个站点的美元硬上限。

如果失败，依次检查：运行服务的 www 用户能否读取 ADC、项目是否启用 API 和关联结算、登录身份是否有权限、模型是否支持该区域、服务器是否能访问 Google。不要在公开日志里打印 ADC 文件或访问令牌。

此交付已做本地接口回归及模拟凭据自动刷新测试；没有你的 Cloud 身份，尚未验证真实调用、组织授权或额度抵扣。

官方参考：
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://docs.cloud.google.com/docs/authentication/set-up-adc-on-premises
- https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/openai
