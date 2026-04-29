#!/usr/bin/env python3
"""
SLO Orchestrator
Coordinates intent classification and data fetching from multiple adapters
"""

import os
import sys
import json
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api_models import QueryRequest, QueryResponse, ErrorResponse, HealthResponse
import config

# Add project directories to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'intent_classifier'))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'context_adapter'))

from intent_classifier.intent_classifier import IntentClassifier
from context_adapter.java_stats import fetch_api_data, transform_to_llm_format
from context_adapter.memory_adapter import fetch_behavior_service_memory, transform_behavior_memory, fetch_patterns_by_intent
from context_adapter.alert_count import fetch_alerts_for_orchestrator
from context_adapter.change_pre_post import fetch_change_impact_for_orchestrator
from context_adapter.infra_adapter import fetch_infra_for_orchestrator
from context_adapter.golden_path_adapter import fetch_golden_path_for_orchestrator
from context_adapter.journey_health_adapter import fetch_journey_health_for_orchestrator
from utils.service_matcher import ServiceMatcher
from utils.token_tracker import TokenTracker
from llm_response_generator import LLMResponseGenerator


class SLOOrchestrator:
    """
    Main orchestrator that coordinates:
    1. Intent classification via LLM
    2. Data fetching from appropriate adapters
    3. Response aggregation
    """

    def __init__(self):
        """Initialize orchestrator with intent classifier and configuration"""
        load_dotenv()

        # Initialize intent classifier
        print("Initializing Intent Classifier...")
        self.classifier = IntentClassifier()
        print("✅ Intent Classifier ready")

        # Initialize service matcher
        print("Initializing Service Matcher...")
        try:
            self.service_matcher = ServiceMatcher("services.yaml")
            print(f"✅ Service Matcher ready ({len(self.service_matcher.services_by_id)} services loaded)")
        except FileNotFoundError:
            print("⚠️  services.yaml not found - service matching disabled")
            self.service_matcher = None

        # Initialize LLM response generator
        print("Initializing LLM Response Generator...")
        self.response_generator = LLMResponseGenerator()
        print("✅ LLM Response Generator ready\n")

        # Configuration from .env via config module
        self.app_id = config.APP_ID
        self.project_id = config.PROJECT_ID
        self.java_stats_username = config.USERNAME
        self.java_stats_password = config.PASSWORD

    def process_query(self, user_query: str, app_id: int = None, project_id: int = None,
                      start_time: int = None, end_time: int = None) -> Dict[str, Any]:
        """
        Process a user query end-to-end

        Args:
            user_query: Natural language query from user

        Returns:
            Dictionary containing:
            - classification: Intent classification results
            - data: Aggregated data from all adapters
            - metadata: Processing metadata
        """
        effective_app_id = app_id if app_id is not None else self.app_id
        effective_project_id = project_id if project_id is not None else self.project_id

        tracker = TokenTracker(effective_app_id, effective_project_id, config.USERNAME)

        print("="*80)
        print("SLO ORCHESTRATOR - Processing Query")
        print("="*80)
        print(f"\n📝 Query: {user_query}\n")

        # Step 1: Classify intent
        print("🔍 Step 1: Analyzing intent...")
        _t0 = datetime.now()
        classification_result = self.classifier.classify(user_query)
        _t1 = datetime.now()
        _usage = self.classifier.last_usage
        tracker.log_task(
            task_name="SLO.intent_classification",
            model_name=self.classifier.model_id,
            started_at=_t0,
            completed_at=_t1,
            input_tokens=_usage.get('input_tokens', 0),
            output_tokens=_usage.get('output_tokens', 0),
            task_status="failed" if "error" in classification_result else "completed",
            response_status=self.classifier.last_http_status,
            had_error="error" in classification_result,
            error_type=classification_result.get("error") if "error" in classification_result else None,
            token_usage_missing=not bool(_usage),
        )

        if "error" in classification_result:
            return {
                "success": False,
                "error": classification_result.get("error"),
                "query": user_query
            }

        # Print classification result
        self.classifier.print_result(classification_result)

        # Step 2: Extract parameters
        entities = classification_result.get('entities', {})
        service = entities.get('service')
        data_sources = classification_result.get('data_sources', [])
        timestamp_resolution = classification_result.get('timestamp_resolution', {})

        # Collect all intents (primary + secondary + enriched) for pattern routing
        all_intents = set()
        all_intents.add(classification_result.get('primary_intent'))
        all_intents.update(classification_result.get('secondary_intents', []))
        all_intents.update(classification_result.get('enriched_intents', []))
        all_intents.discard(None)  # Remove None if present

        if not timestamp_resolution:
            return {
                "success": False,
                "error": "Failed to resolve time range",
                "query": user_query
            }

        primary_range = timestamp_resolution.get('primary_range', {})
        ts_source = timestamp_resolution.get('source', 'fallback')

        # Priority: query-derived timestamps always win when the query mentions time.
        # API-provided start_time/end_time are only used when the query had no time reference (source == 'fallback').
        if ts_source != 'fallback':
            # Query contained a time expression — ignore API-provided values
            start_time = primary_range.get('start_time')
            end_time   = primary_range.get('end_time')
        else:
            # No time in query — use API-provided values if given, else keep the 1-hour fallback
            if not start_time:
                start_time = primary_range.get('start_time')
            if not end_time:
                end_time = primary_range.get('end_time')

        # Enforce minimum 1-hour gap
        # If gap is too small, shift start backwards (not end forwards) so we
        # always query a completed historical window rather than a future one.
        ONE_HOUR_MS = 60 * 60 * 1000
        if start_time is not None and end_time is not None:
            if (end_time - start_time) < ONE_HOUR_MS:
                start_time = end_time - ONE_HOUR_MS

        if start_time is not None and end_time is not None:
            # Always auto-calculate index from the final start/end
            duration_days = (end_time - start_time) / (1000 * 60 * 60 * 24)
            index = 'DAILY' if duration_days > 3 else 'HOURLY'
        else:
            index = timestamp_resolution.get('index')

        print(f"\n📊 Step 2: Fetching data from adapters...")
        print(f"   Data Sources: {', '.join(data_sources)}")
        print(f"   Time Range: {start_time} to {end_time}")
        print(f"   Index: {index}\n")

        # Step 3: Fetch data from adapters
        adapter_data = {}

        # Resolve service_id if service mentioned
        service_id = None
        if service and self.service_matcher:
            print(f"   Resolving service name: '{service}'")
            matches = self.service_matcher.find_matches(service, threshold=0.3, max_results=1)
            if matches:
                service_id = matches[0]['service_id']
                matched_path = matches[0]['service_path']
                score = matches[0]['similarity_score']
                print(f"   ✓ Matched to service_id={service_id} ({matched_path}, score={score:.3f})\n")
            else:
                print(f"   ⚠️  No service match found for '{service}'\n")

        # Fetch from Java Stats API
        if 'java_stats_api' in data_sources:
            print("   → Fetching from Java Stats API...")
            java_data = self._fetch_java_stats(
                start_time_ms=str(start_time),
                end_time_ms=str(end_time),
                index=index,
                app_id=effective_app_id,
                project_id=effective_project_id,
            )
            if java_data:
                adapter_data['java_stats_api'] = java_data
                print("   ✅ Java Stats API data retrieved\n")
            else:
                print("   ⚠️  Java Stats API returned no data\n")

        # Fetch from ClickHouse (memory adapter)
        if 'clickhouse' in data_sources:
            print("   → Fetching from ClickHouse (behavior memory)...")
            memory_data = self._fetch_memory_adapter(
                start_time=start_time,
                end_time=end_time,
                app_id=effective_app_id,
                service_name=service,
                intents=all_intents,
                incident_timestamp=None  # Could extract from entities if needed
            )
            if memory_data:
                adapter_data['clickhouse'] = memory_data
                print("   ✅ ClickHouse data retrieved\n")
            else:
                print("   ⚠️  ClickHouse returned no data\n")

        # Fetch from ClickHouse infra_data (separate table, separate adapter)
        if 'clickhouse_infra' in data_sources:
            print("   → Fetching from ClickHouse (infra metrics)...")
            infra_data = self._fetch_infra_adapter(
                start_time=start_time,
                end_time=end_time,
                app_id=effective_app_id,
                project_id=effective_project_id
            )
            if infra_data:
                adapter_data['clickhouse_infra'] = infra_data
                print("   ✅ Infra metrics retrieved\n")
            else:
                print("   ⚠️  Infra adapter returned no data\n")

        # Fetch from Golden Path API (top-5 quadrant EB transactions)
        if 'golden_path_api' in data_sources:
            print("   → Fetching from Golden Path API (quadrant EB + RESPONSE transactions)...")
            golden_path_data = self._fetch_golden_path(
                app_id=effective_app_id,
                project_id=effective_project_id,
                start_time=start_time,
                end_time=end_time,
            )
            if golden_path_data:
                adapter_data['golden_path_api'] = golden_path_data
                eb_total = golden_path_data.get('summary_EB', {}).get('total_transactions', 0)
                resp_total = golden_path_data.get('summary_response', {}).get('total_transactions', 0)
                print(f"   ✅ Golden Path data retrieved (EB={eb_total}, RESPONSE={resp_total} transactions)\n")
            else:
                print("   ⚠️  Golden Path API returned no data\n")

        # Fetch from Journey Health API (user journey performance)
        if 'journey_health_api' in data_sources:
            print("   → Fetching from Journey Health API (user journey performance)...")
            journey_health_data = self._fetch_journey_health(
                app_id=effective_app_id,
                project_id=effective_project_id,
                start_time=start_time,
                end_time=end_time,
            )
            if journey_health_data:
                adapter_data['journey_health_api'] = journey_health_data
                total = len(journey_health_data.get('records', [{}])[0].get('summaries', []))
                print(f"   ✅ Journey Health data retrieved ({total} journey summaries)\n")
            else:
                print("   ⚠️  Journey Health API returned no data\n")

        # Fetch from Alerts Count API (if in data_sources)
        if 'alerts_count' in data_sources:
            print("   → Fetching from Alerts Count API...")
            alerts_data = self._fetch_alerts_count(
                start_time_ms=str(start_time),
                end_time_ms=str(end_time),
                app_id=effective_app_id,
                project_id=effective_project_id
            )
            if alerts_data:
                adapter_data['alerts_count'] = alerts_data
                alert_summary = alerts_data.get('alerts_count', {}).get('alert', {}) if isinstance(alerts_data.get('alerts_count'), dict) else {}
                total = alert_summary.get('totalCount')
                open_c = alert_summary.get('openCount')
                closed = alert_summary.get('closedCount')
                print(f"   ✅ Alerts Count data retrieved (total: {total}, open: {open_c}, closed: {closed})\n")
            else:
                print("   ⚠️  Alerts Count API returned no data\n")

        # Fetch from Change Impact API (if in data_sources)
        if 'change_impact' in data_sources:
            print("   → Fetching from Change Impact API (pre/post deviations)...")
            change_impact_data = self._fetch_change_impact(app_id=effective_app_id, project_id=effective_project_id)
            if change_impact_data:
                adapter_data['change_impact'] = change_impact_data
                print("   ✅ Change Impact data retrieved\n")
            else:
                print("   ⚠️  Change Impact API returned no data\n")

        # Note: postgres and opensearch adapters not yet implemented
        if 'postgres' in data_sources:
            print("   ⚠️  Postgres adapter not yet implemented")
            adapter_data['postgres'] = {"status": "not_implemented"}

        if 'opensearch' in data_sources:
            print("   ⚠️  OpenSearch adapter not yet implemented")
            adapter_data['opensearch'] = {"status": "not_implemented"}

        # Step 4: Build final response
        result = {
            "success": True,
            "query": user_query,
            "classification": {
                "primary_intent": classification_result.get('primary_intent'),
                "secondary_intents": classification_result.get('secondary_intents', []),
                "enriched_intents": classification_result.get('enriched_intents', []),
                "entities": entities
            },
            "time_resolution": {
                "start_time": start_time,
                "end_time": end_time,
                "index": index,
                "time_range": primary_range.get('time_range')
            },
            "data_sources_used": list(adapter_data.keys()),
            "data": adapter_data,
            "metadata": {
                "app_id": effective_app_id,
                "project_id": effective_project_id,
                "service": service,
                "enrichment_applied": bool(classification_result.get('enrichment_details'))
            }
        }

        print("="*80)
        print("✅ ORCHESTRATION COMPLETE")
        print("="*80)
        print(f"\nData sources fetched: {', '.join(adapter_data.keys())}")
        print(f"Total data keys: {len(adapter_data)}\n")

        # Step 4: Generate conversational response using LLM
        _t2 = datetime.now()
        conversational_result = self.response_generator.generate_response(
            user_query=user_query,
            orchestrator_output=result
        )
        _t3 = datetime.now()
        _resp_usage = self.response_generator.last_usage
        _resp_had_error = not conversational_result.get("success", True)
        tracker.log_task(
            task_name="SLO.response_generation",
            model_name=self.response_generator.model_id,
            started_at=_t2,
            completed_at=_t3,
            input_tokens=_resp_usage.get('input_tokens', 0),
            output_tokens=_resp_usage.get('output_tokens', 0),
            task_status="failed" if _resp_had_error else "completed",
            response_status=self.response_generator.last_http_status,
            had_error=_resp_had_error,
            error_type=conversational_result.get("error") if _resp_had_error else None,
            token_usage_missing=not bool(_resp_usage),
        )

        # Add conversational response to result
        result["conversational_response"] = conversational_result.get("response", "")
        result["response_metadata"] = conversational_result.get("metadata", {})

        return result

    def _fetch_java_stats(
        self,
        start_time_ms: str,
        end_time_ms: str,
        index: str,
        app_id: int,
        project_id: int,
    ) -> Optional[Dict[str, Any]]:
        try:
            raw_data = fetch_api_data(
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                username=self.java_stats_username,
                password=self.java_stats_password,
                application_id=app_id,
                index=index,
                project_id=project_id
            )
            if not raw_data:
                return None
            return transform_to_llm_format(raw_data, start_time_ms, end_time_ms)
        except Exception as e:
            print(f"   ✗ Error fetching Java Stats: {e}")
            return None

    def _fetch_memory_adapter(
        self,
        start_time: int,
        end_time: int,
        app_id: int,
        service_name: Optional[str] = None,
        intents: Optional[set] = None,
        incident_timestamp: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch data from ClickHouse memory adapter with intent-based routing

        Args:
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            service_name: Optional service name filter (from intent classifier)
            intents: Set of all intents (primary + secondary + enriched)
            incident_timestamp: Optional incident timestamp for RECURRING_INCIDENT

        Returns:
            Intent-based pattern data or None if failed
        """
        try:
            # Step 1: Resolve service name to service_id
            service_id = None
            if service_name and self.service_matcher:
                print(f"   Resolving service name: '{service_name}'")
                matches = self.service_matcher.find_matches(service_name, threshold=0.3, max_results=1)
                if matches:
                    service_id = matches[0]['service_id']
                    matched_path = matches[0]['service_path']
                    score = matches[0]['similarity_score']
                    print(f"   ✓ Matched to service_id={service_id} ({matched_path}, score={score:.3f})")
                else:
                    print(f"   ⚠️  No service match found for '{service_name}'")

            # Step 2: Use intent-based routing if intents provided
            if intents:
                result = fetch_patterns_by_intent(
                    intents=intents,
                    start_time=start_time,
                    end_time=end_time,
                    app_id=app_id,
                    service_id=service_id,
                    service_name=service_name,
                    incident_timestamp=incident_timestamp
                )
                return result
            else:
                # Fallback to general fetch (backward compatibility)
                raw_data = fetch_behavior_service_memory(
                    start_time=start_time,
                    end_time=end_time,
                    app_id=app_id,
                    sid=service_name
                )

                if not raw_data:
                    return None

                transformed = transform_behavior_memory(
                    rows=raw_data,
                    start_time=start_time,
                    end_time=end_time,
                    app_id=app_id,
                    sid=service_name
                )
                return transformed

        except Exception as e:
            print(f"   ✗ Error fetching ClickHouse data: {e}")
            return None

    def _fetch_infra_adapter(
        self,
        start_time: int,
        end_time: int,
        app_id: int,
        project_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch infrastructure metrics from ClickHouse infra_data table.

        Args:
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            app_id: Application ID
            project_id: Project ID

        Returns:
            Infra metrics envelope or None if failed
        """
        try:
            return fetch_infra_for_orchestrator(
                app_id=app_id,
                project_id=project_id,
                start_time=start_time,
                end_time=end_time
            )
        except Exception as e:
            print(f"   ✗ Error fetching infra metrics: {e}")
            return None

    def _fetch_golden_path(
        self,
        app_id: int,
        project_id: int,
        start_time: int,
        end_time: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch top-5 quadrant EB transactions from the Golden Path API."""
        try:
            return fetch_golden_path_for_orchestrator(
                app_id=app_id,
                project_id=project_id,
                start_time=start_time,
                end_time=end_time,
                username=self.java_stats_username,
                password=self.java_stats_password,
            )
        except Exception as e:
            print(f"   ✗ Error fetching Golden Path data: {e}")
            return None

    def _fetch_journey_health(
        self,
        app_id: int,
        project_id: int,
        start_time: int,
        end_time: int,
        range_type: str = "CUSTOM",
    ) -> Optional[Dict[str, Any]]:
        """Fetch user journey performance records from the Journey Health API."""
        try:
            return fetch_journey_health_for_orchestrator(
                app_id=app_id,
                project_id=project_id,
                start_time=start_time,
                end_time=end_time,
                range_type=range_type,
                username=self.java_stats_username,
                password=self.java_stats_password,
            )
        except Exception as e:
            print(f"   ✗ Error fetching Journey Health data: {e}")
            return None

    def _fetch_alerts_count(
        self,
        start_time_ms: str,
        end_time_ms: str,
        app_id: int,
        project_id: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch alerts count data from alerts-action API

        Args:
            start_time_ms: Start time in milliseconds (string)
            end_time_ms: End time in milliseconds (string)

        Returns:
            Alerts count data or None if failed
        """
        try:
            return fetch_alerts_for_orchestrator(
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                app_id=app_id,
                project_id=project_id if project_id is not None else self.project_id,
                username=self.java_stats_username,
                password=self.java_stats_password
            )
        except Exception as e:
            print(f"   ✗ Error fetching alerts count: {e}")
            return None

    def _fetch_change_impact(self, app_id: int, project_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Fetch latest change and its impact (pre/post deviations)

        Returns:
            Change impact data or None if failed
        """
        try:
            return fetch_change_impact_for_orchestrator(
                application_id=app_id,
                project_id=project_id if project_id is not None else self.project_id,
                username=self.java_stats_username,
                password=self.java_stats_password
            )
        except Exception as e:
            print(f"   ✗ Error fetching change impact: {e}")
            return None

    def export_to_json(self, result: Dict[str, Any], filepath: str):
        """
        Export orchestrator result to JSON file

        Args:
            result: Orchestrator result dictionary
            filepath: Path to output JSON file
        """
        try:
            with open(filepath, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"✅ Result exported to {filepath}")
        except Exception as e:
            print(f"✗ Failed to export to JSON: {e}")


def main():
    """Main function for interactive testing"""
    print("\n" + "="*80)
    print("CONVERSATIONAL SLO MANAGER - ORCHESTRATOR")
    print("="*80)
    print("\nInitializing orchestrator...")

    try:
        orchestrator = SLOOrchestrator()
        print("✅ Orchestrator initialized successfully!\n")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return

    print("Enter your queries (type 'quit' or 'exit' to stop):")
    print("Commands:")
    print("  - 'export' - export last result to JSON")
    print("  - 'help' - show this help message\n")

    last_result = None

    while True:
        try:
            user_input = input("\nQuery: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye! 👋")
                break

            if user_input.lower() == 'help':
                print("\nCommands:")
                print("  - Enter any natural language query about your services")
                print("  - 'export' - export last result to JSON file")
                print("  - 'quit' or 'exit' - exit the program")
                continue

            if user_input.lower() == 'export':
                if last_result:
                    filename = f"slo_result_{int(last_result['time_resolution']['start_time'])}.json"
                    orchestrator.export_to_json(last_result, filename)
                else:
                    print("⚠️  No result to export. Run a query first.")
                continue

            # Process the query
            result = orchestrator.process_query(user_input)
            last_result = result

            # Print conversational response prominently
            if result.get('success'):
                # Display the conversational response
                print("\n" + "="*80)
                print("💬 CONVERSATIONAL RESPONSE")
                print("="*80)
                print()
                print(result.get('conversational_response', 'No response generated'))
                print()

                # Print technical summary for reference
                print("="*80)
                print("📋 Technical Summary")
                print("="*80)
                print(f"   Primary Intent: {result['classification']['primary_intent']}")
                print(f"   Data Sources Used: {', '.join(result['data_sources_used'])}")

                # Print data stats
                for source, data in result['data'].items():
                    if isinstance(data, dict) and 'stats' in data:
                        stats = data['stats']
                        print(f"\n   {source.upper()} Stats:")
                        for key, value in stats.items():
                            print(f"      • {key}: {value}")

                # Auto-export result to JSON
                print()
                timestamp = int(result['time_resolution']['start_time'])
                filename = f"slo_result_{timestamp}.json"
                orchestrator.export_to_json(result, filename)
            else:
                print(f"\n❌ Error: {result.get('error')}")

        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋")
            break
        except Exception as e:
            print(f"\n❌ Error processing query: {e}")
            import traceback
            traceback.print_exc()


# ── FastAPI Application ────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slo_api")

_orchestrator: Optional[SLOOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    logger.info("Initializing SLOOrchestrator...")
    try:
        _orchestrator = SLOOrchestrator()
        logger.info("SLOOrchestrator ready")
    except Exception as exc:
        logger.error(f"Failed to initialize orchestrator: {exc}")
        _orchestrator = None
    yield
    logger.info("Shutting down SLO API")


app = FastAPI(
    title="SLO Advisor API",
    description="Internal API for conversational SLO queries powered by AWS Bedrock",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=traceback.format_exc()[-500:],
        ).model_dump(),
    )


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health_check():
    """Liveness and readiness probe. Returns 503 if orchestrator failed to initialize."""
    if _orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized — check startup logs",
        )
    services_count = (
        len(_orchestrator.service_matcher.services_by_id)
        if _orchestrator.service_matcher
        else 0
    )
    return HealthResponse(
        status="ok",
        orchestrator_ready=True,
        app_id=_orchestrator.app_id,
        services_loaded=services_count,
        model_id=_orchestrator.response_generator.model_id,
    )


@app.post(
    "/query",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    tags=["slo"],
)
def run_query(body: QueryRequest):
    """
    Submit a natural language SLO query.

    Returns intent classification, all adapter data, and a conversational response.
    Typical latency: 8–15 seconds (two LLM calls + parallel data fetches).
    """
    if _orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    logger.info(f"Query: {body.query!r}, app_id={body.app_id}, project_id={body.project_id}, "
                f"start_time={body.start_time}, end_time={body.end_time}")
    result = _orchestrator.process_query(
        user_query=body.query,
        app_id=body.app_id,
        project_id=body.project_id,
        start_time=body.start_time,
        end_time=body.end_time,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Orchestrator returned failure"),
        )
    return result


if __name__ == "__main__":
    main()
