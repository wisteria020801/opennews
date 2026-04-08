@echo off

:: OpenNews Matrix Bot 启动脚本
:: 版本: v2.3
:: 功能: 启动 Telegram 命令 Bot (长轮询模式)

:: 设置工作目录
cd /d "D:\opennews-mcp\opennews-mcp"

:: 设置环境变量
set BOT_TOKEN_G=8467815691:AAEzA9Jx7a9cjbeUnTOoNefPNwRz6gZDfPQ
set GEMINI_API_KEY=AIzaSyDP3V2Lgh4N2BRIyzvN9y_VAEGcL69GfOQ

:: 检查 Python 环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 未安装或不在 PATH 中
    pause
    exit /b 1
)

:: 启动 Bot
echo [INFO] 启动 OpenNews Matrix Bot...
echo [INFO] 监听 Telegram 命令...
echo [INFO] 按 Ctrl+C 停止

title OpenNews Matrix Bot
python src\bot_command.py --run

:: 捕获退出
echo [INFO] Bot 已停止
timeout /t 3 >nul