<# save_thought_stable.ps1 (minimal stable)
 - One-shot: Gravity rollover -> thoughts.ps1 (-m) -> official save -> run_history
 - Use -BaseDir to pin SkillDays root (e.g., G:\共有ドライブ\SkillDays)
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Text,
  [string]$Tags = "metaskilldays,思想重力,構想",
  [string]$Author = "ryousuke",
  [string]$YearMonth = (Get-Date -Format "yyyy-MM"),
  [string]$SaveDate  = (Get-Date -Format "yyyy-MM-dd"),
  [string]$BaseDir   = "",
  [switch]$DryRun
)

#$env:TS_SKIP_INLINE_SAVE = '1'

$ErrorActionPreference = "Stop"
try { $OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); chcp 65001 | Out-Null } catch {}

function Resolve-Base([string]$Override){
  if ($Override) {
    if (!(Test-Path $Override)) { throw "BaseDir not found: $Override" }
    return (Resolve-Path $Override).Path
  }
  $cands = @(
    "G:\Shared drives\SkillDays",
    "G:\My Drive\SkillDays",
    "G:\共有ドライブ\SkillDays",
    "G:\マイドライブ\SkillDays"
  ) | Where-Object { Test-Path $_ }
  if ($cands.Count -eq 0) { throw "SkillDays base not found. Provide -BaseDir." }
  return (Resolve-Path $cands[0]).Path
}

function Get-VenvPy {
  $here = Get-Location
  $venv = Join-Path $here.Path ".venv\Scripts\python.exe"
  if (!(Test-Path $venv)) { throw "venv python not found: $venv" }
  return $venv
}

# 1) Resolve paths
$Base = Resolve-Base -Override $BaseDir
$GravityDir = Join-Path $Base "gravity"
$RunHistory = Join-Path $Base "run_history.log"
Write-Host ("Base   : {0}" -f $Base)

# 2) Gravity rollover
New-Item -ItemType Directory -Path $GravityDir -Force | Out-Null
$ymDate = [datetime]::ParseExact("$YearMonth-01","yyyy-MM-dd",$null)
$prevMonth = $ymDate.AddMonths(-1).ToString("yyyy-MM")
$gravIn  = Join-Path $Base ("gravity\gravity_{0}.json" -f $YearMonth)
$gravOut = $gravIn

# gravity_{YearMonth}.json が存在するかで分岐
if (Test-Path $gravIn) {
  $prevRaw = Get-Content -LiteralPath $gravIn -Raw -ErrorAction Stop
  try {
    $prev = $prevRaw | ConvertFrom-Json -ErrorAction Stop
  }
  catch {
    # JSONL/NDJSON（.jsonl）を誤って掴んだ場合のフォールバック
    if ($gravIn -match '\.jsonl$') {
      $prev = @()
      Get-Content -LiteralPath $gravIn -ErrorAction Stop | ForEach-Object {
        $line = $_.Trim()
        if ($line) {
          try { $prev += ($line | ConvertFrom-Json) } catch {}
        }
      }
    }
    else {
      # 空や不正JSONは空オブジェクトで継続（初期月の想定）
      $prev = @{}
    }
  }

  $outObj = [ordered]@{
    vectors = $prev.vectors
    meta    = [ordered]@{
      month          = $YearMonth
      inherited_from = $prevMonth
      inherited_at   = (Get-Date).ToString('o')
      policy         = 'copy-forward'
      alpha          = 1.0
    }
    trace   = @{ memory_map_ref = '' }
  }
}
else {
  $outObj = [ordered]@{
    vectors = @{}
    meta    = [ordered]@{
      month          = $YearMonth
      inherited_from = ''
      inherited_at   = (Get-Date).ToString('o')
      policy         = 'init'
      alpha          = 1.0
    }
    trace   = @{ memory_map_ref = '' }
  }
}
$outJson = ($outObj | ConvertTo-Json -Depth 100)
if (-not $DryRun) { $outJson | Set-Content -Path $gravOut -Encoding UTF8 }
Write-Host ("Gravity: {0}" -f $gravOut)

# # --- Safety: ensure month provisioned (empty NDJSON files) ---
# # 保存対象の日付ファイル（journal_by_day/YYYY/MM/YYYY-MM-DD.ndjson）が無ければ、
# # provision_journal_month.ps1 を empty モードで起動して、その月分の“器”を作成する（冪等）。
# if (-not $env:TS_SKIP_MONTH_PROVISION) {
#   try {
#     # SaveDate → YYYY / MM / path
#     $year  = $SaveDate.Substring(0,4)
#     $month = $SaveDate.Substring(5,2)
#     $thoughtDir = Join-Path $Base ("thoughts\journal_by_day\{0}\{1}" -f $year, $month)
#     $target = Join-Path $thoughtDir ("{0}.ndjson" -f $SaveDate)

#     $scriptDir = Split-Path -Parent $PSCommandPath
#     $prov = Join-Path $scriptDir "provision_journal_month.ps1"

#     if (-not (Test-Path $target) -and (Test-Path $prov)) {
#       Write-Host "[provision] month files missing → provisioning empty NDJSON for $YearMonth"
#       & powershell -ExecutionPolicy Bypass -File $prov -BaseDir $Base -YearMonth $YearMonth -Mode empty
#       if ($LASTEXITCODE -ne 0) { Write-Warning "[provision] month provision failed (exit=$LASTEXITCODE)" }
#     }
#   } catch {
#     Write-Warning "[provision] month provision error: $($_.Exception.Message)"
#   }
# }
## --- End ensure month provisioned ---

# 3) Run thoughts.ps1 via venv python (-m)
if (-not $DryRun) {
  if (-not (Test-Path $env:THOUGHTS_CREDS)) { throw "THOUGHTS_CREDS not found: $env:THOUGHTS_CREDS" }
  if ([string]::IsNullOrEmpty($env:THOUGHTS_ROOT)) { throw "THOUGHTS_ROOT not set." }

  # make src importable for called script if it needs it
  $env:PYTHONPATH = Join-Path (Get-Location) "src"

  # ensure execution policy per session
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

  # call thoughts.ps1 (which should internally call venv python with -m after前回修正)
  # 1. 日付を環境変数で明示的に渡す（YYYY-MM-DD）
  $env:TS_SAVE_DATE = $SaveDate

  # 2. thoughts.ps1 を1回だけ呼ぶ
  & powershell -ExecutionPolicy Bypass -File "$PSScriptRoot/thoughts.ps1" `
    -Text $Text `
    -Tags $Tags `
    -Author $Author `
    -GravityPath $gravOut

  # 3. official save（memory_map 更新）
  & python "$PSScriptRoot/run_official_save.py" --date $env:TS_SAVE_DATE
}
# 5) run_history append
if (-not $DryRun) {
  $sha256 = ""
  try {
    $sha256 = [BitConverter]::ToString(
      ([Security.Cryptography.SHA256]::Create()).ComputeHash([Text.Encoding]::UTF8.GetBytes($outJson))
    ).Replace("-","").ToLower()
  } catch { $sha256 = "n/a" }
  $line = "{0} | job=T0152 | step=thought_save+gravity_rollover | date={1} | gravity={2} | policy={3} | sha256={4}" -f `
    (Get-Date -Format o), $SaveDate, (Split-Path $gravOut -Leaf), $outObj.meta.policy, $sha256
  try {
    Add-Content -Path $RunHistory -Value $line
  } catch {
    Write-Warning "run_history append failed: $($_.Exception.Message)"
  }
}

# 6) Reflection (post-save hook) - extended with Task B (re-save reflection_thought)
if (-not $DryRun) {
  Write-Host "[Reflection] post-save reflection hook starting..."

  # a) スキップ判定
  if ($env:TS_SKIP_REFLECTION -eq "1") {
    Write-Host "[Reflection] skipped (TS_SKIP_REFLECTION=1)"
  }
  else {
    try {
      # b) thought NDJSON のパスを決定
      $year  = $SaveDate.Substring(0,4)
      $month = $SaveDate.Substring(5,2)
      $thoughtDir  = Join-Path $Base ("thoughts\journal_by_day\{0}\{1}" -f $year, $month)
      $thoughtFile = Join-Path $thoughtDir ("{0}.ndjson" -f $SaveDate)

      if (-not (Test-Path $thoughtFile)) {
        Write-Warning "[Reflection] thought file not found: $thoughtFile"
      }
      else {

        # c) 出力先ディレクトリ
        if (-not $env:REFLECTION_OUT_DIR) {
          Write-Warning "[Reflection] REFLECTION_OUT_DIR is not set. Skip reflection."
        }
        else {
          # reflection output root
          $reflectionOutDir = $env:REFLECTION_OUT_DIR
          if (-not (Test-Path $reflectionOutDir)) {
            New-Item -ItemType Directory -Path $reflectionOutDir | Out-Null
          }

          $stamp = (Get-Date).ToString("yyyy-MM-dd_HHmmss")
          # reflection_cli.py 用の "アウトディレクトリ" として使う
          $reflectionOutFile = Join-Path $reflectionOutDir ("reflection_{0}.ndjson" -f $stamp)

          # d) reflection CLI 実行
          try {
            Write-Host "[Reflection] running reflection_cli..."

            # reflection_cli.py のパス
            $reflectionScriptPath = $env:REFLECTION_SCRIPT_PATH
            if (-not $reflectionScriptPath) {
              $reflectionScriptPath = Join-Path $PSScriptRoot "src\thoughts_store\cli\reflection_cli.py"
            }

            if (-not (Test-Path $reflectionScriptPath)) {
              Write-Warning "[Reflection] CLI script not found: $reflectionScriptPath"
            }
            else {
              # reflection_cli.py 引数
              $reflectionArgs = @(
                $reflectionScriptPath,
                "--thoughts", $thoughtFile,
                "--out",      $reflectionOutFile
              )

              if ($env:REFLECTION_ALPHA_PATH) {
                $reflectionArgs += @("--alpha", $env:REFLECTION_ALPHA_PATH)
              }

              # ★ stdout をキャプチャ
              $reflectionOutput = & python $reflectionArgs
              $exitCode = $LASTEXITCODE

              if ($exitCode -eq 0) {
                # そのままstdoutを出力
                Write-Host $reflectionOutput
                Write-Host ("[Reflection] generated: {0}" -f $reflectionOutFile)

                # ★ Task B: reflection_thought.ndjson の再保存フェーズ
                try {
                  $refInfo = $reflectionOutput | ConvertFrom-Json
                  $refNdjson = $refInfo.ndjson

                  if ($refNdjson -and (Test-Path $refNdjson)) {
                    Write-Host ("[Reflection] re-save target ndjson: {0}" -f $refNdjson)

                    # save_reflection_thoughts.py を起動
                    $saveRefScript = Join-Path $PSScriptRoot "save_reflection_thoughts.py"

                    if (Test-Path $saveRefScript) {
                      & python $saveRefScript `
                        --base-dir  $Base `
                        --source    $refNdjson `
                        --date      $SaveDate

                      $saveExit = $LASTEXITCODE
                      if ($saveExit -eq 0) {
                        Write-Host "[Reflection] re-save completed."
                      }
                      else {
                        Write-Warning ("[Reflection] re-save script exited with code {0}" -f $saveExit)
                      }
                    }
                    else {
                      Write-Warning "[Reflection] save_reflection_thoughts.py not found. Re-save skipped."
                    }
                  }
                  else {
                    Write-Warning "[Reflection] refInfo.ndjson not found or invalid."
                  }
                }
                catch {
                  Write-Warning "[Reflection] failed to parse reflection JSON: $($_.Exception.Message)"
                }
              }
              else {
                Write-Warning ("[Reflection] reflection CLI exited with code {0}. See above logs." -f $exitCode)
              }
            }
          }
          catch {
            Write-Warning "[Reflection] reflection_cli failed: $($_.Exception.Message)"
          }
        }
      }
    }
    catch {
      Write-Warning "[Reflection] unexpected error: $($_.Exception.Message)"
    }
  }
}

Write-Host "[DONE] Thought flow completed."
if ($DryRun) { Write-Host " - Mode : DRY-RUN" }