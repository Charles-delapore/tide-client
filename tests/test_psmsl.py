"""Tests for the PSMSL adapter and parsers (offline, mocked HTTP)."""

import unittest

import pandas as pd

from tide_client import parsers
from tide_client.exceptions import TideValidationError
from tide_client.psmsl import PSMSLSource
from tide_client.transport import Transport
from tests.helpers import FakeTransport, fixture_text

MONTHLY = fixture_text("psmsl_monthly.txt")
ANNUAL = fixture_text("psmsl_annual.txt")
STATIONS_HTML = fixture_text("psmsl_stations.html")


class TestParsePsmslMonthly(unittest.TestCase):
    def test_rows_and_values(self):
        frame = parsers.parse_psmsl_monthly(MONTHLY)
        self.assertEqual(len(frame), 9)
        self.assertEqual(frame.index[0], pd.Timestamp("1856-01-01"))
        self.assertEqual(frame["value"].iloc[0], 6721.0)
        self.assertEqual(frame["value"].iloc[1], 6721.0)
        self.assertEqual(frame["value"].iloc[2], 6666.0)

    def test_decimal_year_to_month(self):
        frame = parsers.parse_psmsl_monthly(MONTHLY)
        self.assertEqual(frame.index[3], pd.Timestamp("1856-04-01"))
        self.assertEqual(frame.index[4], pd.Timestamp("1856-05-01"))

    def test_missing_sentinel_becomes_nan(self):
        frame = parsers.parse_psmsl_monthly(MONTHLY)
        self.assertEqual(int(frame["value"].isna().sum()), 3)
        self.assertTrue(pd.isna(frame.loc["1861-01-01", "value"]))
        self.assertTrue(pd.isna(frame.loc["1861-02-01", "value"]))

    def test_days_missing_and_flag_kept(self):
        frame = parsers.parse_psmsl_monthly(MONTHLY)
        self.assertEqual(frame.loc["1856-01-01", "days_missing"], 0)
        self.assertEqual(frame.loc["1856-01-01", "flag"], "000")


class TestParsePsmslAnnual(unittest.TestCase):
    def test_rows_and_values(self):
        frame = parsers.parse_psmsl_annual(ANNUAL)
        self.assertEqual(len(frame), 6)
        self.assertEqual(frame.index[0], pd.Timestamp("1856-01-01"))
        self.assertEqual(frame["value"].iloc[0], 6698.0)
        self.assertEqual(frame.loc["1856-01-01", "flag"], "N")


class TestParsePsmslStationTable(unittest.TestCase):
    def test_two_rows(self):
        rows = parsers.parse_psmsl_station_table(STATIONS_HTML)
        self.assertEqual(len(rows), 2)
        by_id = {r["id"]: r for r in rows}
        ny = by_id["12"]
        self.assertEqual(ny["name"], "NEW YORK (THE BATTERY)")
        self.assertAlmostEqual(ny["lat"], 40.700)
        self.assertAlmostEqual(ny["lon"], -74.013)
        self.assertEqual(ny["country"], "USA")
        self.assertEqual(ny["gloss_id"], "960")
        self.assertEqual(ny["coastline"], "121")
        self.assertIn("1", by_id)


class TestPSMSLSource(unittest.TestCase):
    def _source(self):
        mapping = {
            "rlr.monthly.data/12.rlrdata": MONTHLY,
            "rlr.annual.data/12.rlrdata": ANNUAL,
            "psmsl.org/data/obtaining/": STATIONS_HTML,
        }
        return PSMSLSource(FakeTransport(mapping))

    def test_list_stations(self):
        stations = self._source().list_stations()
        self.assertEqual(len(stations), 2)
        self.assertEqual(stations[0].source, "psmsl")
        self.assertEqual(stations[0].datum, "RLR (Revised Local Reference)")
        self.assertEqual(stations[0].unit, "mm")

    def test_get_monthly_series(self):
        series = self._source().get_series("12", interval="monthly")
        self.assertEqual(series.source, "psmsl")
        self.assertEqual(series.interval, "monthly")
        self.assertEqual(series.unit, "mm")
        self.assertEqual(len(series), 9)
        self.assertEqual(series.n_valid, 6)
        self.assertIn("Holgate", series.citation)
        self.assertIn("10.2112/JCOASTRES-D-12-00175.1", series.citation)

    def test_get_annual_series(self):
        series = self._source().get_series("12", interval="annual")
        self.assertEqual(series.interval, "annual")
        self.assertEqual(len(series), 6)

    def test_bad_interval(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("12", interval="hourly")

    def test_unknown_station(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("999999", interval="monthly")


if __name__ == "__main__":
    unittest.main()
