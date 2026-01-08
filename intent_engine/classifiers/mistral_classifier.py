"""
Mistral-Small Classifier Integration

Provides semantic elasticity and handles ambiguous cases better than rule-based Rasa.
"""

import asyncio
from typing import List, Dict, Any
from datetime import datetime
import json

from openai import AsyncOpenAI  # Mistral API is OpenAI-compatible

from ..models.intent_models import (
    BrowsingEvent,
    ClassifierOutput,
    AlternativeIntent,
    IntentType,
    ModelType
)


class MistralClassifier:
    """
    Mistral-Small classifier for semantic intent detection.

    Mistral excels at:
    - Ambiguous patterns
    - Novel/evolving user behavior
    - Semantic understanding beyond keywords
    """

    def __init__(
        self,
        api_key: str = None,
        endpoint: str = "https://api.mistral.ai/v1",
        model: str = "mistral-small-latest",
        timeout: float = 5.0
    ):
        self.model = model
        self.timeout = timeout

        # Mistral API is OpenAI-compatible
        self.client = AsyncOpenAI(
            api_key=api_key or "your-mistral-api-key",
            base_url=endpoint,
            timeout=timeout
        )

    async def classify(self, events: List[BrowsingEvent]) -> ClassifierOutput:
        """
        Classify browsing events using Mistral.

        Args:
            events: List of browsing events to analyze

        Returns:
            ClassifierOutput with intent, confidence, and alternatives
        """
        start_time = datetime.utcnow()

        # Build prompt
        prompt = self._build_prompt(events)

        # Call Mistral API
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": MISTRAL_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.0,  # Deterministic for classification
                max_tokens=200,
                response_format={"type": "json_object"}
            )

        except Exception as e:
            raise RuntimeError(f"Mistral API call failed: {e}")

        # Parse response
        try:
            result = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse Mistral JSON response: {e}")

        # Extract intent and confidence
        intent_str = result.get("intent", "UNKNOWN")
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", "")

        # Map to IntentType
        intent = self._map_mistral_intent(intent_str)

        # Get alternatives
        alternatives_data = result.get("alternatives", [])
        alternatives = [
            AlternativeIntent(
                intent=self._map_mistral_intent(alt["intent"]),
                confidence=alt["confidence"]
            )
            for alt in alternatives_data[:3]
        ]

        # Calculate latency
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return ClassifierOutput(
            model_id=ModelType.MISTRAL_SMALL,
            intent=intent,
            confidence=confidence,
            alternatives=alternatives,
            latency_ms=latency_ms,
            metadata={
                "reasoning": reasoning,
                "mistral_model": self.model
            }
        )

    def _build_prompt(self, events: List[BrowsingEvent]) -> str:
        """
        Build classification prompt for Mistral.

        Strategy:
        - Provide structured event sequence
        - Include temporal context
        - Request structured JSON output
        """
        # Limit to last 20 events to stay within token budget
        recent_events = events[-20:]

        event_descriptions = []
        for i, event in enumerate(recent_events):
            desc = {
                "step": i + 1,
                "type": event.event_type,
                "url_domain": self._extract_domain(event.url) if event.url else None,
                "properties": event.properties
            }
            event_descriptions.append(desc)

        prompt = f"""Analyze this browsing behavior sequence and classify the user's intent.

Browsing Events:
{json.dumps(event_descriptions, indent=2)}

Task:
1. Identify the primary intent from: PURCHASE_INTENT, RESEARCH_INTENT, COMPARISON_INTENT, ENGAGEMENT_INTENT, NAVIGATION_INTENT, UNKNOWN
2. Provide confidence score (0.0 to 1.0)
3. List up to 3 alternative intents with their confidence scores
4. Explain your reasoning briefly

Respond in JSON format:
{{
  "intent": "<primary_intent>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>",
  "alternatives": [
    {{"intent": "<intent>", "confidence": <0.0-1.0>}},
    ...
  ]
}}
"""
        return prompt

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except:
            return "unknown"

    def _map_mistral_intent(self, mistral_intent: str) -> IntentType:
        """Map Mistral intent string to IntentType enum"""
        try:
            return IntentType(mistral_intent)
        except ValueError:
            return IntentType.UNKNOWN

    async def close(self):
        """Close API client"""
        await self.client.close()


# System prompt for Mistral classifier
MISTRAL_SYSTEM_PROMPT = """You are an expert at analyzing web browsing behavior to detect user intent.

Intent Definitions:
- PURCHASE_INTENT: User is actively looking to buy something (viewing products, adding to cart, comparing prices, checking out)
- RESEARCH_INTENT: User is gathering information (reading articles, documentation, guides; high scroll depth, long time on page)
- COMPARISON_INTENT: User is comparing options (multiple product views, review sites, "vs" searches, switching between similar pages)
- ENGAGEMENT_INTENT: User is interacting socially (commenting, liking, sharing, posting; social media activity)
- NAVIGATION_INTENT: User is exploring/browsing casually (category browsing, menu navigation, low engagement per page)
- UNKNOWN: Insufficient data or unclear pattern

Classification Guidelines:
1. Consider the entire sequence, not just individual events
2. Look for patterns: repeated actions, time spent, engagement depth
3. Domain context matters (e.g., amazon.com suggests commerce, medium.com suggests research)
4. Confidence should reflect ambiguity: use < 0.7 when unsure
5. Provide alternative intents when the pattern could fit multiple categories
6. Be conservative: prefer UNKNOWN over low-confidence guesses

Always respond with valid JSON matching the requested schema.
"""
