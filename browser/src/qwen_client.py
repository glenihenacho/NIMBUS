"""
Qwen API Client for Intent Signal Detection

This module provides a client for the Qwen LLM API to analyze web pages
and detect browsing intent signals.
"""

import json
import logging
import os
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class QwenAPIClient:
    """
    Production client for Qwen API

    Qwen is Alibaba's large language model. This client sends web page
    content to Qwen for analysis and receives structured intent signals.
    """

    # Qwen API endpoints
    QWEN_API_BASE = "https://dashscope.aliyuncs.com/api/v1"
    QWEN_CHAT_ENDPOINT = f"{QWEN_API_BASE}/services/aigc/text-generation/generation"

    # System prompt for intent detection
    INTENT_DETECTION_PROMPT = """You are an AI that analyzes web page content to detect user browsing intent signals.

Given a web page URL and content, identify any of the following intent types:
- PURCHASE_INTENT: User is looking to buy something (product pages, carts, checkout)
- RESEARCH_INTENT: User is researching or learning (articles, guides, documentation)
- COMPARISON_INTENT: User is comparing options (comparison tables, reviews, vs pages)
- ENGAGEMENT_INTENT: User is engaging with content (comments, forms, interactions)
- NAVIGATION_INTENT: User is navigating/exploring (category pages, search results)

For each detected intent, provide:
1. type: The intent type
2. confidence: A score from 0.0 to 1.0
3. evidence: What in the page indicates this intent

Respond in JSON format:
{
  "intents": [
    {
      "type": "PURCHASE_INTENT",
      "confidence": 0.85,
      "evidence": "Page contains add-to-cart button and product pricing"
    }
  ]
}
"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Qwen client

        Args:
            api_key: Qwen API key. If not provided, reads from QWEN_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("QWEN_API_KEY")
        if not self.api_key:
            logger.warning("No Qwen API key provided. Using mock responses.")

        self.client = httpx.AsyncClient(timeout=30.0)

    async def analyze_page_content(
        self,
        url: str,
        content: str,
        model: str = "qwen-turbo"
    ) -> dict:
        """
        Analyze page content using Qwen

        Args:
            url: The URL of the page
            content: The HTML content of the page (will be truncated if too long)
            model: Qwen model to use (qwen-turbo, qwen-plus, qwen-max)

        Returns:
            dict with detected intents
        """
        if not self.api_key:
            return self._mock_analysis(url, content)

        # Truncate content to avoid token limits
        max_content_length = 8000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "... [truncated]"

        user_message = f"""Analyze this web page for browsing intent signals:

URL: {url}

Content:
{content}

Identify all intent signals present in this page."""

        try:
            response = await self.client.post(
                self.QWEN_CHAT_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "input": {
                        "messages": [
                            {"role": "system", "content": self.INTENT_DETECTION_PROMPT},
                            {"role": "user", "content": user_message}
                        ]
                    },
                    "parameters": {
                        "temperature": 0.3,
                        "result_format": "message"
                    }
                }
            )

            response.raise_for_status()
            result = response.json()

            # Extract the assistant's response
            output_text = result.get("output", {}).get("text", "")

            # Parse JSON from response
            try:
                # Find JSON in the response
                json_start = output_text.find("{")
                json_end = output_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    return json.loads(output_text[json_start:json_end])
            except json.JSONDecodeError:
                logger.warning("Failed to parse Qwen response as JSON")

            return {"intents": []}

        except httpx.HTTPError as e:
            logger.error(f"Qwen API error: {e}")
            return {"intents": [], "error": str(e)}

    def _mock_analysis(self, url: str, content: str) -> dict:
        """
        Mock analysis when no API key is available

        Uses simple heuristics for development/testing.
        """
        intents = []

        url_lower = url.lower()
        content_lower = content.lower()

        # Purchase intent detection
        purchase_keywords = ["add to cart", "buy now", "checkout", "price", "shop"]
        if any(kw in url_lower or kw in content_lower for kw in purchase_keywords):
            intents.append({
                "type": "PURCHASE_INTENT",
                "confidence": 0.80,
                "evidence": "Page contains purchase-related keywords"
            })

        # Research intent detection
        research_keywords = ["article", "guide", "learn", "how to", "tutorial"]
        if any(kw in url_lower or kw in content_lower for kw in research_keywords):
            intents.append({
                "type": "RESEARCH_INTENT",
                "confidence": 0.75,
                "evidence": "Page contains educational content"
            })

        # Comparison intent detection
        comparison_keywords = ["compare", "vs", "versus", "review", "best"]
        if any(kw in url_lower or kw in content_lower for kw in comparison_keywords):
            intents.append({
                "type": "COMPARISON_INTENT",
                "confidence": 0.72,
                "evidence": "Page contains comparison content"
            })

        return {"intents": intents}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
