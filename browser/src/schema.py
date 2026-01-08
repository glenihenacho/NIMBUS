"""
Canonical Browser Event Schema (v1)

Immutable contract between browser and data infrastructure.
Separates raw events from inferred intent for model swapping and reprocessing.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(Enum):
    """10 canonical event primitives"""
    PAGE_VIEW = "page_view"
    SCROLL = "scroll"
    CLICK = "click"
    HOVER = "hover"
    TEXT_INPUT = "text_input"
    SEARCH = "search"
    FORM_SUBMIT = "form_submit"
    MEDIA_INTERACTION = "media_interaction"
    ERROR = "error"
    CUSTOM_ACTION = "custom_action"


class RetentionTier(Enum):
    """Data retention tiers per GDPR/CCPA"""
    SHORT = "30d"
    MEDIUM = "90d"
    LONG = "365d"


@dataclass
class Session:
    """Tracks sequence within 30-minute windows"""
    session_id: str
    sequence: int  # Enables journey reconstruction without timestamps
    started_at: datetime


@dataclass
class Actor:
    """Pseudonymous identifiers only - no PII"""
    user_id_hash: str      # Client-side hashed
    anonymous_id: str      # Device-generated UUID
    device_id: str         # Hardware fingerprint hash
    account_id: Optional[str] = None


@dataclass
class Context:
    """Event context - URL, viewport, device, geo, temporal"""
    url_domain: str
    url_path: str          # Excludes query params
    viewport_width: int
    viewport_height: int
    device_type: str       # desktop, mobile, tablet
    country: str           # ISO 3166-1 alpha-2
    region: Optional[str] = None
    hour_of_day: int = 0
    day_of_week: int = 0   # 0=Monday
    is_business_hours: bool = False


@dataclass
class Privacy:
    """Consent gates and retention settings"""
    consent_analytics: bool = False
    consent_personalization: bool = False
    consent_monetization: bool = False
    jurisdiction: str = "US-WY"  # Wyoming DAO LLC default
    retention_tier: RetentionTier = RetentionTier.MEDIUM
    data_sale_opt_in: bool = False


@dataclass
class BrowserEvent:
    """
    Top-level event envelope

    Every event contains: event_id, event_type, timestamps,
    session, actor, context, payload, privacy
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.PAGE_VIEW
    event_time: datetime = field(default_factory=datetime.utcnow)
    ingest_time: Optional[datetime] = None  # Set by server

    session: Optional[Session] = None
    actor: Optional[Actor] = None
    context: Optional[Context] = None
    payload: dict = field(default_factory=dict)  # Raw, uninterpreted data
    privacy: Privacy = field(default_factory=Privacy)

    def to_dict(self) -> dict:
        """Serialize for BigQuery/storage"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "event_time": self.event_time.isoformat(),
            "ingest_time": self.ingest_time.isoformat() if self.ingest_time else None,
            "session": {
                "session_id": self.session.session_id,
                "sequence": self.session.sequence,
                "started_at": self.session.started_at.isoformat()
            } if self.session else None,
            "actor": {
                "user_id_hash": self.actor.user_id_hash,
                "anonymous_id": self.actor.anonymous_id,
                "device_id": self.actor.device_id,
                "account_id": self.actor.account_id
            } if self.actor else None,
            "context": {
                "url_domain": self.context.url_domain,
                "url_path": self.context.url_path,
                "viewport_width": self.context.viewport_width,
                "viewport_height": self.context.viewport_height,
                "device_type": self.context.device_type,
                "country": self.context.country,
                "region": self.context.region,
                "hour_of_day": self.context.hour_of_day,
                "day_of_week": self.context.day_of_week,
                "is_business_hours": self.context.is_business_hours
            } if self.context else None,
            "payload": self.payload,
            "privacy": {
                "consent_analytics": self.privacy.consent_analytics,
                "consent_personalization": self.privacy.consent_personalization,
                "consent_monetization": self.privacy.consent_monetization,
                "jurisdiction": self.privacy.jurisdiction,
                "retention_tier": self.privacy.retention_tier.value,
                "data_sale_opt_in": self.privacy.data_sale_opt_in
            }
        }


@dataclass
class IntentInference:
    """
    Intent inference stored separately from raw events

    Enables model swapping without touching raw events:
    - Rasa -> Claude -> custom model migrations
    - Historical reprocessing
    """
    inference_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_event_ids: list[str] = field(default_factory=list)
    model_id: str = "qwen-turbo"
    model_version: str = "1.0"

    intent_type: str = ""
    confidence: float = 0.0
    alternatives: list[dict] = field(default_factory=list)  # [{type, confidence}]

    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Serialize for BigQuery intent_inferences table"""
        return {
            "inference_id": self.inference_id,
            "source_event_ids": self.source_event_ids,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "intent_type": self.intent_type,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "created_at": self.created_at.isoformat()
        }
