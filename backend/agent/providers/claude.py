"""Anthropic Claude LLM provider via anthropic SDK."""

import logging
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from backend.agent.llm_client import LLMClient, Message, ModelTier
from backend.config import get_settings

logger = logging.getLogger(__name__)


class ClaudeLLMClient(LLMClient):
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        key = api_key or settings.anthropic_api_key
        self._client = AsyncAnthropic(api_key=key)
        self._model_light = settings.llm_model_light
        self._model_heavy = settings.llm_model_heavy

    def _select_model(self, tier: ModelTier) -> str:
        return self._model_light if tier == "light" else self._model_heavy

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert to Anthropic message format (role stays as-is)."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(
        self,
        messages: list[Message],
        system_prompt: str,
        model_tier: ModelTier = "light",
    ) -> AsyncIterator[str]:
        model = self._select_model(model_tier)
        converted = self._convert_messages(messages)

        async with self._client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=converted,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_json(
        self,
        messages: list[Message],
        system_prompt: str,
        schema: type[BaseModel],
        model_tier: ModelTier = "light",
    ) -> BaseModel:
        model = self._select_model(model_tier)

        # Instruct Claude to return JSON matching the schema
        json_prompt = (
            f"{system_prompt}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n"
            f"{schema.model_json_schema()}"
        )
        converted = self._convert_messages(messages)

        response = await self._client.messages.create(
            model=model,
            max_tokens=4096,
            system=json_prompt,
            messages=converted,
        )

        text = response.content[0].text
        return schema.model_validate_json(text)
