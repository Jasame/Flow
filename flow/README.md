# Flow 3.0 · 有依据的个性化学习

修改方案、实现范围与后续验收见 [LEARNING-REDESIGN.md](LEARNING-REDESIGN.md)，部署见 [UPGRADE.md](UPGRADE.md)。


本次新增持续学习入口、图谱事件变化、词汇理解/拼写/表达分项，以及Gemini续学上下文。部署与验收见 [UPGRADE.md](UPGRADE.md)。


本版完善手机底部导航、私教、知识图谱、分级语料、词库和练习表单，保留2.5的154篇分级材料与词库、进度和长期私教。部署见UPGRADE.md，适配说明见MOBILE-UI.md。

部署以 UPGRADE.md 为准，合并范围见 UI-INTEGRATION.md，设计规范见 DESIGN.md。以2.1功能为基础合入团队UI，保留所有学习数据与无个人调用次数上限。

# Flow 2.1 · 证据驱动的长期英语私教

新增主题六维阶段、可解释复习队列、持续诊断、周报、证据成就、教学纠正和版本绑定的语料审核。部署以 UPGRADE.md 为准；Google 网关仍为2.0。

本次 v2.0 将主入口重构为长期 AI 英语私教，包含首次起点检查、六维阶段计划、长期对话记忆、自动课后复盘和旅程进度。请优先阅读 UPGRADE.md；旧版文档中的每用户20次限制已移除。

本次 v1.0 AI × 知识图谱自适应学习重构，请优先阅读 `UPGRADE.md`。

# 语流 Flow 宝塔部署指南

现有 flowlang.cn 升级请先阅读 `UPGRADE.md`。

Google Cloud Gemini 接入请先阅读 `VERTEX_SETUP.md`。新版支持 ADC 自动刷新令牌；仅 Vertex 模式需要额外依赖。

这是可部署的英语语法学习试点版，包含真实账号、服务端判题、持久化学习记录、规则推荐、知识关系展示、学习讲解和题目录入后台。当前内置 6 个主题、18 个语法细项、72 道示例题、46 篇语料和 100 个试用词汇义项，适合小范围试用。AI 服务可选，未配置时显示固定学习提示。

## 一、上传与准备

要求 Linux、宝塔 Nginx、Python 3.11 或以上且带 sqlite3 模块、域名及 HTTPS。程序不依赖第三方 Python 包，不需要 Node.js、MySQL 或 Neo4j。推荐关系暂存 SQLite，尚未实现 DKT 模型。

在宝塔文件页面，将压缩包上传至 `/www/wwwroot/` 并解压。确保文件位于：

```
/www/wwwroot/flow/app.py
/www/wwwroot/flow/public/index.html
/www/wwwroot/flow/data/
```

如果解压后多出一层目录，调整为上面的结构。以下命令默认使用该路径。如另选路径，需要同时调整 service 和 env 文件。

在宝塔终端执行：

```bash
python3 --version
python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'
command -v python3
id www
```

如果 Python 低于 3.11 或缺少 sqlite3，先通过服务器对应的包管理器或宝塔 Python 环境补齐。`flow.service` 的 ExecStart 默认 `/usr/bin/python3`；若实际解释器不同，改成 `command -v python3` 返回的绝对路径。

## 二、配置运行环境与管理员

以下首次部署命令需要 root 权限。复制配置文件只在首次部署执行，升级时保留现有配置。

```bash
cd /www/wwwroot/flow
cp flow.env.example /etc/flow.env
chmod 600 /etc/flow.env
chmod 755 /www/wwwroot/flow
chmod 700 /www/wwwroot/flow/data
chown www:www /www/wwwroot/flow/data
```

创建管理员（用户名和密码交互输入，无默认管理员或默认密码）：

```bash
cd /www/wwwroot/flow
python3 app.py --create-admin
chown -R www:www /www/wwwroot/flow/data
```

用户名 3–40 字符，密码至少 10 字符。管理员账号登录后侧栏出现“内容管理”，可编辑、审核、导入和发布题目。普通学生自行注册账号。注册并不会授予管理员权限。

## 三、启动常驻服务

推荐使用 systemd 管理此 Python 服务，与宝塔共存。请先检查 `flow.service` 中解释器与路径是否匹配实际机器。

```bash
cp /www/wwwroot/flow/flow.service /etc/systemd/system/flow.service
systemctl daemon-reload
systemctl enable --now flow
systemctl status flow --no-pager
curl http://127.0.0.1:8090/api/session
```

正常返回：`{"user": null, "ai_enabled": false}`。系统启动时自动初始化数据库。仅监听本机 8090，公网安全组无需开放该端口。

如果宝塔也配置了此项目的 Python 启动任务，请只选一种进程管理方式，避免端口冲突。

## 四、配置宝塔网站

1. 在“网站”中添加你的域名，项目类型选择普通静态网站即可，PHP 选择纯静态。
2. **网站根目录设置为 `/www/wwwroot/flow/public`**，避免源码与数据库落在网站公开目录内。
3. 申请并启用该域名的 SSL 证书，启用强制 HTTPS。
4. 在该网站配置文件的 `server { ... }` 内，用 `nginx-location.conf` 的 `location /` 配置替换已有的同名段。若启用其他反向代理或伪静态，先清理冲突规则。
5. 移除该站点模板中优先拦截 `.js`、`.css` 等静态资源的正则 location，或将这些规则改为反代到同一服务，避免文件请求绕过应用。不要修改宝塔证书验证相关的 `/.well-known/` 配置。
6. 用宝塔的配置检查功能确认 Nginx 配置通过，再重载。
7. 浏览器访问 `https://你的域名`，注册学生账号，或使用刚创建的管理员账号登录。

本项目不是 SPA 伪静态部署，不要添加 `try_files ... /index.html` 作为反代替代。前端和 API 都由同一个本机 Python 服务提供，Nginx 负责 HTTPS 和反代。

生产环境保持 `FLOW_COOKIE_SECURE=1`。若仅用 HTTP 测试，安全 Cookie 不会发送，表现为登录后仍未登录；应先启用 HTTPS。本机临时测试可设置为 0，结束后恢复 1 并重启服务。

## 五、可选接入 AI

在宝塔文件页面或终端编辑 `/etc/flow.env`，填写：

```ini
FLOW_AI_URL=https://你的服务域名/完整的/chat/completions/路径
FLOW_AI_MODEL=你的模型名称
FLOW_AI_KEY=你的接口密钥
```

接口需兼容 OpenAI Chat Completions 格式。URL 必须是完整 HTTPS 接口地址，不是服务商首页。程序不会自动拼接 `/v1/chat/completions`。不要在前端代码或浏览器中填入密钥。

```bash
systemctl restart flow
```

登录后进入“学习中心 → 任意知识点 → 学习答疑”验证。未配置密钥时提供固定学习提示；配置后每账号每天限制 20 次调用。AI 回复并非已审核教学内容，需要核对。服务商调用失败时显示错误，不伪造 AI 回复。AI 对话按账号和知识点保存在本站数据库中，但提问会发送给配置的模型服务商。生产试用前告知参与者此数据流。

## 六、上线验收

- 注册一个学生账号，完成诊断测评，确认出现逐题解析。
- 返回首页，检查累计题数、正确率与推荐内容。
- 刷新并重新登录，检查练习记录仍在。
- 使用另一个账号，确认看不到前一个账号的记录。
- 管理员进入内容管理并新增一道题；普通账号不显示管理入口且接口拒绝访问。
- 在手机和电脑上分别检查显示、按钮与答题流程。

开发阶段已通过自动化接口测试与 Python/JavaScript 语法检查；交付环境不支持浏览器自动化，尚未完成真实浏览器视觉检查及你的宝塔服务器联调。

## 七、维护与备份

日志与重启：

```bash
journalctl -u flow -n 100 --no-pager
systemctl restart flow
```

v0.7 升级会安装每日自动备份与恢复工具，首选 UPGRADE.md 中的新流程。以下为临时手工备份示例：

```bash
mkdir -p /www/backup/flow
chmod 700 /www/backup/flow
python3 - <<'PY'
import sqlite3, datetime
name = '/www/backup/flow/flow-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3'
with sqlite3.connect('/www/wwwroot/flow/data/flow.sqlite3') as source:
    with sqlite3.connect(name) as target:
        source.backup(target)
print(name)
PY
```

首次备份后将备份文件权限设为 600；备份含账号与学习记录。可通过宝塔计划任务定期执行同一备份脚本。恢复时先停止服务，再替换整个 data 目录中的数据库文件（清理旧 WAL/SHM），恢复 www 所有权后启动。建议先在另一个目录验证备份可读取。

升级：先备份，再替换程序文件；保留 `data/` 与 `/etc/flow.env`，不要覆盖真实数据库。v0.7 在启动时自动执行幂等增量迁移，保留现有记录。后续改变数据库结构仍需单独规划迁移。

## 八、源码和边界

- `app.py`：HTTP 接口、认证、判题、推荐和可选 AI。
- `seed.py`：首次启动的教学内容和题目；已有数据库不会因修改此文件而自动更新。
- `public/`：无需构建的界面源码。
- `tests/test_flow.py`：隔离临时数据库中的接口测试。
- `flow.service`、`flow.env.example`、`nginx-location.conf`：部署配置。

本版采用最近最多 10 次作答的正确率作为知识点掌握度，结合教学前置关系推荐学习内容。重复题会影响该指标，它不代表经统计验证的真实能力。v0.7 提供四项主导航、36 篇分级语料、收藏检索、笔记与反馈恢复，以及听说读写主题训练、可选录音提交 Gemini 分析、原稿复练、语境词汇本，并保留此前综合训练、可选 AI 写作反馈、本机口语回听、经验证的邮箱找回与题库审核，详见 UPGRADE.md。尚不包含 DKT、语音评分、教学知识点正文在线编辑及大规模并发支持。适用受控小规模试用，扩大公开运营前需增加更完善的账号滥用防护、可观测性、内容审核流程并进行负载测试。

运行检查：

```bash
python3 -m unittest discover -s tests -v
```

如机器有 Node.js，可附加执行 `node --check public/app.js`；运行网站本身不需要 Node.js。
