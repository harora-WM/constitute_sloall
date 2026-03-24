#!/usr/bin/env python3
"""
Intent Classifier for Conversational SLO Manager
Uses AWS Bedrock Claude Sonnet 4.5 to classify user queries into intents and determine data sources
"""

import os
import json
import yaml
from typing import Dict, List, Set, Any
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
from timestamp import TimestampResolver


class IntentClassifier:
    """Main intent classifier class"""

    def __init__(self):
        """Initialize the intent classifier"""
        # Load environment variables
        load_dotenv()

        # Load YAML configurations
        self.intent_categories = self._load_yaml('intent_categories.yaml')
        self.enrichment_rules = self._load_yaml('enrichment_rules.yaml')
        self.data_sources_config = self._load_yaml('data_sources.yaml')

        # Build intent to data sources mapping
        self.intent_to_data_sources = self._build_intent_data_source_map()

        # Initialize timestamp resolver
        self.timestamp_resolver = TimestampResolver()

        # Initialize AWS Bedrock client
        self.bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )

        # Model configuration
        self.model_id = os.getenv('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')
        self.max_tokens = int(os.getenv('MAX_TOKENS', '500'))
        self.temperature = float(os.getenv('TEMPERATURE', '0.0'))

        # Build system prompt
        self.system_prompt = self._build_system_prompt()

    def _load_yaml(self, filename: str) -> Dict:
        """Load YAML file"""
        try:
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # Build the full path to the YAML file
            file_path = os.path.join(script_dir, filename)

            with open(file_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: {filename} not found")
            return {}
        except yaml.YAMLError as e:
            print(f"Error parsing {filename}: {e}")
            return {}

    def _build_intent_data_source_map(self) -> Dict[str, List[str]]:
        """Build mapping from intent to data sources"""
        intent_map = {}

        for category, category_data in self.intent_categories.items():
            if 'intents' in category_data:
                for intent_name, intent_data in category_data['intents'].items():
                    if 'data_sources' in intent_data:
                        intent_map[intent_name] = intent_data['data_sources']

        return intent_map

    def _build_system_prompt(self) -> str:
        """Build the system prompt for intent classification"""
        prompt = """You are an intent classification engine for an AI-driven SRE reliability platform.

Your ONLY job is to:
1. Identify the PRIMARY intent of the user question.
2. Identify any SECONDARY intents if clearly implied.
3. Extract ENTITIES such as:
   - service name (if mentioned)

You MUST follow these rules strictly:

RULES:
- Return ONLY valid JSON. No explanation text.
- Do NOT guess application, tenant, or IDs.
- If service is unclear, set service = null.
- Use ONLY intents from the allowed list.
- Be conservative. If unsure, choose the closest high-level intent.

ALLOWED PRIMARY INTENTS:

"""

        # Add all categories and their intents
        for category, category_data in self.intent_categories.items():
            if 'intents' in category_data:
                prompt += f"{category}:\n"
                for intent_name, intent_data in category_data['intents'].items():
                    prompt += f"- {intent_name}: {intent_data.get('description', '')}\n"
                prompt += "\n"

        prompt += """OUTPUT JSON SCHEMA:

{
  "primary_intent": "<ONE_ALLOWED_INTENT>",
  "secondary_intents": [],
  "entities": {
    "service": null
  }
}

IMPORTANT:
- primary_intent: Must be a single intent from the allowed list
- secondary_intents: Array of related intents that should be auto-included (from enrichment rules)
- entities.service: Service name if mentioned, otherwise null

NOTE: Do NOT include data_sources in your response. Data sources will be determined automatically based on the intents.

Return ONLY the JSON object. No additional text.
"""

        return prompt

    def _call_bedrock(self, user_query: str) -> Dict[str, Any]:
        """Call AWS Bedrock to classify intent and extract entities"""
        try:
            # Prepare the request body for Claude Sonnet 4.5
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "system": self.system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": user_query
                    }
                ]
            }

            # Invoke the model
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            # Parse the response
            response_body = json.loads(response['body'].read())
            assistant_message = response_body['content'][0]['text']

            # Extract JSON object from response
            # Handle cases where LLM might add extra text
            assistant_message = assistant_message.strip()

            # Find JSON object in the response
            start_idx = assistant_message.find('{')
            end_idx = assistant_message.rfind('}') + 1

            if start_idx != -1 and end_idx > start_idx:
                json_str = assistant_message[start_idx:end_idx]
                result = json.loads(json_str)
                return result
            else:
                # Fallback: try to parse the entire response
                return json.loads(assistant_message)

        except ClientError as e:
            print(f"AWS Bedrock Error: {e}")
            return {}
        except json.JSONDecodeError as e:
            print(f"JSON Parsing Error: {e}")
            print(f"LLM Response: {assistant_message}")
            return {}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {}

    def _get_enrichment_intents(self, primary_intents: List[str]) -> Set[str]:
        """Get all enrichment intents for the primary intents"""
        enriched_intents = set(primary_intents)

        # Process each primary intent
        for intent in primary_intents:
            if intent in self.enrichment_rules:
                # Add all enrichment intents
                for enrichment in self.enrichment_rules[intent]:
                    enriched_intents.add(enrichment)

        return enriched_intents

    def _get_data_sources(self, intents: Set[str]) -> List[str]:
        """Get all required data sources for the intents"""
        data_sources = set()

        for intent in intents:
            if intent in self.intent_to_data_sources:
                data_sources.update(self.intent_to_data_sources[intent])

        return sorted(list(data_sources))

    def classify(self, user_query: str) -> Dict[str, Any]:
        """
        Classify user query and return intent, secondary intents, entities, and data sources

        Args:
            user_query: The user's question

        Returns:
            Dictionary containing:
            - primary_intent: The main detected intent
            - secondary_intents: Related intents from enrichment rules
            - entities: Extracted entities (service)
            - data_sources: Required data sources
            - enrichment_details: Details of which enrichments came from the primary intent
            - timestamp_resolution: Resolved UTC timestamps and index granularity
        """
        # Get classification from LLM
        llm_result = self._call_bedrock(user_query)

        if not llm_result or 'primary_intent' not in llm_result:
            return {
                "error": "Failed to classify intent",
                "query": user_query,
                "primary_intent": None,
                "secondary_intents": [],
                "entities": {
                    "service": None
                },
                "data_sources": [],
                "enrichment_details": {},
                "timestamp_resolution": None
            }

        primary_intent = llm_result.get('primary_intent')
        secondary_intents = llm_result.get('secondary_intents', [])
        entities = llm_result.get('entities', {"service": None})

        # Resolve timestamps directly from the raw user query
        timestamp_resolution = self.timestamp_resolver.resolve_time_range(user_query)

        # Combine primary and secondary intents for enrichment
        all_intents = [primary_intent] + secondary_intents if primary_intent else secondary_intents

        # Get enriched intents from enrichment rules
        enriched_intents = self._get_enrichment_intents(all_intents)

        # Build enrichment details
        enrichment_details = {}
        if primary_intent and primary_intent in self.enrichment_rules:
            enrichment_details[primary_intent] = self.enrichment_rules[primary_intent]

        # Get required data sources from intent definitions (NOT from LLM)
        # This ensures proper mapping based on intent_categories.yaml
        all_data_sources = self._get_data_sources(enriched_intents)

        return {
            "query": user_query,
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "entities": entities,
            "enriched_intents": sorted(list(enriched_intents)),
            "data_sources": all_data_sources,
            "enrichment_details": enrichment_details,
            "timestamp_resolution": timestamp_resolution
        }

    def print_result(self, result: Dict[str, Any]):
        """Pretty print the classification result"""
        if "error" in result:
            print(f"\n❌ Error: {result['error']}\n")
            return

        print("\n" + "="*80)
        print("INTENT CLASSIFICATION RESULT")
        print("="*80)

        print(f"\n📝 Query: {result['query']}")

        print(f"\n🎯 Primary Intent: {result['primary_intent']}")

        if result['secondary_intents']:
            print(f"\n🔗 Secondary Intents: {', '.join(result['secondary_intents'])}")

        print(f"\n📍 Entities Extracted:")
        entities = result.get('entities', {})
        print(f"   • Service: {entities.get('service', 'N/A')}")

        # Print timestamp resolution
        self._print_timestamp_resolution(result.get('timestamp_resolution'))

        if result['enrichment_details']:
            print(f"\n🔄 Enrichment Applied:")
            for primary, enrichments in result['enrichment_details'].items():
                print(f"   {primary} → {', '.join(enrichments)}")

        print(f"\n📊 All Intents (including enrichments):")
        primary = result.get('primary_intent')
        secondary = result.get('secondary_intents', [])
        for intent in result['enriched_intents']:
            if intent == primary:
                marker = "🎯"
            elif intent in secondary:
                marker = "🔗"
            else:
                marker = "  "
            print(f"   {marker} {intent}")

        print(f"\n💾 Data Sources Required:")
        for ds in result['data_sources']:
            # Get description from config
            ds_info = self.data_sources_config.get('data_sources', {}).get(ds, {})
            description = ds_info.get('description', 'No description')
            print(f"   • {ds}: {description}")

        print("\n" + "="*80 + "\n")

    def _print_timestamp_resolution(self, timestamp_resolution: Dict[str, Any]):
        """Print timestamp resolution details"""
        if not timestamp_resolution:
            return

        print(f"\n⏱️  Step 3: Time Range Resolution")
        print(f"   Query: \"{timestamp_resolution['primary_range']['time_range']}\"")
        print(f"\n   Python converts:")
        print(f"      start_time = {timestamp_resolution['primary_range']['start_time']}")
        print(f"      end_time   = {timestamp_resolution['primary_range']['end_time']}")
        print(f"      index      = {timestamp_resolution['index']}")

        print(f"\n   Reason: {timestamp_resolution['index_reason']}")


def main():
    """Main function for interactive testing"""
    print("="*80)
    print("CONVERSATIONAL SLO MANAGER - INTENT CLASSIFIER")
    print("="*80)
    print("\nInitializing classifier...")

    try:
        classifier = IntentClassifier()
        print("✅ Classifier initialized successfully!\n")
    except Exception as e:
        print(f"❌ Failed to initialize classifier: {e}")
        return

    print("Enter your queries (type 'quit' or 'exit' to stop):\n")

    while True:
        try:
            user_input = input("Query: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!\n")
                break

            # Classify the query
            result = classifier.classify(user_input)
            classifier.print_result(result)

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!\n")
            break
        except Exception as e:
            print(f"\n❌ Error processing query: {e}\n")


if __name__ == "__main__":
    main()