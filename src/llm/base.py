"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator, Any


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class GenerationResult:
    """Result from generate_with_tools."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # "stop", "tool_use", "length"
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class ToolDefinition:
    """Definition of a tool for the LLM."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema format
    
    def to_anthropic_format(self) -> dict:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
    
    def to_gemini_format(self) -> dict:
        """Convert to Gemini function declaration format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the provider name (e.g., 'gemini', 'anthropic')."""
        ...
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the current model name."""
        ...
    
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a response from the LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in response.
        
        Returns:
            The generated text response.
        """
        ...
    
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """Generate a response with tool calling support.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            tools: List of tool definitions available to the model.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in response.
        
        Returns:
            GenerationResult with text and/or tool calls.
        """
        # Default implementation for providers that don't support tools
        text = await self.generate(messages, temperature, max_tokens)
        return GenerationResult(text=text)
    
    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in response.
        
        Yields:
            Text chunks as they are generated.
        """
        ...
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is properly configured and available."""
        ...
    
    def supports_tools(self) -> bool:
        """Check if this provider supports native tool/function calling."""
        return False
    
    def supports_vision(self) -> bool:
        """Check if this provider supports image/vision input."""
        return False
