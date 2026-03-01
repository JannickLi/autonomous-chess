"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LLMConfig:
    """Configuration for LLM requests."""

    model: str = "mistral-medium"
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    stop_sequences: list[str] = field(default_factory=list)

    # Provider-specific options
    extra: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    finish_reason: str | None = None
    usage: dict | None = None

    # For tracking
    provider: str = ""
    latency_ms: float = 0.0


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the provider name."""
        ...

    @abstractmethod
    async def complete(self, prompt: str, config: LLMConfig | None = None) -> LLMResponse:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: The input prompt
            config: Optional configuration overrides

        Returns:
            LLMResponse with the generated content
        """
        ...

    @abstractmethod
    async def stream(
        self, prompt: str, config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        """
        Stream a completion for the given prompt.

        Args:
            prompt: The input prompt
            config: Optional configuration overrides

        Yields:
            String chunks of the generated content
        """
        ...

    async def complete_chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """
        Generate a completion for a chat conversation.

        Default implementation converts to a single prompt.
        Providers can override for native chat support.

        Args:
            messages: List of messages with 'role' and 'content'
            config: Optional configuration overrides

        Returns:
            LLMResponse with the generated content
        """
        # Default: convert messages to a prompt string
        prompt = self._messages_to_prompt(messages)
        return await self.complete(prompt, config)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a completion for a chat conversation.

        Default implementation converts to a single prompt.
        Providers can override for native chat support.
        """
        prompt = self._messages_to_prompt(messages)
        async for chunk in self.stream(prompt, config):
            yield chunk

    def _messages_to_prompt(self, messages: list[dict[str, str]]) -> str:
        """Convert chat messages to a single prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"Human: {content}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    def validate_config(self, config: LLMConfig) -> tuple[bool, str | None]:
        """
        Validate configuration for this provider.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if config.temperature < 0 or config.temperature > 2:
            return False, "Temperature must be between 0 and 2"
        if config.max_tokens < 1:
            return False, "max_tokens must be at least 1"
        if config.top_p < 0 or config.top_p > 1:
            return False, "top_p must be between 0 and 1"
        return True, None
