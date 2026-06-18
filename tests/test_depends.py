import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fastlimit import FastLimit, rate_limit
from fastlimit.backends.memory import MemoryBackend


def make_app(dep, user_id_func=None, dry_run=False):
    backend = MemoryBackend()
    limiter = FastLimit(backend=backend, user_id_func=user_id_func, dry_run=dry_run)
    app = FastAPI()
    limiter.init_app(app)

    @app.get("/test", dependencies=[dep])
    async def test_route():
        return {"ok": True}

    return app


async def test_allows_within_limit():
    app = make_app(rate_limit("5/min"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            r = await client.get("/test")
            assert r.status_code == 200


async def test_blocks_over_limit():
    app = make_app(rate_limit("3/min"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            await client.get("/test")
        r = await client.get("/test")
        assert r.status_code == 429
        assert "retry_after" in r.json()


async def test_headers_present():
    app = make_app(rate_limit("10/min"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/test")
        assert "x-ratelimit-limit" in r.headers
        assert "x-ratelimit-remaining" in r.headers
        assert "x-ratelimit-reset" in r.headers


async def test_retry_after_header_on_429():
    app = make_app(rate_limit("1/min"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/test")
        r = await client.get("/test")
        assert r.status_code == 429
        assert "retry-after" in r.headers


async def test_dry_run_never_blocks():
    app = make_app(rate_limit("1/min"), dry_run=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(10):
            r = await client.get("/test")
            assert r.status_code == 200


async def test_exempt_ip():
    backend = MemoryBackend()
    # httpx ASGITransport always presents as 127.0.0.1
    limiter = FastLimit(backend=backend, exempt_ips={"127.0.0.1"})
    app = FastAPI()
    limiter.init_app(app)

    @app.get("/test", dependencies=[rate_limit("1/min")])
    async def test_route():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            r = await client.get("/test")
            assert r.status_code == 200


async def test_dual_bucket_user_limit():
    """Authenticated users hit the user bucket, not the IP bucket."""

    def get_user(req):
        return req.headers.get("X-User-ID")

    # IP limit is strict (2/min), user limit is generous (20/min)
    app = make_app(rate_limit(ip="2/min", user="20/min"), user_id_func=get_user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-User-ID": "user_abc"}
        # authenticated user should NOT be blocked by the strict IP limit
        for _ in range(5):
            r = await client.get("/test", headers=headers)
            assert r.status_code == 200, "authenticated user hit IP bucket — bucket logic is wrong"


async def test_anonymous_hits_ip_bucket():
    """Anonymous requests (no user_id) fall back to the IP bucket."""

    def get_user(req):
        return req.headers.get("X-User-ID")

    app = make_app(rate_limit(ip="2/min", user="20/min"), user_id_func=get_user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # no X-User-ID header → anonymous → IP bucket (limit 2)
        await client.get("/test")
        await client.get("/test")
        r = await client.get("/test")
        assert r.status_code == 429


async def test_user_bucket_limit_enforced():
    """User bucket limit is still enforced for authenticated users."""

    def get_user(req):
        return req.headers.get("X-User-ID")

    app = make_app(rate_limit(ip="100/min", user="2/min"), user_id_func=get_user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-User-ID": "user_abc"}
        await client.get("/test", headers=headers)
        await client.get("/test", headers=headers)
        r = await client.get("/test", headers=headers)
        assert r.status_code == 429


async def test_no_init_app_raises():
    """FastLimitNotInitialized should propagate as an unhandled 500."""

    from fastlimit.exceptions import FastLimitNotInitialized

    app = FastAPI()

    @app.get("/test", dependencies=[rate_limit("10/min")])
    async def test_route():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with pytest.raises(FastLimitNotInitialized):
            await client.get("/test")
