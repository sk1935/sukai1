# 🧠 Multi-Model Forecasting System

A Telegram Bot that automatically predicts Polymarket events using multiple AI models (DeepSeek + OpenRouter) and fuses predictions with market probabilities.

## 🎯 Features

- 🤖 **Multi-Model Ensemble**: Uses DeepSeek, Mistral-7B, and Nous-Hermes-2 for diverse perspectives
- 📊 **Market Integration**: Fetches real-time data from Polymarket API
- 🔀 **Intelligent Fusion**: Weighted averaging with confidence-based weighting
- 📱 **Telegram Bot**: Easy-to-use interface via Telegram

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```
OPENROUTER_API_KEY=your_openrouter_key
DEEPSEEK_API_KEY=your_deepseek_key
TELEGRAM_BOT_TOKEN=your_telegram_token
```

### 3. Run the Bot

```bash
python src/main.py
```

### 4. Use the Bot

Send a message to your Telegram bot:

```
/predict Will Sora be the #1 Free App in the US Apple App Store on Oct 31?
```

## 📁 Project Structure

```
polymarket1/
├── src/
│   ├── __init__.py
│   ├── event_manager.py      # Parse events & fetch Polymarket data
│   ├── prompt_builder.py      # Build prompts for models
│   ├── model_orchestrator.py  # Parallel API calls
│   ├── fusion_engine.py       # Weighted fusion logic
│   ├── output_formatter.py    # Format Telegram output
│   └── main.py                # Bot entry point
├── prompt_templates.py        # Prompt templates
├── model_roles.json           # Model configurations
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
└── README.md                 # This file
```

## 🧩 How It Works

1. **Event Parsing**: Bot extracts event from Telegram message
2. **Market Data**: Fetches probability, rules, and trends from Polymarket
3. **Multi-Model Query**: Parallel calls to DeepSeek + OpenRouter models
4. **Fusion**: Weighted average combining:
   - Model probabilities (weighted by confidence)
   - Market probability (30% weight)
5. **Output**: Formatted report with consensus, uncertainty, and reasoning

## 🔧 Configuration

### Model Weights

Edit `src/model_orchestrator.py` to adjust model weights:

```python
MODELS = {
    "deepseek-chat": {"weight": 3.0},  # Core model
    "mistral-7b-instruct:free": {"weight": 1.0},
    "nous-hermes-2:free": {"weight": 1.0}
}
```

### Fusion Parameters

Edit `src/fusion_engine.py` to adjust fusion weights:

```python
MARKET_WEIGHT = 0.3  # Market probability weight
MODEL_WEIGHT = 0.7   # Model consensus weight
```

## 📝 API Keys

### Telegram Bot Token
1. Talk to [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the token to `.env`

### DeepSeek API Key
1. Sign up at [DeepSeek](https://platform.deepseek.com/)
2. Get your API key from the dashboard
3. Add to `.env`

### OpenRouter API Key
1. Sign up at [OpenRouter](https://openrouter.ai/)
2. Get your API key from the dashboard
3. Add to `.env`

## 🐛 Troubleshooting

- **No market found**: The bot will use mock data if Polymarket API fails
- **Model API errors**: Check your API keys and rate limits
- **Import errors**: Make sure you're running from the project root

## 📄 License

MIT License





# sukai
# sukai1
