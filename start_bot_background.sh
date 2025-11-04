#!/bin/bash
# 后台启动 Polymarket Forecasting Bot（关闭终端后继续运行）

cd "$(dirname "$0")"
source venv/bin/activate

LOG_FILE="bot_debug.log"
PID_FILE="bot.pid"

echo "🤖 后台启动 Bot..."
echo "📄 日志文件: $LOG_FILE"
echo "🆔 PID 文件: $PID_FILE"
echo ""

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "⚠️ Bot 已经在运行（PID: $OLD_PID）"
        echo "💡 如需重启，请先运行: kill $OLD_PID"
        exit 1
    else
        echo "🧹 清理旧的 PID 文件"
        rm "$PID_FILE"
    fi
fi

# 使用 nohup 后台运行
nohup python src/main.py > "$LOG_FILE" 2>&1 &
BOT_PID=$!

# 保存 PID
echo $BOT_PID > "$PID_FILE"

echo "✅ Bot 已在后台启动"
echo "🆔 PID: $BOT_PID"
echo ""
echo "💡 常用命令:"
echo "   查看日志: tail -f $LOG_FILE"
echo "   停止 Bot: kill $BOT_PID"
echo "   查看状态: ps -p $BOT_PID"
echo ""
echo "📱 Bot 现在可以在 Telegram 中使用了！"
echo "   即使关闭 Cursor 或终端，Bot 也会继续运行"

