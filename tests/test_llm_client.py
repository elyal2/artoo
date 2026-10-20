import pytest

from artoo.config import LLMProvider
from artoo.llm.client import LLMClient


def _make_client() -> LLMClient:
    return LLMClient(
        provider=LLMProvider.BEDROCK,
        model="eu.amazon.nova-lite-v1:0",
        api_key=None,
        max_tokens=512,
        temperature=0.2,
        aws_profile=None,
        aws_region="eu-south-2",
    )


def test_is_anthropic_model_claude():
    client = _make_client()
    assert client._is_anthropic_model("eu.anthropic.claude-sonnet-4-20250514")
    assert client._is_anthropic_model("anthropic.claude-v2")
    assert client._is_anthropic_model("us.anthropic.claude-3-5-sonnet-20241022-v2:0")


def test_is_anthropic_model_nova():
    client = _make_client()
    assert not client._is_anthropic_model("eu.amazon.nova-lite-v1:0")
    assert not client._is_anthropic_model("amazon.nova-pro-v1:0")


def test_bedrock_anthropic_body():
    client = _make_client()
    body = client._bedrock_anthropic_body("You are helpful.", "Hello", 1024)
    assert body["anthropic_version"] == "bedrock-2023-05-31"
    assert body["max_tokens"] == 1024
    assert body["temperature"] == 0.2
    assert body["system"] == "You are helpful."
    assert body["messages"] == [{"role": "user", "content": "Hello"}]


def test_bedrock_anthropic_body_no_system():
    client = _make_client()
    body = client._bedrock_anthropic_body(None, "Hello", 2048)
    assert "system" not in body
    assert body["messages"] == [{"role": "user", "content": "Hello"}]


def test_bedrock_nova_body():
    client = _make_client()
    body = client._bedrock_nova_body("System prompt", "User input", 512)
    assert body["messages"] == [{"role": "user", "content": [{"text": "User input"}]}]
    assert body["system"] == [{"text": "System prompt"}]
    assert body["inferenceConfig"]["maxTokens"] == 512
    assert body["inferenceConfig"]["temperature"] == 0.2


def test_bedrock_nova_body_no_system():
    client = _make_client()
    body = client._bedrock_nova_body(None, "User input", 512)
    assert "system" not in body


def test_claude5_models_omit_temperature() -> None:
    from artoo.config import LLMProvider
    from artoo.llm.client import LLMClient, supports_temperature

    assert not supports_temperature("eu.anthropic.claude-sonnet-5-5")
    assert not supports_temperature("claude-sonnet-5-5")
    assert supports_temperature("eu.anthropic.claude-sonnet-4-20250514-v1:0")
    assert supports_temperature("eu.amazon.nova-lite-v1:0")
    c = LLMClient(LLMProvider.BEDROCK, "m", None, 100, 0.2, None, "eu-south-2")
    assert "temperature" not in c._bedrock_anthropic_body(
        "s", "u", 10, "eu.anthropic.claude-sonnet-5-5"
    )
    assert (
        c._bedrock_anthropic_body("s", "u", 10, "eu.anthropic.claude-sonnet-4-x")["temperature"]
        == 0.2
    )


@pytest.mark.asyncio
async def test_bedrock_anthropic_skips_non_text_blocks(monkeypatch) -> None:  # noqa: ANN001
    import io
    import json as _json

    from artoo.config import LLMProvider
    from artoo.llm import client as mod

    payload = {
        "content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ],
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }

    class FakeBedrock:
        def invoke_model(self, **kw):  # noqa: ANN003, ANN201
            return {"body": io.BytesIO(_json.dumps(payload).encode())}

    class FakeSession:
        def __init__(self, **kw) -> None:  # noqa: ANN003
            pass

        def client(self, *a, **kw):  # noqa: ANN002, ANN003, ANN201
            return FakeBedrock()

    monkeypatch.setattr(mod.boto3, "Session", FakeSession)
    c = mod.LLMClient(
        LLMProvider.BEDROCK, "eu.anthropic.claude-sonnet-5-5", None, 100, 0.2, None, "eu-south-2"
    )
    assert await c.complete(system=None, user="hi") == "hello world"
