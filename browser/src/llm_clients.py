"""
vLLM Clients for Mistral and DeepSeek

Cheap classifier (Mistral) + Escalation (DeepSeek) per HANDOFF spec.
"""

import json
import logging
import os
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class VLLMClient:
    """
    Base client for vLLM OpenAI-compatible endpoints.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=timeout)

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 500
    ) -> dict:
        """
        Send chat completion request to vLLM endpoint.
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"vLLM API error: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class MistralClient(VLLMClient):
    """
    Mistral-small client for cheap classification.

    Used in hybrid classifier alongside Rasa Pro.
    Provides semantic elasticity for evolving intent taxonomy.
    """

    SCORING_PROMPT = """You are an intent classifier analyzing web browsing events.

Given the following browsing events, score the likelihood of each intent type:
- PURCHASE_INTENT: User looking to buy (product pages, carts, checkout)
- RESEARCH_INTENT: User researching/learning (articles, guides, docs)
- COMPARISON_INTENT: User comparing options (reviews, vs pages)
- ENGAGEMENT_INTENT: User engaging (comments, forms, interactions)
- NAVIGATION_INTENT: User exploring (category pages, search results)

Output JSON format:
{
  "scores": {
    "PURCHASE_INTENT": 0.XX,
    "RESEARCH_INTENT": 0.XX,
    "COMPARISON_INTENT": 0.XX,
    "ENGAGEMENT_INTENT": 0.XX,
    "NAVIGATION_INTENT": 0.XX
  },
  "top_intent": "...",
  "confidence": 0.XX
}
"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "mistralai/Mistral-7B-Instruct-v0.1"
    ):
        url = base_url or os.getenv("VLLM_MISTRAL_URL", "http://localhost:8001")
        super().__init__(url, model)

    async def score_intent(self, events: list[dict]) -> dict:
        """
        Score intent probabilities for event bundle.

        Returns dict with scores per intent type and top_intent.
        """
        events_text = self._format_events(events)
        messages = [
            {"role": "system", "content": self.SCORING_PROMPT},
            {"role": "user", "content": f"Events:\n{events_text}\n\nScore intents:"}
        ]

        result = await self.chat_completion(messages, temperature=0.3, max_tokens=200)

        if "error" in result:
            return self._mock_scoring(events)

        try:
            content = result["choices"][0]["message"]["content"]
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(content[json_start:json_end])
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse Mistral response: {e}")

        return self._mock_scoring(events)

    def _format_events(self, events: list[dict]) -> str:
        """Format events for prompt."""
        lines = []
        for i, event in enumerate(events):
            event_type = event.get("event_type", "unknown")
            url = event.get("context", {}).get("url", "")
            payload = event.get("payload", {})
            lines.append(f"{i+1}. [{event_type}] {url} - {payload}")
        return "\n".join(lines)

    def _mock_scoring(self, events: list[dict]) -> dict:
        """Fallback mock scoring when API unavailable."""
        # Simple heuristic-based scoring
        scores = {
            "PURCHASE_INTENT": 0.15,
            "RESEARCH_INTENT": 0.20,
            "COMPARISON_INTENT": 0.15,
            "ENGAGEMENT_INTENT": 0.25,
            "NAVIGATION_INTENT": 0.25
        }

        for event in events:
            url = str(event.get("context", {}).get("url", "")).lower()
            payload = str(event.get("payload", {})).lower()

            if any(kw in url or kw in payload for kw in ["cart", "buy", "checkout", "price"]):
                scores["PURCHASE_INTENT"] += 0.20
            if any(kw in url or kw in payload for kw in ["guide", "how-to", "learn", "article"]):
                scores["RESEARCH_INTENT"] += 0.15
            if any(kw in url or kw in payload for kw in ["compare", "vs", "review", "best"]):
                scores["COMPARISON_INTENT"] += 0.15

        # Normalize
        total = sum(scores.values())
        scores = {k: round(v / total, 2) for k, v in scores.items()}

        top_intent = max(scores, key=scores.get)
        return {
            "scores": scores,
            "top_intent": top_intent,
            "confidence": scores[top_intent]
        }


class DeepSeekClient(VLLMClient):
    """
    DeepSeek client for long-chain reasoning (escalation).

    Only called when gating policy triggers escalation:
    - Confidence < 0.70
    - High-risk intent with confidence < 0.85
    - High-value session with confidence < 0.80
    - Top-2 intent margin < 0.10
    """

    REASONING_PROMPT = """You are an expert intent analyst performing deep reasoning on ambiguous browsing behavior.

The cheap classifier was uncertain. Analyze the events carefully:

1. What is the PRIMARY intent signal?
2. Are there conflicting signals?
3. What context supports your conclusion?
4. What confidence level is justified?
5. What are alternative interpretations?

Think step-by-step, then output JSON:
{
  "reasoning": "Step-by-step analysis...",
  "final_intent": "...",
  "confidence": 0.XX,
  "alternatives": [{"intent": "...", "confidence": 0.XX}],
  "supporting_signals": ["event_id_1", "event_id_2"]
}
"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "deepseek-ai/deepseek-coder-33b-instruct"
    ):
        url = base_url or os.getenv("VLLM_DEEPSEEK_URL", "http://localhost:8002")
        super().__init__(url, model, timeout=60.0)  # Longer timeout for reasoning

    async def reason(self, events: list[dict], cheap_result: dict) -> dict:
        """
        Perform deep reasoning on ambiguous event bundle.

        Args:
            events: Raw event bundle
            cheap_result: Result from cheap classifier (Rasa + Mistral)

        Returns:
            Dict with final_intent, confidence, reasoning, alternatives
        """
        events_text = self._format_events(events)
        cheap_text = json.dumps(cheap_result, indent=2)

        messages = [
            {"role": "system", "content": self.REASONING_PROMPT},
            {"role": "user", "content": f"""Events:
{events_text}

Cheap classifier result:
{cheap_text}

Perform deep reasoning to resolve the ambiguity:"""}
        ]

        result = await self.chat_completion(messages, temperature=0.5, max_tokens=500)

        if "error" in result:
            return self._fallback_result(cheap_result)

        try:
            content = result["choices"][0]["message"]["content"]
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(content[json_start:json_end])
                parsed["model"] = "deepseek-reasoning"
                return parsed
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse DeepSeek response: {e}")

        return self._fallback_result(cheap_result)

    def _format_events(self, events: list[dict]) -> str:
        """Format events for reasoning prompt."""
        lines = []
        for event in events:
            event_id = event.get("event_id", "unknown")
            event_type = event.get("event_type", "unknown")
            url = event.get("context", {}).get("url", "")
            payload = json.dumps(event.get("payload", {}))
            lines.append(f"[{event_id}] {event_type}: {url}\n  Payload: {payload}")
        return "\n".join(lines)

    def _fallback_result(self, cheap_result: dict) -> dict:
        """Fallback when DeepSeek unavailable - use cheap result with lower confidence."""
        return {
            "final_intent": cheap_result.get("top_intent", "NAVIGATION_INTENT"),
            "confidence": cheap_result.get("confidence", 0.5) * 0.9,  # Reduce confidence
            "reasoning": "DeepSeek unavailable - using cheap classifier result",
            "alternatives": [],
            "model": "fallback"
        }


class GatingPolicy:
    """
    Gating policy for escalation to DeepSeek.

    Thresholds from HANDOFF_intent_detection_engine.md:
    - Base confidence < 0.70 → escalate
    - High-risk intent < 0.85 → escalate
    - High-value session < 0.80 → escalate
    - Top-2 margin < 0.10 → escalate
    """

    HIGH_RISK_INTENTS = ["PURCHASE_INTENT", "FINANCIAL_INTENT", "PERSONAL_DATA"]

    def __init__(
        self,
        base_threshold: float = 0.70,
        high_risk_threshold: float = 0.85,
        high_value_threshold: float = 0.80,
        ambiguity_margin: float = 0.10
    ):
        self.base_threshold = base_threshold
        self.high_risk_threshold = high_risk_threshold
        self.high_value_threshold = high_value_threshold
        self.ambiguity_margin = ambiguity_margin

    def should_escalate(
        self,
        intent: str,
        confidence: float,
        scores: dict[str, float],
        session_value: Optional[float] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if escalation to DeepSeek is needed.

        Returns:
            (should_escalate, reason)
        """
        # Condition 1: Low confidence on any intent
        if confidence < self.base_threshold:
            return True, "low_confidence"

        # Condition 2: High-risk intents require higher confidence
        if intent in self.HIGH_RISK_INTENTS and confidence < self.high_risk_threshold:
            return True, "high_risk_low_confidence"

        # Condition 3: High-value sessions require higher confidence
        if session_value and session_value > 100 and confidence < self.high_value_threshold:
            return True, "high_value_low_confidence"

        # Condition 4: Ambiguity between top intents
        if scores:
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2:
                margin = sorted_scores[0] - sorted_scores[1]
                if margin < self.ambiguity_margin:
                    return True, "ambiguous"

        return False, None
