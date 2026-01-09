"""Unit tests for PAT Browser Agent (no browser required)"""

import pytest
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/home/user/NIMBUS/browser')

from src.agent import IntentType, IntentSignal, DataSegment
from src.llm_clients import MistralClient, DeepSeekClient, GatingPolicy


class TestIntentSignal:
    """Tests for IntentSignal dataclass"""

    def test_create_signal(self):
        signal = IntentSignal(
            type=IntentType.PURCHASE_INTENT,
            confidence=0.85,
            url="https://example.com/product",
            timestamp=datetime.utcnow(),
            metadata={"source": "test"}
        )

        assert signal.type == IntentType.PURCHASE_INTENT
        assert signal.confidence == 0.85
        assert "example.com" in signal.url

    def test_signal_to_dict(self):
        signal = IntentSignal(
            type=IntentType.RESEARCH_INTENT,
            confidence=0.72,
            url="https://example.com/article",
            timestamp=datetime(2024, 1, 15, 12, 0, 0),
            metadata={"keywords": ["guide"]}
        )

        d = signal.to_dict()
        assert d["type"] == "RESEARCH_INTENT"
        assert d["confidence"] == 0.72
        assert "keywords" in d["metadata"]


class TestDataSegment:
    """Tests for DataSegment dataclass"""

    def test_create_segment(self):
        signals = [
            IntentSignal(
                type=IntentType.PURCHASE_INTENT,
                confidence=0.80,
                url="https://example.com/shop",
                timestamp=datetime.utcnow(),
                metadata={}
            )
        ]

        segment = DataSegment(
            segment_type=IntentType.PURCHASE_INTENT,
            time_window_days=7,
            confidence_min=0.70,
            confidence_max=0.90,
            signals=signals,
            created_at=datetime.utcnow()
        )

        assert segment.segment_type == IntentType.PURCHASE_INTENT
        assert len(segment.signals) == 1

    def test_segment_id_format(self):
        segment = DataSegment(
            segment_type=IntentType.COMPARISON_INTENT,
            time_window_days=7,
            confidence_min=0.70,
            confidence_max=0.85,
            signals=[],
            created_at=datetime.utcnow()
        )

        # Format: TYPE|WINDOW|RANGE
        assert segment.segment_id == "COMPARISON_INTENT|7D|0.70-0.85"

    def test_segment_to_dict(self):
        segment = DataSegment(
            segment_type=IntentType.ENGAGEMENT_INTENT,
            time_window_days=14,
            confidence_min=0.60,
            confidence_max=0.80,
            signals=[],
            created_at=datetime(2024, 1, 20)
        )

        d = segment.to_dict()
        assert d["segment_type"] == "ENGAGEMENT_INTENT"
        assert d["time_window_days"] == 14
        assert d["confidence_range"]["min"] == 0.60
        assert d["signal_count"] == 0


class TestMistralClient:
    """Tests for MistralClient (mock mode when vLLM unavailable)"""

    @pytest.mark.asyncio
    async def test_score_purchase_intent(self):
        client = MistralClient()

        events = [{
            "event_type": "page_view",
            "context": {"url": "https://shop.example.com/cart/checkout"},
            "payload": {"title": "Buy Now - Checkout"}
        }]

        result = await client.score_intent(events)

        # Should return scores dict with top_intent
        assert "scores" in result
        assert "top_intent" in result
        assert "confidence" in result
        await client.close()

    @pytest.mark.asyncio
    async def test_score_research_intent(self):
        client = MistralClient()

        events = [{
            "event_type": "page_view",
            "context": {"url": "https://blog.example.com/guide/how-to-learn"},
            "payload": {"title": "Learning Guide"}
        }]

        result = await client.score_intent(events)
        assert "RESEARCH_INTENT" in result.get("scores", {})
        await client.close()


class TestGatingPolicy:
    """Tests for GatingPolicy escalation logic"""

    def test_low_confidence_escalates(self):
        policy = GatingPolicy()

        should_escalate, reason = policy.should_escalate(
            intent="PURCHASE_INTENT",
            confidence=0.60,
            scores={"PURCHASE_INTENT": 0.60}
        )

        assert should_escalate is True
        assert reason == "low_confidence"

    def test_high_confidence_no_escalation(self):
        policy = GatingPolicy()

        should_escalate, reason = policy.should_escalate(
            intent="NAVIGATION_INTENT",
            confidence=0.85,
            scores={"NAVIGATION_INTENT": 0.85}
        )

        assert should_escalate is False
        assert reason is None

    def test_high_risk_intent_escalates(self):
        policy = GatingPolicy()

        # PURCHASE_INTENT is high-risk, needs confidence >= 0.85
        should_escalate, reason = policy.should_escalate(
            intent="PURCHASE_INTENT",
            confidence=0.75,
            scores={"PURCHASE_INTENT": 0.75}
        )

        assert should_escalate is True
        assert reason == "high_risk_low_confidence"

    def test_ambiguous_scores_escalate(self):
        policy = GatingPolicy()

        # Top-2 margin < 0.10 triggers escalation
        should_escalate, reason = policy.should_escalate(
            intent="PURCHASE_INTENT",
            confidence=0.72,
            scores={
                "PURCHASE_INTENT": 0.72,
                "RESEARCH_INTENT": 0.68  # Only 0.04 margin
            }
        )

        assert should_escalate is True
        assert reason == "ambiguous"


class TestIntentTypes:
    """Tests for IntentType enum"""

    def test_all_intent_types(self):
        types = list(IntentType)
        assert len(types) == 5

        type_names = [t.value for t in types]
        assert "PURCHASE_INTENT" in type_names
        assert "RESEARCH_INTENT" in type_names
        assert "COMPARISON_INTENT" in type_names
        assert "ENGAGEMENT_INTENT" in type_names
        assert "NAVIGATION_INTENT" in type_names

    def test_to_contract_id(self):
        assert IntentType.PURCHASE_INTENT.to_contract_id() == 0
        assert IntentType.RESEARCH_INTENT.to_contract_id() == 1
        assert IntentType.COMPARISON_INTENT.to_contract_id() == 2
        assert IntentType.ENGAGEMENT_INTENT.to_contract_id() == 3
        assert IntentType.NAVIGATION_INTENT.to_contract_id() == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
