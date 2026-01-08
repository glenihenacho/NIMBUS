"""
Core data models for the intent detection engine.

These models define the structure of events, decisions, and inference runs
across the entire pipeline.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from uuid import UUID, uuid4


class IntentType(str, Enum):
    """Intent classification types"""
    PURCHASE_INTENT = "PURCHASE_INTENT"
    RESEARCH_INTENT = "RESEARCH_INTENT"
    COMPARISON_INTENT = "COMPARISON_INTENT"
    ENGAGEMENT_INTENT = "ENGAGEMENT_INTENT"
    NAVIGATION_INTENT = "NAVIGATION_INTENT"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    """Risk levels for gating policy"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ModelType(str, Enum):
    """Model types in the pipeline"""
    RASA = "rasa"
    MISTRAL_SMALL = "mistral-small"
    DEEPSEEK_REASONING = "deepseek-reasoning"


# Event models (ingestion)

class BrowsingEvent(BaseModel):
    """Raw browsing event from RudderStack"""
    event_id: UUID = Field(default_factory=uuid4)
    session_id: str
    user_id_hash: str
    event_type: str  # page_view, click, scroll, search, etc.
    url: Optional[str] = None
    url_hash: Optional[str] = None
    timestamp: datetime
    properties: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# Classifier output models

class AlternativeIntent(BaseModel):
    """Alternative intent prediction"""
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)


class ClassifierOutput(BaseModel):
    """Output from cheap classifiers (Rasa/Mistral)"""
    model_id: ModelType
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: List[AlternativeIntent] = Field(default_factory=list)
    latency_ms: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator('confidence')
    def confidence_valid(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Confidence must be between 0 and 1')
        return v

    @property
    def top2_margin(self) -> float:
        """Calculate margin between top 2 predictions"""
        if not self.alternatives:
            return 1.0
        second_best = max(self.alternatives, key=lambda x: x.confidence)
        return self.confidence - second_best.confidence


# Escalation models

class SupportingSignal(BaseModel):
    """Evidence supporting the intent decision"""
    source_event_id: UUID
    signal_type: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    description: str


class EscalationOutput(BaseModel):
    """Output from DeepSeek reasoning model"""
    model_id: ModelType = ModelType.DEEPSEEK_REASONING
    final_intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_signals: List[SupportingSignal] = Field(default_factory=list)
    alternatives: List[AlternativeIntent] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    reasoning_trace: Optional[str] = None  # For debugging
    latency_ms: float

    class Config:
        json_encoders = {
            UUID: lambda v: str(v)
        }


# Decision models

class GatingDecision(BaseModel):
    """Gating policy decision"""
    should_escalate: bool
    reason: str
    cheap_confidence: float
    top2_margin: float
    risk_level: RiskLevel
    high_value_session: bool


class IntentDecision(BaseModel):
    """Final intent decision for product use"""
    decision_id: UUID = Field(default_factory=uuid4)
    session_id: str
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    was_escalated: bool
    gating_decision: GatingDecision
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # For analytics
    source_event_ids: List[UUID] = Field(default_factory=list)
    model_used: ModelType

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# Inference run models (for logging/monitoring)

class InferenceRun(BaseModel):
    """Record of each model inference run"""
    run_id: UUID = Field(default_factory=uuid4)
    decision_id: UUID
    model_id: ModelType
    input_event_count: int
    output: Dict[str, Any]  # Serialized classifier/escalation output
    latency_ms: float
    success: bool
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# Session models (operational)

class Session(BaseModel):
    """Session metadata for routing decisions"""
    session_id: str
    user_id_hash: str
    event_count: int = 0
    current_sequence: int = 0
    value_score: float = 0.0  # For high_value_session gating
    risk_level: RiskLevel = RiskLevel.LOW
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Router request/response models

class InferenceRequest(BaseModel):
    """Request to router service"""
    session_id: str
    events: List[BrowsingEvent]
    force_escalation: bool = False  # For testing

    @validator('events')
    def events_not_empty(cls, v):
        if not v:
            raise ValueError('Events list cannot be empty')
        return v


class InferenceResponse(BaseModel):
    """Response from router service"""
    decision: IntentDecision
    inference_runs: List[InferenceRun]
    total_latency_ms: float
    policy_version: str = "1.0.0"

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# High-risk intent configuration

HIGH_RISK_INTENTS = {
    IntentType.PURCHASE_INTENT,
    # Add more as needed
}


# Gating policy constants

class GatingConfig(BaseModel):
    """Configuration for gating policy"""
    default_threshold: float = 0.70
    high_risk_threshold: float = 0.85
    high_value_threshold: float = 0.80
    top2_margin_threshold: float = 0.10

    # High value session criteria
    high_value_min_events: int = 10
    high_value_min_score: float = 0.6
