#!/bin/bash
echo "================================================"
echo "  进销存管理系统 (IMS) v1.0 MVP"
echo "================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python 3.9+"
    exit 1
fi

# Install dependencies
echo "[检测] 正在检查依赖..."
python3 -m pip install -r requirements.txt --quiet 2>/dev/null
echo "[完成] 依赖检查完成"
echo ""

# Launch
echo "[启动] 正在启动服务..."
echo "[访问] http://127.0.0.1:5000"
echo "[提示] 按 Ctrl+C 停止服务"
echo ""

# Open browser
if command -v xdg-open &> /dev/null; then
    xdg-open http://127.0.0.1:5000
elif command -v open &> /dev/null; then
    open http://127.0.0.1:5000
fi

python3 start.py
