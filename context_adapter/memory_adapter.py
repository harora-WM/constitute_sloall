"""
Service Behavior Memory Adapter
Fetches Service's behavioral patterns from ClickHouse for specific application and service within time range
Returns all patterns from ai_service_behavior_memory table without intent-based filtering
"""

import os
import sys
import json
import requests
from typing import Dict, List, Any, Optional, Set
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# -------------------------------------------------------------------
# Time helper
# -------------------------------------------------------------------

def ms_to_datetime_str(timestamp_ms: int) -> str:
    """
    Convert Unix timestamp in milliseconds to ClickHouse-compatible datetime string

    Args:
        timestamp_ms: Unix timestamp in milliseconds

    Returns:
        Datetime string in format 'YYYY-MM-DD HH:MM:SS'
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# -------------------------------------------------------------------
# ClickHouse fetch
# -------------------------------------------------------------------

def fetch_behavior_service_memory(
    start_time: int,
    end_time: int,
    app_id: int,
    project_id: int,
    sid: Optional[str] = None,
    service_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch behavior service memory records from ClickHouse for specific application and service

    Note: start_time and end_time are kept for backward compatibility but NOT used in filtering.
    This function returns ALL behavior patterns for the application regardless of time range.

    Args:
        start_time: Start time in Unix milliseconds (not used for filtering)
        end_time: End time in Unix milliseconds (not used for filtering)
        app_id: Application ID
        project_id: Project ID
        sid: Service name (optional - fallback filter if service_id not provided)
        service_id: Resolved service ID from service_matcher (preferred filter)

    Returns:
        List of ALL behavior memory records for the application
    """

    clickhouse_url = config.CLICKHOUSE_URL
    auth = (config.CLICKHOUSE_USERNAME, config.CLICKHOUSE_PASSWORD)

    # Build WHERE clause - filter by app_id, project_id, and service_id (preferred) or service name
    where_clause = f"WHERE application_id = {app_id}\n      AND project_id = {project_id}"

    if service_id is not None:
        where_clause += f"\n      AND service_id = {service_id}"
    elif sid:
        where_clause += f"\n      AND service = '{sid}'"

    query = f"""
    SELECT
        application_id,
        project_id,
        service_id,
        service,
        metric,
        baseline_state,
        baseline_value,
        pattern_type,
        pattern_window,
        delta_success,
        delta_latency_p90,
        support_days,
        confidence,
        long_term,
        recency,
        first_seen,
        last_seen,
        detected_at
    FROM ai_service_behavior_memory
    {where_clause}
    ORDER BY detected_at DESC
    FORMAT JSONEachRow
    """

    try:
        response = requests.get(
            clickhouse_url,
            auth=auth,
            params={
                "query": query.strip(),
                "database": config.CLICKHOUSE_DATABASE
            },
            timeout=30
        )
        response.raise_for_status()

        rows = [
            json.loads(line)
            for line in response.text.strip().split("\n")
            if line.strip()
        ]

        print(f"✓ Fetched {len(rows)} behavior records")
        return rows

    except requests.exceptions.Timeout as e:
        print(f"✗ ClickHouse timeout after 30s: {e}")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Cannot connect to ClickHouse: {e}")
        raise
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"✗ ClickHouse authentication failed - check credentials")
        elif e.response.status_code == 400:
            print(f"✗ Invalid SQL query: {e.response.text}")
        else:
            print(f"✗ ClickHouse HTTP error {e.response.status_code}: {e.response.text}")
        raise
    except json.JSONDecodeError as e:
        print(f"✗ Failed to parse ClickHouse response as JSON: {e}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")
        raise


# -------------------------------------------------------------------
# Transform to LLM format
# -------------------------------------------------------------------

def transform_behavior_memory(
    rows: List[Dict[str, Any]],
    start_time: int,
    end_time: int,
    app_id: int,
    project_id: int,
    sid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Transform behavior memory records to LLM-ready format

    Args:
        rows: List of raw behavior memory records from ClickHouse
        start_time: Start time in Unix milliseconds
        end_time: End time in Unix milliseconds
        app_id: Application ID
        sid: Service name (optional)

    Returns:
        LLM-ready formatted dictionary
    """

    # Define required fields
    REQUIRED_FIELDS = [
        "application_id", "service_id", "service", "metric", "baseline_state", "baseline_value",
        "pattern_type", "pattern_window", "delta_success", "delta_latency_p90",
        "support_days", "confidence", "first_seen", "last_seen", "detected_at"
    ]

    services = set()
    patterns = []
    skipped_records = 0

    for i, r in enumerate(rows):
        # Validate required fields exist
        missing_fields = [field for field in REQUIRED_FIELDS if field not in r]

        if missing_fields:
            print(f"⚠ Warning: Record {i} missing fields {missing_fields}, skipping...")
            skipped_records += 1
            continue

        try:
            services.add(r["service"])

            patterns.append({
                "application_id": r["application_id"],
                "service_id": r["service_id"],
                "service": r["service"],
                "metric": r["metric"],
                "baseline_state": r["baseline_state"],
                "baseline_value": r["baseline_value"],
                "pattern_type": r["pattern_type"],
                "pattern_window": r["pattern_window"],
                "delta": {
                    "success": r["delta_success"],
                    "latency_p90": r["delta_latency_p90"]
                },
                "support_days": r["support_days"],
                "confidence": r["confidence"],
                "weights": {
                    "long_term": r.get("long_term"),
                    "recency": r.get("recency")
                },
                "seen": {
                    "first": r["first_seen"],
                    "last": r["last_seen"]
                },
                "detected_at": r["detected_at"]
            })

        except (KeyError, TypeError, ValueError) as e:
            print(f"⚠ Warning: Error processing record {i}: {e}, skipping...")
            skipped_records += 1
            continue

    if skipped_records > 0:
        print(f"⚠ Skipped {skipped_records} invalid records out of {len(rows)}")

    stats = {
        "total_records": len(patterns),
        "services_affected": len(services),
        "chronic": sum(1 for p in patterns if p["baseline_state"] == "CHRONIC"),
        "at_risk": sum(1 for p in patterns if p["baseline_state"] == "AT_RISK"),
        "healthy": sum(1 for p in patterns if p["baseline_state"] == "HEALTHY")
    }

    # Convert timestamps to readable format for display
    start_dt = datetime.fromtimestamp(start_time / 1000).strftime("%Y-%m-%d %H:%M:%S")
    end_dt = datetime.fromtimestamp(end_time / 1000).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "data_source": "ai_service_behavior_memory",
        "query": {
            "application_id": app_id,
            "project_id": project_id,
            "service": sid if sid else "ALL",
            "start_time": start_time,
            "end_time": end_time,
            "start_time_readable": start_dt,
            "end_time_readable": end_dt
        },
        "stats": stats,
        "patterns": patterns
    }


# -------------------------------------------------------------------
# Orchestrator-facing function with intent routing
# -------------------------------------------------------------------

def fetch_patterns_by_intent(
    intents: Set[str],
    start_time: int,
    end_time: int,
    app_id: int,
    project_id: int,
    service_id: Optional[int] = None,
    service_name: Optional[str] = None,
    incident_timestamp: Optional[int] = None
) -> Dict[str, Any]:
    """
    Orchestrator-facing function that fetches ALL behavior memory data

    Simplified to return all patterns from ai_service_behavior_memory table
    regardless of specific intents. This provides complete context to the LLM
    without filtering by pattern types.

    Args:
        intents: Set of intent names (primary, secondary, enriched combined)
        start_time: Start time in Unix milliseconds
        end_time: End time in Unix milliseconds
        app_id: Application ID
        project_id: Project ID
        service_id: Optional service ID (resolved from service name)
        service_name: Optional service name (raw from intent classifier)
        incident_timestamp: Optional incident timestamp (currently not used)

    Returns:
        Dictionary with all behavior memory patterns in the time range
    """
    print("   Fetching all behavior patterns from ai_service_behavior_memory")

    # Fetch all behavior memory records for the given time range and app_id/project_id
    # Prefer service_id filter (exact match) over raw service_name
    rows = fetch_behavior_service_memory(start_time, end_time, app_id, project_id, service_name, service_id)

    # Transform to LLM-ready format
    result = transform_behavior_memory(rows, start_time, end_time, app_id, project_id, service_name)

    # Add metadata about which intents triggered this fetch
    result["triggered_by_intents"] = list(intents) if intents else []

    return result


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

if __name__ == "__main__":
    # Example usage
    # Time range: Last 30 days from now
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    end_time = int(now.timestamp() * 1000)
    start_time = int((now - timedelta(days=30)).timestamp() * 1000)

    # Example parameters
    APP_ID = config.APP_ID
    PROJECT_ID = config.PROJECT_ID
    SID = None  # None = fetch all services, or specify like "payment-api"

    print("Fetching AI Service Behavior Memory")
    print("=" * 50)
    print(f"Application ID: {APP_ID}")
    print(f"Project ID: {PROJECT_ID}")
    print(f"Service: {SID if SID else 'ALL'}")
    print(f"Time Range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")
    print()

    raw_rows = fetch_behavior_service_memory(start_time, end_time, APP_ID, PROJECT_ID, SID)
    llm_output = transform_behavior_memory(raw_rows, start_time, end_time, APP_ID, PROJECT_ID, SID)

    output_file = "ai_service_behavior_memory_output.json"
    with open(output_file, "w") as f:
        json.dump(llm_output, f, indent=2)

    print(f"\n✓ Saved {output_file}")
    print(f"Records           : {llm_output['stats']['total_records']}")
    print(f"Services affected : {llm_output['stats']['services_affected']}")
    print(f"Chronic           : {llm_output['stats']['chronic']}")
    print(f"At Risk           : {llm_output['stats']['at_risk']}")
    print(f"Healthy           : {llm_output['stats']['healthy']}")
