<# run_daily_thought.ps1 (with generate_today_theme args)
#>

[CmdletBinding()]
param(
  [string]$BaseDir    = "",
  [string]$YearMonth  = (Get-Date -Format "yyyy-MM"),
  [string]$TargetDate = (Get-Date -Format "yyyy-MM-dd"),
  [string]$PythonExe  = "python",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# --- Resolve BaseDir --------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($BaseDir)) {
  if ($env:SKILLDAYS_BASE) {
    $BaseDir = $env:SKILLDAYS_BASE
  }
  else {
    $BaseDir = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
  }
}

Write-Host "run_daily_thought: BaseDir    = $BaseDir"
Write-Host "run_daily_thought: TargetDate = $TargetDate"
Write-Host "run_daily_thought: YearMonth  = $YearMonth"
if ($DryRun) {
  Write-Host "run_daily_thought: Mode       = DRY-RUN"
}

# --- Script path setup ------------------------------------------------------
$backendDir  = $PSScriptRoot
$themeScript = Join-Path $backendDir "generate_today_theme.py"
$saveScript  = Join-Path $backendDir "save_thought_stable.ps1"

if (-not (Test-Path $themeScript)) { throw "not found: $themeScript" }
if (-not (Test-Path $saveScript))  { throw "not found: $saveScript" }

# reflection_cli のアウトプットを置く暫定ディレクトリ
$reflectionOutDir = Join-Path $BaseDir "python\thoughts_store\reflection_output"
if (-not (Test-Path $reflectionOutDir)) {
  New-Item -ItemType Directory -Path $reflectionOutDir | Out-Null
}

# --- Run generate_today_theme.py -------------------------------------------
Write-Host "run_daily_thought: Running generate_today_theme.py ..."
Write-Host "run_daily_thought:   --base-dir          = $BaseDir"
Write-Host "run_daily_thought:   --today             = $TargetDate"
Write-Host "run_daily_thought:   --reflection-out-dir= $reflectionOutDir"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $PythonExe

# 引数をすべて明示的に付ける
$psi.Arguments = '"' + $themeScript + '"' `
  + ' --base-dir "' + $BaseDir + '"' `
  + ' --today "' + $TargetDate + '"' `
  + ' --reflection-out-dir "' + $reflectionOutDir + '"'

$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError  = $true
$psi.UseShellExecute        = $false
$psi.CreateNoWindow         = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$null   = $proc.Start()
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()
$exitCode = $proc.ExitCode
$proc.Dispose()

if ($exitCode -ne 0) {
  Write-Error "run_daily_thought: generate_today_theme.py failed (code=$exitCode)"
  if ($stderr) {
    Write-Error $stderr
  }
  throw "generate_today_theme.py failed with exit code $exitCode"
}

$themeText = $stdout.Trim()
if (-not $themeText) {
  throw "run_daily_thought: Theme is empty"
}

$previewLen = [Math]::Min(80, $themeText.Length)
$preview    = $themeText.Substring(0, $previewLen) -replace "`r"," " -replace "`n"," "
Write-Host "run_daily_thought: Theme preview: $preview"

if ($DryRun) {
  Write-Host "run_daily_thought: DRY-RUN => skip save"
  return
}

# --- Save via save_thought_stable.ps1 --------------------------------------
Write-Host "run_daily_thought: Saving via save_thought_stable.ps1 ..."

& $saveScript `
  -Text $themeText `
  -Tags "daily-thought,今日の思想テーマ" `
  -Author "ryousuke" `
  -YearMonth $YearMonth `
  -SaveDate $TargetDate `
  -BaseDir $BaseDir

if ($LASTEXITCODE -ne 0) {
  throw "run_daily_thought: save_thought_stable.ps1 failed (exit=$LASTEXITCODE)"
}

Write-Host "run_daily_thought: Completed successfully."
