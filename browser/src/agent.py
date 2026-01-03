"""
PAT AI Browser Agent - Powered by Qwen

This agent autonomously browses the web to extract web browsing intent signals
that are packaged as data segments for the PAT marketplace.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Types of browsing intent signals"""
    PURCHASE_INTENT = "PURCHASE_INTENT"
    RESEARCH_INTENT = "RESEARCH_INTENT"
    COMPARISON_INTENT = "COMPARISON_INTENT"
    ENGAGEMENT_INTENT = "ENGAGEMENT_INTENT"
    NAVIGATION_INTENT = "NAVIGATION_INTENT"


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


class QwenClient:
    """
    Client for Qwen LLM API

    In production, this would connect to Qwen's API.
    For the prototype, we simulate intent detection.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        logger.info("Initialized Qwen client")

    async def analyze_page(self, page_content: str, url: str) -> list[IntentSignal]:
        """
        Analyze page content to detect intent signals

        In production, this sends the content to Qwen for analysis.
        The model identifies:
        - Purchase intent (product pages, cart, checkout)
        - Research intent (comparison pages, reviews)
        - Engagement signals (time on page, scroll depth)
        """
        signals = []

        # Simulate Qwen analysis (in production, call Qwen API)
        # Detection heuristics based on URL patterns and content

        if any(kw in url.lower() for kw in ["product", "buy", "shop", "cart"]):
            signals.append(IntentSignal(
                type=IntentType.PURCHASE_INTENT,
                confidence=0.85,
                url=url,
                timestamp=datetime.utcnow(),
                metadata={"source": "url_pattern", "keywords": ["product", "buy"]}
            ))

        if any(kw in url.lower() for kw in ["compare", "review", "vs"]):
            signals.append(IntentSignal(
                type=IntentType.COMPARISON_INTENT,
                confidence=0.75,
                url=url,
                timestamp=datetime.utcnow(),
                metadata={"source": "url_pattern", "keywords": ["compare", "review"]}
            ))

        if any(kw in url.lower() for kw in ["article", "blog", "learn", "guide"]):
            signals.append(IntentSignal(
                type=IntentType.RESEARCH_INTENT,
                confidence=0.70,
                url=url,
                timestamp=datetime.utcnow(),
                metadata={"source": "url_pattern", "keywords": ["article", "learn"]}
            ))

        return signals


class BrowserAgent:
    """
    AI Browser Agent for collecting web browsing intent signals

    Uses Playwright for browser automation and Qwen for intent analysis.
    """

    def __init__(self, qwen_client: QwenClient):
        self.qwen = qwen_client
        self.browser: Optional[Browser] = None
        self.collected_signals: list[IntentSignal] = []
        logger.info("Initialized Browser Agent")

    async def start(self, headless: bool = True):
        """Start the browser"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=headless)
        logger.info(f"Browser started (headless={headless})")

    async def stop(self):
        """Stop the browser"""
        if self.browser:
            await self.browser.close()
            logger.info("Browser stopped")

    async def navigate_and_analyze(self, url: str) -> list[IntentSignal]:
        """
        Navigate to a URL and analyze for intent signals
        """
        if not self.browser:
            raise RuntimeError("Browser not started. Call start() first.")

        page = await self.browser.new_page()

        try:
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Get page content for analysis
            content = await page.content()
            title = await page.title()

            logger.info(f"Page loaded: {title}")

            # Analyze with Qwen
            signals = await self.qwen.analyze_page(content, url)

            # Store collected signals
            self.collected_signals.extend(signals)

            logger.info(f"Detected {len(signals)} intent signals")
            return signals

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
        """
        Create a data segment from collected signals
        """
        # Filter signals by type and confidence
        filtered_signals = [
            s for s in self.collected_signals
            if s.type == segment_type
            and confidence_min <= s.confidence <= confidence_max
        ]

        # Filter by time window
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
            "agent_version": "1.0.0"
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported {len(segments)} segments to {filepath}")


async def main():
    """Example usage of the browser agent"""

    # Initialize components
    qwen = QwenClient()
    agent = BrowserAgent(qwen)

    try:
        # Start browser
        await agent.start(headless=True)

        # Example URLs to analyze
        urls = [
            "https://example.com/products/laptop",
            "https://example.com/compare/laptops",
            "https://example.com/blog/buying-guide",
        ]

        # Browse and collect signals
        signals = await agent.browse_urls(urls)
        print(f"\nCollected {len(signals)} total signals")

        # Create data segments
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

        # Export for marketplace
        if segments:
            agent.export_segments(segments, "segments_output.json")

            print("\n=== Created Segments ===")
            for segment in segments:
                print(f"  {segment.segment_id}: {len(segment.signals)} signals")

    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
