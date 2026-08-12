# Exchange Online 人工迁移命令指南

本文档给真实环境的人工执行者使用，按阶段组织。所有命令在 Exchange Online 管理员 PowerShell 中执行。

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

```powershell
# 安装模块并登录
Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
Import-Module ExchangeOnlineManagement -Force

# 先检查是否已登录：有返回即已连接，跳过登录步骤
Get-ConnectionInformation
# 文档验证方式：能显示邮箱列表即已登录
Get-Mailbox -ResultSize 3

# 未连接时再执行登录（登录窗口使用拥有 Exchange 管理员权限的 M365 账号）
Connect-ExchangeOnline
```

注意：

- 若 M365 账号首次登录且组织开启了安全默认值，会强制先注册 MFA 验证方法才能登录，按向导完成即可：
  1. Microsoft Authenticator（推荐）：手机安装 App → 登录界面选"其他方式"→ 扫二维码绑定账号 → 之后登录时在 App 批准或输入验证码
  2. 电话：注册手机号，登录时收短信验证码
  3. 备用邮箱：注册邮箱接收验证码
- EXO 连接只在当前 PowerShell 会话内有效，后续命令必须在同一会话中执行；换窗口/重开进程后需重新检查连接并登录

腾讯侧配置：

- 腾讯企业邮设置 → 客户端设置 → 收取选项：默认"最近 30 天"改为"全部"，推荐勾选"收取我的文件夹"
- 确认源账号可 IMAP 访问（迁移依赖源密码）

源容量摸底（用源 CSV 凭据连接，密码不回显、不落盘）：

```bash
python skills/email/scripts/email_migration.py probe password.csv
```

`probe` 会逐账号列出文件夹与邮件数并写报告到 output/email-migration/。邮件总数明显偏小（如只有几十封）通常说明腾讯"收取范围"仍是"最近 30 天"，需先改设置再迁移。

迁移终结点与 MRM 策略：

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
# 读取 CSV（修改后需重新执行）并创建分析批处理
$csvData = [System.IO.File]::ReadAllBytes("C:\path\to\migration.csv")
New-MigrationBatch -Analyze -SourceEndpoint "TencentIMAPEndpoint" -AutoStart -Name "TencentToM365_Analysis" -CsvData $csvData -AllowUnknownColumnsInCsv $true
Get-MigrationBatch -Identity "TencentToM365_Analysis"

# 查看每个用户的预估数据量（注意：此命令有 BUG，可能重复显示非本批次的 Identity）
Get-MigrationUser -BatchId "TencentToM365_Analysis" | Get-MigrationUserStatistics |
    Format-Table Identity, TotalItemsInSourceMailboxCount, EstimatedTotalTransferSize
```

导出统计到 CSV 后，用脚本筛超限名单（大小超 45GB 或数量超 50 万）：

```powershell
Get-MigrationUser -BatchId "TencentToM365_Analysis" | Get-MigrationUserStatistics |
    Export-Csv -Path "analysis_stats.csv" -NoTypeInformation -Encoding UTF8
```

```bash
python skills/email/scripts/email_migration.py analyze output/email-migration/analysis_stats.csv
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
- 商业标准版默认无归档：只能靠 imapsync 按时间筛选兜底（见 TODO），旧邮件归属需提前与用户确认

确认名单后删除分析批处理，避免记录与正式迁移重叠：

```powershell
Get-MigrationBatch | Where-Object {$_.Identity -like "TencentToM365_Analysis*"} | Remove-MigrationBatch -Confirm:$false
```

## 4. 阶段 2：小批量验证

```powershell
# 用完整 CSV 的子集创建正式迁移批处理
$batchName = "TencentToM365_Test_" + (Get-Date -Format "yyyyMMdd_HHmm")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
Get-MigrationUser -BatchId $batchName | Get-MigrationUserStatistics |
    Format-Table Identity, Status, PercentComplete, ItemsSynced
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
$batchName = "TencentToM365_Full_" + (Get-Date -Format "yyyyMMdd_HHmm")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
Get-MigrationUser -BatchId $batchName
Get-MigrationUser -BatchId $batchName | Get-MigrationUserStatistics |
    Format-Table Identity, Status, PercentComplete, ItemsSynced
```

监控：轮询 `Get-MigrationBatch` 直到 Status 为 Completed 或 Failed。失败用户通过 Exchange 管理中心查看具体错误（https://admin.cloud.microsoft/exchange#/migrationbatch），处理完错误后单独重试或并入下一批。

## 6. 阶段 4：收尾核对

```powershell
# 导出文件夹统计，用脚本生成核对报告
Get-MailboxFolderStatistics -Identity <目标邮箱> | Select-Object Identity, FolderPath, ItemsInFolder |
    Export-Csv -Path "folder_stats.csv" -NoTypeInformation -Encoding UTF8
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
Get-MigrationBatch | Where-Object {$_.Identity -like "TencentToM365*"} | Remove-MigrationBatch -Confirm:$false
```

## 7. 注意事项与硬限制

- 官方 IMAP 迁移硬限制：单邮箱最多迁移 500,000 项，按"最新到最旧"迁移，超出部分静默丢弃；单封邮件最大 35MB
- 只迁移收件箱及其他邮件文件夹；联系人、日历、任务不迁移，需另行方案
- MRM/存档策略：M365 默认 MRM 策略会把邮件自动移走/删除，迁移期间建议移除目标邮箱保留策略
- 超限判断不能只看大小：同时筛大小超 45GB 与数量超 50 万条
- 按时间迁移边界：官方按时间能力分"分析统计"与"XML mapping 分发到归档"两层；商业标准版默认无归档许可，需 imapsync 兜底
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

## 9. TODO：imapsync 兜底

超限邮箱（>50GB 或 >50 万条）无法由官方工具精细控制保留范围，需用 imapsync 按时间筛选迁移，例如只迁最近 1 年：

```bash
imapsync --host1 imap.exmail.qq.com --user1 源登录名 --password1 源密码 \
         --host2 outlook.office365.com --user2 目标邮箱 --password2 目标邮箱密码 \
         --ssl1 --ssl2
```

前置条件（尚未实现）：

- 用户提供目标邮箱密码（源 CSV 增加 `TargetEmailPassword` 列）
- 确认超限邮箱的保留策略（如最近 1 年 / 塞满 50GB）与旧邮件归属
- 计划：为每个超限邮箱生成 imapsync 命令清单（读取源 CSV，密码不回显），人工逐批执行
