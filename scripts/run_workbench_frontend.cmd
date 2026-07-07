@echo off
REM Windows native cmd 工作台前端启动器。
REM
REM 用法：
REM   scripts\run_workbench_frontend.cmd

setlocal
cd /d "%~dp0\.."

if "%FRONTEND_HOST%"=="" (
  for /f "delims=" %%H in ('python -c "import sys; sys.path.insert(0, r'frontend\streamlit_app'); from config_resolver import resolve_workbench_config; print(resolve_workbench_config()['frontend_host'])"') do (
    set "FRONTEND_HOST=%%H"
  )
)

if "%FRONTEND_PORT%"=="" (
  for /f "delims=" %%P in ('python -c "import sys; sys.path.insert(0, r'frontend\streamlit_app'); from config_resolver import resolve_workbench_config; print(resolve_workbench_config()['frontend_port'])"') do (
    set "FRONTEND_PORT=%%P"
  )
)

if "%FRONTEND_HOST%"=="" set "FRONTEND_HOST=127.0.0.1"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=8501"

python -m streamlit run frontend\streamlit_app\streamlit_entry.py --server.port %FRONTEND_PORT% --server.address %FRONTEND_HOST% --server.headless true

endlocal
