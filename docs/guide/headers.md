# Headers

fastlimit injects rate limit headers into **every response** — both allowed and blocked.

## Default headers

**On allowed requests:**

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1781736212
```

**On blocked requests (429):**

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1781736212
Retry-After: 41
```

`X-RateLimit-Reset` is a Unix timestamp (seconds). `Retry-After` is seconds until the client can retry.

---

## How headers are injected

FastAPI provides a `Response` object as an injectable dependency — any dependency in the chain can add headers to it before the response is sent. fastlimit uses this to set `X-RateLimit-*` headers from inside the rate limit dependency, before your route handler even runs.

This means headers are set correctly regardless of what your route returns — `dict`, Pydantic model, `FileResponse`, `StreamingResponse`, anything. Your route function never needs to touch `Response` directly.

```python
# fastlimit does this internally — you never write this yourself
async def dependency(request: Request, response: Response):
    ...
    response.headers["X-RateLimit-Remaining"] = "7"
```

Because this happens at the dependency level (not middleware), FastAPI has already wired up the response object and any headers set on it will appear in the final response — no matter what the route handler returns.

---

## Customising header names

```python
from fastlimit import FastLimit, HeaderConfig

limiter = FastLimit(
    headers=HeaderConfig(
        limit="X-My-Limit",
        remaining="X-My-Remaining",
        reset="X-My-Reset",
        retry_after="Retry-After",
    )
)
```

IETF draft style:

```python
headers=HeaderConfig(
    limit="RateLimit-Limit",
    remaining="RateLimit-Remaining",
    reset="RateLimit-Reset",
)
```

## Disabling headers

```python
limiter = FastLimit(headers=HeaderConfig(enabled=False))
```

## Custom 429 response body

By default, blocked requests return:

```json
{"detail": "Rate limit exceeded. Try again in 41s.", "retry_after": 41}
```

To customise:

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from fastlimit import FastLimit, RateLimitExceeded

async def my_error_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": exc.detail,
            "retry_after_seconds": exc.retry_after,
        },
    )

limiter = FastLimit(error_handler=my_error_handler)
```

The `exc` object exposes: `exc.retry_after` (int), `exc.detail` (str), `exc.limit` (int | None), `exc.reset_ms` (int | None).
