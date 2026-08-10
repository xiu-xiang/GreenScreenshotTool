@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动绿色截图工具（开发版，含模型预加载提示）...
".venv\Scripts\python.exe" run.py
