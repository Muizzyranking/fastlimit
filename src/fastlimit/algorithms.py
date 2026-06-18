import enum


class Algorithm(enum.StrEnum):
    """Rate limiting algorithm to use.

    Attributes:
        SLIDING_WINDOW: Smoothest. Tracks exact request timestamps in a rolling
            window. Best burst protection. Slightly more memory per key.
        FIXED_WINDOW: Simplest. Counts resets on a fixed clock boundary (e.g.
            every full minute). Allows 2x burst at window edges.
        TOKEN_BUCKET: Most flexible. Tokens refill continuously; allows short
            bursts up to bucket capacity. Good for APIs with bursty-but-fair usage.
    """

    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    TOKEN_BUCKET = "token_bucket"
