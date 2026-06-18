# Full App Example

A complete FastAPI application with authentication middleware, dual-bucket rate limiting, Redis backend, and custom error handling.

```python title="main.py"
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastlimit import FastLimit, HeaderConfig, RateLimitExceeded, Algorithm

app = FastAPI(title="My API")

# Custom 429 response
async def on_rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": exc.detail,
            "retry_after": exc.retry_after,
        },
        headers={"Retry-After": str(exc.retry_after)},
    )

limiter = FastLimit(
    redis_url="redis://localhost:6379",
    algorithm=Algorithm.SLIDING_WINDOW,
    user_id_func=lambda req: getattr(req.state, "user_id", None),
    headers=HeaderConfig(enabled=True),
    key_prefix="myapi",
    exempt_ips={"127.0.0.1"},   # skip health checks
    dry_run=False,
    trusted_proxies=1,
    error_handler=on_rate_limited,
)
limiter.init_app(app)

app.include_router(auth_router)
app.include_router(api_router)
```

```python title="middleware/auth.py"
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if token:
            # your real token validation here
            request.state.user_id = validate_token(token)
        else:
            request.state.user_id = None
        return await call_next(request)

app.add_middleware(AuthMiddleware)
```

```python title="routes/api.py"
from fastapi import APIRouter
from fastlimit import rate_limit, rule, limit
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["api"])

# Custom rule — inline
@router.get(
    "/photos",
    dependencies=[rate_limit(ip="30/min", user="200/min")],
)
async def list_photos():
    return {"photos": []}

# Custom rule — named and reusable
EXPORT_LIMIT = rule(ip="10/hour", user="50/hour", cost=5, name="export")

@router.post("/export", dependencies=[rate_limit(EXPORT_LIMIT)])
async def export_data():
    return {"export": "started"}

# Decorator style — async only
@router.get("/feed")
@limit(ip="60/min", user="300/min")
async def get_feed():
    # returns a Pydantic model — works fine, headers already injected
    return {"items": [], "page": 1}
```

---

## Running it

```bash
# start Redis
docker run -p 6379:6379 redis:alpine

# start the app
uvicorn main:app --reload
```

```bash
# test the limit
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code} " http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"a@b.com","password":"x"}'
done
# 200 200 200 200 200 429
```
