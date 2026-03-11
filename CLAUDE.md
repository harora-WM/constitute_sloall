# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A **Conversational SLO (Service Level Objective) Manager** using AWS Bedrock Claude Sonnet 4.5 in a **two-layer LLM architecture**: intent classification → multi-source data fetching → conversational response generation.

## Development Commands

```bash
# Setup
source .venv/bin/activate
pip install -r requirements.txt

# Interactive CLI (must run from project root)
python main.py

# FastAPI server (must run from project root)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

# Generate services.yaml from ClickHouse (run when services change)
python fetch_services.py

# Test all adapters end-to-end (requires live credentials)
python test_new_adapters.py

# Test components individually
python utils/service_matcher.py "dashboard-stats"
python llm_response_generator.py
cd intent_classifier && python intent_classifier.py
cd context_adapter && python memory_adapter.py
cd context_adapter && python java_stats.py
cd context_adapter && python alret_count.py
cd context_adapter && python change_pre_post.py
```

**CLI commands inside the interactive loop:** `export`, `help`, `quit`/`exit`

**CRITICAL:** All commands must be run from the project root. The intent classifier uses relative paths (via `__file__`) to load YAML configs in `intent_classifier/`.

## FastAPI Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness/readiness probe. Returns 503 if orchestrator failed to initialize. |
| POST | `/query` | Submit a natural language SLO query. Body: `QueryRequest` (`query`, `app_id`, `project_id`). Typical latency: 8–15s (two LLM calls + parallel data fetches). |

**Do NOT run FastAPI with more than 1 worker** — boto3 clients are stateful and multiple workers cause Bedrock rate limit issues. Always use `--workers 1`.

## Architecture

### End-to-End Flow

```
User Query
  -> Step 1: Intent Classification (LLM Call #1, intent_classifier.py)
      Extracts: primary_intent, secondary_intents, enriched_intents,
                entities (service, time_range), data_sources, timestamps
  -> Step 2: Service Resolution (service_matcher.py)
      Fuzzy match service name -> service_id using services.yaml
  -> Step 3: Data Fetching (parallel)
      java_stats_api  -- if 'java_stats_api' in data_sources (intent-routed)
      clickhouse      -- if 'clickhouse' in data_sources (all 76 patterns, no filtering)
      alerts_count    -- ALWAYS fetched (regardless of intent)
      change_impact   -- ALWAYS fetched (regardless of intent)
  -> Step 4: Conversational Response (LLM Call #2, llm_response_generator.py)
      Input: full orchestrator output
      Output: natural language answer
  -> Auto-export: slo_result_{start_timestamp}.json
```

### Core Components

**`config.py`** — Single source of truth for all configuration. Loads `.env` using its own `__file__` path (works from any working directory). Every adapter and `main.py` imports this instead of calling `os.getenv()` directly.

**`main.py`** — Contains `SLOOrchestrator` class, `main()` interactive CLI, and the FastAPI `app` instance. `app_id` and `project_id` come from `config.APP_ID` / `config.PROJECT_ID` for CLI; for API they come from the request body (defaulting to the same config values if not supplied).

**`intent_classifier/intent_classifier.py`** — Layer 1 LLM (AWS Bedrock). Outputs primary/secondary/enriched intents, entities, data_sources list, and UTC millisecond timestamps. Config files: `intent_categories.yaml` (9 categories, 50+ intents), `enrichment_rules.yaml`, `data_sources.yaml`.

**`context_adapter/java_stats.py`** — Fetches real-time SLO metrics from Watermelon API via Keycloak auth. Routes by **primary intent first**, then falls back to secondary/enriched:
- `CURRENT_HEALTH` -> `get_current_health()` -> 4 arrays (unhealthy_eb, at_risk_eb, unhealthy_response, at_risk_response)
- `SERVICE_HEALTH` -> `get_service_health(service_id)` -> same 4 arrays for one service (returns None if no service_id)
- `ERROR_BUDGET_STATUS` -> `get_error_budget_status()` -> 3 arrays (unhealthy_eb, at_risk_eb, healthy_eb)

**`context_adapter/memory_adapter.py`** — Fetches historical behavior patterns from ClickHouse `ai_service_behavior_memory` table. Returns **ALL** patterns for the given `app_id` with no time or intent filtering. Currently 76 patterns for app 31854.

**`context_adapter/alret_count.py`** — Fetches alert action counts from `wmerrorbudgetalertandnotificationservice` API via Keycloak auth. Always called by orchestrator for the full query time window, SLO types `["ERROR", "RESPONSE"]`. Entry point: `fetch_alerts_for_orchestrator()`.

**`context_adapter/change_pre_post.py`** — Fetches the latest deployment change (from `wmebonboarding` release-histories API) and top-5 EB/RESPONSE deviations pre/post that release (from `wmerrorbudgetstatisticsservice`). Always called by orchestrator. Entry point: `fetch_change_impact_for_orchestrator()`.

**`llm_response_generator.py`** — Layer 2 LLM (AWS Bedrock). Receives complete orchestrator output and generates a conversational response as "SLO Advisor". System prompt defines interpretation of health status, burn rates, pattern types, and deviation data.

**`api_models.py`** — Pydantic v2 request/response models. `QueryRequest` takes `query`, `app_id` (default `31854`), and `project_id` (default `215853`). `data` field in `QueryResponse` is `Dict[str, Any]` since each adapter returns a different schema.

**`utils/service_matcher.py`** — Fuzzy matching via `SequenceMatcher`. Loads `services.yaml` (125 services). Threshold: 0.3; substring matches boosted to 0.7. Returns ranked results with similarity scores.

**`utils/time_range_resolver.py`** / **`intent_classifier/timestamp.py`** — Two equivalent implementations for converting natural language time ranges to UTC milliseconds. "current" = last 1 hour. Index granularity: HOURLY (<=3 days), DAILY (>3 days). Always milliseconds.

## Data Sources

| Source | Triggered | Description |
|--------|-----------|-------------|
| `java_stats_api` | If in `data_sources` from intent | Real-time SLO metrics; primary intent routes to correct function |
| `clickhouse` | If in `data_sources` from intent | All 76 historical behavior patterns; no time/intent filtering |
| `alerts_count` | Always | Alert action counts for query time window |
| `change_impact` | Always | Latest deployment + top-5 EB/RESPONSE deviations pre/post release |
| `postgres` | Not implemented | Planned for SLO definitions |
| `opensearch` | Not implemented | Planned for logs/traces |

### ClickHouse Tables
- `ai_service_behavior_memory` — behavior patterns (76 records, app 31854)
- `ai_service_features_hourly` — service inventory (source for `services.yaml`)

## Environment Variables (.env)

All configuration lives in `.env` and is loaded centrally by `config.py`. No credentials are hardcoded in any adapter.

```bash
# AWS Bedrock
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0

# Layer 1 LLM (intent classification)
MAX_TOKENS=500
TEMPERATURE=0.0

# Layer 2 LLM (response generation)
RESPONSE_MAX_TOKENS=2000
RESPONSE_TEMPERATURE=0.3

# Keycloak
KEYCLOAK_URL=https://wm-sandbox-auth-1.watermelon.us/realms/watermelon/protocol/openid-connect/token
KEYCLOAK_CLIENT_ID=web_app

# Adapter API URLs (full URLs, no base URL construction in code)
JAVA_STATS_API_URL=https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/transactions/distinct/top-5/ALL
ALERTS_COUNT_API_URL=https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetalertandnotificationservice/api/alerts-action/count
RELEASE_HISTORIES_API_URL=https://wm-sandbox-1.watermelon.us/services/wmebonboarding/api/release-histories/application
RELEASE_IMPACT_API_URL=https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/release-impact/transactions/top-5/POST

# Credentials (shared across Java Stats, Alerts, Change Impact adapters)
USERNAME=wmadmin
PASSWORD=your_password

# Application defaults (overridden per-request via FastAPI body)
APP_ID=31854
PROJECT_ID=215853

# Java Stats pagination
JAVA_STATS_PAGE_SIZE=2000

# Change impact analysis windows
CHANGE_POST_PERIOD=DAY
CHANGE_POST_PERIOD_DURATION=18
CHANGE_PRE_PERIOD=DAY
CHANGE_PRE_PERIOD_DURATION=15

# ClickHouse
CLICKHOUSE_URL=http://ec2-47-129-241-41.ap-southeast-1.compute.amazonaws.com:8123
CLICKHOUSE_USERNAME=wm_test
CLICKHOUSE_PASSWORD=your_password
CLICKHOUSE_DATABASE=metrics

# OpenSearch (adapter not yet integrated)
OPENSEARCH_HOST=your_host
OPENSEARCH_PORT=9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=your_password
OPENSEARCH_USE_SSL=False
OPENSEARCH_PAGE_SIZE=5000
```

**Note on `RELEASE_HISTORIES_API_URL`:** the `application_id` is appended dynamically in code (`f"{config.RELEASE_HISTORIES_API_URL}/{application_id}"`) since it varies per request.

## Common Gotchas

**Java Stats returns None for SERVICE_HEALTH:** Requires a service_id — only triggers when a service name is mentioned and successfully matched.

**Wrong arrays from Java Stats:** CURRENT_HEALTH must return 4 arrays. If only 3 are returned, ERROR_BUDGET_STATUS is being used instead. Primary intent takes precedence — check intent classification output.

**Memory adapter returns 0 records:** Verify ClickHouse connectivity and that `app_id = 31854` has data. (Note: services.yaml is not required for memory adapter — it's used for service name matching only.)

**Intent classifier fails:** Must run from project root. Verify AWS credentials and `BEDROCK_MODEL_ID` in `.env`.

**Import errors on startup:** Ensure `__init__.py` files exist in `intent_classifier/`, `context_adapter/`, and `utils/`.

**`context_adapter/intent_based_queries.py`** is no longer used — `memory_adapter.py` now fetches all patterns directly without intent-based dispatch. The file still exists in the repo but is not imported anywhere.

**Adding a new adapter:** import `config` at the top (with the `sys.path.insert` pattern used in existing adapters), add any new URLs/credentials to `.env` and `config.py`, then wire the entry-point function into `SLOOrchestrator.process_query()` in `main.py`.
