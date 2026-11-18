[CmdletBinding()]
param([switch]$RequireMultiUser)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $projectRoot)

# Creates the ignored local QA template on first use, then provisions only the
# dedicated QA accounts through the server-side Supabase Admin API.
& node (Join-Path $repositoryRoot 'scripts\qa\provision-e2e-credentials.js')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
. (Join-Path $PSScriptRoot 'import-qa-env.ps1') -RequireAuth -RequireInvalidPassword -RequireFixtures -RequireMultiUser:$RequireMultiUser
& node (Join-Path $repositoryRoot 'scripts\qa\setup-e2e-fixtures.js')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
