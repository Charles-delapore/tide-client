"""Error types for tide-client."""


class TideError(Exception):
    """Base error for all tide-client failures."""


class TideValidationError(TideError):
    """A caller-supplied argument is invalid (bad station, interval, datum)."""


class TideNotFoundError(TideError):
    """The requested station or series does not exist at the source (HTTP 404)."""


class TideRateLimitError(TideError):
    """The source refused the request for rate limiting (HTTP 429)."""


class TideAuthError(TideError):
    """The source requires authentication (HTTP 401/403)."""


class TideServerError(TideError):
    """The source failed with a 5xx response or an unreadable reply."""


class TideParseError(TideError):
    """A response arrived but could not be parsed into a series or station list."""
