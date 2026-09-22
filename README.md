# 服务器巡检平台（server-inspect-platform）

对 Linux 主机执行**系统**与**安全**两类巡检，结果写入数据库，一键导出 Markdown 报告。

提供 REST 接口 + 极简 Web 页面，支持巡检本机，也支持通过 SSH 巡检远程主机。

---

## 为什么做这个

原来做服务器巡检是手动跑一堆脚本：登录机器、执行 `vmstat`、`df`、翻 `auth.log`、看 `sshd_config`，
结果散落在各个终端里，查历史只能靠翻聊天记录。

这个平台把这件事变成一条链路：

```
发起巡检 → 逐项采集 → 判定是否越线 → 落库 → 出报告 → 查历史
```

采集逻辑沿用了已有的 Shell 脚本（SSH 登录审计、CIS 基线核查），
区别在于：**从"手动跑脚本"变成"可调度、可存储、可追溯的服务"**。

---

## 功能

- **两类巡检项**：系统类（CPU / 内存 / 磁盘 / 负载）、安全类（SSH 登录失败 / root 登录策略 / 密码有效期）
- **阈值判定**：每项检查给出实测值 + 阈值，结果分 `正常 / 警告 / 异常` 三档
- **本地 + 远程**：`address=local` 巡检本机；填 IP + SSH 账号巡检远程主机
- **结果落库**：SQLite 存三张表（主机 / 巡检记录 / 逐项结果），历史随时可查
- **报告导出**：一键生成 Markdown 巡检报告，含结论、分组明细和待处理问题清单
- **定时巡检**：设置 `SCHEDULE_MINUTES` 后自动周期性巡检（默认关闭）
- **容器化部署**：`docker compose up` 一条命令起服务

---

## 巡检项

| 分类 | 检查项 | 判定方式 |
| --- | --- | --- |
| 系统 | CPU 使用率 | `vmstat` 采样，阈值 < 80% |
| 系统 | 内存使用率 | `free` 计算，阈值 < 85% |
| 系统 | 根分区磁盘使用率 | `df /`，阈值 < 85% |
| 系统 | 系统负载（每核） | `loadavg / nproc`，阈值 < 1.5 |
| 安全 | SSH 登录失败次数 | 统计 `auth.log` 中 Failed password，≥ 5 次判异常 |
| 安全 | SSH root 登录策略 | 检查 `PermitRootLogin`，`yes` 判异常 |
| 安全 | 密码有效期策略 | 检查 `PASS_MAX_DAYS`，超过 365 天判异常 |

> 采集命令统一以 `LC_ALL=C` 执行：中文 locale 下 `free` 的表头会被翻译成「内存：」，
> 用 `^Mem:` 匹配取不到值；部分 locale 还会用逗号作小数点，导致数值被拆成两段。

判定逻辑分三档：越过阈值判 `异常`，达到阈值 80%~90% 判 `警告`（提前预警），其余判 `正常`。
指标不可用时（例如没有权限读 `auth.log`）判 `警告` 并说明原因，不会伪装成正常。

阈值集中在 `app/config.py`，也可用环境变量覆盖，改阈值不用动代码。

---

## 技术栈

| 层 | 选型 |
| --- | --- |
| Web 框架 | FastAPI（自带 Swagger 接口文档） |
| ORM | SQLAlchemy 2.x |
| 数据库 | SQLite |
| 远程执行 | paramiko（SSH） |
| 定时调度 | APScheduler |
| 页面 | Jinja2 + 原生 JS |
| 部署 | Docker + Docker Compose |

---

## 快速开始

### 方式一：Docker（推荐）

```bash
docker compose up -d --build
```

打开 http://127.0.0.1:8000

### 方式二：本地直接跑

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

打开 http://127.0.0.1:8000 ，接口文档在 http://127.0.0.1:8000/docs

### 用起来

1. 页面上添加一台主机：名称随便写，地址填 `local` 表示巡检本机
2. 点「立即巡检」，几秒后出结果
3. 点「查看」下载该次巡检的 Markdown 报告

> 巡检项里的安全类检查需要读 `/var/log/auth.log`，普通用户读不到。
> 想让这两项正常出值，把运行用户加入 `adm` 组：`sudo usermod -aG adm $USER` 后重新登录。

### 实际跑一次长什么样

在 Ubuntu 22.04 虚拟机上对 `local` 巡检的一次真实输出：

```
巡检 #3  正常4/警告1/异常2 共7项
[PASS] CPU 使用率            0   (< 80%)
[PASS] 内存使用率         32.42   (< 85%)
[PASS] 根分区磁盘使用率      73   (< 85%)
[PASS] 系统负载（每核）    0.06   (< 1.5)
[FAIL] SSH 登录失败次数       5   (≥ 5 次即告警)
[WARN] SSH root 登录策略          (不允许 root 直接登录)
[FAIL] 密码有效期策略     99999   (≤ 365 天)
```

后三项不是程序出错，而是这台机器上**真实存在的加固缺口**：
`PASS_MAX_DAYS=99999`（密码永不过期）、`PermitRootLogin` 在 `sshd_config` 里被注释掉
（等于依赖发行版默认值，CIS 要求显式写 `no`）、以及实验过程中累计的 5 次 SSH 登录失败。
这三条正说明工具真的能查出问题 —— 巡检工具的价值在于"能发现问题"，不是"永远全绿"。

---

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/hosts` | 登记一台被巡检主机 |
| GET | `/api/hosts` | 主机列表 |
| DELETE | `/api/hosts/{id}` | 删除主机 |
| POST | `/api/scans` | 对指定主机发起一次巡检 |
| GET | `/api/scans` | 历史巡检记录（可按主机过滤） |
| GET | `/api/scans/{id}` | 某次巡检的逐项结果 |
| GET | `/api/scans/{id}/report` | 导出 Markdown 报告 |
| GET | `/api/health` | 健康检查 |

示例：

```bash
# 登记本机
curl -X POST http://127.0.0.1:8000/api/hosts \
  -H 'Content-Type: application/json' \
  -d '{"name":"ubuntu-test","address":"local"}'

# 发起巡检
curl -X POST http://127.0.0.1:8000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"host_id":1}'

# 看报告
curl http://127.0.0.1:8000/api/scans/1/report
```

---

## 项目结构

```
server-inspect-platform/
├── app/
│   ├── main.py         # FastAPI 入口：路由、页面、定时任务
│   ├── config.py       # 阈值与运行参数（环境变量可覆盖）
│   ├── database.py     # 引擎与会话管理
│   ├── models.py       # 三张表：hosts / scans / check_results
│   ├── schemas.py      # 请求与响应模型
│   ├── checks.py       # 巡检项定义（命令 + 判定逻辑）
│   ├── connector.py    # 执行器：本地 shell / 远程 SSH
│   ├── runner.py       # 巡检执行引擎
│   ├── report.py       # Markdown 报告渲染
│   └── templates/
│       └── index.html  # 极简页面
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 设计说明

**巡检项与执行方式解耦。** `checks.py` 里每个巡检项只描述「跑什么命令、怎么判定」，
不关心命令在哪台机器上跑；`connector.py` 负责把它送到本地或远程执行。
所以新增巡检项只是往列表里加一条，不用改执行链路。

**三层数据模型。** `hosts → scans → check_results` 一条链：
一台主机可以有多次巡检，一次巡检有多个检查项结果。
汇总数字（总数/正常/警告/异常）冗余在 `scans` 表上，列表页不用联表统计。

**判定不掩盖失败。** 命令执行失败或指标读不到时，不返回 0 假装正常，
而是标记 `警告/异常` 并在说明里写清原因 —— 巡检工具最忌讳的就是"假通过"。

**刻意不做并发。** 一次巡检 7 条命令，串行几秒内完成。
多主机并发留到需要时再加，先保证结果可追溯。

---

## 后续计划

- [ ] 多主机并发巡检（线程池）
- [ ] 巡检报告 PDF 导出
- [ ] 阈值越线后邮件/企业微信告警
- [ ] 巡检项以配置文件的形式外置，支持自定义
- [ ] 页面加上趋势图（同一主机多次巡检的指标变化）
