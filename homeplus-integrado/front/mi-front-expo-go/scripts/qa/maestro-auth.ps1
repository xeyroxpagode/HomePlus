[CmdletBinding()]
param([string]$AppId)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'maestro-bootstrap.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'maestro-preflight.ps1') -AppId $AppId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
. (Join-Path $PSScriptRoot 'maestro-runtime.ps1') -AppId $AppId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $AppId) { $AppId = ((Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'app.json') | ConvertFrom-Json).expo.android.package) }
$maestro = (Get-Command maestro -ErrorAction SilentlyContinue).Source
if (-not $maestro) { $maestro = 'C:\Tools\Maestro\maestro\bin\maestro.bat' }

Get-ChildItem -LiteralPath (Join-Path $projectRoot '.maestro\auth') -File -Filter '*.yaml' |
  Sort-Object FullName |
  ForEach-Object {
    Write-Host "[QA] Ejecutando $($_.FullName)"
    & $maestro test -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "HOMEPLUS_DEV_BUNDLE_URL=$env:HOMEPLUS_DEV_BUNDLE_URL" -e "QA_A_EMAIL=$env:QA_A_EMAIL" -e "QA_A_PASSWORD=$env:QA_A_PASSWORD" -e "QA_INVALID_PASSWORD=$env:QA_INVALID_PASSWORD" $_.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }

Write-Host '[QA] Auth Maestro flows passed.'
