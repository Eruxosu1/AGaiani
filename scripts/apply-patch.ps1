<#
  apply-patch.ps1 - apply a .patch from Claude and push it.
  Usage (from D:\AGaiani):
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-patch.ps1 -Patch name.patch -Message "Commit message"
  Steps: pause auto-sync -> git apply --check -> git apply -> delete patch -> git add -A -> commit --no-verify -> push -> resume auto-sync.
  Auto-sync is ALWAYS resumed (finally block), even if something fails.
#>
param(
    [Parameter(Mandatory = $true)][string]$Patch,
    [Parameter(Mandatory = $true)][string]$Message,
    [string]$RepoPath = "D:\AGaiani",
    [string]$TaskName = "AGaianiGitHubSync"
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $RepoPath
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
try {
    if ($task) { Disable-ScheduledTask -TaskName $TaskName | Out-Null }
    if (-not (Test-Path -LiteralPath $Patch)) { throw "Patch file not found: $Patch" }
    git apply --ignore-whitespace --check $Patch
    if ($LASTEXITCODE -ne 0) { throw "git apply --check failed. Send the error text to Claude." }
    git apply --ignore-whitespace $Patch
    if ($LASTEXITCODE -ne 0) { throw "git apply failed." }
    Remove-Item -LiteralPath $Patch
    git add -A
    git commit --no-verify -m $Message
    git push
    Write-Host "Done: $Message"
}
finally {
    if ($task) { Enable-ScheduledTask -TaskName $TaskName | Out-Null }
}
