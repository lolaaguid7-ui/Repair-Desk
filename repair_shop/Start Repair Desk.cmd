@echo off
cd /d "%~dp0"
echo Repair Desk - local workshop management
echo Open http://127.0.0.1:5001 in your browser.
echo Keep this window open while using the app.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
) else if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" run.py
) else (
  echo Python environment not found. See README.md for setup instructions.
)
pause