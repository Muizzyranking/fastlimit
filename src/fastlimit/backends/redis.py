"""
Redis backend using Lua scripts for atomic rate limiting.

Supports all three algorithms via dedicated Lua scripts.
Requires the ``redis`` extra: ``pip install fastlimit[redis]``.

Good for:
- Multi-process / multi-worker deployments
- Persistent limits across restarts
- High-throughput production systems

Example::

    from fastlimit.backends.redis import RedisBackend
    from fastlimit import FastLimit

    limiter = FastLimit(redis_url="redis://localhost:6379")
"""

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastlimit.algorithms import Algorithm
from fastlimit.backends import BackendResult
from fastlimit.rules import BucketConfig

if TYPE_CHECKING:
    from redis.asyncio import Redis

_LUA_DIR = Path(__file__).parent.parent / "lua"

_LUA_FILES: dict[Algorithm, Path] = {
    Algorithm.SLIDING_WINDOW: _LUA_DIR / "sliding_window.lua",
    Algorithm.FIXED_WINDOW: _LUA_DIR / "fixed_window.lua",
    Algorithm.TOKEN_BUCKET: _LUA_DIR / "token_bucket.lua",
}


class RedisBackend:
    """
    Redis-backed rate limiter using atomic Lua scripts.

    Args:
        client: An async ``redis.asyncio.Redis`` client instance.
        algorithm: Which algorithm to use. Defaults to
            :attr:`~fastlimit.Algorithm.SLIDING_WINDOW`.
        key_prefix: Prefix for all Redis keys.

    Raises:
        ImportError: If the ``redis`` package is not installed.
    """

    def __init__(
        self,
        client: "Redis",
        algorithm: Algorithm = Algorithm.SLIDING_WINDOW,
        key_prefix: str = "fastlimit",
    ) -> None:
        try:
            import redis.asyncio  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "Redis support requires the 'redis' package. "
                "Install it with: pip install fastlimit[redis]"
            ) from e

        self._client = client
        self._algorithm = algorithm
        self._prefix = key_prefix
        self._scripts: dict[Algorithm, str] = {}

    def _get_lua(self, algorithm: Algorithm) -> str:
        if algorithm not in self._scripts:
            self._scripts[algorithm] = _LUA_FILES[algorithm].read_text()
        return self._scripts[algorithm]

    async def check_and_increment(
        self,
        key: str,
        bucket: BucketConfig,
        cost: int,
    ) -> BackendResult:
        full_key = f"{self._prefix}:{key}"
        now_ms = int(time.time() * 1000)
        window_ms = bucket.window_sec * 1000
        lua = self._get_lua(self._algorithm)

        argv: list[int | str]
        if self._algorithm == Algorithm.SLIDING_WINDOW:
            argv = [now_ms, window_ms, bucket.limit, cost, os.urandom(8).hex()]
        elif self._algorithm == Algorithm.FIXED_WINDOW:
            argv = [now_ms, bucket.window_sec, bucket.limit, cost]
        else:
            argv = [now_ms, window_ms, bucket.limit, cost]

        result = await self._client.eval(lua, 1, full_key, *argv)

        allowed = int(result[0]) == 1
        retry_after_ms = int(result[1])
        reset_ms = int(result[2])
        remaining = int(result[3])
        limit_val = int(result[4])

        return BackendResult(
            allowed=allowed,
            limit=limit_val,
            remaining=remaining,
            reset_ms=reset_ms,
            retry_after_ms=retry_after_ms,
        )

    async def reset(self, key: str) -> None:
        """Delete a single bucket key from Redis."""
        await self._client.delete(f"{self._prefix}:{key}")

    async def clear_all(self, pattern: str | None = None) -> None:
        """
        Delete all fastlimit keys matching a pattern.
        """
        match = pattern or f"{self._prefix}:*"
        async for key in self._client.scan_iter(match=match):
            await self._client.delete(key)
