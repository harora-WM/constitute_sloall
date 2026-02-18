"""
Script to get the latest change and fetch top 5 services with deviations.
Combines functionality from changes.py and deviation.py.
"""
import requests
import json
from typing import Optional, Dict, Any


def get_access_token(
    username: str,
    password: str,
    keycloak_url: str = "https://wm-sandbox-auth-1.watermelon.us/realms/watermelon/protocol/openid-connect/token",
    client_id: str = "web_app"
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
        # Make POST request with SSL verification disabled
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.post(
            keycloak_url,
            data=data,
            headers=headers,
            verify=False
        )

        # Check if request was successful
        response.raise_for_status()

        # Parse JSON response
        response_data = response.json()

        # Extract access token
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


def get_latest_change(token: str, application_id: int = 31854) -> Optional[Dict[str, Any]]:
    """
    Get the latest change from release-histories API.

    Args:
        token: Access token for authentication
        application_id: Application ID

    Returns:
        Latest change data if successful, None otherwise
    """
    url = f"https://wm-sandbox-1.watermelon.us/services/wmebonboarding/api/release-histories/application/{application_id}"
    headers = {
        'Authorization': f'Bearer {token}'
    }

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.get(
            url,
            headers=headers,
            verify=False
        )

        response.raise_for_status()
        changes_data = response.json()

        if changes_data and len(changes_data) > 0:
            # The first item is the latest change (sorted by date)
            latest_change = changes_data[0]
            print(f"✓ Found latest change: {latest_change.get('version')} - {latest_change.get('description')}")
            print(f"  Release DateTime: {latest_change.get('releaseDateTime')}")
            print(f"  DateTime Millis: {latest_change.get('dateTimeMillis')}")
            return latest_change
        else:
            print("✗ No changes found")
            return None

    except Exception as e:
        print(f"✗ Failed to get latest change: {e}")
        return None


def get_top_5_eb_deviations(token: str, release_time_millis: int, application_id: int = 31854, sort_order: str = "DESC") -> Optional[Dict[str, Any]]:
    """
    Get top 5 services with EB (Error Budget) deviations for a specific release time.

    Args:
        token: Access token for authentication
        release_time_millis: Release time in milliseconds
        application_id: Application ID
        sort_order: Sort order - "DESC" for positive deviations, "ASC" for negative deviations

    Returns:
        Top 5 EB deviations data if successful, None otherwise
    """
    url = f"https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/release-impact/transactions/top-5/POST?priority=DEVIATION&sort={sort_order}"

    params = {
        "applicationId": application_id,
        "postPeriod": "DAY",
        "postPeriodDuration": 18,
        "prePeriod": "DAY",
        "prePeriodDuration": 15,
        "queryBy": "EB",
        "releaseTime": release_time_millis
    }

    headers = {
        'Authorization': f'Bearer {token}'
    }

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.post(
            url,
            json=params,
            headers=headers,
            verify=False
        )

        response.raise_for_status()
        deviations_data = response.json()

        deviation_type = "positive" if sort_order == "DESC" else "negative"
        print(f"✓ Successfully retrieved top 5 {deviation_type} EB deviations")
        print(f"  Number of services: {len(deviations_data)}")

        return deviations_data

    except Exception as e:
        print(f"✗ Failed to get top 5 EB deviations ({sort_order}): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response status: {e.response.status_code}")
            print(f"  Response text: {e.response.text[:500]}")
        return None


def get_top_5_response_deviations(token: str, release_time_millis: int, application_id: int = 31854, sort_order: str = "DESC") -> Optional[Dict[str, Any]]:
    """
    Get top 5 services with RESPONSE deviations for a specific release time.

    Args:
        token: Access token for authentication
        release_time_millis: Release time in milliseconds
        application_id: Application ID
        sort_order: Sort order - "DESC" for positive deviations, "ASC" for negative deviations

    Returns:
        Top 5 RESPONSE deviations data if successful, None otherwise
    """
    url = f"https://wm-sandbox-1.watermelon.us/services/wmerrorbudgetstatisticsservice/api/release-impact/transactions/top-5/POST?priority=DEVIATION&sort={sort_order}"

    params = {
        "applicationId": application_id,
        "postPeriod": "DAY",
        "postPeriodDuration": 18,
        "prePeriod": "DAY",
        "prePeriodDuration": 15,
        "queryBy": "RESPONSE",
        "releaseTime": release_time_millis
    }

    headers = {
        'Authorization': f'Bearer {token}'
    }

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.post(
            url,
            json=params,
            headers=headers,
            verify=False
        )

        response.raise_for_status()
        deviations_data = response.json()

        deviation_type = "positive" if sort_order == "DESC" else "negative"
        print(f"✓ Successfully retrieved top 5 {deviation_type} RESPONSE deviations")
        print(f"  Number of services: {len(deviations_data)}")

        return deviations_data

    except Exception as e:
        print(f"✗ Failed to get top 5 RESPONSE deviations ({sort_order}): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response status: {e.response.status_code}")
            print(f"  Response text: {e.response.text[:500]}")
        return None


def fetch_change_impact_for_orchestrator(
    application_id: int = 31854,
    username: str = "wmadmin",
    password: str = "WM@Dm1n@#2024!!$"
) -> Optional[Dict[str, Any]]:
    """
    Fetch latest change and its impact (pre/post deviations) for orchestrator integration.

    Args:
        application_id: Application ID (default: 31854)
        username: Keycloak username
        password: Keycloak password

    Returns:
        Dictionary with change impact data in orchestrator-compatible format, or None if failed
    """
    # Step 1: Get access token
    token = get_access_token(username, password)
    if not token:
        print("✗ Failed to obtain access token for change impact data")
        return None

    # Step 2: Get latest change
    latest_change = get_latest_change(token, application_id)
    if not latest_change:
        print("✗ Failed to get latest change for change impact data")
        return None

    release_time_millis = latest_change.get('dateTimeMillis')
    if not release_time_millis:
        print("✗ No dateTimeMillis found in latest change")
        return None

    # Step 3: Get all deviations (EB and RESPONSE, positive and negative)
    positive_eb = get_top_5_eb_deviations(token, release_time_millis, application_id, sort_order="DESC")
    negative_eb = get_top_5_eb_deviations(token, release_time_millis, application_id, sort_order="ASC")
    positive_response = get_top_5_response_deviations(token, release_time_millis, application_id, sort_order="DESC")
    negative_response = get_top_5_response_deviations(token, release_time_millis, application_id, sort_order="ASC")

    # Return in orchestrator-compatible format
    return {
        "data_source": "change_pre_post_impact",
        "latest_change": {
            "version": latest_change.get('version'),
            "description": latest_change.get('description'),
            "releaseDateTime": latest_change.get('releaseDateTime'),
            "dateTimeMillis": latest_change.get('dateTimeMillis')
        },
        "eb_deviations": {
            "top_5_positive": positive_eb if positive_eb else [],
            "top_5_negative": negative_eb if negative_eb else []
        },
        "response_deviations": {
            "top_5_positive": positive_response if positive_response else [],
            "top_5_negative": negative_response if negative_response else []
        },
        "stats": {
            "total_eb_deviations": (len(positive_eb) if positive_eb else 0) + (len(negative_eb) if negative_eb else 0),
            "total_response_deviations": (len(positive_response) if positive_response else 0) + (len(negative_response) if negative_response else 0)
        }
    }


if __name__ == "__main__":
    print("=" * 70)
    print("Top 5 Deviation Services for Latest Change")
    print("=" * 70)

    # Hardcoded credentials
    username = "wmadmin"
    password = "WM@Dm1n@#2024!!$"

    # Step 1: Get access token
    print("\n[Step 1] Getting Access Token...")
    token = get_access_token(username, password)

    if not token:
        print("\n✗ Failed to obtain access token. Exiting.")
        exit(1)

    # Step 2: Get latest change
    print("\n[Step 2] Fetching Latest Change...")
    latest_change = get_latest_change(token)

    if not latest_change:
        print("\n✗ Failed to get latest change. Exiting.")
        exit(1)

    # Step 3: Get top 5 deviations for the latest change
    print("\n[Step 3] Fetching Top 5 Deviations...")
    release_time_millis = latest_change.get('dateTimeMillis')

    if not release_time_millis:
        print("\n✗ No dateTimeMillis found in latest change. Exiting.")
        exit(1)

    # Get EB deviations (positive and negative)
    print("\n  [3a] Fetching EB Deviations...")
    print("    [3a.1] Fetching Positive EB Deviations (DESC)...")
    positive_eb_deviations = get_top_5_eb_deviations(token, release_time_millis, sort_order="DESC")

    print("    [3a.2] Fetching Negative EB Deviations (ASC)...")
    negative_eb_deviations = get_top_5_eb_deviations(token, release_time_millis, sort_order="ASC")

    # Get RESPONSE deviations (positive and negative)
    print("\n  [3b] Fetching RESPONSE Deviations...")
    print("    [3b.1] Fetching Positive RESPONSE Deviations (DESC)...")
    positive_response_deviations = get_top_5_response_deviations(token, release_time_millis, sort_order="DESC")

    print("    [3b.2] Fetching Negative RESPONSE Deviations (ASC)...")
    negative_response_deviations = get_top_5_response_deviations(token, release_time_millis, sort_order="ASC")

    # Check if we got any data
    if (positive_eb_deviations is not None or negative_eb_deviations is not None or
        positive_response_deviations is not None or negative_response_deviations is not None):

        # Save the results to a JSON file
        output_file = 'top_5_deviations_result.json'
        result = {
            "latest_change": {
                "version": latest_change.get('version'),
                "description": latest_change.get('description'),
                "releaseDateTime": latest_change.get('releaseDateTime'),
                "dateTimeMillis": latest_change.get('dateTimeMillis')
            },
            "eb_deviations": {
                "top_5_positive": positive_eb_deviations if positive_eb_deviations else [],
                "top_5_negative": negative_eb_deviations if negative_eb_deviations else []
            },
            "response_deviations": {
                "top_5_positive": positive_response_deviations if positive_response_deviations else [],
                "top_5_negative": negative_response_deviations if negative_response_deviations else []
            }
        }

        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"\n✓ Saved results to {output_file}")

        # Display summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Latest Change: {latest_change.get('version')}")
        print(f"Description: {latest_change.get('description')}")
        print(f"Release Time: {latest_change.get('releaseDateTime')}")

        # Display EB deviations
        print("\n" + "-" * 70)
        print("ERROR BUDGET (EB) DEVIATIONS")
        print("-" * 70)

        if positive_eb_deviations:
            print(f"\nTop 5 Services with Positive EB Deviations:")
            for idx, service in enumerate(positive_eb_deviations, 1):
                service_name = service.get('transactionName', 'Unknown')
                deviation = service.get('deviation', 'N/A')
                print(f"  {idx}. {service_name} - Deviation: {deviation}")

        if negative_eb_deviations:
            print(f"\nTop 5 Services with Negative EB Deviations:")
            for idx, service in enumerate(negative_eb_deviations, 1):
                service_name = service.get('transactionName', 'Unknown')
                deviation = service.get('deviation', 'N/A')
                print(f"  {idx}. {service_name} - Deviation: {deviation}")

        # Display RESPONSE deviations
        print("\n" + "-" * 70)
        print("RESPONSE TIME DEVIATIONS")
        print("-" * 70)

        if positive_response_deviations:
            print(f"\nTop 5 Services with Positive RESPONSE Deviations:")
            for idx, service in enumerate(positive_response_deviations, 1):
                service_name = service.get('transactionName', 'Unknown')
                deviation = service.get('deviation', 'N/A')
                print(f"  {idx}. {service_name} - Deviation: {deviation}")

        if negative_response_deviations:
            print(f"\nTop 5 Services with Negative RESPONSE Deviations:")
            for idx, service in enumerate(negative_response_deviations, 1):
                service_name = service.get('transactionName', 'Unknown')
                deviation = service.get('deviation', 'N/A')
                print(f"  {idx}. {service_name} - Deviation: {deviation}")

        print("=" * 70)
    else:
        print("\n✗ Failed to get any deviations. Exiting.")
        exit(1)
