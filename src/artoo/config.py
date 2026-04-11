from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    BEDROCK = "bedrock"


class Settings(BaseSettings):
    """Global application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_file=(".env.local", ".env"), env_file_encoding="utf-8")

    # LLM
    llm_provider: LLMProvider = Field(default=LLMProvider.BEDROCK)
    llm_model: str = Field(default="eu.amazon.nova-lite-v1:0")
    llm_api_key: Optional[str] = Field(default=None)
    llm_aws_profile: Optional[str] = Field(default=None)
    llm_aws_region: Optional[str] = Field(default="eu-south-2")
    llm_max_tokens: int = Field(default=1024)
    llm_temperature: float = Field(default=0.2)

    # PostgreSQL (shared with OpenMetadata Postgres compose)
    postgres_dsn: str = Field(
        default="postgresql://artoo_demo:artoo_demo@postgresql:5432/hotel_demo"
    )
    postgres_password: Optional[str] = Field(default=None)

    # OpenMetadata
    openmetadata_url: str = Field(default="http://openmetadata-server:8585")
    openmetadata_api_token: Optional[str] = Field(default=None)

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
