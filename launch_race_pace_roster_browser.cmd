@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "APP_HTML=%PROJECT_ROOT%tools\ams2_roster_browser\index.html"
set "APP_HTML_URI=file:///%APP_HTML:\=/%"
set "RACE_PACE_PARENT=C:\Users\hfaur\AppData\Roaming"
set "RACE_PACE_PROFILE=race-pace-career-app"

set "BROWSER="
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "BROWSER=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" set "BROWSER=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "BROWSER=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "BROWSER=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

if not defined BROWSER (
  echo Could not find Microsoft Edge or Google Chrome.
  pause
  exit /b 1
)

start "" "%BROWSER%" ^
  --user-data-dir="%RACE_PACE_PARENT%" ^
  --profile-directory="%RACE_PACE_PROFILE%" ^
  --allow-file-access-from-files ^
  --app="%APP_HTML_URI%"

endlocal
