<#
  sync-to-github.ps1
  Auto commit + push: project folder on PC -> GitHub (one direction: PC -> GitHub).

  Run once:
    powershell -NoProfile -ExecutionPolicy Bypass -File D:\AGaiani\scripts\sync-to-github.ps1
  Run in watch mode (stays open, syncs ~1 minute after last change):
    powershell -NoProfile -ExecutionPolicy Bypass -File D:\AGaiani\scripts\sync-to-github.ps1 -Watch

  Log file: %LOCALAPPDATA%\agaiani-sync\sync.log

  Safety checks before every commit (if any fails, NOTHING is committed):
    - file names that must never go to GitHub (.env, keys, browser profiles, archives, databases)
    - files bigger than MaxFileMB (GitHub rejects files > 100 MB)
    - secret-like values in ADDED lines (private keys, bot tokens, sk- keys, long quoted secrets)
#>
param(
    [string]$RepoPath = "D:\AGaiani",
    [string]$Branch = "main",
    [int]$MaxFileMB = 90,
    [switch]$Watch,
    [int]$DebounceSeconds = 60,
    [int]$FallbackMinutes = 10
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:GIT_TERMINAL_PROMPT = "0"

# ---------- logging ----------
$LogDir = Join-Path $env:LOCALAPPDATA "agaiani-sync"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "sync.log"
if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 2MB)) {
    Move-Item -Force $LogFile ($LogFile + ".old")
}

function Write-Log([string]$Msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Msg
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

# ---------- git helper (never throws on stderr warnings) ----------
function Invoke-Git {
    $out = & git -c core.quotepath=false @args 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    [pscustomobject]@{ Code = $code; Out = ($out -join "`n") }
}

function Get-Count([string]$Range) {
    $o = (Invoke-Git rev-list --count $Range).Out.Trim()
    $n = 0
    [void][int]::TryParse($o, [ref]$n)
    return $n
}

# ---------- safety rules ----------
$BlockedNames = @(
    '(^|/)\.env($|\.(?!example|sample))',
    '\.pem$', '\.key$', '\.pfx$', '\.p12$',
    '(^|/)(MOHS2|renders|frames|Output)/',
    '\.zipmod$', '\.unity3d$', '\.cube$', '\.resource$',
    '\.mp4$', '\.webm$', '\.mov$', '\.avi$', '\.wav$',
    '\.safetensors$', '\.gguf$', '\.ckpt$', '\.pt$',
    '\.sqlite3?$', '\.db$',
    '\.zip$', '\.7z$', '\.rar$', '\.bin$',
    '(^|/)node_modules/',
    '(^|/)(bin|obj)/',
    '(^|/)\.next'
)

$SecretPatterns = @(
    'BEGIN [A-Z ]*PRIVATE KEY',
    '[0-9]{8,10}:[A-Za-z0-9_-]{35}',
    'sk[-_](live|proj|ant)[A-Za-z0-9_-]{10,}',
    '(?i)(service_role|secret|passw(or)?d|api[_-]?key|token)[A-Za-z_]*\s*[:=]\s*[''"](?!(?-i:[A-Z0-9_]+)[''"])[A-Za-z0-9_\-\.]{16,}[''"]'
)

# ---------- one sync pass ----------
function Sync-Once {
    $mutex = New-Object System.Threading.Mutex($false, "Global\agaiani-github-sync")
    if (-not $mutex.WaitOne(0)) { Write-Log "Another sync is running, skipped."; return }
    try {
        Set-Location -LiteralPath $RepoPath
        if (-not (Test-Path ".git")) { Write-Log "ERROR: $RepoPath is not a git repository."; return }
        if ((Test-Path ".git\rebase-merge") -or (Test-Path ".git\rebase-apply") -or (Test-Path ".git\MERGE_HEAD")) {
            Write-Log "A rebase/merge is in progress. Resolve it manually, sync skipped."
            return
        }

        $st = Invoke-Git status --porcelain
        if ($st.Out.Trim()) {
            Invoke-Git add -A | Out-Null

            $names = (Invoke-Git diff --cached --name-only --diff-filter=ACMR).Out -split "`n" |
                Where-Object { $_ -and ($_ -notmatch '^warning:') }

            $problems = @()
            foreach ($n in $names) {
                foreach ($p in $BlockedNames) {
                    if ($n -match $p) { $problems += "blocked file name: $n"; break }
                }
                if (Test-Path -LiteralPath $n) {
                    $len = (Get-Item -LiteralPath $n -Force).Length
                    if ($len -gt ($MaxFileMB * 1MB)) {
                        $problems += ("file too big ({0} MB): {1}" -f [math]::Round($len / 1MB), $n)
                    }
                }
            }

            if (-not $problems) {
                $diff = (Invoke-Git diff --cached -U0 --no-color).Out -split "`n"
                $cur = ""
                foreach ($l in $diff) {
                    if ($l.StartsWith("+++ ")) { $cur = $l.Substring(4); continue }
                    if ($l.StartsWith("+")) {
                        foreach ($rx in $SecretPatterns) {
                            if ($l -match $rx) { $problems += "possible secret in: $cur"; break }
                        }
                    }
                }
            }

            if ($problems) {
                Invoke-Git reset | Out-Null
                Write-Log "SYNC BLOCKED, nothing was committed. Fix the items below (add to .gitignore or remove the secret):"
                $problems | Select-Object -Unique | ForEach-Object { Write-Log ("  - " + $_) }
                return
            }

            $q = Invoke-Git diff --cached --quiet
            if ($q.Code -ne 0) {
                $msg = "auto: " + (Get-Date -Format "yyyy-MM-dd HH:mm")
                $c = Invoke-Git commit --no-verify -m $msg
                if ($c.Code -ne 0) { Write-Log ("Commit failed: " + $c.Out); return }
                Write-Log "Committed: $msg"
            }
        }

        $f = Invoke-Git fetch origin $Branch
        if ($f.Code -ne 0) { Write-Log ("Fetch failed (offline or no access?): " + $f.Out); return }

        $behind = Get-Count "HEAD..origin/$Branch"
        if ($behind -gt 0) {
            $r = Invoke-Git pull --rebase origin $Branch
            if ($r.Code -ne 0) {
                Invoke-Git rebase --abort | Out-Null
                Write-Log ("Rebase conflict, aborted. Resolve manually: " + $r.Out)
                return
            }
            Write-Log "Rebased onto origin/$Branch ($behind new commit(s) from GitHub)."
        }

        $ahead = Get-Count "origin/$Branch..HEAD"
        if ($ahead -gt 0) {
            $p = Invoke-Git push origin $Branch
            if ($p.Code -ne 0) { Write-Log ("Push failed: " + $p.Out); return }
            Write-Log "Pushed $ahead commit(s) to origin/$Branch."
        }
    }
    finally {
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
}

# ---------- entry point ----------
if ($Watch) {
    Write-Log "Watch mode started for $RepoPath (debounce ${DebounceSeconds}s, fallback ${FallbackMinutes} min)."
    $w = New-Object System.IO.FileSystemWatcher $RepoPath
    $w.IncludeSubdirectories = $true
    $w.NotifyFilter = [System.IO.NotifyFilters]'FileName, DirectoryName, LastWrite, Size'
    $ignore = '^(\.git|MOHS2|renders|frames|Output|bin|obj|__pycache__|\.pytest_cache|logs|tmp)(\\|$)'
    $dirty = $false
    $last = Get-Date
    $lastRun = Get-Date
    Sync-Once
    while ($true) {
        $r = $w.WaitForChanged([System.IO.WatcherChangeTypes]::All, 5000)
        if ((-not $r.TimedOut) -and ($r.Name -notmatch $ignore)) { $dirty = $true; $last = Get-Date }
        $now = Get-Date
        if (($dirty -and (($now - $last).TotalSeconds -ge $DebounceSeconds)) -or
            (($now - $lastRun).TotalMinutes -ge $FallbackMinutes)) {
            $dirty = $false
            $lastRun = $now
            Sync-Once
        }
    }
}
else {
    Sync-Once
}
