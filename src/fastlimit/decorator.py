"""
Decorator-style rate limiting.

Injects rate limit dependencies into the route function's __signature__ so
FastAPI picks them up automatically — no Request in the user's function needed.

Usage:

    @router.get("/feed")
    @limit("100/min", user="500/min")
    async def feed():
        return {"ok": True}
"""

import functools
import inspect
from collections.abc import Callable
from typing import Any

from fastlimit.depends import rate_limit
from fastlimit.rules import RateLimitRule

# Prefix for injected hidden parameter names — must not clash with user params
_PARAM_PREFIX = "_fastlimit_dep_"


def limit(
    default: str | RateLimitRule | None = None,
    *,
    ip: str | None = None,
    user: str | None = None,
    cost: int = 1,
    name: str | None = None,
) -> Callable[[Any], Any]:
    """
    Decorator that adds a rate limit to a FastAPI route.

    Identical arguments to `fastlimit.depends.rate_limit`.
    The route function does **not** need ``Request`` in its signature.

    Args:
        default: IP-only rate string.
        ip: Rate string for IP bucket.
        user: Rate string for user bucket.
        cost: Request cost per call.
        name: Stable Redis key name.

    Returns:
        A decorator that injects the rate limit as a hidden FastAPI dependency.

    Examples::

        from fastlimit import limit

        @router.get("/photos")
        @limit("20/min")
        async def list_photos(): ...

        @router.post("/upload")
        @limit(ip="5/min", user="30/min")
        async def upload(): ...

        # Stacking: each @limit adds an independent bucket
        @router.get("/feed")
        @limit("200/min")
        @limit(user="1000/min")
        async def feed(): ...
    """
    dep = rate_limit(default, ip=ip, user=user, cost=cost, name=name)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Strip all injected dep kwargs before passing to original function
            clean_kwargs = {k: v for k, v in kwargs.items() if not k.startswith(_PARAM_PREFIX)}
            return await func(*args, **clean_kwargs)

        # Count existing injected deps so stacked @limit decorators get unique param names
        existing_sig = inspect.signature(wrapper)
        n_existing = sum(1 for p in existing_sig.parameters if p.startswith(_PARAM_PREFIX))
        param_name = f"{_PARAM_PREFIX}{n_existing}"

        # Inject the Depends into __signature__ so FastAPI resolves it
        old_params = list(existing_sig.parameters.values())
        new_param = inspect.Parameter(
            param_name,
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=dep,
            annotation=None,
        )
        new_sig = existing_sig.replace(parameters=old_params + [new_param])
        object.__setattr__(wrapper, "__signature__", new_sig)
        return wrapper

    return decorator
