"""
DeepSeek Reasoning Model Integration

Provides long-chain reasoning for ambiguous, high-risk, or high-value intent decisions.
"""

import asyncio
from typing import List, Dict, Any
from datetime import datetime
from uuid import UUID
import json

from openai import AsyncOpenAI  # DeepSeek API is OpenAI-compatible

from ..models.intent_models import (
    BrowsingEvent,
    ClassifierOutput,
    EscalationOutput,
    SupportingSignal,
    AlternativeIntent,
    IntentType,
    ModelType,
    Session
)


class DeepSeekReasoner:
    """
    DeepSeek reasoning model for complex intent resolution.

    DeepSeek excels at:
    - Multi-step reasoning about user behavior
    - Resolving ambiguous patterns
    - Explaining decisions with evidence
    - High-stakes decisions requiring confidence
    """

    def __init__(
        self,
        api_key: str = None,
        endpoint: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-reasoner",
        timeout: float = 30.0  # Longer timeout for reasoning
    ):
        self.model = model
        self.timeout = timeout

        # DeepSeek API is OpenAI-compatible
        self.client = AsyncOpenAI(
            api_key=api_key or "your-deepseek-api-key",
            base_url=endpoint,
            timeout=timeout
        )

    async def reason(
        self,
        events: List[BrowsingEvent],
        cheap_output: ClassifierOutput,
        session: Session
    ) -> EscalationOutput:
        """
        Perform long-chain reasoning to resolve intent.

        Args:
            events: List of browsing events
            cheap_output: Output from cheap classifier (for context)
            session: Session metadata

        Returns:
            EscalationOutput with final intent, confidence, reasoning, and evidence
        """
        start_time = datetime.utcnow()

        # Build reasoning prompt
        prompt = self._build_reasoning_prompt(events, cheap_output, session)

        # Call DeepSeek API
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": DEEPSEEK_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent reasoning
                max_tokens=1500,  # Allow for detailed reasoning
                response_format={"type": "json_object"}
            )

        except Exception as e:
            raise RuntimeError(f"DeepSeek API call failed: {e}")

        # Parse response
        try:
            result = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse DeepSeek JSON response: {e}")

        # Extract structured output
        final_intent = self._map_intent(result.get("final_intent", "UNKNOWN"))
        confidence = result.get("confidence", 0.0)
        reasoning_trace = result.get("reasoning", "")
        recommended_action = result.get("recommended_action")

        # Parse supporting signals
        supporting_signals = []
        for signal_data in result.get("supporting_signals", []):
            try:
                supporting_signals.append(SupportingSignal(
                    source_event_id=UUID(signal_data["event_id"]),
                    signal_type=signal_data["signal_type"],
                    relevance_score=signal_data["relevance_score"],
                    description=signal_data["description"]
                ))
            except (KeyError, ValueError) as e:
                # Skip malformed signals
                continue

        # Parse alternatives
        alternatives = []
        for alt_data in result.get("alternatives", []):
            try:
                alternatives.append(AlternativeIntent(
                    intent=self._map_intent(alt_data["intent"]),
                    confidence=alt_data["confidence"]
                ))
            except (KeyError, ValueError):
                continue

        # Calculate latency
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return EscalationOutput(
            final_intent=final_intent,
            confidence=confidence,
            supporting_signals=supporting_signals,
            alternatives=alternatives,
            recommended_action=recommended_action,
            reasoning_trace=reasoning_trace,
            latency_ms=latency_ms
        )

    def _build_reasoning_prompt(
        self,
        events: List[BrowsingEvent],
        cheap_output: ClassifierOutput,
        session: Session
    ) -> str:
        """
        Build comprehensive reasoning prompt for DeepSeek.

        Includes:
        - Full event history (or recent window)
        - Cheap classifier's prediction
        - Session context (value score, risk level)
        - Specific reasoning task
        """
        # Serialize events with full context
        event_data = []
        for event in events[-30:]:  # Last 30 events
            event_data.append({
                "event_id": str(event.event_id),
                "type": event.event_type,
                "url_domain": self._extract_domain(event.url) if event.url else None,
                "timestamp": event.timestamp.isoformat(),
                "properties": event.properties
            })

        prompt = f"""You are tasked with making a high-confidence intent classification decision.

CONTEXT:
Session ID: {session.session_id}
Total Events in Session: {session.event_count}
Session Value Score: {session.value_score:.2f}
Risk Level: {session.risk_level.value}

INITIAL CLASSIFIER OUTPUT:
The cheap classifier (Rasa/Mistral) predicted:
- Intent: {cheap_output.intent.value}
- Confidence: {cheap_output.confidence:.2f}
- Model: {cheap_output.model_id.value}

However, this was escalated to you because:
- The confidence may be insufficient for this decision
- The pattern may be ambiguous
- The session may be high-value or high-risk

BROWSING EVENT SEQUENCE:
{json.dumps(event_data, indent=2)}

YOUR TASK:
Analyze the complete browsing sequence and make a final intent classification.

Consider:
1. Overall behavioral pattern across all events
2. Temporal patterns (sequence, timing, duration)
3. Domain context and page types
4. Engagement signals (scroll depth, time on page, interactions)
5. Whether the cheap classifier's prediction aligns with the evidence

Provide:
1. Your final intent classification (PURCHASE_INTENT, RESEARCH_INTENT, COMPARISON_INTENT, ENGAGEMENT_INTENT, NAVIGATION_INTENT, or UNKNOWN)
2. Your confidence score (0.0 to 1.0) - be conservative if evidence is weak
3. Supporting signals: cite specific events (by event_id) that support your decision
4. Alternative intents if the pattern is genuinely ambiguous
5. A recommended action (if applicable)
6. Your reasoning process

Respond in JSON format:
{{
  "final_intent": "<intent>",
  "confidence": <0.0-1.0>,
  "reasoning": "<detailed multi-step reasoning>",
  "supporting_signals": [
    {{
      "event_id": "<uuid>",
      "signal_type": "<what this event indicates>",
      "relevance_score": <0.0-1.0>,
      "description": "<why this supports the intent>"
    }},
    ...
  ],
  "alternatives": [
    {{"intent": "<intent>", "confidence": <0.0-1.0>}},
    ...
  ],
  "recommended_action": "<optional: what to do with this intent>"
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

    def _map_intent(self, intent_str: str) -> IntentType:
        """Map intent string to IntentType enum"""
        try:
            return IntentType(intent_str)
        except ValueError:
            return IntentType.UNKNOWN

    async def close(self):
        """Close API client"""
        await self.client.close()


# System prompt for DeepSeek reasoner
DEEPSEEK_SYSTEM_PROMPT = """You are an expert reasoning system for intent classification in web browsing behavior.

Your role is to make high-confidence decisions when simpler classifiers are uncertain. You have been escalated to because:
- The cheap classifier's confidence is low
- The pattern is ambiguous or complex
- The decision is high-stakes (high-value user or high-risk intent)

Intent Definitions:
- PURCHASE_INTENT: Active buying behavior (product pages, cart actions, checkout, price comparison)
- RESEARCH_INTENT: Information gathering (reading content, high engagement with informational pages, bookmarking)
- COMPARISON_INTENT: Evaluating options (multiple similar products, review sites, "vs" queries, tab switching)
- ENGAGEMENT_INTENT: Social interaction (commenting, liking, sharing, community participation)
- NAVIGATION_INTENT: Casual browsing (exploring categories, low engagement per page, menu navigation)
- UNKNOWN: Genuinely unclear or insufficient evidence

Reasoning Approach:
1. Analyze the complete behavioral sequence, not isolated events
2. Look for intent progression (e.g., research → comparison → purchase)
3. Weight recent events more heavily for current intent
4. Consider domain context and page semantics
5. Identify contradictory signals and resolve them
6. Be explicit about your reasoning steps
7. Cite specific events as evidence
8. Quantify your confidence honestly - if uncertain, say so

Quality Standards:
- Confidence > 0.85: Strong evidence, clear pattern
- Confidence 0.70-0.85: Reasonable evidence, some ambiguity
- Confidence < 0.70: Weak evidence, consider UNKNOWN

Always provide supporting evidence (event IDs) for your decision.
Always respond with valid JSON matching the requested schema.
"""


# Example usage for testing
async def test_deepseek():
    """Test DeepSeek reasoner with example data"""
    from ..models.intent_models import BrowsingEvent, ClassifierOutput, Session, RiskLevel
    from uuid import uuid4
    from datetime import datetime

    # Create test events
    events = [
        BrowsingEvent(
            session_id="test-session",
            user_id_hash="test-user",
            event_type="page_view",
            url="https://amazon.com/laptop",
            timestamp=datetime.utcnow(),
            properties={"scroll_depth": 80, "time_on_page": 45}
        ),
        BrowsingEvent(
            session_id="test-session",
            user_id_hash="test-user",
            event_type="click",
            url="https://amazon.com/laptop",
            timestamp=datetime.utcnow(),
            properties={"element": "add-to-cart"}
        )
    ]

    # Create cheap classifier output
    cheap_output = ClassifierOutput(
        model_id=ModelType.MISTRAL_SMALL,
        intent=IntentType.PURCHASE_INTENT,
        confidence=0.65,
        alternatives=[],
        latency_ms=100.0
    )

    # Create session
    session = Session(
        session_id="test-session",
        user_id_hash="test-user",
        event_count=2,
        value_score=0.8,
        risk_level=RiskLevel.MEDIUM
    )

    # Test reasoner
    reasoner = DeepSeekReasoner()
    result = await reasoner.reason(events, cheap_output, session)

    print("DeepSeek Result:")
    print(f"Intent: {result.final_intent}")
    print(f"Confidence: {result.confidence}")
    print(f"Reasoning: {result.reasoning_trace}")
    print(f"Supporting Signals: {len(result.supporting_signals)}")

    await reasoner.close()


if __name__ == "__main__":
    asyncio.run(test_deepseek())
