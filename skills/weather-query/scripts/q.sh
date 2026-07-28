#!/usr/bin/env bash
# macOS/Linux wrapper: force UTF-8 locale then call query.py.
# Mirrors q.bat (cmd.exe) and q.ps1 (PowerShell) for cross-shell parity.
#
# Usage: q <location> [options]
# Example: q 北京 --json
#
# Required: Python 3.8+ on PATH.
# Optional: chmod +x q.sh once after copying.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
python "$SCRIPT_DIR/query.py" "$@"