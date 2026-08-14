@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Missing virtual environment: .venv\Scripts\python.exe
    echo Please create the venv and install dependencies first.
    pause
    exit /b 1
)

if "%HOST%"=="" set HOST=127.0.0.1
if "%PORT%"=="" set PORT=5000
if "%FLASK_DEBUG%"=="" set FLASK_DEBUG=true
if "%OPEN_BROWSER%"=="" set OPEN_BROWSER=true

echo Starting API Test Platform...
echo URL: http://%HOST%:%PORT%/
echo FLASK_DEBUG=%FLASK_DEBUG%
echo OPEN_BROWSER=%OPEN_BROWSER%
echo.

set "BASE_URL=http://%HOST%:%PORT%/"

echo Checking database migration state...
".venv\Scripts\python.exe" -m flask --app run.py db upgrade
if errorlevel 1 (
    echo.
    echo [ERROR] Database migration failed. Please inspect the migration output above.
    pause
    exit /b 1
)
echo Database migration is up to date.
echo.

echo Ensuring UI automation worker is running...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$worker = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'scripts\\run_ui_automation_worker.py' -and $_.CommandLine -match 'api-test-platform' } | Select-Object -First 1; if (-not $worker) { exit 1 }"
if errorlevel 1 (
    if not exist "instance\ui_automation\worker" mkdir "instance\ui_automation\worker"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$projectRoot = (Get-Location).Path; $python = Join-Path $projectRoot '.venv\Scripts\python.exe'; $script = 'scripts\run_ui_automation_worker.py'; $outLog = Join-Path $projectRoot 'instance\ui_automation\worker\worker.out.log'; $errLog = Join-Path $projectRoot 'instance\ui_automation\worker\worker.err.log'; try { Start-Process -FilePath $python -ArgumentList @('-u', $script) -WorkingDirectory $projectRoot -WindowStyle Minimized -RedirectStandardOutput $outLog -RedirectStandardError $errLog -ErrorAction Stop; Start-Sleep -Milliseconds 500; $pattern = [regex]::Escape($script); $worker = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match $pattern -and $_.CommandLine -match [regex]::Escape($projectRoot) } | Select-Object -First 1; if (-not $worker) { Add-Content -Path $errLog -Value ((Get-Date -Format o) + ' Worker process exited during startup.'); exit 2 } } catch { Add-Content -Path $errLog -Value ((Get-Date -Format o) + ' Failed to start worker: ' + $_.Exception.Message); exit 3 }"
    if errorlevel 1 (
        echo [ERROR] UI automation worker failed to start. See instance\ui_automation\worker\worker.err.log
        pause
        exit /b 1
    )
    echo Started UI automation worker. Logs: instance\ui_automation\worker\worker.out.log
) else (
    echo UI automation worker is already running.
)

echo Ensuring Android UI automation worker is running...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$worker = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'scripts\\run_android_ui_automation_worker.py' -and $_.CommandLine -match 'api-test-platform' } | Select-Object -First 1; if (-not $worker) { exit 1 }"
if errorlevel 1 (
    if not exist "instance\android_ui_automation\worker" mkdir "instance\android_ui_automation\worker"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$projectRoot = (Get-Location).Path; $python = Join-Path $projectRoot '.venv\Scripts\python.exe'; $script = 'scripts\run_android_ui_automation_worker.py'; $outLog = Join-Path $projectRoot 'instance\android_ui_automation\worker\worker.out.log'; $errLog = Join-Path $projectRoot 'instance\android_ui_automation\worker\worker.err.log'; try { Start-Process -FilePath $python -ArgumentList @('-u', $script) -WorkingDirectory $projectRoot -WindowStyle Minimized -RedirectStandardOutput $outLog -RedirectStandardError $errLog -ErrorAction Stop; Start-Sleep -Milliseconds 500; $pattern = [regex]::Escape($script); $worker = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match $pattern -and $_.CommandLine -match [regex]::Escape($projectRoot) } | Select-Object -First 1; if (-not $worker) { Add-Content -Path $errLog -Value ((Get-Date -Format o) + ' Worker process exited during startup.'); exit 2 } } catch { Add-Content -Path $errLog -Value ((Get-Date -Format o) + ' Failed to start worker: ' + $_.Exception.Message); exit 3 }"
    if errorlevel 1 (
        echo [ERROR] Android UI automation worker failed to start. See instance\android_ui_automation\worker\worker.err.log
        pause
        exit /b 1
    )
    echo Started Android UI automation worker. Logs: instance\android_ui_automation\worker\worker.out.log
) else (
    echo Android UI automation worker is already running.
)

echo Checking whether the web port is already in use...
".venv\Scripts\python.exe" scripts\startup_probe.py port %PORT%
set "PORT_CHECK_EXIT=%ERRORLEVEL%"

if "%PORT_CHECK_EXIT%"=="2" (
    echo Port %PORT% is already in use. Checking whether the platform is already running...
    set "PORT_PID="
    set "PORT_PROCESS_NAME="
    for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess)"`) do set "PORT_PID=%%P"
    if defined PORT_PID (
        for /f "tokens=1 delims=," %%N in ('tasklist /FI "PID eq %PORT_PID%" /FO CSV /NH 2^>nul') do set "PORT_PROCESS_NAME=%%~N"
    )
    ".venv\Scripts\python.exe" scripts\startup_probe.py url "%BASE_URL%"
    set "HEALTH_CHECK_EXIT=%ERRORLEVEL%"

    if "%HEALTH_CHECK_EXIT%"=="3" (
        echo.
        echo API Test Platform is already running at %BASE_URL%
        if defined PORT_PID (
            if defined PORT_PROCESS_NAME (
                echo Listening process: PID %PORT_PID% ^| %PORT_PROCESS_NAME%
            ) else (
                echo Listening process: PID %PORT_PID%
            )
        )
        if /i "%OPEN_BROWSER%"=="true" (
            start "" "%BASE_URL%"
        ) else (
            echo Browser auto-open is disabled for this session.
        )
        exit /b 0
    )

    echo.
    echo [ERROR] Port %PORT% is occupied by another process, and the platform did not respond at %BASE_URL%
    if defined PORT_PID (
        if defined PORT_PROCESS_NAME (
            echo Occupying process: PID %PORT_PID% ^| %PORT_PROCESS_NAME%
        ) else (
            echo Occupying process: PID %PORT_PID%
        )
    )
    echo Stop the other process or change PORT before starting.
    pause
    exit /b 1
)
if not "%PORT_CHECK_EXIT%"=="0" (
    echo.
    echo [ERROR] Failed to inspect port %PORT%. Please check your PowerShell environment and retry.
    pause
    exit /b 1
)

if /i "%FLASK_DEBUG%"=="true" (
    echo Development mode is enabled. Python/template changes will auto-reload the web service.
    echo If you change worker logic, restart the affected worker separately to pick up those changes.
    echo.
)

".venv\Scripts\python.exe" run.py

if errorlevel 1 (
    echo.
    echo [ERROR] Project exited with a non-zero status.
    pause
    exit /b 1
)

endlocal
