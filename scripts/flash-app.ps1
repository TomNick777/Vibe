param(
    [Parameter(Mandatory = $true)][string]$Port,
    [Parameter(Mandatory = $true)][string]$Backup
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskImage = Join-Path $taskRoot 'build/StopWatch-UserDemo.bin'
$taskPartition = Join-Path $taskRoot 'build/partition_table/partition-table.bin'
& uv run --python 3.12 python (Join-Path $PSScriptRoot 'check-flash-backup.py') $Backup $taskImage $taskPartition
if ($LASTEXITCODE -ne 0) { throw 'Backup/partition validation failed; nothing was flashed.' }
& uv run --python 3.12 --with esptool==5.5.0 python -m esptool --chip esp32s3 --port $Port --baud 460800 --after hard-reset write-flash 0x20000 $taskImage
if ($LASTEXITCODE -ne 0) { throw 'App-only flash failed. Preserve the backup for recovery.' }
