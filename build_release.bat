@echo off
setlocal

echo ==========================================
echo  Reliability Modeler - Release Builder
echo ==========================================

REM 1. Clean previous builds
echo.
echo [1/4] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist Reference_Release rmdir /s /q Reference_Release
if exist *.spec del *.spec

REM 2. Verify PyInstaller
echo.
echo [2/4] Verifying PyInstaller...
python -m pip install pyinstaller
if %errorlevel% neq 0 (
    echo Error: Failed to install PyInstaller.

    exit /b %errorlevel%
)

REM 3. Build Executable
echo.
echo [3/4] Building Executable (this may take a minute)...
python -m PyInstaller --name "ReliabilityModeler" --onefile --clean reliability_modeler.py
if %errorlevel% neq 0 (
    echo Error: PyInstaller build failed.

    exit /b %errorlevel%
)

REM 4. Package Release
echo.
echo [4/4] Creating Release Package...
mkdir Reference_Release
copy dist\ReliabilityModeler.exe Reference_Release\
copy fault_categories.conf Reference_Release\
copy README.md Reference_Release\
copy USER_MANUAL.md Reference_Release\
copy CHANGELOG.md Reference_Release\
if exist LICENSE copy LICENSE Reference_Release\

mkdir Reference_Release\input
copy input\error_log.csv Reference_Release\input\

echo.
echo ==========================================
echo  BUILD SUCCESSFUL!
echo ==========================================
echo.
echo Release created in: Reference_Release\
echo.

