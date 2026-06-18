# Algorithms

Set the algorithm when creating your limiter:

```python
limiter = FastLimit(algorithm=Algorithm.SLIDING_WINDOW)   # default
limiter = FastLimit(algorithm=Algorithm.FIXED_WINDOW)
limiter = FastLimit(algorithm=Algorithm.TOKEN_BUCKET)
```

---

## Sliding window (default)

Tracks the exact timestamp of every request in a rolling window. The window moves with each request — there are no fixed clock boundaries.

```
window = 60s, limit = 5

timeline ──────────────────────────────────────►
         t=0  t=10  t=20  t=30  t=40  t=50  t=60  t=70
requests  ●    ●     ●     ●     ●                  ●
                                        ▲
                                   5th request at t=40
                                   next slot frees at t=60
                                   (oldest request + window)
```

**Best for:** Most APIs. Smoothest protection against burst traffic.

**Trade-off:** Slightly more memory per key (stores timestamps instead of a counter). With Redis, uses a sorted set.

---

## Fixed window

Divides time into fixed-length buckets (e.g. every full minute). The counter resets at the boundary.

```
window = 60s, limit = 5

|──── 0–60s ────|──── 60–120s ────|
  ●●●●●  ← 5      ●●●●●  ← 5
  at t=59, you      at t=60, full
  used all 5        bucket resets
```

**Best for:** Simpler use cases where exact burst control is less critical. Lower memory than sliding window.

**Trade-off:** At the boundary between windows, a client can make `limit * 2` requests in a short period — 5 at t=59 and 5 more at t=60.

---

## Token bucket

A bucket fills with tokens at a steady rate. Each request consumes one token (or `cost` tokens). The bucket can accumulate up to `limit` tokens, allowing short bursts.

```
window = 60s, limit = 10
refill rate = 10 tokens / 60s ≈ 1 token every 6 seconds

t=0:   bucket=10  → request → bucket=9
t=6:   bucket=10  → 5 rapid requests → bucket=5
t=36:  bucket=10  (refilled over 30s)
```

**Best for:** APIs where you want to allow occasional bursts but maintain a long-term average rate. File uploads, video processing, report generation.

**Trade-off:** Slightly more complex to reason about. The `remaining` header reflects current token count, which may feel less intuitive than a request count.

---

## Choosing an algorithm

| | Sliding Window | Fixed Window | Token Bucket |
|---|:---:|:---:|:---:|
| Burst protection | ✅ Best | ⚠️ Boundary leak | ✅ Configurable |
| Memory usage | Higher | Lowest | Low |
| Intuitive headers | ✅ | ✅ | ⚠️ |
| Recommended for | Most APIs | Simple counters | Bursty workloads |

When in doubt, use `"sliding_window"`. It's the default for a reason.
