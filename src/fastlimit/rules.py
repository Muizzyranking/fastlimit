import re
import uuid
from dataclasses import dataclass

# Time unit map — everything normalises to seconds

_UNIT_SECONDS: dict[str, int] = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
}

# matches "5/min", "100 / hours", "3/5min", "10/2hours"
_RATE_RE = re.compile(r"^(\d+)\s*/\s*(\d*)(\w+)$")


def _parse_rate(rate: str) -> "BucketConfig":
    """
    Parse a human-readable rate string into a BucketConfig.

    Supported formats::

        "10/min"       → 10 requests per 60 seconds
        "100/hour"     → 100 requests per 3600 seconds
        "5/s"          → 5 requests per second
        "3/5min"       → 3 requests per 300 seconds
        "1000/day"     → 1000 requests per 86400 seconds

    Args:
        rate: Rate string in ``"limit/[multiplier]unit"`` format.

    Returns:
        BucketConfig with resolved window_sec and limit.

    Raises:
        ValueError: If the format or time unit is unrecognised.
    """
    m = _RATE_RE.match(rate.strip())
    if not m:
        raise ValueError(
            f"Invalid rate '{rate}'. "
            "Expected format: '10/min', '100/hour', '3/5min'. "
            f"Valid units: {', '.join(sorted(_UNIT_SECONDS))}."
        )

    limit_str, multiplier_str, unit = m.group(1), m.group(2), m.group(3).lower()

    if unit not in _UNIT_SECONDS:
        raise ValueError(
            f"Unknown time unit '{unit}' in rate '{rate}'. "
            f"Valid units: {', '.join(sorted(_UNIT_SECONDS))}."
        )

    unit_sec = _UNIT_SECONDS[unit]
    multiplier = int(multiplier_str) if multiplier_str else 1
    window_sec = unit_sec * multiplier

    return BucketConfig(window_sec=window_sec, limit=int(limit_str))


@dataclass(frozen=True)
class BucketConfig:
    """
    Resolved rate limit for a single bucket (IP or user).

    Attributes:
        window_sec: Rolling window size in seconds.
        limit: Maximum requests allowed within the window.
    """

    window_sec: int
    limit: int

    def __post_init__(self) -> None:
        if self.window_sec <= 0:
            raise ValueError(f"window_sec must be positive, got {self.window_sec}")
        if self.limit <= 0:
            raise ValueError(f"limit must be positive, got {self.limit}")


@dataclass(frozen=True)
class RateLimitRule:
    """
    A fully resolved rate limit rule.

    Prefer creating rules via :func:`rule` rather than directly.

    Attributes:
        name: Unique rule name. Used as part of the Redis/memory key.
        ip_limit: Limit applied per IP address. ``None`` to disable.
        user_limit: Limit applied per authenticated user. ``None`` to disable.
        cost: How many tokens/requests this rule costs per call. Default 1.
    """

    name: str
    ip_limit: BucketConfig | None = None
    user_limit: BucketConfig | None = None
    cost: int = 1

    def __post_init__(self) -> None:
        if self.ip_limit is None and self.user_limit is None:
            raise ValueError(
                f"RateLimitRule '{self.name}': at least one of ip_limit or user_limit must be set."
            )
        if self.cost < 1:
            raise ValueError(f"cost must be >= 1, got {self.cost}")


# ===========================
# Public factory
# ==========================


def rule(
    default: str | None = None,
    *,
    ip: str | None = None,
    user: str | None = None,
    name: str | None = None,
    cost: int = 1,
) -> RateLimitRule:
    """
    Create a :class:`RateLimitRule` from human-readable rate strings.

    Args:
        default: Shorthand for IP-only limiting. Equivalent to ``ip=...``.
            Cannot be combined with ``ip``.
        ip: Rate string for IP-based bucket. e.g. ``"10/min"``.
        user: Rate string for authenticated-user bucket. e.g. ``"50/min"``.
        name: Stable name for Redis key prefix. Auto-generated if omitted.
            Set this for predictable key names and easier Redis inspection.
        cost: Request cost per call. Useful for heavy endpoints. Default ``1``.

    Returns:
        A frozen :class:`RateLimitRule`.

    Raises:
        ValueError: If both ``default`` and ``ip`` are set, or neither bucket
            is provided, or any rate string is invalid.

    Examples::

        # IP-only (anonymous endpoints)
        rule("10/min")
        rule(ip="10/min")

        # Separate limits per IP and authenticated user
        rule(ip="10/min", user="50/min")

        # Named rule for predictable Redis keys
        rule(ip="20/min", user="100/hour", name="photo_download")

        # Heavy endpoint — counts as 5 requests per call
        rule("10/min", cost=5)

        # Non-standard window
        rule("3/5min")         # 3 requests per 5 minutes
        rule("1000/day")       # 1000 requests per day
    """
    if default is not None and ip is not None:
        raise ValueError(
            "Cannot set both 'default' and 'ip'. "
            "Use 'default' as shorthand for IP-only, or 'ip' explicitly."
        )

    ip_str = default if default is not None else ip

    if ip_str is None and user is None:
        raise ValueError("At least one of 'default', 'ip', or 'user' must be set.")

    return RateLimitRule(
        name=name or f"rl_{uuid.uuid4().hex[:8]}",
        ip_limit=_parse_rate(ip_str) if ip_str else None,
        user_limit=_parse_rate(user) if user else None,
        cost=cost,
    )
