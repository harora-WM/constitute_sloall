# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A fully **Conversational SLO (Service Level Objective) Manager** that uses AWS Bedrock Claude Sonnet 4.5 in a **two-layer LLM architecture** to understand user queries, fetch relevant data from multiple sources, and generate natural language responses about service reliability.

**Key Features:**
- **Two-layer LLM architecture**: Intent classification → Data fetching → Conversational response generation
- Natural language query understanding with intent classification
- Multi-source data aggregation (Java Stats API, ClickHouse patterns)
- Service name → Service ID resolution with fuzzy matching
- Automatic time range resolution with index granularity
- **Complete historical context**: Returns ALL behavior patterns (no time/intent filtering)
- **Primary intent precedence**: Respects user's main question over LLM's secondary classifications
- Automatic JSON export after every query
- Interactive CLI interface

## Development Commands

### Environment Setup
```bash
# Python 3.12 or higher recommended
source venv/bin/activate
pip install -r requirements.txt
```

### Running the System

**Orchestrator (Primary Entry Point)**
```bash
python orchestrator.py
# Interactive CLI with:
# - Intent classification
# - Data fetching from multiple sources
# - Conversational response generation
# - Automatic JSON export
```

**Example Queries:**
```
what is the health of my application in the past 30 days
which services show sudden drop
is payment-api healthy?
show me error budget status
what are the most critical issues?
```

**CLI Commands:**
- `export` - Re-export last result to JSON
- `help` - Show help message
- `quit` or `exit` - Exit the program

**Generate Service Mapping**
```bash
python fetch_services.py
# Fetches all services from ClickHouse → generates services.yaml
# Run this when services change or for initial setup
```

**Test Components Individually**
```bash
# Service matcher
python utils/service_matcher.py "dashboard-stats"

# Intent classifier
cd intent_classifier && python intent_classifier.py

# LLM response generator
python llm_response_generator.py

# Adapters
cd context_adapter && python memory_adapter.py
cd context_adapter && python java_stats.py
```

## Architecture

### Two-Layer LLM Architecture

**Why Two Layers:**
1. **Layer 1 (Intent Classification)**: Understand what user wants → Route to correct data sources
2. **Layer 2 (Response Generation)**: Analyze fetched data → Generate conversational answer

This separation allows focused system prompts for each task and prevents data fetching logic from being mixed with response generation.

### Complete End-to-End Flow

```
User Natural Language Query
    ↓
┌─────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (orchestrator.py)                              │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Intent Classification (LLM Call #1)                 │
│ (intent_classifier.py - AWS Bedrock Claude 4.5)             │
│                                                              │
│ Extracts:                                                    │
│ • Primary intent                                             │
│ • Secondary intents (from LLM)                               │
│ • Enriched intents (from enrichment_rules.yaml)              │
│ • Entities (service, time_range)                             │
│ • Data sources required                                      │
│ • Resolved timestamps with index granularity                 │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Service Resolution (if service mentioned)           │
│ (service_matcher.py)                                         │
│                                                              │
│ • Fuzzy match service name → service_id                      │
│ • Uses services.yaml (125 services for app 31854)            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Data Fetching (Parallel)                            │
│                                                              │
│ Java Stats API              ClickHouse                       │
│ (java_stats.py)             (memory_adapter.py)              │
│                                                              │
│ Intent routing:             Returns ALL patterns:            │
│ ├─ PRIMARY intent first     • No time filtering              │
│ ├─ CURRENT_HEALTH           • No intent filtering            │
│ ├─ SERVICE_HEALTH           • All 76 historical patterns     │
│ └─ ERROR_BUDGET_STATUS      • Complete context for LLM       │
│                                                              │
│ Returns 4 arrays for        FROM: ai_service_behavior        │
│ CURRENT_HEALTH,             _memory table                    │
│ 3 arrays for ERROR_BUDGET   WHERE app_id = 31854 ONLY        │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Data Aggregation                                             │
│                                                              │
│ {                                                            │
│   classification: {...},                                     │
│   data: {                                                    │
│     java_stats_api: {...},                                   │
│     clickhouse: {                                            │
│       stats: {...},                                          │
│       patterns: [all 76 patterns],                           │
│       triggered_by_intents: [...]                            │
│     }                                                        │
│   },                                                         │
│   metadata: {...}                                            │
│ }                                                            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Conversational Response (LLM Call #2)               │
│ (llm_response_generator.py - AWS Bedrock Claude 4.5)        │
│                                                              │
│ Input: Complete orchestrator output                          │
│                                                              │
│ System Prompt Includes:                                      │
│ • Expert SLO analyst role                                    │
│ • Data source interpretation guidelines                      │
│ • Health status definitions                                  │
│ • Burn rate severity levels                                  │
│ • Pattern type explanations                                  │
│ • Response formatting guidelines                             │
│                                                              │
│ Output: Natural language conversational response             │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ FINAL OUTPUT                                                 │
│                                                              │
│ 💬 Conversational Response (displayed to user)              │
│ 📋 Technical Summary (stats, intents, sources)              │
│ 💾 Auto-export to JSON file                                 │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Orchestrator (`orchestrator.py`)
**Role:** Main coordinator of the entire pipeline

**Responsibilities:**
- Initialize all sub-components (intent classifier, service matcher, response generator)
- Process user queries through the 4-step pipeline
- Aggregate data from all sources
- Pass complete context to LLM response generator
- Display results and auto-export to JSON

**Key Configuration:**
- `app_id = 31854` (hardcoded, can be made configurable)
- Java Stats credentials from .env

### 2. Intent Classifier (`intent_classifier/intent_classifier.py`)
**Role:** Layer 1 LLM - Understand user intent

**LLM:** AWS Bedrock Claude Sonnet 4.5
**Input:** User query
**Output:**
- `primary_intent`: Main question being asked
- `secondary_intents`: Related aspects (from LLM)
- `enriched_intents`: Auto-added context (from enrichment_rules.yaml)
- `entities`: Extracted service name, time range, comparison range
- `data_sources`: Required sources based on intent_categories.yaml
- `timestamp_resolution`: Resolved UTC timestamps + index granularity

**Configuration Files:**
- `intent_categories.yaml` - 9 categories, 50+ intents with data source mappings
- `enrichment_rules.yaml` - Auto-enrichment rules
- `data_sources.yaml` - Data source capabilities and timeouts

### 3. Service Matcher (`utils/service_matcher.py`)
**Role:** Resolve service names to service IDs

**Method:** Fuzzy matching using SequenceMatcher
- Loads `services.yaml` (125 services for app 31854)
- Threshold: 0.3 (default)
- Substring matches get score boost to 0.7
- Returns ranked matches with similarity scores

### 4. Java Stats Adapter (`context_adapter/java_stats.py`)
**Role:** Fetch real-time SLO metrics from Watermelon API

**Authentication:** Keycloak → Bearer token → API call

**CRITICAL: Primary Intent Precedence**
```python
# Checks PRIMARY intent FIRST (not secondary/enriched)
if primary_intent == "SERVICE_HEALTH":
    return get_service_health(...)  # Specific service only
elif primary_intent == "CURRENT_HEALTH":
    return get_current_health(...)  # All 4 arrays (EB + RESPONSE)
elif primary_intent == "ERROR_BUDGET_STATUS":
    return get_error_budget_status(...)  # 3 EB arrays only

# Fallback to checking all intents if primary doesn't match
elif "SERVICE_HEALTH" in intents:
    return get_service_health(...)
# ... etc
```

**Intent Functions:**
- `get_current_health()` - **CURRENT_HEALTH** intent
  - Returns 4 arrays: unhealthy_eb, at_risk_eb, unhealthy_response, at_risk_response
  - Application-wide health for all services

- `get_service_health()` - **SERVICE_HEALTH** intent
  - Requires service_id (returns None if not provided)
  - Returns same 4 arrays but filtered to specific service

- `get_error_budget_status()` - **ERROR_BUDGET_STATUS** intent
  - Returns 3 arrays: unhealthy_eb, at_risk_eb, healthy_eb
  - EB category only, service_id optional

**Why This Matters:**
Previously, if user asked "what is the health?" (CURRENT_HEALTH primary) but LLM also added ERROR_BUDGET_STATUS as secondary, the ERROR_BUDGET_STATUS would hijack and return only 3 arrays instead of all 4. Now primary intent is respected first.

### 5. Memory Adapter (`context_adapter/memory_adapter.py`)
**Role:** Fetch historical behavior patterns from ClickHouse

**CRITICAL: No Filtering - Returns ALL Patterns**

**What Changed:**
```python
# BEFORE: Filtered by time AND intent
WHERE app_id = 31854
  AND detected_at >= start_time
  AND detected_at <= end_time
  AND pattern_type IN (specific types based on intent)

# AFTER: Only by app_id
WHERE app_id = 31854
```

**Why:**
- User asks "last hour" but patterns detected months ago are still relevant context
- LLM needs complete historical view to make connections
- Only 76 total patterns - not a volume problem
- Removed ~50 lines of complex intent-based routing logic

**Returns:**
```python
{
  "data_source": "ai_service_behavior_memory",
  "stats": {
    "total_records": 76,
    "services_affected": 5,
    "chronic": 61,
    "at_risk": 14,
    "healthy": 1
  },
  "patterns": [all 76 patterns],
  "triggered_by_intents": [list of intents]  # Just metadata
}
```

### 6. LLM Response Generator (`llm_response_generator.py`)
**Role:** Layer 2 LLM - Generate conversational responses

**LLM:** AWS Bedrock Claude Sonnet 4.5 (separate call from intent classification)
**Input:** Complete orchestrator output (query + classification + all data)
**Output:** Natural language conversational response

**System Prompt Includes:**
- Expert SLO analyst role definition
- Data source explanations:
  - Java Stats: health status, burn rates, success rates, latency
  - ClickHouse: pattern types, baseline states, confidence scores
- Metric interpretation guidelines:
  - Health status: UNHEALTHY (breached), AT_RISK (close), HEALTHY (safe)
  - Burn rate levels: >10 critical, 5-10 high, 1-5 moderate, <1 low
  - Pattern types: sudden_spike/drop, drift_up/down, daily, weekly, volume_driven
  - Baseline states: CHRONIC, AT_RISK, HEALTHY
- Response formatting rules:
  - Start with direct answer to question
  - Use specific numbers and service names
  - Prioritize by impact (unhealthy first)
  - Highlight trends from patterns
  - Provide actionable recommendations
  - Use bullet points and formatting

**Environment Variables:**
```bash
RESPONSE_MAX_TOKENS=2000  # Default: 2000 (more than intent classification)
RESPONSE_TEMPERATURE=0.3  # Default: 0.3 (slightly higher for natural responses)
```

### 7. Time Range Resolution (`utils/time_range_resolver.py`, `intent_classifier/timestamp.py`)
**Role:** Convert natural language to UTC milliseconds

**Key Rules:**
- "current" = last 1 hour (not zero duration)
- Index granularity: HOURLY (≤3 days), DAILY (>3 days)
- Min duration: 5 minutes, Max: 2 years
- Always milliseconds (not seconds)
- Two implementations exist (both work similarly)

## Critical Design Decisions

### 1. Two-Layer LLM Architecture
**Decision:** Use LLM twice - once for intent, once for response

**Why:**
- Separation of concerns: understanding vs. analysis
- Focused system prompts for each task
- Intent classification doesn't need to see all the data
- Response generation gets complete context without routing logic

**Trade-off:** 2 LLM calls per query (slightly slower, higher cost)

### 2. Primary Intent Precedence
**Decision:** Check primary intent FIRST before checking all intents

**Why:**
- User's main question should be answered, not LLM's secondary guesses
- Prevents ERROR_BUDGET_STATUS from hijacking CURRENT_HEALTH queries
- More predictable behavior

**Implementation:**
```python
# orchestrator.py passes primary_intent separately
_fetch_java_stats(..., primary_intent=primary_intent, intents=all_intents)

# java_stats.py checks primary first, then falls back to all intents
```

### 3. No Filtering in Memory Adapter
**Decision:** Return ALL 76 patterns regardless of time range or intent

**Why:**
- Historical patterns detected long ago are still relevant context
- LLM can make better connections with complete history
- Simplifies code (removed complex routing logic)
- Only 76 patterns total - not a performance issue

**What Was Removed:**
- Time-based WHERE clause filtering by detected_at
- Intent-based routing (dispatch_intent_query, 7 specialized functions)
- Pattern type filtering based on specific intents

### 4. Automatic JSON Export
**Decision:** Auto-export after every successful query

**Why:**
- Complete audit trail of all queries and responses
- Debug data when tuning conversational responses
- Raw data access for further analysis
- Includes both structured data AND conversational response

**File Naming:** `slo_result_{start_time_timestamp}.json`

## Data Sources

| Source | Status | Description | Filtering |
|--------|--------|-------------|-----------|
| `java_stats_api` | ✅ Implemented | Real-time SLO metrics | Intent-based (primary first) |
| `clickhouse` | ✅ Implemented | Historical behavior patterns | App ID only (no time/intent) |
| `postgres` | ⏳ Planned | SLO definitions, alerts | Not implemented |
| `opensearch` | ⏳ Planned | Logs, traces | Not implemented |

### ClickHouse Tables
- `ai_service_behavior_memory` - Behavior patterns (76 records for app 31854)
- `ai_service_features_hourly` - Service inventory (for services.yaml)

### Current Patterns in Database
- `daily`: 15 records (TIME_WINDOW_ANOMALY)
- `weekly`: 58 records (SEASONALITY_PATTERN)
- `volume_driven`: 2 records (CAPACITY_RISK)
- `sudden_drop`: 1 record (UNDERCURRENTS_TREND)

Not in DB yet: `drift_up`, `drift_down`, `sudden_spike`

## Key Files

### Core System
- `orchestrator.py` - Main coordinator (4-step pipeline)
- `llm_response_generator.py` - Conversational response generation (Layer 2 LLM)
- `intent_classifier/intent_classifier.py` - Intent classification (Layer 1 LLM)
- `context_adapter/java_stats.py` - Real-time metrics (primary intent precedence)
- `context_adapter/memory_adapter.py` - Historical patterns (no filtering)
- `utils/service_matcher.py` - Service name → ID fuzzy matching
- `utils/time_range_resolver.py` - Time parsing

### Configuration
- `intent_classifier/intent_categories.yaml` - 9 categories, 50+ intents
- `intent_classifier/enrichment_rules.yaml` - Auto-enrichment rules
- `intent_classifier/data_sources.yaml` - Data source capabilities
- `services.yaml` - 125 services for app 31854 (generated)
- `.env` - AWS credentials, API credentials

### Documentation
- `ARCHITECTURE.md` - Detailed architecture diagrams and flow
- `README.md` - Quick start guide

### Utilities
- `fetch_services.py` - Generate services.yaml from ClickHouse
- `context_adapter/intent_based_queries.py` - No longer used (kept for reference)

## Environment Variables (.env)

**Required:**
```bash
# AWS Bedrock (for both LLM layers)
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0

# Intent Classification (Layer 1 LLM)
MAX_TOKENS=500
TEMPERATURE=0.0

# Response Generation (Layer 2 LLM) - Optional
RESPONSE_MAX_TOKENS=2000  # Default: 2000
RESPONSE_TEMPERATURE=0.3  # Default: 0.3
```

**Optional (defaults provided):**
```bash
# Java Stats API
JAVA_STATS_USERNAME=wmadmin
JAVA_STATS_PASSWORD=your_password
```

## Important Notes

### Credentials and Security
- AWS credentials in `.env` (required for both LLM layers)
- Java Stats credentials in `.env` (optional, defaults provided)
- ClickHouse credentials **hardcoded** in code:
  - `memory_adapter.py`
  - `fetch_services.py`
  - URL: `http://ec2-47-129-241-41.ap-southeast-1.compute.amazonaws.com:8123`
  - Auth: `("wm_test", "Watermelon@123")`
- **Never commit credential changes**
- **TODO**: Migrate hardcoded credentials to .env

### Common Gotchas

**Memory Adapter Returns 0 Records:**
- Check if services.yaml exists (run `fetch_services.py`)
- Verify app_id = 31854 is correct
- Note: Memory adapter returns ALL 76 patterns regardless of time query

**Java Stats Returns None:**
- **SERVICE_HEALTH**: Requires service_id - returns None if service not mentioned
- Check Keycloak credentials in .env
- Verify Watermelon API is accessible

**Wrong Arrays Returned from Java Stats:**
- **CURRENT_HEALTH should return 4 arrays** (EB + RESPONSE categories)
- If only getting 3 arrays, check if ERROR_BUDGET_STATUS is hijacking as secondary intent
- Primary intent now takes precedence - this should be fixed

**Intent Classification Issues:**
- Must run from project root (YAML configs use relative paths)
- Check AWS credentials in .env
- Verify BEDROCK_MODEL_ID is correct

**Response Generation Not Working:**
- Check RESPONSE_MAX_TOKENS and RESPONSE_TEMPERATURE in .env
- Verify AWS credentials (uses same Bedrock client)
- LLM response generator uses separate system prompt from intent classifier

### Working Directory Requirement
**CRITICAL:** All commands must be run from project root directory
```bash
cd /path/to/constitute_slo  # Must be in project root
source venv/bin/activate
python orchestrator.py
```
Why: Intent classifier uses relative paths to YAML configs

### Service Matching
- Requires `services.yaml` (run `fetch_services.py` if missing)
- Fuzzy matching threshold: 0.3 (configurable)
- Substring matches boosted to 0.7
- Returns ranked matches with scores
- 125 services currently in mapping

### JSON Export
- **Automatic** after every successful query
- File naming: `slo_result_{start_timestamp}.json`
- Includes:
  - Original query
  - Intent classification
  - All data from all sources
  - **Conversational response** (new field)
  - Response generation metadata
- Can also manually export with `export` command

### Testing
- No formal unit tests
- Each module has `if __name__ == "__main__":` test block
- Test by running files directly
- Integration testing via orchestrator CLI

## Example Queries and Expected Behavior

### Health Queries
```
Query: "what is the health of my application in the past 30 days"
→ Primary: CURRENT_HEALTH
→ Java Stats: get_current_health() → 4 arrays (EB + RESPONSE)
→ ClickHouse: All 76 patterns
→ Response: Natural language summary of 17 unhealthy services with specifics
→ Auto-export: slo_result_1768348800000.json
```

### Service-Specific Queries
```
Query: "is payment-api healthy?"
→ Primary: SERVICE_HEALTH
→ Service Match: "payment-api" → service_id via fuzzy matching
→ Java Stats: get_service_health(service_id) → filtered to that service
→ ClickHouse: All 76 patterns (LLM filters relevant ones in response)
→ Response: Specific analysis of payment-api health
```

### Pattern Queries
```
Query: "which services show sudden drop"
→ Primary: UNDERCURRENTS_TREND
→ Java Stats: May return None (no matching primary intent)
→ ClickHouse: All 76 patterns (including 1 sudden_drop)
→ Response: LLM identifies and explains the sudden_drop pattern
```

### Error Budget Queries
```
Query: "show me error budget status"
→ Primary: ERROR_BUDGET_STATUS
→ Java Stats: get_error_budget_status() → 3 EB arrays only
→ ClickHouse: All 76 patterns
→ Response: EB consumption analysis with burn rates
```

## Future Enhancements
- Add postgres and opensearch adapters
- Make app_id configurable (currently hardcoded to 31854)
- Add caching layer for repeated queries
- Implement REST API using FastAPI
- Add retry logic for failed adapter calls
- Move all credentials to .env
- Add proper logging and monitoring
- Implement cross-application correlation
- Add service dependency awareness
- Implement severity scoring and impact assessment
- Add user feedback loop for response quality
- Implement response streaming for faster UX
- Add conversation history/context

## Scalability Considerations

**Current Limitations:**
- Single application focus (app_id 31854)
- Hardcoded pattern types and thresholds
- No query optimization (each query fetches all data)
- No caching (repeated queries hit APIs/DB every time)
- Two LLM calls per query (cost and latency)

**For Production Scale:**
- Implement caching layer (Redis/in-memory)
- Add query result batching
- Implement data source connection pooling
- Add rate limiting and quota management
- Implement response streaming for better UX
- Add monitoring and alerting for LLM costs
- Implement fallback mechanisms for LLM failures
