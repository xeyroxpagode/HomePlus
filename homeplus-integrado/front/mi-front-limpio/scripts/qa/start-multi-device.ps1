[CmdletBinding()]
param([int]$MinimumDevices = 2)

$ErrorActionPreference = 'Stop'
$adb = (Get-Command adb -ErrorAction SilentlyContinue).Source
if (-not $adb) { throw 'adb no está disponible en PATH.' }

$online = @(& $adb devices -l | Select-String -Pattern '^\S+\s+device(?:\s|$)' | ForEach-Object { ($_.Line -split '\s+')[0] })
if ($online.Count -lt $MinimumDevices) {
  Write-Host "MULTI_DEVICE_READY - NEEDS_RUNTIME_QA (se requieren $MinimumDevices devices; disponibles: $($online.Count))."
  exit 2
}

Write-Host "MULTI_DEVICE_A=$($online[0])"
Write-Host "MULTI_DEVICE_B=$($online[1])"
if ($online.Count -ge 3) { Write-Host "MULTI_DEVICE_C=$($online[2])" }
exit 0
