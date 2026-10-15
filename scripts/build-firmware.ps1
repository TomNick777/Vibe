param([ValidateSet('build', 'size', 'menuconfig', 'reconfigure')][string]$Action = 'build')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:IDF_TOOLS_PATH = Join-Path $taskRoot '.tools/espressif'
$taskExport = Join-Path $taskRoot '.tools/esp-idf/export.ps1'
if (-not (Test-Path -LiteralPath $taskExport)) { throw 'Install ESP-IDF v5.5.4 in .tools/esp-idf first.' }
. $taskExport
Push-Location $taskRoot
try {
    & python (Join-Path $taskRoot '.tools/esp-idf/tools/idf.py') $Action
    if ($LASTEXITCODE -ne 0) { throw "Firmware $Action failed ($LASTEXITCODE)." }
} finally { Pop-Location }
