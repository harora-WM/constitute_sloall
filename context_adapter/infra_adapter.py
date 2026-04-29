"""
Infra Adapter - Fetches infrastructure metric records from ClickHouse.

Source table: metrics.infra_data (configurable via CLICKHOUSE_INFRA_TABLE)
Filters: app_id, project_id, and a time window over `record_time`
         (start_time / end_time are Unix epoch milliseconds).

All credentials / host / database / table are read from the central config.py
so this adapter mirrors the pattern used by memory_adapter.py and friends.
"""

import os
import sys
import json
import requests
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# -------------------------------------------------------------------
# ClickHouse fetch
# -------------------------------------------------------------------

def fetch_infra_data(
    app_id: int,
    project_id: int,
    start_time: int,
    end_time: int,
) -> List[Dict[str, Any]]:
    """
    Fetch rows from metrics.infra_data between start_time and end_time (inclusive).

    Args:
        app_id: Application ID to filter on.
        project_id: Project ID to filter on.
        start_time: Window start as Unix epoch milliseconds.
        end_time: Window end as Unix epoch milliseconds.

    Returns:
        List of row dicts (all columns from the table).
    """
    query = f"""
    SELECT * FROM {config.CLICKHOUSE_DATABASE}.{config.CLICKHOUSE_INFRA_TABLE}
    WHERE app_id = {int(app_id)}
      AND project_id = {int(project_id)}
      AND record_time >= fromUnixTimestamp64Milli({int(start_time)})
      AND record_time <= fromUnixTimestamp64Milli({int(end_time)})
    FORMAT JSON
    """

    response = requests.get(
        config.CLICKHOUSE_URL,
        params={"query": query},
        auth=(config.CLICKHOUSE_USERNAME, config.CLICKHOUSE_PASSWORD),
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    data = result.get("data", [])
    print(
        f"✓ Fetched {len(data)} infra records from "
        f"{config.CLICKHOUSE_DATABASE}.{config.CLICKHOUSE_INFRA_TABLE}"
    )
    return data


# -------------------------------------------------------------------
# Orchestrator-facing entry point
# -------------------------------------------------------------------

def fetch_infra_for_orchestrator(
    app_id: int,
    project_id: int,
    start_time: int,
    end_time: int,
) -> Dict[str, Any]:
    """
    Orchestrator-facing function. Returns a structured envelope with filters,
    record count, and raw records suitable for the Layer 2 LLM.

    Args:
        app_id: Application ID.
        project_id: Project ID.
        start_time: Window start (Unix epoch ms).
        end_time: Window end (Unix epoch ms).

    Returns:
        Dict with data_source, filters, total_records, records.
    """
    records = fetch_infra_data(app_id, project_id, start_time, end_time)
    return {
        "data_source": "clickhouse_infra",
        "filters": {
            "app_id": app_id,
            "project_id": project_id,
            "start_time_ms": start_time,
            "end_time_ms": end_time,
        },
        "total_records": len(records),
        "records": records,
    }


# -------------------------------------------------------------------
# Main (standalone run)
# -------------------------------------------------------------------

if __name__ == "__main__":
    print("Infra Adapter - Testing")
    print("=" * 50)

    app_id = config.APP_ID
    project_id = config.PROJECT_ID
    # Time range: last 7 days
    from datetime import datetime, timedelta, timezone
    _now = datetime.now(timezone.utc)
    end_time = int(_now.timestamp() * 1000)
    start_time = int((_now - timedelta(days=7)).timestamp() * 1000)

    print(f"Application ID : {app_id}")
    print(f"Project ID     : {project_id}")
    print(f"Start (ms)     : {start_time}")
    print(f"End   (ms)     : {end_time}\n")

    try:
        result = fetch_infra_for_orchestrator(
            app_id=app_id,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
        )
        output_file = "infra_data_output.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n✓ Saved {result['total_records']} records to {output_file}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
