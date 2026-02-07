"""LLM Provider manager for switching between providers."""

import logging
import json
from typing import Optional

from src.config import Config
from .base import LLMProvider
from .gemini_provider import GeminiProvider
from .anthropic_provider import AnthropicProvider

logger = logging.getLogger(__name__)


class ProviderManager:
    """Manages multiple LLM providers with hot-swap switching."""
    
    def __init__(self, config: Config):
        """Initialize provider manager.
        
        Args:
            config: Application configuration.
        """
        self.config = config
        self.providers: dict[str, LLMProvider] = {}
        self.active_provider: str = config.default_provider
        self._state_file = config.paths.state_file
    
    async def initialize(self) -> None:
        """Initialize all configured providers."""
        # Create Gemini provider if configured
        if self.config.gemini.api_key:
            self.providers["gemini"] = GeminiProvider(
                api_key=self.config.gemini.api_key,
                model=self.config.gemini.model,
            )
        
        # Create Anthropic provider if configured
        if self.config.anthropic.api_key:
            self.providers["anthropic"] = AnthropicProvider(
                api_key=self.config.anthropic.api_key,
                model=self.config.anthropic.model,
                admin_api_key=self.config.anthropic.admin_api_key,
            )
        
        # Load saved state
        self._load_state()
        
        # Validate active provider exists
        if self.active_provider not in self.providers:
            # Try to fall back to any available provider
            if self.providers:
                fallback = next(iter(self.providers.keys()))
                logger.warning(
                    f"Configured provider '{self.active_provider}' not available, "
                    f"falling back to '{fallback}'"
                )
                self.active_provider = fallback
            else:
                raise ValueError(
                    "No LLM providers configured. "
                    "Please set GEMINI_API_KEY or ANTHROPIC_API_KEY."
                )
        
        logger.info(f"Initialized providers: {list(self.providers.keys())}")
        logger.info(f"Active provider: {self.active_provider}")
    
    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                if "active_provider" in data:
                    self.active_provider = data["active_provider"]
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self) -> None:
        """Save state to disk."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing state or create new
            data = {}
            if self._state_file.exists():
                try:
                    data = json.loads(self._state_file.read_text())
                except Exception:
                    pass
            
            # Update provider
            data["active_provider"] = self.active_provider
            
            self._state_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    def switch(self, provider_name: str) -> None:
        """Switch to a different provider.
        
        Args:
            provider_name: Name of the provider to switch to.
        
        Raises:
            ValueError: If provider is not available.
        """
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' is not available")
        
        provider = self.providers[provider_name]
        if not provider.is_available():
            raise ValueError(f"Provider '{provider_name}' is not properly configured")
        
        self.active_provider = provider_name
        self._save_state()
        logger.info(f"Switched to provider: {provider_name}")
    
    def get_active(self) -> LLMProvider:
        """Get the currently active provider."""
        return self.providers[self.active_provider]
    
    def list_providers(self) -> list[dict]:
        """List all available providers with their status."""
        result = []
        for name, provider in self.providers.items():
            result.append({
                "name": name,
                "model": provider.model_name,
                "available": provider.is_available(),
                "active": name == self.active_provider,
            })
        return result
