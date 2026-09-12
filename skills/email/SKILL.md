---
name: email
description: >-
  大规模企业邮箱迁移（腾讯企业邮等 IMAP 源 → Microsoft 365 Exchange Online 50GB 邮箱）的
  端到端工作流：CSV 准备与校验、容量摸底基线、超限识别、小批量验证、分批迁移、迁移后核对与
  汇总报告，以及 imapsync 第三方兜底（TODO）。当用户要求"迁移企业邮箱/批量邮箱"、"腾讯企业邮
  迁移到微软/Exchange Online"、"生成或校验迁移 CSV"、"分析超限邮箱"、"分批迁移邮箱"、"核对
  迁移结果"、"出迁移汇总报告/进度报告"时使用，也适用于其他 IMAP 源 → Exchange Online 的迁移场景。
metadata:
  version: "2.5.0"
---

# email — 大型企业邮箱迁移（入口）

把数百个邮箱从腾讯企业邮等 IMAP 源迁到 M365 Exchange Online（单邮箱 50GB 硬上限）。核心矛盾：源不限容量、目标 50GB 封顶；官方工具超限会从最旧邮件静默丢弃，但支持 `-ContentFilter` 按 Received 时间裁剪（商业标准版直接可用，优先于 imapsync）。

本文件只讲**流程、分工、硬性纪律**；命令细节、参数、故障排查一律见 `references/`。

## 文档体系与强制阅读顺序

| 文档 | 定位 | 何时读 |
|------|------|--------|
| 本文件 | 入口：流程、分工、硬性纪律 | 每次任务开始 |
| `references/migration-workflow.md` | **唯一 EXO 操作手册**：执行模式、生命周期规则、逐阶段命令模板、核对口径、故障排查、超限路线 | 执行任何 EXO 操作前，读 0.5 节全文 + 对应阶段章节 |
| `references/report-spec.md` | 汇总报告规范：Sheet 结构、列口径、数据源、着色、列宽 | 生成/更新汇总报告前 |
| `docs/email_root_task.md` | 原始需求背景与约束 | 首次理解场景时 |
| `docs/email_migrate.md` | 背景与现场实测结论（命令细节已并入 workflow） | 需要背景/实测结论时 |

**强制规则**：
1. 执行任何 EXO 命令前，必须已读 workflow 0.5 节（EXO 命令执行模式与规范）全文，并查阅其中该命令的条目；禁止凭记忆或单一文档执行。
2. 修改 CSV、批次、终结点等高危操作前，对照下文「硬性纪律」逐条自查。
3. 文档间冲突时以 `references/migration-workflow.md` 为准，并当场修正过时的一方。
4. **发现本技能的坑直接修**：脚本/文档有 bug、口径错误或实测踩坑，直接修代码 + 文档并补回归测试，写清改了什么即可；不要只报告不修、不要反复征求同意。

## 基线口径（最高优先级，务必遵守）

1. **基线的唯一来源是 `probe` 产物**：`email_check_success_*.csv`（账号级：`email,total_count,total_size,size_text(MB)`）与 `probe_report_*.csv`（逐文件夹明细）。账号封数与占用空间一律以它为准。
2. **名单 CSV（password.csv 等）里的 `total_count/total_size/size_text(MB)` 是 `backfill` 回填的历史拷贝，不是基线**：只能参考，禁止当基线用于核对与报告；同名列数量不全 ≠ 没有基线。
3. 需要基线时按以下顺序处理，**禁止跳步、禁止自作主张重跑 probe**：
   - a. 先找 `probe` 产物 CSV（默认落在产物根目录的 `email-migration/` 子目录，见"产物路径"）；
   - b. 找不到就查 `logs/probe_*.log`——日志含逐账号「文件夹 N 个/邮件总数/空间占用」与逐文件夹明细，可据以重建（封数精确；空间占用按日志小数位反算，有 ±几 KB 级舍入误差）；
   - c. 确实拿不到、或用户明确要求刷新，才重跑 `probe`。
4. **重跑 probe 前必须先问用户**，标准口径：**「是否重新联网跑 probe 对原邮箱数据摸底，还是直接使用现有的上次摸底结果文件？」** 问的同时给出：现有基线的来源与时间点、重跑代价（约 20~30 分钟、只读源端）。**用户答复前禁止开跑。**
5. 基线与 webmail 抽样交叉校验（尤其收取范围收敛后）见 workflow「源端统计标准方法」。

## 产物路径（`--output` 语义）

- 脚本 `--output` 传**产物根目录**（默认 `output`），脚本内部自动拼 `email-migration/` 子目录，产物落在 `<根>/email-migration/`（CSV、`logs/`、`state/`）。传 `output/email-migration` 会得到嵌套目录 `output/email-migration/email-migration/`，禁止。
- 迁移数据只走共享产物目录，便于跨会话续接与脚本消费。

## 执行边界（双模式）

- **模式 A：agent 代理执行 EXO（默认）**：agent 以持久 PTY 会话建立 EXO 连接，用户完成一次浏览器授权，之后 agent 在同一会话内执行一切 EXO 命令。规范见 workflow 0.5 节。 **会话生命周期归用户**：用户未明确要求断开之前，禁止 `Disconnect-ExchangeOnline`、`exit` 或终止该持久会话进程（重建需用户重新完成浏览器授权，代价高、可能受限）。
- **模式 B：人工执行（回退）**：PTY 不可用或用户要求人工确认时，agent 产出精排命令，人工在已登录 PowerShell 执行，结果经共享输出文件回流。
- **agent 始终独立执行**：`validate`/`generate`/`split`/`backfill`（本地 CSV）、`probe`/`check`（源 IMAP 直连）、`analyze`/`verify`（消费已导出 CSV）、`state`（本地状态）。

## 硬性纪律：跑前检查（下发 EXO 命令前必做）

**高危规则速查**（违反即失败或泄露，逐条自查；完整规范以 workflow 0.5 节为权威）：

1. `-CSVData` 只接受 CSV 文件字节：`[System.IO.File]::ReadAllBytes(<路径>)`；禁止传 `Import-Csv` 对象数组（类型错误，且报错回显含密码内容）。
2. 删除批次必须逐批显式 `-Identity`；管道删除对 Stopped 批静默失效。未到 Stopped 禁止删除；`Get-MigrationBatch` 为空前禁止建新批。
3. 终结点 `TencentIMAPEndpoint` 保留勿删。
4. 迁移前必做：腾讯"收取范围"确认为"全部"；目标邮箱 `MaxReceiveSize` 放大至 150MB。
5. **EXO 会话不主动断开**：用户未明确说明时，禁止 `Disconnect-ExchangeOnline`、`exit`、终止会话进程或关闭窗口；仅当用户明确指示（或会话已确认失效需恢复）才可断开，并说明原因。

**勘察清单**——先排除隐患，再执行正式命令：命名冲突先查后建；不直接信 `Get-MigrationUserStatistics` 的 BatchId 过滤输出（有 BUG），用 `-Identity` 定向核对；源/目标账号存在性；`-Analyze` 前置条件；同批两次连通性测试会被节流；删前确认只删终态批。细节见 workflow。

## 工作流（每阶段一个交互闭环；阶段结尾执行 `state --advance`）

> 各阶段的完整命令、CSV 格式、故障排查、超限处理路线见 `references/migration-workflow.md` 对应章节。

- **阶段 0 前置检查**：`validate` → `generate` → `probe` 摸底（基线）→ `check` 验登录可用性。收取范围必须为"全部"，并与 webmail 抽样交叉验证基线。
- **阶段 1 分析 + 超限识别**：建 `-Analyze` 批 → 导出统计 → `analyze` 筛超限（默认 >45GB 或 >50 万条，见 workflow）。超限路线：优先 `-ContentFilter`，需归档才用 XML mapping，imapsync 仅兜底。
- **阶段 2 小批量验证**：`split --batch-size 15` 拆验证批 → 正式迁移 → 核对邮件数/文件夹映射/抽样完整性，通过才放量。
- **阶段 3 分批正式迁移**：`split --batch-size 50` → 按创建批次规范建批并监控至完成；大邮箱（10GB+）首轮数小时属正常，**勿删批重建**。
- **阶段 4 收尾核对**：导出 `folder_stats.csv`（列必须 `EmailAddress,FolderPath,ItemsInFolder`）→ `verify` 出核对报告；全部通过后清理终态批、切换 MX、停同步；**终结点保留**。汇总报告见 `references/report-spec.md`。目标侧邮件数口径 = 邮件类文件夹的**可见**邮件数，禁用邮箱 `ItemCount`（含日历/隐藏项），详见 report-spec.md「目标侧统计口径」。

## 分步执行与进度播报（硬性）

多步任务一次只做一步、执行前说明意图与预计耗时、执行后立即播报结果——按全局记忆「进度可见」规则执行，此处只列本技能的追加硬性要求：

- 长步骤（probe 20~30 分钟、逐邮箱导 `folder_stats`、批处理等待）必须周期性播报进度，禁止静默长跑。
- 禁止无差别全树扫描目录，只走精确路径；输出体量未知时先探规模（计数/表头/tail）再决定是否读取。
- 禁止自作主张替用户做选择（如是否重跑 probe，见「基线口径」第 4 条）。

## 固化流程：收尾出报告（按序执行，不要手敲命令拼参数）

1. **EXO 会话检查（步骤 1）**：在模式 A 的会话内 `. <技能目录>/scripts/exo_tasks.ps1`，然后 `Assert-ExoSession`。
   - 未登录则提示 `Connect-ExchangeOnline`；会话归用户掌握，**不得自动连接或断开**。
2. **源账号可用性（步骤 2）**：`python <技能目录>/scripts/email_migration.py check password.csv`（登录即登出，不统计邮件）。
3. **源端摸底（步骤 3，可选）**：`python <技能目录>/scripts/email_migration.py probe password.csv --manifest password.csv`
   - 参数详见 `probe --help` 的说明表（`--detail/--no-detail`、`--no-size`、`--retry N`、`--timeout`、`--host/--port`，每条都标注多拿什么数据、是否增加耗时）。
4. **出最终报告（步骤 4）**：`python <技能目录>/scripts/email_migration.py report --batch <批名> [--dry-run]`
   - 直接取**最近一次 probe 摸底 CSV**（不重跑 probe，避免浪费时间），并把该 CSV 的「基线文件 / 基线数据时间」写入报告概要；
   - `user_stats.csv`/`target_stats.csv` 由 EXO 会话内 `Export-UserStats`/`Export-TargetStats` 导出；
   - 输入缺失或统计早于基线时会明确告警；`--dry-run` 只校验时效不生成。
## 状态机（跨会话续接）

进入任务先读、离开任务前更新状态文件 `<产物根>/email-migration/state/email-migration-state.json`，阶段推进必须落盘，避免重复已完成步骤：

```bash
python <技能目录>/scripts/email_migration.py state              # 查看
python <技能目录>/scripts/email_migration.py state --advance    # 阶段完成推进
python <技能目录>/scripts/email_migration.py state --todo "..." # 记待确认
python <技能目录>/scripts/email_migration.py state --confirm "..." # 标确认
python <技能目录>/scripts/email_migration.py state --phase phase3 # 跳阶段
python <技能目录>/scripts/email_migration.py state --note "..." # 记备注
```

## 资源

- `scripts/email_migration.py`：`validate/generate/split/analyze/probe/check/backfill/verify/report/state`；用法见 `--help`。密码只在代码内流转，命令/报告/日志不出现密码原文。`check` 只做登录可用性探测并出报告，**不做任何账号在不同名单文件间的移动/归类**——名单归属由用户决定。
- `scripts/rebuild_baseline_from_probe_log.py`：probe 产物 CSV 缺失时，从 `logs/probe_*.log` 重建基线 CSV（口径同 probe）。
- `scripts/gen_migration_report.py`：报告生成引擎（由 `report` 子命令调用，也可独立运行），结构见 `references/report-spec.md`。
- `scripts/exo_tasks.ps1`：EXO 侧固化任务（模式 A 会话内 dot-source）：`Assert-ExoSession`（只查不断）、`Export-UserStats`/`Export-TargetStats`/`Export-FolderStats`（供报告与核对）。**该脚本从不连接、不断开会话、不删除对象。** `Export-TargetStats`/`Export-FolderStats` 的邮件数口径 = 邮件类文件夹的**可见**邮件数（`VisibleItemsInFolder`），坑见 report-spec.md。
- `references/migration-workflow.md`：**EXO 操作手册**——执行模式、批生命周期、逐阶段命令、CSV 格式、核对口径、故障排查、超限路线、`-ContentFilter`、imapsync 兜底。**执行真实环境操作前先读对应章节**。
- `docs/email_root_task.md`：原始需求背景与约束。
