"""Configuration management for Tele-Agent."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    admin_id: int = field(default_factory=lambda: int(os.getenv("TELEGRAM_ADMIN_ID", "0")))


@dataclass
class GeminiConfig:
    """Google Gemini configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))


@dataclass
class AnthropicConfig:
    """Anthropic Claude configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    admin_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_ADMIN_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"))


def _resolve_personality_file(env_key: str, filename: str) -> Path:
    """Resolve personality file path - check env var, then personality/, then root."""
    # First: explicit env var
    if os.getenv(env_key):
        return Path(os.getenv(env_key))
    # Second: personality directory (container mount point)
    personality_path = Path(f"./personality/{filename}")
    if personality_path.exists():
        return personality_path
    # Third: root directory (development)
    return Path(f"./{filename}")


@dataclass
class PathsConfig:
    """File system paths configuration."""
    skills_dir: Path = field(default_factory=lambda: Path(os.getenv("SKILLS_DIR", "./skills")))
    state_file: Path = field(default_factory=lambda: Path(os.getenv("STATE_FILE", "./data/state.json")))
    
    # Behavior documents (can be mounted via env vars in container)
    soul_file: Path = field(default_factory=lambda: _resolve_personality_file("SOUL_FILE", "SOUL.md"))
    identity_file: Path = field(default_factory=lambda: _resolve_personality_file("IDENTITY_FILE", "IDENTITY.md"))
    user_file: Path = field(default_factory=lambda: _resolve_personality_file("USER_FILE", "USER.md"))
    tools_file: Path = field(default_factory=lambda: _resolve_personality_file("TOOLS_FILE", "TOOLS.md"))


@dataclass
class Config:
    """Main configuration container."""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    default_provider: str = field(default_factory=lambda: os.getenv("DEFAULT_LLM_PROVIDER", "gemini"))
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if not self.telegram.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not self.telegram.admin_id:
            errors.append("TELEGRAM_ADMIN_ID is required")
        
        # Validate provider-specific configs based on default
        if self.default_provider == "gemini" and not self.gemini.api_key:
            errors.append("GEMINI_API_KEY is required when using Gemini provider")
        if self.default_provider == "anthropic" and not self.anthropic.api_key:
            errors.append("ANTHROPIC_API_KEY is required when using Anthropic provider")
        
        return errors


# Global config instance
config = Config()
