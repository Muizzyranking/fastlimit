"""
fastlimit — rate limiting for FastAPI.

Quickstart::

    from fastapi import FastAPI
    from fastlimit import FastLimit, rate_limit

    app = FastAPI()
    limiter = FastLimit()
    limiter.init_app(app)

    @app.get("/hello", dependencies=[rate_limit("10/min")])
    async def hello():
        return {"hello": "world"}

With Redis and dual IP/user limits::

    limiter = FastLimit(
        redis_url="redis://localhost:6379",
        user_id_func=lambda req: getattr(req.state, "user_id", None),
    )
    limiter.init_app(app)

    @app.post("/upload", dependencies=[rate_limit(ip="5/min", user="50/min")])
    async def upload(): ...
"""

from fastlimit.algorithms import Algorithm
from fastlimit.decorator import limit
from fastlimit.depends import rate_limit
from fastlimit.exceptions import FastLimitNotInitialized, MissingUserID, RateLimitExceeded
from fastlimit.headers import HeaderConfig
from fastlimit.limiter import FastLimit
from fastlimit.rules import BucketConfig, RateLimitRule, rule

__all__ = [
    # Core
    "FastLimit",
    "rate_limit",
    "limit",
    # Rule building
    "rule",
    "RateLimitRule",
    "BucketConfig",
    # Config
    "Algorithm",
    "HeaderConfig",
    # Exceptions
    "RateLimitExceeded",
    "FastLimitNotInitialized",
    "MissingUserID",
]

__version__ = "0.1.0"
