# One-time: create the local git repository in D:\AGaiani and connect it to your PRIVATE GitHub repo.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\init-repo.ps1 -RemoteUrl https://github.com/<you>/<repo>.git
param([Parameter(Mandatory = $true)][string]$RemoteUrl)
Set-Location -LiteralPath "D:\AGaiani"
if (-not (Test-Path ".git")) { git init -b main }
git remote remove origin 2>$null
git remote add origin $RemoteUrl
git add -A
git commit --no-verify -m "M0: project skeleton, plan, tools, git workflow"
git push -u origin main
