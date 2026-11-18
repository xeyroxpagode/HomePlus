@echo off
setlocal EnableExtensions

rem Source: this Android Studio / Maestro workspace.
set "SOURCE=%~dp0..\.."
for %%I in ("%SOURCE%") do set "SOURCE=%%~fI"

rem Resolve directory junctions (for example C:\HP) before calculating the
rem sibling Expo Go workspace. Otherwise the target would incorrectly become
rem C:\mi-front-expo-go and could keep stale dependencies.
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$item = Get-Item -LiteralPath $env:SOURCE; if ($item.Target) { [System.IO.Path]::GetFullPath([string]$item.Target) } else { $item.FullName }"`) do set "SOURCE=%%I"

rem Target: a sibling JS-only Expo Go workspace under front\.
for %%I in ("%SOURCE%\..\mi-front-expo-go") do set "TARGET=%%~fI"

echo.
echo Source: %SOURCE%
echo Target: %TARGET%
echo.
echo Copying source changes without native build, Maestro, Metro, or dependency artifacts...
robocopy "%SOURCE%" "%TARGET%" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD node_modules android ios .expo* .tmp* .maestro .gradle build qa /XF ".env" "*.apk" "*.aab"
set "ROBOCOPY_EXIT=%ERRORLEVEL%"
if %ROBOCOPY_EXIT% GEQ 8 (
  echo ERROR: robocopy failed with exit code %ROBOCOPY_EXIT%.
  exit /b %ROBOCOPY_EXIT%
)

if exist "%TARGET%\android" (
  echo ERROR: %TARGET%\android already exists. It was not removed automatically.
  echo Keep this Expo Go workspace JS-only, or choose another empty target directory.
  exit /b 1
)

if not exist "%TARGET%\.env" (
  copy /Y "%SOURCE%\.env" "%TARGET%\.env" >nul
  if errorlevel 1 (
    echo ERROR: Could not create %TARGET%\.env from the source environment.
    exit /b 1
  )
  echo IMPORTANT: Update EXPO_PUBLIC_API_URL in %TARGET%\.env to your PC LAN IP before opening Expo Go.
)

pushd "%TARGET%"
call npm ci
if errorlevel 1 (
  set "NPM_EXIT=%ERRORLEVEL%"
  popd
  exit /b %NPM_EXIT%
)
popd

echo.
echo Expo Go workspace is ready: %TARGET%
echo Start it with: %TARGET%\scripts\expo-go\start-expo-go.cmd
exit /b 0
