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
