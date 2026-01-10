"""
PAT Intent Detection Engine

Hybrid intent detection pipeline: Rasa Open Source + Mistral + DeepSeek.
Creates monetizable data segments for the PAT marketplace.
"""

from .agent import BrowserAgent, IntentType, IntentSignal, DataSegment
from .schema import EventType, BrowserEvent, IntentInference, Context, Privacy
from .llm_clients import MistralClient, DeepSeekClient, GatingPolicy
from .marketplace_client import MarketplaceClient, LocalStorageClient

__version__ = "2.0.0"

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
    # LLM Clients (Mistral + DeepSeek)
    "MistralClient",
    "DeepSeekClient",
    "GatingPolicy",
    # Marketplace
    "MarketplaceClient",
    "LocalStorageClient",
]
