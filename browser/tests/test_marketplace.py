"""Unit tests for Marketplace Client"""

import pytest
import os
import json
import tempfile
import sys
sys.path.insert(0, '/home/user/NIMBUS/browser')

from src.marketplace_client import LocalStorageClient


class TestLocalStorageClient:
    """Tests for LocalStorageClient"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def client(self, temp_dir):
        """Create client with temp storage"""
        return LocalStorageClient(storage_dir=temp_dir)

    @pytest.mark.asyncio
    async def test_submit_segment(self, client, temp_dir):
        segment = {
            "segment_id": "PURCHASE_INTENT|7D|0.70-0.85",
            "segment_type": "PURCHASE_INTENT",
            "signal_count": 5
        }

        result = await client.submit_segment(segment)

        assert result["status"] == "stored"
        assert "segment_id" in result

        # Check file exists
        filepath = os.path.join(temp_dir, f"{segment['segment_id']}.json")
        assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_submit_batch(self, client):
        segments = [
            {"segment_id": "seg1", "type": "PURCHASE_INTENT"},
            {"segment_id": "seg2", "type": "RESEARCH_INTENT"},
        ]

        result = await client.submit_batch(segments)

        assert result["submitted"] == 2
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_get_segment_status(self, client):
        segment = {
            "segment_id": "test_segment",
            "data": "test"
        }

        await client.submit_segment(segment)
        status = await client.get_segment_status("test_segment")

        assert "segment" in status
        assert status["segment"]["segment_id"] == "test_segment"

    @pytest.mark.asyncio
    async def test_get_nonexistent_segment(self, client):
        status = await client.get_segment_status("nonexistent")
        assert "error" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
