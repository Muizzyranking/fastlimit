from dataclasses import dataclass


@dataclass
class HeaderConfig:
    """
    Controls which rate limit headers are injected into responses.

    All header names are customisable so you can match your API's existing
    conventions or comply with specific standards.

    Attributes:
        enabled: Master switch. Set ``False`` to suppress all rate limit headers.
        limit: Header reporting the bucket's total request limit.
        remaining: Header reporting requests remaining in the current window.
        reset: Header reporting the UTC epoch second when the window resets.
        retry_after: Header added on 429 responses. Reports seconds until retry.

    Examples::

        # defaults — standard X-RateLimit-* headers
        HeaderConfig()

        # disabled
        HeaderConfig(enabled=False)

        # custom names
        HeaderConfig(
            limit="X-My-Limit",
            remaining="X-My-Remaining",
            reset="X-My-Reset",
        )

        # RateLimit-* style (IETF draft)
        HeaderConfig(
            limit="RateLimit-Limit",
            remaining="RateLimit-Remaining",
            reset="RateLimit-Reset",
        )
    """

    enabled: bool = True
    limit: str = "X-RateLimit-Limit"
    remaining: str = "X-RateLimit-Remaining"
    reset: str = "X-RateLimit-Reset"
    retry_after: str = "Retry-After"

    def build(
        self,
        *,
        limit: int,
        remaining: int,
        reset_ms: int,
    ) -> dict[str, str]:
        """Return header dict to inject on successful (non-blocked) responses."""
        if not self.enabled:
            return {}
        return {
            self.limit: str(limit),
            self.remaining: str(max(remaining, 0)),
            self.reset: str(reset_ms // 1000),
        }

    def build_retry(
        self,
        *,
        retry_after: int,
        limit: int | None = None,
        reset_ms: int | None = None,
    ) -> dict[str, str]:
        """Return header dict to inject on 429 responses."""
        if not self.enabled:
            return {}
        headers: dict[str, str] = {}
        if limit is not None and reset_ms is not None:
            headers.update(
                self.build(
                    limit=limit,
                    remaining=0,
                    reset_ms=reset_ms,
                )
            )
        headers.update({self.retry_after: str(retry_after)})
        return headers
