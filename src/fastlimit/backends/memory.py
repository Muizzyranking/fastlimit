"""
In-process memory backend using a sliding window.

Uses a sorted list of timestamps per key. An asyncio.Lock per key ensures
atomicity without blocking the event loop.

Good for:
- Development and testing
- Single-process deployments
- Environments without Redis

Not suitable for:
- Multi-process / multi-worker deployments (each worker has its own state)
- Persistent limits across restarts
"""

import asyncio
import time
from collections import defaultdict

from fastlimit.backends import BackendResult
from fastlimit.rules import BucketConfig


class MemoryBackend:
    """
    Sliding window rate limiter backed by in-process memory.

    .. warning::
        State is **not shared** across processes or workers. Use
        :class:`~fastlimit.backends.redis.RedisBackend` for multi-worker
        deployments.

    Args:
        key_prefix: Optional prefix for all keys. Useful when multiple
            limiter instances share one memory space.
    """

    def __init__(self, key_prefix: str = "fastlimit") -> None:
        self._prefix = key_prefix
        # key → sorted list of (timestamp_ms,) tuples
        self._windows: dict[str, list[int]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def check_and_increment(
        self,
        key: str,
        bucket: BucketConfig,
        cost: int,
    ) -> BackendResult:
        full_key = f"{self._prefix}:{key}"
        lock = self._locks[full_key]

        async with lock:
            now_ms = int(time.time() * 1000)
            window_ms = bucket.window_sec * 1000
            cutoff_ms = now_ms - window_ms

            timestamps = self._windows[full_key]

            # evict expired entries
            while timestamps and timestamps[0] <= cutoff_ms:
                timestamps.pop(0)

            count = len(timestamps)

            if count + cost > bucket.limit:
                # oldest entry tells us when a slot frees up
                oldest_ms = timestamps[0] if timestamps else now_ms
                retry_after_ms = max((oldest_ms + window_ms) - now_ms, 1000)
                return BackendResult(
                    allowed=False,
                    limit=bucket.limit,
                    remaining=0,
                    reset_ms=oldest_ms + window_ms,
                    retry_after_ms=retry_after_ms,
                )

            # record the request (one entry per cost unit)
            for _ in range(cost):
                timestamps.append(now_ms)

            remaining = bucket.limit - (count + cost)
            reset_ms = now_ms + window_ms

            return BackendResult(
                allowed=True,
                limit=bucket.limit,
                remaining=remaining,
                reset_ms=reset_ms,
            )

    async def reset(self, key: str) -> None:
        """Clear all recorded requests for a key. Useful in tests."""
        full_key = f"{self._prefix}:{key}"
        async with self._locks[full_key]:
            self._windows.pop(full_key, None)

    async def clear_all(self) -> None:
        """Clear all state. Useful in tests."""
        self._windows.clear()
        self._locks.clear()
