[CmdletBinding()]
param([string]$AppId)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $projectRoot)
$adb = (Get-Command adb -ErrorAction SilentlyContinue).Source
if (-not $adb) { $adb = 'C:\Android\Sdk\platform-tools\adb.exe' }
if (-not (Test-Path $adb)) { throw 'adb is required to load the current Metro bundle.' }

$device = (& $adb devices | Select-String '^emulator-\S+\s+device' | Select-Object -First 1)
if (-not $device) { throw 'A running Android emulator is required for the Maestro development runtime.' }
$serial = ($device.Line -split '\s+')[0]

try {
  $null = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8081/status' -TimeoutSec 2
} catch {
  $stdout = Join-Path $projectRoot '.expo\maestro-metro.out.log'
  $stderr = Join-Path $projectRoot '.expo\maestro-metro.err.log'
  Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', 'npx expo start --dev-client --lan') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
  $deadline = (Get-Date).AddSeconds(30)
  do {
    Start-Sleep -Milliseconds 500
    try { $null = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8081/status' -TimeoutSec 2; break } catch {}
  } while ((Get-Date) -lt $deadline)
  if ((Get-Date) -ge $deadline) { throw 'Metro did not become ready on port 8081.' }
}

$bundleUrl = 'homeplus://expo-development-client/?url=http%3A%2F%2F10.0.2.2%3A8081'
& $adb -s $serial shell am start -W -a android.intent.action.VIEW -d $bundleUrl | Out-Null

# A freshly cleared Expo development client may show its one-time developer
# welcome overlay. Back dismisses that host UI without touching HomePlus state.
# Cold starts of the development client can take longer than a warm Metro
# reload.  Keep waiting on the observable readiness marker instead of adding
# fixed sleeps to individual flows.
$deadline = (Get-Date).AddSeconds(45)
do {
  Start-Sleep -Milliseconds 500
  $ui = & $adb -s $serial exec-out uiautomator dump /dev/tty 2>$null
  if ($ui -match 'auth.ready') { break }
  if ($ui -match 'This is the developer menu') { & $adb -s $serial shell input keyevent 4 | Out-Null }
} while ((Get-Date) -lt $deadline)
if ($ui -notmatch 'auth.ready') { throw 'Current HomePlus bundle did not expose auth.ready.' }

$env:HOMEPLUS_ANDROID_APP_ID = $AppId
$env:HOMEPLUS_DEV_BUNDLE_URL = $bundleUrl
Write-Host '[QA runtime] Current Metro bundle loaded on emulator.'
