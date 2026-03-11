from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


# ── Request ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000,
                       description="Natural language SLO query")
    app_id: int = Field(default=31854, description="Application ID")
    project_id: int = Field(default=215853, description="Project ID")


# ── Sub-models mirroring orchestrator output ───────────────────────────────────

class ClassificationResult(BaseModel):
    primary_intent: Optional[str]
    secondary_intents: List[str]
    enriched_intents: List[str]
    entities: Dict[str, Any]


class TimeResolution(BaseModel):
    start_time: Optional[int]
    end_time: Optional[int]
    index: Optional[str]
    time_range: Optional[str]


class QueryMetadata(BaseModel):
    app_id: int
    project_id: int
    service: Optional[str]
    enrichment_applied: bool


class ResponseMetadata(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


# ── Response models ────────────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    success: bool
    query: str
    classification: ClassificationResult
    time_resolution: TimeResolution
    data_sources_used: List[str]
    data: Dict[str, Any]
    metadata: QueryMetadata
    conversational_response: str
    response_metadata: ResponseMetadata


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    query: Optional[str] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    orchestrator_ready: bool
    app_id: int
    services_loaded: int
    model_id: str
