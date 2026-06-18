"""
Provides the ``rate_limit()`` dependency factory.

This is the primary interface users interact with when adding rate limits
to FastAPI routes.
"""

from typing import Any

from fastapi import Depends, Request, Response

from fastlimit.limiter import get_limiter
from fastlimit.rules import RateLimitRule
from fastlimit.rules import rule as _rule


def rate_limit(
    default: str | RateLimitRule | None = None,
    *,
    ip: str | None = None,
    user: str | None = None,
    cost: int = 1,
    name: str | None = None,
) -> Any:
    """
    Create a FastAPI dependency that enforces a rate limit.

    The resolved rule is evaluated at **request time** — the limiter is
    looked up from ``app.state``.

    Args:
        default: a rate string (``"10/min"``) for IP-only limiting. Acts as
            shorthand for ``ip=``. Cannot be combined with ``ip``.
        ip: Rate string for the IP bucket. e.g. ``"10/min"``.
        user: Rate string for the authenticated-user bucket. e.g. ``"50/min"``.
        cost: Request cost. Useful for expensive endpoints. Default ``1``.
        name: Optional stable name for Redis key prefix.

    Returns:
        A ``fastapi.Depends`` object to use in ``dependencies=[...]``.

    Examples::

        # IP-only shorthand
        dependencies=[rate_limit("10/min")]

        # Explicit IP
        dependencies=[rate_limit(ip="10/min")]

        # Dual bucket
        dependencies=[rate_limit(ip="10/min", user="50/min")]

        # Pre-built rule
        dependencies=[rate_limit(Rules.LOGIN)]

        # Inline on a router
        router = APIRouter(dependencies=[rate_limit("200/min")])

    Raises:
        FastLimitNotInitialized: At request time if ``limiter.init_app(app)``
            was never called.
        RateLimitExceeded: At request time if the limit is exceeded.
    """
    # Resolve the rule once at decoration time, not per-request
    if isinstance(default, RateLimitRule):
        resolved_rule = default
    else:
        resolved_rule = _rule(default, ip=ip, user=user, cost=cost, name=name)

    async def dependency(
        request: Request,
        response: Response,
    ) -> None:
        limiter = get_limiter(request)
        await limiter.check(request, response, resolved_rule)

    return Depends(dependency)
