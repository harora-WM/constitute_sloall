# Conversational SLO Manager - Complete Architecture

## 🎯 System Overview

A fully conversational SLO analysis system that uses AWS Bedrock Claude Sonnet 4.5 at TWO layers:
1. **Intent Classification Layer** - Understands what the user is asking
2. **Response Generation Layer** - Generates natural language answers from data

## 📊 Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER NATURAL LANGUAGE QUERY                        │
│                     "What is the health of my application?"                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ORCHESTRATOR LAYER                                │
│                           (orchestrator.py)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────┴─────────────────┐
                    ↓                                   ↓
┌────────────────────────────────────┐  ┌────────────────────────────────────┐
│   STEP 1: INTENT CLASSIFICATION    │  │   STEP 2: SERVICE RESOLUTION       │
│   (intent_classifier.py)           │  │   (service_matcher.py)             │
│                                    │  │                                    │
│   AWS Bedrock Claude 4.5           │  │   Fuzzy matching                   │
│   ↓                                │  │   services.yaml lookup             │
│   • Primary Intent                 │  │   ↓                                │
│   • Secondary Intents              │  │   service_name → service_id        │
│   • Entities (service, time)       │  │                                    │
│   • Enriched Intents               │  │                                    │
│   • Data Sources Required          │  │                                    │
│   • Time Resolution                │  │                                    │
└────────────────────────────────────┘  └────────────────────────────────────┘
                    │                                   │
                    └─────────────────┬─────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                     STEP 3: DATA FETCHING (PARALLEL)                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ↓                       ↓                       ↓
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│   JAVA STATS API     │  │    CLICKHOUSE        │  │   POSTGRES           │
│   (java_stats.py)    │  │  (memory_adapter.py) │  │  (Not implemented)   │
│                      │  │                      │  │                      │
│ Intent Routing:      │  │ Fetches ALL patterns │  │                      │
│ ├─ SERVICE_HEALTH    │  │ from table:          │  │                      │
│ ├─ CURRENT_HEALTH    │  │ ai_service_behavior  │  │                      │
│ └─ ERROR_BUDGET      │  │ _memory              │  │                      │
│                      │  │                      │  │                      │
│ Primary intent has   │  │ No time filtering    │  │                      │
│ precedence over      │  │ No intent filtering  │  │                      │
│ secondary            │  │                      │  │                      │
│                      │  │ Returns ALL 76       │  │                      │
│ Returns:             │  │ historical patterns  │  │                      │
│ • All 4 arrays for   │  │                      │  │                      │
│   CURRENT_HEALTH     │  │                      │  │                      │
│ • EB arrays only     │  │                      │  │                      │
│   for ERROR_BUDGET   │  │                      │  │                      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA AGGREGATION IN ORCHESTRATOR                          │
│                                                                              │
│  {                                                                           │
│    "success": true,                                                          │
│    "query": "What is the health...",                                         │
│    "classification": {...},                                                  │
│    "time_resolution": {...},                                                 │
│    "data": {                                                                 │
│      "java_stats_api": {...},                                                │
│      "clickhouse": {...}                                                     │
│    },                                                                        │
│    "metadata": {...}                                                         │
│  }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│           STEP 4: CONVERSATIONAL RESPONSE GENERATION                         │
│                   (llm_response_generator.py)                                │
│                                                                              │
│   AWS Bedrock Claude 4.5 (SECOND LLM CALL)                                  │
│                                                                              │
│   Input: Complete orchestrator output + System Prompt                       │
│                                                                              │
│   System Prompt:                                                            │
│   • Expert SLO analyst role                                                 │
│   • Data source interpretation guidelines                                   │
│   • Health status definitions                                               │
│   • Burn rate severity levels                                               │
│   • Pattern type explanations                                               │
│   • Response formatting guidelines                                          │
│                                                                              │
│   Output: Natural language conversational response                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FINAL OUTPUT TO USER                                    │
│                                                                              │
│  💬 CONVERSATIONAL RESPONSE                                                  │
│  ════════════════════════════════════════════════════════════════════        │
│                                                                              │
│  Your application has 17 unhealthy services out of 128 total. The most      │
│  critical is 'wmebonboarding/api/custom-metric-configs' with only 6.26%     │
│  success rate (target: 98%) and a burn rate of 46.87...                     │
│                                                                              │
│  [Full natural language analysis with specific metrics, patterns,           │
│   recommendations, and actionable insights]                                  │
│                                                                              │
│  ════════════════════════════════════════════════════════════════════        │
│  📋 Technical Summary                                                        │
│  ════════════════════════════════════════════════════════════════════        │
│     Primary Intent: CURRENT_HEALTH                                           │
│     Data Sources: java_stats_api, clickhouse                                │
│     Stats: {...}                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🔧 Key Components

### 1. Orchestrator (`orchestrator.py`)
**Role:** Main coordinator
- Initializes all sub-components
- Manages query processing pipeline
- Aggregates data from all sources
- Passes complete context to LLM response generator

**Key Changes Made:**
- ✅ Passes `primary_intent` separately to Java Stats adapter
- ✅ Primary intent takes precedence over secondary intents
- ✅ Integrated LLM response generator as final step
- ✅ Returns both raw data AND conversational response

### 2. Intent Classifier (`intent_classifier/intent_classifier.py`)
**Role:** Understand user intent
- **LLM:** AWS Bedrock Claude Sonnet 4.5
- **Input:** User query
- **Output:**
  - Primary intent
  - Secondary intents (from LLM)
  - Enriched intents (from enrichment_rules.yaml)
  - Entities (service, time_range)
  - Data sources required
  - Resolved timestamps

### 3. Service Matcher (`utils/service_matcher.py`)
**Role:** Resolve service names to IDs
- Loads services.yaml (125 services)
- Fuzzy matching with SequenceMatcher
- Returns ranked matches with scores

### 4. Java Stats Adapter (`context_adapter/java_stats.py`)
**Role:** Fetch real-time SLO metrics
- **Source:** Watermelon API via Keycloak auth
- **Intent-based routing with 3 functions:**
  - `get_current_health()` - Returns ALL 4 arrays (EB + RESPONSE)
  - `get_service_health()` - Filtered to specific service
  - `get_error_budget_status()` - EB category only

**Key Changes Made:**
- ✅ Primary intent checked FIRST
- ✅ CURRENT_HEALTH no longer hijacked by ERROR_BUDGET_STATUS
- ✅ Fallback to priority order for secondary intents

### 5. Memory Adapter (`context_adapter/memory_adapter.py`)
**Role:** Fetch historical behavior patterns
- **Source:** ClickHouse `ai_service_behavior_memory` table

**Key Changes Made:**
- ✅ Removed intent-based filtering (no more dispatch_intent_query)
- ✅ Removed time-based filtering (no start_time/end_time WHERE clause)
- ✅ Returns ALL 76 historical patterns regardless of query
- ✅ Simplified from ~50 lines to ~15 lines

**Why:** Give LLM complete historical context to make better analysis

### 6. LLM Response Generator (`llm_response_generator.py`)
**Role:** Generate conversational responses
- **LLM:** AWS Bedrock Claude Sonnet 4.5 (SECOND call)
- **Input:** Complete orchestrator output
- **Output:** Natural language response

**System Prompt Includes:**
- Expert SLO analyst role definition
- Data source explanations (Java Stats, ClickHouse)
- Metric interpretation guidelines
  - Health status meanings (UNHEALTHY, AT_RISK, HEALTHY)
  - Burn rate severity levels
  - Pattern type definitions
  - Baseline state meanings
- Response formatting guidelines
  - Start with direct answer
  - Use specific numbers and service names
  - Prioritize by impact
  - Highlight trends from patterns
  - Provide actionable recommendations
  - Use bullet points and formatting
- Example tone and style

## 🔑 Critical Design Decisions

### 1. **Two-Layer LLM Architecture**
- **Layer 1 (Intent):** Classify what user wants → Route to correct data sources
- **Layer 2 (Response):** Analyze data → Generate conversational answer

**Why:** Separation of concerns - intent understanding vs. data analysis

### 2. **Primary Intent Precedence**
```python
# Check primary intent FIRST
if primary_intent == "CURRENT_HEALTH":
    return get_current_health(...)  # All 4 arrays

# Then check secondary/enriched intents
elif "ERROR_BUDGET_STATUS" in intents:
    return get_error_budget_status(...)  # 3 EB arrays
```

**Why:** Respect user's main question over LLM's secondary classifications

### 3. **No Filtering in Memory Adapter**
```python
# Before: Filtered by time AND intent
WHERE app_id = 31854
  AND detected_at >= start_time
  AND detected_at <= end_time
  AND pattern_type IN ('sudden_drop', ...)

# After: Only by app_id
WHERE app_id = 31854
```

**Why:**
- User asks "last hour" but patterns detected months ago are still relevant
- LLM should see ALL historical context to make connections
- Only 76 patterns total - not a volume problem

### 4. **Complete Data in Prompt**
The LLM response generator receives:
- Original query
- Intent classification
- ALL Java Stats data (unhealthy, at-risk, healthy)
- ALL ClickHouse patterns (76 records)
- Metadata

**Why:** LLM needs complete context to generate accurate, specific responses

## 📁 File Structure

```
constitute_slo/
├── orchestrator.py                      # Main coordinator
├── llm_response_generator.py           # NEW: Conversational response layer
├── intent_classifier/
│   ├── intent_classifier.py            # Layer 1 LLM (intent)
│   ├── intent_categories.yaml          # Intent definitions
│   ├── enrichment_rules.yaml           # Auto-enrichment
│   └── timestamp.py                    # Time resolution
├── context_adapter/
│   ├── java_stats.py                   # MODIFIED: Primary intent first
│   ├── memory_adapter.py               # MODIFIED: No filtering
│   └── intent_based_queries.py         # Unused now
├── utils/
│   ├── service_matcher.py              # Service name → ID
│   └── time_range_resolver.py          # Time parsing
├── services.yaml                        # Service mapping (125 services)
└── .env                                 # AWS credentials
```

## 🚀 Running the System

```bash
# Activate venv
source venv/bin/activate

# Run orchestrator (interactive CLI)
python orchestrator.py

# Example queries
Query: what is the health of my application in the past 30 days
Query: which services show sudden drop
Query: is payment-api healthy?
Query: show me error budget status

# Commands
export    # Export last result to JSON
quit      # Exit
```

## 🔄 Complete Query Example

**User Query:** "What is the health of my application?"

**Step 1 - Intent Classification:**
- Primary: `CURRENT_HEALTH`
- Secondary: `SLO_STATUS`, `ERROR_BUDGET_STATUS` (from LLM)
- Enriched: `ALERT_STATUS`, `INCIDENT_STATUS` (from rules)
- Time: `current` → last 1 hour
- Data sources: `java_stats_api`, `clickhouse`

**Step 2 - Service Resolution:**
- No service mentioned → `service_id = None`

**Step 3 - Data Fetching:**

**Java Stats (because primary_intent = CURRENT_HEALTH):**
```python
get_current_health(app_id=31854, ...)
# Returns all 4 arrays:
# - unhealthy_services_eb (17 services)
# - at_risk_services_eb (1 service)
# - unhealthy_services_response (if any)
# - at_risk_services_response (if any)
```

**ClickHouse:**
```sql
SELECT * FROM ai_service_behavior_memory
WHERE application_id = 31854
# Returns all 76 patterns
```

**Step 4 - Response Generation:**

**Input to LLM:**
```
User Query: What is the health of my application?

Intent: CURRENT_HEALTH

Java Stats Data:
- 128 total services
- 17 unhealthy (EB)
- 1 at-risk (EB)
- [Full service details with metrics]

ClickHouse Data:
- 76 total patterns
- 61 chronic patterns
- 14 at-risk patterns
- [Full pattern details]
```

**LLM Output:**
```
Your application has 17 unhealthy services out of 128 total SLOs...

**Most Critical Issues:**
• wmebonboarding/api/custom-metric-configs: Only 6.26% success rate
  (target: 98%), burning error budget 47x faster than sustainable

• Others service: 90.6% success rate (target: 98%), 53,410 errors
  out of 568,059 requests...

**Historical Patterns:**
Your behavior memory shows 61 chronic patterns across 5 services...

**Recommendation:**
Focus on the top 3 services with burn rates >10...
```

## 🎯 Success Metrics

The system is working correctly when:

✅ **Intent Classification:** Correctly identifies CURRENT_HEALTH, SERVICE_HEALTH, ERROR_BUDGET_STATUS
✅ **Primary Intent Respected:** CURRENT_HEALTH returns all 4 arrays, not just EB
✅ **Memory Adapter:** Returns all 76 patterns regardless of time query
✅ **Service Matching:** Fuzzy matches service names to IDs
✅ **Response Generation:** Natural language answers with specific metrics
✅ **Complete Context:** LLM sees all data (Java Stats + ClickHouse)

## 🔐 Environment Variables

```bash
# AWS Bedrock (Required)
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0

# Intent Classification
MAX_TOKENS=500
TEMPERATURE=0.0

# Response Generation (Optional - defaults provided)
RESPONSE_MAX_TOKENS=2000
RESPONSE_TEMPERATURE=0.3

# Java Stats API (Optional - defaults provided)
JAVA_STATS_USERNAME=wmadmin
JAVA_STATS_PASSWORD=your_password
```

## 📝 Notes

- **Two LLM calls per query:** Intent classification + Response generation
- **ClickHouse data:** All historical patterns (not filtered by time)
- **Java Stats:** Intent-based routing with primary intent precedence
- **No tests:** Manual testing only via orchestrator CLI
- **Hardcoded:** app_id=31854, ClickHouse credentials
