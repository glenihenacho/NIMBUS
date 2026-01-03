"""
PAT AI Browser Agent

A Qwen-powered browser agent for collecting web browsing intent signals
that are packaged as data segments for the PAT marketplace.
"""

from .agent import BrowserAgent, IntentType, IntentSignal, DataSegment
from .qwen_client import QwenAPIClient
from .marketplace_client import MarketplaceClient, LocalStorageClient

__version__ = "1.0.0"

__all__ = [
    "BrowserAgent",
    "IntentType",
    "IntentSignal",
    "DataSegment",
    "QwenAPIClient",
    "MarketplaceClient",
    "LocalStorageClient",
]
