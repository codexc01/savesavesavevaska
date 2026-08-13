"""Phase 14 tests — Redis caching & queue layer with graceful fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.cache import (
    cache_message_quick,
    get_cached_message_quick,
    is_update_processed,
)


class TestRedisFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_redis_client_none(self):
        with patch("app.services.cache.get_redis_client", return_value=None):
            assert await is_update_processed(12345) is False

            cached_ok = await cache_message_quick("bc_1400", 11, 22, {"text": "hello"})
            assert cached_ok is False

            cached_msg = await get_cached_message_quick("bc_1400", 11, 22)
            assert cached_msg is None


class TestRedisCacheMocked:
    @pytest.mark.asyncio
    async def test_cache_and_get_message(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        mock_redis.get.return_value = '{"text": "cached data"}'

        with patch("app.services.cache.get_redis_client", return_value=mock_redis):
            cached_ok = await cache_message_quick("bc_1400", 11, 22, {"text": "cached data"})
            assert cached_ok is True
            mock_redis.set.assert_awaited_once()

            data = await get_cached_message_quick("bc_1400", 11, 22)
            assert data is not None
            assert data["text"] == "cached data"
            mock_redis.get.assert_awaited_once()
