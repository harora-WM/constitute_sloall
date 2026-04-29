"""
Transform Watermelon API response to LLM-ready format.
Combines EB and RESPONSE data categories per service.
Fetches data directly from API.
"""
import os
import sys
import json
import requests
import urllib3
from typing import Dict, List, Any, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def get_access_token(
    username: str,
    password: str,
    keycloak_url: str = config.KEYCLOAK_URL,
    client_id: str = config.KEYCLOAK_CLIENT_ID
) -> Optional[str]:
    """
    Get access token from Keycloak authentication endpoint.

    Args:
        username: Keycloak username
        password: Keycloak password
        keycloak_url: Keycloak token endpoint URL
        client_id: OAuth2 client ID

    Returns:
        Access token string if successful, None otherwise
    """
    # Prepare the request data
    data = {
        'grant_type': 'password',
        'client_id': client_id,
        'username': username,
        'password': password
    }

    # Headers
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        # Suppress SSL warnings
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.post(
            keycloak_url,
            data=data,
            headers=headers,
            verify=False
        )

        response.raise_for_status()
        response_data = response.json()
        access_token = response_data.get('access_token')

        if access_token:
            print("✓ Successfully obtained access token")
            return access_token
        else:
            print("✗ No access_token found in response")
            return None

    except Exception as e:
        print(f"✗ Failed to get access token: {e}")
        return None


def fetch_api_data(
    start_time_ms: str,
    end_time_ms: str,
    username: str,
    password: str,
    application_id: int,
    index: str,
    project_id: int = config.PROJECT_ID
) -> Optional[List[Dict]]:
    """
    Fetch transaction data directly from Watermelon API.

    Args:
        start_time_ms: Start time in Unix milliseconds
        end_time_ms: End time in Unix milliseconds
        username: Keycloak username
        password: Keycloak password
        application_id: Application ID (e.g., 31854 for WMPlatform)
        index: Time granularity (options: 'HOURLY', 'DAILY', 'WEEKLY', 'MONTHLY')
        project_id: Project ID (e.g., 215853)

    Returns:
        List of transaction records if successful, None otherwise
    """
    # Get access token
    token = get_access_token(username, password)
    if not token:
        return None

    # API endpoint and parameters
    transactions_url = config.JAVA_STATS_API_URL
    params = {
        'application_id': application_id,
        'project_id': project_id,
        'page_id': 0,
        'page_size': config.JAVA_STATS_PAGE_SIZE,
        'range': 'CUSTOM',
        'index': index,
        'start_time': start_time_ms,
        'end_time': end_time_ms
    }
    headers = {
        'Authorization': f'Bearer {token}'
    }

    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.get(
            transactions_url,
            params=params,
            headers=headers,
            verify=False
        )

        response.raise_for_status()
        data = response.json()

        print(f"✓ Successfully fetched {len(data)} records from API")
        return data

    except Exception as e:
        print(f"✗ Failed to fetch data from API: {e}")
        return None


def transform_eb_service(eb_record: Dict) -> Dict[str, Any]:
    """
    Transform EB record into service format.

    Args:
        eb_record: Record with dataCategory = "EB"

    Returns:
        Formatted EB service dictionary
    """
    return {
        "service_id": eb_record.get("transactionId"),
        "service": eb_record.get("transactionName", ""),
        "health": eb_record.get("ebHealth", "HEALTHY"),
        "success": {
            "rate": round(eb_record.get("successRate", 0), 2),
            "target": eb_record.get("shortTargetSLO", 0),
            "breached": eb_record.get("ebBreached", False)
        },
        "latency": {
            "p95": round(eb_record.get("avgPercentiles", {}).get("95.0", 0), 2),
            "target_seconds": eb_record.get("responseSlo", 0),
            "target_percent": eb_record.get("responseTargetPercent", 0),
            "breach_count": int(eb_record.get("responseBreachCount", 0))
        },
        "volume": {
            "total_requests": int(eb_record.get("totalCount", 0)),
            "errors": int(eb_record.get("errorCount", 0))
        },
        "risk": {
            "burn_rate": round(eb_record.get("burnRate", 0), 2)
        }
    }


def transform_response_service(response_record: Dict) -> Dict[str, Any]:
    """
    Transform RESPONSE record into service format.

    Args:
        response_record: Record with dataCategory = "RESPONSE"

    Returns:
        Formatted RESPONSE service dictionary
    """
    return {
        "service_id": response_record.get("transactionId"),
        "service": response_record.get("transactionName", ""),
        "health": response_record.get("responseHealth", "HEALTHY"),
        "success": {
            "rate": round(response_record.get("successRate", 0), 2),
            "target": response_record.get("shortTargetSLO", 0),
            "breached": response_record.get("ebBreached", False)
        },
        "latency": {
            "p95": round(response_record.get("avgPercentiles", {}).get("95.0", 0), 2),
            "target_seconds": response_record.get("responseSlo", 0),
            "target_percent": response_record.get("responseTargetPercent", 0),
            "breach_count": int(response_record.get("responseBreachCount", 0))
        },
        "volume": {
            "total_requests": int(response_record.get("totalCount", 0)),
            "errors": int(response_record.get("errorCount", 0))
        },
        "risk": {
            "burn_rate": round(response_record.get("burnRate", 0), 2)
        }
    }


def transform_to_llm_format(raw_data: List[Dict], start_time_ms: str, end_time_ms: str) -> Dict[str, Any]:
    """
    Transform raw API response to LLM-ready format with separate EB and RESPONSE arrays.

    Args:
        raw_data: List of transaction records from API
        start_time_ms: Start time in milliseconds (string)
        end_time_ms: End time in milliseconds (string)

    Returns:
        LLM-ready formatted dictionary with 4 separate arrays
    """
    # Separate EB and RESPONSE records
    eb_services = []
    response_services = []

    for record in raw_data:
        data_category = record.get("dataCategory")

        if data_category == "EB":
            eb_service = transform_eb_service(record)
            eb_services.append(eb_service)
        elif data_category == "RESPONSE":
            response_service = transform_response_service(record)
            response_services.append(response_service)

    # Filter and categorize EB services
    eb_unhealthy = [s for s in eb_services if s["health"] == "UNHEALTHY"]
    eb_at_risk = [s for s in eb_services if s["health"] == "AT_RISK"]
    eb_healthy = [s for s in eb_services if s["health"] == "HEALTHY"]

    # Filter and categorize RESPONSE services
    response_unhealthy = [s for s in response_services if s["health"] == "UNHEALTHY"]
    response_at_risk = [s for s in response_services if s["health"] == "AT_RISK"]
    response_healthy = [s for s in response_services if s["health"] == "HEALTHY"]

    # Sort all arrays by volume (total_requests descending)
    eb_unhealthy.sort(key=lambda x: x["volume"]["total_requests"], reverse=True)
    eb_at_risk.sort(key=lambda x: x["volume"]["total_requests"], reverse=True)
    response_unhealthy.sort(key=lambda x: x["volume"]["total_requests"], reverse=True)
    response_at_risk.sort(key=lambda x: x["volume"]["total_requests"], reverse=True)

    # Convert timestamps to readable dates
    start_date = datetime.fromtimestamp(int(start_time_ms) / 1000).strftime("%Y-%m-%d")
    end_date = datetime.fromtimestamp(int(end_time_ms) / 1000).strftime("%Y-%m-%d")

    # Get application name and granularity from first record
    application_name = raw_data[0].get("applicationName", "WMPlatform") if raw_data else "WMPlatform"
    granularity = raw_data[0].get("index", "DAILY") if raw_data else "DAILY"

    # Build final structure
    return {
        "application": application_name,
        "window": {
            "start": start_date,
            "end": end_date,
            "granularity": granularity
        },

        "stats": {
            "total_slos": len(raw_data),
            "unhealthy_slo": len(eb_unhealthy) + len(response_unhealthy),
            "at_risk_slo": len(eb_at_risk) + len(response_at_risk),
            "healthy_slo": len(eb_healthy) + len(response_healthy),
            "eb_unhealthy": len(eb_unhealthy),
            "eb_at_risk": len(eb_at_risk),
            "eb_healthy": len(eb_healthy),
            "response_unhealthy": len(response_unhealthy),
            "response_at_risk": len(response_at_risk),
            "response_healthy": len(response_healthy)
        },

        "unhealthy_services_eb": eb_unhealthy,
        "at_risk_services_eb": eb_at_risk,
        "unhealthy_services_response": response_unhealthy,
        "at_risk_services_response": response_at_risk
    }


if __name__ == "__main__":
    print("Fetching and Transforming API Data to LLM Format")
    print("=" * 50)

    # Configuration parameters
    username = config.USERNAME
    password = config.PASSWORD
    application_id = config.APP_ID
    project_id = config.PROJECT_ID
    index = 'DAILY'

    # Time range (Unix timestamps in milliseconds)
    start_time = '1774752587000'
    end_time = '1777430987000'

    # Fetch data from API
    print("\n--- Fetching data from API ---")
    raw_data = fetch_api_data(
        start_time,
        end_time,
        username,
        password,
        application_id,
        index,
        project_id
    )

    if not raw_data:
        print("✗ Failed to fetch data from API. Exiting.")
        exit(1)

    # Transform
    print("\n--- Transforming data ---")
    llm_format = transform_to_llm_format(raw_data, start_time, end_time)

    # Save output
    with open('llm_ready_output.json', 'w') as f:
        json.dump(llm_format, f, indent=2)

    print(f"✓ Transformed data saved to llm_ready_output.json")
    print(f"\nSLO Summary:")
    print(f"  Total SLOs: {llm_format['stats']['total_slos']}")
    print(f"  Unhealthy SLO: {llm_format['stats']['unhealthy_slo']}")
    print(f"  At Risk SLO: {llm_format['stats']['at_risk_slo']}")
    print(f"  Healthy SLO: {llm_format['stats']['healthy_slo']}")
    print(f"\nEB SLOs:")
    print(f"  EB Unhealthy: {llm_format['stats']['eb_unhealthy']}")
    print(f"  EB At Risk: {llm_format['stats']['eb_at_risk']}")
    print(f"  EB Healthy: {llm_format['stats']['eb_healthy']}")
    print(f"\nResponse SLOs:")
    print(f"  Response Unhealthy: {llm_format['stats']['response_unhealthy']}")
    print(f"  Response At Risk: {llm_format['stats']['response_at_risk']}")
    print(f"  Response Healthy: {llm_format['stats']['response_healthy']}")
    print(f"\nOutput Arrays:")
    print(f"  Unhealthy Services (EB): {len(llm_format['unhealthy_services_eb'])}")
    print(f"  At Risk Services (EB): {len(llm_format['at_risk_services_eb'])}")
    print(f"  Unhealthy Services (RESPONSE): {len(llm_format['unhealthy_services_response'])}")
    print(f"  At Risk Services (RESPONSE): {len(llm_format['at_risk_services_response'])}")
