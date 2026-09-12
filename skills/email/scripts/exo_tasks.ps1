# exo_tasks.ps1 — EXO 侧固化任务（模式 A 持久会话内 dot-source 使用）
# 用法（在已登录的 EXO PowerShell 会话内）：
#   . .\skills\email\scripts\exo_tasks.ps1
#   Assert-ExoSession
#   Export-UserStats   -BatchId <批名>
#   Export-TargetStats -BatchId <批名>
#   Export-FolderStats -BatchId <批名>
# 硬性约束：本脚本只读+导出；不连接、不断开会话、不删除任何对象。

function Get-EmailMigrationOutDir {
    param([string]$OutDir)
    if ($OutDir) { return $OutDir }
    $root = if ($env:EMAIL_MIGRATION_OUTPUT) { $env:EMAIL_MIGRATION_OUTPUT } else { 'output' }
    $sub  = if ($env:EMAIL_MIGRATION_SUBDIR) { $env:EMAIL_MIGRATION_SUBDIR } else { 'email-migration' }
    return (Join-Path $root $sub)
}

function Assert-ExoSession {
    <#  步骤 1：确认 EXO 是否已登录，保证后续可持续操作。
        只检查、不连接、不断开；未登录时给出下一步动作。 #>
    if (-not (Get-Command Get-ConnectionInformation -ErrorAction SilentlyContinue)) {
        Write-Host '[FAIL] 未加载 ExchangeOnlineManagement 模块。请在本会话执行： Import-Module ExchangeOnlineManagement -Force' -ForegroundColor Red
        return $false
    }
    $conn = Get-ConnectionInformation -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq 'Connected' }
    if (-not $conn) {
        Write-Host '[FAIL] EXO 未登录（或登录态已失效）。请在本会话执行： Connect-ExchangeOnline' -ForegroundColor Red
        Write-Host '       注意：会话由用户掌握，脚本不会自动连接，也不会断开已建立的会话。'
        return $false
    }
    foreach ($c in $conn) {
        Write-Host ("[OK] EXO 已连接：{0}（{1}）" -f $c.UserPrincipalName, $c.ConnectionUri) -ForegroundColor Green
    }
    return $true
}

function Assert-ExoModuleAndSession {
    if (-not (Assert-ExoSession)) { throw 'EXO 会话不可用，已中止（未执行任何写操作）。' }
}

function Get-BatchMailboxList {
    param([Parameter(Mandatory)][string]$BatchId)
    $users = Get-MigrationUser -BatchId $BatchId
    if (-not $users) { throw "批次 $BatchId 下没有迁移用户，请先确认批次名。" }
    return @($users)
}

function Export-UserStats {
    <#  逐用户引擎统计 -> user_stats.csv（报告输入 1）
        列：EmailAddress,Status,SyncedItemCount,SkippedItemCount,EstimatedTotalTransferSize,LastSuccessfulSyncTime #>
    param([Parameter(Mandatory)][string]$BatchId, [string]$OutDir)
    Assert-ExoModuleAndSession
    $OutDir = Get-EmailMigrationOutDir $OutDir
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $rows = Get-BatchMailboxList -BatchId $BatchId | ForEach-Object {
        $st = Get-MigrationUserStatistics -Identity $_.Identity
        [PSCustomObject]@{
            EmailAddress               = $_.Identity
            Status                     = $_.Status
            SyncedItemCount            = $st.SyncedItemCount
            SkippedItemCount           = $st.SkippedItemCount
            EstimatedTotalTransferSize = "$($st.EstimatedTotalTransferSize)"
            LastSuccessfulSyncTime     = $st.LastSuccessfulSyncTime
        }
    }
    $path = Join-Path $OutDir 'user_stats.csv'
    $rows | Export-Csv -Path $path -NoTypeInformation -Encoding UTF8
    $sw.Stop()
    Write-Host ("[OK] user_stats.csv 行数 {0}，耗时 {1:N1}s，路径 {2}" -f $rows.Count, $sw.Elapsed.TotalSeconds, $path) -ForegroundColor Green
}

function Export-TargetStats {
    <#  目标邮箱实际落库 -> target_stats.csv（报告输入 2）
        邮件数口径 = 邮件类文件夹（Inbox/SentItems/DeletedItems/Drafts/JunkEmail/Outbox/UserCreated）的【可见邮件】数
        （VisibleItemsInFolder）。非邮件文件夹与 HiddenItemsInFolder（系统隐藏项）都不计入。
        日历/联系人/任务/日记/注释 及 Calendar Logging、Recoverable Items、Purges/Deletions/Versions
        等系统文件夹一律不计入。禁用 Get-MailboxStatistics.ItemCount：那是整个邮箱项数，含非邮件项与隐藏项。
        TotalItemSize 以字符串导出，本地正则提取字节；排除系统邮箱。 #>
    param([Parameter(Mandatory)][string]$BatchId, [string]$OutDir)
    Assert-ExoModuleAndSession
    $OutDir = Get-EmailMigrationOutDir $OutDir
    $mailFolderTypes = @('Inbox','SentItems','DeletedItems','Drafts','JunkEmail','Outbox','UserCreated')
    # 一级路径属于这些非邮件根目录的一律不算邮件（如系统自动挂的 /日历/中国 节假日，类型也是 UserCreated）。
    $nonMailRoots = @('日历','Calendar','联系人','Contacts','任务','Tasks','日记','Journal','注释','Notes',
                      '对话历史记录','Conversation History','Yammer 根目录','Yammer Root','存档','Archive')
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $rows = Get-BatchMailboxList -BatchId $BatchId |
        Where-Object { $_.Identity -notlike '*Discovery*' } | ForEach-Object {
        # 必须用 V3 REST 版 cmdlet：只有它区分 VisibleItemsInFolder / HiddenItemsInFolder。
        # 经典 Get-MailboxFolderStatistics 的 ItemsInFolder 含隐藏项，会把 3 封邮件算成 11 项。
        # FolderType：V3 cmdlet 的用户自建文件夹是 'User Created'（带空格），统一去空白再比对。
        $folders = @(Get-EXOMailboxFolderStatistics -Identity $_.Identity | Where-Object {
            $ft = $_.FolderType -replace '\s+', ''
            if ($mailFolderTypes -notcontains $ft) { return $false }
            if ($ft -eq 'UserCreated' -and $nonMailRoots -contains ($_.FolderPath -split '/')[1]) { return $false }
            return $true
        })
        $count = 0
        $bytes = [int64]0
        foreach ($fo in $folders) {
            $count += [int]$fo.VisibleItemsInFolder
            # FolderSize 是字符串（"175.9 KB (180,074 bytes)"），统一从字节数括号里取。
            $m = [regex]::Match([string]$fo.FolderSize, '\(([\d,]+)\s+bytes\)')
            if ($m.Success) { $bytes += [int64]($m.Groups[1].Value -replace ',', '') }
        }
        [PSCustomObject]@{
            EmailAddress  = $_.Identity
            ItemCount     = $count
            TotalItemSize = ('{0} KB ({1} bytes)' -f ($bytes / 1KB).ToString('N1', $inv),
                                                        $bytes.ToString('N0', $inv))
        }
    }
    $path = Join-Path $OutDir 'target_stats.csv'
    $rows | Export-Csv -Path $path -NoTypeInformation -Encoding UTF8
    $sw.Stop()
    Write-Host ("[OK] target_stats.csv 行数 {0}，耗时 {1:N1}s，路径 {2}" -f @($rows).Count, $sw.Elapsed.TotalSeconds, $path) -ForegroundColor Green
}

function Export-FolderStats {
    <#  目标侧逐文件夹邮件数 -> folder_stats.csv（verify 输入；报告不使用）
        前三列 EmailAddress,FolderPath,ItemsInFolder 是 verify 依赖的列名，保持不变；
        口径：ItemsInFolder 填【可见邮件数】VisibleItemsInFolder，不含 HiddenItemsInFolder
        （隐藏项由迁移/系统写入，客户端看不见，计入会与源端 IMAP 逐文件夹数对不上）；
        另补 HiddenItemsInFolder/FolderType 便于人工核对。 #>
    param([Parameter(Mandatory)][string]$BatchId, [string]$OutDir)
    Assert-ExoModuleAndSession
    $OutDir = Get-EmailMigrationOutDir $OutDir
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $rows = Get-BatchMailboxList -BatchId $BatchId | ForEach-Object {
        $addr = $_.Identity
        Get-EXOMailboxFolderStatistics -Identity $addr |
            Select-Object @{N='EmailAddress';E={$addr}}, FolderPath, FolderType,
                          @{N='ItemsInFolder';E={$_.VisibleItemsInFolder}},
                          @{N='HiddenItemsInFolder';E={$_.HiddenItemsInFolder}}
    }
    $path = Join-Path $OutDir 'folder_stats.csv'
    $rows | Export-Csv -Path $path -NoTypeInformation -Encoding UTF8
    $sw.Stop()
    Write-Host ("[OK] folder_stats.csv 行数 {0}，耗时 {1:N1}s，路径 {2}" -f @($rows).Count, $sw.Elapsed.TotalSeconds, $path) -ForegroundColor Green
}

Write-Host 'exo_tasks.ps1 已加载：Assert-ExoSession / Export-UserStats / Export-TargetStats / Export-FolderStats' -ForegroundColor Cyan