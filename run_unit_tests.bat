@echo off
REM Runs the unit suite. Install dev deps first: pip install -r requirements-dev.txt
echo Running Unit Tests...
python -m pytest tests/unit %*
if %errorlevel% neq 0 (
    echo.
    echo Tests Failed!
    exit /b %errorlevel%
)
echo.
echo All Unit Tests Passed!
