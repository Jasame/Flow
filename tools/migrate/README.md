# Flow 服务器迁移清单

目标：把 flow.jasa.hk 从旧服务器搬到新的香港服务器，**数据不丢、停机不超过半小时、随时能退回**。

分三步走，每一步做完再进下一步。打勾的方框照着做就行。

| 文件 | 在哪儿运行 | 做什么 |
|---|---|---|
| `inventory.sh` | 旧服务器（也可在新服务器上对比） | 只读盘点：列出 Flow 用到的所有东西，不显示密钥 |
| `pack.sh` | 旧服务器 | 打包：程序、录音、配置、凭据、后台服务、自动部署、Python、数据库快照；不停服务 |
| `unpack.sh` | 新服务器 | 解包到相同位置、换上数据库、启动网站和备份（不开自动部署） |
| `check_ai.py` | 新服务器 | 真的调用一次 AI（文字 + 录音），确认这台服务器能用 |
| `check_site.py` | 任何电脑 | 不改域名，直连新服务器 IP 逐项检查，并和线上对比 |

> 包里有密钥（`/etc/flow.env`、Google AI 凭据）。只在两台服务器之间直接传，不要下载到电脑、不要发到聊天里，用完就删。

---

## 第一步：买之前和刚买后（7 天退款期内）

- [ ] **测线路**：在晚上 8–11 点，用 itdog 对新服务器的 IP 做 ping 和 TCPing 443，看大陆各地的延迟和丢包。大多数地区 50 ms 以内、丢包接近 0 最好，100 ms 以内可以接受。
- [ ] **装环境**：新服务器装宝塔面板，系统尽量和旧服务器一样（旧服务器跑 `bash inventory.sh` 第一段能看到系统版本和 CPU 架构，两台架构必须一样，一般都是 x86_64）。
- [ ] **测 AI 要等第二步解包之后**（它要用旧服务器拷来的配置和凭据），但也要在退款期内做完：第二步里专门有这一项。

**拿到脚本**：在两台服务器上都执行一次（脚本来自 GitHub 上的公开仓库，只是普通文件）：
```bash
mkdir -p /root/flow-migrate-tools && cd /root/flow-migrate-tools
for f in inventory.sh pack.sh unpack.sh check_ai.py check_site.py README.md; do
  curl -fsSLO "https://cdn.jsdelivr.net/gh/Jasame/Flow@main/tools/migrate/$f"
done
```

## 第二步：搭好新服务器（旧网站照常运行）

在**旧服务器**上：
- [ ] `cd /root/flow-migrate-tools && bash inventory.sh > inventory.txt`，看一遍：
  - 「网站目录」里除了 `flow` 还有别的网站吗（比如 `xmc.hk`）？要一起搬就告诉我，另外安排；
  - 「Google AI 凭据文件」那一行有路径，并且文件存在。
- [ ] `bash pack.sh` → 得到 `/root/flow-migrate-日期.tar.gz`，记下它打印的校验值。
- [ ] `scp /root/flow-migrate-日期.tar.gz root@新服务器IP:/root/`

在**新服务器**上：
- [ ] `sha256sum /root/flow-migrate-日期.tar.gz`，和旧服务器打印的校验值一样。
- [ ] `cd /root/flow-migrate-tools && bash unpack.sh /root/flow-migrate-日期.tar.gz`
  - 它会把所有东西放回和旧服务器一样的位置，换上数据库，启动网站、每日备份和每日任务，最后打印「健康检查：200」。
  - **自动部署这时不会打开**，切换那天再开。
- [ ] **AI 检查（最关键，不通就在退款期内退掉这台服务器）**：
  ```bash
  sudo /opt/uv-python/cpython-3.11.18-linux-x86_64-gnu/bin/python3.11 /root/flow-migrate-tools/check_ai.py
  ```
  （Python 路径以 `inventory.sh` 里「Flow 正在用的 Python」为准。）文字和录音都显示「成功」才继续。
- [ ] **宝塔里建站点**：新建站点 `flow.jasa.hk`，反向代理到 `http://127.0.0.1:8090`。照着 `/root/flow-migrate-stage/reference/nginx/` 里旧服务器的配置填（有一份管录音的额外配置在 `extension` 文件夹里，也要加上）。
- [ ] **HTTPS 证书**：切换后不再经过 Cloudflare 代理，新服务器需要自己的证书。在宝塔「SSL → Let's Encrypt」里选 **DNS 验证**，用一个只有这个域名 DNS 编辑权限的 Cloudflare API 令牌，这样**切换前就能申请好**。
- [ ] **跑线上自动测试**（在新服务器上，用的是新服务器自己的数据库副本，会真实调用 AI 约 17 次）：
  ```bash
  cd /root/claude-ops/autodeploy/daily && set -a && . /etc/flow.env && set +a && \
    /opt/uv-python/cpython-3.11.18-linux-x86_64-gnu/bin/python3.11 -I qa_e2e.py
  ```
  最后一行是检查项总数和失败数，应当全部通过（AI 偶尔超时失败一两项可以重跑一次）。
- [ ] **从外面检查**（在任何电脑上，把 IP 换成新服务器的）：
  ```bash
  python3 check_site.py 新服务器IP
  ```
  全部打勾，而且「部署状态」显示「和线上一致」。每一项的毫秒数都包含新建一次 HTTPS 连接，只用来和后面括号里的线上数字比较，不代表实际打开速度。

## 第三步：切换（选深夜，停写约 15–30 分钟）

**提前说明**：Cloudflare 的 DNS 记录默认缓存 5 分钟，改 IP 后几分钟内全国生效，不用提前准备。
从第二步打全量包到切换这段时间，**先不要发新版本**；如果发了也没关系，切换后新服务器打开自动部署时会按顺序补上。

**切换当天**：
1. [ ] 旧服务器：停止网站和定时任务，不再有新数据写入
   ```bash
   systemctl stop flow flow-daily.timer flow-backup.timer flow-autodeploy.timer
   ```
2. [ ] 旧服务器：只打包数据库 `cd /root/flow-migrate-tools && bash pack.sh --db-only`，`scp` 到新服务器。
3. [ ] 新服务器：换上最新数据库 `bash unpack.sh /root/flow-migrate-日期-db.tar.gz --db`（会自动重启网站）。
4. [ ] Cloudflare：`flow.jasa.hk` 改成新服务器的 IP，并且改成**仅 DNS（灰色云朵）**。
5. [ ] 新服务器：打开自动部署 `systemctl enable --now flow-autodeploy.timer`。旧服务器的自动部署保持关闭。
6. [ ] 检查：`python3 check_site.py 新服务器IP` 全部通过；手机流量（不连 Wi-Fi）打开网站，登录、学一篇、复习一次。
7. [ ] 告诉我，我发一个小版本走一遍自动部署和线上自动测试，确认新服务器的发布流程也通了。

**出问题怎么退回**：Cloudflare 把 IP 改回旧服务器，旧服务器 `systemctl start flow flow-daily.timer flow-backup.timer flow-autodeploy.timer`。切换后新产生的数据在新服务器上，退回前用 `pack.sh --db-only` 反方向拷回去即可。

## 收尾（切换后几天内）

- [ ] 旧服务器保留至少 3–7 天，确认没问题再停机。期间**不要**在旧服务器上启动网站。
- [ ] itdog 全国测速，和迁移前对比。
- [ ] 第二天确认：新服务器的每日备份（`/www/backup/flow/daily` 里有新文件夹）和凌晨 4 点的每日线上测试都正常。
- [ ] 删掉两台服务器上的迁移包：`rm -f /root/flow-migrate-*.tar.gz`；新服务器 `rm -rf /root/flow-migrate-stage`。

## 需要你决定 / 由你操作的事

- 买服务器、登录服务器、改 Cloudflare、创建 Cloudflare API 令牌：都由你来做（或你在内置浏览器里登录宝塔后，我在面板终端里一步步执行，每一步先告诉你）。
- 旧服务器上的其他网站（如果有）怎么处理。
- 切换的时间。
