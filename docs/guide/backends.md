# Backends

fastlimit ships with two backends and a protocol for building your own.

---

## MemoryBackend (default)

No configuration required. State lives in-process.

```python
limiter = FastLimit()   # uses MemoryBackend automatically
```

**Good for:**

- Development and local testing
- Single-process deployments
- Environments without Redis

**Not suitable for:**

- Multi-worker deployments (each worker has its own counter — limits are not shared)
- Persistent limits across restarts

---

## RedisBackend

Requires `pip install "fastlimit[redis]"`.

```python
limiter = FastLimit(redis_url="redis://localhost:6379")
```

Redis connection URL formats:

```python
# standalone
"redis://localhost:6379"
"redis://:password@localhost:6379/0"
"rediss://localhost:6380"         # TLS

# Redis Cluster — all keys use hash tags so multi-key scripts work correctly
"redis://cluster-node:6379"
```

**Good for:**

- Multi-process and multi-worker deployments
- Persistent limits across restarts
- High-throughput production systems

All three algorithms are implemented as atomic Lua scripts — no race conditions even under high concurrency.

---

## Custom backends

Implement the `Backend` protocol and pass it directly:

```python
from fastlimit.backends import Backend, BackendResult
from fastlimit.rules import BucketConfig


class MyBackend:
    async def check_and_increment(
        self,
        key: str,
        bucket: BucketConfig,
        cost: int,
    ) -> BackendResult:
        # your logic here
        # key   → e.g. "rl_abc123:ip:1.2.3.4"
        # bucket → BucketConfig(window_sec=60, limit=10)
        # cost  → how many slots to consume
        ...
        return BackendResult(
            allowed=True,
            limit=bucket.limit,
            remaining=9,
            reset_ms=int(time.time() * 1000) + bucket.window_sec * 1000,
        )


limiter = FastLimit(backend=MyBackend())
```

`BackendResult` fields:

| Field | Type | Description |
|---|---|---|
| `allowed` | `bool` | Whether the request is within the limit |
| `limit` | `int` | Total bucket capacity |
| `remaining` | `int` | Slots remaining after this request |
| `reset_ms` | `int` | Epoch ms when the window resets |
| `retry_after_ms` | `int` | Ms until retry is safe (blocked requests only) |

**What you can build with a custom backend:**

- **Memcached backend** — lower memory overhead than Redis for simple counters
- **DynamoDB backend** — for serverless deployments with no Redis
- **Postgres backend** — if you want limits persisted in your existing database
- **Multi-tier backend** — check local memory first, fall back to Redis (lower latency)
- **Observability backend** — wrap another backend and emit metrics to Prometheus/Datadog

---

## Swapping backends in tests

```python
from fastlimit import FastLimit
from fastlimit.backends.memory import MemoryBackend

# give each test its own clean backend
@pytest.fixture
def limiter():
    backend = MemoryBackend()
    lim = FastLimit(backend=backend)
    return lim

@pytest.fixture
async def app(limiter):
    app = FastAPI()
    limiter.init_app(app)
    ...
    return app
```

You can also clear state between tests:

```python
await backend.clear_all()
```
