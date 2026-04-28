"""
GoldenPath Adapter - Fetches top-5 quadrant transaction records for both EB and RESPONSE metrics.

Endpoints:
  /api/transactions/top-5/quadrant/EB       → error-budget quadrant analysis
  /api/transactions/top-5/quadrant/RESPONSE → response-time quadrant analysis
Auth: Keycloak password grant → Bearer token (single token used for both calls)
Filters: application_id, project_id, start_time / end_time (Unix epoch milliseconds)
"""
import os
import sys
import json
import requests
import urllib3
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

KEYCLOAK_URL = config.KEYCLOAK_URL
GOLDEN_PATH_EB_API_URL = config.GOLDEN_PATH_EB_API_URL
GOLDEN_PATH_RESPONSE_API_URL = config.GOLDEN_PATH_RESPONSE_API_URL

QUADRANTS = ("hvhe", "hvle", "lvhe", "lvle")
MIN_ABS_ERROR_RATE = 0.01


def get_access_token(
    username: str,
    password: str,
    keycloak_url: str = KEYCLOAK_URL,
    client_id: str = config.KEYCLOAK_CLIENT_ID,
) -> Optional[str]:
    data = {
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(keycloak_url, data=data, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as exc:
        print(f"[GoldenPathAdapter] ✗ Failed to get access token: {exc}")
        return None


def _fetch_raw(
    token: str,
    application_id: int,
    project_id: int,
    start_time: int,
    end_time: int,
    api_url: str,
    label: str,
) -> Optional[List[Dict[str, Any]]]:
    """Internal: fetch one quadrant endpoint with an already-obtained token."""
    params = {
        "application_id": int(application_id),
        "project_id": int(project_id),
        "start_time": int(start_time),
        "end_time": int(end_time),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(api_url, params=params, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data if isinstance(data, list) else [data]
        print(f"[GoldenPathAdapter] ✓ {label}: fetched {len(records)} record(s)")
        return records
    except Exception as exc:
        status_code = "NA"
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            status_code = exc.response.status_code
        print(f"[GoldenPathAdapter] ✗ {label}: failed — {exc} | status={status_code}")
        return None


def _filter_by_error_rate(
    record: Dict[str, Any],
    min_rate: float = MIN_ABS_ERROR_RATE,
) -> Dict[str, Any]:
    """Keep only transactions where absoluteErrorRateAgainstApplication > min_rate in every quadrant."""
    filtered = dict(record)
    for q in QUADRANTS:
        if q in filtered and "data" in filtered[q]:
            filtered[q] = dict(filtered[q])
            filtered[q]["data"] = [
                t for t in filtered[q]["data"]
                if t.get("absoluteErrorRateAgainstApplication", 0) > min_rate
            ]
    return filtered


def _build_summary(record: Dict[str, Any]) -> Dict[str, int]:
    return {
        "total_transactions": sum(len(record.get(q, {}).get("data", [])) for q in QUADRANTS),
        "hvhe_transactions": len(record.get("hvhe", {}).get("data", [])),
        "hvle_transactions": len(record.get("hvle", {}).get("data", [])),
        "lvhe_transactions": len(record.get("lvhe", {}).get("data", [])),
        "lvle_transactions": len(record.get("lvle", {}).get("data", [])),
    }


def fetch_golden_path_data(
    application_id: int,
    project_id: int,
    start_time: int,
    end_time: int,
    username: str,
    password: str,
    api_url: str = GOLDEN_PATH_EB_API_URL,
) -> Optional[List[Dict[str, Any]]]:
    """Low-level fetch for a single quadrant endpoint (standalone / testing use)."""
    token = get_access_token(username, password)
    if not token:
        return None
    return _fetch_raw(token, application_id, project_id, start_time, end_time, api_url, label=api_url.split("/")[-1])


def fetch_golden_path_for_orchestrator(
    app_id: int = config.APP_ID,
    project_id: int = config.PROJECT_ID,
    start_time: int = None,
    end_time: int = None,
    username: str = config.USERNAME,
    password: str = config.PASSWORD,
) -> Optional[Dict[str, Any]]:
    """
    Orchestrator-facing entry point. Fetches both EB and RESPONSE quadrant data
    using a single Keycloak token and returns a combined structured envelope.
    """
    token = get_access_token(username, password)
    if not token:
        return None

    eb_records = _fetch_raw(
        token, app_id, project_id, start_time, end_time,
        api_url=config.GOLDEN_PATH_EB_API_URL, label="EB",
    )
    response_records = _fetch_raw(
        token, app_id, project_id, start_time, end_time,
        api_url=config.GOLDEN_PATH_RESPONSE_API_URL, label="RESPONSE",
    )

    if eb_records is None and response_records is None:
        return None

    eb_record = _filter_by_error_rate((eb_records or [{}])[0])
    response_record = _filter_by_error_rate((response_records or [{}])[0])

    return {
        "data_source": "golden_path_api",
        "filters": {
            "application_id": app_id,
            "project_id": project_id,
            "start_time_ms": start_time,
            "end_time_ms": end_time,
            "min_absolute_error_rate": MIN_ABS_ERROR_RATE,
        },
        "summary_EB": _build_summary(eb_record),
        "records_EB": [eb_record] if eb_records else [],
        "summary_response": _build_summary(response_record),
        "records_response": [response_record] if response_records else [],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    print("GoldenPath Adapter - Testing (EB + RESPONSE)")
    print("=" * 50)

    app_id = config.APP_ID
    project_id = config.PROJECT_ID
    start_time = 1775586600000
    end_time = 1776969000000

    print(f"Application ID : {app_id}")
    print(f"Project ID     : {project_id}")
    print(f"Start (ms)     : {start_time}")
    print(f"End   (ms)     : {end_time}\n")

    try:
        result = fetch_golden_path_for_orchestrator(
            app_id=app_id,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
            username=config.USERNAME,
            password=config.PASSWORD,
        )
        if result:
            output_file = "golden_path_output.json"
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2, default=str)
            s_eb = result['summary_EB']
            s_resp = result['summary_response']
            print(f"\n✓ Saved to {output_file}")
            print(f"  EB       — total={s_eb['total_transactions']} (hvhe={s_eb['hvhe_transactions']}, hvle={s_eb['hvle_transactions']}, lvhe={s_eb['lvhe_transactions']}, lvle={s_eb['lvle_transactions']})")
            print(f"  RESPONSE — total={s_resp['total_transactions']} (hvhe={s_resp['hvhe_transactions']}, hvle={s_resp['hvle_transactions']}, lvhe={s_resp['lvhe_transactions']}, lvle={s_resp['lvle_transactions']})")
        else:
            print("✗ No data returned")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
