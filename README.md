# fastlimit

Rate limiting for FastAPI with clean route signatures, IP/user-aware buckets,
pluggable backends, and automatic rate limit headers.

```python
from fastapi import FastAPI
from fastlimit import FastLimit, rate_limit

app = FastAPI()

limiter = FastLimit(
    redis_url="redis://localhost:6379",  # omit for the in-memory backend
    user_id_func=lambda request: getattr(request.state, "user_id", None),
)
limiter.init_app(app)


@app.post("/upload", dependencies=[rate_limit(ip="10/min", user="50/min")])
async def upload():
    return {"ok": True}
```

No `Request` parameter is required in your route handler, and your handler can
keep returning normal FastAPI values such as dictionaries, Pydantic models, or
responses.

## Why fastlimit?

Many FastAPI rate limiters make rate limiting visible in every route signature
or only give you one simple bucket per endpoint. fastlimit is built for APIs
that need anonymous and authenticated traffic to be treated differently without
leaking that plumbing into application code.

With `rate_limit(ip="10/min", user="50/min")`, anonymous requests are limited by
client IP and authenticated requests are limited by the user ID returned from
`user_id_func`.

## Features

- FastAPI dependency API: `dependencies=[rate_limit("10/min")]`
- Decorator API: `@limit("10/min")`
- No forced `Request` argument in route functions
- IP and authenticated-user buckets
- In-memory backend for development and tests
- Redis backend for multi-worker production deployments
- Sliding window, fixed window, and token bucket algorithms
- Automatic `X-RateLimit-*` and `Retry-After` headers
- Custom header names and custom 429 responses
- Request cost support for expensive endpoints
- Dry-run mode for observing limits before enforcement
- Exempt IPs and trusted proxy support
- Typed package (`py.typed`)

## Installation

```bash
pip install fastlimit
```

For Redis-backed limits:

```bash
pip install "fastlimit[redis]"
```

With `uv`:

```bash
uv add fastlimit
uv add "fastlimit[redis]"
```

## Quickstart

Create and register one limiter for your FastAPI app:

```python
from fastapi import FastAPI
from fastlimit import FastLimit

app = FastAPI()

limiter = FastLimit(
    # Use Redis in production. Omit redis_url for the in-memory backend.
    redis_url="redis://localhost:6379",

    # Return a stable user ID for authenticated requests, or None for anonymous.
    user_id_func=lambda request: getattr(request.state, "user_id", None),
)
limiter.init_app(app)
```

Add limits to routes:

```python
from fastapi import APIRouter
from fastlimit import rate_limit

router = APIRouter()


@router.post("/register", dependencies=[rate_limit("10/min")])
async def register():
    return {"ok": True}


@router.post("/upload", dependencies=[rate_limit(ip="5/min", user="50/min")])
async def upload():
    return {"ok": True}
```

The shorthand `rate_limit("10/min")` is equivalent to
`rate_limit(ip="10/min")`.

## Decorator style

If you prefer decorators:

```python
from fastlimit import limit


@router.get("/feed")
@limit("100/min")
async def feed():
    return {"items": []}
```

The decorator injects a hidden FastAPI dependency, so the route function still
does not need a `Request` parameter.

## Rate strings

Rate strings use the format `limit/window`:

```python
rate_limit("5/s")
rate_limit("10/min")
rate_limit("100/hour")
rate_limit("1000/day")
rate_limit("3/5min")
```

Supported units include seconds, minutes, hours, and days, with common aliases
such as `s`, `sec`, `min`, `hour`, and `day`.

## Backends

fastlimit ships with two backends:

- `MemoryBackend`, used by default, stores counters in the current Python
  process. It is useful for development, tests, and single-process apps.
- `RedisBackend`, enabled with `redis_url`, shares counters across workers and
  should be used for multi-process or production deployments.

```python
from fastlimit import FastLimit

limiter = FastLimit()  # in-memory
limiter = FastLimit(redis_url="redis://localhost:6379")  # Redis
```

Custom backends can be passed with `FastLimit(backend=...)` by implementing the
`fastlimit.backends.Backend` protocol.

## Algorithms

Choose the algorithm when creating the limiter:

```python
from fastlimit import Algorithm, FastLimit

FastLimit(algorithm=Algorithm.SLIDING_WINDOW)  # default
FastLimit(algorithm=Algorithm.FIXED_WINDOW)
FastLimit(algorithm=Algorithm.TOKEN_BUCKET)
```

- `SLIDING_WINDOW`: best default for most APIs; smooth rolling windows.
- `FIXED_WINDOW`: simple counters with fixed reset boundaries.
- `TOKEN_BUCKET`: allows short bursts while maintaining a long-term rate.

## Response headers

Allowed requests include:

```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1781736212
```

Blocked requests return HTTP 429 and include:

```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1781736212
Retry-After: 41
```

Header names can be customized with `HeaderConfig`, or disabled entirely.

## Advanced options

```python
from fastlimit import FastLimit, HeaderConfig

limiter = FastLimit(
    redis_url="redis://localhost:6379",
    key_prefix="my_api",
    headers=HeaderConfig(
        limit="RateLimit-Limit",
        remaining="RateLimit-Remaining",
        reset="RateLimit-Reset",
    ),
    exempt_ips={"127.0.0.1"},
    trusted_proxies=1,
    dry_run=False,
)
```

Individual routes can also set a request `cost`:

```python
@router.post("/export", dependencies=[rate_limit("100/hour", cost=10)])
async def export():
    ...
```

## Documentation

- Documentation: <https://fastlimit.muizzyranking.me>
- Repository: <https://github.com/muizzyranking/fastlimit>
- Issues: <https://github.com/muizzyranking/fastlimit/issues>

## Development

This project uses Python 3.11+ and `uv`.

```bash
uv sync --all-extras --dev
uv run pytest
uv run ruff check src tests
uv run mypy
```

Build the package:

```bash
uv build
```

Serve the docs locally:

```bash
uv run mkdocs serve
```

## License

MIT
