# Flow · 语流

面向自托管的英语学习与 AI 私教项目。当前网站源码为 **3.4**，配套 AI 网关为 **2.2**。

## 功能

- 持续学习、听说读写练习、分级语料与个人词汇本。
- 基于作答证据的知识图谱、复习建议和学习档案。
- AI 私教、逐步显示回复、任务排队、重试与长期学习记忆。
- 可选 OpenAI 兼容接口、Gemini / Vertex AI 和独立网关。
- 账号隔离、持久化记录与备份维护工具。

## 项目结构

| 目录 | 用途 |
| --- | --- |
| `flow/` | Python 网站后端、无需构建的前端和测试 |
| `flow/public/` | 页面、样式与 JavaScript |
| `flow-gateway/` | 可选 AI 网关及其部署脚本 |
| `validation/` | 验证工具 |

## 安装与升级

网站使用 Python 3.11 或以上及 SQLite；核心网站不需要 Node.js。Vertex 模式的附加依赖见 `flow/requirements-vertex.txt`。

- [首次部署指南](flow/README.md)
- [3.4 升级说明](START-HERE.md)
- [网站升级与验收](flow/UPGRADE.md)
- [AI / Vertex 接入](flow/VERTEX_SETUP.md)
- [网关部署](flow-gateway/README.md)
- [架构](flow/ARCHITECTURE.md)

部署脚本面向指定 Linux / systemd 环境。运行前核对域名、路径与服务配置，升级已有实例时保留并备份实际数据库和密钥。

## 测试

```bash
cd flow
python3 -m unittest discover -s tests -v
```

原交付包的验证记录保存在 [VALIDATION.md](VALIDATION.md)，是历史交付记录，不代表本次整理已重新运行测试，也不代表真实模型认证和生产环境已经验收。

## 数据与隐私

真实数据库、账户资料、学习记录、录音、备份、环境配置、API 密钥和云凭据不纳入公开仓库。只保留示例配置。

教学语料与导入词典应与用户运行数据区分管理；第三方来源内容的许可不随程序源码许可证自动授予。维护者已确认随包词典数据为原创或已获得公开再分发授权，因此本仓库保留该词典。此确认不额外授予超出原有授权的使用权。

## 许可

原创程序源码采用 [MIT 许可证](LICENSE)。教学内容、导入词典及第三方材料不在该源码许可授权范围内；其使用和再分发须遵循各自授权。
