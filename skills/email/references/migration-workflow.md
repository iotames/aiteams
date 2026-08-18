# Exchange Online 人工迁移命令指南

本文档给真实环境的人工执行者使用，按阶段组织。所有命令在已登录的 Exchange Online 管理员 PowerShell 中执行。

## 交互闭环约定

- 每阶段命令**结果导出到共享目录** `output/email-migration/`（已被 .gitignore 忽略），供 `email_migration.py` 脚本消费并生成报告。
- 阶段状态写在 `output/email-migration/state/email-migration-state.json`，用 `state` 子命令读写，供切会话/中断后续接。
- 你只需复制粘贴命令；技能负责解析导出的结果并给下一步。
- EXO 连接只在一个 PowerShell 会话内有效：**建议在同一个会话内把"创建批处理→导出统计"一气呵成**；换窗口/重开进程后需先重新登录（`Connect-ExchangeOnline`）再操作。

## 目录

1. CSV 格式与准备
2. 阶段 0：前置检查
3. 阶段 1：分析与超限识别
4. 阶段 2：小批量验证
5. 阶段 3：分批正式迁移
6. 阶段 4：收尾核对
7. 注意事项与硬限制
8. 故障排查
9. TODO：imapsync 兜底

## 0. 脚本用途 | 谁执行（按数据来源划界）

| 能力 | 数据来源 | 执行者 |
|------|----------|--------|
| `validate`/`generate`/`split` CSV | 本地文件 | agent 独立 |
| `probe` 源邮箱摸底（邮件数/占用字节） | 源 IMAP + 源密码 | agent 独立 |
| `analyze` / `verify` | 人导出的 CSV | agent 独立（消费导出） |
| 一切 EXO 命令 | M365 目标侧 | **必须人工**（已登录 PowerShell） |
| `state` | 本地状态文件 | agent 独立 |

**why**：`Connect-ExchangeOnline` 是交互式登录，登录态绑定在打开它的 PowerShell 会话内；pi 的命令行跑在独立的 bash 子进程（Git Bash/MSYS2/WSL），拿不到你的会话 token，也执行不了 M365 命令。凡不碰 EXO 登录态、数据来自「本地文件或源 IMAP 直连」→ agent 可独立跑；要到 M365 目标侧读写 → 一律人工在已登录 PowerShell 执行。

## 1. CSV 格式与准备

源 CSV 由用户按以下格式准备（可用 scripts/email_migration.py validate 校验）。主迁移只需要前三列：

```csv
EmailAddress,UserName,Password
target1@company.onmicrosoft.com,user1@tencent.com,源密码
```

- `EmailAddress`（必填）：迁移目标邮箱地址
- `UserName`（必填）：源邮箱 IMAP 登录名
- `Password`（必填）：源邮箱密码
- 附加列（如 `TargetEmailPassword`=目标邮箱密码）**仅在 imapsync 兜底时需要**：出现超限邮箱后，要求用户按需补充该列再跑 validate。官方迁移会忽略未知列，创建迁移批处理必须带 `-AllowUnknownColumnsInCsv $true`

创建迁移批处理时始终使用：

```powershell
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
```

## 2. 阶段 0：前置检查

> **硬顺序：先登录 EXO，再做所有 PowerShell 操作。** `Connect-ExchangeOnline` 是唯一入口，未登录时任何 EXO 命令都执行不了。登录动作只在每个新 PowerShell 会话开头做一次。

```powershell
# 1) 一次性准备（每个新会话只需做一次，首次才需要）
Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
Import-Module ExchangeOnlineManagement -Force

# 2) 登录（登录窗口使用拥有 Exchange 管理员权限的 M365 账号；成功后回到命令行提示符）
Connect-ExchangeOnline
```

| 对象 | 是否跨会话共享 |
|---|---|
| 登录凭据 / token | ❌ 不共享，换会话/重开需重登 |
| 终结点 / 迁移批处理 / 邮箱对象 / 节流状态 | ✅ 服务端持久化，跨会话天然存在 |

**验证登录成功**（登录后同一会话内，能读出邮箱即证明已连接且权限可用）：

```powershell
Get-Mailbox -ResultSize 3 | Format-Table Name, RecipientTypeDetails
```

**终结点（先查再建，不盲目重复）**——终结点是服务端持久化对象，可能早前会话已建过：

```powershell
# 先查已有终结点，避免重复新建报"已存在"
Get-MigrationEndpoint
# 确认不存在时再新建：
# New-MigrationEndpoint -IMAP -Name "TencentIMAPEndpoint" -RemoteServer "imap.exmail.qq.com" -Port 993 -Security Ssl
```

**连通性测试（注意服务端节流）**：上一次尝试离得太近会被拒绝（"上一次连接尝试发生时间距离现在太近"），稍后再试即可，不是事故。

```powershell
Test-MigrationServerAvailability -IMAP -RemoteServer "imap.exmail.qq.com" -Port 993 -Security Ssl
```

注意：

- 若 M365 账号首次登录且组织开启了安全默认值，会强制先注册 MFA 验证方法才能登录，按向导完成即可：
  1. Microsoft Authenticator（推荐）：手机安装 App → 登录界面选"其他方式"→ 扫二维码绑定账号 → 之后登录时在 App 批准或输入验证码
  2. 电话：注册手机号，登录时收短信验证码
  3. 备用邮箱：注册邮箱接收验证码
- EXO 连接只在当前 PowerShell 会话内有效，后续命令必须在同一会话中执行；换窗口/重开进程后需先重新登录（`Connect-ExchangeOnline`）

腾讯侧配置：

- 腾讯企业邮设置 → 客户端设置 → 收取选项：默认"最近 30 天"改为"全部"，推荐勾选"收取我的文件夹"
- 确认源账号可 IMAP 访问（迁移依赖源密码）

源容量摸底（用源 CSV 凭据连接，密码不回显、不落盘）：

```bash
python skills/email/scripts/email_migration.py probe password.csv
```

`probe` 会逐账号列出文件夹与邮件数并写报告到 output/email-migration/。邮件总数明显偏小（如只有几十封）通常说明腾讯"收取范围"仍是"最近 30 天"，需先改设置再迁移。

### 迁移终结点与 MRM 策略

```bash
# 一次性导出迁移 CSV（含源密码）到共享目录
python skills/email/scripts/email_migration.py generate password.csv
```

（`generate` 默认写出到 `output/email-migration/migration_<时间戳>.csv`，后续 split/批处理都用它。）

```powershell
# 迁移终结点（已创建可跳过）
New-MigrationEndpoint -IMAP -Name "TencentIMAPEndpoint" -RemoteServer "imap.exmail.qq.com" -Port 993 -Security Ssl
Test-MigrationServerAvailability -IMAP -RemoteServer "imap.exmail.qq.com" -Port 993 -Security Ssl
# 迁移期间移除目标邮箱 MRM 保留策略（完成后按需恢复）
Set-Mailbox -Identity <目标邮箱> -RetentionPolicy $null
```

## 3. 阶段 1：分析与超限识别

分析批处理要求目标 EXO 邮箱已创建并分配许可证。

```powershell
# 读取 CSV（修改后需重新执行），创建分析批处理
# 用时间戳命名避免与历史分析批撞名/叠加
$csvData = [System.IO.File]::ReadAllBytes("C:\path\to\migration.csv")
$analysisName = "Analysis_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-MigrationBatch -Analyze -SourceEndpoint "TencentIMAPEndpoint" -AutoStart -Name $analysisName -CsvData $csvData -AllowUnknownColumnsInCsv $true
Get-MigrationBatch -Identity $analysisName

# 查看每个用户的预估数据量
# 注意：Get-MigrationUserStatistics 按 BatchId 过滤有 BUG，会带出历史批记录导致同一邮箱重复显示；
# 用本次批名 + 取最新一条状态为准，或用 -Identity 定向查单邮箱
Get-MigrationUser -BatchId $analysisName | Get-MigrationUserStatistics |
    Format-Table Identity, TotalItemsInSourceMailboxCount, EstimatedTotalTransferSize
```

导出统计到 `output/email-migration/analysis_stats.csv`，随后用脚本筛超限名单（大小超 45GB 或数量超 50 万）：

```powershell
# 导出统计（导出到共享目录，供 analyze 脚本消费），用本次批名
Get-MigrationUser -BatchId $analysisName | Get-MigrationUserStatistics |
    Export-Csv -Path "output/email-migration/analysis_stats.csv" -NoTypeInformation -Encoding UTF8
# 建议：导出后用脚本先看表头确认列名齐全再 analyze；若空文件说明 Get-Mailbox 过滤没匹配到，改用 PrimarySmtpAddress 过滤
```

```bash
python skills/email/scripts/email_migration.py analyze output/email-migration/analysis_stats.csv --show-identities
```

超限判定阈值在迁移开始前已与用户确认：

- 大小阈值默认 >45GB（50GB 目标容量留 5GB 余量），对应 `--size-gb`，可调（如 40GB/48GB）
- 条数阈值默认 >50 万，对应 `--count`，可调（可设更低值提前预警；注意官方迁移硬限制为 50 万项，超出部分从最旧开始静默丢弃）
- 用户未说明或不确定时按默认值执行；用户特别指出的以用户实际说明为准

按时间窗口查看数据分布（月粒度）：

```powershell
Get-MailboxAnalysisRequestStatistics <待分析邮箱> -IncludeAnalysisResult -IncludeFolderDetails -ItemsStartTime "2025/08/01"
```

超限处理路线（需人工确认）：

- 有云归档许可（E3/E5 或 Exchange Online Archiving）：用 `-IncludeMappingResult` 生成 XML mapping，把旧邮件分发到主/归档邮箱
- **按时间筛选迁移**（单邮箱落在主邮箱）→ 用 `-ContentFilter`（见阶段 3b），商业标准版直接可用，无需云归档

确认名单后删除分析批处理，避免记录与正式迁移重叠：

```powershell
# 删除分析批（用本次批名；Removing 后台清理属正常）
Get-MigrationBatch | Where-Object { $_.Identity -eq $analysisName } | Remove-MigrationBatch -Confirm:$false
```

## 4. 阶段 2：小批量验证

```powershell
# 用完整 CSV 的子集创建正式迁移批处理（时间戳命名）
$batchName = "Migrate_Test_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
Get-MigrationUser -BatchId $batchName | Get-MigrationUserStatistics |
    Format-Table Identity, Status, PercentComplete, ItemsSynced
# 注意 BatchId 过滤 BUG：会带出历史批重复记录，取 Sync/Synced 那条为本次结果；
# 关键看 SyncedItemCount/TransferredItemCount 与源估算一致即成功；为 0 多为已迁过去重（正常）
# 需定向查单邮箱时：Get-MigrationUser -Identity <邮箱> | Get-MigrationUserStatistics
```

验证要点：

- 邮件数是否符合预期；迁移状态与进度
- 文件夹映射（腾讯中文/自定义文件夹 vs M365 标准文件夹）是否错位、重复
- 抽样邮件完整性（收件人、附件、时间）
- 测试账号应覆盖两类场景：
  - 目标邮箱非空：验证迁移是追加/合并还是覆盖，迁移前后邮件数对比
  - 收件箱已清空但已删除邮件（Deleted Items）有内容：验证这些邮件是否进入目标邮箱、进入哪个文件夹

## 5. 阶段 3：分批正式迁移

```powershell
# 每批独立批处理，时间戳命名；建议每批 100 人以内
$batchName = "Migrate_Batch_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
Get-MigrationUser -BatchId $batchName
Get-MigrationUser -BatchId $batchName | Get-MigrationUserStatistics |
    Format-Table Identity, Status, PercentComplete, ItemsSynced
```

监控：轮询 `Get-MigrationBatch` 直到 Status 为 Completed 或 Failed。失败用户通过 Exchange 管理中心查看具体错误（https://admin.cloud.microsoft/exchange#/migrationbatch），处理完错误后单独重试或并入下一批。

### 阶段 3b：按时间范围只迁最近 N 年（`-ContentFilter`）

对于超限/需裁剪的邮箱，可用官方 `New-MigrationBatch` 的 `-ContentFilter` 参数**按 Received 时间筛选**，只迁移匹配时段的邮件。此能力商业标准版直接可用，**不依赖云归档许可**。

```powershell
# 只迁移最近 1 年（动态计算截止日期）
$yearAgo = (Get-Date).AddYears(-1).ToString("yyyy/M/d")
$filter = "Received -ge '" + $yearAgo + "'"

$batchName = "Migrate_1Y_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart \
    -AllowUnknownColumnsInCsv $true -ContentFilter $filter -ContentFilterLanguage "zh-CN"
```

**`-ContentFilter` 语法（OPATH 过滤）：**
- 只支持 `Received`（收件时间），**不支持 `Sent`（发件时间）**。
- 操作符：`-gt`/`-ge`/`-lt`/`-le`/`-and`/`-or`。
- 时间值单引号包住、格式 `yyyy/M/d`（如 `'2023/1/1'`）。
- 官方示例：`"Received -gt '8/23/2020'"`、`"Received -le '2019/01/01'"`、`"Received -gt '8/23/2015' -and Received -lt '8/23/2020'"`。
- 此参数与 `-Analyze` 相互独立：做按时间迁移时**不要加 `-Analyze`**。

## 6. 阶段 4：收尾核对

```powershell
# 导出文件夹统计到共享目录，用脚本生成核对报告
# 注意：verify 脚本只识别 EmailAddress/FolderPath/ItemsInFolder 三列；
# Get-Mailbox -Identity 返回 GUID、Get-MailboxFolderStatistics 不带邮箱地址，
# 故用外层对象的 PrimarySmtpAddress 作 EmailAddress 列来区分邮箱。
Get-Mailbox -ResultSize unlimited |
    Where-Object { $_.PrimarySmtpAddress -like "*@sendike1.onmicrosoft.com" } |  # 按需过滤目标邮箱
    ForEach-Object {
        $addr = $_.PrimarySmtpAddress
        Get-MailboxFolderStatistics -Identity $_.Identity |
            Select-Object @{N="EmailAddress";E={$addr}}, FolderPath, ItemsInFolder
    } |
    Export-Csv -Path "output/email-migration/folder_stats.csv" -NoTypeInformation -Encoding UTF8
```

```bash
python skills/email/scripts/email_migration.py verify output/email-migration/folder_stats.csv
```

人工核对：

- 已删除邮件覆盖情况（报告中的 DeletedItemsNotCleared）
- 文件夹映射是否出现重复或异常（如腾讯自定义文件夹变成独立文件夹）
- 空目标邮箱是否对应迁移失败用户
- 完成与清理：删除终态批处理；全部验证通过后切换 MX 至 M365，确认路由稳定后停止批处理同步并清理

```powershell
# 删除所有测试/历史迁移批（终态批安全；Removing 后台清理中，稍后消失属正常）
Get-MigrationBatch | Where-Object {
        $_.Status -in @("Completed","CompletedWithErrors","Failed","Stopped","Removing")
    } | Remove-MigrationBatch -Confirm:$false
# 删除后状态先变 Removing 再过几分钟消失，不是删不干净，勿重复删/报错
# 注意：终结点 TencentIMAPEndpoint 不在批处理里，勿用此命令；保留供后续迁移复用
```

## 7. 注意事项与硬限制

- 官方 IMAP 迁移硬限制：单邮箱最多迁移 500,000 项，按"最新到最旧"迁移，超出部分静默丢弃；单封邮件最大 35MB
- 只迁移收件箱及其他邮件文件夹；联系人、日历、任务不迁移，需另行方案
- MRM/存档策略：M365 默认 MRM 策略会把邮件自动移走/删除，迁移期间建议移除目标邮箱保留策略
- 超限判断不能只看大小：同时筛大小超 45GB 与数量超 50 万条
- 按时间迁移边界：官方 `-ContentFilter` 支持按 Received 时间筛选（只迁匹配邮件），商业标准版可直接用；XML mapping 分发到归档才需云归档许可
- 分析批处理前提：目标 EXO 邮箱已创建

## 8. 故障排查

```powershell
# 查看帮助
Get-Help New-MigrationBatch -Detailed
# 查看所有迁移任务
Get-MigrationBatch
# 删除指定批处理（仅未运行或已完成时）
Remove-MigrationBatch -Identity $batchName -Confirm:$false
```

- 登录提示"是否登录到此设备上的所有应用和网站"：先选"否"，出问题再选"是"
- 迁移用户重复/统计异常：`Get-MigrationUserStatistics` 存在 BatchId 过滤 BUG，以 Identity 为准去重

## 9. 按时间迁移：官方 `-ContentFilter`（优先）

微软官方 `New-MigrationBatch` 的 `-ContentFilter` 参数支持按 Received 时间筛选（语法见阶段 3b），**这是按时间迁移的正解，商业标准版可直接用，优先于 imapsync**。示例只迁最近 1 年：

```powershell
$yearAgo = (Get-Date).AddYears(-1).ToString("yyyy/M/d")
$filter = "Received -ge '" + $yearAgo + "'"
New-MigrationBatch -Name <batch> -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart     -AllowUnknownColumnsInCsv $true -ContentFilter $filter -ContentFilterLanguage "zh-CN"
```

## 10. imapsync（仅当官方 `-ContentFilter` 无法覆盖时才用）

imapsync 仅用于官方 `-ContentFilter` 覆盖不到的细粒度筛选（按发件人/主题/Sent 时间——注意官方只支持 Received）或逐封对比场景：

```bash
imapsync --host1 imap.exmail.qq.com --user1 源登录名 --password1 源密码          --host2 outlook.office365.com --user2 目标邮箱 --password2 目标邮箱密码          --ssl1 --ssl2 --search "SINCE 1-Jan-2022"
```

前置条件（尚未实现）：

- 用户提供目标邮箱密码（源 CSV 增加 `TargetEmailPassword` 列）
- 确认超限邮箱的保留策略（如最近 1 年 / 塞满 50GB）与旧邮件归属
- 计划：为每个超限邮箱生成 imapsync 命令清单（读取源 CSV，密码不回显），人工逐批执行
