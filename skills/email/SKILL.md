---
name: email
description: >-
  大规模企业邮箱迁移（腾讯企业邮等 IMAP 源 → Microsoft 365 Exchange Online 50GB 邮箱）的
  端到端工作流：CSV 准备与校验、容量分析与超限识别、小批量验证、分批迁移、迁移后核对，
  以及 imapsync 第三方兜底（TODO）。当用户要求"迁移企业邮箱/批量邮箱"、"腾讯企业邮迁移到
  微软/Exchange Online"、"生成或校验迁移 CSV"、"分析超限邮箱"、"分批迁移邮箱"、"核对迁移结果"
  时使用，也适用于其他 IMAP 源 → Exchange Online 的迁移场景。
metadata:
  version: "2.4.0"
---

# email — 大型企业邮箱迁移

把数百个邮箱从腾讯企业邮等 IMAP 源迁到 M365 Exchange Online（单邮箱 50GB 硬上限）。核心矛盾：源不限容量、目标 50GB 封顶；官方工具超限会从最旧邮件静默丢弃，但支持 `-ContentFilter` 按 Received 时间裁剪（商业标准版直接可用，优先于 imapsync）。

## 文档体系与强制阅读顺序

| 文档 | 定位 | 何时读 |
|------|------|--------|
| 本文件 | 入口：流程、分工、硬性纪律 | 每次任务开始 |
| `references/migration-workflow.md` | 工作流规范：执行模式、生命周期规则、命令模板、核对口径 | 执行任何 EXO 操作前，读 0.5 节全文 + 对应阶段章节 |
| `docs/email_migrate.md` | EXO 命令手册：逐条命令、参数、用途 | 执行任何 EXO 命令前，查对应命令条目 |
| `docs/email_root_task.md` | 原始需求背景 | 仅首次理解场景时 |

**强制规则**：
1. 执行任何 EXO 命令前，必须已读 workflow 0.5 节（EXO 命令执行模式与规范）全文，并查阅 `docs/email_migrate.md` 中该命令的条目；禁止凭记忆或单一文档执行。
2. 修改 CSV、批次、终结点等高危操作前，对照下文「硬性纪律」逐条自查。
3. 文档间冲突时，以 `references/migration-workflow.md` 为准，并修正过时一方。

## 执行边界（双模式）

- **模式 A：agent 代理执行 EXO（默认）**：agent 以持久 PTY 会话建立 EXO 连接，用户完成一次浏览器授权，之后 agent 在同一会话内执行一切 EXO 命令。规范见 workflow 0.5 节。
- **模式 B：人工执行（回退）**：PTY 不可用或用户要求人工确认时，agent 产出精排命令，人工在已登录 PowerShell 执行，结果经共享输出文件回流。
- **agent 始终独立执行**：`validate` / `generate` / `split` / `backfill`（本地 CSV）、`probe` / `check`（源 IMAP 直连）、`analyze` / `verify`（消费已导出 CSV）、`state`（本地状态）。

## 硬性纪律：跑前检查（下发 EXO 命令前必做）

**高危规则速查**（违反即失败或泄露，逐条自查；完整规范以 `references/migration-workflow.md` 0.5 节为权威，本表为入口速查）：

1. `-CSVData` 只接受 CSV 文件字节：`[System.IO.File]::ReadAllBytes(<路径>)`；禁止传 `Import-Csv` 对象数组（类型错误，且报错回显含密码内容）。
2. 删除批次必须逐批显式 `-Identity`；管道删除对 Stopped 批静默失效。未到 Stopped 状态禁止删除；`Get-MigrationBatch` 为空前禁止建新批。
3. 终结点 `TencentIMAPEndpoint` 保留勿删。
4. 迁移前必做：腾讯"收取范围"确认为"全部"；目标邮箱 `MaxReceiveSize` 放大至 150MB。

**勘察清单**——先排除隐患，再执行正式命令：

1. **命名冲突**：新批/终结点名是否已存在（反复调试易撞）→ `Get-MigrationBatch` / `Get-MigrationEndpoint` 先查，已存在先删旧或用时间戳新名。
2. **残留批污染统计**：历史批干扰数据 → 不直接信 `Get-MigrationUserStatistics` 的 BatchId 过滤输出（有 BUG 会带出别批记录），用 `-Identity` 定向 + 显式 `BatchId` 核对。
3. **账号存在性**：CSV 源/目标账号两端是否都对 → `probe` 测源、目标已建判断。
4. **状态前置**：`-Analyze` 要求目标邮箱已建；正式迁移要求分析/连通性就绪。前置未满足就不跑。
5. **节流**：连通性测试、批处理紧连两次会被拒绝，需拉开间隔或先查已有。
6. **删前确认**：`Remove-MigrationBatch` 只删终态批，`Syncing/Synced` 先 `Stop` 或跳过；仍无效则到网页后台手动删（admin.cloud.microsoft/exchange#/migrationbatch）。

## 工作流（每阶段一个交互闭环；每阶段结尾 `state --advance`）

> 每阶段展开：**具体 PowerShell 命令、CSV 格式、故障排查、超限处理路线、交互详情 → 见 `references/migration-workflow.md` 对应章节**。SKILL.md 只记录流程与分工，不重复命令细节。

### 阶段 0：前置检查
- agent：`validate` 校验 CSV → `generate` 生成迁移 CSV → `probe` 测源 IMAP 摸底（邮件数/占用字节）→ `check` 只验证源账号登录可用性（改密后快速验凭据，不统计邮件）。probe 只依赖 UserName/Password，摸底 CSV 可不含目标邮箱；`--manifest`/`backfill` 细节见参考文档。
- **基线交叉验证（硬性）**：probe 结果必须抽样对照腾讯 webmail 实际数（收件箱 + 我的文件夹）。IMAP 求和明显小于 webmail 实际数（如 <50%）即收取范围受限，此时摸底与迁移都只见部分邮件——必须先改收取范围为"全部"再 probe，禁止以受限基线建批或核对；已建批的，改后靠增量同步补齐或重建批次。
- 人工/确认项：M365 邮箱已建并分配许可证、腾讯 IMAP 可访问且收取范围="全部"（默认只收 30 天）。
- **硬顺序：先登录 EXO** `Import-Module ExchangeOnlineManagement; Connect-ExchangeOnline`，再验证终结点就绪。终结点/批处理服务端持久化，**先查再建**，勿盲目重复 `New-MigrationEndpoint`。

### 阶段 1：分析 + 超限识别
- 建（模式 A）或人工在已登录会话建分析批 `New-MigrationBatch -Analyze`，导出统计 CSV 到共享目录。
- agent：`analyze <csv>` 筛超限名单（阈值默认 >45GB 或 >50 万条，见参考）。
- 超限处理路线（人工确认）：优先 `-ContentFilter` 按时间裁；需归档才 XML mapping（要云归档许可）；imapsync 仅兜底。

### 阶段 2：小批量验证
- agent：`split <csv> --batch-size 15` 拆验证批。
- agent（模式 A）或人工：执行小批量正式迁移，核对邮件数/文件夹映射/抽样完整性；用 `-Identity` 定向查单邮箱规避 BatchId BUG。验证通过才放量。

### 阶段 3：分批正式迁移
- agent：`split <csv> --batch-size 50` 拆全量批。
- agent（模式 A）或人工：按创建批次规范建批并监控至完成；**进行中/完成后按需产出迁移数据汇总报告**（workflow 0.5「迁移数据汇总报告规范」，`scripts/gen_migration_report.py`）；失败用户经 Exchange 管理中心处理。
- **大邮箱（10GB+）**：首轮同步数小时属正常，**勿删批重建**；增量同步机制与"源端删除不同步"见参考文档。

### 阶段 4：收尾核对
- 导出 `Get-MailboxFolderStatistics` 到 `folder_stats.csv`（列名必须 `EmailAddress,FolderPath,ItemsInFolder`，用 `PrimarySmtpAddress` 标识邮箱）。
- agent：`verify <csv>` 生成核对报告；验收输出在迁移数据汇总报告中追加文件夹对账、跳过明细两个 sheet（workflow 0.5「迁移数据汇总报告规范」）。
- 全部通过后：清理终态批、人工切换 MX 至 M365、停同步清理；**终结点 `TencentIMAPEndpoint` 保留勿删**。

## 状态机（跨会话续接）

每次进入/离开任务先读状态文件 `output/email-migration/state/email-migration-state.json`，避免重复已完成步骤：

```bash
python skills/email/scripts/email_migration.py state              # 查看
python skills/email/scripts/email_migration.py state --advance    # 阶段完成推进
python skills/email/scripts/email_migration.py state --todo "..." # 记待确认
python skills/email/scripts/email_migration.py state --confirm "..." # 标确认
python skills/email/scripts/email_migration.py state --phase phase3 # 跳阶段
python skills/email/scripts/email_migration.py state --note "..." # 记备注
```

## 资源

- `scripts/email_migration.py`：`validate/generate/split/analyze/probe/check/backfill/verify/state`；运行 `python <技能目录>/scripts/email_migration.py --help` 查用法。密码只在代码内流转，命令/报告/日志不出现密码原文。`check` 只做登录可用性探测并出报告，**不做任何账号在不同名单文件间的移动/归类**——名单归属由用户决定。
- `references/migration-workflow.md`：**EXO 人工命令指南**——CSV 格式、连接、终结点、分析、批处理、核对、注意事项、故障排查、超限路线、`-ContentFilter` 时间裁剪、imapsync 兜底，含「脚本用途 | 谁执行」一览。**执行真实环境操作前先读对应章节**。
- `docs/`：原始需求文档（背景、约束），理解场景时阅读。
