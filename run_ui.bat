@echo off
rem 브라우저 UI 를 연다. 처음 실행하면 .venv 를 만들고 reportlab 을 설치한다.
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist .venv (
  echo 가상환경을 만드는 중...
  %PY% -m venv .venv
)

.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

echo.
.venv\Scripts\python.exe -m minutes_generator --check-fonts
echo.
.venv\Scripts\python.exe -m minutes_generator --ui
pause
