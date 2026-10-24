@echo off
rem ---------------------------------------------------------------------------
rem  Ninja Defenders - daily free Ruby Cat Stone
rem  Double-click this file on Windows. It sets everything up on the first run,
rem  asks for your account id if you did not put it in .env, and pauses at the
rem  end so you can read the result.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="NINJA_USER_ID" set "NINJA_USER_ID=%%B"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
)

rem Edge is installed on every Windows 10/11 machine, so default to it here.
if not defined BROWSER set "BROWSER=edge"

rem Keep Selenium's driver cache inside the project: some accounts cannot write
rem to %USERPROFILE%\.cache.
if not defined SE_CACHE_PATH set "SE_CACHE_PATH=%~dp0.selenium"

".venv\Scripts\python.exe" claim.py %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Done - nothing else to do today.
) else (
    echo Finished with exit code %RC%.
    echo Run with DEBUG=1 to save a screenshot and the page HTML into artifacts\.
)
echo.
pause
exit /b %RC%

:nopython
echo.
echo Python was not found. Install Python 3.9+ from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:failed
echo.
echo Setup failed - see the messages above.
pause
exit /b 1
