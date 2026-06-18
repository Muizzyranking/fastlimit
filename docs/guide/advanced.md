# Advanced Usage

## Dry run mode

Evaluate limits without enforcing them. Useful for observing impact before enabling rate limiting in production.

```python
limiter = FastLimit(dry_run=True)
```

When a request would be blocked, fastlimit logs a warning instead of returning 429:

```
WARNING fastlimit [DRY RUN]: would have blocked 1.2.3.4 — retry after 41s.
```

---

## Exempt IPs

Skip rate limiting for specific IPs — useful for internal health checks or trusted callers:

```python
limiter = FastLimit(
    exempt_ips={"127.0.0.1", "10.0.0.1"},
)
```

---

## Request cost

Some endpoints are more expensive than others. `cost` lets you consume multiple slots per call:

```python
# export costs 10 slots — a user with 100/hour gets 10 exports per hour
@router.post("/export", dependencies=[rate_limit("100/hour", cost=10)])
async def export():
    ...
```

---

## Key prefix

If multiple apps share one Redis instance, set a unique prefix per app:

```python
limiter = FastLimit(
    redis_url="redis://localhost:6379",
    key_prefix="myapp_v2",
)
# keys look like: myapp_v2:login:ip:1.2.3.4
```

---

## Trusted proxies

When your app runs behind a reverse proxy (nginx, Cloudflare, a load balancer), the real client IP is in `X-Forwarded-For`, not `request.client.host`. `trusted_proxies` tells fastlimit how many proxy hops to trust.

```
Client → Cloudflare → nginx → your app
```

`X-Forwarded-For: 1.2.3.4, 172.16.0.1, 10.0.0.1`

With `trusted_proxies=2` (Cloudflare + nginx), fastlimit picks `1.2.3.4` — the real client IP.

```python
limiter = FastLimit(trusted_proxies=2)
```

| Value | Effect |
|---|---|
| `0` | Use `request.client.host` directly — no header parsing |
| `1` | Trust one proxy (default — works for most setups) |
| `2` | Trust two proxies (e.g. Cloudflare + nginx) |

!!! warning "Security"
    Setting `trusted_proxies` too high lets clients spoof their IP by
    adding fake entries to `X-Forwarded-For`. Set it to exactly the
    number of proxies between the internet and your app.

---

## Router-level limits

Apply a limit to every route under a router:

```python
from fastapi import APIRouter
from fastlimit import rate_limit

# every route in this router gets the limit
router = APIRouter(dependencies=[rate_limit("200/min")])
```

---

## App-level fallback

```python
app = FastAPI(dependencies=[rate_limit("500/min", name="global")])
```

---

## Applying both router and route limits

When a route has a router-level limit and its own limit, **both are checked independently**. The first one to block wins.

```python
router = APIRouter(dependencies=[rate_limit("200/min", name="router_global")])

@router.post("/upload", dependencies=[rate_limit(ip="5/min", user="50/min")])
async def upload():
    # checked: 200/min global, then 5/min IP + 50/min user
    ...
```

---

## `from_env()` (coming soon)

Load limiter config from environment variables:

```bash
FASTLIMIT_REDIS_URL=redis://localhost:6379
FASTLIMIT_ALGORITHM=sliding_window
FASTLIMIT_KEY_PREFIX=myapp
FASTLIMIT_DRY_RUN=false
```

```python
limiter = FastLimit.from_env()
```
