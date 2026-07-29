@echo off
chcp 65001 >nul
title 进销存管理系统 (IMS)
echo ================================================
echo   进销存管理系统 (IMS) v1.0 MVP
echo ================================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

REM 安装依赖
echo [检测] 正在检查依赖...
python -m pip install -r requirements.txt --quiet
echo [完成] 依赖检查完成
echo.

REM 启动
echo [启动] 正在启动服务...
echo [访问] http://127.0.0.1:5000
echo [提示] 按 Ctrl+C 停止服务
echo.
start http://127.0.0.1:5000
python start.py

pause
