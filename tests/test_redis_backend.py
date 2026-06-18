import fakeredis
import pytest

from fastlimit.algorithms import Algorithm
from fastlimit.backends.redis import RedisBackend
from fastlimit.rules import BucketConfig

BUCKET = BucketConfig(window_sec=60, limit=5)


def make_backend(algorithm: Algorithm = Algorithm.SLIDING_WINDOW) -> RedisBackend:
    # version=(7,0,0) enables Lua scripting support via lupa
    client = fakeredis.FakeAsyncRedis(version=(7, 0, 0))
    return RedisBackend(client, algorithm=algorithm)


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_allows_within_limit(algorithm):
    backend = make_backend(algorithm)
    for _ in range(5):
        result = await backend.check_and_increment("test:ip:1.2.3.4", BUCKET, cost=1)
        assert result.allowed, f"{algorithm}: should be allowed"


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_blocks_over_limit(algorithm):
    backend = make_backend(algorithm)
    for _ in range(5):
        await backend.check_and_increment("test:ip:1.2.3.4", BUCKET, cost=1)
    result = await backend.check_and_increment("test:ip:1.2.3.4", BUCKET, cost=1)
    assert not result.allowed, f"{algorithm}: should be blocked"
    assert result.retry_after_ms > 0


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_remaining_decrements(algorithm):
    backend = make_backend(algorithm)
    r1 = await backend.check_and_increment("test:ip:2.2.2.2", BUCKET, cost=1)
    assert r1.remaining == 4
    r2 = await backend.check_and_increment("test:ip:2.2.2.2", BUCKET, cost=1)
    assert r2.remaining == 3


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_different_keys_independent(algorithm):
    backend = make_backend(algorithm)
    for _ in range(5):
        await backend.check_and_increment("test:ip:1.1.1.1", BUCKET, cost=1)
    result = await backend.check_and_increment("test:ip:2.2.2.2", BUCKET, cost=1)
    assert result.allowed


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_cost_consumes_multiple_slots(algorithm):
    backend = make_backend(algorithm)
    result = await backend.check_and_increment("test:ip:3.3.3.3", BUCKET, cost=3)
    assert result.allowed
    assert result.remaining == 2
    result = await backend.check_and_increment("test:ip:3.3.3.3", BUCKET, cost=3)
    assert not result.allowed


async def test_reset_clears_key():
    backend = make_backend()
    for _ in range(5):
        await backend.check_and_increment("test:ip:4.4.4.4", BUCKET, cost=1)
    await backend.reset("test:ip:4.4.4.4")
    result = await backend.check_and_increment("test:ip:4.4.4.4", BUCKET, cost=1)
    assert result.allowed


async def test_result_fields_present():
    backend = make_backend()
    result = await backend.check_and_increment("test:fields", BUCKET, cost=1)
    assert result.allowed is True
    assert result.limit == 5
    assert isinstance(result.remaining, int)
    assert result.reset_ms > 0
    assert result.retry_after_ms == 0


async def test_blocked_result_fields():
    backend = make_backend()
    for _ in range(5):
        await backend.check_and_increment("test:blocked", BUCKET, cost=1)
    result = await backend.check_and_increment("test:blocked", BUCKET, cost=1)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after_ms > 0
    assert result.reset_ms > 0
