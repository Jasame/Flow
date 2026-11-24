# 参与 Flow

感谢你帮助改进项目。先阅读 [项目首页](README.md)、[使用支持](SUPPORT.md) 和 [安全报告说明](SECURITY.md)。

## 反馈与修改

1. 在 [Issues](https://github.com/Jasame/Flow/issues) 搜索已有反馈；普通问题使用 Bug 或功能建议模板。
2. 从最新 `main` 创建自己的功能分支。一次提交集中解决一个问题，避免混入格式重写。
3. 修改前先在独立开发环境复现问题，补充与行为相关的回归检查。
4. 发起 Pull Request，说明问题、行为变化、验证结果与部署影响。未验证的部分请写明。

## 本地检查

推送之前只跑改到的部分，全套交给 CI。CI 每个 Pull Request 都会把网站测试分 2 份、页面测试分 5 份同时跑，大约 6 分钟跑完。具体哪种改动跑哪些测试，见 [tools/README.md 的「推之前跑哪些测试」](tools/README.md)。

```bash
python3 tools/run_tests.py --changed          # 这个分支改到的模块对应的网站测试
python3 tools/run_tests.py test_vocab         # 指定的测试文件
python3 tools/run_tests.py                    # 全部网站测试，多个进程同时跑（笔记本上约 3 分钟）
python3 tools/run_tests.py --ui phone desktop # 改到的页面对应的设备组（需要 Playwright，用本机的 Chrome）
```

`next.js`、`next.css`、操作指南的 PDF 和 `manifest.json` 都是生成出来的，不提交：git 会忽略它们，发版时由 `tools/build_release.py` 用提交里的源文件生成。改前端只提交 `flow/public/src/next/` 里的源文件；改指南只提交 `guide.md` 和截图。想在本地看到生成的结果，运行 `python3 tools/build_release.py --here`（PDF 需要 Playwright）。合并 main 遇到冲突时，先运行 `python3 tools/settle_merge.py`：生成文件、`release-files.txt` 和 `upgrade.sh` 里的文件清单会自动处理好，剩下的才需要手工解决。

前端检查（在仓库根目录，需要 Node.js）：

```bash
python3 tools/build_front.py
for js in flow/public/next.js flow/public/sw.js flow/public/survey.js xmc-admin/admin.js; do node --check "$js" || exit; done
```

网关检查（在仓库根目录）：

```bash
cd flow-gateway
python3 -m unittest discover -s tests -v
```

Vertex / 真实 AI 需要自己的服务端配置。常规测试使用模拟响应，不要求提交云凭据。

## 数据与内容

- 使用临时数据库和虚构账号。不要把线上数据用于 Issue、测试或截图。
- 不提交实际配置、密钥、Cookie、数据库、录音、备份及包含个人信息的日志。
- 新增教学内容、字体或第三方资源时说明来源和再分发许可。
- 数据库结构、环境变量或部署方式有变化时，同步更新文档并说明兼容与回退方式。

## 许可

原创软件贡献按仓库 [LICENSE](LICENSE) 的 MIT 条款提供。导入词典、教学内容和第三方材料不自动适用源码许可。
