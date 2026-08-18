---
name: email
description: >-
  大规模企业邮箱迁移（腾讯企业邮等 IMAP 源 → Microsoft 365 Exchange Online 50GB 邮箱）的
  端到端工作流：CSV 准备与校验、容量分析与超限识别、小批量验证、分批迁移、迁移后核对，
  以及 imapsync 第三方兜底（TODO）。当用户要求"迁移企业邮箱/批量邮箱"、"腾讯企业邮迁移到
  微软/Exchange Online"、"生成或校验迁移 CSV"、"分析超限邮箱"、"分批迁移邮箱"、"核对迁移结果"
  时使用，也适用于其他 IMAP 源 → Exchange Online 的迁移场景。
metadata:
  version: "2.0.0"
---

# email — 大型企业邮箱迁移

把数百个邮箱从腾讯企业邮等 IMAP 源迁到 M365 Exchange Online（单邮箱 50GB 硬上限）。核心矛盾：源不限容量、目标 50GB 封顶；官方工具超限会从最旧邮件静默丢弃，但支持 `-ContentFilter` 按 Received 时间裁剪（商业标准版直接可用，优先于 imapsync）。

**执行边界（决定谁能跑什么，先读）**：agent 的命令行跑在独立 bash 子进程（Git Bash/MSYS2/WSL），拿不到 `Connect-ExchangeOnline` 绑定在你 PowerShell 会话里的登录态 token。因此——

- **agent 可独立跑**：`validate` / `generate` / `split`（本地 CSV）、`probe`（源 IMAP 直连）、`analyze` / `verify`（消费已导出 CSV）、`state`（本地状态）。这些都不碰 EXO 登录态、数据来自本地文件或源 IMAP 直连。
- **必须人工在已登录 PowerShell 执行**：一切 EXO 命令（`Get-Mailbox` / `New-MigrationEndpoint` / `New-MigrationBatch` / `Get-MailboxFolderStatistics` 等）。agent 只产出精排命令、消费你的导出结果、推进状态，闭环靠共享输出文件承载。

## 硬性纪律：跑前检查（下发 EXO 命令前必做）

**先勘察、排除隐患，再执行**——任一命中先加前置勘察命令，确认无隐患再给正式命令：

1. **命名冲突**：新批/终结点名是否已存在（反复调试易撞）→ `Get-MigrationBatch` / `Get-MigrationEndpoint` 先查，已存在先删旧或用时间戳新名。
2. **残留批污染统计**：历史批干扰数据 → 不直接信 `Get-MigrationUserStatistics` 的 BatchId 过滤输出（有 BUG 会带出别批记录），用 `-Identity` 定向 + 显式 `BatchId` 核对。
3. **账号存在性**：CSV 源/目标账号两端是否都对 → `probe` 测源、目标已建判断。
4. **状态前置**：`-Analyze` 要求目标邮箱已建；正式迁移要求分析/连通性就绪。前置未满足就不跑。
5. **节流**：连通性测试、批处理紧连两次会被拒绝，需拉开间隔或先查已有。
6. **删前确认**：`Remove-MigrationBatch` 只删终态批，`Syncing/Synced` 先 `Stop` 或跳过；**绝不删复用的 `TencentIMAPEndpoint` 终结点**。

## 工作流（每阶段一个交互闭环；每阶段结尾 `state --advance`）

> 每阶段展开：**具体 PowerShell 命令、CSV 格式、故障排查、超限处理路线、交互详情 → 见 `references/migration-workflow.md` 对应章节**。SKILL.md 只记录流程与分工，不重复命令细节。

### 阶段 0：前置检查
- agent：`validate` 校验 CSV → `generate` 生成迁移 CSV → `probe` 测源 IMAP 摸底（邮件数/占用字节）。
- 人工：确认 M365 邮箱已建并分配许可证、腾讯 IMAP 可访问且收取范围="全部"（默认只收 30 天）。
- **硬顺序：先登录 EXO** `Import-Module ExchangeOnlineManagement; Connect-ExchangeOnline`，再验证终结点就绪。终结点/批处理服务端持久化，**先查再建**，勿盲目重复 `New-MigrationEndpoint`。

### 阶段 1：分析 + 超限识别
- 人工在已登录会话建分析批 `New-MigrationBatch -Analyze`，导出统计 CSV 到共享目录。
- agent：`analyze <csv>` 筛超限名单（阈值默认 >45GB 或 >50 万条，见参考）。
- 超限处理路线（人工确认）：优先 `-ContentFilter` 按时间裁；需归档才 XML mapping（要云归档许可）；imapsync 仅兜底。

### 阶段 2：小批量验证
- agent：`split <csv> --batch-size 15` 拆验证批。
- 人工：执行小批量正式迁移，核对邮件数/文件夹映射/抽样完整性；用 `-Identity` 定向查单邮箱规避 BatchId BUG。验证通过才放量。

### 阶段 3：分批正式迁移
- agent：`split <csv> --batch-size 50` 拆全量批。
- 人工：逐批 `New-MigrationBatch -AllowUnknownColumnsInCsv $true`，监控至完成；失败用户经 Exchange 管理中心处理。

### 阶段 4：收尾核对
- 人工导出 `Get-MailboxFolderStatistics` 到 `folder_stats.csv`（列名必须 `EmailAddress,FolderPath,ItemsInFolder`，用 `PrimarySmtpAddress` 标识邮箱）。
- agent：`verify <csv>` 生成核对报告。
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

- `scripts/email_migration.py`：`validate/generate/split/analyze/probe/verify/state`；运行 `python <技能目录>/scripts/email_migration.py --help` 查用法。密码只在代码内流转，命令/报告/日志不出现密码原文。
- `references/migration-workflow.md`：**EXO 人工命令指南**——CSV 格式、连接、终结点、分析、批处理、核对、注意事项、故障排查、超限路线、`-ContentFilter` 时间裁剪、imapsync 兜底，含「脚本用途 | 谁执行」一览。**执行真实环境操作前先读对应章节**。
- `docs/`：原始需求文档（背景、约束），理解场景时阅读。
