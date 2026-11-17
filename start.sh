#!/usr/bin/env bash
# ==============================================================================
# 📱 Mobile Photo Cleanup Kit - macOS / Linux 一键启动脚本
# ==============================================================================

set -e

# 定位脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================="
echo " 📱 正在启动 手机相册缩略图与重复文件对比清理 Web 控制台..."
echo "=============================================================="

# 检测 Python3
if command -v python3 &>/dev/null; then
    PY_BIN="python3"
elif command -v python &>/dev/null; then
    PY_BIN="python"
else
    echo "❌ 错误: 未检测到 Python，请先安装 Python 3.8+。"
    exit 1
fi

PORT=8899
URL="http://localhost:${PORT}"

# 在后台或前台启动服务，并自动调用系统默认浏览器
echo "🚀 正在启动本地 Web 服务 (端口: ${PORT})..."

# 检测系统并打开浏览器
open_browser() {
    sleep 1.2
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open "$URL" 2>/dev/null || true
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        xdg-open "$URL" 2>/dev/null || true
    fi
}

open_browser &

# 启动 Web 服务 (Web-First 模式，所有扫描/比对/清理均在网页端完成)
exec "$PY_BIN" cleaner serve --port "$PORT" --host "0.0.0.0"
