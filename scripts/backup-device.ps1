param([string]$Port = 'COM3')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv to use the verified esptool v5.5.0 backup environment.' }
$taskBackupDir = Join-Path $taskRoot 'backups'
New-Item -ItemType Directory -Force -Path $taskBackupDir | Out-Null
$taskNow = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time'))
$taskName = $taskNow.ToString('yyyy-MM-dd-HHmmss') + '-original'
$taskImage = Join-Path $taskBackupDir ($taskName + '.bin')
if (Test-Path -LiteralPath $taskImage) { throw 'Backup already exists; refusing to overwrite it.' }
& uv run --with esptool==5.5.0 python -m esptool --chip esp32s3 --port $Port --baud 115200 --after hard-reset read-flash 0 ALL $taskImage
if ($LASTEXITCODE -ne 0) { throw "Device backup failed ($LASTEXITCODE)." }
$taskLength = (Get-Item -LiteralPath $taskImage).Length
if ($taskLength -ne 16777216) { throw "Expected 16 MB Flash, received $taskLength bytes. Check the device before flashing." }
$taskHash = (Get-FileHash -LiteralPath $taskImage -Algorithm SHA256).Hash
@{ file = $taskImage; bytes = $taskLength; sha256 = $taskHash; port = $Port; capturedAt = $taskNow.ToString('o') + '+08:00' } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackupDir ($taskName + '.json')) -Encoding utf8
Write-Output "Backup: $taskImage"
Write-Output "SHA256: $taskHash"
