from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

import boto3
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from ..config import LLMProvider, settings


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

    async def complete(self, *, system: Optional[str], user: str) -> str:
        if self.provider == LLMProvider.ANTHROPIC:
            return await self._anthropic_complete(system, user)
        if self.provider == LLMProvider.OPENAI:
            return await self._openai_complete(system, user)
        if self.provider == LLMProvider.BEDROCK:
            return await self._bedrock_complete(system, user)
        raise ValueError(f"Unsupported provider {self.provider}")

    async def _anthropic_complete(self, system: Optional[str], user: str) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC api key missing")
        client = AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(
            model=self.model,
            system=system or "",
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text  # type: ignore[index]

    async def _openai_complete(self, system: Optional[str], user: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI api key missing")
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    async def _bedrock_complete(self, system: Optional[str], user: str) -> str:
        body = {
            "messages": [
                *(
                    [{"role": "system", "content": [{"type": "text", "text": system}]}]
                    if system
                    else []
                ),
                {"role": "user", "content": [{"type": "text", "text": user}]},
            ],
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }

        def _invoke() -> str:
            session_kwargs = {"profile_name": self.aws_profile} if self.aws_profile else {}
            session = boto3.Session(**session_kwargs)
            client = session.client("bedrock-runtime", region_name=self.aws_region)
            response = client.invoke_model(
                modelId=self.model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            payload = json.loads(response["body"].read())
            # Bedrock response format: {"output": {"message": {"content": [{"text": "..."}]}}}
            return (
                payload.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
            )

        return await asyncio.to_thread(_invoke)


__all__ = ["LLMClient"]
