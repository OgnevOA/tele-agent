# Development Setup Script for Windows
# Run: .\scripts\dev-setup.ps1

Write-Host "Setting up Tele-Agent development environment..." -ForegroundColor Cyan

# Check Python version
$pythonVersion = python --version 2>&1
if ($pythonVersion -notmatch "Python 3\.(1[1-9]|[2-9]\d)") {
    Write-Host "Error: Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python version OK: $pythonVersion" -ForegroundColor Green

# Create virtual environment if not exists
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}
Write-Host "✓ Virtual environment ready" -ForegroundColor Green

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

# Create .env if not exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from template..." -ForegroundColor Yellow
    Copy-Item env.example .env
    Write-Host "! Edit .env with your TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, and API keys" -ForegroundColor Magenta
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit .env with your Telegram credentials"
Write-Host "  2. Add your API key (GEMINI_API_KEY or ANTHROPIC_API_KEY)"
Write-Host "  3. Run bot: python -m src.main"
Write-Host "  4. Or press F5 in VS Code/Cursor to debug"
