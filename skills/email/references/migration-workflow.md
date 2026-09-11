# Exchange Online 人工迁移命令指南

本文档给真实环境的人工执行者使用，按阶段组织。所有命令在已登录的 Exchange Online 管理员 PowerShell 中执行。

## 交互闭环约定

- 每阶段命令**结果导出到共享目录** `output/email-migration/`（已被 .gitignore 忽略），供 `email_migration.py` 脚本消费并生成报告。
- 阶段状态写在 `output/email-migration/state/email-migration-state.json`，用 `state` 子命令读写，供切会话/中断后续接。
- 你只需复制粘贴命令；技能负责解析导出的结果并给下一步。
- EXO 连接只在一个 PowerShell 会话内有效：**建议在同一个会话内把"创建批处理→导出统计"一气呵成**；换窗口/重开进程后需先重新登录（`Connect-ExchangeOnline`）再操作。

## 目录

0. 脚本用途 | 谁执行
0.5 EXO 命令执行模式与规范
1. CSV 格式与准备
2. 阶段 0：前置检查
3. 阶段 1：分析与超限识别
4. 阶段 2：小批量验证
5. 阶段 3：分批正式迁移
6. 阶段 4：收尾核对
7. 注意事项与硬限制
8. 故障排查
9. 按时间迁移 ContentFilter（优先）
10. imapsync 兜底

## 0. 脚本用途 | 谁执行（按数据来源划界）

| 能力 | 数据来源 | 执行者 |
|------|----------|--------|
| `validate`/`generate`/`split` CSV | 本地文件 | agent 独立 |
| `probe` 源邮箱摸底（邮件数/占用字节） | 源 IMAP + 源密码 | agent 独立 |
| `check` 源账号登录可用性验证（登录即登出，不统计邮件；适合改密后批量验凭据） | 源 IMAP + 源密码 | agent 独立 |
| `backfill` 汇总表统计列回填源清单（按 UserName=email 匹配） | 本地文件 | agent 独立 |
| `analyze` / `verify` | 人导出的 CSV | agent 独立（消费导出） |
| 一切 EXO 命令 | M365 目标侧 | **agent（PTY 持久会话，见 0.5）或人工**（已登录 PowerShell），两者等价 |
| `state` | 本地状态文件 | agent 独立 |

**why**：`Connect-ExchangeOnline` 是交互式登录，登录态绑定在打开它的 PowerShell 会话内；pi 的命令行跑在独立的 bash 子进程（Git Bash/MSYS2/WSL），拿不到你的会话 token，也执行不了 M365 命令。凡不碰 EXO 登录态、数据来自「本地文件或源 IMAP 直连」→ agent 可独立跑；要到 M365 目标侧读写 → 一律人工在已登录 PowerShell 执行。

## 0.5 EXO 命令执行模式与规范

本技能支持两种 EXO 执行模式，按环境选择其一。本地 CSV 与源 IMAP 操作（`validate`/`generate`/`split`/`backfill`/`probe`/`check`/`analyze`/`verify`/`state`）不受此约束，始终由 agent 独立执行。

### 模式 A：agent 代理执行（默认）

单一持久 PowerShell 会话，规则如下：

1. **会话建立**：以 PTY 模式启动 `powershell -NoExit -Command "Import-Module ExchangeOnlineManagement -Force"`，随后在会话内交互式执行 `Connect-ExchangeOnline`，由用户在浏览器完成一次授权。禁止将连接参数拼入启动命令串（`-ShowBanner:$false` 经 `-Command` 传入会因类型转换失败）。
2. **会话独占**：全部 EXO 命令必须在同一会话内执行。普通 exec 新进程无登录态，命令必然失败。
3. **连接验证**：`Get-ConnectionInformation` 返回 Connected 方可操作；以 `Get-Mailbox -ResultSize 3` 验证权限。
4. **轮询等待**：批次状态轮询在会话内以 `Start-Sleep -Seconds N; Get-MigrationBatch` 完成。

### 模式 B：人工执行（回退）

PTY 不可用或用户要求人工确认时，agent 产出精排命令，用户在已登录 PowerShell 执行，结果经共享输出文件回流。

### 批次生命周期规范

| 操作 | 规则 |
|------|------|
| 停止 | `Stop-MigrationBatch` 后 Stopping 状态持续 1~3 分钟；未到 Stopped 禁止删除 |
| 删除 | 逐批 `Remove-MigrationBatch -Identity <批名> -Confirm:$false`；管道方式对 Stopped 批静默失效，禁止使用 |
| 清理 | Removing 状态持续约 3 分钟；`Get-MigrationBatch` 返回空之前禁止创建新批 |
| 冲突 | 同一邮箱禁止同时存在于两个活跃批次（创建会被拒绝） |
| 重复 | 删除重建不产生邮件重复；同批次内 Stop→Start / Sync Now 为增量同步，不重复迁移 |

### 创建批次规范

1. `-CSVData` 仅接受 CSV 文件字节：必须使用 `$csvData = [System.IO.File]::ReadAllBytes(<CSV路径>)`。禁止传入 `Import-Csv` 对象数组——类型转换失败，且报错信息会回显含密码的文件内容。
2. 命令模板：

```powershell
$csvData = [System.IO.File]::ReadAllBytes("D:\path\migration_xxx.csv")
$batchName = "Migrate_Full_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart -AllowUnknownColumnsInCsv $true
```

3. 创建结果以复查为准（返回对象字段渲染不可靠）：`Get-MigrationBatch` 显示 `Status=Syncing`，且 `Get-MigrationUser -BatchId <批名> | Measure-Object` 计数等于 CSV 行数，方为就绪。

### 目标邮箱统计导出规范

1. `TotalItemSize` 以字符串导出（`"$($s.TotalItemSize)"`），本地正则 `\(([\d,]+) bytes\)` 提取字节数；`.Value.Bytes` 在 EXO 3.x 取不到值。
2. 邮箱标识使用外层 `PrimarySmtpAddress`；排除系统邮箱（`-notlike "*Discovery*"`）。

### 单封邮件大小限制

1. 实际拦截点为目标邮箱 `MaxReceiveSize`（默认 36MB）。每次重建批次前，对所有目标邮箱放大：

```powershell
Get-Mailbox -ResultSize unlimited |
    Where-Object { $_.PrimarySmtpAddress -like "*@<目标域名>.onmicrosoft.com" -and $_.PrimarySmtpAddress -notlike "*Discovery*" } |
    Set-Mailbox -MaxReceiveSize 150MB -MaxSendSize 150MB
```

2. 该操作幂等，重复执行无害。执行后抽样验证应显示 `150 MB (157,286,400 bytes)`。
3. 官方文档"单封 35MB 上限"说法已过时，勿引用为硬限制。超限邮件被跳过并记录于批次错误报告，收尾核对时按报告处理。
4. 腾讯企业邮单封上限 50MB，存量邮件实测存在超过 150MB 者，迁移前放大目标限制为必做项。

### 迁移进度查询标准命令（用户问"进度如何"时使用）

进度 = 目标侧已落库 vs 源端 probe 基线，两条命令：

```powershell
# 1) 批次内单用户引擎统计：已同步条目 / 跳过条目 / 引擎预估总量 / 最后同步时间
Get-MigrationUserStatistics -Identity <目标邮箱> |
    Format-List Status, SyncedItemCount, SkippedItemCount, EstimatedTotalTransferSize, LastSuccessfulSyncTime

# 2) 目标邮箱实际落库（权威数字）：邮件数 + 占用
$s = Get-MailboxStatistics -Identity <目标邮箱>
"$($s.ItemCount) / $($s.TotalItemSize)"
```

- 进度百分比 = 目标 `ItemCount` ÷ 源端 probe 基线总数（按大小同理）。
- `EstimatedTotalTransferSize` 是引擎"已发现项"的动态估计，会随枚举推进增长，**不是**源端总量；总量基准只用 probe 基线。
- `SkippedItemCount > 0` 时导出批次错误报告核对（大邮件超限等）。
- EAC/批次显示的"数据一致性分数"（如 Perfect）是**引擎内部自洽性指标**（已同步部分与 IMAP 所见一致），**不是完整度证明**——IMAP 视图被截断时它照样显示 Perfect。完整度唯一判据：目标侧落库 vs 源端 probe 基线（webmail 交叉验证过的）。
- 引擎 `SyncedItemCount` 与目标 `ItemCount` 允许小幅偏差（时间差），大幅偏差（>5%）按核对口径排查。

### 迁移数据汇总报告规范（Excel，全流程单一份）

**定位**：进行中即为工作进度汇报，完成后同一结构即验收结果；不另设"验收报告"。脚本：`scripts/gen_migration_report.py`（参数 `--user-stats / --target-stats / --baseline / --out / --batch / --note`）。

数据采集（EXO 会话内两条标准导出，见"目标端统计标准方法"与进度查询命令）：

```powershell
# 1) 逐用户引擎统计 -> user_stats.csv
Get-MigrationUser -BatchId <批名> | ForEach-Object {
    $st = Get-MigrationUserStatistics -Identity $_.Identity
    [PSCustomObject]@{ EmailAddress = $_.Identity; Status = $_.Status
        SyncedItemCount = $st.SyncedItemCount; SkippedItemCount = $st.SkippedItemCount
        EstimatedTotalTransferSize = "$($st.EstimatedTotalTransferSize)"
        LastSuccessfulSyncTime = $st.LastSuccessfulSyncTime } } |
    Export-Csv <产物目录>\user_stats.csv -NoTypeInformation -Encoding UTF8

# 2) 目标邮箱实际落库 -> target_stats.csv
```

Sheet 结构（两个固定 + 两个完成追加）：

**Sheet2 迁移概要**（管理视角，只写管理层关心的数字）：账号总数、已完成、同步中、失败/停止、原邮箱邮件总数、原邮箱空间合计、目标邮箱邮件总数、目标邮箱空间合计、完成度（按邮件总数计）、完成度（按空间占用计）、跳过邮件合计、最近同步时间、更新时间。不放批次名等纯技术标识于正文之外。

**Sheet2 迁移数据汇总**（默认打开即显示的首页，每账号一行），列序固定：
用户名 → 原邮箱空间占用 → 目标邮箱空间占用 → 原邮箱邮件总数 → 目标邮箱邮件总数 → 完成度（按邮件总数计）→ 最近同步时间 → 本批次已同步 → 跳过邮件数 → 迁移状态 → 说明（最右列）。无源列即无法对账，禁止省略原邮箱两列；不设按空间计的完成度列。
- 状态文案：已完成账号显示"已完成，增量同步中"（Synced 批次在 Complete 收尾前持续每 24h 增量，如实呈现）；同步中显示"同步中"。
- 着色：完成度 <100% 的单元格标红色；跳过邮件数 >0 的单元格标红色。
- **说明列**（自动生成）：完成度 >100% → "同步期间有新增邮件，故完成度超过100%"；跳过 >0 → "存在跳过邮件，待错误报告核对"；两者同时命中优先显示前者。
- 打开时默认激活本 sheet。

**生成前置（必做）**：生成报告前必须先询问用户"是否重新摸底源邮箱（邮件总数/空间占用），更新基线文件"——尤其验收环节；用户确认后先跑 probe 更新基线再生成报告，未确认可用现有基线出进度版。

**完成后追加**：
- Sheet3 文件夹对账：邮箱、文件夹名（UTF-7 解码）、匹配类型（直接/系统映射）、源邮件数、目标邮件数、差值、状态；匹配失败标"目标缺失/源缺失"，禁止静默丢行。
- Sheet4 跳过明细：数据源为管理员邮箱错误报告邮件附件 CSV（PowerShell 无逐项接口）；字段：邮箱、用户名、主题、接收时间、所在文件夹、失败原因；无跳过保留表头+"无跳过项"。

规范：
1. `SkippedItemCount > 0` 的账号在概要备注点名，指向 Sheet4。
2. 基线校准状态必须在备注写明（哪些账号为新基线、哪些为收取范围变更前旧基线待重校）。
3. 引擎预估传输量不进报告（对管理无意义）；总量与进度一律以源基线为准。
4. **输入 CSV 必须当次实时导出**（每次生成报告前都重新执行两条标准导出命令），禁止复用历史导出文件——过期数据会让"最近同步时间/完成度"全部失真且无从察觉。概要中的"更新时间"即数据时效，与报告生成时间一致。
5. 密码与凭据字段禁止进入任何输入输出。
6. 状态用中文业务词，禁用引擎术语（Synced/Syncing 等）直接呈现。
7. **最近同步时间**：数据源为 `Get-MigrationUserStatistics` 的 **`LastSuccessfulSyncTime`**（勿用 `LastSyncedDateTime`——该字段长期为空，实测不可用）。注意两点：① 该值为 UTC，展示前必须转本地时区（EXO 导出的 DateTime 字符串无时区标记，按 UTC 处理）；② 个别账号可能仍为空，显示"首轮同步进行中"，禁止留空。
8. **列宽规范**：所有列宽 ≥ max(表头显示宽度, 内容显示宽度) + 4（CJK 按 2 倍计）；生成脚本内置 `set_widths` 自动计算，禁止手工写死小于表头的列宽。
9. EXO 返回的时间为 UTC（如 `StartDateTime`），展示前必须转本地时区。

### 源端统计标准方法（基线）

1. 统计一律用 `probe` 脚本产出（逐文件夹 `SELECT readonly` + EXISTS 计数、SIZE 累加），结果落盘 CSV，禁止手写临时脚本另搞一套口径。
2. **收取范围变更后必须重跑 probe 并与 webmail 对照验证生效**，两轮数字一致才算基线；"设置已保存"不等于"已生效"（实测存在生效延迟，期间 IMAP 只见部分邮件且无任何报错）。
3. 基线三要素：邮件总数（probe 汇总）、文件夹数（probe 文件夹列表）、占用空间（probe SIZE 合计，与 webmail"已使用容量"交叉核对）。

### 目标端统计标准方法

1. 邮箱级（邮件总数 + 占用）：

```powershell
Get-Mailbox -ResultSize unlimited |
    Where-Object { $_.PrimarySmtpAddress -like "*@<目标域名>.onmicrosoft.com" -and $_.PrimarySmtpAddress -notlike "*Discovery*" } |
    ForEach-Object {
        $addr = $_.PrimarySmtpAddress
        $s = Get-MailboxStatistics -Identity $_.Identity
        [PSCustomObject]@{ EmailAddress = $addr; ItemCount = $s.ItemCount; TotalItemSize = "$($s.TotalItemSize)" }
    } |
    Export-Csv -Path "<产物目录>\target_stats.csv" -NoTypeInformation -Encoding UTF8
```

2. 文件夹级（逐文件夹邮件数，与源端 probe 逐文件夹对账）：

```powershell
Get-MailboxFolderStatistics -Identity <目标邮箱> |
    Select-Object @{N="EmailAddress";E={<目标邮箱>}}, FolderPath, ItemsInFolder |
    Export-Csv -Path "<产物目录>\folder_stats.csv" -NoTypeInformation -Encoding UTF8
```

3. 本地解析 `TotalItemSize` 字符串提取字节数后，与源端基线做"总数 + 文件夹级"双层对比。

### 源/目标核对口径

1. probe 邮件数合计与目标 `ItemCount` 差值 ±2% 内视为一致（探测与同步存在时间差）。
2. 源端 IMAP 逐文件夹计数必须用 `SELECT(<文件夹>, readonly=True)` 后读 EXISTS；腾讯对含空格/特殊字符的文件夹名（如 `Sent Messages`）执行 STATUS 会报 BAD，且 imaplib 不自动加引号——文件夹名必须手动包双引号 `"'%s'" % name` 后再 SELECT。漏掉这类文件夹会造成数千封级别的统计缺口。
3. 核对时源端大小基线以 webmail 后台"已使用容量"为准（IMAP 无可靠的总量 SIZE 接口）。
2. 腾讯"收取范围"非"全部"时，IMAP 仅暴露近期邮件：后台显示容量远大于 IMAP 求和，且旧邮件静默不迁。迁移前必须确认为"全部"。
3. **probe 基线必须与 webmail 抽样交叉验证**（至少抽 1 个账号）：IMAP 求和 < webmail 实际数的 50% 即收取范围受限，禁止以该基线建批或核对。
4. 收取范围受限时已建批次的补救：改为"全部"后，批次每 24 小时自动增量同步会补齐新可见邮件；确认全部补齐后再 Complete。改设置后先重新 probe 校准基线。

### agent 侧脚本执行规范

1. 禁止在 PowerShell 内联多行 Python（引号转义不可靠）；必须先写 .py 文件再执行。
2. PTY 会话内 EXO 报错可能回显敏感字段；含密码文件的操作须保证参数合法，避免进入报错分支。

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

`probe` 会逐账号列出文件夹与邮件数并写报告到 output/email-migration/。报告为 probe_report_*.csv，共 5 列：`SourceEmail, FolderName, MailCount, MailSizeBytes, Status`（MailSizeBytes 为各文件夹占用字节；Status 为 OK / SELECT 失败 / SELECT 异常 / 失败:异常名:服务端返回信息，账号级连接失败时 FolderName 为空）。邮件总数明显偏小（如只有几十封）通常说明腾讯"收取范围"仍是"最近 30 天"，需先改设置再迁移。

probe 同时生成逐账号汇总表 `email_check_success_<时间戳>.csv`（与探测报告同时间戳配对）：

- 列：`email, total_count, total_size, size_text(MB)`；登录失败的账号三项留空，失败原因见 probe_report
- probe 只需源账号（UserName/Password），不校验目标邮箱列；加 `--manifest password.csv` 时汇总表额外带 `EmailAddress`（目标邮箱）列
- 密码列永不进入任何产物；日志同步落盘 `output/email-migration/logs/probe_*.log`，运行中可 tail 观测实时进度

把汇总表统计列回填源清单（如给 password.csv 补 total_count/total_size/size_text(MB)，按 UserName=email 匹配——去首尾空格、忽略大小写；匹配不到或探测失败的行统计列留空，幂等可重跑）：

```bash
python skills/email/scripts/email_migration.py backfill output/email-migration/email_check_success_<时间戳>.csv password.csv
```

### 账号可用性验证（check，不统计邮件）

改密码后或迁移前想快速确认"账号密码能不能登录"，不需要 probe 的完整摸底时用 `check`：登录成功即登出，不列文件夹、不统计邮件，速度远快于 probe。支持一次传多个 CSV，exit code：0=全部通过，2=有失败账号，1=个别 CSV 校验失败被跳过（其余文件照常验证，报告中不含被跳过文件的账号）；跳过与失败并存时 exit 1 优先——先修文件，再全量重测。

```bash
python skills/email/scripts/email_migration.py check password-1.csv password-2.csv password-3.csv password-4.csv
```

产物为 `check_report_<时间戳>.csv`（列：`SourceFile, EmailAddress, UserName, Status, Detail`；密码不进任何产物）。日志同步落盘 `output/email-migration/logs/check_*.log`，运行中可 tail 观测实时进度。**注意：check 只出报告，不会移动或归类任何账号**——失败账号放进哪个名单、批次如何调整，一律由用户决定。

判定细则（依据 2026-09 实测）：

- **判定流程为 LOGIN → SELECT INBOX（只读）→ LOGOUT**，以 SELECT INBOX 能否打开为准——这是迁移搬运邮件的必要条件
- **LOGIN 后任何阶段断连（socket EOF）＝ IMAP/SMTP 服务未开启**：腾讯对未开启账号 LOGIN/NOOP/SELECT 都会应答，会话收尾时才掐线；脚本判为"会话被拒"并提示开启服务，开启后重测 LOGOUT 正常即通过
- **LOGIN 直接被拒**（腾讯合并报错 "Login fail. Account is abnormal..."）：账号异常/IMAP 未开启/密码错误（安全登录需客户端专用密码）/频率限制，脚本打印排查清单
- 网络类错误（timeout/refused）单独提示查网络

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
# 建议：导出后用脚本先看表头确认列名齐全再 analyze；若空文件说明 Get-MigrationUser -BatchId 过滤没匹配到，改用 PrimarySmtpAddress 过滤
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

**增量同步机制（大邮箱必读，10GB+ 首轮慢属正常）**：

- 首轮全量同步完成后，服务端**每 24 小时自动做一次增量同步**，只搬源端新增/有变化的邮件，不会整箱重传；该循环持续到对批执行 Complete（收尾）或删除批次为止。
- 大邮箱首轮同步数小时属正常，**耐心等、勿删批重建**——删批重跑同一账号会从头再来全量，且可能产生重复项。
- 增量按条目对比，**不是按时间戳过滤**；`-ContentFilter` 只作用于首轮全量范围。
- **删除不同步**：源端删除/标记改动不反映到目标，目标只增不减。
- 收尾顺序：全量 Synced → 观察 1-2 次增量 → 切 MX → 最后一次增量兜底 → `Complete-MigrationBatch` 收尾（见阶段 4）。

### 阶段 3b：按时间范围只迁最近 N 年（`-ContentFilter`）

对于超限/需裁剪的邮箱，可用官方 `New-MigrationBatch` 的 `-ContentFilter` 参数**按 Received 时间筛选**，只迁移匹配时段的邮件。此能力商业标准版直接可用，**不依赖云归档许可**。

```powershell
# 只迁移最近 1 年（动态计算截止日期）
$yearAgo = (Get-Date).AddYears(-1).ToString("yyyy/M/d")
$filter = "Received -ge '" + $yearAgo + "'"

$batchName = "Migrate_1Y_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-MigrationBatch -Name $batchName -SourceEndpoint "TencentIMAPEndpoint" -CSVData $csvData -AutoStart \
    -AllowUnknownColumnsInCsv $true -ContentFilter $filter
```
> **说明**：`New-MigrationBatch` 官方没有 `-ContentFilterLanguage` 参数（该参数属传统 Set-ContentFilterConfig 类）。若 `Get-Help New-MigrationBatch` 返回的属性中包含 ContentFilterLanguage 则可保留，否则按本文件删除该参数（无需它也能用 -ContentFilter）。


**`-ContentFilter` 语法（OPATH 过滤）：**
- 只支持 `Received`（收件时间），**不支持 `Sent`（发件时间）**。
- 操作符：`-gt`/`-ge`/`-lt`/`-le`/`-and`/`-or`。
- 时间值单引号包住、格式 `yyyy/M/d`（如 `'2023/1/1'`）。
- 官方示例：`"Received -gt '8/23/2020'"`、`"Received -le '2019/01/01'"`、`"Received -gt '8/23/2015' -and Received -lt '8/23/2020'"`。
- 此参数与 `-Analyze` 相互独立：做按时间迁移时**不要加 `-Analyze`**。

## 6. 阶段 4：收尾核对

```powershell
# 确认各批全量同步完成（Status: Completed/Synced）且 MX 已切换、观察过 1-2 次增量后，
# 逐批执行收尾（Complete-MigrationBatch 会停止后续增量同步，务必最后一步再做）
Get-MigrationBatch | Format-Table Identity, Status, LastSyncedDateTime
Complete-MigrationBatch -Identity <批名> -Confirm:$false
```

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
# 注意：实测 Stopped 批用管道方式删除可能静默失效（不报错也不删），优先用网页后台手动删
Get-MigrationBatch | Where-Object {
        $_.Status -in @("Completed","CompletedWithErrors","Failed","Stopped","Removing")
    } | ForEach-Object {
        Write-Host "正在删除: $($_.Identity)"
        Remove-MigrationBatch -Identity $_.Identity -Confirm:$false
    }
# 删除后状态先变 Removing 再过几分钟消失，不是删不干净，勿重复删/报错
# 管道删除无效时（命令执行但批次仍在），改用网页后台手动删除：
#   https://admin.cloud.microsoft/exchange#/migrationbatch → 选中批次 → 删除
# 注意：终结点 TencentIMAPEndpoint 不在批处理里，勿用此命令；保留供后续迁移复用
```

## 7. 注意事项与硬限制

- 官方 IMAP 迁移硬限制：单邮箱最多迁移 500,000 项，按"最新到最旧"迁移，超出部分静默丢弃；单封大小实际受目标邮箱 MaxReceiveSize 约束（默认 36MB，迁移前放大到 150MB，见 0.5 节"单封邮件大小限制"）；迁移后核对批次错误报告确认有无超限被跳过的邮件
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

## 9. 按时间迁移：官方 `-ContentFilter`（优先）——完整命令与语法见阶段 3b。**结论：官方 `-ContentFilter` 支持按 Received 时间筛选，商业标准版直接可用，优先于 imapsync。**

## 10. imapsync（仅当官方 `-ContentFilter` 无法覆盖时才用）

imapsync 仅用于官方 `-ContentFilter` 覆盖不到的细粒度筛选（按发件人/主题/Sent 时间——注意官方只支持 Received）或逐封对比场景：

```bash
imapsync --host1 imap.exmail.qq.com --user1 源登录名 --password1 源密码          --host2 outlook.office365.com --user2 目标邮箱 --password2 目标邮箱密码          --ssl1 --ssl2 --search "SINCE 1-Jan-2022"
```

前置条件（尚未实现）：

- 用户提供目标邮箱密码（源 CSV 增加 `TargetEmailPassword` 列）
- 确认超限邮箱的保留策略（如最近 1 年 / 塞满 50GB）与旧邮件归属
- 计划：为每个超限邮箱生成 imapsync 命令清单（读取源 CSV，密码不回显），人工逐批执行
