# Flow 3.4 AI 验证说明

逐项修改、部署顺序和验收命令以根目录 START-HERE.md 与本目录 UPGRADE.md 为准。本轮未访问生产凭据或修改线上服务器。

## 已验证的层次

- 受控HTTP链路：网站 → 网关 → 模拟Google SSE；包括实际分段抵达、队列和终止事件。
- 原生Vertex ADC音频传输：模型路径、inlineData、格式校验、思考内容过滤及结束事件；没有实际向Google发送录音。
- 学习记录：提示失败不误记、写作任务依据、反馈纠正、记忆固定、口语写作作品与难度观察。
- UI：多任务分别保留、立即完成、失败片段、账号隔离、重试更新、窄屏与继续输入。

## 仍需部署后实测

运行 ai_check.py，默认检查普通文字、实时输出和反馈结构；可选 --grounding 与 --audio。它会产生真实请求并报告首字与完成耗时，但不打印凭据。
登录后的 /api/ai/status 只显示配置字段是否完整及当前账号成功时间，不会自动发起收费模型请求；它不是实时健康认证。

配置、IAM、区域、模型支持、Google额度、代理与CDN的实际状态必须在部署环境核实。实体手机麦克风、软键盘、浏览器TTS和录音理解效果需要人工验收。

## 学习与数据边界

预览不是正式成果。AI语义判断可能出错，可通过反馈纠正入口补充原意。作品、修订与AI意见不直接转为认证等级。难度校准机制现已开始采集样本，不能将“机制存在”说成“已有真实校准结果”。

任务队列为单进程运行时协调；重启后中断任务标为可重试，未开始的队列不保证自动恢复。失败片段保留在当前标签页，完整成功结果保存在服务器。

## 原生接口依据

Google音频理解官方说明：https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/audio-understanding
Google流式方法：https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.publishers.models/streamGenerateContent
