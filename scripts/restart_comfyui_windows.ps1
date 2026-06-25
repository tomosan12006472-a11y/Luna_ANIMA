param(
  [Parameter(Mandatory = $true)]
  [string]$Config,

  [string]$StatusFile = ""
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Error $Message
  exit 1
}

function Emit([string]$Line) {
  Write-Output $Line
  if ($StatusFile) {
    $statusDir = Split-Path -Parent $StatusFile
    if ($statusDir) { New-Item -ItemType Directory -Force -Path $statusDir | Out-Null }
    Add-Content -LiteralPath $StatusFile -Value $Line -Encoding UTF8
  }
}

function FullPath([string]$PathText) {
  return [System.IO.Path]::GetFullPath($PathText)
}

function NormalizePath([string]$PathText) {
  return (FullPath $PathText).TrimEnd("\").ToLowerInvariant()
}

function IsUnderRoot([string]$Child, [string]$Root) {
  $childPath = NormalizePath $Child
  $rootPath = NormalizePath $Root
  return $childPath -eq $rootPath -or $childPath.StartsWith($rootPath + "\")
}

function Get-ListenerPids([int]$Port) {
  try {
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
      Where-Object { $_.OwningProcess } |
      Select-Object -ExpandProperty OwningProcess -Unique
  } catch {
    @()
  }
}

function Get-ProcessInfo([int]$ProcessId) {
  Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function CommandLineContainsPath([string]$CommandLine, [string]$PathText) {
  if (-not $CommandLine -or -not $PathText) { return $false }
  $needle = (NormalizePath $PathText).Replace("/", "\")
  $haystack = $CommandLine.ToLowerInvariant().Replace("/", "\")
  return $haystack.Contains($needle)
}

function Is-VerifiedComfyProcess($Proc, $ConfigData) {
  if (-not $Proc) { return $false }
  if ([int]$Proc.ProcessId -eq [int]$PID) { return $false }

  $cmd = [string]($Proc.CommandLine)
  $exe = [string]($Proc.ExecutablePath)
  $root = FullPath ([string]$ConfigData.comfyui_root)
  $mainScript = FullPath ([string]$ConfigData.main_script)
  $python = FullPath ([string]$ConfigData.python_executable)

  if (-not $cmd) { return $false }
  if (-not (CommandLineContainsPath $cmd $mainScript)) { return $false }
  if (-not (CommandLineContainsPath $cmd $root)) { return $false }
  if ($exe -and -not (IsUnderRoot $mainScript $root)) { return $false }

  if ($exe -and ((NormalizePath $exe) -eq (NormalizePath $python))) { return $true }
  if (CommandLineContainsPath $cmd $python) { return $true }

  $parent = Get-ProcessInfo ([int]$Proc.ParentProcessId)
  if ($parent) {
    $parentExe = [string]($parent.ExecutablePath)
    $parentCmd = [string]($parent.CommandLine)
    if ($parentExe -and ((NormalizePath $parentExe) -eq (NormalizePath $python))) { return $true }
    if (CommandLineContainsPath $parentCmd $python) { return $true }
  }

  return $false
}

function Wait-ForPortClosed([int]$Port, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $pids = @(Get-ListenerPids $Port)
    if ($pids.Count -eq 0) { return $true }
    Start-Sleep -Milliseconds 300
  }
  return $false
}

function Wait-ForProcessExit([int]$ProcessId, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
    Start-Sleep -Milliseconds 300
  }
  return $false
}

function Quote-Arg([string]$Arg) {
  if ($null -eq $Arg) { return '""' }
  if ($Arg -notmatch '[\s"]') { return $Arg }
  $escaped = $Arg -replace '(\\*)"', '$1$1\"'
  $escaped = $escaped -replace '(\\+)$', '$1$1'
  return '"' + $escaped + '"'
}

if (-not (Test-Path -LiteralPath $Config)) {
  Fail "restart config not found"
}

$configData = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $configData.enabled) {
  Fail "restart config is disabled"
}
if ([string]$configData.mode -ne "windows_wrapper") {
  Fail "unsupported restart config mode"
}

$comfyRoot = FullPath ([string]$configData.comfyui_root)
$python = FullPath ([string]$configData.python_executable)
$mainScript = FullPath ([string]$configData.main_script)
$cwd = FullPath ([string]$configData.cwd)
$port = [int]$configData.port
$stopTimeout = 15
if ($configData.stop_timeout_seconds) { $stopTimeout = [int]$configData.stop_timeout_seconds }
$logDir = FullPath ([string]$configData.log_dir)
$args = @($configData.args | ForEach-Object { [string]$_ })

if (-not (Test-Path -LiteralPath $comfyRoot -PathType Container)) { Fail "comfyui_root does not exist" }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { Fail "python_executable does not exist" }
if (-not (Test-Path -LiteralPath $mainScript -PathType Leaf)) { Fail "main_script does not exist" }
if (-not (Test-Path -LiteralPath $cwd -PathType Container)) { Fail "cwd does not exist" }
if (-not (IsUnderRoot $mainScript $comfyRoot)) { Fail "main_script is outside comfyui_root" }
if (-not (IsUnderRoot $cwd $comfyRoot)) { Fail "cwd is outside comfyui_root" }
if ($args.Count -eq 0) { Fail "args is empty" }

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $logDir "comfyui_restart_$stamp.out.log"
$stderrLog = Join-Path $logDir "comfyui_restart_$stamp.err.log"

$oldPid = $null
$listenerPids = @(Get-ListenerPids $port)
if ($listenerPids.Count -gt 0) {
  foreach ($candidatePid in $listenerPids) {
    $proc = Get-ProcessInfo ([int]$candidatePid)
    if (Is-VerifiedComfyProcess $proc $configData) {
      $oldPid = [int]$candidatePid
      break
    }
  }
  if (-not $oldPid) {
    Fail "listener process did not match configured ComfyUI"
  }
}

if ($oldPid) {
  Emit "old_pid=$oldPid"
  Emit "stage=stopping"
  & taskkill.exe /PID $oldPid /T | Out-Null
  if (-not (Wait-ForProcessExit $oldPid $stopTimeout)) {
    & taskkill.exe /PID $oldPid /T /F | Out-Null
    if (-not (Wait-ForProcessExit $oldPid $stopTimeout)) {
      Fail "old ComfyUI process did not stop"
    }
  }
  Emit "stage=port_closing"
  if (-not (Wait-ForPortClosed $port $stopTimeout)) {
    Fail "ComfyUI port did not close"
  }
}

Emit "stage=starting"
$argumentList = ($args | ForEach-Object { Quote-Arg $_ }) -join " "
$newProcess = Start-Process `
  -FilePath $python `
  -ArgumentList $argumentList `
  -WorkingDirectory $cwd `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru

if (-not $newProcess -or -not $newProcess.Id) {
  Fail "failed to start ComfyUI"
}

Emit "new_pid=$($newProcess.Id)"
Emit "log_available=true"
exit 0
