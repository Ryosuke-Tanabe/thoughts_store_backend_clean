param(
  [Parameter(Mandatory = $true)][string]$Text,
  [string]$Tags = "",
  [string]$Author = "ryousuke",
  [Parameter(Mandatory = $true)][string]$GravityPath
)

# ----------------------------------------
# 0) 日付の決定（TS_SAVE_DATE があればそれを優先）
# ----------------------------------------
if ($env:TS_SAVE_DATE -and $env:TS_SAVE_DATE -match '^\d{4}-\d{2}-\d{2}$') {
  $saveDate = [datetime]::ParseExact($env:TS_SAVE_DATE, 'yyyy-MM-dd', $null)
}
else {
  # 日本時間（PCローカルが日本前提）で今日
  $saveDate = Get-Date
}

$year    = $saveDate.ToString('yyyy')
$month   = $saveDate.ToString('MM')
$dateStr = $saveDate.ToString('yyyy-MM-dd')

# ----------------------------------------
# 1) SkillDays BaseDir と journal_by_day のパスを決める
#    GravityPath: G:\共有ドライブ\SkillDays\gravity\gravity_2025-11.json
#    → BaseDir = G:\共有ドライブ\SkillDays
# ----------------------------------------
$gravityFile = Get-Item -LiteralPath $GravityPath
$gravityDir  = $gravityFile.Directory      # ...\SkillDays\gravity
$baseDir     = $gravityDir.Parent.FullName # ...\SkillDays

$journalRoot = Join-Path $baseDir "thoughts\journal_by_day"
$journalDir  = Join-Path $journalRoot "$year\$month"
$journalFile = Join-Path $journalDir "$dateStr.ndjson"

if (-not (Test-Path $journalDir)) {
  New-Item -ItemType Directory -Path $journalDir -Force | Out-Null
}

# NOTE: Do NOT pre-create $journalFile (0KB禁止). It will be created by Add-Content on first write.

# ----------------------------------------
# 2) 直近の prev_hash を取得
# ----------------------------------------
$prevHash = $null
if (Test-Path $journalFile) {
  $lines = Get-Content -LiteralPath $journalFile -ErrorAction SilentlyContinue
  if ($lines -and $lines.Count -gt 0) {
    try { $last = $lines[-1] | ConvertFrom-Json; $prevHash = $last.hash }
    catch { Write-Warning "[thoughts.ps1] failed to parse last line as JSON. prev_hash will be null." }
  }
}

# ----------------------------------------
# 3) 新しいレコードを作成して追記
#    フォーマット:
#    {id, t_utc, author, text, gravity, prev_hash, hash, algo, v}
# ----------------------------------------
# ランダムID（12桁の16進）
$id = ([guid]::NewGuid().ToString('N')).Substring(0, 12)

# UTC 時刻
$nowUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ')

# gravity はとりあえず空オブジェクト（必要ならあとで拡張）
$gravity = @{}

# ハッシュ対象のペイロード文字列
$payload = "$id|$nowUtc|$Author|$Text"

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$bytes  = [System.Text.Encoding]::UTF8.GetBytes($payload)
$hashBytes = $sha256.ComputeHash($bytes)
$hash = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })

# レコード本体（順序付きで書いておくと見やすい）
$record = [ordered]@{
  id        = $id
  t_utc     = $nowUtc
  author    = $Author
  text      = $Text
  gravity   = $gravity
  prev_hash = $prevHash
  hash      = $hash
  algo      = "sha256(payload)"
  v         = 1
}

$recordJson = $record | ConvertTo-Json -Compress

# 末尾に1行追記
Add-Content -LiteralPath $journalFile -Value $recordJson -Encoding UTF8

Write-Host ("[thoughts.ps1] appended thought to " + $journalFile)

# ----------------------------------------
# 4) ThoughtStore 側（Google Drive / Gravity）の更新
#    ここは従来のマインドをそのまま維持
# ----------------------------------------
$backendRoot = "C:\python\thoughts_store\thoughts_store_backend"
$cliScript   = Join-Path $backendRoot "src\thoughts_store\cli\save_thought.py"
$credsPath   = Join-Path $backendRoot "secrets\thoughts-store-backend-7e31c99a6c44.json"
$rootId      = "1ZqZIxlgZ7vRG3EvmAZIEikeyzktHyP7Z"  # JournalフォルダのルートID（ログより）

Push-Location $backendRoot
try {
  $argsList = @(
    $cliScript,
    "--creds",        $credsPath,
    "--root",         $rootId,
    "--author",       $Author,
    "--text",         $Text,
    "--gravity-json", "@$GravityPath"
  )

  Write-Host (">> python " + ($argsList -join " "))
  & python @argsList
  if ($LASTEXITCODE -ne 0) {
    throw ("save_thought.py failed. ExitCode={0}" -f $LASTEXITCODE)
  }

  Write-Host "笨・Thought saved (see thoughts root for new file)."
}
catch {
  Write-Error $_
  exit 1
}
finally {
  Pop-Location
}
