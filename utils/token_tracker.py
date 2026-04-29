"""
Token usage tracker — writes one row per LLM task to metrics.llm_token_usage in ClickHouse.
Errors are swallowed so a logging failure never breaks the main pipeline.
"""

import json
import uuid
import sys
import os
from datetime import datetime
from typing import Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_PROJECT_NAME = "Conversational_SLO"
_MODEL_PROVIDER = "bedrock"
_CH_TABLE = "llm_token_usage"


class TokenTracker:
    """
    One instance per pipeline run. Generates a single batch_id (UUID) shared
    across all tasks in that run and auto-increments run_id (1, 2, ...) per task logged.
    """

    def __init__(self, app_id: int, project_id: int, username: str):
        self.app_id = int(app_id)
        self.project_id = int(project_id)
        self.username = username
        self.batch_id = str(uuid.uuid4())
        self._run_counter = 0

    def log_task(
        self,
        task_name: str,
        model_name: str,
        started_at: datetime,
        completed_at: datetime,
        input_tokens: int = 0,
        output_tokens: int = 0,
        task_status: str = "completed",
        response_status: str = "200",
        had_error: bool = False,
        error_type: Optional[str] = None,
        token_usage_missing: bool = False,
    ) -> None:
        self._run_counter += 1
        duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))

        def _fmt(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"

        row = {
            "app_id": self.app_id,
            "project_id": self.project_id,
            "task_id": str(uuid.uuid4()),
            "run_id": str(self._run_counter),
            "batch_id": self.batch_id,
            "task_name": task_name,
            "project_name": _PROJECT_NAME,
            "username": self.username,
            "started_at": _fmt(started_at),
            "completed_at": _fmt(completed_at),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "task_status": task_status,
            "model_name": model_name,
            "model_provider": _MODEL_PROVIDER,
            "had_error": had_error,
            "error_type": error_type,
            "duration_ms": duration_ms,
            "response_status": response_status,
            "token_usage_missing": token_usage_missing,
        }
        self._insert(row)

    def _insert(self, row: dict) -> None:
        query = f"INSERT INTO {config.CLICKHOUSE_DATABASE}.{_CH_TABLE} FORMAT JSONEachRow"
        try:
            resp = requests.post(
                config.CLICKHOUSE_URL,
                params={"query": query},
                data=json.dumps(row),
                auth=(config.CLICKHOUSE_USERNAME, config.CLICKHOUSE_PASSWORD),
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:
            print(f"[TokenTracker] Failed to log '{row.get('task_name')}': {exc}")
