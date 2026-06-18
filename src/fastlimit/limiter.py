import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from fastlimit.algorithms import Algorithm
from fastlimit.backends import Backend, BackendResult
from fastlimit.backends.memory import MemoryBackend
from fastlimit.exceptions import FastLimitNotInitialized, MissingUserID, RateLimitExceeded
from fastlimit.headers import HeaderConfig
from fastlimit.rules import RateLimitRule

logger = logging.getLogger("fastlimit")

_STATE_KEY = "fastlimit"


class FastLimit:
    """
    The main entry point for fastlimit.

    Create one instance per application, call :meth:`init_app` to register it,
    then use the standalone :func:`~fastlimit.depends.rate_limit` function in
    your routes — no need to import the limiter in route files.

    Args:
        redis_url: Redis connection URL. When provided, a
            :class:`~fastlimit.backends.redis.RedisBackend` is used.
            When omitted, falls back to the in-process
            :class:`~fastlimit.backends.memory.MemoryBackend`.
        backend: Supply a custom backend directly. Takes precedence over
            ``redis_url``. Must satisfy the :class:`~fastlimit.backends.Backend`
            protocol.
        algorithm: Rate limiting algorithm. Defaults to
            :attr:`~fastlimit.Algorithm.SLIDING_WINDOW`.
        user_id_func: Callable ``(request) -> str | None`` that extracts the
            authenticated user's identifier from the request. Required when any
            rule uses ``user=``.
        headers: Header injection config. Defaults to standard
            ``X-RateLimit-*`` headers.
        key_prefix: Redis/memory key prefix. Change this if multiple apps share
            one Redis instance.
        exempt_ips: Set of IP addresses that bypass all rate limits (e.g.
            internal health-check callers).
        dry_run: When ``True``, limits are evaluated but never enforced.
            Useful for observing impact before enabling limits in production.
        error_handler: Optional async callable
            ``(request, exc) -> Response`` to customise the 429 response body.
        trusted_proxies: Number of trusted reverse proxies. Used to correctly
            extract the real client IP from ``X-Forwarded-For``.

    Examples::

        # Minimal — memory backend, standard headers
        limiter = FastLimit()
        limiter.init_app(app)

        # Redis backend
        limiter = FastLimit(redis_url="redis://localhost:6379")
        limiter.init_app(app)

        # Full config
        limiter = FastLimit(
            redis_url="redis://localhost:6379",
            algorithm=Algorithm.TOKEN_BUCKET,
            user_id_func=lambda req: getattr(req.state, "user_id", None),
            headers=HeaderConfig(enabled=True),
            key_prefix="myapp",
            exempt_ips={"127.0.0.1"},
            dry_run=False,
        )
        limiter.init_app(app)
    """

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        backend: Backend | None = None,
        algorithm: Algorithm = Algorithm.SLIDING_WINDOW,
        user_id_func: Callable[[Request], str | None] | None = None,
        headers: HeaderConfig | None = None,
        key_prefix: str = "fastlimit",
        exempt_ips: set[str] | None = None,
        dry_run: bool = False,
        error_handler: Callable[..., Any] | None = None,
        trusted_proxies: int = 1,
    ) -> None:
        self._algorithm = algorithm
        self._user_id_func = user_id_func
        self._headers = headers or HeaderConfig()
        self._key_prefix = key_prefix
        self._exempt_ips = exempt_ips or set()
        self._dry_run = dry_run
        self._error_handler = error_handler
        self._trusted_proxies = trusted_proxies
        self._backend: Backend = backend or self._build_backend(redis_url, algorithm, key_prefix)

    def _build_backend(
        self,
        redis_url: str | None,
        algorithm: Algorithm,
        key_prefix: str,
    ) -> Backend:
        if redis_url is not None:
            try:
                from redis.asyncio import from_url

                from fastlimit.backends.redis import RedisBackend

                client = from_url(redis_url, decode_responses=False)
                return RedisBackend(client, algorithm=algorithm, key_prefix=key_prefix)
            except ImportError as e:
                raise ImportError(
                    "redis_url was provided but the 'redis' package is not installed. "
                    "Run: pip install fastlimit[redis]"
                ) from e
        return MemoryBackend(key_prefix=key_prefix)

    def init_app(self, app: FastAPI) -> None:
        """
        Register this limiter with a FastAPI application.

        Must be called before the app starts serving requests. Attaches the
        limiter to ``app.state`` and registers the 429 exception handler.

        Args:
            app: The FastAPI application instance.
        """
        setattr(app.state, _STATE_KEY, self)
        app.add_exception_handler(RateLimitExceeded, self._exception_handler)  # type: ignore[arg-type]
        if self._dry_run:
            logger.warning("fastlimit is running in DRY RUN mode — limits will not be enforced.")

    # =====================================
    # main check
    # =====================================

    async def check(
        self,
        request: Request,
        response: Response,
        rule: RateLimitRule,
    ) -> None:
        """
        Evaluate all buckets for a rule and raise or inject headers.

        Called by the :func:`~fastlimit.depends.rate_limit` dependency.

        Args:
            request: The incoming FastAPI request.
            response: The outgoing response (for header injection).
            rule: The resolved :class:`~fastlimit.rules.RateLimitRule`.

        Raises:
            RateLimitExceeded: If any bucket is exhausted and not in dry-run mode.
            MissingUserID: If a user bucket is configured but no
                ``user_id_func`` was provided.
        """
        ip = self._get_ip(request)

        if ip in self._exempt_ips:
            logger.debug("fastlimit: exempt IP %s — skipping checks.", ip)
            return

        user_id = self._get_user_id(request, rule)
        result: BackendResult | None = None

        if user_id and rule.user_limit:
            # authenticated — use user bucket exclusively
            key = f"{rule.name}:user:{user_id}"
            result = await self._backend.check_and_increment(key, rule.user_limit, rule.cost)

        elif rule.ip_limit:
            # anonymous (or no user_limit defined) — use IP bucket
            if ip:
                key = f"{rule.name}:ip:{ip}"
                result = await self._backend.check_and_increment(key, rule.ip_limit, rule.cost)
            else:
                logger.warning(
                    "fastlimit: rule '%s' has ip_limit but IP could not be resolved.",
                    rule.name,
                )

        elif rule.user_limit and not user_id:
            raise MissingUserID(rule.name)

        if result is not None:
            if not result.allowed:
                await self._handle_blocked(request, result)
                return

            # Inject headers
            headers = self._headers.build(
                limit=result.limit,
                remaining=result.remaining,
                reset_ms=result.reset_ms,
            )
            for k, v in headers.items():
                response.headers[k] = v

    async def _handle_blocked(self, request: Request, result: BackendResult) -> None:
        retry_after = max(1, result.retry_after_ms // 1000)
        if self._dry_run:
            logger.info(
                "fastlimit [DRY RUN]: would have blocked %s — retry after %ss.",
                self._get_ip(request),
                retry_after,
            )
            return
        raise RateLimitExceeded(
            retry_after=retry_after,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            limit=result.limit,
            reset_ms=result.reset_ms,
        )

    async def _exception_handler(self, request: Request, exc: RateLimitExceeded) -> Response:
        if self._error_handler:
            return await self._error_handler(request, exc)

        retry_headers = self._headers.build_retry(
            retry_after=exc.retry_after, limit=exc.limit, reset_ms=exc.reset_ms
        )
        return JSONResponse(
            status_code=429,
            content={"detail": exc.detail, "retry_after": exc.retry_after},
            headers=retry_headers,
        )

    def _get_ip(self, request: Request) -> str:
        tp = self._trusted_proxies
        if tp == 0:
            return request.client.host if request.client else "unknown"

        forwarded = request.headers.get("X-Forwarded-For", "")
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]

        if len(ips) >= tp + 1:
            return ips[-(tp + 1)]
        if ips:
            return ips[0]
        return request.client.host if request.client else "unknown"

    def _get_user_id(self, request: Request, rule: RateLimitRule) -> str | None:
        if rule.user_limit is None:
            return None
        if self._user_id_func is None:
            if rule.ip_limit is None:
                raise MissingUserID(rule.name)
            return None
        return self._user_id_func(request)


def get_limiter(request: Request) -> FastLimit:
    """
    Retrieve the :class:`FastLimit` instance from ``app.state``.

    Raises:
        FastLimitNotInitialized: If :meth:`FastLimit.init_app` was never called.
    """
    limiter = getattr(request.app.state, _STATE_KEY, None)
    if limiter is None:
        raise FastLimitNotInitialized()
    return limiter
