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
    llm_model: str = Field(default="eu.anthropic.claude-sonnet-5-5")
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
    enrichment_llm_model: Optional[str] = Field(
        default=None,
        description="LLM model for the enricher (defaults to llm_model). Can be a cheaper model.",
    )
    enrichment_max_tokens: int = Field(
        default=8192,
        description="Max tokens for enricher LLM responses (wide tables need long JSON).",
    )
    doc_enricher_model: Optional[str] = Field(
        default=None,
        description="Multimodal Claude model for the documentation enricher (defaults to llm_model).",
    )
    doc_enricher_max_tokens: int = Field(default=16000, ge=1024)
    doc_max_upload_mb: int = Field(default=25, ge=1, description="Total size of one upload batch.")
    doc_max_text_chars: int = Field(default=200_000, ge=1000, description="Per text document.")
    enrichment_column_batch_size: int = Field(
        default=20,
        description=(
            "Max columns described per enricher LLM call; wider tables are split into balanced "
            "batches so the JSON never hits the output limit. 0 disables batching."
        ),
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
        default="",
        description="Demo profile (maps to demos/<profile>/); empty = generic rules only.",
    )
    profiles_dir: str = Field(
        default="demos",
        description="Directory containing demo profiles (<profiles_dir>/<profile>/profile.yaml).",
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
    max_result_rows: int = Field(
        default=50_000,
        description="Hard cap of rows materialised per query; beyond it the result is truncated.",
    )
    result_page_size: int = Field(default=50, ge=1, description="Default rows per result page.")
    result_page_size_max: int = Field(
        default=250, ge=1, description="Largest page a client may ask."
    )
    result_cache_ttl_seconds: int = Field(
        default=900, ge=1, description="Idle time after which a stored result expires."
    )
    result_cache_max_entries: int = Field(
        default=20, ge=1, description="Stored results kept in memory (least recently used evicted)."
    )

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
