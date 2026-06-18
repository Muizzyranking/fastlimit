from typing import Protocol, runtime_checkable

from fastlimit.rules import BucketConfig


@runtime_checkable
class Backend(Protocol):
    """
    Protocol all rate limit backends must satisfy.

    Each backend implements a single method :meth:`check_and_increment` that
    atomically checks whether a request is within the limit and records it if so.

    Backends are responsible for:

    - Atomically checking + recording requests (no race conditions).
    - Returning accurate ``remaining``, ``reset_ms``, and ``retry_after_ms`` values.
    - Cleaning up expired data (TTL management).
    """

    async def check_and_increment(
        self,
        key: str,
        bucket: BucketConfig,
        cost: int,
    ) -> "BackendResult":
        """
        Check the bucket and record the request if allowed.

        Args:
            key: Unique bucket key, e.g. ``"rl:login:ip:1.2.3.4"``.
            bucket: The :class:`~fastlimit.rules.BucketConfig` for this bucket.
            cost: How many tokens/slots to consume.

        Returns:
            A :class:`BackendResult` with allowed status and window metadata.
        """
        ...


class BackendResult:
    """
    Result returned by :meth:`Backend.check_and_increment`.

    Attributes:
        allowed: ``True`` if the request is within the limit.
        limit: Total request limit for this bucket.
        remaining: Requests remaining after this one.
        reset_ms: Epoch milliseconds when the current window resets.
        retry_after_ms: Milliseconds until retry is safe (only when blocked).
    """

    __slots__ = ("allowed", "limit", "remaining", "reset_ms", "retry_after_ms")

    def __init__(
        self,
        *,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_ms: int,
        retry_after_ms: int = 0,
    ) -> None:
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.reset_ms = reset_ms
        self.retry_after_ms = retry_after_ms
