# fastlimit

**Rate limiting for FastAPI.**

Separate IP and user buckets per endpoint. Pluggable backends. No forced `Request` in your function signature.

```python
from fastlimit import FastLimit, rate_limit

limiter = FastLimit(redis_url="redis://localhost:6379")
limiter.init_app(app)

# anonymous users: 10/min by IP
# authenticated users: 50/min by user ID — independent bucket
@router.post("/upload", dependencies=[rate_limit(ip="10/min", user="50/min")])
async def upload():
    return {"ok": True}
```

---

## Why fastlimit?

Most FastAPI rate limiters give you **one bucket** — either IP or user ID. That works for simple cases, but falls apart the moment you want to treat authenticated and anonymous traffic differently.

**fastlimit gives you two independent buckets per endpoint.**

An anonymous user hitting `/upload` might get 5 requests per minute. A logged-in user gets 50. The limits are tracked separately, enforced separately, and reported separately in response headers — with a single line of config and zero changes to your route function.

### What was frustrating about existing solutions

Before building fastlimit, the main alternative was [SlowAPI](https://github.com/laurents/slowapi). It works, but a few things stood out as friction:

**Forced `Request` in function signatures.** SlowAPI's decorator style requires you to add `request: Request` to every rate-limited route, even when your function has no other reason to touch the request object. This leaks infrastructure concerns into your business logic.

```python
# SlowAPI — you must add request: Request
@app.get("/items")
@limiter.limit("10/minute")
async def get_items(request: Request):   # <-- forced, even if unused
    return items
```

**Header injection forces `Response` return types.** SlowAPI can inject rate limit headers into responses, but when you enable it, every rate-limited route must return a `Response` object directly. You can't return a dict, a Pydantic model, or a list and have FastAPI serialize it — returning anything other than a `Response` breaks the header injection. So you end up choosing between clean return types or rate limit headers. Most people drop the headers and handle them manually.

**Single limit per endpoint.** There's no clean way to say "5/min for anonymous, 50/min for logged-in" — you get one bucket, and you have to implement the user/IP distinction yourself.

**fastlimit fixes all three.**

---

## Features

- **Dual buckets** — separate IP and user limits per endpoint, both optional
- **Clean API** — `dependencies=[rate_limit("10/min")]` or `@limit("10/min")`, your choice
- **No `Request` in your functions** — ever, in either style
- **Pluggable backends** — in-memory (default) or Redis, swap with one line
- **Three algorithms** — `"sliding_window"`, `"fixed_window"`, `"token_bucket"`
- **Full headers on all responses** — including 429s (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`)
- **Custom backends** — implement the `Backend` protocol and plug anything in
- **Dry run mode** — observe impact before enforcing in production
- **Exempt IPs** — skip rate limiting for health checks and internal callers
- **Request cost** — heavy endpoints can consume multiple slots per call

---

## Installation

```bash
# Basic (in-memory backend)
pip install fastlimit

# With Redis support
pip install "fastlimit[redis]"

# With uv
uv add fastlimit
uv add "fastlimit[redis]"
```

---

## At a glance

=== "dependencies=[] style"

    ```python
    from fastapi import APIRouter
    from fastlimit import rate_limit

    router = APIRouter()

    # IP-only — good for anonymous endpoints
    @router.post("/register", dependencies=[rate_limit("10/min")])
    async def register():
        return {"ok": True}

    # Dual bucket — good for authenticated endpoints
    @router.post("/upload", dependencies=[rate_limit(ip="5/min", user="50/min")])
    async def upload():
        return {"ok": True}

    # Use a preset
    async def login():
        return {"ok": True}
    ```

=== "@limit decorator style"

    ```python
    from fastapi import APIRouter
    from fastlimit import limit

    router = APIRouter()

    @router.get("/feed")
    @limit("100/min")
    async def feed():          # no Request needed
        return {"items": []}

    @router.post("/upload")
    @limit(ip="5/min", user="50/min")
    async def upload():
        return {"ok": True}
    ```

=== "App setup"

    ```python
    from fastapi import FastAPI
    from fastlimit import FastLimit

    app = FastAPI()

    limiter = FastLimit(
        redis_url="redis://localhost:6379",   # omit for in-memory
        user_id_func=lambda req: getattr(req.state, "user_id", None),
    )
    limiter.init_app(app)
    ```

---

## How it works

`rate_limit()` returns a FastAPI `Depends` object. When placed in `dependencies=[]`, FastAPI resolves it before your route handler runs — checking the limit, raising a 429 if exceeded, and injecting rate limit headers into the response automatically.

The limiter instance lives on `app.state`, so `rate_limit()` is a **standalone function** — no need to import your limiter in every route file.

```
request arrives
    │
    ▼
FastAPI resolves rate_limit() Depends
    │
    ├── reads limiter from app.state
    ├── resolves IP from X-Forwarded-For
    ├── resolves user_id via user_id_func
    ├── checks IP bucket  ──► blocked? → 429 + full headers
    ├── checks user bucket ─► blocked? → 429 + full headers
    └── injects X-RateLimit-* headers into response
    │
    ▼
your route handler runs
    │
    ▼
return dict / Pydantic model / anything
headers already set ✓
```
