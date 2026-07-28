# Windows PowerShell wrapper: force UTF-8 then call query.py.
# Mirrors q.bat (cmd.exe fallback) and q.sh (POSIX) for cross-shell parity.
#
# Usage: powershell -File q.ps1 <location> [options]
# Or after Set-Alias q q.ps1: q 北京 --json
#
# This script is preferred over q.bat on Windows because PowerShell
# has native UTF-8 console support (PS 5.1+ via $OutputEncoding).

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
& python "$scriptDir\query.py" @args
exit $LASTEXITCODE