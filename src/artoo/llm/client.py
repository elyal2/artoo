from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import boto3
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from ..config import LLMProvider, settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMClient:
    provider: LLMProvider
    model: str
    api_key: Optional[str]
    max_tokens: int
    temperature: float
    aws_profile: Optional[str]
    aws_region: Optional[str]

    @classmethod
    def default(cls) -> "LLMClient":
        return cls(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            aws_profile=settings.llm_aws_profile,
            aws_region=settings.llm_aws_region,
        )

    async def complete(
        self,
        *,
        system: Optional[str],
        user: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        effective_model = model or self.model
        effective_tokens = max_tokens or self.max_tokens
        logger.debug(
            "LLM call: provider=%s model=%s max_tokens=%d",
            self.provider.value,
            effective_model,
            effective_tokens,
        )
        if self.provider == LLMProvider.ANTHROPIC:
            return await self._anthropic_complete(system, user, effective_model, effective_tokens)
        if self.provider == LLMProvider.OPENAI:
            return await self._openai_complete(system, user, effective_model, effective_tokens)
        if self.provider == LLMProvider.BEDROCK:
            return await self._bedrock_complete(system, user, effective_model, effective_tokens)
        raise ValueError(f"Unsupported provider {self.provider}")

    async def _anthropic_complete(
        self, system: Optional[str], user: str, model: str, max_tokens: int
    ) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC api key missing")
        client = AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(
            model=model,
            system=system or "",
            max_tokens=max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text  # type: ignore[index]

    async def _openai_complete(
        self, system: Optional[str], user: str, model: str, max_tokens: int
    ) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI api key missing")
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def _is_anthropic_model(self, model: str) -> bool:
        return "anthropic" in model or "claude" in model

    async def _bedrock_complete(
        self, system: Optional[str], user: str, model: str, max_tokens: int
    ) -> str:
        if self._is_anthropic_model(model):
            body = self._bedrock_anthropic_body(system, user, max_tokens)
        else:
            body = self._bedrock_nova_body(system, user, max_tokens)

        def _invoke() -> str:
            session_kwargs = {"profile_name": self.aws_profile} if self.aws_profile else {}
            session = boto3.Session(**session_kwargs)
            client = session.client("bedrock-runtime", region_name=self.aws_region)
            response = client.invoke_model(
                modelId=model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            payload = json.loads(response["body"].read())
            if self._is_anthropic_model(model):
                return payload.get("content", [{}])[0].get("text", "")
            return (
                payload.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
            )

        return await asyncio.to_thread(_invoke)

    def _bedrock_anthropic_body(self, system: Optional[str], user: str, max_tokens: int) -> dict:
        messages = [{"role": "user", "content": user}]
        body: dict = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system
        return body

    def _bedrock_nova_body(self, system: Optional[str], user: str, max_tokens: int) -> dict:
        body: dict = {
            "messages": [
                {"role": "user", "content": [{"text": user}]},
            ],
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": self.temperature,
            },
        }
        if system:
            body["system"] = [{"text": system}]
        return body


__all__ = ["LLMClient"]
