@echo off
REM ClineDesktop2API — launch Cline Desktop routed through the local proxy.
REM Fixes "Token registration failed: 403" (Cloud Armor JA3 fingerprint block).
REM
REM 1. Start proxy.py in another window first:  python proxy.py
REM 2. Run this script.
REM
REM The proxy must be listening on 127.0.0.1:61022.

set "CLINE_API_BASE_URL=http://127.0.0.1:61022"
set "CLINE_ENVIRONMENT=production"

start "" "C:\Users\mrenm\AppData\Local\Cline\cline-app.exe"

echo Launched Cline with CLINE_API_BASE_URL=%CLINE_API_BASE_URL%
