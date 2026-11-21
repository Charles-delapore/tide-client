"""Linear trend with a 95% confidence interval.

Ordinary least squares on time in years. The optional AR(1) variant
inflates the standard error by sqrt((1+rho)/(1-rho)) with rho the lag-1
autocorrelation of the residuals, the adjustment used in sea-level
trend work in the spirit of the TG-Rate-95CI approach (implemented
here from the standard formula, not copied from that code).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tide_client.exceptions import TideValidationError
from tide_client.models import Series, TrendResult
from tide_client.parsers import YE_FREQ

_T_CRITICAL = 1.96  # normal approximation for the 95% interval


def trend(series: Series, ar1: bool = False) -> TrendResult:
    """Fit a linear trend (mm/yr) to a series and return slope + 95% CI."""
    frame = series.data.dropna(subset=["value"])
    if len(frame) < 3:
        raise TideValidationError("need at least 3 valid observations for a trend")
    years = frame.index.year + (frame.index.dayofyear - 1) / 365.25
    x = np.asarray(years, dtype=float)
    y = np.asarray(frame["value"], dtype=float)
    n = len(x)
    x_mean = x.mean()
    sxx = float(((x - x_mean) ** 2).sum())
    if sxx == 0:
        raise TideValidationError("series spans no time; cannot fit a trend")
    slope = float(((x - x_mean) * (y - y.mean())).sum() / sxx)
    intercept = float(y.mean() - slope * x_mean)
    fitted = intercept + slope * x
    residuals = y - fitted
    dof = n - 2
    sigma2 = float((residuals**2).sum() / dof) if dof > 0 else 0.0
    se = math.sqrt(sigma2 / sxx)
    rho: float | None = None
    method = "ols"
    if ar1:
        method = "ols-ar1"
        if n > 3:
            rho = float(np.corrcoef(residuals[:-1], residuals[1:])[0, 1])
            if not math.isfinite(rho):
                rho = 0.0
            rho = max(-0.9, min(0.9, rho))
            se = se * math.sqrt((1 + rho) / (1 - rho))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - float((residuals**2).sum()) / ss_tot if ss_tot > 0 else 0.0
    half = _T_CRITICAL * se
    return TrendResult(
        slope=slope,
        intercept=intercept,
        se=se,
        ci_low=slope - half,
        ci_high=slope + half,
        n=n,
        r_squared=r_squared,
        method=method,
        rho=rho,
    )


def trend_annual(series: Series, ar1: bool = True) -> TrendResult:
    """Trend of the annual means of a series (the usual sea-level form)."""
    if series.interval == "annual":
        return trend(series, ar1=ar1)
    annual = series.data.resample(YE_FREQ)["value"].mean().to_frame()
    annual.index = annual.index.normalize().to_period("Y").to_timestamp()
    annual = annual.dropna(subset=["value"])
    sub = Series(
        station=series.station,
        source=series.source,
        interval="annual",
        datum=series.datum,
        unit=series.unit,
        data=annual,
        citation=series.citation,
    )
    return trend(sub, ar1=ar1)
