param([ValidateSet('run','doctor','scan','init')][string]$Action = 'run')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'windows_bridge/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create windows_bridge/.venv and install windows_bridge[dev] first.'
}
& $taskPython -m m5vibe $Action
if ($LASTEXITCODE -ne 0) { throw "Vibe Bridge $Action failed ($LASTEXITCODE)." }
