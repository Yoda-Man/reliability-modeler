#!/usr/bin/env sh
# Runs the unit suite. Install dev deps first: pip install -r requirements-dev.txt
set -e
cd "$(dirname "$0")"
exec python3 -m pytest tests/unit "$@"
