#!/bin/bash
# 停止后台运行的 Bot

cd "$(dirname "$0")"
PID_FILE="bot.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️ 未找到 PID 文件，Bot 可能未在运行"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "⚠️ Bot 进程不存在（PID: $PID）"
    rm "$PID_FILE"
    exit 1
fi

echo "🛑 正在停止 Bot（PID: $PID）..."
kill "$PID"

# 等待进程结束
sleep 2

if ps -p "$PID" > /dev/null 2>&1; then
    echo "⚠️ 进程仍在运行，强制终止..."
    kill -9 "$PID"
fi

rm "$PID_FILE"
echo "✅ Bot 已停止"

