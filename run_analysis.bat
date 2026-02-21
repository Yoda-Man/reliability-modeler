@echo off
echo ===================================================
echo   Reliability Modeler - Manager Launcher
echo ===================================================
echo.
echo Running analysis on input/error_log.csv...
echo.
python reliability_modeler.py
echo.
if %errorlevel% neq 0 (
    echo Error: Script execution failed.
    pause
    exit /b %errorlevel%
)
echo.
echo Analysis complete! Check the 'output' folder for results.
echo.
pause
