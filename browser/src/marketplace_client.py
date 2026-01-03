"""
PAT Marketplace API Client

This module provides a client for submitting data segments to the PAT
marketplace for listing and trading.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class MarketplaceClient:
    """
    Client for the PAT Data Performance Marketplace API

    Handles authentication, segment submission, and marketplace interactions.
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """
        Initialize the marketplace client

        Args:
            api_base: Marketplace API base URL
            api_key: API key for authentication
        """
        self.api_base = api_base or os.getenv(
            "PAT_MARKETPLACE_API",
            "https://api.pat-marketplace.io/v1"
        )
        self.api_key = api_key or os.getenv("PAT_MARKETPLACE_KEY")

        self.client = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}" if self.api_key else ""
            }
        )

    async def submit_segment(self, segment: dict) -> dict:
        """
        Submit a data segment to the marketplace

        Args:
            segment: Segment data dictionary

        Returns:
            API response with segment ID and listing status
        """
        try:
            response = await self.client.post(
                "/segments",
                json={
                    "segment": segment,
                    "submitted_at": datetime.utcnow().isoformat()
                }
            )

            if response.status_code == 201:
                result = response.json()
                logger.info(f"Segment submitted: {result.get('segment_id')}")
                return result

            logger.error(f"Segment submission failed: {response.status_code}")
            return {"error": response.text, "status": response.status_code}

        except httpx.HTTPError as e:
            logger.error(f"Marketplace API error: {e}")
            return {"error": str(e)}

    async def submit_batch(self, segments: list[dict]) -> dict:
        """
        Submit multiple segments in a batch

        Args:
            segments: List of segment dictionaries

        Returns:
            Batch submission result
        """
        try:
            response = await self.client.post(
                "/segments/batch",
                json={
                    "segments": segments,
                    "submitted_at": datetime.utcnow().isoformat()
                }
            )

            if response.status_code in (200, 201):
                result = response.json()
                logger.info(f"Batch submitted: {len(segments)} segments")
                return result

            return {"error": response.text, "status": response.status_code}

        except httpx.HTTPError as e:
            logger.error(f"Batch submission error: {e}")
            return {"error": str(e)}

    async def get_segment_status(self, segment_id: str) -> dict:
        """
        Get the status of a submitted segment

        Args:
            segment_id: The segment identifier

        Returns:
            Segment status and pricing information
        """
        try:
            response = await self.client.get(f"/segments/{segment_id}")

            if response.status_code == 200:
                return response.json()

            return {"error": "Segment not found", "status": response.status_code}

        except httpx.HTTPError as e:
            logger.error(f"Get segment error: {e}")
            return {"error": str(e)}

    async def get_pricing(self, segment_type: str, time_window: int) -> dict:
        """
        Get current pricing for a segment type

        Args:
            segment_type: Type of intent signal
            time_window: Time window in days

        Returns:
            Current bid/ask prices and volume
        """
        try:
            response = await self.client.get(
                "/pricing",
                params={
                    "type": segment_type,
                    "window": time_window
                }
            )

            if response.status_code == 200:
                return response.json()

            return {"error": "Pricing not available"}

        except httpx.HTTPError as e:
            logger.error(f"Get pricing error: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class LocalStorageClient:
    """
    Local storage client for development/testing

    Stores segments to local JSON files instead of the marketplace API.
    """

    def __init__(self, storage_dir: str = "./segment_storage"):
        """
        Initialize local storage

        Args:
            storage_dir: Directory to store segment files
        """
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    async def submit_segment(self, segment: dict) -> dict:
        """Save segment to local storage"""
        segment_id = segment.get("segment_id", f"segment_{datetime.utcnow().timestamp()}")
        filepath = os.path.join(self.storage_dir, f"{segment_id}.json")

        with open(filepath, "w") as f:
            json.dump({
                "segment": segment,
                "stored_at": datetime.utcnow().isoformat(),
                "status": "stored_locally"
            }, f, indent=2)

        logger.info(f"Segment stored locally: {filepath}")
        return {"segment_id": segment_id, "filepath": filepath, "status": "stored"}

    async def submit_batch(self, segments: list[dict]) -> dict:
        """Save multiple segments"""
        results = []
        for segment in segments:
            result = await self.submit_segment(segment)
            results.append(result)

        return {"submitted": len(results), "results": results}

    async def get_segment_status(self, segment_id: str) -> dict:
        """Get segment from local storage"""
        filepath = os.path.join(self.storage_dir, f"{segment_id}.json")

        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)

        return {"error": "Segment not found"}

    async def close(self):
        """No-op for local storage"""
        pass
