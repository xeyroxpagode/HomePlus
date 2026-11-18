[CmdletBinding()]
param([string]$Architectures = 'x86_64')

$ErrorActionPreference = 'Stop'
$frontend = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$repository = (Resolve-Path (Join-Path $frontend '../..')).Path
$socketDirectory = Join-Path $repository '.jtmp'
New-Item -ItemType Directory -Path $socketDirectory -Force | Out-Null
$previousJavaOptions = $env:JAVA_TOOL_OPTIONS
try {
  $env:JAVA_TOOL_OPTIONS = "$previousJavaOptions -Djdk.net.unixdomain.tmpdir=$socketDirectory".Trim()
  Push-Location (Join-Path $frontend 'android')
  try {
    & .\gradlew.bat :app:assembleDebug "-PreactNativeArchitectures=$Architectures" --no-daemon --console=plain
    if ($LASTEXITCODE -ne 0) { throw 'Android development build failed. See the Gradle output.' }
  } finally { Pop-Location }
} finally { $env:JAVA_TOOL_OPTIONS = $previousJavaOptions }
