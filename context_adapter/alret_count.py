"""
Fetch alerts-action count data from Watermelon API.
"""
import os
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
import urllib3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

KEYCLOAK_URL = config.KEYCLOAK_URL
ALERTS_COUNT_URL = config.ALERTS_COUNT_API_URL


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
        response = requests.post(
            keycloak_url,
            data=data,
            headers=headers,
            verify=False,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as exc:
        print(f"Failed to get access token: {exc}")
        return None


def _parse_count_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        raw_text = response.text.strip()
        if raw_text.isdigit():
            return int(raw_text)
        try:
            return float(raw_text)
        except ValueError:
            return raw_text


def fetch_alerts_action_count(
    start_date_ms: str,
    end_date_ms: str,
    application_slo_filters: List[Dict[str, Any]],
    username: str,
    password: str,
    project_id: int = config.PROJECT_ID,
    api_url: str = ALERTS_COUNT_URL,
) -> Optional[Any]:
    token = get_access_token(username, password)
    if not token:
        return None

    params = {"startDate": start_date_ms, "endDate": end_date_ms, "project_id": project_id}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }

    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(
            api_url,
            params=params,
            json=application_slo_filters,
            headers=headers,
            verify=False,
            timeout=30,
        )
        response.raise_for_status()
        return _parse_count_response(response)
    except Exception as exc:
        status_code = "NA"
        allow_header = "NA"
        response_text = ""
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            status_code = str(exc.response.status_code)
            allow_header = exc.response.headers.get("Allow", "NA")
            response_text = exc.response.text[:500]
        print(
            "Failed to fetch alerts-action count: "
            f"{exc} | status={status_code} | allow={allow_header} | body={response_text}"
        )
        return None


def main(
    username: str,
    password: str,
    start_date_ms: str,
    end_date_ms: str,
    application_slo_filters: List[Dict[str, Any]],
    project_id: int = config.PROJECT_ID,
    output_file: str = "alerts_action_count_output.json",
) -> int:
    response_payload = fetch_alerts_action_count(
        start_date_ms=start_date_ms,
        end_date_ms=end_date_ms,
        application_slo_filters=application_slo_filters,
        username=username,
        password=password,
        project_id=project_id,
    )
    if response_payload is None:
        return 1

    output: Dict[str, Any] = {
        "request": {
            "endpoint": ALERTS_COUNT_URL,
            "startDate": start_date_ms,
            "endDate": end_date_ms,
            "applicationSloFilters": application_slo_filters,
        },
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "response": response_payload,
    }

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2)

    print(f"Saved alerts-action count response to {output_file}")
    return 0


def fetch_alerts_for_orchestrator(
    start_time_ms: str,
    end_time_ms: str,
    app_id: int = config.APP_ID,
    project_id: int = config.PROJECT_ID,
    username: str = config.USERNAME,
    password: str = config.PASSWORD
) -> Optional[Dict[str, Any]]:
    """
    Fetch alerts-action count data for orchestrator integration.

    Args:
        start_time_ms: Start time in milliseconds (string)
        end_time_ms: End time in milliseconds (string)
        app_id: Application ID (default: 31854)
        project_id: Project ID (default: 215853)
        username: Keycloak username
        password: Keycloak password

    Returns:
        Dictionary with alerts count data in orchestrator-compatible format, or None if failed
    """
    # Build application SLO filters using project_id
    # Note: app_id filter returns 0 results — alerts are indexed by project_id (sid)
    application_slo_filters = [
        {"id": project_id, "sloTypes": ["ERROR", "RESPONSE"]}
    ]

    # Fetch the data
    response_payload = fetch_alerts_action_count(
        start_date_ms=start_time_ms,
        end_date_ms=end_time_ms,
        application_slo_filters=application_slo_filters,
        username=username,
        password=password,
        project_id=project_id,
    )

    if response_payload is None:
        return None

    # Return in orchestrator-compatible format
    return {
        "data_source": "alerts_action_count",
        "query": {
            "start_time": start_time_ms,
            "end_time": end_time_ms,
            "app_id": app_id,
            "project_id": project_id,
            "slo_types": ["ERROR", "RESPONSE"]
        },
        "alerts_count": response_payload,
        "fetched_at": datetime.now(timezone.utc).isoformat()
    }


if __name__ == "__main__":
    print("Fetching alerts-action count data from API")
    print("=" * 50)

    # Configuration parameters
    username = config.USERNAME
    password = config.PASSWORD
    start_date = "1771957800000"
    end_date = "1773340200000"
    application_slo_filters = [
        {"id": 32707,  "sloTypes": ["RESPONSE"]},
        {"id": 32752,  "sloTypes": ["ERROR"]},
        {"id": 215853, "sloTypes": ["ERROR", "RESPONSE"]},
        {"id": 217602, "sloTypes": ["ERROR"]},
        {"id": 32753,  "sloTypes": ["ERROR"]},
        {"id": 32722,  "sloTypes": ["ERROR"]},
    ]
    output_file = "alerts_action_count_output.json"

    raise SystemExit(
        main(
            username=username,
            password=password,
            start_date_ms=start_date,
            end_date_ms=end_date,
            application_slo_filters=application_slo_filters,
            output_file=output_file,
        )
    )