"""LLM provider registry for runtime provider lookup."""

from typing import Type

from .provider import LLMProvider


class ProviderRegistry:
    """Registry for LLM providers, allowing runtime lookup and switching."""

    _providers: dict[str, Type[LLMProvider]] = {}
    _instances: dict[str, LLMProvider] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type[LLMProvider]) -> None:
        """Register a provider class."""
        cls._providers[name.lower()] = provider_class

    @classmethod
    def get(cls, name: str, **kwargs) -> LLMProvider:
        """
        Get a provider instance by name.

        Instances are cached and reused.
        """
        name = name.lower()

        if name not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unknown provider: {name}. Available: {available}")

        # Create cache key including kwargs
        cache_key = f"{name}:{hash(frozenset(kwargs.items()))}"

        if cache_key not in cls._instances:
            cls._instances[cache_key] = cls._providers[name](**kwargs)

        return cls._instances[cache_key]

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._providers.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a provider is registered."""
        return name.lower() in cls._providers

    @classmethod
    def clear_instances(cls) -> None:
        """Clear all cached instances (useful for testing)."""
        cls._instances.clear()


def register_provider(name: str):
    """Decorator to register a provider class."""

    def decorator(cls: Type[LLMProvider]) -> Type[LLMProvider]:
        ProviderRegistry.register(name, cls)
        return cls

    return decorator


def get_provider(name: str, **kwargs) -> LLMProvider:
    """Convenience function to get a provider instance."""
    return ProviderRegistry.get(name, **kwargs)
