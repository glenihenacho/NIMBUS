"""
Router Client for PAT Browser Agent

Replaces the simple Qwen client with calls to the intent detection router.
"""

import asyncio
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RouterClient:
    """
    Client for the Intent Detection Router Service.

    This replaces QwenAPIClient with a more sophisticated inference pipeline:
    - Cheap classifier (Rasa/Mistral)
    - Confidence gating
    - Escalation to DeepSeek when needed
    """

    def __init__(
        self,
        router_endpoint: str = "http://localhost:8000",
        timeout: float = 30.0
    ):
        self.router_endpoint = router_endpoint
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        logger.info(f"RouterClient initialized: {router_endpoint}")

    async def infer_intent(
        self,
        session_id: str,
        events: List[Dict[str, Any]],
        force_escalation: bool = False
    ) -> Dict[str, Any]:
        """
        Send browsing events to router for intent classification.

        Args:
            session_id: Session identifier
            events: List of browsing event dictionaries
            force_escalation: Force escalation to DeepSeek (for testing)

        Returns:
            Router inference response with decision and metadata
        """
        try:
            # Convert events to router format
            formatted_events = self._format_events(session_id, events)

            # Call router API
            response = await self.client.post(
                f"{self.router_endpoint}/infer",
                json={
                    "session_id": session_id,
                    "events": formatted_events,
                    "force_escalation": force_escalation
                }
            )
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"Intent inference complete: session={session_id}, "
                f"intent={result['decision']['intent']}, "
                f"confidence={result['decision']['confidence']:.2f}, "
                f"escalated={result['decision']['was_escalated']}"
            )

            return result

        except httpx.HTTPError as e:
            logger.error(f"Router API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Intent inference failed: {e}")
            raise

    async def analyze_page_content(
        self,
        url: str,
        content: str,
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Analyze page content for intent signals.

        This method provides backward compatibility with the old QwenAPIClient.

        Args:
            url: Page URL
            content: HTML content
            session_id: Session identifier

        Returns:
            Dictionary with intents array (backward compatible format)
        """
        # Create a single page_view event
        events = [{
            "event_type": "page_view",
            "url": url,
            "timestamp": datetime.utcnow().isoformat(),
            "properties": {
                "content_length": len(content),
                "has_content": bool(content.strip())
            }
        }]

        # Get router inference
        result = await self.infer_intent(session_id, events)

        # Convert to old format for backward compatibility
        decision = result["decision"]
        return {
            "intents": [
                {
                    "type": decision["intent"],
                    "confidence": decision["confidence"],
                    "evidence": f"Router decision (was_escalated={decision['was_escalated']})"
                }
            ],
            "metadata": {
                "was_escalated": decision["was_escalated"],
                "model_used": decision["model_used"],
                "total_latency_ms": result["total_latency_ms"]
            }
        }

    def _format_events(
        self,
        session_id: str,
        events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Format events for router API.

        Ensures all required fields are present and properly formatted.
        """
        formatted = []

        for event in events:
            formatted_event = {
                "event_id": event.get("event_id", self._generate_event_id()),
                "session_id": session_id,
                "user_id_hash": event.get("user_id_hash", "anonymous"),
                "event_type": event.get("event_type", "unknown"),
                "url": event.get("url"),
                "url_hash": event.get("url_hash"),
                "timestamp": event.get("timestamp", datetime.utcnow().isoformat()),
                "properties": event.get("properties", {})
            }
            formatted.append(formatted_event)

        return formatted

    def _generate_event_id(self) -> str:
        """Generate a unique event ID"""
        from uuid import uuid4
        return str(uuid4())

    async def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        try:
            response = await self.client.get(f"{self.router_endpoint}/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get router stats: {e}")
            return {}

    async def health_check(self) -> bool:
        """Check if router is healthy"""
        try:
            response = await self.client.get(f"{self.router_endpoint}/health")
            response.raise_for_status()
            result = response.json()
            return result.get("status") == "healthy"
        except:
            return False

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
        logger.info("RouterClient closed")


# Example usage with browser agent
async def example_usage():
    """Example of using RouterClient with browser agent"""
    from .agent import BrowserAgent

    # Initialize router client (instead of QwenAPIClient)
    router = RouterClient(router_endpoint="http://localhost:8000")

    # Check health
    if not await router.health_check():
        print("⚠ Router service is not healthy!")
        return

    # Initialize browser agent with router client
    agent = BrowserAgent(router)  # Pass router instead of qwen_client

    try:
        await agent.start(headless=True)

        # Example URLs
        urls = [
            "https://amazon.com/laptop",
            "https://amazon.com/laptop-reviews",
            "https://amazon.com/cart"
        ]

        # Browse and collect signals
        signals = await agent.browse_urls(urls)
        print(f"\nCollected {len(signals)} signals")

        # Create segments
        segments = []
        for intent_type in ["PURCHASE_INTENT", "RESEARCH_INTENT", "COMPARISON_INTENT"]:
            segment = agent.create_segment(
                segment_type=intent_type,
                time_window_days=7,
                confidence_min=0.70,
                confidence_max=0.90
            )
            if segment.signals:
                segments.append(segment)

        print(f"\nCreated {len(segments)} segments")

        # Get router stats
        stats = await router.get_stats()
        print(f"\nRouter stats: {stats}")

    finally:
        await agent.stop()
        await router.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
