"""
Rasa Pro Classifier Integration

Provides known-intent stability and deterministic behavior for common patterns.
"""

import asyncio
import httpx
from typing import List, Dict, Any
from datetime import datetime

from ..models.intent_models import (
    BrowsingEvent,
    ClassifierOutput,
    AlternativeIntent,
    IntentType,
    ModelType
)


class RasaClassifier:
    """
    Rasa Pro classifier for deterministic intent detection.

    Rasa excels at:
    - Known, well-defined intents
    - Stable, controllable predictions
    - Fast inference with low latency
    """

    def __init__(
        self,
        rasa_endpoint: str = "http://localhost:5005",
        model_name: str = "intent-classifier",
        timeout: float = 2.0
    ):
        self.rasa_endpoint = rasa_endpoint
        self.model_name = model_name
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def classify(self, events: List[BrowsingEvent]) -> ClassifierOutput:
        """
        Classify browsing events using Rasa.

        Args:
            events: List of browsing events to analyze

        Returns:
            ClassifierOutput with intent, confidence, and alternatives
        """
        start_time = datetime.utcnow()

        # Convert events to Rasa input format
        text = self._events_to_text(events)

        # Call Rasa API
        try:
            response = await self.client.post(
                f"{self.rasa_endpoint}/model/parse",
                json={
                    "text": text,
                    "message_id": events[0].session_id if events else "unknown"
                }
            )
            response.raise_for_status()
            result = response.json()

        except Exception as e:
            raise RuntimeError(f"Rasa API call failed: {e}")

        # Parse Rasa response
        intent_data = result.get("intent", {})
        intent_name = intent_data.get("name", "UNKNOWN")
        confidence = intent_data.get("confidence", 0.0)

        # Map Rasa intent to our IntentType
        intent = self._map_rasa_intent(intent_name)

        # Get alternative intents (top 3)
        intent_ranking = result.get("intent_ranking", [])
        alternatives = [
            AlternativeIntent(
                intent=self._map_rasa_intent(alt["name"]),
                confidence=alt["confidence"]
            )
            for alt in intent_ranking[1:4]  # Skip first (main intent)
        ]

        # Calculate latency
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return ClassifierOutput(
            model_id=ModelType.RASA,
            intent=intent,
            confidence=confidence,
            alternatives=alternatives,
            latency_ms=latency_ms,
            metadata={
                "rasa_intent_name": intent_name,
                "entities": result.get("entities", [])
            }
        )

    def _events_to_text(self, events: List[BrowsingEvent]) -> str:
        """
        Convert browsing events to text for Rasa.

        Strategy:
        - Concatenate event types and properties into a single text
        - Include temporal patterns (sequence, timing)
        - Keep it concise for fast processing
        """
        parts = []

        for i, event in enumerate(events[-10:]):  # Last 10 events only
            event_desc = f"{event.event_type}"

            # Add URL domain if available
            if event.url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(event.url).netloc
                    event_desc += f" on {domain}"
                except:
                    pass

            # Add key properties
            if event.properties:
                if "scroll_depth" in event.properties:
                    event_desc += f" scrolled {event.properties['scroll_depth']:.0f}%"
                if "time_on_page" in event.properties:
                    event_desc += f" for {event.properties['time_on_page']}s"

            parts.append(event_desc)

        return " | ".join(parts)

    def _map_rasa_intent(self, rasa_intent: str) -> IntentType:
        """
        Map Rasa intent names to our IntentType enum.

        Assumes Rasa is trained with intents like:
        - purchase_intent
        - research_intent
        - comparison_intent
        - etc.
        """
        intent_map = {
            "purchase_intent": IntentType.PURCHASE_INTENT,
            "research_intent": IntentType.RESEARCH_INTENT,
            "comparison_intent": IntentType.COMPARISON_INTENT,
            "engagement_intent": IntentType.ENGAGEMENT_INTENT,
            "navigation_intent": IntentType.NAVIGATION_INTENT,
        }

        return intent_map.get(rasa_intent.lower(), IntentType.UNKNOWN)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Rasa training data example (for reference)
RASA_TRAINING_EXAMPLE = """
# Rasa NLU Training Data (intent-classifier)

## intent:purchase_intent
- page_view on amazon.com | click on product | click on add to cart
- page_view on ebay.com | search | click on product | scrolled 80%
- page_view on shopify-store.com | click on buy now
- search | page_view on product page | page_view on checkout
- multiple product views | price comparison | add to cart

## intent:research_intent
- page_view on wikipedia.org | scrolled 95% for 180s
- page_view on medium.com | scrolled 100% for 240s
- search | page_view on article | bookmark
- page_view on documentation | scrolled 70% for 300s
- multiple article views | high scroll depth

## intent:comparison_intent
- search for "laptop vs desktop" | click on comparison
- page_view on review site | multiple product views
- search | page_view on product A | page_view on product B | page_view on product A
- click on compare | page_view on comparison table
- multiple tabs with similar products

## intent:engagement_intent
- page_view on social media | click on like | click on comment
- page_view on forum | form submit for comment
- page_view on video | click on subscribe | click on share
- multiple social interactions | high engagement

## intent:navigation_intent
- page_view | click on category | page_view
- search | refine search | search again
- page_view on homepage | click on menu | click on submenu
- browsing category pages | low scroll depth | quick transitions

## intent:unknown
- single page view
- very short session
- random clicks
"""
