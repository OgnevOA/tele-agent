# Tele-Agent

A self-hosted personal assistant accessed via Telegram with local LLM inference, skill-based architecture, and interactive learning capabilities.

## Features

- **Multi-Provider LLM Support**: Switch between Ollama (local), Google Gemini, and Anthropic Claude
- **Skill-Based Architecture**: Modular skills stored as Markdown files
- **Semantic Search**: ChromaDB-powered skill matching
- **Interactive Learning**: Teach the agent new skills through conversation
- **Personality System**: Customizable agent behavior via SOUL.md, IDENTITY.md, etc.

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai/) (for local LLM inference)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))

### Windows Development

```powershell
# Run setup script
.\scripts\dev-setup.ps1

# Or manually:
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item env.example .env
# Edit .env with your settings

# Start Ollama
ollama run llama3

# Run the bot
python -m src.main
```

Press **F5** in VS Code/Cursor to debug with breakpoints.

### Docker (TrueNAS Scale / Linux)

```bash
# Copy env.example to .env and configure
cp env.example .env

# Build and run
docker-compose up -d
```

See [DEPLOY.md](DEPLOY.md) for detailed TrueNAS Scale deployment instructions.

## Configuration

Edit `.env` file:

```env
# Required
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_ID=your_telegram_user_id

# LLM Providers (configure at least one)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-1.5-flash

ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-3-haiku-20240307

# Default provider
DEFAULT_LLM_PROVIDER=ollama
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Show help |
| `/model` | Switch LLM provider |
| `/skills` | Manage skills |
| `/status` | System status |
| `/reload` | Reload skills and config |

## Skills

Skills are stored as Markdown files in the `skills/` directory:

```markdown
---
title: Check Weather
author: user
created: 2026-02-02
---

# Description
Check the weather for a location.

# Dependencies
- requests

# Code
```python
import requests

def execute(location="London"):
    # Your code here
    return f"Weather in {location}: Sunny, 20°C"
```

### Creating Skills

1. **Manually**: Add a `.md` file to `skills/`
2. **Interactively**: Ask the bot to do something it doesn't know, then teach it

## Personality Files

- `SOUL.md` - Core personality and behavior
- `IDENTITY.md` - Agent name, vibe, emoji
- `USER.md` - Information about you
- `TOOLS.md` - Environment-specific config

## Architecture

```
src/
├── main.py           # Entry point
├── config.py         # Configuration
├── bot/              # Telegram handlers
├── core/             # LangGraph state machine
├── llm/              # LLM providers
├── skills/           # Skill parser/executor
└── retrieval/        # ChromaDB vector store
```

## Security

- Only responds to configured admin user
- Skills run in sandboxed environment
- Configurable execution timeout

## License

MIT
