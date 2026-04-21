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
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "global.anthropic.claude-sonnet-4-6"
)

# ── Layer 1 LLM (intent classification) ───────────────────────────────────────
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "500"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))

# ── Layer 2 LLM (response generation) ─────────────────────────────────────────
RESPONSE_MAX_TOKENS = int(os.getenv("RESPONSE_MAX_TOKENS", "2000"))
RESPONSE_TEMPERATURE = float(os.getenv("RESPONSE_TEMPERATURE", "0.3"))

# ── Keycloak ───────────────────────────────────────────────────────────────────
KEYCLOAK_URL = os.getenv(
    "KEYCLOAK_URL",
    "https://wm-sandbox-auth-1.watermelon.us/realms/watermelon/protocol/openid-connect/token"
)
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "web_app")

# ── Adapter API URLs ───────────────────────────────────────────────────────────
JAVA_STATS_API_URL = os.getenv(
    "JAVA_STATS_API_URL",
    "https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/transactions/distinct/top-5/ALL"
)
ALERTS_COUNT_API_URL = os.getenv(
    "ALERTS_COUNT_API_URL",
    "https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetalertandnotificationservice/api/alerts-action/count"
)
RELEASE_HISTORIES_API_URL = os.getenv(
    "RELEASE_HISTORIES_API_URL",
    "https://wm-sandbox-1.watermelon.us/services/wmebonboarding/api/release-histories/application"
)
RELEASE_IMPACT_API_URL = os.getenv(
    "RELEASE_IMPACT_API_URL",
    "https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/release-impact/transactions/top-5/POST"
)

# ── Credentials ────────────────────────────────────────────────────────────────
USERNAME = os.getenv("USERNAME", "wmadmin")
PASSWORD = os.getenv("PASSWORD")

# ── Application defaults ───────────────────────────────────────────────────────
APP_ID = int(os.getenv("APP_ID", "31854"))
PROJECT_ID = int(os.getenv("PROJECT_ID", "215853"))

# ── Java Stats API pagination ──────────────────────────────────────────────────
JAVA_STATS_PAGE_SIZE = int(os.getenv("JAVA_STATS_PAGE_SIZE", "2000"))

# ── Change impact analysis windows ────────────────────────────────────────────
CHANGE_POST_PERIOD = os.getenv("CHANGE_POST_PERIOD", "DAY")
CHANGE_POST_PERIOD_DURATION = int(os.getenv("CHANGE_POST_PERIOD_DURATION", "18"))
CHANGE_PRE_PERIOD = os.getenv("CHANGE_PRE_PERIOD", "DAY")
CHANGE_PRE_PERIOD_DURATION = int(os.getenv("CHANGE_PRE_PERIOD_DURATION", "15"))

# ── ClickHouse ─────────────────────────────────────────────────────────────────
CLICKHOUSE_URL = os.getenv(
    "CLICKHOUSE_URL",
    "http://ec2-47-129-241-41.ap-southeast-1.compute.amazonaws.com:8123"
)
CLICKHOUSE_USERNAME = os.getenv("CLICKHOUSE_USERNAME", "wm_test")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "Watermelon@123")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "metrics")
CLICKHOUSE_INFRA_TABLE = os.getenv("CLICKHOUSE_INFRA_TABLE", "infra_data")

# ── OpenSearch ─────────────────────────────────────────────────────────────────
OPENSEARCH_HOST = os.getenv(
    "OPENSEARCH_HOST",
    "a3e621c5bdd854d52afe8f599d849ed1-1076846566.ap-south-1.elb.amazonaws.com"
)
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "W@terlem0n@123#")
OPENSEARCH_USE_SSL = os.getenv("OPENSEARCH_USE_SSL", "False").lower() == "true"
OPENSEARCH_PAGE_SIZE = int(os.getenv("OPENSEARCH_PAGE_SIZE", "5000"))
