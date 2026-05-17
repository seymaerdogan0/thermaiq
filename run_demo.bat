@echo off
setlocal

set "ROOT=%~dp0"

echo Starting ThermaIQ backend on http://127.0.0.1:8001
start "ThermaIQ Backend" cmd /k "cd /d %ROOT%backend && python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload"

echo Starting ThermaIQ frontend on http://127.0.0.1:3000
start "ThermaIQ Frontend" cmd /k "cd /d %ROOT% && python -m http.server 3000 -d frontend"

timeout /t 3 /nobreak >nul
start http://127.0.0.1:3000

echo.
echo ThermaIQ demo is running.
echo Frontend : http://127.0.0.1:3000
echo Backend  : http://127.0.0.1:8001/docs
echo.
echo Keep the two opened terminal windows running during the demo.
pause
