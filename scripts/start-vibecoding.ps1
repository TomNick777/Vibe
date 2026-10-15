param([ValidateSet('run','doctor','scan','init')][string]$Action = 'run')
$ErrorActionPreference = 'Stop'
# Compatibility entry point retained for existing shortcuts and commands.
& (Join-Path $PSScriptRoot 'start-vibe.ps1') -Action $Action
