
# Reliability Modeler - Automated Test Script

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Write-Host "Project Root: $projectRoot" -ForegroundColor Gray

$outputDir = Join-Path $projectRoot "tests\test_output"
$pythonScript = Join-Path $projectRoot "reliability_modeler.py"
$inputCsv = Join-Path $projectRoot "input/error_log.csv"

$logDir = Join-Path $projectRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "test_run_$timestamp.log"

Start-Transcript -Path $logFile -Append

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Reliability Modeler - Automated Tests  " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Set CWD to project root so relative paths in python script work
Set-Location $projectRoot
Write-Host "Current Location: $(Get-Location)" -ForegroundColor Gray
Write-Host "Input CSV exists: $(Test-Path $inputCsv)" -ForegroundColor Gray
python --version

# Function to run a test case
function Invoke-ReliabilityTest {
    param (
        [string]$Name,
        [scriptblock]$Command,
        [string]$CheckPath = $null
    )

    Write-Host "`n[TEST] $Name" -ForegroundColor Yellow
    try {
        & $Command
        if ($LASTEXITCODE -eq 0) {
            if ($CheckPath -and -not (Test-Path $CheckPath)) {
                Write-Host "  [FAIL] Expected artifact not found: $CheckPath" -ForegroundColor Red
                return $false
            }
            Write-Host "  [PASS]" -ForegroundColor Green
            return $true
        }
        else {
            Write-Host "  [FAIL] Script returned exit code $LASTEXITCODE" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "  [FAIL] Exception: $_" -ForegroundColor Red
        return $false
    }
}

# 1. Clean Output Directory
Write-Host "`nCleaning output directory..."
if (Test-Path $outputDir) {
    Remove-Item -Recurse -Force $outputDir -ErrorAction SilentlyContinue
}

# 2. Test Default Run
$test1 = Invoke-ReliabilityTest -Name "Run with defaults" -Command {
    python $pythonScript --output-dir $outputDir
} -CheckPath $outputDir

# 3. Test Help Message
$test2 = Invoke-ReliabilityTest -Name "Run --help" -Command {
    python $pythonScript --help
}

# 4. Test Explicit CSV
$test3 = Invoke-ReliabilityTest -Name "Run with explicit CSV" -Command {
    python $pythonScript --csv $inputCsv --output-dir $outputDir
}

# Summary
Write-Host "`n=========================================" -ForegroundColor Cyan
if ($test1 -and $test2 -and $test3) {
    Write-Host "  ALL TESTS PASSED" -ForegroundColor Green
}
else {
    Write-Host "  SOME TESTS FAILED" -ForegroundColor Red
}
Write-Host "=========================================" -ForegroundColor Cyan

Write-Host "`nContents of $outputDir :"
if (Test-Path $outputDir) {
    Get-ChildItem $outputDir | Select-Object Name
}
else {
    Write-Host "Directory not found!" -ForegroundColor Red
}

Stop-Transcript
