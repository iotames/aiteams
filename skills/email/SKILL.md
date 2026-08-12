---
name: email
description: >-
  大规模企业邮箱迁移（腾讯企业邮等 IMAP 源 → Microsoft 365 Exchange Online 50GB 邮箱）的
  端到端工作流：CSV 准备与校验、容量分析与超限识别、小批量验证、分批迁移、迁移后核对，
  以及 imapsync 第三方兜底（TODO）。当用户要求"迁移企业邮箱/批量邮箱"、"腾讯企业邮迁移到
  微软/Exchange Online"、"生成或校验迁移 CSV"、"分析超限邮箱"、"分批迁移邮箱"、"核对迁移结果"
  时使用，也适用于其他 IMAP 源 → Exchange Online 的迁移场景。
---

# email — 大规模企业邮箱迁移

## 概述

把数百个邮箱从腾讯企业邮等源迁移到 Exchange Online 标准版（每邮箱 50GB 硬上限）。核心矛盾：源容量不限、目标 50GB 封顶，且官方迁移工具无法按时间/容量筛选，超限时从最旧邮件开始静默丢弃。本技能提供脚本辅助与人工命令指南；真实连接类操作（Exchange Online 管理、迁移批处理）由人工执行，每个阶段都有必须人工确认的节点。

## 安全与隐私（最先读）

- 密码文件（如 password.csv）禁止用 cat/Get-Content 等命令直接读取，只用 `scripts/email_migration.py` 等代码读取
- 密码原文不得进入对话、日志、文档或任何输出；脚本只打印脱敏汇总
- 含密码的产物默认输出到 `<cwd>/output/email-migration/`（已被项目 .gitignore 忽略），不要移入仓库
- 不把含密码的文件内容粘贴给用户或写入记忆

## 交互第一步：向用户确认 CSV 格式

开始任何迁移任务前，先向用户展示并确认源 CSV 格式。主迁移只需要官方三列：

```csv
EmailAddress,UserName,Password
```

- 官方必填列：`EmailAddress`=目标邮箱地址；`UserName`=源邮箱登录名；`Password`=源邮箱密码
- 附加列（如 `TargetEmailPassword`=目标邮箱密码）只有 imapsync 等第三方兜底工具才需要，**不是主迁移的必需项**：当出现超限邮箱需要兜底时，再要求用户按需补充该列。官方迁移会忽略未知列，创建迁移批处理必须加 `-AllowUnknownColumnsInCsv $true`
- 校验失败（缺列、空值、重复）时，要求用户修正 CSV 后重试；不要猜测或补造字段
- 确认两列映射语义：`EmailAddress` 是目标地址，`UserName` 是源登录名，两者通常不同（如仅域名不同）

## 交互第二步：确认超限判定阈值

迁移开始前，向用户说明超限判定阈值（用于阶段 1 的 `analyze`），两个阈值都是可调默认值：

- 大小阈值：默认 >45GB（给 50GB 目标容量留 5GB 余量）
- 条数阈值：默认 >50 万条（接近官方迁移硬限制，超出会静默丢弃；作为判定阈值可调，也可设更低值提前预警）

询问用户是否需要变更（如 40GB / 48GB、40 万条）；用户未说明或不确定时按默认值执行，用户特别指出的以用户实际说明为准。

## 工作流

### 阶段 0：前置检查（脚本 validate + 人工）

1. 用 `python skills/email/scripts/email_migration.py validate <csv>` 校验源 CSV（脱敏汇总）
2. 用 `probe <csv>` 连接源 IMAP 摸底（逐账号文件夹与邮件数，密码不回显）；邮件总数受腾讯"收取范围"影响，结果偏小说明仍是"最近 30 天"
3. 人工确认：目标 M365 邮箱已创建并分配许可证；腾讯侧 IMAP 可访问且收取范围为"全部"（默认只收 30 天，需提前调整）
4. 人工执行：先检查是否已登录（`Get-ConnectionInformation` 有返回即已连接，已登录则跳过 `Connect-ExchangeOnline`；或用文档方式 `Get-Mailbox -ResultSize 3` 验证），未登录再执行 `Connect-ExchangeOnline`；随后创建/测试 IMAP 迁移终结点（腾讯 `imap.exmail.qq.com:993 SSL`）、迁移期间移除目标邮箱 MRM 保留策略

注意：EXO 连接只在当前 PowerShell 会话内有效，多步操作要在同一个会话中完成（或由人工在自己的会话中执行）。

### 阶段 1：分析与超限识别（人工分析批处理 + 脚本 analyze）

1. 人工创建分析批处理 `New-MigrationBatch -Analyze`，等待完成后导出统计 CSV
2. 用 `analyze <stats.csv>` 筛超限名单（阈值按交互第二步确认结果，默认 >45GB 或 >50 万条），报告写入 output
3. 对超限邮箱，人工用 `Get-MailboxAnalysisRequestStatistics -IncludeAnalysisResult -IncludeFolderDetails -ItemsStartTime ...` 查看时间分布，确定保留策略（如只迁最近 1 年）
4. **人工确认**超限处理路线：有云归档许可走 XML mapping 分发；无许可走 imapsync 兜底（当前 TODO）
5. 确认后删除分析批处理，避免与正式迁移批处理记录重叠

### 阶段 2：小批量验证（脚本 split + 人工）

1. 用 `generate <csv>` 生成 EXO 迁移 CSV，用 `split <csv> --batch-size 15` 拆出验证批次
2. 人工执行小批量正式迁移（10~20 人），核对邮件数、迁移状态、文件夹映射、抽样邮件完整性
3. **人工确认**验证通过后再放量；测试账号应覆盖"目标邮箱非空"与"收件箱已清空但已删除邮件有内容"两类场景

### 阶段 3：分批正式迁移（脚本 split + 人工）

1. 用 `split <csv> --batch-size 50` 拆分全量批次
2. 人工逐批创建 `New-MigrationBatch -CSVData ... -AllowUnknownColumnsInCsv $true`，监控状态与进度
3. 失败用户通过 Exchange 管理中心查看错误，处理后再迁移

### 阶段 4：收尾核对（脚本 verify + 人工）

1. 人工导出 `Get-MailboxFolderStatistics` 统计，用 `verify <folder-stats.csv>` 生成核对报告
2. 核对：已删除邮件覆盖情况、文件夹映射是否错位/重复、空目标邮箱是否有迁移失败
3. 全部验证通过后人工切换 MX 至 M365，确认路由稳定后停止批处理同步并清理

## 资源

- `scripts/email_migration.py`：子命令 validate / generate / split / analyze / verify / probe，运行 `python skills/email/scripts/email_migration.py --help` 查看用法；脚本安全约束见文件头注释
- `references/migration-workflow.md`：Exchange Online 人工命令指南（CSV 格式、分析、批处理、核对、注意事项、故障排查），执行真实环境操作前先读对应阶段
- `docs/`：原始需求文档（背景、痛点、约束），理解场景时阅读

## TODO

- 【暂停·下次继续】Exchange Online 管理员登录卡点：`Connect-ExchangeOnline` 因管理员账号两步验证未走通而暂停。已完成的真实进展：password.csv 校验通过；腾讯 IMAP 摸底完成（2 个账号，邮件数 87/26，报告 `output/email-migration/probe_report_20260812_162708.csv`）；迁移 CSV 已生成（`output/email-migration/migration_20260812_161642.csv`）。下次从阶段 0 第 4 步继续：先 `Get-ConnectionInformation` 判断是否已登录（已登录则跳过登录），未登录则先完成 MFA 验证方法注册再 `Connect-ExchangeOnline`；超限阈值按默认 45GB / 50 万条执行（用户未另行指定）
- imapsync 兜底迁移：超限邮箱按时间筛选（如最近 1 年）或塞满 50GB 的迁移，需要目标邮箱密码（`TargetEmailPassword`）。待用户提供目标密码并确认保留策略后实现
- 联系人、日历、任务迁移：官方 IMAP 迁移不覆盖，需另行方案（如腾讯企业邮通讯录导出导入）
