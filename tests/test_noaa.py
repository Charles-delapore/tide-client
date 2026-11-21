"""Tests for the NOAA CO-OPS adapter and its parsers."""

import unittest

from tide_client import parsers
from tide_client.exceptions import TideValidationError
from tide_client.noaa import NOAASource
from tests.helpers import FakeTransport, fixture_json

HOURLY = fixture_json("noaa_hourly.json")
MONTHLY = fixture_json("noaa_monthly.json")
STATIONS = fixture_json("noaa_stations.json")


class TestParseNoaaHourly(unittest.TestCase):
    def test_values_in_mm(self):
        frame = parsers.parse_noaa_hourly(HOURLY)
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame["value"].iloc[0], -1049.0)
        self.assertEqual(frame["value"].iloc[1], -818.0)
        self.assertEqual(frame.index[0].strftime("%Y-%m-%d %H:%M"), "2026-01-01 00:00")
        self.assertEqual(frame.loc["2026-01-01 00:00", "flag"], "0,0")

    def test_empty_value_becomes_nan(self):
        payload = {"data": [{"t": "2026-01-01 00:00", "v": "", "s": "", "f": "0,0"}]}
        frame = parsers.parse_noaa_hourly(payload)
        self.assertEqual(len(frame), 1)
        self.assertTrue(frame["value"].isna().iloc[0])


class TestParseNoaaMonthly(unittest.TestCase):
    def test_msl_column(self):
        frame = parsers.parse_noaa_monthly(MONTHLY, datum="MSL")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.index[0].strftime("%Y-%m-%d"), "2025-01-01")
        self.assertEqual(frame["value"].iloc[0], 18.0)

    def test_other_datum_column(self):
        frame = parsers.parse_noaa_monthly(MONTHLY, datum="MHHW")
        self.assertEqual(frame["value"].iloc[0], 896.0)


class TestNOAASource(unittest.TestCase):
    def _source(self):
        mapping = {
            "stations.json": STATIONS,
            "product=hourly_height": HOURLY,
            "product=monthly_mean": MONTHLY,
        }
        return NOAASource(FakeTransport(mapping))

    def test_list_stations(self):
        stations = self._source().list_stations()
        self.assertEqual(len(stations), 2)
        sf = [s for s in stations if s.station_id == "9414290"][0]
        self.assertEqual(sf.name, "San Francisco")
        self.assertAlmostEqual(sf.latitude, 37.806305)
        self.assertAlmostEqual(sf.longitude, -122.46589)
        self.assertEqual(sf.extra["state"], "CA")

    def test_get_hourly_series(self):
        series = self._source().get_series(
            "9414290", interval="hourly", datum="MSL", start="2026-01-01", end="2026-01-02"
        )
        self.assertEqual(series.source, "noaa")
        self.assertEqual(series.interval, "hourly")
        self.assertEqual(series.unit, "mm")
        self.assertEqual(len(series), 3)
        self.assertIn("NOAA Tides and Currents", series.citation)

    def test_get_daily_series_resamples_hourly(self):
        series = self._source().get_series(
            "9414290", interval="daily", datum="MSL", start="2026-01-01", end="2026-01-02"
        )
        self.assertEqual(series.interval, "daily")
        self.assertEqual(len(series), 1)
        self.assertAlmostEqual(series.data["value"].iloc[0], -789.0)

    def test_get_monthly_series(self):
        series = self._source().get_series(
            "9414290", interval="monthly", datum="MSL", start="2025-01-01", end="2025-12-31"
        )
        self.assertEqual(series.interval, "monthly")
        self.assertEqual(len(series), 2)

    def test_get_annual_series_resamples_monthly(self):
        series = self._source().get_series(
            "9414290", interval="annual", datum="MSL", start="2025-01-01", end="2025-12-31"
        )
        self.assertEqual(series.interval, "annual")
        self.assertEqual(len(series), 1)
        self.assertEqual(series.data.index[0].strftime("%Y-%m-%d"), "2025-01-01")

    def test_dates_required(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("9414290", interval="hourly")

    def test_bad_datum(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series(
                "9414290", interval="hourly", datum="XYZ", start="2026-01-01", end="2026-01-02"
            )

    def test_unknown_station(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series(
                "0000000", interval="hourly", start="2026-01-01", end="2026-01-02"
            )


if __name__ == "__main__":
    unittest.main()
