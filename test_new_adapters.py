#!/usr/bin/env python3
"""
Test script to verify that alert_count and change_pre_post adapters are integrated
and their data is included in the final JSON output and LLM input.
"""

import json
from orchestrator import SLOOrchestrator


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


if __name__ == "__main__":
    success = test_integration()
    exit(0 if success else 1)

