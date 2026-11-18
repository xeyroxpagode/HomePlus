[CmdletBinding()]
param([string]$AppId)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'maestro-bootstrap.ps1') -RequireMultiUser
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'maestro-preflight.ps1') -AppId $AppId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$adb = (Get-Command adb -ErrorAction SilentlyContinue).Source
$devices = @(& $adb devices -l | Select-String -Pattern '^\S+\s+device(?:\s|$)' | ForEach-Object { ($_.Line -split '\s+')[0] })
if ($devices.Count -lt 2) {
  Write-Host 'MULTI_DEVICE_READY - NEEDS_RUNTIME_QA (no hay un segundo device disponible).'
  exit 2
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $AppId) { $AppId = ((Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'app.json') | ConvertFrom-Json).expo.android.package) }
$maestro = (Get-Command maestro -ErrorAction SilentlyContinue).Source
if (-not $maestro) { $maestro = 'C:\Tools\Maestro\maestro\bin\maestro.bat' }
$runMessage = "QA E2E $([guid]::NewGuid().ToString('N'))"

& $maestro test --device $devices[0] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "QA_RUN_MESSAGE=$runMessage" (Join-Path $projectRoot '.maestro\multi\login-a.yaml')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $maestro test --device $devices[1] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "QA_RUN_MESSAGE=$runMessage" (Join-Path $projectRoot '.maestro\multi\login-b.yaml')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $maestro test --device $devices[0] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "QA_RUN_MESSAGE=$runMessage" (Join-Path $projectRoot '.maestro\multi\message-send-a.yaml')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $maestro test --device $devices[1] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "QA_RUN_MESSAGE=$runMessage" (Join-Path $projectRoot '.maestro\multi\message-receive-b.yaml')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $maestro test --device $devices[0] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" (Join-Path $projectRoot '.maestro\multi\task-share-a.yaml')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($devices.Count -ge 3) {
  & $maestro test --device $devices[2] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" -e "QA_RUN_MESSAGE=$runMessage" (Join-Path $projectRoot '.maestro\multi\login-c.yaml')
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  # Backend concurrency remains the authority. These independent device jobs
  # exercise the UX/runtime convergence of two near-simultaneous claims.
  $claimB = Start-Job -ScriptBlock {
    param($maestroPath, $device, $applicationId, $flow)
    & $maestroPath test --device $device -e "HOMEPLUS_ANDROID_APP_ID=$applicationId" $flow
    exit $LASTEXITCODE
  } -ArgumentList $maestro, $devices[1], $AppId, (Join-Path $projectRoot '.maestro\multi\task-claim-b.yaml')
  $claimC = Start-Job -ScriptBlock {
    param($maestroPath, $device, $applicationId, $flow)
    & $maestroPath test --device $device -e "HOMEPLUS_ANDROID_APP_ID=$applicationId" $flow
    exit $LASTEXITCODE
  } -ArgumentList $maestro, $devices[2], $AppId, (Join-Path $projectRoot '.maestro\multi\task-claim-c.yaml')
  Wait-Job -Job $claimB, $claimC | Out-Null
  Receive-Job -Job $claimB, $claimC | Write-Host
  if ($claimB.State -ne 'Completed' -or $claimC.State -ne 'Completed' -or $claimB.ChildJobs[0].JobStateInfo.State -ne 'Completed' -or $claimC.ChildJobs[0].JobStateInfo.State -ne 'Completed') {
    throw 'One of the multi-device claim flows failed.'
  }
} else {
  & $maestro test --device $devices[1] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" (Join-Path $projectRoot '.maestro\multi\task-claim-b.yaml')
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $maestro test --device $devices[0] -e "HOMEPLUS_ANDROID_APP_ID=$AppId" (Join-Path $projectRoot '.maestro\multi\task-observe-a.yaml')
exit $LASTEXITCODE
