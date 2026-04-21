#!/usr/bin/env python3
"""
Test script to verify that alert_count and change_pre_post adapters are integrated
and their data is included in the final JSON output and LLM input.
"""

import json
from main import SLOOrchestrator


def test_integration():
    """Test that all data sources are included in orchestrator output"""
    print("=" * 80)
    print("TESTING NEW ADAPTERS INTEGRATION")
    print("=" * 80)
    
    # Initialize orchestrator
    print("\n[1] Initializing orchestrator...")
    try:
        orchestrator = SLOOrchestrator()
        print("✅ Orchestrator initialized successfully!\n")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return False
    
    # Run a simple test query
    print("[2] Running test query...")
    test_query = "What is the health of my application?"
    
    try:
        result = orchestrator.process_query(test_query)
    except Exception as e:
        print(f"❌ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Check if query was successful
    if not result.get('success'):
        print(f"❌ Query returned error: {result.get('error')}")
        return False
    
    print("✅ Query executed successfully!\n")
    
    # Verify data sources
    print("[3] Verifying data sources in result...")
    data_sources = result.get('data', {}).keys()
    print(f"   Data sources found: {list(data_sources)}")
    
    expected_sources = ['java_stats_api', 'clickhouse', 'alerts_count', 'change_impact']
    missing_sources = []
    
    for source in expected_sources:
        if source in data_sources:
            print(f"   ✅ {source} - PRESENT")
        else:
            print(f"   ❌ {source} - MISSING")
            missing_sources.append(source)
    
    # Check if conversational response was generated
    print("\n[4] Verifying conversational response...")
    if result.get('conversational_response'):
        print("   ✅ Conversational response generated")
        print(f"   Response length: {len(result['conversational_response'])} characters")
    else:
        print("   ❌ No conversational response found")
    
    # Export to JSON for inspection
    print("\n[5] Exporting result to JSON...")
    output_file = "test_integration_result.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"   ✅ Result exported to {output_file}")
    except Exception as e:
        print(f"   ❌ Failed to export: {e}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 80)
    
    if missing_sources:
        print(f"❌ FAILED - Missing data sources: {', '.join(missing_sources)}")
        return False
    else:
        print("✅ SUCCESS - All expected data sources are present!")
        print(f"\nData sources included:")
        for source in data_sources:
            print(f"  • {source}")
        
        print(f"\nConversational response: {'✅ Generated' if result.get('conversational_response') else '❌ Missing'}")
        print(f"Output JSON: {output_file}")
        return True


def test_infra_adapter():
    """Verify infra adapter fires for an INFRA_METRICS-style query."""
    print("\n" + "=" * 80)
    print("TESTING INFRA ADAPTER INTEGRATION")
    print("=" * 80)

    print("\n[1] Initializing orchestrator...")
    try:
        orchestrator = SLOOrchestrator()
        print("✅ Orchestrator initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return False

    # Host-level, percentile-aware phrasing so the classifier routes to INFRA_METRICS
    infra_query = "What's the p95 CPU utilization across hosts in the last 6 hours?"
    print(f"[2] Running infra query: {infra_query!r}")
    try:
        result = orchestrator.process_query(infra_query)
    except Exception as e:
        print(f"❌ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    if not result.get('success'):
        print(f"❌ Query returned error: {result.get('error')}")
        return False

    primary = result.get('classification', {}).get('primary_intent')
    print(f"\n[3] Primary intent: {primary}")

    data_sources = list(result.get('data', {}).keys())
    print(f"   Data sources fetched: {data_sources}")

    infra = result.get('data', {}).get('clickhouse_infra')
    if infra is None:
        print("❌ clickhouse_infra missing from orchestrator output")
        print("   (classifier likely did not emit INFRA_METRICS for this query)")
        return False

    print("   ✅ clickhouse_infra present")
    print(f"   Filters        : {infra.get('filters')}")
    print(f"   Total records  : {infra.get('total_records')}")

    # Shape checks — don't require rows (test env may be empty),
    # just that the envelope is well-formed.
    for key in ("data_source", "filters", "total_records", "records"):
        if key not in infra:
            print(f"❌ Infra envelope missing key: {key}")
            return False

    output_file = "test_infra_result.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n   Result exported to {output_file}")
    print("✅ Infra adapter integration OK")
    return True


if __name__ == "__main__":
    ok_core  = test_integration()
    ok_infra = test_infra_adapter()
    exit(0 if (ok_core and ok_infra) else 1)

