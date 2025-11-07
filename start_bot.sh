#!/bin/bash
# Start the Polymarket Forecasting Bot

cd "$(dirname "$0")"

# 添加日志输出到文件，方便查看DEBUG信息
LOG_FILE="bot_debug.log"
echo "🤖 启动Bot，日志将保存到: $LOG_FILE"
echo "💡 查看实时日志: tail -f $LOG_FILE"
echo "💡 查看DEBUG日志: grep '\[DEBUG\]' $LOG_FILE"
echo "💡 查看超时日志: grep '\[TIMEOUT\]' $LOG_FILE"
echo ""

# 使用虚拟环境中的 Python 解释器
./venv/bin/python src/main.py 2>&1 | tee -a "$LOG_FILE"



