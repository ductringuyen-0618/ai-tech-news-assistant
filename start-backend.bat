@echo off
echo Starting backend server...
cd /d "%~dp0backend"
py -m uvicorn src.main:app --port 8000 --env-file .env
