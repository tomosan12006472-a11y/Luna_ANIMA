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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=%PORT%; $repo=(Resolve-Path '.').Path; $targetPids=@(); $targetPids += Get-CimInstance Win32_Process | Where-Object { (($_.CommandLine -and $_.CommandLine.Contains($repo)) -or ($_.ExecutablePath -and $_.ExecutablePath.Contains($repo))) -and $_.CommandLine -match ('--port\s+' + $port) } | ForEach-Object { $_.ProcessId }; $targetPids += Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -in @('0.0.0.0','::','127.0.0.1','::1') } | ForEach-Object { $_.OwningProcess }; $targetPids = $targetPids | Where-Object { $_ } | Select-Object -Unique; foreach ($targetPid in $targetPids) { try { Stop-Process -Id $targetPid -Force -ErrorAction Stop } catch {} }; if ($targetPids.Count -gt 0) { Start-Sleep -Milliseconds 800 }"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" -m uvicorn app.main:app --host %HOST% --port %PORT%
