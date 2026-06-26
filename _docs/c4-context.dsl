workspace {

    model {
        user = person "User" "A data analyst or business user querying the catalog"

        artoo = softwareSystem "artoo" "Natural-language analytics over PostgreSQL using OpenMetadata and LLMs" {
            chat = container "artoo-chat" "Static chat UI with D3.js chart rendering and table browser" "HTML/JavaScript"
            api = container "artoo-api" "FastAPI backend exposing /api/query, /api/tables, /api/table/{fqn}, /health, and /mcp" "Python, FastAPI"
            enricher = container "artoo-enricher" "CLI that bootstraps governance taxonomy and enriches metadata in OpenMetadata" "Python"
        }

        openmetadata = softwareSystem "OpenMetadata" "Metadata catalog storing schemas, glossary terms, tags, domains, and custom properties"
        postgresql = softwareSystem "PostgreSQL" "Demo data source queried by the API and ingested by OpenMetadata"

        user -> chat "Asks questions and explores tables"
        chat -> api "POST /api/query, GET /api/tables, GET /api/table/{fqn}"
        api -> openmetadata "Fetches schema, constraints, and metadata context"
        api -> postgresql "Runs EXPLAIN and executes SQL"
        enricher -> openmetadata "Bootstraps taxonomy and writes enrichments"
        openmetadata -> postgresql "Ingests metadata from"
    }

    views {
        systemContext artoo "SystemContext" {
            include *
            autolayout lr
        }

        container artoo "Containers" {
            include *
            autolayout lr
        }

        theme default
    }
}
