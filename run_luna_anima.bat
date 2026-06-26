@echo off
setlocal
cd /d "%~dp0"
set "PORT=51031"
if "%LUNA_ANIMA_HOST%"=="" (
  set "HOST=127.0.0.1"
) else (
  set "HOST=%LUNA_ANIMA_HOST%"
)
set "LUNA_ANIMA_HOST=%HOST%"
if exist "user_data\comfyui_restart_env.bat" (
  call "user_data\comfyui_restart_env.bat"
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=%PORT%; $repo=(Resolve-Path '.').Path; function Test-LunaProcess { param($proc) if (-not $proc) { return $false }; $cmd=[string]$proc.CommandLine; $exe=[string]$proc.ExecutablePath; if (-not $cmd) { return $false }; $underRepo=($cmd.Contains($repo) -or ($exe -and $exe.Contains($repo))); $hasApp=($cmd -match 'uvicorn' -and $cmd -match 'app\.main:app'); $hasPort=($cmd -match ('--port\s+' + [regex]::Escape([string]$port))); return ($underRepo -and $hasApp -and $hasPort) }; $targetPids=@(); $targetPids += Get-CimInstance Win32_Process | Where-Object { Test-LunaProcess $_ } | ForEach-Object { $_.ProcessId }; $listenerPids = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -in @('0.0.0.0','::','127.0.0.1','::1') } | ForEach-Object { $_.OwningProcess }; foreach ($listenerPid in ($listenerPids | Where-Object { $_ } | Select-Object -Unique)) { $proc=Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$listenerPid) -ErrorAction SilentlyContinue; if (Test-LunaProcess $proc) { $targetPids += $listenerPid } else { Write-Host ('Luna ANIMA: skip non-matching listener PID ' + $listenerPid + ' on port ' + $port) } }; $targetPids = $targetPids | Where-Object { $_ } | Select-Object -Unique; foreach ($targetPid in $targetPids) { try { Stop-Process -Id $targetPid -Force -ErrorAction Stop } catch {} }; if ($targetPids.Count -gt 0) { Start-Sleep -Milliseconds 800 }"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" -m uvicorn app.main:app --host %HOST% --port %PORT%
