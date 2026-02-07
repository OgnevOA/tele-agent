"""Ollama LLM provider implementation."""

import logging
from typing import Optional, AsyncIterator

import httpx

from .base import LLMProvider, ToolDefinition, GenerationResult

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider for local LLM inference."""
    
    def __init__(self, base_url: str, model: str, embed_model: str = "nomic-embed-text"):
        """Initialize Ollama provider.
        
        Args:
            base_url: Ollama API base URL (e.g., http://localhost:11434).
            model: Model name for chat (e.g., llama3, mistral).
            embed_model: Model name for embeddings (e.g., nomic-embed-text).
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._embed_model = embed_model
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None
    
    @property
    def name(self) -> str:
        return "ollama"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=120.0,
            )
        return self._client
    
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a response using Ollama."""
        client = await self._get_client()
        
        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        
        payload = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        try:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
    
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Ollama."""
        client = await self._get_client()
        
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        
        payload = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        try:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise
    
    async def embed(self, text: str) -> list[float]:
        """Generate embeddings using Ollama.
        
        Returns empty list if Ollama is not available.
        """
        # Check availability first - skip if Ollama isn't running
        if not await self.check_available_async():
            logger.debug("Ollama not available, skipping embed creation")
            return []
        
        client = await self._get_client()
        
        payload = {
            "model": self._embed_model,
            "input": text,
        }
        
        try:
            response = await client.post("/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()
            # Ollama returns {"embeddings": [[...]]} for single input
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            return []
        except Exception as e:
            logger.warning(f"Ollama embedding error: {e}")
            return []
    
    def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        if self._available is not None:
            return self._available
        
        try:
            import httpx
            response = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        
        return self._available
    
    async def check_available_async(self) -> bool:
        """Async check if Ollama is available."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        return self._available
    
    def supports_tools(self) -> bool:
        """Ollama doesn't support native tool calling - use RAG fallback."""
        return False
    
    def supports_vision(self) -> bool:
        """Ollama can support vision with specific models (llava, bakllava)."""
        # Check if model name suggests vision support
        vision_models = ["llava", "bakllava", "moondream"]
        return any(vm in self._model.lower() for vm in vision_models)
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
