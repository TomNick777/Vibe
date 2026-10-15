$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskDriverDir = Join-Path $taskRoot '.tools/vbcable'
$taskArchive = Join-Path $taskDriverDir 'VBCABLE_Driver_Pack45.zip'
New-Item -ItemType Directory -Force -Path $taskDriverDir | Out-Null
if (-not (Test-Path -LiteralPath $taskArchive)) {
    Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip' -OutFile $taskArchive
}
Expand-Archive -LiteralPath $taskArchive -DestinationPath $taskDriverDir -Force
$taskInstaller = Join-Path $taskDriverDir 'VBCABLE_Setup_x64.exe'
if (-not (Test-Path -LiteralPath $taskInstaller)) { throw 'Official archive does not contain the expected x64 setup.' }
$taskSignature = Get-AuthenticodeSignature -LiteralPath $taskInstaller
if ($taskSignature.Status -ne 'Valid' -or $taskSignature.SignerCertificate.Subject -notmatch '^CN=BUREL VINCENT Entrepreneur individuel,|VB-AUDIO') {
    throw 'VB-CABLE installer signature is not valid for the expected publisher.'
}
Write-Output "Installer: $taskInstaller"
Write-Output "Verified publisher: $($taskSignature.SignerCertificate.Subject)"
Write-Output "SHA256: $((Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash)"
Write-Output 'Run the official installer as administrator, complete its dialog, and restart Windows as requested by its vendor.'
Write-Output 'Then run scripts/start-vibecoding.ps1 doctor. This helper does not bundle or install the third-party driver.'
