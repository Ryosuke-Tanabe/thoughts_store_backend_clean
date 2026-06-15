param(
  [Parameter(Mandatory=$true)]
  [string]$BaseDir,
  [string]$YearMonth,            # yyyy-MM (optional). If omitted: current JST month.
  [switch]$DryRun
)

<#
.SYNOPSIS
  Ensure month directory exists for thoughts/journal_by_day (directory-only provisioning).

.DESCRIPTION
  POLICY (T0169):
   - Do NOT pre-create daily .ndjson files.
   - .ndjson is created only when an actual thought record is appended (Lazy Create).
   - If a placeholder is needed for structure, use .gitkeep (NOT .ndjson).

.PARAMETERS
  -BaseDir     SkillDays base (e.g., G:\共有ドライブ\SkillDays)
  -YearMonth   Target month in yyyy-MM. If omitted, uses current month in JST.
  -DryRun      No writes (simulates).
#>

function Get-JstNow { (Get-Date).ToUniversalTime().AddHours(9) }

$jstNow = Get-JstNow
if (-not $YearMonth) { $YearMonth = $jstNow.ToString('yyyy-MM') }
if ($YearMonth -notmatch '^\d{4}-\d{2}$') { throw "YearMonth must be yyyy-MM" }

$year  = [int]$YearMonth.Substring(0,4)
$month = [int]$YearMonth.Substring(5,2)

$monthDir = Join-Path $BaseDir ("thoughts\journal_by_day\{0}\{1:00}" -f $year,$month)

if ($DryRun) {
  Write-Host "[provision] (DryRun) ensure month dir only: $monthDir"
  return
}

New-Item -ItemType Directory -Force -Path $monthDir | Out-Null

# Optional: keep folder with non-ndjson placeholder
$keep = Join-Path $monthDir ".gitkeep"
if (-not (Test-Path $keep)) { New-Item -ItemType File -Path $keep | Out-Null }

Write-Host "[provision] ensured month dir only (no .ndjson pre-create): $monthDir"
