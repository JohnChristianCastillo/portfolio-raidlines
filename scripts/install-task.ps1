# Register (or re-register) the Scheduled Task that keeps the site current.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1 -At 03:30
#   powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1 -Remove
#
# The loop it closes: refresh.ps1 snapshots and force-pushes the data branch,
# Cloudflare notices the branch moved and rebuilds, the site is current. Nothing
# needs to be running for visitors, only for the refresh.
#
# -Full is deliberate. An ordinary snapshot skips boards already on disk, which is
# what makes it resumable, but it also means an unforced daily run would find
# everything present and do nothing. A refresh has to rewrite.
#
# StartWhenAvailable matters more than the hour on a laptop that is not always on:
# a run missed while it was asleep happens at the next opportunity instead of being
# skipped until tomorrow.

param(
    [string]$TaskName = "Raidlines snapshot refresh",
    [string]$At = "05:00",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..").Path
$script = Join-Path $repo "scripts\refresh.ps1"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "removed '$TaskName'"
    } else {
        Write-Output "'$TaskName' was not registered"
    }
    return
}

if (-not (Test-Path $script)) { throw "no refresh script at $script" }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Full" `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -Daily -At $At

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
    -MultipleInstances IgnoreNew

# Runs as you, only when logged on. A refresh needs the git credentials and the
# .env in your profile, so running it as SYSTEM would fail on both.
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Snapshots Warcraft Logs and publishes to the data branch, which makes Cloudflare rebuild raidlines." `
    -Force | Out-Null

Write-Output "registered '$TaskName', daily at $At"
Write-Output "  run now:   Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "  check:     Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Output "  remove:    scripts\install-task.ps1 -Remove"
