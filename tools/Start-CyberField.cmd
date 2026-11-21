@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "MEDIACRAWLER_DIR=%CD%\MediaCrawler"
set "MEDIACRAWLER_PYTHON=%CD%\runtime\python.exe"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\browsers"
set "LLM_API_KEY="
if not exist "data\temp" mkdir "data\temp"
if errorlevel 1 goto failed
set "TEMP=%CD%\data\temp"
set "TMP=%TEMP%"
if not exist "runtime\python.exe" goto failed
set "OPEN_BROWSER=--open-browser"
if "%~1"=="--no-browser" set "OPEN_BROWSER="
"runtime\python.exe" -B -m collect.web_app --port 0 %OPEN_BROWSER%
if errorlevel 1 goto failed
popd
exit /b 0
:failed
echo CyberField could not start. Extract the whole ZIP to a writable folder and try again.
pause
popd
exit /b 1
