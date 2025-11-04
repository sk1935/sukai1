#!/bin/bash
# 查看调试日志的便捷脚本

LOG_FILE="bot_debug.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "❌ 日志文件不存在: $LOG_FILE"
    echo "💡 请先运行 bot，日志会写入此文件"
    exit 1
fi

echo "=" | head -c 80 && echo ""
echo "📋 查看DEBUG日志".center(80) | tr ' ' '='
echo "=" | head -c 80 && echo ""

echo ""
echo "【选项】"
echo "1. 查看所有DEBUG日志"
echo "2. 查看所有超时日志"
echo "3. 查看所有错误日志"
echo "4. 查看最近的50行日志"
echo "5. 实时跟踪日志（类似tail -f）"
echo ""
read -p "选择选项 (1-5): " choice

case $choice in
    1)
        echo "📊 所有DEBUG日志："
        grep "\[DEBUG\]" "$LOG_FILE" | tail -100
        ;;
    2)
        echo "⏱️ 所有超时日志："
        grep "\[TIMEOUT\]" "$LOG_FILE" | tail -50
        ;;
    3)
        echo "❌ 所有错误日志："
        grep "\[ERROR\]" "$LOG_FILE" | tail -50
        ;;
    4)
        echo "📄 最近50行日志："
        tail -50 "$LOG_FILE"
        ;;
    5)
        echo "👀 实时跟踪日志（Ctrl+C退出）："
        tail -f "$LOG_FILE"
        ;;
    *)
        echo "无效选项"
        ;;
esac
