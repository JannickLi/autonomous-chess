"""Mistral AI provider implementation."""

import time
from typing import AsyncIterator

import httpx

from backend.core import get_settings
from backend.llm.provider import LLMConfig, LLMProvider, LLMResponse
from backend.llm.registry import register_provider


@register_provider("mistral")
class MistralProvider(LLMProvider):
    """Mistral AI provider using their HTTP API."""

    BASE_URL = "https://api.mistral.ai/v1"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or get_settings().mistral_api_key
        if not self._api_key:
            raise ValueError("Mistral API key not configured")

    @property
    def name(self) -> str:
        return "mistral"

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def complete(self, prompt: str, config: LLMConfig | None = None) -> LLMResponse:
        config = config or LLMConfig()
        start_time = time.time()

        messages = [{"role": "user", "content": prompt}]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": config.model,
                    "messages": messages,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "top_p": config.top_p,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", config.model),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
            provider=self.name,
            latency_ms=latency_ms,
        )

    async def stream(
        self, prompt: str, config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        config = config or LLMConfig()

        messages = [{"role": "user", "content": prompt}]

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.BASE_URL}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": config.model,
                    "messages": messages,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "top_p": config.top_p,
                    "stream": True,
                },
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        import json

                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

    async def complete_chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Native chat completion for Mistral."""
        config = config or LLMConfig()
        start_time = time.time()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": config.model,
                    "messages": messages,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "top_p": config.top_p,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", config.model),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
            provider=self.name,
            latency_ms=latency_ms,
        )
