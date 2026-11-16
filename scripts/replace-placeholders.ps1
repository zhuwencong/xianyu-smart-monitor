<#
.SYNOPSIS
    把仓库里的占位符替换成真实的 GitHub 用户名 / 仓库名 / 署名。

.DESCRIPTION
    开源模板里的 <GITHUB_USER>、xianyu-smart-monitor、<SECURITY_EMAIL> 等占位符
    需要一次性替换。这个脚本只改 git 已跟踪的文本文件（没有 git 时退回目录扫描），
    会跳过 .venv、node_modules、data、logs、state 等运行时目录。

    注意：脚本会跳过**自己**和 scripts/build-market-index.mjs。
    这两个文件里的 <GITHUB_USER> 是「未填」判定的哨兵值，不能被替换掉，
    否则第二次运行就失去了检测能力（曾经踩过：哨兵被换成真实用户名后，
    市场索引生成器开始把真实仓库地址当成占位符拒绝）。

.EXAMPLE
    pwsh -File scripts/replace-placeholders.ps1 -GitHubUser yourname

.EXAMPLE
    pwsh -File scripts/replace-placeholders.ps1 -GitHubUser yourname -Repo my-monitor -Author "Zhang San" -SecurityEmail sec@example.com

.EXAMPLE
    pwsh -File scripts/replace-placeholders.ps1 -GitHubUser yourname -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$GitHubUser,

    [string]$Repo = 'xianyu-smart-monitor',

    [string]$Author = '闲鱼智能监控 Contributors',

    [string]$SecurityEmail = '',

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot

$ExcludeDirs = @(
    '.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.preview', '.preview_check', '.tools', '.workbuddy', 'data', 'logs',
    'images', 'jsonl', 'price_history', 'state', 'dist', 'release', '.mypy_cache'
)

$TextExtensions = @(
    '.md', '.txt', '.json', '.yml', '.yaml', '.mjs', '.js', '.ts', '.vue',
    '.py', '.ps1', '.sh', '.bat', '.toml', '.cfg', '.ini', '.html', '.svg', '.example'
)

function Get-TargetFiles {
    param([string]$Root)

    # 哨兵文件：绝不改写（见 .DESCRIPTION）
    $SentinelFiles = @(
        'scripts/replace-placeholders.ps1',
        'scripts/build-market-index.mjs'
    )

    $isSentinel = {
        param([string]$Path)
        $relative = $Path.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
        $SentinelFiles -contains $relative
    }

    if (Test-Path (Join-Path $Root '.git')) {
        Push-Location $Root
        try {
            $tracked = & git ls-files 2>$null
        }
        finally {
            Pop-Location
        }
        if ($tracked) {
            return $tracked |
                ForEach-Object { Join-Path $Root $_ } |
                Where-Object { (Test-Path -LiteralPath $_) -and -not (& $isSentinel $_) }
        }
    }

    Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
        $relative = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
        $segments = $relative -split '[\\/]'
        (-not ($segments | Where-Object { $ExcludeDirs -contains $_ })) -and -not (& $isSentinel $_.FullName)
    } | ForEach-Object { $_.FullName }
}

$replacements = [ordered]@{
    '<GITHUB_USER>' = $GitHubUser
}

if ($Repo -ne 'xianyu-smart-monitor') {
    $replacements['xianyu-smart-monitor'] = $Repo
}

if ($Author -ne '闲鱼智能监控 Contributors') {
    $replacements['闲鱼智能监控 Contributors'] = $Author
}

if ($SecurityEmail) {
    $replacements['<SECURITY_EMAIL>'] = $SecurityEmail
}

Write-Host "仓库根目录: $RepoRoot"
Write-Host "替换规则:"
foreach ($key in $replacements.Keys) {
    Write-Host ("  {0}  ->  {1}" -f $key, $replacements[$key])
}
if ($DryRun) { Write-Host "模式: 预演（不写文件）`n" } else { Write-Host "模式: 写入`n" }

$encoding = New-Object System.Text.UTF8Encoding($false)
$changedFiles = 0
$totalHits = 0

foreach ($file in Get-TargetFiles -Root $RepoRoot) {
    $extension = [System.IO.Path]::GetExtension($file).ToLowerInvariant()
    $leaf = [System.IO.Path]::GetFileName($file)
    if ($TextExtensions -notcontains $extension -and $leaf -notlike '*.example') { continue }

    $content = [System.IO.File]::ReadAllText($file)
    $updated = $content
    $hits = 0

    foreach ($key in $replacements.Keys) {
        $count = ([regex]::Matches($updated, [regex]::Escape($key))).Count
        if ($count -gt 0) {
            $updated = $updated.Replace($key, $replacements[$key])
            $hits += $count
        }
    }

    if ($hits -eq 0) { continue }

    $relative = $file.Substring($RepoRoot.Length).TrimStart('\', '/')
    Write-Host ("  {0}（{1} 处）" -f $relative, $hits)
    $changedFiles += 1
    $totalHits += $hits

    if (-not $DryRun) {
        [System.IO.File]::WriteAllText($file, $updated, $encoding)
    }
}

Write-Host ""
Write-Host ("完成：{0} 个文件，{1} 处替换。" -f $changedFiles, $totalHits)

if ($changedFiles -eq 0) {
    Write-Host "没有需要替换的内容，说明已经替换过或占位符写法不同。"
    exit 0
}

if (-not $DryRun) {
    Write-Host ""
    Write-Host "下一步："
    Write-Host "  1. node scripts/build-market-index.mjs      # 重新生成市场索引（仓库地址变了）"
    Write-Host "  2. node scripts/check-plugin-versions.mjs   # 校验版本一致"
    Write-Host "  3. git add -A; git commit -m 'chore: 填充仓库身份信息'"
}
