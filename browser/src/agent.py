"""
PAT Browser Agent - Hybrid Intent Detection

Collects browser events using canonical schema (v1) and extracts
intent signals via Rasa + Mistral + DeepSeek pipeline.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from playwright.async_api import async_playwright, Browser

from .llm_clients import MistralClient, DeepSeekClient, GatingPolicy
from .schema import EventType, BrowserEvent, IntentInference, Context, Privacy

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """
    Intent signal types - aligned with DataMarketplace.SegmentType

    Maps to smart contract enum:
    0 = PURCHASE_INTENT
    1 = RESEARCH_INTENT
    2 = COMPARISON_INTENT
    3 = ENGAGEMENT_INTENT
    4 = NAVIGATION_INTENT
    """
    PURCHASE_INTENT = "PURCHASE_INTENT"
    RESEARCH_INTENT = "RESEARCH_INTENT"
    COMPARISON_INTENT = "COMPARISON_INTENT"
    ENGAGEMENT_INTENT = "ENGAGEMENT_INTENT"
    NAVIGATION_INTENT = "NAVIGATION_INTENT"

    def to_contract_id(self) -> int:
        """Map to smart contract SegmentType enum index"""
        return list(IntentType).index(self)


@dataclass
class IntentSignal:
    """Represents a detected browsing intent signal"""
    type: IntentType
    confidence: float  # 0.0 to 1.0
    url: str
    timestamp: datetime
    metadata: dict

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "url": self.url,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class DataSegment:
    """
    A data segment for the PAT marketplace

    Format: SEGMENT_TYPE | TIME_WINDOW | CONFIDENCE_RANGE
    Example: PURCHASE_INTENT | 7D | 0.70-0.85
    """
    segment_type: IntentType
    time_window_days: int
    confidence_min: float
    confidence_max: float
    signals: list[IntentSignal]
    created_at: datetime

    @property
    def segment_id(self) -> str:
        """Generate segment identifier"""
        return f"{self.segment_type.value}|{self.time_window_days}D|{self.confidence_min:.2f}-{self.confidence_max:.2f}"

    def to_dict(self) -> dict:
        """Convert to dictionary for marketplace submission"""
        return {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type.value,
            "time_window_days": self.time_window_days,
            "confidence_range": {
                "min": self.confidence_min,
                "max": self.confidence_max
            },
            "signal_count": len(self.signals),
            "created_at": self.created_at.isoformat(),
            "signals": [s.to_dict() for s in self.signals]
        }


class BrowserAgent:
    """
    Browser Agent for collecting web browsing intent signals

    Uses Playwright for browser automation and hybrid Mistral+DeepSeek
    for intent analysis. Collects raw events using canonical schema (v1).
    """

    def __init__(
        self,
        mistral_client: Optional[MistralClient] = None,
        deepseek_client: Optional[DeepSeekClient] = None,
        gating_policy: Optional[GatingPolicy] = None
    ):
        self.mistral = mistral_client or MistralClient()
        self.deepseek = deepseek_client or DeepSeekClient()
        self.gating = gating_policy or GatingPolicy()
        self.browser: Optional[Browser] = None
        self.collected_signals: list[IntentSignal] = []
        self.raw_events: list[BrowserEvent] = []
        self.inferences: list[IntentInference] = []
        logger.info("Initialized Browser Agent (Mistral + DeepSeek)")

    async def start(self, headless: bool = True):
        """Start the browser"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=headless)
        logger.info(f"Browser started (headless={headless})")

    async def stop(self):
        """Stop the browser and cleanup clients"""
        if self.browser:
            await self.browser.close()
        await self.mistral.close()
        await self.deepseek.close()
        logger.info("Browser stopped")

    def _create_page_event(self, url: str, title: str) -> BrowserEvent:
        """Create canonical PAGE_VIEW event"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        now = datetime.utcnow()

        return BrowserEvent(
            event_type=EventType.PAGE_VIEW,
            event_time=now,
            context=Context(
                url_domain=parsed.netloc,
                url_path=parsed.path,
                viewport_width=1920,
                viewport_height=1080,
                device_type="desktop",
                country="US",
                hour_of_day=now.hour,
                day_of_week=now.weekday(),
                is_business_hours=9 <= now.hour <= 17
            ),
            payload={"title": title, "url": url},
            privacy=Privacy(consent_monetization=True, data_sale_opt_in=True)
        )

    async def _analyze_events(self, events: list[dict]) -> tuple[str, float, str]:
        """
        Analyze events using hybrid Mistral + DeepSeek pipeline.

        Returns: (intent_type, confidence, model_used)
        """
        # Step 1: Cheap classification (Mistral)
        cheap_result = await self.mistral.score_intent(events)
        top_intent = cheap_result.get("top_intent", "NAVIGATION_INTENT")
        confidence = cheap_result.get("confidence", 0.5)
        scores = cheap_result.get("scores", {})

        # Step 2: Gating policy - escalate if uncertain
        should_escalate, reason = self.gating.should_escalate(
            intent=top_intent,
            confidence=confidence,
            scores=scores
        )

        # Step 3: Escalate to DeepSeek if needed
        if should_escalate:
            logger.info(f"Escalating to DeepSeek: {reason}")
            deep_result = await self.deepseek.reason(events, cheap_result)
            return (
                deep_result.get("final_intent", top_intent),
                deep_result.get("confidence", confidence),
                "deepseek"
            )

        return top_intent, confidence, "mistral"

    async def navigate_and_analyze(self, url: str) -> list[IntentSignal]:
        """
        Navigate to a URL and analyze for intent signals

        Creates canonical PAGE_VIEW event and stores intent inferences separately.
        """
        if not self.browser:
            raise RuntimeError("Browser not started. Call start() first.")

        page = await self.browser.new_page()

        try:
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)

            content = await page.content()
            title = await page.title()

            logger.info(f"Page loaded: {title}")

            # Create and store raw event (canonical schema)
            event = self._create_page_event(url, title)
            self.raw_events.append(event)

            # Prepare event bundle for analysis
            event_bundle = [event.to_dict()]

            # Analyze with hybrid pipeline
            intent_str, confidence, model = await self._analyze_events(event_bundle)

            try:
                intent_type = IntentType(intent_str)
            except ValueError:
                intent_type = IntentType.NAVIGATION_INTENT

            # Create signal
            signal = IntentSignal(
                type=intent_type,
                confidence=confidence,
                url=url,
                timestamp=datetime.utcnow(),
                metadata={"model": model, "title": title}
            )

            # Store inference separately per canonical schema
            self.inferences.append(IntentInference(
                source_event_ids=[event.event_id],
                model_id=model,
                intent_type=intent_type.value,
                confidence=confidence,
                alternatives=[]
            ))

            self.collected_signals.append(signal)
            logger.info(f"Detected {intent_type.value} ({confidence:.2f}) via {model}")
            return [signal]

        except Exception as e:
            logger.error(f"Error analyzing {url}: {e}")
            return []
        finally:
            await page.close()

    async def browse_urls(self, urls: list[str]) -> list[IntentSignal]:
        """Browse multiple URLs and collect signals"""
        all_signals = []

        for url in urls:
            signals = await self.navigate_and_analyze(url)
            all_signals.extend(signals)
            await asyncio.sleep(1)  # Rate limiting

        return all_signals

    def create_segment(
        self,
        segment_type: IntentType,
        time_window_days: int = 7,
        confidence_min: float = 0.70,
        confidence_max: float = 0.85
    ) -> DataSegment:
        """Create a data segment from collected signals"""
        filtered_signals = [
            s for s in self.collected_signals
            if s.type == segment_type
            and confidence_min <= s.confidence <= confidence_max
        ]

        cutoff = datetime.utcnow() - timedelta(days=time_window_days)
        filtered_signals = [
            s for s in filtered_signals
            if s.timestamp >= cutoff
        ]

        segment = DataSegment(
            segment_type=segment_type,
            time_window_days=time_window_days,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            signals=filtered_signals,
            created_at=datetime.utcnow()
        )

        logger.info(f"Created segment: {segment.segment_id} with {len(filtered_signals)} signals")
        return segment

    def export_segments(self, segments: list[DataSegment], filepath: str):
        """Export segments to JSON file for marketplace submission"""
        data = {
            "segments": [s.to_dict() for s in segments],
            "exported_at": datetime.utcnow().isoformat(),
            "agent_version": "2.0.0"
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported {len(segments)} segments to {filepath}")

    def export_raw_events(self, filepath: str):
        """
        Export raw events and inferences per canonical schema

        Separates raw events from intent inferences for:
        - Model swapping without touching raw events
        - Historical reprocessing
        - GDPR/CCPA compliance via retention_tier
        """
        data = {
            "events_raw": [e.to_dict() for e in self.raw_events],
            "intent_inferences": [i.to_dict() for i in self.inferences],
            "exported_at": datetime.utcnow().isoformat(),
            "schema_version": "v1"
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported {len(self.raw_events)} events, {len(self.inferences)} inferences to {filepath}")


async def main():
    """Example usage of the browser agent"""

    # Initialize with hybrid classifier
    agent = BrowserAgent()

    try:
        await agent.start(headless=True)

        urls = [
            "https://example.com/products/laptop",
            "https://example.com/compare/laptops",
            "https://example.com/blog/buying-guide",
        ]

        signals = await agent.browse_urls(urls)
        print(f"\nCollected {len(signals)} total signals")

        segments = []
        for intent_type in IntentType:
            segment = agent.create_segment(
                segment_type=intent_type,
                time_window_days=7,
                confidence_min=0.70,
                confidence_max=0.90
            )
            if segment.signals:
                segments.append(segment)

        if segments:
            agent.export_segments(segments, "segments_output.json")
            print("\n=== Created Segments ===")
            for segment in segments:
                print(f"  {segment.segment_id}: {len(segment.signals)} signals")

    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
