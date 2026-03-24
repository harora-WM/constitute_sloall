# Conversational SLO Manager

An AI-powered SLO orchestration system that uses AWS Bedrock Claude Sonnet 4.6 to analyze natural language queries about service reliability and fetch data from multiple sources.

## Quick Start

### 1. Setup Environment

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create or update `.env` file with your credentials:

```bash
# AWS Bedrock Configuration (Required)
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6

# LLM Parameters
MAX_TOKENS=500
TEMPERATURE=0.0

# Java Stats API Credentials (Optional - defaults provided)
JAVA_STATS_USERNAME=wmadmin
JAVA_STATS_PASSWORD=your_password
```

### 3. Run the Orchestrator

```bash
# Interactive CLI (run from project root)
python main.py

# FastAPI server (run from project root)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Then enter queries like:
- "What is the health status of payment-api in the last 7 days?"
- "Show me error budget burn rate for the past 10 days"
- "What services are unhealthy today?"

## Architecture

```
User Query (query, app_id, project_id)
    ↓
Orchestrator (main.py)
    ↓
Intent Classifier (AWS Bedrock Claude 4.6)
    ↓
Intent + Entities + Data Sources + Timestamps
    ↓
┌─────────────────────────────────────────────────────────┐
│             Adapter Routing                             │
│  intent-gated: java_stats_api, clickhouse               │
│  always-on:    alerts_count, change_impact              │
└─────────────────────────────────────────────────────────┘
    ↓
LLM Response Generator (AWS Bedrock Claude 4.6)
    ↓
Conversational Response + JSON Export
```

## Components

### Main Entry Point
- **`main.py`** - Contains `SLOOrchestrator`, interactive CLI, and FastAPI app (`GET /health`, `POST /query`). `app_id` and `project_id` are passed via request body for API; defaults used for CLI.

### Intent Classification
- **`intent_classifier/intent_classifier.py`** - LLM-based intent analyzer
- **`intent_classifier/intent_categories.yaml`** - Intent definitions and data source mappings
- **`intent_classifier/enrichment_rules.yaml`** - Auto-enrichment rules for related intents
- **`intent_classifier/timestamp.py`** - Time range resolver

### Context Adapters
- **`context_adapter/java_stats.py`** - Fetches SLO metrics from Watermelon API (intent-gated)
- **`context_adapter/memory_adapter.py`** - Fetches behavior patterns from ClickHouse (intent-gated)
- **`context_adapter/alret_count.py`** - Fetches alert action counts (always fetched)
- **`context_adapter/change_pre_post.py`** - Fetches latest deployment and pre/post deviations (always fetched)

### Utilities
- **`utils/time_range_resolver.py`** - Natural language time parsing

## Example Query Flow

```bash
Query: "Show unhealthy services in the past 7 days"

1. Intent Classification:
   - Primary Intent: SERVICE_HEALTH
   - Enriched Intents: SERVICE_HEALTH, UNDERCURRENTS_TREND
   - Entities: time_range="past_7_days"
   - Data Sources: ["java_stats_api", "clickhouse"]

2. Time Resolution:
   - start_time: 1769691000000 (7 days ago)
   - end_time: 1770296000000 (now)
   - index: DAILY

3. Data Fetching:
   - java_stats_api → Error budget, latency, health status
   - clickhouse → Behavior patterns and anomalies
   - alerts_count → Alert action counts (always fetched)
   - change_impact → Latest deployment + pre/post deviations (always fetched)

4. Response:
   {
     "success": true,
     "classification": {...},
     "time_resolution": {...},
     "data": {
       "java_stats_api": {...},
       "clickhouse": {...},
       "alerts_count": {...},
       "change_impact": {...}
     },
     "conversational_response": "..."
   }
```

## Supported Data Sources

| Data Source | Status | Triggered | Description |
|------------|---------|-----------|-------------|
| `java_stats_api` | ✅ Implemented | Intent-gated | Real-time SLO metrics from Watermelon API |
| `clickhouse` | ✅ Implemented | Intent-gated | Historical behavior patterns and AI memory |
| `alerts_count` | ✅ Implemented | Always | Alert action counts for query time window |
| `change_impact` | ✅ Implemented | Always | Latest deployment + pre/post EB/RESPONSE deviations |
| `postgres` | ⏳ Planned | Intent-gated | SLO definitions, alerts, incidents |
| `opensearch` | ⏳ Planned | Intent-gated | Logs, traces, full-text search |

## Development

### Run Individual Components

**Test Intent Classifier Only:**
```bash
cd intent_classifier
python intent_classifier.py
```

**Test Java Stats Adapter:**
```bash
cd context_adapter
python java_stats.py
```

**Test Memory Adapter:**
```bash
cd context_adapter
python memory_adapter.py
```

**Test Time Resolution:**
```bash
cd utils
python time_range_resolver.py
```

## Configuration Files

- **`.env`** - Environment variables and credentials
- **`intent_categories.yaml`** - 9 intent categories with 50+ specific intents
- **`enrichment_rules.yaml`** - Auto-enrichment mappings
- **`data_sources.yaml`** - Data source capabilities and settings

## Troubleshooting

### Import Errors
Make sure `__init__.py` files exist in:
- `intent_classifier/`
- `context_adapter/`
- `utils/`

### AWS Bedrock Connection Issues
- Verify AWS credentials in `.env`
- Check AWS region matches your Bedrock access
- Ensure model ID is correct

### Adapter Connection Failures
- **Java Stats API**: Check Keycloak credentials
- **ClickHouse**: Verify ClickHouse server is accessible

## License

Proprietary - Internal use only
