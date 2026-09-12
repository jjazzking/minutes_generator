#!/usr/bin/env bash
# 브라우저 UI 를 연다. 처음 실행하면 .venv 를 만들고 reportlab 을 설치한다.
set -e
cd "$(dirname "$0")"

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

if [ ! -d .venv ]; then
  echo "가상환경을 만드는 중..."
  "$PY" -m venv .venv
fi

VENV_PY=".venv/bin/python"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

echo
"$VENV_PY" -m minutes_generator --check-fonts
echo
exec "$VENV_PY" -m minutes_generator --ui "$@"
