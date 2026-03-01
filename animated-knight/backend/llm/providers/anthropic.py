"""Anthropic Claude provider implementation."""

import time
from typing import AsyncIterator

import httpx

from backend.core import get_settings
from backend.llm.provider import LLMConfig, LLMProvider, LLMResponse
from backend.llm.registry import register_provider


@register_provider("anthropic")
class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using their HTTP API."""

    BASE_URL = "https://api.anthropic.com/v1"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or get_settings().anthropic_api_key
        if not self._api_key:
            raise ValueError("Anthropic API key not configured")

    @property
    def name(self) -> str:
        return "anthropic"

    def _get_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    async def complete(self, prompt: str, config: LLMConfig | None = None) -> LLMResponse:
        config = config or LLMConfig(model="claude-3-sonnet-20240229")
        start_time = time.time()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/messages",
                headers=self._get_headers(),
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        return LLMResponse(
            content=content,
            model=data.get("model", config.model),
            finish_reason=data.get("stop_reason"),
            usage=data.get("usage"),
            provider=self.name,
            latency_ms=latency_ms,
        )

    async def stream(
        self, prompt: str, config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        config = config or LLMConfig(model="claude-3-sonnet-20240229")

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.BASE_URL}/messages",
                headers=self._get_headers(),
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "stream": True,
                },
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        import json

                        try:
                            event = json.loads(data)
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            continue

    async def complete_chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Native chat completion for Anthropic."""
        config = config or LLMConfig(model="claude-3-sonnet-20240229")
        start_time = time.time()

        # Extract system message if present
        system = None
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)

        body = {
            "model": config.model,
            "messages": chat_messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/messages",
                headers=self._get_headers(),
                json=body,
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        return LLMResponse(
            content=content,
            model=data.get("model", config.model),
            finish_reason=data.get("stop_reason"),
            usage=data.get("usage"),
            provider=self.name,
            latency_ms=latency_ms,
        )
