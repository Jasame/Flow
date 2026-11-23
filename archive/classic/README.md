# 经典版（已归档，r20）

这里是 Flow 经典版的前端：AI 私教、诊断测评、内容管理、旧的知识图谱和练习页面。从 r20 起它**不再有任何入口**：

- 网站不再提供这些文件；它们也不在 `tools/release-files.txt` 和 `flow/upgrade.sh` 里，发版时不会装到服务器上。
- `/`、`/?classic=1`、`/classic`、`/practice/…/` 以及其他带查询参数的旧链接，都打开学习主线（`next.html`）。
- 学习网站只开放学习主线、问卷、登录和账号要用的接口（`flow/app.py` 里的 `OPEN_API`）。其他 `/api/…` 一律返回 404，包括经典版的接口和它的管理员功能（统计、备份状态、手动生成热点、发布题目、审核候选材料）。
- 管理功能只在 xmc.hk 的运营后台（`flow/flow_admin.py` + `xmc-admin/`），那里有「管理员」和「只看数据」两种角色，敏感操作会留操作记录。

## 后端代码

经典版用过的服务模块大多也在给学习主线用（比如 `lab_service`、`learning_service`、`practice_service`），所以留在 `flow/`。下面这些模块现在只剩建表和旧数据的作用，没有任何接口能访问到：

`meeting_service.py`、`meeting_path.py`、`guest_first.py`、`pilot_service.py`、`knowledge_service.py`、`core_words.py`、`ai_help_service.py`、`seed.py`、`content_v03.py`、`migration_35.py`、`corpus_import.py`

数据库里的旧表和数据都保留，不删除。

只测经典版接口的两组旧测试也移到了这里（`tests/test_flow.py`、`tests/test_ai_integration.py`），不再运行。其中仍然有用的一条检查（不泄露服务器文件、首页有 CSP）搬进了 `flow/tests/test_admin_roles.py`。

## 想再看一眼经典版

只在自己电脑上看，不要部署。用 r19 的代码另开一个目录，数据也放在临时目录里：

```
git worktree add /tmp/flow-r19 r19
FLOW_DATA_DIR=/tmp/flow-r19-data FLOW_COOKIE_SECURE=0 python3 /tmp/flow-r19/flow/app.py
```

然后打开 `http://127.0.0.1:8090/?classic=1`。看完用 `git worktree remove /tmp/flow-r19` 删掉。
