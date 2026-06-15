<# monitor_monthly_jobs.ps1 (simple)
 - 月初タスク(例: provision_journal_month.ps1)の実行状況を簡易チェックするスクリプト
 - 想定: C:\python\thoughts_store\thoughts_store_backend\ に配置
 - BaseDir: SkillDays の共有ドライブルート (例: G:\共有ドライブ\SkillDays)
 - 出力: BaseDir\logs\monthly_jobs_YYYY-MM.log
#>

[CmdletBinding()]
param(
  [string]$BaseDir   = "",
  [string]$YearMonth = (Get-Date -Format "yyyy-MM"),
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# --- BaseDir 解決 --------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($BaseDir)) {
  if ($env:SKILLDAYS_BASE) {
    $BaseDir = $env:SKILLDAYS_BASE
  }
  else {
    throw "BaseDir is empty and SKILLDAYS_BASE is not set. Please specify -BaseDir."
  }
}

Write-Host "monitor_monthly_jobs: BaseDir   = $BaseDir"
Write-Host "monitor_monthly_jobs: YearMonth = $YearMonth"
if ($DryRun) {
  Write-Host "monitor_monthly_jobs: Mode      = DRY-RUN"
}

# --- Year / Month 抽出 ---------------------------------------------------
if ($YearMonth -notmatch '^\d{4}-\d{2}$') {
  throw "YearMonth must be in format yyyy-MM (e.g. 2025-11). Got: $YearMonth"
}
$year  = $YearMonth.Substring(0,4)
$month = $YearMonth.Substring(5,2)

# --- ログファイルパス ----------------------------------------------------
$logsDir = Join-Path $BaseDir "logs"
$logFile = Join-Path $logsDir ("monthly_jobs_{0}.log" -f $YearMonth)

# DryRun でなければ logs ディレクトリを用意
if (-not $DryRun) {
  if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
  }
}

function Write-JobLogLine {
  param(
    [string]$Line
  )
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $full = "[{0}] {1}" -f $timestamp, $Line
  Write-Host $full
  if (-not $DryRun) {
    $full | Out-File -FilePath $logFile -Encoding utf8 -Append
  }
}

# WARN が発生したかどうかのフラグ
$global:MonthlyJobHasWarning = $false

Write-JobLogLine "=== Monthly job check start (YearMonth=$YearMonth) ==="

# --- チェック対象: provision_journal_month.ps1 の効果をざっくり見る ----
Write-JobLogLine "Job: provision_journal_month - journal_by_day フォルダの月初セットアップ"

$journalDir = Join-Path $BaseDir ("thoughts\journal_by_day\{0}\{1}" -f $year, $month)
if (Test-Path $journalDir) {
  Write-JobLogLine ("  [OK] journal_by_day dir exists: {0}" -f $journalDir)
}
else {
  Write-JobLogLine ("  [WARN] journal_by_day dir NOT found: {0}" -f $journalDir)
  $global:MonthlyJobHasWarning = $true
}

# --- サマリ通知行 --------------------------------------------------------
if ($global:MonthlyJobHasWarning) {
  Write-JobLogLine "[SUMMARY] Monthly job check result: WARN (some checks failed)."
}
else {
  Write-JobLogLine "[SUMMARY] Monthly job check result: OK (all checks passed)."
}

Write-JobLogLine "=== Monthly job check end ==="
