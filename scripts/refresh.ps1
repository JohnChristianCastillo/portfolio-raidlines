# Refresh the snapshot and publish it. This is what the Scheduled Task runs.
#
#   powershell -ExecutionPolicy Bypass -File scripts\refresh.ps1
#
# Three steps, in order, each only run if the last succeeded:
#   1. snapshot  ask Warcraft Logs for anything that changed
#   2. publish   force-push the result to the orphan data branch
#   3. trigger   push an empty commit to main so Cloudflare rebuilds
#
# Step 3 is not redundant. Cloudflare builds on a push to its production branch,
# which is main; a push to the data branch does not move main and so does not
# rebuild anything. Without this the data branch would go on updating daily while
# the published site served whatever it had at the last code change.
#
# Safe to run at any time and safe to interrupt. The snapshot skips boards already
# on disk, so a run that dies halfway costs nothing and the next one continues.
#
# -Full rewrites every board, and the Scheduled Task uses it. An ordinary run skips
# boards already on disk, which is what makes it resumable, but it also means an
# unforced refresh would find everything present and do nothing. Rankings churn even
# when the file list does not.

param(
    [switch]$Full,
    [string]$LogDir = "$PSScriptRoot\..\_logs"
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path "$PSScriptRoot\.."
$python = Join-Path $repo "backend\.venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$log = Join-Path $LogDir "refresh_$stamp.log"

function Write-Log($message) {
    $line = "{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $message
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Invoke-Logged($workingDir, $commandLine) {
    # Redirection is done by cmd, not PowerShell. Piping a native command's stderr
    # through PowerShell wraps every line in an ErrorRecord and trips
    # $ErrorActionPreference = Stop, so git writing an ordinary progress line to
    # stderr would abort the run. cmd just appends bytes to the file.
    Push-Location $workingDir
    try {
        & cmd /c "$commandLine >> `"$log`" 2>&1"
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

Write-Log "refresh starting in $repo"

if (-not (Test-Path $python)) {
    Write-Log "ERROR: no venv at $python. Create it with: python -m venv backend\.venv"
    exit 1
}

# --- 1. snapshot ------------------------------------------------------------------
$snapshotArgs = @("tools\snapshot.py")
if ($Full) { $snapshotArgs += "--force" }

Write-Log "snapshot $($snapshotArgs -join ' ')"
$code = Invoke-Logged (Join-Path $repo "backend") "`"$python`" $($snapshotArgs -join ' ')"
if ($code -ne 0) {
    Write-Log "ERROR: snapshot exited $code, not publishing. See $log"
    exit $code
}
Write-Log "snapshot done"

# --- 2. publish -------------------------------------------------------------------
# Publishing needs bash, which ships with Git for Windows.
$bash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $bash)) {
    $bash = (Get-Command bash -ErrorAction SilentlyContinue).Source
}
if (-not $bash) {
    Write-Log "ERROR: bash not found. Publishing needs Git for Windows."
    exit 1
}

Write-Log "publishing to the data branch"
$code = Invoke-Logged $repo "`"$bash`" scripts/publish-data.sh"
if ($code -ne 0) {
    Write-Log "ERROR: publish exited $code. See $log"
    exit $code
}

Write-Log "published to the data branch"

# --- 3. trigger the rebuild -------------------------------------------------------
# The build fetches the data branch itself, so main needs no content change, only a
# new commit for Cloudflare to react to. Fast-forward first: refusing to push onto a
# diverged main is better than forcing over work done from another machine.
$code = Invoke-Logged $repo "git pull --ff-only"
if ($code -ne 0) {
    Write-Log "WARNING: main could not fast-forward, so no rebuild was triggered."
    Write-Log "The data branch is published; push main by hand to pick it up."
    exit 0
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$code = Invoke-Logged $repo "git commit --allow-empty -m `"Refresh snapshot $stamp`""
if ($code -eq 0) {
    $code = Invoke-Logged $repo "git push origin main"
}
if ($code -ne 0) {
    Write-Log "WARNING: could not trigger the rebuild. Data is published; push main by hand."
    exit 0
}

Write-Log "pushed main, Cloudflare will rebuild"

# Keep a fortnight of logs. Enough to see a pattern, not enough to accumulate.
Get-ChildItem $LogDir -Filter "refresh_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Log "refresh complete"
