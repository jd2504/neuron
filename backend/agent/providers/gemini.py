"""Google Gemini LLM provider via google-genai SDK."""

import logging
from collections.abc import AsyncIterator

from pydantic import BaseModel

from google import genai

from backend.agent.llm_client import LLMClient, Message, ModelTier
from backend.config import get_settings

logger = logging.getLogger(__name__)


class GeminiLLMClient(LLMClient):
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        key = api_key or settings.google_api_key
        if not key:
            logger.warning("No GOOGLE_API_KEY set — Gemini calls will fail")
        self._api_key = key
        self._client: genai.Client | None = None
        self._model_light = settings.llm_model_light
        self._model_heavy = settings.llm_model_heavy

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "GOOGLE_API_KEY not set. Add it to .env to use Gemini."
                )
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _select_model(self, tier: ModelTier) -> str:
        return self._model_light if tier == "light" else self._model_heavy

    def _convert_messages(
        self, messages: list[Message]
    ) -> list[dict]:
        """Convert internal Message format to Gemini content format.

        Gemini uses 'model' instead of 'assistant'.
        """
        converted = []
        for msg in messages:
            role = "model" if msg.role == "assistant" else msg.role
            converted.append({"role": role, "parts": [{"text": msg.content}]})
        return converted

    async def generate(
        self,
        messages: list[Message],
        system_prompt: str,
        model_tier: ModelTier = "light",
    ) -> AsyncIterator[str]:
        model = self._select_model(model_tier)
        contents = self._convert_messages(messages)

        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
        )

        stream = await self._get_client().aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def generate_json(
        self,
        messages: list[Message],
        system_prompt: str,
        schema: type[BaseModel],
        model_tier: ModelTier = "light",
    ) -> BaseModel:
        model = self._select_model(model_tier)
        contents = self._convert_messages(messages)

        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=schema,
        )

        response = await self._get_client().aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        return schema.model_validate_json(response.text)
