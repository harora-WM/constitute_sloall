"""
Unified LLM client — routes calls to AWS Bedrock or Ollama based on config.LLM_PROVIDER.

Exposes two methods used across all LLM call sites:
  complete(system, user, max_tokens, temperature) -> str
  stream(system, user, max_tokens, temperature)   -> Generator[str]
"""

import json
import logging
from typing import Generator

import config

logger = logging.getLogger(__name__)


class LLMClient:

    def __init__(self):
        self.provider = config.LLM_PROVIDER.lower()

        if self.provider == "bedrock":
            import boto3
            self._bedrock = boto3.client(
                service_name="bedrock-runtime",
                region_name=config.AWS_REGION,
                aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            )
            self.model_id = config.BEDROCK_MODEL_ID

        elif self.provider == "ollama":
            self._ollama_url = config.OLLAMA_BASE_URL.rstrip("/")
            self.model_id = config.OLLAMA_MODEL

        else:
            raise ValueError(
                f"Unknown LLM_PROVIDER: {self.provider!r}. Must be 'bedrock' or 'ollama'."
            )

    # ── Public interface ───────────────────────────────────────────────────────

    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        """Blocking completion. Returns the full response text."""
        if self.provider == "bedrock":
            return self._complete_bedrock(system, user, max_tokens, temperature)
        return self._complete_ollama(system, user, max_tokens, temperature)

    def stream(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> Generator[str, None, None]:
        """Streaming completion. Yields text chunks as they arrive."""
        if self.provider == "bedrock":
            yield from self._stream_bedrock(system, user, max_tokens, temperature)
        else:
            yield from self._stream_ollama(system, user, max_tokens, temperature)

    # ── Bedrock ────────────────────────────────────────────────────────────────

    def _bedrock_body(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> dict:
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

    def _complete_bedrock(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        from botocore.exceptions import ClientError
        try:
            response = self._bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(self._bedrock_body(system, user, max_tokens, temperature)),
            )
            body = json.loads(response["body"].read())
            return body["content"][0]["text"]
        except ClientError as e:
            logger.error("Bedrock error: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected Bedrock error: %s", e)
            raise

    def _stream_bedrock(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> Generator[str, None, None]:
        from botocore.exceptions import ClientError
        try:
            response = self._bedrock.invoke_model_with_response_stream(
                modelId=self.model_id,
                body=json.dumps(self._bedrock_body(system, user, max_tokens, temperature)),
            )
            for event in response["body"]:
                chunk = event.get("chunk")
                if chunk:
                    data = json.loads(chunk["bytes"].decode())
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
        except ClientError as e:
            logger.error("Bedrock streaming error: %s", e)
            raise

    # ── Ollama ─────────────────────────────────────────────────────────────────

    def _ollama_messages(self, system: str, user: str) -> list:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _ollama_num_predict(self, max_tokens: int) -> int:
        # Thinking models (e.g. qwen3) consume internal reasoning tokens against
        # num_predict before producing output. Add 2000 tokens of headroom so
        # the model always has budget left for the actual response.
        return max_tokens + 2000

    def _complete_ollama(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        import requests
        try:
            resp = requests.post(
                f"{self._ollama_url}/api/chat",
                json={
                    "model": self.model_id,
                    "messages": self._ollama_messages(system, user),
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": self._ollama_num_predict(max_tokens)},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.RequestException as e:
            logger.error("Ollama error: %s", e)
            raise

    def _stream_ollama(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> Generator[str, None, None]:
        import requests
        try:
            with requests.post(
                f"{self._ollama_url}/api/chat",
                json={
                    "model": self.model_id,
                    "messages": self._ollama_messages(system, user),
                    "stream": True,
                    "options": {"temperature": temperature, "num_predict": self._ollama_num_predict(max_tokens)},
                },
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done"):
                            break
        except requests.RequestException as e:
            logger.error("Ollama streaming error: %s", e)
            raise
