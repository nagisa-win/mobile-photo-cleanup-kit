@echo off
REM ==============================================================================
REM 📱 Mobile Photo Cleanup Kit - Windows 一键启动脚本
REM ==============================================================================

chcp 65001 >nul
title 手机相册缩略图与重复文件对比清理 Web 控制台

echo ==============================================================
echo  📱 正在启动 手机相册缩略图与重复文件对比清理 Web 控制台...
echo ==============================================================

set PORT=8899
set URL=http://localhost:%PORT%

REM 检测 Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未检测到 Python，请先从官网或 Microsoft Store 安装 Python 3.8+ 并添加至 PATH。
    pause
    exit /b 1
)

echo [信息] 正在拉起默认浏览器: %URL%
start "" "%URL%"

echo [信息] 正在启动 Web 服务 (端口: %PORT%)...
python cleaner serve --port %PORT% --host 0.0.0.0

pause
