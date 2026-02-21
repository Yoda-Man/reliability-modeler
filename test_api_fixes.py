
import asyncio
import sys
import os
from pathlib import Path

# Mock FastAPI for simple testing if needed, or just import the function
# We can just import and call run_analysis_pipeline directly

# Set up environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR / "web" / "api"))

# Need to mock uvicorn and other things if we were running the app,
# but we just want to test run_analysis_pipeline from main.py
os.chdir(BASE_DIR / "web" / "api")

from main import run_analysis_pipeline

async def test():
    print("Testing Sample Data Analysis...")
    sample_path = Path("sample_data.csv")
    try:
        result = await run_analysis_pipeline(sample_path, "sample_data.csv", 1000.0)
        print("Sample Data Result: SUCCESS")
        print(f"Summary: {result.get('summary')}")
        print(f"Models: {[m['name'] for m in result.get('models', [])]}")
    except Exception as e:
        print(f"Sample Data Analysis FAILED: {e}")
        import traceback
        traceback.print_exc()

    print("\nTesting User CSV Analysis (error_log.csv)...")
    user_csv = BASE_DIR / "input" / "error_log.csv"
    try:
        result = await run_analysis_pipeline(user_csv, "error_log.csv", 1000.0)
        print("User CSV Result: SUCCESS")
        print(f"Summary: {result.get('summary')}")
    except Exception as e:
        print(f"User CSV Analysis FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
