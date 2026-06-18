class RateLimitExceeded(Exception):
    """Raised when any rate limit bucket is exhausted."""

    def __init__(
        self,
        retry_after: int,
        detail: str = "Too many requests.",
        limit: int | None = None,
        reset_ms: int | None = None,
    ):
        self.retry_after = retry_after
        self.detail = detail
        self.limit = limit
        self.reset_ms = reset_ms
        super().__init__(detail)


class FastLimitNotInitialized(RuntimeError):
    """Raised when rate_limit() is used but limiter.init_app() was never called."""

    def __init__(self) -> None:
        super().__init__(
            "fastlimit is not initialized on this app. "
            "Did you forget to call limiter.init_app(app)?"
        )


class MissingUserID(RuntimeError):
    """Raised when a user= rule is set but user_id_func is not configured."""

    def __init__(self, rule_name: str) -> None:
        super().__init__(
            f"Rule '{rule_name}' has a user limit but FastLimit has no user_id_func configured. "
            "Pass user_id_func=lambda req: ... when creating FastLimit()."
        )
