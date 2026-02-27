"""Provider-agnostic LLM interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel


class Message(BaseModel):
    """Internal message format. Providers convert at their boundary."""

    role: Literal["user", "assistant"]
    content: str


ModelTier = Literal["light", "heavy"]


class LLMClient(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        system_prompt: str,
        model_tier: ModelTier = "light",
    ) -> AsyncIterator[str]:
        """Stream text chunks from the LLM."""
        ...

    @abstractmethod
    async def generate_json(
        self,
        messages: list[Message],
        system_prompt: str,
        schema: type[BaseModel],
        model_tier: ModelTier = "light",
    ) -> BaseModel:
        """Generate a structured JSON response matching the given schema."""
        ...


def get_llm_client(provider: str, **kwargs) -> LLMClient:
    """Factory: instantiate the correct provider. Lazy imports."""
    if provider == "gemini":
        from backend.agent.providers.gemini import GeminiLLMClient

        return GeminiLLMClient(**kwargs)
    elif provider == "claude":
        from backend.agent.providers.claude import ClaudeLLMClient

        return ClaudeLLMClient(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
