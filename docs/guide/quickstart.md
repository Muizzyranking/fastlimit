# Quickstart

Get rate limiting working in under 5 minutes.

## 1. Install

```bash
pip install fastlimit

# with Redis (recommended for production)
pip install "fastlimit[redis]"
```

## 2. Create a limiter

```python title="main.py"
from fastapi import FastAPI
from fastlimit import FastLimit

app = FastAPI()

limiter = FastLimit(
    # omit redis_url to use the in-memory backend (great for dev/testing)
    redis_url="redis://localhost:6379",

    # tells fastlimit how to find the logged-in user's ID on a request
    # return None for anonymous/unauthenticated requests
    user_id_func=lambda req: getattr(req.state, "user_id", None),
)

# registers the limiter on app.state + adds the 429 exception handler
limiter.init_app(app)
```

## 3. Add limits to routes

```python title="routes.py"
from fastapi import APIRouter
from fastlimit import rate_limit

router = APIRouter()

# Anonymous endpoint — limit by IP only
@router.post("/register", dependencies=[rate_limit("10/min")])
async def register():
    return {"ok": True}

# Authenticated endpoint — separate limits for IP and user
@router.post("/upload", dependencies=[rate_limit(ip="5/min", user="50/min")])
async def upload():
    return {"file": "uploaded"}
```

That's it. No `Request` in your function signatures. No middleware setup. Headers are injected automatically.

---

## What you get out of the box

**On every allowed request:**
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1781736212
```

**On a blocked request (429):**
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1781736212
Retry-After: 41
```

```json
{"detail": "Rate limit exceeded. Try again in 41s.", "retry_after": 41}
```

---

## Using the decorator style

If you prefer decorators over `dependencies=[]`:

```python
from fastlimit import limit

@router.get("/feed")
@limit("100/min")
async def feed():
    return {"items": []}
```

!!! warning "Async only"
    The `@limit` decorator only works with `async def` routes. For sync routes,
    use `dependencies=[rate_limit(...)]` instead.

---

---

## Testing without Redis

The default in-memory backend works with no config at all:

```python
limiter = FastLimit()   # in-memory, zero deps
limiter.init_app(app)
```

This is perfect for development and unit tests. Just swap in `redis_url` for production.
