"""
Central configuration for the SLO Manager.
All values are read from environment variables (via .env).
Import this module instead of calling os.getenv() directly in adapters.
"""
import os
from dotenv import load_dotenv

# Load .env from the project root (the directory where this file lives)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# ── AWS / Bedrock ──────────────────────────────────────────────────────────────
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID")

# ── Layer 1 LLM (intent classification) ───────────────────────────────────────
MAX_TOKENS = int(os.getenv("MAX_TOKENS"))
TEMPERATURE = float(os.getenv("TEMPERATURE"))

# ── Layer 2 LLM (response generation) ─────────────────────────────────────────
RESPONSE_MAX_TOKENS = int(os.getenv("RESPONSE_MAX_TOKENS"))
RESPONSE_TEMPERATURE = float(os.getenv("RESPONSE_TEMPERATURE"))

# ── Keycloak ───────────────────────────────────────────────────────────────────
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")

# ── Adapter API URLs ───────────────────────────────────────────────────────────
JAVA_STATS_API_URL = os.getenv("JAVA_STATS_API_URL")
# DISABLED: alerts_count adapter
# ALERTS_COUNT_API_URL = os.getenv("ALERTS_COUNT_API_URL")
RELEASE_HISTORIES_API_URL = os.getenv("RELEASE_HISTORIES_API_URL")
RELEASE_IMPACT_API_URL = os.getenv("RELEASE_IMPACT_API_URL")

# ── Credentials ────────────────────────────────────────────────────────────────
USERNAME = os.getenv("WM_USERNAME")
PASSWORD = os.getenv("WM_PASSWORD")

# ── Application defaults ───────────────────────────────────────────────────────
APP_ID = int(os.getenv("APP_ID"))
PROJECT_ID = int(os.getenv("PROJECT_ID"))

# ── Java Stats API pagination ──────────────────────────────────────────────────
JAVA_STATS_PAGE_SIZE = int(os.getenv("JAVA_STATS_PAGE_SIZE"))

# ── Change impact analysis windows ────────────────────────────────────────────
CHANGE_POST_PERIOD = os.getenv("CHANGE_POST_PERIOD")
CHANGE_POST_PERIOD_DURATION = int(os.getenv("CHANGE_POST_PERIOD_DURATION"))
CHANGE_PRE_PERIOD = os.getenv("CHANGE_PRE_PERIOD")
CHANGE_PRE_PERIOD_DURATION = int(os.getenv("CHANGE_PRE_PERIOD_DURATION"))

# ── ClickHouse ─────────────────────────────────────────────────────────────────
CLICKHOUSE_URL = os.getenv("CLICKHOUSE_URL")
CLICKHOUSE_USERNAME = os.getenv("CLICKHOUSE_USERNAME")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE")
# DISABLED: clickhouse_infra adapter
# CLICKHOUSE_INFRA_TABLE = os.getenv("CLICKHOUSE_INFRA_TABLE")
CLICKHOUSE_SERVICES_TABLE = os.getenv("CLICKHOUSE_SERVICES_TABLE")

# ── OpenSearch ─────────────────────────────────────────────────────────────────
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT"))
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD")
OPENSEARCH_USE_SSL = os.getenv("OPENSEARCH_USE_SSL", "False").lower() == "true"
OPENSEARCH_PAGE_SIZE = int(os.getenv("OPENSEARCH_PAGE_SIZE"))
