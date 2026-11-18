[CmdletBinding()]
param(
  [string]$AppId
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Fail([string]$message) {
  Write-Error "[QA preflight] $message"
  exit 1
}

function Resolve-Executable([string]$name, [string[]]$fallbacks) {
  $found = Get-Command $name -ErrorAction SilentlyContinue
  if ($found) { return $found.Source }
  foreach ($candidate in $fallbacks) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
  }
  return $null
}

if (-not $AppId) {
  $config = Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'app.json') | ConvertFrom-Json
  $AppId = $config.expo.android.package
}
if (-not $AppId) { Fail 'No se pudo resolver expo.android.package desde app.json.' }

$java = Resolve-Executable 'java' @()
if (-not $java) { Fail 'Java 17+ no está disponible en PATH.' }
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$javaVersion = (& $java -version 2>&1 | Select-Object -First 1)
$ErrorActionPreference = $previousErrorActionPreference
if ($javaVersion -notmatch 'version "(1[7-9]|[2-9][0-9])') { Fail "Java 17+ es obligatorio. Detectado: $javaVersion" }

$sdkRoots = @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME, 'C:\Android\Sdk', "$env:LOCALAPPDATA\Android\Sdk") | Where-Object { $_ }
$adbFallbacks = $sdkRoots | ForEach-Object { Join-Path $_ 'platform-tools\adb.exe' }
$adb = Resolve-Executable 'adb' $adbFallbacks
if (-not $adb) { Fail 'adb no está disponible. Agregá Android SDK platform-tools al PATH de usuario.' }

$maestro = Resolve-Executable 'maestro' @('C:\Tools\Maestro\maestro\bin\maestro.bat')
if (-not $maestro) { Fail 'Maestro CLI no está disponible. Abrí una terminal nueva o instalalo según docs/QA_MAESTRO.md.' }

try { $maestroVersion = (& $maestro --version 2>&1 | Select-Object -Last 1).ToString().Trim() } catch { Fail "Maestro no pudo ejecutarse: $($_.Exception.Message)" }
try {
  # `adb devices` starts its daemon on first use and writes that normal startup
  # notice to stderr.  Do not treat the notice as a failing Maestro preflight.
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  $null = & $adb start-server 2>&1
  $devices = & $adb devices -l 2>&1
  $adbDevicesExitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference
  if ($adbDevicesExitCode -ne 0) { Fail 'adb no pudo listar los dispositivos disponibles.' }
} catch { Fail "adb no pudo ejecutarse: $($_.Exception.Message)" }
$adbVersion = (& $adb version 2>&1 | Select-Object -First 2 | Select-Object -Last 1)

Write-Host "Java: $javaVersion"
Write-Host "ADB: $adbVersion"
Write-Host "Maestro: $maestroVersion"
Write-Host "Android package: $AppId"

$onlineDevices = @($devices | Select-String -Pattern '^\S+\s+device(?:\s|$)')
if ($onlineDevices.Count -eq 0) {
  Write-Host ($devices -join [Environment]::NewLine)
  Fail 'No hay Android device/emulator en estado device. Iniciá el AVD y repetí el preflight.'
}

Write-Host "Devices:"; $onlineDevices | ForEach-Object { Write-Host "  $($_.Line)" }

$missingPackage = $false
foreach ($deviceMatch in $onlineDevices) {
  $serial = ($deviceMatch.Line -split '\s+')[0]
  $packagePath = & $adb -s $serial shell pm path $AppId 2>$null
  if ($LASTEXITCODE -ne 0 -or -not ($packagePath -match '^package:')) {
    Write-Warning "HomePlus no está instalado en $serial ($AppId)."
    $missingPackage = $true
  } else {
    Write-Host "HomePlus instalado en ${serial}: $packagePath"
  }
}
if ($missingPackage) { Fail 'Instalá un development build de HomePlus antes de ejecutar Maestro.' }

Write-Host '[QA preflight] PASS'
