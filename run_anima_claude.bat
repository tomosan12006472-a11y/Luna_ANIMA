@echo off
setlocal
cd /d "%~dp0"
set "PORT=51031"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=%PORT%; $repo=(Resolve-Path '.').Path; $targetPids=@(); $targetPids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($repo) -and $_.CommandLine -match ('--port\s+' + $port) } | ForEach-Object { $_.ProcessId }; $targetPids += Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::' } | ForEach-Object { $_.OwningProcess }; $targetPids = $targetPids | Where-Object { $_ } | Select-Object -Unique; foreach ($targetPid in $targetPids) { try { Stop-Process -Id $targetPid -Force -ErrorAction Stop } catch {} }; if ($targetPids.Count -gt 0) { Start-Sleep -Milliseconds 800 }"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
