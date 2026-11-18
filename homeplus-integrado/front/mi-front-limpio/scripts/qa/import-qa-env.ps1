[CmdletBinding()]
param(
  [switch]$RequireAuth,
  [switch]$RequireInvalidPassword,
  [switch]$RequireMultiUser,
  [switch]$RequireFixtures
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $projectRoot)
$candidatePaths = @(
  $env:HOMEPLUS_QA_ENV_FILE,
  (Join-Path $repositoryRoot '.env.qa'),
  (Join-Path $projectRoot '.env.qa')
) | Where-Object { $_ }

foreach ($candidate in $candidatePaths) {
  if (-not (Test-Path -LiteralPath $candidate)) { continue }
  foreach ($line in Get-Content -LiteralPath $candidate) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
    $parts = $trimmed -split '=', 2
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
      [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
  }
  break
}

$required = @()
if ($RequireAuth) { $required += 'QA_A_EMAIL', 'QA_A_PASSWORD' }
if ($RequireInvalidPassword) { $required += 'QA_INVALID_PASSWORD' }
if ($RequireMultiUser) { $required += 'QA_B_EMAIL', 'QA_B_PASSWORD', 'QA_C_EMAIL', 'QA_C_PASSWORD' }
if ($RequireFixtures) { $required += 'QA_FIXTURES_ENABLED', 'QA_ENVIRONMENT', 'QA_SUPABASE_URL' }

$missing = $required | Where-Object { -not [Environment]::GetEnvironmentVariable($_, 'Process') }
if ($missing.Count -gt 0) {
  throw "Missing QA configuration: $($missing -join ', '). Copy .env.qa.example to .env.qa or inject the variables in CI."
}
if ($RequireFixtures -and -not [Environment]::GetEnvironmentVariable('QA_SUPABASE_SECRET_KEY', 'Process') -and -not [Environment]::GetEnvironmentVariable('QA_SUPABASE_SERVICE_ROLE_KEY', 'Process')) {
  throw 'Missing QA admin configuration: QA_SUPABASE_SECRET_KEY or QA_SUPABASE_SERVICE_ROLE_KEY.'
}
