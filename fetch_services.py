#!/usr/bin/env python3
"""
Service Mapping Fetcher
Fetches all distinct services for an application from ClickHouse and creates a service mapping YAML file
"""

import os
import sys
import requests
import json
import yaml
from typing import Dict, List, Any
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ClickHouse Configuration
CLICKHOUSE_URL = config.CLICKHOUSE_URL
CLICKHOUSE_USER = config.CLICKHOUSE_USERNAME
CLICKHOUSE_PASSWORD = config.CLICKHOUSE_PASSWORD
CLICKHOUSE_DB = config.CLICKHOUSE_DATABASE
CLICKHOUSE_TABLE = config.CLICKHOUSE_SERVICES_TABLE


def fetch_distinct_services(application_id: int) -> List[Dict[str, Any]]:
    """
    Fetch all distinct services and their IDs for a given application from ClickHouse

    Args:
        application_id: Application ID to fetch services for

    Returns:
        List of dictionaries with service and service_id
    """

    query = f"""
    SELECT DISTINCT
        service,
        service_id,
        application_id
    FROM {CLICKHOUSE_DB}.{CLICKHOUSE_TABLE}
    WHERE application_id = {application_id}
    ORDER BY service_id ASC
    FORMAT JSONEachRow
    """

    try:
        response = requests.get(
            CLICKHOUSE_URL,
            auth=(CLICKHOUSE_USER, CLICKHOUSE_PASSWORD),
            params={"query": query.strip()},
            timeout=30
        )
        response.raise_for_status()

        # Parse JSONEachRow format
        services = [
            json.loads(line)
            for line in response.text.strip().split("\n")
            if line.strip()
        ]

        print(f"✓ Fetched {len(services)} distinct services for application_id={application_id}")
        return services

    except requests.exceptions.Timeout as e:
        print(f"✗ ClickHouse timeout after 30s: {e}")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Cannot connect to ClickHouse: {e}")
        raise
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"✗ ClickHouse authentication failed - check credentials")
        else:
            print(f"✗ ClickHouse HTTP error {e.response.status_code}: {e.response.text}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")
        raise


def extract_service_name(service_url: str) -> str:
    """
    Extract a clean service name from the full service URL

    Examples:
        "GET https://example.com:443/services/wmtest/api/test-runs" -> "wmtest/api/test-runs"
        "POST https://example.com/api/users" -> "api/users"

    Args:
        service_url: Full service URL with method

    Returns:
        Cleaned service name
    """
    try:
        # Remove HTTP method (GET, POST, etc.)
        parts = service_url.split(maxsplit=1)
        if len(parts) == 2:
            url = parts[1]
        else:
            url = service_url

        # Extract path after domain
        if "://" in url:
            # Split by :// and take everything after domain:port
            after_protocol = url.split("://", 1)[1]
            if "/" in after_protocol:
                path = after_protocol.split("/", 1)[1]
            else:
                path = after_protocol
        else:
            path = url

        # Remove /services/ prefix if exists
        if path.startswith("services/"):
            path = path[9:]  # len("services/") = 9

        return path

    except Exception:
        # If parsing fails, return original
        return service_url


def create_service_mapping(services: List[Dict[str, Any]], include_clean_names: bool = True) -> Dict[str, Any]:
    """
    Create a structured service mapping from raw service data

    Args:
        services: List of service dictionaries from ClickHouse
        include_clean_names: Whether to include cleaned service names

    Returns:
        Structured mapping dictionary
    """

    # Create mapping by service_id
    services_by_id = {}

    # Track application_id
    app_id = services[0]['application_id'] if services else None

    for svc in services:
        service_id = svc['service_id']
        service_name = svc['service']

        service_entry = {
            'service_id': service_id,
            'service_name': service_name,
        }

        # Add cleaned name if requested
        if include_clean_names:
            clean_name = extract_service_name(service_name)
            service_entry['service_path'] = clean_name

        services_by_id[service_id] = service_entry

    return {
        'application_id': app_id,
        'total_services': len(services),
        'services_by_id': services_by_id,
        'metadata': {
            'source': 'ClickHouse',
            'database': CLICKHOUSE_DB,
            'table': CLICKHOUSE_TABLE,
            'generated_at': None  # Will be set during save
        }
    }


def save_to_yaml(data: Dict[str, Any], output_file: str = "services.yaml") -> None:
    """
    Save service mapping to YAML file

    Args:
        data: Service mapping dictionary
        output_file: Output YAML file path
    """
    from datetime import datetime

    # Add timestamp
    data['metadata']['generated_at'] = datetime.now().isoformat()

    try:
        with open(output_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"✓ Saved service mapping to {output_file}")
        print(f"  Total services: {data['total_services']}")
        print(f"  Application ID: {data['application_id']}")

    except Exception as e:
        print(f"✗ Failed to save YAML file: {e}")
        raise


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch service mapping from ClickHouse")
    parser.add_argument(
        '--app-id',
        type=int,
        default=config.APP_ID,
        help=f'Application ID to fetch services for (default: {config.APP_ID})'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='services.yaml',
        help='Output YAML file path (default: services.yaml)'
    )
    parser.add_argument(
        '--no-clean-names',
        action='store_true',
        help='Do not include cleaned service path names'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("SERVICE MAPPING FETCHER")
    print("=" * 80)
    print(f"\nApplication ID: {args.app_id}")
    print(f"Output file: {args.output}")
    print()

    # Fetch services
    print("Fetching services from ClickHouse...")
    services = fetch_distinct_services(args.app_id)

    if not services:
        print("⚠ No services found for this application ID")
        return

    # Create mapping
    print("\nCreating service mapping...")
    mapping = create_service_mapping(services, include_clean_names=not args.no_clean_names)

    # Save to YAML
    print("\nSaving to YAML...")
    save_to_yaml(mapping, args.output)

    # Print sample
    print("\n" + "=" * 80)
    print("SAMPLE SERVICES (first 5):")
    print("=" * 80)
    for i, (service_id, service_info) in enumerate(list(mapping['services_by_id'].items())[:5]):
        print(f"\nService ID: {service_id}")
        print(f"  Full Name: {service_info['service_name'][:80]}...")
        if 'service_path' in service_info:
            print(f"  Clean Path: {service_info['service_path']}")

    print("\n" + "=" * 80)
    print(f"✅ Complete! Check {args.output} for full mapping")
    print("=" * 80)


if __name__ == "__main__":
    main()
