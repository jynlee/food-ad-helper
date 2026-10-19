@echo off
rem 월 1회 갱신 (Windows 작업 스케줄러용). 실행 기록은 logs\run_monthly.log 에 남는다.
cd /d "%~dp0.."
set PYTHONUTF8=1
echo ===== %date% %time% ===== >> logs\run_monthly.log
.venv\Scripts\python.exe -u scripts\run_monthly.py >> logs\run_monthly.log 2>&1
