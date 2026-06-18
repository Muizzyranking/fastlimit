# Why fastlimit

*A practical rate limiter built out of frustration with the existing options.*

---

When you add rate limiting to a FastAPI app, the obvious starting point is [SlowAPI](https://github.com/laurents/slowapi). It's the most referenced option, it works, and it gets the job done for basic use cases.

But after using it on an API, a few things became friction points that never went away.

## The problem with a single bucket

SlowAPI gives you one rate limit per endpoint. You pass a rate string, it checks either the IP or the user, your choice, and blocks the request if the count is exceeded.

This falls apart the moment your API has both authenticated and unauthenticated users hitting the same endpoint.

Say you have a `/search` endpoint. Anonymous users should get 10 requests per minute — enough to explore, not enough to scrape. Authenticated users should get 200 per minute — they're paying customers. With a single bucket, you have to pick one. You either protect against scraping (and frustrate your paying users) or you give everyone the authenticated limit (and have no protection for anonymous traffic).

The workaround is to check authentication inside the route and apply different limits manually. That's boilerplate you now maintain in every endpoint that has this distinction.

**fastlimit solves this with two independent buckets.** You declare the IP limit and the user limit separately. They're tracked separately. One can be exceeded without affecting the other. And both are reported separately in response headers so the client knows exactly which bucket it's hitting.

```python
@router.get("/search", dependencies=[rate_limit(ip="10/min", user="200/min")])
async def search(q: str):
    ...
```

That's it. Anonymous users get 10. Authenticated users get 200. Independent counters, one line.

## Forcing `Request` into function signatures

This one bothered me more than it probably should.

SlowAPI's decorator approach requires you to add `request: Request` to the function signature of every rate-limited route, even when your route has no other reason to touch the request object.

```python
@app.get("/items")
@limiter.limit("10/minute")
async def get_items(request: Request, db: Session = Depends(get_db)):
    # request is here only because SlowAPI needs it
    # it's never actually used in this function
    return db.query(Item).all()
```

Rate limiting is infrastructure. Your route handler shouldn't need to know it exists. When you're reading `get_items` three months later, `request: Request` creates noise — you have to check whether it's actually used anywhere or whether it's just there for the limiter.

**fastlimit injects rate limiting as a proper FastAPI dependency.** Your function signature stays clean. You return whatever you want — dict, Pydantic model, `FileResponse`, anything.

```python
@router.get("/items")
@limit("10/min")
async def get_items(db: Session = Depends(get_db)):
    return db.query(Item).all()   # clean, no Request
```

The mechanism for this is that FastAPI uses `inspect.signature()` to discover dependencies. fastlimit overrides `__signature__` on the wrapper function to inject a hidden `Depends` parameter — the same hook FastAPI itself uses for `Annotated[X, Depends(...)]`. The parameter is resolved by FastAPI, strips itself from kwargs before reaching your function, and leaves no trace.

## The header injection problem

SlowAPI supports injecting rate limit headers into responses, but there's a catch: when you enable it, **every rate-limited route must return a `Response` object directly**.

You can't return a dict. You can't return a Pydantic model. You can't return a list or a string and expect FastAPI to serialize it. The moment SlowAPI tries to inject headers onto the response, it assumes it's working with an actual `Response` — and returning anything else breaks.

This forces an impossible choice: either you get rate limit headers and give up on FastAPI's clean return types, or you return Pydantic models and drop the headers entirely. I ended up removing header injection and handling it manually, which I would have to do on every project I use slowapi.

```python
# SlowAPI with headers — you're forced to return Response directly
@app.get("/items")
@limiter.limit("10/minute")
async def get_items(request: Request, response: Response):
    items = await fetch_items()
    # can't just return items — have to manually build the response
    return JSONResponse(content=jsonable_encoder(items))
```

**fastlimit injects headers through FastAPI's `Response` dependency** — the same mechanism FastAPI uses for setting response headers from inside any dependency. The `Response` object is injected into the rate limit dependency itself, not your route function. Your route returns whatever it wants and FastAPI handles serialization as normal.

```python
# fastlimit — return anything, headers just work
@router.get("/items", dependencies=[rate_limit("10/min")])
async def get_items() -> list[Item]:
    return await fetch_items()   # Pydantic model, dict, list — anything
```

## What fastlimit looks like in practice

Setup is one object and one method call:

```python
limiter = FastLimit(
    redis_url="redis://localhost:6379",
    user_id_func=lambda req: getattr(req.state, "user_id", None),
)
limiter.init_app(app)
```

The `user_id_func` is how fastlimit finds the authenticated user — whatever your auth middleware puts on `request.state`, that's what you point it at. After that, every route file just imports `rate_limit` or `limit` — no limiter import, no global state to manage.

Routes look like this:

```python
# anonymous endpoint
@router.post("/register", dependencies=[rate_limit("10/min")])
async def register(body: RegisterRequest):
    return await create_user(body)

# authenticated endpoint with separate limits
@router.post("/upload", dependencies=[rate_limit(ip="5/min", user="50/min")])
async def upload(file: UploadFile):
    return await store_file(file)

# decorator style for those who prefer it
@router.get("/feed")
@limit(ip="60/min", user="300/min")
async def get_feed():
    return await fetch_feed()
```

The response headers on every request, allowed or blocked:

```
X-RateLimit-Limit: 50
X-RateLimit-Remaining: 47
X-RateLimit-Reset: 1781736212

# on a 429:
X-RateLimit-Remaining: 0
Retry-After: 41
```

---

The goal with fastlimit was to build the rate limiter I actually wanted to use — one that handles the authenticated/anonymous distinction cleanly, stays out of your function signatures, and works correctly with the full FastAPI response pipeline. Whether it's useful to others is up to whether these friction points resonate.
