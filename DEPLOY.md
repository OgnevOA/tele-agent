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
   | `DEFAULT_LLM_PROVIDER` | `ollama`, `gemini`, or `anthropic` | ✅ |
   | `OLLAMA_BASE_URL` | `http://192.168.1.x:11434` | If using Ollama |
   | `OLLAMA_MODEL` | `llama3` | If using Ollama |
   | `GEMINI_API_KEY` | Your Gemini API key | If using Gemini |
   | `ANTHROPIC_API_KEY` | Your Anthropic API key | If using Anthropic |

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
   - Update `image:` with your actual GHCR image path
   - Adjust volume paths for your pool

3. Create `.env` file:
   ```bash
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_ADMIN_ID=123456789
   DEFAULT_LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://192.168.1.100:11434
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
- Ollama installed and running

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
   # Edit .env with your settings
   ```

3. Create personality files in project root:
   - `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`

4. Start Ollama:
   ```powershell
   ollama run llama3
   ```

5. Run the bot:
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

## Connecting to Ollama

### Ollama on TrueNAS Host
```bash
OLLAMA_BASE_URL=http://host.docker.internal:11434
# or use TrueNAS IP directly:
OLLAMA_BASE_URL=http://192.168.1.100:11434
```

### Ollama as Container (same compose)
```yaml
services:
  ollama:
    image: ollama/ollama
    container_name: ollama
    volumes:
      - /mnt/pool/apps/ollama:/root/.ollama
    ports:
      - "11434:11434"

  tele-agent:
    # ...
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      - ollama
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

### Ollama connection failed
- Ensure Ollama is running: `curl http://localhost:11434/api/tags`
- Check firewall allows port 11434
- For containers, ensure proper networking

### Skills not loading
- Check `/app/skills` volume mount
- Ensure `.md` files have valid format with code blocks

### View logs
```bash
docker logs tele-agent -f
# or check mounted logs directory
tail -f /mnt/pool/apps/tele-agent/logs/tele-agent.log
```
