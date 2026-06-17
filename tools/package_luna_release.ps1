param(
  [string]$AnimaRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$SdxlRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\SAA_claude')).Path,
  [string]$OutDir = (Join-Path (Split-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path -Parent) 'luna_dist')
)

$ErrorActionPreference = 'Stop'

function Copy-LunaPackage {
  param(
    [string]$SourceRoot,
    [string]$StageRoot,
    [string]$RunScript
  )

  New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
  foreach ($name in @('app', 'config')) {
    Copy-Item -LiteralPath (Join-Path $SourceRoot $name) -Destination (Join-Path $StageRoot $name) -Recurse -Force
  }
  foreach ($name in @(
    'requirements.txt',
    'README.md',
    'SETUP_FOR_AI_AGENT.md',
    'LUNA_DISTRIBUTION_TERMS.md',
    'THIRD_PARTY_NOTICES.md',
    'release_manifest.json',
    'setup_venv.bat',
    $RunScript
  )) {
    Copy-Item -LiteralPath (Join-Path $SourceRoot $name) -Destination (Join-Path $StageRoot $name) -Force
  }
  $userData = Join-Path $StageRoot 'user_data'
  New-Item -ItemType Directory -Force -Path $userData | Out-Null
  Set-Content -LiteralPath (Join-Path $userData '.gitkeep') -Value '' -Encoding ascii
  Get-ChildItem -LiteralPath $StageRoot -Recurse -Directory -Force |
    Where-Object { $_.Name -in @('__pycache__', '.pytest_cache') } |
    Remove-Item -Recurse -Force
  Get-ChildItem -LiteralPath $StageRoot -Recurse -File -Force |
    Where-Object { $_.Extension -in @('.pyc', '.pyo', '.log') } |
    Remove-Item -Force
}

function New-LunaZip {
  param(
    [string]$StageRoot,
    [string]$ZipPath
  )
  if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
  }
  Compress-Archive -Path (Join-Path $StageRoot '*') -DestinationPath $ZipPath -Force
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "luna-release-$stamp"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$dist = (Resolve-Path -LiteralPath $OutDir).Path

try {
  New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

  $animaStage = Join-Path $tempRoot 'Luna_ANIMA'
  $sdxlStage = Join-Path $tempRoot 'Luna_SDXL'
  $suiteStage = Join-Path $tempRoot 'Luna_Image_Tools'

  Copy-LunaPackage -SourceRoot $AnimaRoot -StageRoot $animaStage -RunScript 'run_luna_anima.bat'
  Copy-LunaPackage -SourceRoot $SdxlRoot -StageRoot $sdxlStage -RunScript 'run_luna_sdxl.bat'

  New-Item -ItemType Directory -Force -Path $suiteStage | Out-Null
  Copy-Item -LiteralPath $animaStage -Destination (Join-Path $suiteStage 'Luna_ANIMA') -Recurse -Force
  Copy-Item -LiteralPath $sdxlStage -Destination (Join-Path $suiteStage 'Luna_SDXL') -Recurse -Force
  Set-Content -LiteralPath (Join-Path $suiteStage 'README_ja.md') -Encoding utf8 -Value @'
# Luna Image Tools

This bundle contains:

- Luna ANIMA
- Luna SDXL

Run `setup_venv.bat` inside each app folder, then launch each app with its `run_luna_*.bat` file.

Default local URLs:

- Luna ANIMA: http://127.0.0.1:51031/
- Luna SDXL: http://127.0.0.1:51032/

Redistribution and program modification are prohibited. See each app folder for the detailed terms.
'@

  $animaZip = Join-Path $dist "Luna_ANIMA_$stamp.zip"
  $sdxlZip = Join-Path $dist "Luna_SDXL_$stamp.zip"
  $suiteZip = Join-Path $dist "Luna_Image_Tools_$stamp.zip"

  New-LunaZip -StageRoot $animaStage -ZipPath $animaZip
  New-LunaZip -StageRoot $sdxlStage -ZipPath $sdxlZip
  New-LunaZip -StageRoot $suiteStage -ZipPath $suiteZip

  $checksumPath = Join-Path $dist "checksums_$stamp.txt"
  Get-FileHash -Algorithm SHA256 $animaZip, $sdxlZip, $suiteZip |
    ForEach-Object { "$($_.Hash)  $(Split-Path $_.Path -Leaf)" } |
    Set-Content -LiteralPath $checksumPath -Encoding ascii

  [pscustomobject]@{
    ok = $true
    out_dir = $dist
    anima_zip = $animaZip
    sdxl_zip = $sdxlZip
    suite_zip = $suiteZip
    checksums = $checksumPath
  } | ConvertTo-Json -Compress
}
finally {
  if (Test-Path -LiteralPath $tempRoot) {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
  }
}
