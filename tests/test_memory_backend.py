import asyncio

import pytest

from fastlimit.backends.memory import MemoryBackend
from fastlimit.rules import BucketConfig

BUCKET = BucketConfig(window_sec=60, limit=5)


@pytest.fixture
def backend():
    return MemoryBackend()


async def test_allows_within_limit(backend):
    for _ in range(5):
        result = await backend.check_and_increment("test:ip:1.2.3.4", BUCKET, cost=1)
        assert result.allowed


async def test_blocks_over_limit(backend):
    for _ in range(5):
        await backend.check_and_increment("test:ip:1.2.3.4", BUCKET, cost=1)

    result = await backend.check_and_increment("test:ip:1.2.3.4", BUCKET, cost=1)
    assert not result.allowed
    assert result.retry_after_ms > 0


async def test_remaining_decrements(backend):
    r1 = await backend.check_and_increment("test:ip:2.2.2.2", BUCKET, cost=1)
    assert r1.remaining == 4

    r2 = await backend.check_and_increment("test:ip:2.2.2.2", BUCKET, cost=1)
    assert r2.remaining == 3


async def test_different_keys_are_independent(backend):
    for _ in range(5):
        await backend.check_and_increment("test:ip:1.1.1.1", BUCKET, cost=1)

    result = await backend.check_and_increment("test:ip:2.2.2.2", BUCKET, cost=1)
    assert result.allowed


async def test_cost_consumes_multiple_slots(backend):
    result = await backend.check_and_increment("test:ip:3.3.3.3", BUCKET, cost=3)
    assert result.allowed
    assert result.remaining == 2

    result = await backend.check_and_increment("test:ip:3.3.3.3", BUCKET, cost=3)
    assert not result.allowed


async def test_reset_clears_key(backend):
    for _ in range(5):
        await backend.check_and_increment("test:ip:4.4.4.4", BUCKET, cost=1)

    await backend.reset("test:ip:4.4.4.4")
    result = await backend.check_and_increment("test:ip:4.4.4.4", BUCKET, cost=1)
    assert result.allowed


async def test_clear_all(backend):
    await backend.check_and_increment("test:ip:a", BUCKET, cost=1)
    await backend.check_and_increment("test:ip:b", BUCKET, cost=1)
    await backend.clear_all()

    result = await backend.check_and_increment("test:ip:a", BUCKET, cost=1)
    assert result.remaining == 4  # full bucket again


async def test_concurrent_requests_no_race(backend):
    bucket = BucketConfig(window_sec=60, limit=10)
    results = await asyncio.gather(
        *[backend.check_and_increment("test:concurrent", bucket, cost=1) for _ in range(15)]
    )
    allowed = sum(1 for r in results if r.allowed)
    blocked = sum(1 for r in results if not r.allowed)
    assert allowed == 10
    assert blocked == 5
