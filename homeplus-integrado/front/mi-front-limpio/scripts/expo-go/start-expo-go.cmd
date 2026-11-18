@echo off
setlocal EnableExtensions

set "SOURCE=%~dp0..\.."
for %%I in ("%SOURCE%") do set "SOURCE=%%~fI"

rem Resolve aliases/junctions such as C:\HP before locating the sibling copy.
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$item = Get-Item -LiteralPath $env:SOURCE; if ($item.Target) { [System.IO.Path]::GetFullPath([string]$item.Target) } else { $item.FullName }"`) do set "SOURCE=%%I"

for %%I in ("%SOURCE%\..\mi-front-expo-go") do set "PROJECT=%%~fI"

if not exist "%PROJECT%\package.json" (
  echo ERROR: Expo Go workspace not found: %PROJECT%
  echo Run setup-expo-go-copy.cmd from the Maestro workspace first.
  exit /b 1
)

pushd "%PROJECT%"
call npm run start:expo-go
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
