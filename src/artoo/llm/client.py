from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import boto3  # type: ignore[import-untyped]
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from ..config import LLMProvider, settings

logger = logging.getLogger(__name__)


def supports_temperature(model: str) -> bool:
    """Claude 5.x models reject the `temperature` parameter (ValidationException)."""
    return re.search(r"claude-(?:sonnet|opus|haiku|fable)-5", model) is None


def _log_usage(model: str, input_tokens: Any, output_tokens: Any) -> None:
    logger.info(
        "LLM usage",
        extra={"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens},
    )


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
        kwargs: dict[str, Any] = {}
        if supports_temperature(model):
            kwargs["temperature"] = self.temperature
        response = await client.messages.create(
            model=model,
            system=system or "",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        _log_usage(model, response.usage.input_tokens, response.usage.output_tokens)
        return "".join(b.text for b in response.content if b.type == "text")

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
        if response.usage:
            _log_usage(model, response.usage.prompt_tokens, response.usage.completion_tokens)
        return response.choices[0].message.content or ""

    def _is_anthropic_model(self, model: str) -> bool:
        return "anthropic" in model or "claude" in model

    async def _bedrock_complete(
        self, system: Optional[str], user: str, model: str, max_tokens: int
    ) -> str:
        if self._is_anthropic_model(model):
            body = self._bedrock_anthropic_body(system, user, max_tokens, model)
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
            usage = payload.get("usage", {})
            _log_usage(
                model,
                usage.get("input_tokens", usage.get("inputTokens")),
                usage.get("output_tokens", usage.get("outputTokens")),
            )
            if self._is_anthropic_model(model):
                # Claude 5.x may return non-text blocks (e.g. thinking) before the text block
                return "".join(
                    str(b.get("text", ""))
                    for b in payload.get("content", [])
                    if b.get("type", "text") == "text"
                )
            return str(
                payload.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
            )

        return await asyncio.to_thread(_invoke)

    def _bedrock_anthropic_body(
        self, system: Optional[str], user: str, max_tokens: int, model: str = ""
    ) -> dict[str, Any]:
        messages = [{"role": "user", "content": user}]
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if supports_temperature(model):
            body["temperature"] = self.temperature
        if system:
            body["system"] = system
        return body

    def _bedrock_nova_body(
        self, system: Optional[str], user: str, max_tokens: int
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
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
