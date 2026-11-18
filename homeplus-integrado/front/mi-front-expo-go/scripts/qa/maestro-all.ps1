[CmdletBinding()]
param(
  [string]$AppId
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
& (Join-Path $PSScriptRoot 'maestro-bootstrap.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'maestro-preflight.ps1') -AppId $AppId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
. (Join-Path $PSScriptRoot 'maestro-runtime.ps1') -AppId $AppId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $AppId) {
  $AppId = ((Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'app.json') | ConvertFrom-Json).expo.android.package)
}
$maestro = (Get-Command maestro -ErrorAction SilentlyContinue).Source
if (-not $maestro) { $maestro = 'C:\Tools\Maestro\maestro\bin\maestro.bat' }
$flows = @()
foreach ($suite in @('smoke', 'auth', 'navigation', 'messaging')) {
  $suitePath = Join-Path $projectRoot ".maestro\\$suite"
  if (Test-Path -LiteralPath $suitePath) {
    $flows += Get-ChildItem -LiteralPath $suitePath -Recurse -File -Filter '*.yaml' | Sort-Object FullName
  }
}
if ($flows.Count -eq 0) { Write-Error '[QA] No se encontraron flows Maestro.'; exit 1 }

foreach ($flow in $flows) {
  Write-Host "[QA] Ejecutando $($flow.FullName)"
  & $maestro test -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "HOMEPLUS_DEV_BUNDLE_URL=$env:HOMEPLUS_DEV_BUNDLE_URL" -e "QA_A_EMAIL=$env:QA_A_EMAIL" -e "QA_A_PASSWORD=$env:QA_A_PASSWORD" -e "QA_INVALID_PASSWORD=$env:QA_INVALID_PASSWORD" $flow.FullName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host '[QA] All Maestro flows passed.'
exit 0
