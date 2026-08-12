## 背景

公司要从腾讯企业邮迁移到微软邮箱。腾讯企业邮单邮箱空间没限制，微软邮箱标准版，单邮箱空间限制50G。

你帮我规划一下迁移方。包括腾讯企业邮和微软邮箱要做什么配置，迁移的时候，依赖的命令行的安装和使用。

## 微软官方迁移方案

使用超级管理员运行 PowerShell 命令窗口

### ExchangeOnline工具准备

```powershell
# 安装 ExchangeOnlineManagement 模块。
Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber

# 修改执行策略为 RemoteSigned 
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

# 手动导入模块
Import-Module ExchangeOnlineManagement -Force

# 当 Connect-ExchangeOnline 命令执行后
# PowerShell 会弹出一个登录窗口。请使用你拥有 Exchange 管理员权限的 Microsoft 365 账号进行登录。
Connect-ExchangeOnline

# 登录成功后。提示：
# 是否登录到此设备上的所有应用和网站
# 点击 先点击否。如果后续出问题，那就点击是 。
# 我们正在向你的公司注册此设备。请稍等。。。。账号已添加到此设备。

# 验证是否登录成功。
# 显示3个邮箱列表
Get-Mailbox -ResultSize 3
```

### 邮箱账号准备

1. 待迁移的邮箱：设置 - 客户端设置 - 收取选项： 如果是默认 收取 `最近30天` ，则改为： 收取 `全部` 的邮件。同时，推荐勾选 `收取“我的文件夹“`。
2. ExchangeOnline支持的CSV迁移文件：标题行字段为 `EmailAddress,UserName,Password`，代表 `迁移目标邮箱地址,源邮箱登录名,源邮箱密码`。示例：`target@xxx.onmicrosoft.com,yourname@tencent.com,xxxxxx`。

### 迁移命令

#### 准备与验证

**命令 1：创建迁移终结点**（如果之前已创建可跳过）

```powershell
# 1. 确保已创建迁移终结点（如果之前已创建可跳过）
New-MigrationEndpoint -IMAP -Name "TencentIMAPEndpoint" -RemoteServer "imap.exmail.qq.com" -Port 993 -Security Ssl
```

**命令 2：测试迁移端点连通性**

```powershell
Test-MigrationServerAvailability -IMAP -RemoteServer "imap.exmail.qq.com" -Port 993 -Security Ssl
```

**命令 3：迁移期间移除目标邮箱 MRM 保留策略**（迁移完成后按需恢复）

```powershell
Set-Mailbox -Identity <目标邮箱> -RetentionPolicy $null
```

#### 分析与筛选

**命令 4：读取 CSV 文件内容**（修改 CSV 内容后需重新执行）

```powershell
# 读取csv文件内容。注意：修改csv内容后，要重新执行读取命令。
# 建议先用少量用户测试，确认没问题后再放全部500人
$csvData = [System.IO.File]::ReadAllBytes("C:\path\to\your\migration.csv")
```

**命令 5：创建用于分析的批处理**

```powershell
# 先创建用于分析的批处理
New-MigrationBatch -Analyze -SourceEndpoint "TencentIMAPEndpoint" -AutoStart -Name "TencentToM365_Analysis" -CsvData $csvData -AllowUnknownColumnsInCsv $true
```

**命令 6：查看分析批处理的状态**

```powershell
# 查看用于分析的批处理的状态
Get-MigrationBatch -Identity "TencentToM365_Analysis"
```

**命令 7：查看每个用户的预估数据量（项目数和大小）**

```powershell
# 查看每个用户的预估数据量（项目数和大小）.注意，这个命令有BUG：会把 BatchId 不等于 TencentToM365_Analysis 的 Identity 的信息也显示在结果中。故同样的Identity可能会多次重复展示。
# EstimatedTotalTransferSize 是格式化字符串（如 "28.45 GB (30,551,458,399 bytes)"），不能直接比大小，需要 .ToBytes() 转换。
Get-MigrationUser -BatchId "TencentToM365_Analysis" | Get-MigrationUserStatistics | Format-Table Identity, TotalItemsInSourceMailboxCount, EstimatedTotalTransferSize
```

**命令 8：按时间窗口查看分析结果（月粒度）**

```powershell
# 统计 2025-08 至今每个文件夹的条目数和大小
$user = "<待分析邮箱>"
Get-MailboxAnalysisRequestStatistics $user -IncludeAnalysisResult -IncludeFolderDetails -ItemsStartTime "2025/08/01"
```

**命令 9：导出超限邮箱名单（大小超 45GB 或数量超 50 万）**

```powershell
Get-MigrationUser -BatchId "TencentToM365_Analysis" |
    Where-Object { $_.EstimatedTotalSize -gt 45GB -or $_.EstimatedTotalCount -gt 500000 } |
    Format-Table Identity, EstimatedTotalCount, EstimatedTotalSize
```

#### 正式迁移

**命令 10：创建迁移任务并执行迁移**

```powershell
# 创建迁移任务-设置迁移任务名称
$batchName = "TencentToM365_Full_" + (Get-Date -Format "yyyyMMdd_HHmm")
# 创建迁移任务-执行迁移
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
```

**命令 11：查看迁移任务状态与进度**

```powershell
# 查看任务状态
Get-MigrationUser -BatchId $batchName
Get-MigrationUser -BatchId $batchName | Get-MigrationUserStatistics |
    Format-Table Identity, Status, PercentComplete, ItemsSynced
```

**命令 12：删除已完成的批处理**（仅批处理未运行或已完成时执行）

```powershell
# 如果批处理迁移任务，未运行或已完成，可以删除。
# 轮询 Get-MigrationBatch 等待 Status 变为 Completed（或 Failed 后处理完错误）再删除。
Remove-MigrationBatch -Identity $batchName -Confirm:$false
```

**命令 13：查看所有迁移任务**

```powershell
# 查看所有迁移任务
Get-MigrationBatch
```

**命令 14：删除所有与 TencentToM365 相关的批处理**

```powershell
# 删除所有与 TencentToM365 相关的批处理
Get-MigrationBatch | Where-Object {$_.Identity -like "TencentToM365*"} | Remove-MigrationBatch -Confirm:$false
```

#### 迁移后核对

**命令 15：核对文件夹映射**

```powershell
Get-MailboxFolderStatistics -Identity <目标邮箱> | Select-Object Name, FolderPath
```

获取帮助：

```powershell
# 1. 查看基本帮助
Get-Help New-MigrationBatch
# 2. 查看详细帮助（含参数说明和示例）
Get-Help New-MigrationBatch -Detailed
# 查看完整帮助（含所有技术细节）
Get-Help New-MigrationBatch -Full
```

**痛点：不知道哪些邮箱超50G**

```powershell
# 待验证

# 获取所有用户的分析结果
$results = Get-MigrationUser -BatchId "TencentToM365_Analysis"

# 筛选出估算大小超过 45GB 的邮箱（留5GB余量）
# EstimatedTotalSize 是字节数，可直接数值比较
Get-MigrationUser -BatchId "TencentToM365_Analysis" |
    Where-Object { $_.EstimatedTotalSize -gt 45GB } |
    Format-Table Identity, EstimatedTotalCount, EstimatedTotalSize

```

- 分析批处理创建后，用 Get-MailboxAnalysisRequestStatistics -IncludeAnalysisResult -IncludeFolderDetails -ItemsStartTime "2025/08/01" 可按时间窗口查看每个文件夹的条目数和大小（月粒度）。
- 还能用 -IncludeMappingResult 生成 XML mapping，把旧邮件自动映射到归档邮箱，官方方案是 "Automated large mailbox migration from IMAP sources"。
- 两个前提需要写进文档：① IMAP 分析要求目标 EXO 邮箱已创建；② mapping 分发依赖主邮箱+云归档（Main/Auxiliary Archive），商业标准版默认没有云归档，需 E3/E5 或 Exchange Online Archiving 附加。所以标准版下


### Exchange管理中心

用管理员身份，登录微软官方的`Exchange管理中心` 查看迁移错误: https://admin.cloud.microsoft/exchange#/migrationbatch

--------------------------------

## 注意事项

1. **官方 IMAP 迁移硬限制**（对腾讯企业邮同样适用）：
   - 单邮箱最多迁移 500,000 项，按"最新到最旧"顺序迁移，超出部分静默丢弃；
   - 单封邮件最大 35 MB；
   - 只迁移收件箱及其他邮件文件夹，**联系人、日历、任务不迁移**，需另行方案（如腾讯企业邮通讯录导出后导入）。
2. **MRM/存档策略**：微软迁移工具会把策略自动删除或移走的邮件标记为"缺失"。M365 新邮箱默认应用默认 MRM 策略，迁移期间建议移除目标邮箱保留策略（命令 3），迁移完成后再按需恢复。
3. **超限判断不能只看大小**：同时筛选大小超 45GB 与数量超 50 万项（命令 9）。
4. **按时间迁移的边界**：官方按时间能力分两层——分析统计（命令 8）与 XML mapping 分发到归档（需云归档许可）。商业标准版默认无归档许可，此时超限邮箱只能靠第三方工具 imapsync 按时间筛选兜底（见"第三方迁移工具"），旧邮件留在腾讯邮箱，需提前明确归属。
5. **文件夹映射**：腾讯企业邮文件夹命名（中文名、自定义文件夹）与 M365 标准文件夹（Inbox、Sent Items 等）映射可能错位，迁移后需核对（命令 15），避免出现重复或异常文件夹。
6. **分析批处理前提**：目标 EXO 邮箱必须已创建。

## 工程化实施方案

### 阶段 0：前置检查

- 确认所有目标 M365 邮箱已创建并分配许可证（分析批处理与正式迁移均要求）。
- 确认腾讯企业邮账号可 IMAP 访问，且收取范围为"全部"。
- 生成 CSV 迁移文件（格式见"邮箱账号准备"）。
- 创建迁移终结点并测试连通性（命令 1、命令 2）。
- 迁移期间移除目标邮箱 MRM 保留策略（命令 3），迁移完成后再恢复。

### 阶段 1：分析与超限名单

- 读取 CSV 并创建分析批处理（命令 4、命令 5），等待完成（命令 6）。
- 查看预估数据量（命令 7），导出超限名单（命令 9）。
- 对超限邮箱先按时间窗口看数据分布（命令 8）：有归档许可则生成 XML mapping 分发到主/归档邮箱；无许可则走第三方工具 imapsync 兜底。
- 导出名单并确认后删除分析批处理（命令 14），避免迁移用户记录与正式迁移批处理重叠。

### 阶段 2：小批量验证（10~20 人）

- 用完整 CSV 的子集创建正式迁移批处理（命令 10）。
- 验证内容：邮件数、迁移状态与进度（命令 11）、文件夹映射（命令 15）、抽样邮件完整性。
- 确认无误后再放量。

### 阶段 3：分批正式迁移

- 建议每批 100 人以内，按批创建独立批处理（命令 10，沿用时间戳命名）。
- 每批用命令 11 监控状态与进度；失败用户通过 Exchange 管理中心查看具体错误，处理完错误后单独重试或并入下一批。

### 阶段 4：收尾

- 批处理处于 Completed/Failed 终态后删除（命令 12~14）。
- 核对文件夹映射（命令 15）与邮件抽样。
- 联系人/日历另行迁移（IMAP 方案不覆盖）。
- 超限邮箱按阶段 1 确定的路线执行兜底迁移。
- 全部验证完成后切换 MX 至 M365，确认路由稳定后停止批处理同步并清理。

---------------

## 第三方迁移工具

```bash
imapsync --host1 imap.exmail.qq.com --user1 your_tencent@company.com --password1 '你的腾讯邮箱密码' \
         --host2 outlook.office365.com --user2 your_microsoft@company.com --password2 '你的微软邮箱密码' \
         --ssl1 --ssl2
```
