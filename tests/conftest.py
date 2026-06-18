import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fastlimit import FastLimit, rate_limit
from fastlimit.backends.memory import MemoryBackend


def build_app(limiter: FastLimit | None = None, route_dep=None) -> FastAPI:
    app = FastAPI()
    lim = limiter or FastLimit()
    lim.init_app(app)

    dep = route_dep or rate_limit("100/min")

    @app.get("/test", dependencies=[dep])
    async def test_route():
        return {"ok": True}

    return app


@pytest.fixture
def memory_backend():
    return MemoryBackend()


@pytest.fixture
def limiter(memory_backend):
    return FastLimit(backend=memory_backend)


@pytest.fixture
def app(limiter):
    return build_app(limiter)


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
