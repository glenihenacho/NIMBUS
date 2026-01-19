"""
Hybrid Intent Detection Clients

Per HANDOFF_intent_detection_engine.md:
- Cheap classifier: Rasa Open Source (deterministic) + Mistral-small (semantic)
- Escalation: DeepSeek reasoning (gated, expensive)
"""

import json
import logging
import os
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# Rasa Client (Deterministic NLU)
# =============================================================================

class RasaClient:
    """
    Rasa Open Source client for deterministic intent classification.

    Fast inference (<50ms), handles intent classification from DOM/metadata.
    Used as primary classifier in hybrid Rasa + Mistral pipeline.
    """

    # Map browsing event types to Rasa intent format
    INTENT_MAPPING = {
        "page_view": "view_page",
        "product_view": "purchase_intent",
        "add_to_cart": "purchase_intent",
        "checkout_start": "purchase_intent",
        "search": "navigation_intent",
        "article_read": "research_intent",
        "comparison_view": "comparison_intent",
        "form_submit": "engagement_intent",
        "scroll": "engagement_intent",
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 5.0
    ):
        self.base_url = (base_url or os.getenv("RASA_URL", "http://localhost:5005")).rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout)

    async def parse(self, events: list[dict]) -> dict:
        """
        Parse event bundle using Rasa NLU.

        Returns dict with intent, confidence, entities.
        """
        # Convert events to text for Rasa parsing
        text = self._events_to_text(events)

        try:
            response = await self.client.post(
                f"{self.base_url}/model/parse",
                json={"text": text}
            )
            response.raise_for_status()
            result = response.json()

            return {
                "intent": result.get("intent", {}).get("name", "navigation_intent"),
                "confidence": result.get("intent", {}).get("confidence", 0.5),
                "entities": result.get("entities", []),
                "classifier": "rasa"
            }
        except httpx.HTTPError as e:
            logger.warning(f"Rasa API error: {e}, using heuristic fallback")
            return self._heuristic_classify(events)

    def _events_to_text(self, events: list[dict]) -> str:
        """Convert browsing events to natural language text for Rasa."""
        if not events:
            return "user browsing"

        parts = []
        for event in events:
            event_type = event.get("event_type", "page_view")
            url = event.get("context", {}).get("url", "")
            payload = event.get("payload", {})

            if "title" in payload:
                parts.append(f"viewing {payload['title']}")
            elif "query" in payload:
                parts.append(f"searching for {payload['query']}")
            elif "product" in str(url).lower() or "item" in str(url).lower():
                parts.append("looking at products")
            elif "cart" in str(url).lower():
                parts.append("adding to cart")
            elif "checkout" in str(url).lower():
                parts.append("checking out")
            elif "article" in str(url).lower() or "blog" in str(url).lower():
                parts.append("reading articles")
            elif "compare" in str(url).lower() or "vs" in str(url).lower():
                parts.append("comparing options")
            else:
                parts.append(f"browsing {url[:50] if url else 'page'}")

        return " and ".join(parts[:5])  # Limit to 5 most recent

    def _heuristic_classify(self, events: list[dict]) -> dict:
        """Fallback heuristic classification when Rasa unavailable."""
        scores = {
            "PURCHASE_INTENT": 0.0,
            "RESEARCH_INTENT": 0.0,
            "COMPARISON_INTENT": 0.0,
            "ENGAGEMENT_INTENT": 0.0,
            "NAVIGATION_INTENT": 0.2,  # Default bias
        }

        for event in events:
            event_type = event.get("event_type", "")
            url = str(event.get("context", {}).get("url", "")).lower()
            payload = str(event.get("payload", {})).lower()

            # Purchase signals
            if any(kw in url or kw in payload for kw in ["cart", "buy", "checkout", "price", "product"]):
                scores["PURCHASE_INTENT"] += 0.25
            # Research signals
            if any(kw in url or kw in payload for kw in ["guide", "how-to", "learn", "article", "doc", "tutorial"]):
                scores["RESEARCH_INTENT"] += 0.25
            # Comparison signals
            if any(kw in url or kw in payload for kw in ["compare", "vs", "review", "best", "top"]):
                scores["COMPARISON_INTENT"] += 0.25
            # Engagement signals
            if event_type in ["form_submit", "comment", "share", "like"]:
                scores["ENGAGEMENT_INTENT"] += 0.25

        # Normalize
        total = sum(scores.values()) or 1.0
        scores = {k: v / total for k, v in scores.items()}

        top_intent = max(scores, key=scores.get)
        return {
            "intent": top_intent,
            "confidence": scores[top_intent],
            "entities": [],
            "classifier": "heuristic"
        }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# =============================================================================
# Hybrid Classifier (Rasa + Mistral)
# =============================================================================

class HybridClassifier:
    """
    Hybrid intent classifier combining Rasa and Mistral per HANDOFF spec.

    Flow:
    1. Run Rasa (fast, deterministic)
    2. If Rasa confidence < 0.75, also run Mistral
    3. Ensemble: average confidences when both run
    """

    RASA_CONFIDENCE_THRESHOLD = 0.75

    def __init__(
        self,
        rasa_client: Optional['RasaClient'] = None,
        mistral_client: Optional['MistralClient'] = None
    ):
        self.rasa = rasa_client or RasaClient()
        self.mistral = mistral_client or MistralClient()

    async def classify(self, events: list[dict]) -> dict:
        """
        Run hybrid classification on event bundle.

        Returns dict with intent, confidence, scores, classifier_used.
        """
        # Step 1: Rasa classification (always runs first)
        rasa_result = await self.rasa.parse(events)
        rasa_intent = rasa_result["intent"]
        rasa_conf = rasa_result["confidence"]

        # Step 2: Mistral scoring if Rasa confidence below threshold
        if rasa_conf < self.RASA_CONFIDENCE_THRESHOLD:
            logger.debug(f"Rasa conf {rasa_conf:.2f} < {self.RASA_CONFIDENCE_THRESHOLD}, running Mistral")
            mistral_result = await self.mistral.score_intent(events)
            mistral_conf = mistral_result.get("confidence", 0.5)
            mistral_scores = mistral_result.get("scores", {})

            # Ensemble: average confidences
            final_conf = (rasa_conf + mistral_conf) / 2

            # Use Mistral's top intent if it matches Rasa, otherwise trust Rasa
            mistral_intent = mistral_result.get("top_intent", rasa_intent)
            if mistral_intent == rasa_intent:
                final_intent = rasa_intent
            else:
                # Conflicting intents - use the one with higher confidence
                final_intent = rasa_intent if rasa_conf >= mistral_conf else mistral_intent

            return {
                "top_intent": final_intent,
                "confidence": final_conf,
                "scores": mistral_scores,
                "classifier": "rasa+mistral",
                "rasa_result": rasa_result,
                "mistral_result": mistral_result
            }
        else:
            # Rasa confidence high enough - use Rasa alone
            return {
                "top_intent": rasa_intent,
                "confidence": rasa_conf,
                "scores": {rasa_intent: rasa_conf},
                "classifier": "rasa",
                "rasa_result": rasa_result
            }

    async def close(self):
        """Close clients."""
        await self.rasa.close()
        await self.mistral.close()


# =============================================================================
# vLLM Base Client
# =============================================================================


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

    Used in hybrid classifier alongside Rasa Open Source.
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
