"""Tests for the SONEL adapter and its parsers."""

import unittest

import pandas as pd

from tide_client import parsers
from tide_client.exceptions import TideParseError, TideValidationError
from tide_client.sonel import SONELSource
from tests.helpers import FakeTransport, fixture_json, fixture_text

SLV = fixture_text("sonel_slv.txt")
AJAX = fixture_json("sonel_ajax.json")
STATIONS = fixture_json("sonel_stations.geojson")


class TestParseSonelSlv(unittest.TestCase):
    def test_rows_and_values(self):
        frame = parsers.parse_sonel_slv(SLV)
        self.assertEqual(len(frame), 6)
        self.assertEqual(frame.index[0], pd.Timestamp("1941-05-20"))
        self.assertEqual(frame["value"].iloc[0], 3782.0)
        self.assertEqual(frame["value"].iloc[5], 3878.0)

    def test_decimal_date(self):
        text = "1941.3889\t3782\n1941.3917\t3724\n"
        frame = parsers.parse_sonel_slv(text, decimal_date=True)
        self.assertEqual(frame.index[0], pd.Timestamp("1941-05-01"))

    def test_missing_sentinel(self):
        text = "1941-05-20\t3782\n1941-05-21\t-99999\n1941-05-22\t\n"
        frame = parsers.parse_sonel_slv(text)
        self.assertEqual(len(frame), 3)
        self.assertEqual(int(frame["value"].isna().sum()), 2)


class TestSONELSource(unittest.TestCase):
    def _source(self):
        mapping = {
            "getdatamaps.php": STATIONS,
            "ajaxJson.php": AJAX,
            "msl/Demerliac/VALIDATED/dLROCH.slv": SLV,
        }
        return SONELSource(FakeTransport(mapping))

    def test_list_stations(self):
        stations = self._source().list_stations()
        self.assertEqual(len(stations), 2)
        rochelle = [s for s in stations if s.station_id == "1787"][0]
        self.assertEqual(rochelle.name, "LA ROCHELLE")
        self.assertEqual(rochelle.code, "LROCH")
        self.assertAlmostEqual(rochelle.latitude, 46.1585)
        self.assertAlmostEqual(rochelle.longitude, -1.2207)
        self.assertEqual(rochelle.country, "FRANCE")

    def test_get_daily_series_by_id(self):
        series = self._source().get_series("1787", interval="daily")
        self.assertEqual(series.source, "sonel")
        self.assertEqual(series.interval, "daily")
        self.assertEqual(series.unit, "mm")
        self.assertEqual(len(series), 6)
        self.assertEqual(series.data["value"].iloc[0], 3782.0)
        self.assertIn("SONEL", series.citation)

    def test_get_series_by_code(self):
        series = self._source().get_series("LROCH", interval="daily")
        self.assertEqual(series.station.station_id, "1787")

    def test_bad_interval(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("1787", interval="hourly")

    def test_bad_filter(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("1787", interval="daily", filter_name="Gaussian")

    def test_unknown_station(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("999999", interval="daily")

    def test_ajax_failure_raises(self):
        source = SONELSource(
            FakeTransport(
                {
                    "getdatamaps.php": STATIONS,
                    "ajaxJson.php": {"success": False, "message": "no file"},
                }
            )
        )
        with self.assertRaises(TideParseError):
            source.get_series("1787", interval="daily")


if __name__ == "__main__":
    unittest.main()
