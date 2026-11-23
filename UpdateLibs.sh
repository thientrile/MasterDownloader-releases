#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found in PATH."
    exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
fi

PY_EXE=".venv/bin/python"

"$PY_EXE" -m pip install --upgrade pip setuptools wheel
"$PY_EXE" -m pip install --upgrade -r requirements.txt
"$PY_EXE" -m pip check
"$PY_EXE" -m pip list --outdated --format=columns
