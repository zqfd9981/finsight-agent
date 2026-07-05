@echo off
REM Windows native cmd 工作台后端启动器（包装 Python launcher）。
REM
REM 用法：
REM   scripts\run_workbench_backend.cmd
REM   scripts\run_workbench_backend.cmd --reload

@python scripts\run_workbench_backend.py %*
