"""
PAT Intent Detection Engine

Hybrid intent detection pipeline: Rasa Pro + Mistral + DeepSeek.
Creates monetizable data segments for the PAT marketplace.
"""

from .agent import BrowserAgent, IntentType, IntentSignal, DataSegment
from .schema import EventType, BrowserEvent, IntentInference, Context, Privacy
from .llm_clients import MistralClient, DeepSeekClient, GatingPolicy
from .marketplace_client import MarketplaceClient, LocalStorageClient

__version__ = "1.0.0"

__all__ = [
    # Agent
    "BrowserAgent",
    "IntentType",
    "IntentSignal",
    "DataSegment",
    # Schema
    "EventType",
    "BrowserEvent",
    "IntentInference",
    "Context",
    "Privacy",
    # LLM Clients
    "MistralClient",
    "DeepSeekClient",
    "GatingPolicy",
    # Marketplace
    "MarketplaceClient",
    "LocalStorageClient",
]
