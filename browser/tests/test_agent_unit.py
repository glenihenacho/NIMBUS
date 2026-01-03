"""Unit tests for PAT Browser Agent (no browser required)"""

import pytest
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/home/user/NIMBUS/browser')

from src.agent import IntentType, IntentSignal, DataSegment, QwenClient


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


class TestQwenClient:
    """Tests for QwenClient (mock mode)"""

    @pytest.mark.asyncio
    async def test_analyze_purchase_url(self):
        client = QwenClient()

        signals = await client.analyze_page(
            page_content="<html>Buy now</html>",
            url="https://shop.example.com/product/laptop"
        )

        # Should detect purchase intent from URL pattern
        purchase_signals = [s for s in signals if s.type == IntentType.PURCHASE_INTENT]
        assert len(purchase_signals) > 0
        assert purchase_signals[0].confidence > 0.7

    @pytest.mark.asyncio
    async def test_analyze_comparison_url(self):
        client = QwenClient()

        signals = await client.analyze_page(
            page_content="<html>Compare products</html>",
            url="https://example.com/compare/phones-vs-tablets"
        )

        comparison_signals = [s for s in signals if s.type == IntentType.COMPARISON_INTENT]
        assert len(comparison_signals) > 0

    @pytest.mark.asyncio
    async def test_analyze_research_url(self):
        client = QwenClient()

        signals = await client.analyze_page(
            page_content="<html>Learn how to code</html>",
            url="https://blog.example.com/article/learn-python"
        )

        research_signals = [s for s in signals if s.type == IntentType.RESEARCH_INTENT]
        assert len(research_signals) > 0


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
