FROM python:3.12-slim AS base
ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (dependency manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app
COPY pyproject.toml ./

RUN uv pip install --system .

COPY src ./src
COPY demos ./demos
COPY openmetadata ./openmetadata
COPY _docs ./_docs
COPY .env.example ./.env.example

# --- Enricher image ---
FROM base AS enricher
CMD ["uv", "run", "python", "-m", "artoo.enricher"]

# --- API image ---
FROM base AS api
CMD ["uv", "run", "uvicorn", "artoo.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
