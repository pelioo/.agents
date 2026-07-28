@echo off
REM Smart Windows wrapper:
REM   1) If PowerShell is available, delegate to q.ps1 (preferred - native UTF-8).
REM   2) Otherwise (rare), fall back to direct cmd mode with chcp 65001.
REM Mirrors q.sh (POSIX) for cross-platform parity.

REM Detect PowerShell via 'where'. Errorlevel 0 = found, non-zero = missing.
where powershell >nul 2>&1

REM if/else block: the LAST command's exit code becomes the script's exit code.
if errorlevel 1 (
    REM --- fallback: direct cmd mode ---
    chcp 65001 >nul
    set PYTHONIOENCODING=utf-8
    python "%~dp0query.py" %*
) else (
    REM --- preferred: delegate to PowerShell ---
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0q.ps1" %*
)