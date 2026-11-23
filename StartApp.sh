#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PY_EXE="python3"
if [[ -x ".venv/bin/python" ]]; then
    PY_EXE=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
    PY_EXE=".venv/bin/python"
else
    echo "python3 is required but was not found in PATH."
    exit 1
fi

if [[ -f "requirements.txt" ]]; then
    if [[ "${UPDATE_LIBS:-0}" == "1" ]]; then
        "$PY_EXE" -m pip install --upgrade pip setuptools wheel
        "$PY_EXE" -m pip install --upgrade -r requirements.txt
    else
        "$PY_EXE" -m pip install -r requirements.txt
    fi
fi

if [[ -n "${WSL_DISTRO_NAME:-}" && -z "${QT_QPA_PLATFORM:-}" ]]; then
    XCB_PLUGIN="$("$PY_EXE" - <<'PY'
from PyQt6.QtCore import QLibraryInfo
from pathlib import Path
print(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platforms" / "libqxcb.so")
PY
)"
    if ldd "$XCB_PLUGIN" 2>/dev/null | grep -q "not found"; then
        echo "Qt xcb backend is not fully installed; using WSLg Wayland."
        echo "For fewer PyQt crashes, run:"
        echo "  sudo apt-get install -y libxcb-cursor0 libxcb-icccm4 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render-util0"
    else
        export QT_QPA_PLATFORM=xcb
    fi
fi

export QT_STYLE_OVERRIDE="${QT_STYLE_OVERRIDE:-Fusion}"

exec "$PY_EXE" "App.py"
