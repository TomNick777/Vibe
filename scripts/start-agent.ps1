param([string]$UxPlayPath = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskServer = Join-Path $taskRoot 'server'
$taskPython = Join-Path $taskServer '.venv/Scripts/python.exe'
$taskEnvFile = Join-Path $taskServer '.env'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Install server dependencies into server/.venv first.' }
if (Test-Path -LiteralPath $taskEnvFile) {
    # Load simple dotenv assignments without executing arbitrary shell text.
    foreach ($taskLine in Get-Content -LiteralPath $taskEnvFile) {
        if ($taskLine -match '^\s*([A-Z_][A-Z_0-9]*)\s*=\s*(.*?)\s*$') {
            $taskKey = $Matches[1]
            $taskValue = $Matches[2]
            if ($taskValue -match '^(["''])(.*)\1$') { $taskValue = $Matches[2] }
            else { $taskValue = ($taskValue -replace '\s+#.*$', '').Trim() }
            [Environment]::SetEnvironmentVariable($taskKey, $taskValue, 'Process')
        }
    }
}
if ($UxPlayPath) { $env:UXPLAY_BINARY = $UxPlayPath }
elseif (-not $env:UXPLAY_BINARY) { $env:UXPLAY_BINARY = Join-Path $taskRoot '.tools/msys64/ucrt64/bin/uxplay.exe' }
if (-not (Test-Path -LiteralPath $env:UXPLAY_BINARY)) { throw "UxPlay not found: $env:UXPLAY_BINARY" }
$env:PATH = (Split-Path -Parent $env:UXPLAY_BINARY) + ';' + $env:PATH
$env:HIDAGENT_DATA = Join-Path $taskServer '.hidagent'
Push-Location $taskServer
try { & $taskPython -m hidagent } finally { Pop-Location }
