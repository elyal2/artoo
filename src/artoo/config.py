from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    BEDROCK = "bedrock"


class Settings(BaseSettings):
    """Global application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: LLMProvider = Field(default=LLMProvider.BEDROCK)
    llm_model: str = Field(default="eu.amazon.nova-lite-v1:0")
    llm_intent_model: Optional[str] = Field(
        default=None,
        description="LLM model for intent classification (defaults to llm_model). Use a more capable model for better conversational/data_query routing.",
    )
    llm_explanation_model: Optional[str] = Field(
        default=None,
        description="LLM model for result explanation (defaults to llm_model). Use a more capable model for better interpretations of complex queries.",
    )
    llm_chart_model: Optional[str] = Field(
        default=None,
        description="LLM model for chart visualization (defaults to llm_model). Use a more capable model like Claude Sonnet for better charts.",
    )
    llm_chart_max_tokens: int = Field(
        default=4096,
        description="Max tokens for chart LLM responses (needs more for D3 code generation).",
    )
    llm_api_key: Optional[str] = Field(default=None)
    llm_aws_profile: Optional[str] = Field(default=None)
    llm_aws_region: Optional[str] = Field(default="eu-south-2")
    llm_max_tokens: int = Field(default=1024)
    llm_temperature: float = Field(default=0.2)

    # PostgreSQL (shared with OpenMetadata Postgres compose)
    demo_profile: str = Field(
        default="hotel",
        description="Demo data profile to load (maps to demos/<profile>/).",
    )
    postgres_dsn: str = Field(
        default="postgresql://artoo_demo:artoo_demo@postgresql:5432/artoo_demo"
    )
    postgres_password: Optional[str] = Field(default=None)

    # OpenMetadata
    openmetadata_url: str = Field(default="http://openmetadata-server:8585")
    openmetadata_api_token: Optional[str] = Field(default=None)
    openmetadata_service_name: str = Field(
        default="artoo-postgres",
        description="Name of the database service registered in OpenMetadata.",
    )
    openmetadata_db_filter: Optional[str] = Field(
        default=None,
        description="Optional database FQN prefix to filter tables returned by OpenMetadata (e.g. 'my-service.my_db'). If unset, all tables are returned.",
    )

    # API settings
    api_port: int = Field(default=8000)
    query_timeout_seconds: int = Field(default=10)
    max_result_rows: int = Field(default=100)

    # Enricher settings
    sample_rows: int = Field(default=5)
    enrichment_concurrency: int = Field(default=3)

    # Logging
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")


settings = Settings()


def _extract_db_name(dsn: str) -> str:
    path = urlparse(dsn).path.lstrip("/")
    return path.split("/")[0] if path else "artoo_demo"
