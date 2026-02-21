@echo off
echo Running Unit Tests...
python -m pytest tests/unit
if %errorlevel% neq 0 (
    echo.
    echo Tests Failed!
    echo Ensure pytest is installed: pip install pytest
) else (
    echo.
    echo All Unit Tests Passed!
)
pause
