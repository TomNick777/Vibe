$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskRuntime = Join-Path $taskRoot '.tools/msys64/ucrt64/bin'
$taskSource = Join-Path $taskRoot 'external/UxPlay'
$taskBuild = Join-Path $taskRoot '.tools/uxplay-build'
$taskCmake = Join-Path $taskRuntime 'cmake.exe'
if (-not (Test-Path -LiteralPath $taskCmake)) { throw 'Install the MSYS2 UCRT64 UxPlay dependencies first.' }
if (-not (Test-Path -LiteralPath (Join-Path $taskSource 'CMakeLists.txt'))) { throw 'Clone FDH2/UxPlay into external/UxPlay first.' }
$env:PATH = $taskRuntime + ';' + $env:PATH
& $taskCmake -S $taskSource -B $taskBuild -G Ninja -DCMAKE_BUILD_TYPE=Release -DNO_MARCH_NATIVE=ON
if ($LASTEXITCODE -ne 0) { throw 'UxPlay configuration failed.' }
& $taskCmake --build $taskBuild --parallel 4
if ($LASTEXITCODE -ne 0) { throw 'UxPlay build failed.' }
Copy-Item -LiteralPath (Join-Path $taskBuild 'uxplay.exe') -Destination (Join-Path $taskRuntime 'uxplay.exe')
& (Join-Path $taskRuntime 'uxplay.exe') -h
if ($LASTEXITCODE -ne 0) { throw 'UxPlay startup check failed.' }
