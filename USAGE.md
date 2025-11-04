# 🤖 Bot 使用指南

## 📱 如何找到你的 Bot

1. **获取 Bot 用户名**：
   - 在 Telegram 中打开与 `@BotFather` 的对话
   - 发送 `/mybots` 查看你创建的 Bot 列表
   - 找到你的 Bot，会显示 Bot 的用户名（例如：`@your_bot_name`）

2. **搜索并启动 Bot**：
   - 在 Telegram 搜索栏中输入你的 Bot 用户名（例如：`@your_bot_name`）
   - 点击找到的 Bot
   - 点击 **"Start"** 或 **"开始"** 按钮

## 🎯 使用 Bot

### 基本命令

- `/start` - 查看欢迎信息和说明
- `/help` - 查看帮助信息
- `/predict <事件描述>` - 预测一个事件

### 示例

```
/predict Will Sora be the #1 Free App in the US Apple App Store on Oct 31?
```

## ❓ 常见问题

### Bot 没有响应？

1. **检查 Bot 是否运行**：
   ```bash
   ps aux | grep "python.*main.py"
   ```

2. **重启 Bot**：
   ```bash
   ./start_bot.sh
   ```

3. **查看错误日志**：
   检查运行 Bot 的终端窗口，查看是否有错误信息

### 找不到 Bot？

- 确保 Bot 用户名正确（通过 `/mybots` 在 BotFather 中查看）
- 确保 Bot 没有被删除或禁用

### Bot Token 错误？

- 检查 `.env` 文件中的 `TELEGRAM_BOT_TOKEN` 是否正确
- 如果 Token 失效，在 BotFather 中使用 `/token` 获取新 Token

## 🔧 BotFather 命令说明

你看到的那些命令（如 `/newbot`, `/mybots` 等）是给 **BotFather** 用的，用来管理 Bot，不是给你的 Bot 用的。

**给你的 Bot 用的命令**（在 Bot 对话中发送）：
- `/start`
- `/help`  
- `/predict <事件>`





