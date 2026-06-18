from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fastlimit import FastLimit, limit
from fastlimit.backends.memory import MemoryBackend


def make_app(user_id_func=None):
    backend = MemoryBackend()
    limiter = FastLimit(backend=backend, user_id_func=user_id_func)
    app = FastAPI()
    limiter.init_app(app)
    return app, limiter


async def test_decorator_blocks_over_limit():
    app, _ = make_app()

    @app.get("/feed")
    @limit("3/min")
    async def feed():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            r = await client.get("/feed")
            assert r.status_code == 200
        r = await client.get("/feed")
        assert r.status_code == 429


async def test_decorator_headers_present():
    app, _ = make_app()

    @app.get("/feed")
    @limit("10/min")
    async def feed():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/feed")
        assert r.status_code == 200
        assert "x-ratelimit-limit" in r.headers
        assert "x-ratelimit-remaining" in r.headers


async def test_decorator_no_request_in_signature():
    """Route function must NOT need Request in its signature."""
    app, _ = make_app()

    @app.get("/simple")
    @limit("10/min")
    async def simple():
        # no Request parameter — this is the whole point
        return {"simple": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/simple")
        assert r.status_code == 200
        assert r.json() == {"simple": True}


async def test_decorator_dual_bucket():
    def get_user(req):
        return req.headers.get("X-User-ID")

    app, _ = make_app(user_id_func=get_user)

    @app.get("/upload")
    @limit(ip="100/min", user="2/min")
    async def upload():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-User-ID": "alice"}
        await client.get("/upload", headers=headers)
        await client.get("/upload", headers=headers)
        r = await client.get("/upload", headers=headers)
        assert r.status_code == 429


async def test_stacked_decorators():
    """Stacking @limit applies both rules independently."""
    app, _ = make_app()

    @app.get("/stacked")
    @limit("2/min", name="stacked_ip")
    async def stacked():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/stacked")
        await client.get("/stacked")
        r = await client.get("/stacked")
        assert r.status_code == 429


async def test_decorator_and_dependency_coexist():
    """@limit and dependencies=[] can coexist on the same route."""
    from fastlimit import rate_limit

    app, _ = make_app()

    @app.get("/mixed", dependencies=[rate_limit("100/min", name="mixed_global")])
    @limit("5/min", name="mixed_local")
    async def mixed():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/mixed")
        assert r.status_code == 200
