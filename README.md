# 汀沿巡查 · 公共座椅漏查估算

汀沿养护站的 7 人班组负责滨江步道的座椅清点与维修。过去两支队把照片交到 `沿江座椅盘点-11月.xlsx` 汇总。领班难以发现两轮记录里同号复记，也不好区分确实漏查与资产迁移，低重合区段常被迫照单派发。系统把区段、两轮带编号的发现、补巡优先级接起来，生成值班组派发表。

| 角色 | 页面 | 权限与动作 |
|---|---|---|
| `analyst` 路线协调员 | 巡查区段、巡查批次、双轮发现清单、漏查估算 | 管理区段与批次、登记发现、核对双轮标签并创建估算 |
| `manager` 巡查领班 | 补巡派发 | 协调员权限，另可签核计划、查看审计 |
| `viewer` 养护观察员 | 各模块 | 查阅记录与导出派发表 |

## 批次归集与迟到补入

离线巡查常晚于回传，跨日上传不能按回传时间归批。系统以**批次采集时段**（`survey_batches.collected_from/collected_to`）为准归集：

1. 先在「巡查批次」建立批次与实际采集窗口。
2. 每条发现带设备生成的去重键 `client_ref` 与实际采集时间 `collected_at`。采集时间落在窗口内进入当批台账（`current`）；落在窗口外（跨日迟到）进入该批次的**补入队列**（`pending`），不混入当批口径。
3. **幂等入库**：设备重试或整批重送保持同一 `client_ref`，命中唯一索引即返回已入库记录，绝不重复写入；轮内同标签自然键冲突仍返回 409。
4. 首版估算只锁定窗口内记录。补入队列非空时由协调员发起「补入重算」：补入记录先锁定为 `supplemented`，后台按「旧版快照 + 补入记录」生成新版本。
5. **一次性原子切换**：新版本计算成功后，旧版本整体置为失效、新版本成为唯一有效版本（`is_effective`）；计算失败则补入记录退回队列、旧派发表保持有效与原口径。历史版本的快照与结果始终保留，可随时复查。
6. 页面在「巡查批次」显示每个批次的补入队列数、累计补入数与版本链；「补巡派发」展示当前有效/历史标识、补入状态以及各区段**前后漏查数对比**和补入明细。
7. 下载的 CSV 同时带出当前有效版本号、本版是否有效、前后漏查对比与本次补入差异记录。

## 周末工作剧本

1. 07:20 查看 `NOV21-BENCH` 岸段范围，分别派出 A、B 两组，期间分开记录。
2. 08:05 收到 A 轮柳渡段 30 张有效座椅编号。
3. 09:15 收到 B 轮柳渡段 26 张有效编号，18 个标签同号。
4. 09:30 检查芦廊段 `BANK-04-S017` 的 B 轮待核照片。确认同一实物后在台账查验。
5. 09:40 标记船坞段受围挡影响，石桥段仅 1 个重合标签，均作为人工复核项。
6. 10:00 确认两轮独立，设最少 5 个匹配。柳渡段实见 38 个编号，估计总量约 43.05，漏查约 5.05。
7. 10:15 领班签核「午班优先巡柳渡段」，持久留存排程意见。
8. 10:30 养护员下载 CSV 发给午班，现场发现用于下一轮新的批次。

## 启动

```bash
cp .env.example .env
docker compose up --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

前端 `http://localhost:18283`、API `http://localhost:19283/docs`、MySQL `17783`。账号 `analyst@tingyan.demo`、`manager@tingyan.demo`、`viewer@tingyan.demo`，统一密码 `BankBench2026!`。

| 服务 | 作用 |
|---|---|
| frontend | Nginx 1.27，原生 HTML/CSS/JS，`/api` 反代 |
| backend | Python 3.11、FastAPI、SQLAlchemy 与 JWT 权限 |
| worker | 持久估算任务，Redis 唤醒，生成共享卷 JSON 产物 |
| db | MySQL 8.0 持久存储区段、发现、补巡单、审计 |
| redis | Redis 7，由后端与 Worker 使用 |

`.env` 提供各映射端口、`SEED_DEMO`、`NETWORK_SUBNET`、`JWT_SECRET`、`DB_PASSWORD` 和 `MYSQL_ROOT_PASSWORD` 的覆盖入口。数据表与校验见 `backend/src/models` 与 `schemas`，保留数据卷的结构升级见 `backend/src/config/migrations.py`（应用启动时幂等执行），计算见 `backend/src/services/coverage.py`，页面见 `frontend/src/pages`。本地可用 `docker compose exec -T backend python -m compileall src` 检查 Python 模块。角色、任务与归集状态在 `backend/src/constants/enums.py`、`frontend/src/constants/enums.js`、权限和流程页配套定义；照片标签核验状态同时在 `CaptureInput` 与双轮清单页出现。

## 计算口径

按批次、区段、轮次和唯一实物标签记录。同一轮的同一标签重复写入会阻断；跨轮合并以交集 `m` 和并集计算。Chapman 点估计为 `(nA+1)(nB+1)/(m+1)-1`，使用 Chapman 方差公式。漏查估计为总量减实见，并按分段结果排序。已确认独立样本、区段封闭、标签全部核对且重合数达到门槛后才输出数值。共享巡查路径、材质或位置导致可见性不均会偏置估计。项目使用固定模拟清单，每个派发表版本保留计算时快照与口径，补入重算生成新版本而不改写历史版本；建议按报告复查，派发表在系统中签核后可下载（仅当前有效版本可签核），现场派单仍由班组执行。

MIT License，见 `LICENSE`。
