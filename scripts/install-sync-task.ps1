# Registers the Windows scheduled task that syncs D:\AGaiani to GitHub every 10 minutes.
$act = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\AGaiani\scripts\sync-to-github.ps1"'
$trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "AGaianiGitHubSync" -Action $act -Trigger $trg -Settings $set -Description "Auto commit and push D:\AGaiani to GitHub"
