#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate
exec uvicorn backend.main:app --port 8765 --reload
