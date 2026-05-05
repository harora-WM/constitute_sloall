# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A **Conversational SLO (Service Level Objective) Manager** using AWS Bedrock Claude Sonnet 4.6 in a **two-layer LLM architecture**: intent classification → multi-source data fetching → conversational response generation.

## Development Commands

```bash
# Setup
source .venv/bin/activate
pip install -r requirements.txt

# Interactive CLI (must run from project root)
python main.py

# FastAPI server (must run from project root)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

# Streamlit UI — requires FastAPI backend to be running first
streamlit run app.py

# Generate services.yaml manually (auto-runs on every orchestrator startup)
python fetch_services.py

# Integration test: SLOOrchestrator end-to-end + infra_adapter standalone (requires live credentials)
python tests/test_new_adapters.py

# Test components individually
python utils/service_matcher.py "dashboard-stats"
python llm_response_generator.py
cd intent_classifier && python intent_classifier.py
cd intent_classifier && python timestamp.py "show errors in the last 15 minutes"
cd context_adapter && python memory_adapter.py
cd context_adapter && python java_stats.py
cd context_adapter && python alert_count.py
cd context_adapter && python change_pre_post.py
cd context_adapter && python infra_adapter.py
```

**CLI commands inside the interactive loop:** `export`, `help`, `quit`/`exit`

**CRITICAL:** All commands must be run from the project root. The intent classifier uses relative paths (via `__file__`) to load YAML configs in `intent_classifier/`.

## FastAPI Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness/readiness probe. Returns 503 if orchestrator failed to initialize. |
| POST | `/query` | Submit a natural language SLO query. Body: `QueryRequest` (`query`, `app_id`, `project_id`, optional `start_time`, `end_time` in Unix epoch ms). `start_time`/`end_time` are only used when the query contains no time reference; if the query mentions a time expression they are ignored entirely. A minimum 2-hour gap is always enforced. `index` is always auto-calculated (`>3 days → DAILY`, else `HOURLY`). Typical latency: 8–15s (two LLM calls + sequential data fetches). |
| POST | `/query/stream` | Same parameters as `/query`. Returns a Server-Sent Events stream. Event types: `metadata` (once, after data fetching — contains classification, time_resolution, data_sources_used, data), `token` (one per LLM text chunk), `done` (final sanitized full_text), `error` (on failure). Used by the Streamlit UI; the plain `/query` endpoint remains for other clients. |

**Do NOT run FastAPI with more than 1 worker** — boto3 clients are stateful and multiple workers cause Bedrock rate limit issues. Always use `--workers 1`.

## Architecture

### End-to-End Flow

```
User Query
  -> Step 1: Intent Classification (LLM Call #1, intent_classifier.py)
      Extracts: primary_intent, secondary_intents, enriched_intents,
                entities (service only), data_sources, timestamps
  -> Step 2: Service Resolution (service_matcher.py)
      Fuzzy match service name -> service_id using services.yaml
  -> Step 3: Data Fetching (sequential)
      java_stats_api    -- if 'java_stats_api' in data_sources (intent-routed)
      clickhouse        -- if 'clickhouse' in data_sources (all patterns, no filtering)
      change_impact     -- if 'change_impact' in data_sources
      [clickhouse_infra]  -- DISABLED; adapter and intent both commented out
      [alerts_count]      -- DISABLED; adapter and intent both commented out
  -> Step 4: Conversational Response (LLM Call #2, llm_response_generator.py)
      Input: full orchestrator output
      Output: natural language answer
  -> Auto-export: slo_result_{start_timestamp}.json
```

### Core Components

**`config.py`** — Single source of truth for all configuration. Loads `.env` using its own `__file__` path (works from any working directory). All modules — `context_adapter/`, `intent_classifier/`, and `main.py` — import this instead of calling `os.getenv()` directly.

**`main.py`** — Contains `SLOOrchestrator` class, `main()` interactive CLI, and the FastAPI `app` instance. `app_id` and `project_id` come from `config.APP_ID` / `config.PROJECT_ID` for CLI; for API they come from the request body (defaulting to the same config values if not supplied). On every startup, `SLOOrchestrator.__init__()` automatically refreshes `services.yaml` by calling `fetch_services.py` functions before initializing `ServiceMatcher` — no need to run `fetch_services.py` manually. Data fetching logic lives in `_prepare_context()` (intent classification + all adapter calls, returns result dict without LLM response); `process_query()` calls it then calls `generate_response()`. The `/query/stream` endpoint calls `_prepare_context()` directly, sends a `metadata` SSE event, then streams tokens from `generate_response_stream()`.

**`intent_classifier/intent_classifier.py`** — Layer 1 LLM (AWS Bedrock). Outputs primary/secondary/enriched intents, entities (`service` only — no `time_range`/`comparison_range`), data_sources list, and UTC millisecond timestamps. Timestamp resolution calls `timestamp.py` with the raw user query string. Config files: `intent_categories.yaml` (9 active categories: STATE, TREND, PATTERN, CAUSE, IMPACT, ACTION, PREDICT, OPTIMIZE, EVIDENCE; 28 active intents), `enrichment_rules.yaml` (maps primary intents → additional enriched intents to auto-add), `data_sources.yaml`.

Key active enrichment chains that indirectly trigger data sources:
- `ROOT_CAUSE_SINGLE` / `ROOT_CAUSE_MULTI` → enriches `UNDERCURRENTS_TREND` + `MITIGATION_STEPS`; also directly carries `change_impact` in their own data_sources
- `CHANGE_RISK` / `ROLLBACK_ADVICE` → enriches `PRE_POST_CHANGE` + `CHANGE_AUDIT` → both carry `change_impact`
- `SLO_BURN_TREND` → enriches `RISK_PREDICTION` + `CAPACITY_RISK`
- `CAPACITY_RISK` / `PERFORMANCE_BOTTLENECK` → enriches `QUERY_OPTIMIZATION` + `RESOURCE_WASTE` (the `INFRA_METRICS` enrichment in these chains is DISABLED)
- `CURRENT_HEALTH` enrichment to `ALERT_STATUS` / `INCIDENT_STATUS` is DISABLED; `ALERT_DEBUG` intent is DISABLED entirely

All enrichments are resolved in a single flattened pass by `intent_classifier.py` before returning. Multi-hop chains like `RECURRING_INCIDENT → ROOT_CAUSE_SINGLE → UNDERCURRENTS_TREND` work because the pass iterates over the growing set until stable.

**`context_adapter/java_stats.py`** — Fetches real-time SLO metrics from Watermelon API via Keycloak auth. Always calls `fetch_api_data()` → `transform_to_llm_format()`, returning 4 arrays (unhealthy_eb, at_risk_eb, unhealthy_response, at_risk_response) for all services regardless of intent. Service filtering and EB-only views are left to the Layer 2 LLM.

**`context_adapter/memory_adapter.py`** — Fetches historical behavior patterns from ClickHouse `ai_service_behavior_memory` table. When called by the orchestrator, `_fetch_memory_adapter` receives the full `intents` set and routes to `fetch_patterns_by_intent()`. If no intents are provided it falls back to `fetch_behavior_service_memory()` (backward-compat path). Filters by both `app_id` and `project_id` (required). Currently 108 patterns for app 31854 / project 215853.

**`context_adapter/alert_count.py`** — Fetches alert action counts from `wmerrorbudgetalertandnotificationservice` API via Keycloak auth. Called by orchestrator when `alerts_count` appears in `data_sources`, for the full query time window, SLO types `["ERROR", "RESPONSE"]`. Entry point: `fetch_alerts_for_orchestrator()`.

**`context_adapter/change_pre_post.py`** — Fetches the latest deployment change (from `wmebonboarding` release-histories API) and top-5 EB/RESPONSE deviations pre/post that release (from `wmerrorbudgetstatisticsservice`). Called by orchestrator when `change_impact` appears in `data_sources`. Entry point: `fetch_change_impact_for_orchestrator()`.

**`context_adapter/infra_adapter.py`** — Fetches host-level infrastructure metrics (CPU / memory / disk) from ClickHouse table `metrics.infra_data` (collected by SolarWinds and Zabbix). Only triggered when `clickhouse_infra` appears in `data_sources` (i.e. when the classifier routes to the `INFRA_METRICS` intent). Filters by `app_id`, `project_id`, and the resolved `record_time` window. Granularity is **per host**, not per service — there is no service_id/service_name column. Entry point: `fetch_infra_for_orchestrator(app_id, project_id, start_time, end_time)`. Records are one row per `(host_name, metric_type, record_time)`; `metric_type` values are `{solarwinds,zabbix}_{cpu,memory,disk}`.

**`llm_response_generator.py`** — Layer 2 LLM (AWS Bedrock). Receives complete orchestrator output and generates a conversational response as "SLO Advisor". System prompt (v3) defines interpretation rules for all 6 data source types: real-time SLO metrics, historical behavior patterns, alert/incident history, deployment change impact, host-level infra metrics, and intent classification. Includes a pattern→action cheat sheet (sudden drop, drift, seasonal, chronic, volume-driven, etc.). Has two call paths: `generate_response()` (blocking, returns full text) and `generate_response_stream()` (generator, yields raw text chunks via `invoke_model_with_response_stream`). The streaming endpoint accumulates chunks and applies `_sanitize_response()` to the full text at the end, so sanitization is not skipped.

Internal system names (ClickHouse, Java Stats API, etc.) are intentionally hidden from users at two levels: (1) the system prompt has an "ABSOLUTE OUTPUT RULE" at the top forbidding their use, and all section headers use user-friendly descriptions; (2) `_sanitize_response()` is a post-processing step applied to every LLM response that regex-replaces any leaked names as a deterministic safety net. **If you add a new data source that introduces a new technology name the LLM might mention, add it to the replacement patterns in `_sanitize_response()`.**

Currently sanitized by `_sanitize_response()`: `Java Stats API`, `Java Stats`, `ClickHouse`. **Not yet sanitized:** `SolarWinds`, `Zabbix` (both mentioned by name in the Layer 2 system prompt under section 7). If the LLM leaks these, add replacements — e.g. replace `SolarWinds`/`Zabbix` with `monitoring system`.

Two system prompt sections are defined but excluded from the active prompt: `_SECTION_3_ALERT` (alert & incident history interpretation rules, including the critical note that alerts are application-level only, never service-level) and `_SECTION_5_INFRA` (host-level infra metrics interpretation rules, including dual-tool handling for SolarWinds vs Zabbix). `_ALERT_INTERPRETATION_RULES` (severity 1–7 table) is also defined but unused. To re-enable: insert the variable(s) into the `return` string in `_build_system_prompt()`, renumber the active sections accordingly (currently 1–4), and re-enable the corresponding adapter + intent classifier entries (see disabled entries in Data Sources table above).

**`api_models.py`** — Pydantic v2 request/response models. `QueryRequest` takes `query`, `app_id` (default `31854`), `project_id` (default `215853`), and optional `start_time`/`end_time` (Unix epoch ms, default `None`). `data` field in `QueryResponse` is `Dict[str, Any]` since each adapter returns a different schema.

**`utils/service_matcher.py`** — Fuzzy matching via `SequenceMatcher`. Loads `services.yaml` (auto-generated; count varies by `app_id`). Threshold: 0.3; substring matches boosted to 0.7. Returns ranked results with similarity scores.

**`intent_classifier/timestamp.py`** — Converts the raw user query directly to UTC millisecond timestamps using a **hybrid three-stage approach**: (1) deterministic regex/rule-based parsing, (2) Claude Sonnet LLM fallback for complex/ambiguous expressions, (3) hard fallback to last 2 hours. Determines index granularity: HOURLY (<=3 days), DAILY (>3 days). Called with the raw query string, not an LLM-extracted label.

**`app.py`** — Streamlit chat UI. Talks to the FastAPI backend at `http://localhost:8000`. Renders the conversational response as markdown; shows intent, resolved time range, index, and per-source stats in a collapsible "Technical details" expander. App ID, Project ID, and optional Start/End Time override (Unix ms) are configurable from the sidebar. Internal data-source keys (`java_stats_api`, `clickhouse`, etc.) are mapped to user-friendly display names via `SOURCE_DISPLAY_NAMES` dict at the top of the file. Per-source stats are rendered by `render_source_stat()` which has three branches keyed on envelope shape: `stats` (change_impact), `total_records` (clickhouse, infra), and `records` list (generic fallback). **When adding a new adapter: (1) add its key → display name to `SOURCE_DISPLAY_NAMES`; (2) if its envelope shape doesn't match an existing branch, add one to `render_source_stat()` in `app.py`.**

## Data Sources

| Source | Status | Description |
|--------|--------|-------------|
| `java_stats_api` | Active | Real-time SLO metrics; always fetches all services regardless of intent — Layer 2 LLM handles filtering |
| `clickhouse` | Active | All historical behavior patterns; no time/intent filtering |
| `change_impact` | Active | Latest deployment + top-5 EB/RESPONSE deviations pre/post release |
| `clickhouse_infra` | **Disabled** | Host-level CPU/memory/disk metrics from `metrics.infra_data`; adapter, intent classifier, and LLM prompt all commented out |
| `alerts_count` | **Disabled** | Alert action counts for query time window; adapter, intent classifier, and LLM prompt all commented out |
| `postgres` | Not implemented | Planned for SLO definitions; returns `{"status": "not_implemented"}` if classifier routes to it |
| `opensearch` | Not implemented | Planned for logs/traces; returns `{"status": "not_implemented"}` if classifier routes to it |

### ClickHouse Tables
- `ai_service_behavior_memory` — behavior patterns (108 records, app 31854 / project 215853); filtered by both `application_id` and `project_id`
- `ai_service_features_hourly` — service inventory (source for `services.yaml`)
- `infra_data` — host-level infra metrics (CPU / memory / disk via SolarWinds and Zabbix); queried by `infra_adapter.py`. Table name overridable via `CLICKHOUSE_INFRA_TABLE`.

## Environment Variables (.env)

All configuration lives in `.env` and is loaded centrally by `config.py`. No credentials are hardcoded in any adapter.

```bash
# AWS Bedrock
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6

# Layer 1 LLM (intent classification)
MAX_TOKENS=500
TEMPERATURE=0.0

# Layer 2 LLM (response generation)
RESPONSE_MAX_TOKENS=5000
RESPONSE_TEMPERATURE=0.3

# Keycloak
KEYCLOAK_URL=https://wm-sandbox-auth-1.watermelon.us/realms/watermelon/protocol/openid-connect/token
KEYCLOAK_CLIENT_ID=web_app

# Adapter API URLs (full URLs, no base URL construction in code)
JAVA_STATS_API_URL=https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/transactions/distinct/top-5/ALL
# DISABLED: ALERTS_COUNT_API_URL=https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetalertandnotificationservice/api/alerts-action/count
RELEASE_HISTORIES_API_URL=https://wm-sandbox-1.watermelon.us/services/wmebonboarding/api/release-histories/application
RELEASE_IMPACT_API_URL=https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/release-impact/transactions/top-5/POST
# Credentials (shared across all Keycloak-authenticated adapters: Java Stats, Change Impact)
WM_USERNAME=wmadmin
WM_PASSWORD=your_password

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
CLICKHOUSE_SERVICES_TABLE=ai_service_features_hourly
# DISABLED: CLICKHOUSE_INFRA_TABLE=infra_data

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

**Java Stats always returns 4 arrays for all services:** `fetch_api_data` + `transform_to_llm_format` always produces unhealthy_eb, at_risk_eb, unhealthy_response, at_risk_response for all services regardless of which intent triggered the fetch. Intent-based routing functions were removed — the Layer 2 LLM handles focus on specific services or EB-only views.

**Memory adapter returns 0 records:** Verify ClickHouse connectivity and that `app_id = 31854` has data. (Note: services.yaml is not required for memory adapter — it's used for service name matching only.)

**Intent classifier fails:** Must run from project root. Verify AWS credentials and `BEDROCK_MODEL_ID` in `.env`.

**Import errors on startup:** Ensure `__init__.py` files exist in `intent_classifier/`, `context_adapter/`, and `utils/`.


**`start_time`/`end_time` from API are only a fallback:** They are used only when the query contains no time reference (`timestamp source == "fallback"`). If the query mentions any time expression (regex or LLM matched), these fields are ignored regardless of their value. A minimum 2-hour gap is always enforced after resolution by shifting `start_time` backwards (`start = end - 2 hours`) — not forwards — so the query always covers a completed historical window rather than a future one.

**`change_pre_post` ignores query time window:** It always fetches the single latest release from the API (sorted by date) and uses that release's `dateTimeMillis` as the anchor. The user's query start/end time is never passed to this adapter.

**`alert_count` via orchestrator uses `project_id` filter only:** `fetch_alerts_for_orchestrator()` sends `[{"id": project_id, "sloTypes": ["ERROR", "RESPONSE"]}]`. The API requires `project_id` (215853) — using only `app_id` (31854) returns 0 results because all alerts are indexed by `sid: project_id`. The `app_id` is retained in the returned query metadata for traceability only. The `__main__` block uses more granular per-service filters for standalone testing only.

**`timestamp.py` LLM fallback must return `{"ambiguous": true}` for time-less queries — not invent a default:** The system prompt in `_parse_with_llm` explicitly instructs the model to return `{"ambiguous": true}` when the query has no time reference, and the parser converts that to `None` so `source` falls through to `'fallback'`. This is load-bearing: if the LLM fabricates a default window (e.g. "last 1 hour") for a time-less query, `source` becomes `'llm'` and `main.py` ignores the API-provided `start_time`/`end_time`, silently overriding the caller. Do not loosen the prompt or remove the `ambiguous` branch in the parser.

**`clickhouse_infra` is a distinct data source key from `clickhouse`:** `memory_adapter.py` and `infra_adapter.py` hit two different tables and are gated independently. The orchestrator fires `infra_adapter` only when the classifier emits `clickhouse_infra` in `data_sources` (currently only the `INFRA_METRICS` intent does). Don't reuse the `clickhouse` key for new ClickHouse adapters — add a new keyed source instead so adapters stay independently gated.

**`infra_data` has no service column:** Only `host_name` is available. If a user asks for infra on a specific service, the adapter still returns all hosts for the app/project — there is no host→service mapping in the codebase. The Layer 2 system prompt is aware of this; don't add fake service filtering in the adapter.

**`_fetch_memory_adapter` re-resolves service_id internally:** `main.py` already resolves `service_id` near the top of `process_query()` but then calls `_fetch_memory_adapter(service_name=service, ...)` passing the raw name. The method re-resolves via `ServiceMatcher` internally. This double resolution is harmless but means you'll see two "Resolving service name" log lines per query when a service is mentioned. Do not assume `service_id` has been pre-resolved when working on `_fetch_memory_adapter`.

**Adding a new adapter:** At the top of the new file, use the `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` pattern before `import config` (see existing adapters). All adapters expose two functions: a low-level `fetch_xxx_data(...)` that returns raw records, and an orchestrator-facing `fetch_xxx_for_orchestrator(...)` that returns a structured envelope. The orchestrator only calls the `_for_orchestrator` wrapper. Add any new URLs/credentials to `.env` and `config.py`, then wire the entry-point function into `SLOOrchestrator._prepare_context()` in `main.py` (not `process_query()` — the data-fetch logic now lives in `_prepare_context`).

After wiring, three more steps to keep internal names hidden from users: (1) add the new data-source key → friendly display name to `SOURCE_DISPLAY_NAMES` in `app.py`; (2) if the envelope shape is not `stats` or `total_records`, add a display branch to `render_source_stat()` in `app.py`; (3) if the new source introduces a technology name the LLM might mention (e.g. a new database or API brand name), add a regex replacement for it in `_sanitize_response()` in `llm_response_generator.py`.

The envelope format varies by adapter — there is no single canonical schema. As a convention, aim for `{data_source, filters, records, total_records, fetched_at}` where it fits, but existing adapters deviate:
- `infra_adapter`: `{data_source, filters, total_records, records}` — no `fetched_at`
- `alert_count`: `{data_source, query, alerts_count, fetched_at}` — uses `query` not `filters`, no `records`
- `change_pre_post`: `{data_source, latest_change, eb_deviations, response_deviations, stats}` — fully custom

The Layer 2 system prompt documents how to interpret each of these structures.

**`ARCHITECTURE.md` is partially outdated:** It references 76 behavior patterns and "128 total services"; it also says "No tests" but `tests/test_new_adapters.py` exists. Both service and pattern counts vary by app_id/environment. Treat `CLAUDE.md` as the authoritative reference; `ARCHITECTURE.md` documents an earlier state of the system.

**`README.md` has stale references:** It shows `source venv/bin/activate` (should be `.venv`) and includes a test command `python utils/time_range_resolver.py` pointing to a file that no longer exists. The equivalent standalone test is `cd intent_classifier && python timestamp.py "your query"`, which is already listed in the Development Commands above.
