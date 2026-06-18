# Rules & Rate Strings

## Rate strings

Rate limits are expressed as human-readable strings: `"limit/[multiplier]unit"`.

| Format | Meaning |
|---|---|
| `"10/min"` | 10 requests per minute |
| `"100/hour"` | 100 requests per hour |
| `"5/s"` | 5 requests per second |
| `"1000/day"` | 1000 requests per day |
| `"3/5min"` | 3 requests per 5 minutes |
| `"10/2hours"` | 10 requests per 2 hours |

All time unit variants are supported: `s`, `sec`, `second`, `seconds`, `m`, `min`, `minute`, `minutes`, `h`, `hr`, `hour`, `hours`, `d`, `day`, `days`.

---

## The `rate_limit()` function

```python
rate_limit(default?, *, ip?, user?, cost?, name?)
```

| Argument | Type | Description |
|---|---|---|
| `default` | `str` | Shorthand for IP-only limit. Cannot be combined with `ip`. |
| `ip` | `str` | Rate string for the IP bucket (anonymous users). |
| `user` | `str` | Rate string for the user bucket (authenticated users). |
| `cost` | `int` | How many slots this request consumes. Default `1`. |
| `name` | `str` | Stable name for Redis key prefix. Auto-generated if omitted. |

```python
# IP only — for public/anonymous endpoints
rate_limit("10/min")
rate_limit(ip="10/min")          # same thing

# User only — for endpoints that always require auth
rate_limit(user="50/min")

# Dual bucket — anonymous gets IP limit, authenticated gets user limit
rate_limit(ip="10/min", user="50/min")
```

---

## How dual buckets work

When you set both `ip=` and `user=`, fastlimit picks **one bucket per request** — not both:

- If the request has a user ID → user bucket applies
- If the request is anonymous (no user ID) → IP bucket applies

This means authenticated and anonymous users have fully independent limits. An authenticated user with `user="50/min"` will never be blocked by the `ip="10/min"` anonymous limit, even if they share an IP with other users.

```
ip="10/min", user="50/min"

anonymous  → IP bucket    → 10 requests/min
logged in  → user bucket  → 50 requests/min  (IP bucket not checked)
```

---

## User limits are always explicit

`default` and the positional shorthand only set the IP bucket. User limits always require `user=`. This is intentional — it makes the distinction between anonymous and authenticated limits impossible to confuse.

---

## The `rule()` factory

For reusable named rules:

```python
from fastlimit import rule, rate_limit

PHOTO_DOWNLOAD = rule(ip="20/min", user="100/hour", name="photo_download")

@router.get("/photos/{id}/download", dependencies=[rate_limit(PHOTO_DOWNLOAD)])
async def download_photo(id: str):
    ...
```

Setting `name` keeps Redis keys predictable and easy to inspect:
```
fastlimit:photo_download:ip:1.2.3.4
fastlimit:photo_download:user:user_abc123
```

Without `name`, an 8-character random hex is generated at import time (e.g. `rl_a3f9c21b`). This is stable within a process but will change on restart, so set `name` for any rule you want to monitor in Redis.

---

## Request cost

Heavy endpoints can consume multiple slots per call:

```python
# costs 5 slots — a user with 50/min can only call this 10 times per minute
@router.post("/export", dependencies=[rate_limit("50/min", cost=5)])
async def export_data():
    ...
```
