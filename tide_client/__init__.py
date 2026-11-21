"""Unified tide-gauge and sea-level time-series client.

Sources: PSMSL, UHSLC (via ERDDAP), SONEL and NOAA CO-OPS. The library
ships no data and redistributes no upstream data; every call fetches
on demand from the source, optionally through a user-chosen local cache.
"""

from tide_client.client import TideClient
from tide_client.exceptions import (
    TideAuthError,
    TideError,
    TideNotFoundError,
    TideParseError,
    TideRateLimitError,
    TideServerError,
    TideValidationError,
)
from tide_client.models import Series, Station, TrendResult

__version__ = "0.1.0"

__all__ = [
    "TideClient",
    "Station",
    "Series",
    "TrendResult",
    "TideError",
    "TideAuthError",
    "TideNotFoundError",
    "TideParseError",
    "TideRateLimitError",
    "TideServerError",
    "TideValidationError",
    "__version__",
]
