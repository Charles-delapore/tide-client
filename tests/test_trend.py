"""Tests for trend fitting."""

import unittest

import numpy as np
import pandas as pd

from tide_client.exceptions import TideValidationError
from tide_client.models import Series, Station
from tide_client.trend import trend, trend_annual

STATION = Station(source="psmsl", station_id="12", name="NEW YORK (THE BATTERY)")


def make_series(years, values, interval="annual"):
    index = pd.DatetimeIndex([pd.Timestamp(year=int(y), month=1, day=1) for y in years])
    frame = pd.DataFrame({"value": values}, index=index)
    return Series(station=STATION, source="psmsl", interval=interval, datum="RLR", unit="mm", data=frame)


class TestTrend(unittest.TestCase):
    def test_exact_linear_slope(self):
        years = list(range(2000, 2021))
        values = [1000.0 + 3.0 * (y - 2000) for y in years]
        result = trend(make_series(years, values))
        self.assertAlmostEqual(result.slope, 3.0, places=6)
        self.assertAlmostEqual(result.r_squared, 1.0, places=6)
        self.assertEqual(result.method, "ols")
        self.assertEqual(result.n, 21)

    def test_ci_contains_true_slope(self):
        rng = np.random.default_rng(0)
        years = list(range(2000, 2021))
        values = [1000.0 + 3.0 * (y - 2000) + float(rng.normal(0, 5)) for y in years]
        result = trend(make_series(years, values))
        self.assertLess(result.ci_low, 3.0)
        self.assertGreater(result.ci_high, 3.0)
        self.assertGreater(result.se, 0)

    def test_ar1_widens_interval(self):
        rng = np.random.default_rng(0)
        years = list(range(2000, 2021))
        noise = [0.0]
        for _ in range(len(years) - 1):
            noise.append(0.9 * noise[-1] + float(rng.normal(0, 5)))
        values = [1000.0 + 3.0 * (y - 2000) + e for y, e in zip(years, noise)]
        series = make_series(years, values)
        plain = trend(series, ar1=False)
        adjusted = trend(series, ar1=True)
        self.assertEqual(adjusted.method, "ols-ar1")
        self.assertIsNotNone(adjusted.rho)
        self.assertGreater(adjusted.rho, 0.5)
        self.assertGreater(adjusted.se, plain.se)

    def test_too_few_points(self):
        with self.assertRaises(TideValidationError):
            trend(make_series([2000, 2001], [1000.0, 1003.0]))

    def test_missing_values_ignored(self):
        years = list(range(2000, 2021))
        values = [1000.0 + 3.0 * (y - 2000) for y in years]
        values[5] = float("nan")
        result = trend(make_series(years, values))
        self.assertEqual(result.n, 20)
        self.assertAlmostEqual(result.slope, 3.0, places=6)


class TestTrendAnnual(unittest.TestCase):
    def test_monthly_resampled_to_annual(self):
        index = pd.date_range("2020-01-01", periods=36, freq="MS")
        values = [1000.0 + 3.0 * (t.year - 2020) + t.month / 12.0 for t in index]
        frame = pd.DataFrame({"value": values}, index=index)
        series = Series(
            station=STATION, source="psmsl", interval="monthly", datum="RLR", unit="mm", data=frame
        )
        result = trend_annual(series)
        self.assertEqual(result.n, 3)
        self.assertAlmostEqual(result.slope, 3.0, places=1)


if __name__ == "__main__":
    unittest.main()
