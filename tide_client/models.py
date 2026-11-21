"""Data models: Station, Series and TrendResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd


@dataclass
class Station:
    """One tide-gauge station in one source.

    ``station_id`` is the source-native identifier as a string: PSMSL numeric
    id, UHSLC numeric id, SONEL numeric id, NOAA numeric id. ``code`` holds
    the source-native short code where one exists (SONEL ``sta_acro``).
    ``cross_refs`` maps another source name to that source's station id for
    the same physical gauge, when a shared key (GLOSS id, name + position)
    establishes the match.
    """

    source: str
    station_id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    country: str | None = None
    code: str | None = None
    datum: str | None = None
    unit: str | None = None
    start: date | None = None
    end: date | None = None
    gloss_id: str | None = None
    cross_refs: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"Station(source={self.source!r}, station_id={self.station_id!r}, "
            f"name={self.name!r}, lat={self.latitude}, lon={self.longitude})"
        )


@dataclass
class Series:
    """One fetched time series.

    ``data`` is a pandas DataFrame with a DatetimeIndex and at least a
    ``value`` column in millimetres. ``flag`` / ``quality`` columns hold the
    source quality flag when the source provides one. Missing observations
    are NaN; the source sentinel (PSMSL/SONEL -99999, NOAA empty string)
    is already converted. ``citation`` is the per-source attribution string
    for this fetch.
    """

    station: Station
    source: str
    interval: str
    datum: str
    unit: str
    data: pd.DataFrame
    citation: str = ""
    quality: str | None = None

    def __len__(self) -> int:
        return len(self.data)

    @property
    def start(self) -> pd.Timestamp | None:
        return self.data.index.min() if len(self.data) else None

    @property
    def end(self) -> pd.Timestamp | None:
        return self.data.index.max() if len(self.data) else None

    @property
    def n_valid(self) -> int:
        return int(self.data["value"].notna().sum()) if "value" in self.data else 0

    def to_xarray(self):  # pragma: no cover - thin optional wrapper
        """Return the series as an xarray Dataset (requires xarray)."""
        try:
            import xarray as xr
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "xarray is not installed; install tide-client[xarray] to use to_xarray()"
            ) from exc
        return xr.Dataset.from_dataframe(self.data)

    def __repr__(self) -> str:
        return (
            f"Series(source={self.source!r}, station={self.station.name!r}, "
            f"interval={self.interval!r}, datum={self.datum!r}, "
            f"n={len(self.data)}, n_valid={self.n_valid})"
        )


@dataclass
class TrendResult:
    """Linear trend of a series, with a 95% confidence interval.

    ``slope`` is millimetres per year. ``method`` is ``ols`` or ``ols-ar1``;
    the AR(1) variant inflates the standard error by sqrt((1+rho)/(1-rho))
    with rho the lag-1 autocorrelation of the residuals, the adjustment used
    in sea-level trend work in the spirit of the TG-Rate-95CI approach.
    """

    slope: float
    intercept: float
    se: float
    ci_low: float
    ci_high: float
    n: int
    r_squared: float
    method: str = "ols"
    rho: float | None = None

    def __repr__(self) -> str:
        return (
            f"TrendResult(slope={self.slope:.3f} mm/yr, "
            f"95% CI [{self.ci_low:.3f}, {self.ci_high:.3f}], "
            f"n={self.n}, method={self.method!r})"
        )
