"""Anthropic Claude LLM provider implementation."""

import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, AsyncIterator

import httpx

from .base import LLMProvider, ToolDefinition, ToolCall, GenerationResult

logger = logging.getLogger(__name__)


@dataclass
class UsageStats:
    """Track token usage and costs (session-based)."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    requests: int = 0
    
    def add(self, input_tokens: int, output_tokens: int, cache_read: int = 0) -> None:
        """Add usage from a request."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_read_tokens += cache_read
        self.requests += 1
    
    def reset(self) -> None:
        """Reset all counters."""
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.requests = 0


@dataclass
class AdminUsageReport:
    """Usage report from Anthropic Admin API."""
    uncached_input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_tokens: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    
    @property
    def total_tokens(self) -> int:
        return self.uncached_input_tokens + self.output_tokens + self.cache_read_input_tokens


@dataclass 
class AdminCostReport:
    """Cost report from Anthropic Admin API."""
    total_cost_cents: float = 0.0
    currency: str = "USD"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    breakdown: dict = field(default_factory=dict)
    
    @property
    def total_cost_usd(self) -> float:
        """Convert cents to dollars."""
        return self.total_cost_cents / 100.0


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider for cloud LLM inference with native tool calling."""
    
    def __init__(self, api_key: str, model: str, admin_api_key: str = ""):
        """Initialize Anthropic provider.
        
        Args:
            api_key: Anthropic API key.
            model: Model name (e.g., claude-3-haiku-20240307).
            admin_api_key: Optional separate admin API key for usage/cost reports.
        """
        self._api_key = api_key
        self._model = model
        self._admin_api_key = admin_api_key or api_key  # Fall back to regular key
        self._client = None
        self.usage = UsageStats()
    
    @property
    def name(self) -> str:
        return "anthropic"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self):
        """Get or create Anthropic client."""
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client
    
    def _prepare_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Prepare messages for Anthropic API.
        
        Returns:
            Tuple of (system_prompt, anthropic_messages)
        """
        system_prompt = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_prompt = content
            elif role == "tool_result":
                # Format tool result for Anthropic
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_use_id", ""),
                        "content": content,
                    }],
                })
            else:
                # Handle regular messages or messages with tool_use
                if isinstance(content, list):
                    anthropic_messages.append({"role": role, "content": content})
                else:
                    anthropic_messages.append({"role": role, "content": content})
        
        return system_prompt, anthropic_messages
    
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a response using Claude."""
        client = self._get_client()
        system_prompt, anthropic_messages = self._prepare_messages(messages)
        
        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=max_tokens or 4096,
                system=system_prompt if system_prompt else None,
                messages=anthropic_messages,
                temperature=temperature,
            )
            
            # Track usage
            if hasattr(response, 'usage'):
                self.usage.add(
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
            
            # Extract text from response
            if response.content:
                for block in response.content:
                    if hasattr(block, 'text'):
                        return block.text
            return ""
            
        except Exception as e:
            logger.error(f"Anthropic generation error: {e}")
            raise
    
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """Generate a response with native tool calling support."""
        client = self._get_client()
        system_prompt, anthropic_messages = self._prepare_messages(messages)
        
        # Convert tools to Anthropic format
        anthropic_tools = [tool.to_anthropic_format() for tool in tools]
        
        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=max_tokens or 4096,
                system=system_prompt if system_prompt else None,
                messages=anthropic_messages,
                tools=anthropic_tools if anthropic_tools else None,
                temperature=temperature,
            )
            
            # Track usage
            if hasattr(response, 'usage'):
                self.usage.add(
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
            
            # Parse response
            text = ""
            tool_calls = []
            
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    ))
            
            # Determine finish reason
            finish_reason = "stop"
            if response.stop_reason == "tool_use":
                finish_reason = "tool_use"
            elif response.stop_reason == "max_tokens":
                finish_reason = "length"
            
            return GenerationResult(
                text=text,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
            
        except Exception as e:
            logger.error(f"Anthropic tool calling error: {e}")
            raise
    
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Claude."""
        client = self._get_client()
        system_prompt, anthropic_messages = self._prepare_messages(messages)
        
        try:
            async with client.messages.stream(
                model=self._model,
                max_tokens=max_tokens or 4096,
                system=system_prompt if system_prompt else None,
                messages=anthropic_messages,
                temperature=temperature,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
                    
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise
    
    async def embed(self, text: str) -> list[float]:
        """Anthropic doesn't support embeddings - raise error."""
        raise NotImplementedError(
            "Anthropic does not support embeddings. "
            "Use Gemini for embeddings."
        )
    
    def is_available(self) -> bool:
        """Check if Anthropic is properly configured."""
        return bool(self._api_key)
    
    def supports_tools(self) -> bool:
        """Anthropic Claude supports native tool calling."""
        return True
    
    def supports_embeddings(self) -> bool:
        return False
    
    def supports_vision(self) -> bool:
        """Claude supports vision/image analysis."""
        return True
    
    async def get_usage_report(self, days: int = 7) -> Optional[AdminUsageReport]:
        """Fetch usage report from Anthropic Admin API.
        
        Args:
            days: Number of days to look back (default 7).
        
        Returns:
            AdminUsageReport or None if API call fails.
        
        See: https://platform.claude.com/docs/en/api/admin/usage_report/retrieve_messages
        """
        try:
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=days)
            
            url = "https://api.anthropic.com/v1/organizations/usage_report/messages"
            params = {
                "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ending_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bucket_width": "1d",
            }
            headers = {
                "X-Api-Key": self._admin_api_key,
                "anthropic-version": "2023-06-01",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=30)
                
                if response.status_code == 403:
                    logger.warning("Admin API access denied - may need admin API key")
                    return None
                
                response.raise_for_status()
                data = response.json()
            
            # Aggregate results
            report = AdminUsageReport(
                period_start=start.strftime("%Y-%m-%d"),
                period_end=now.strftime("%Y-%m-%d"),
            )
            
            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
                    report.uncached_input_tokens += result.get("uncached_input_tokens", 0)
                    report.output_tokens += result.get("output_tokens", 0)
                    report.cache_read_input_tokens += result.get("cache_read_input_tokens", 0)
                    
                    # Cache creation tokens
                    cache_creation = result.get("cache_creation", {})
                    report.cache_creation_tokens += cache_creation.get("ephemeral_1h_input_tokens", 0)
                    report.cache_creation_tokens += cache_creation.get("ephemeral_5m_input_tokens", 0)
            
            return report
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"Admin API error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch usage report: {e}")
            return None
    
    async def get_cost_report(self, days: int = 7) -> Optional[AdminCostReport]:
        """Fetch cost report from Anthropic Admin API.
        
        Args:
            days: Number of days to look back (default 7).
        
        Returns:
            AdminCostReport or None if API call fails.
        
        See: https://platform.claude.com/docs/en/api/admin/cost_report/retrieve
        """
        try:
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=days)
            
            url = "https://api.anthropic.com/v1/organizations/cost_report"
            params = {
                "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ending_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bucket_width": "1d",
                "group_by[]": "description",
            }
            headers = {
                "X-Api-Key": self._admin_api_key,
                "anthropic-version": "2023-06-01",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=30)
                
                if response.status_code == 403:
                    logger.warning("Admin API access denied - may need admin API key")
                    return None
                
                response.raise_for_status()
                data = response.json()
            
            # Aggregate costs
            report = AdminCostReport(
                period_start=start.strftime("%Y-%m-%d"),
                period_end=now.strftime("%Y-%m-%d"),
            )
            
            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
                    amount = float(result.get("amount", 0))
                    report.total_cost_cents += amount
                    report.currency = result.get("currency", "USD")
                    
                    # Track breakdown by model/type
                    model = result.get("model", "unknown")
                    token_type = result.get("token_type", "unknown")
                    key = f"{model}:{token_type}"
                    report.breakdown[key] = report.breakdown.get(key, 0) + amount
            
            return report
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"Admin API error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch cost report: {e}")
            return None