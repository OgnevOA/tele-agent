# Deployment Guide

## Quick Start - TrueNAS Scale

The container image is automatically built and pushed to GitHub Container Registry via GitHub Actions.

**Image:** `ghcr.io/ognevoa/tele-agent:latest`

### Prerequisites on TrueNAS

1. Create a dataset for the app (e.g., `/mnt/pool/apps/tele-agent`)
2. Create subdirectories:
   ```bash
   mkdir -p /mnt/pool/apps/tele-agent/{data,personality,logs,skills}
   ```
3. Copy your personality files to `personality/`:
   - `SOUL.md` - Core personality
   - `IDENTITY.md` - Name, avatar, vibe
   - `USER.md` - Info about you
   - `TOOLS.md` - Environment settings (Home Assistant, etc.)

4. Copy skills (optional - use defaults or customize):
   ```bash
   # Copy from repo or create your own
   cp skills/*.md /mnt/pool/apps/tele-agent/skills/
   ```

---

## Option 1: TrueNAS Apps (Custom App)

1. Go to **Apps** → **Discover Apps** → **Custom App**

2. **Basic Configuration:**
   - Application Name: `tele-agent`
   - Image Repository: `ghcr.io/ognevoa/tele-agent`
   - Image Tag: `latest`

3. **Environment Variables:**
   | Variable | Value | Required |
   |----------|-------|----------|
   | `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather | ✅ |
   | `TELEGRAM_ADMIN_ID` | Your Telegram user ID | ✅ |
   | `DEFAULT_LLM_PROVIDER` | `gemini` or `anthropic` | ✅ |
   | `GEMINI_API_KEY` | Your Gemini API key | Recommended |
   | `ANTHROPIC_API_KEY` | Your Anthropic API key | Optional |

   **Note:** Gemini is recommended as it supports embeddings for vector search.

4. **Storage (Host Path Volumes):**
   | Container Path | Host Path | Mode |
   |---------------|-----------|------|
   | `/app/data` | `/mnt/pool/apps/tele-agent/data` | Read/Write |
   | `/app/personality` | `/mnt/pool/apps/tele-agent/personality` | Read Only |
   | `/app/skills` | `/mnt/pool/apps/tele-agent/skills` | Read Only |
   | `/app/logs` | `/mnt/pool/apps/tele-agent/logs` | Read/Write |

5. Click **Install**

---

## Option 2: Docker Compose (via Portainer/Dockge)

Use `docker-compose.truenas.yml` from the repo:

1. Copy to TrueNAS:
   ```bash
   scp docker-compose.truenas.yml root@truenas:/mnt/pool/apps/tele-agent/docker-compose.yml
   ```

2. Edit the compose file:
   - Adjust volume paths for your pool

3. Create `.env` file:
   ```bash
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_ADMIN_ID=123456789
   DEFAULT_LLM_PROVIDER=gemini
   GEMINI_API_KEY=your_gemini_api_key
   # Optional: ANTHROPIC_API_KEY=your_anthropic_key
   ```

4. Deploy:
   ```bash
   docker-compose up -d
   ```

---

## GitHub Actions - Automatic Builds

The repo includes `.github/workflows/docker-build.yml` which:
- Builds on every push to `main`/`master`
- Creates multi-arch images (amd64 + arm64)
- Pushes to GitHub Container Registry (ghcr.io)
- Tags: `latest`, `main`, and commit SHA

### First-time Setup

1. The workflow uses `GITHUB_TOKEN` automatically - no secrets needed
2. After first build, make the package public:
   - Go to your GitHub profile → Packages
   - Click on `tele-agent`
   - Settings → Change visibility → Public

### Manual Trigger

Go to **Actions** → **Build and Push Docker Image** → **Run workflow**

---

## Local Development (Windows)

### Prerequisites
- Python 3.11+
- Gemini API key (or Anthropic API key)

### Setup

1. Create virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Create `.env` file:
   ```powershell
   Copy-Item env.example .env
   # Edit .env with your API keys
   ```

3. Create personality files in project root:
   - `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`

4. Run the bot:
   ```powershell
   python -m src.main
   ```

### Debugging in VS Code / Cursor

Add to `.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Tele-Agent",
            "type": "debugpy",
            "request": "launch",
            "module": "src.main",
            "cwd": "${workspaceFolder}",
            "envFile": "${workspaceFolder}/.env",
            "console": "integratedTerminal"
        }
    ]
}
```

---

## LLM Providers

### Gemini (Recommended)
- Supports text generation and embeddings
- Required for vector search functionality
- Get API key: https://makersuite.google.com/app/apikey

```bash
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-1.5-flash
DEFAULT_LLM_PROVIDER=gemini
```

### Anthropic Claude
- Supports text generation only (no embeddings)
- If using Anthropic as default, also set Gemini key for embeddings

```bash
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-3-haiku-20240307
DEFAULT_LLM_PROVIDER=anthropic
# Still need Gemini for embeddings:
GEMINI_API_KEY=your_gemini_key
```

---

## Updating the Bot

### From GitHub (recommended)
The container auto-updates if you use `:latest` tag with Watchtower or similar.

Or manually:
```bash
docker pull ghcr.io/ognevoa/tele-agent:latest
docker-compose up -d
```

### From Source
```bash
git pull
docker-compose build --no-cache
docker-compose up -d
```

---

## Troubleshooting

### Bot not responding
- Check `TELEGRAM_ADMIN_ID` matches your Telegram user ID
- Get your ID: message [@userinfobot](https://t.me/userinfobot)

### Personality not loading
- Check `/app/personality` mount contains your .md files
- Verify file permissions (readable by container)

### API errors
- Verify your API keys are valid
- Check API quotas/limits on provider dashboards

### Skills not loading
- Check `/app/skills` volume mount
- Ensure `.md` files have valid format with code blocks

### View logs
```bash
docker logs tele-agent -f
# or check mounted logs directory
tail -f /mnt/pool/apps/tele-agent/logs/tele-agent.log
```
