"""Tests for the UHSLC adapter (ERDDAP) and its parsers."""

import unittest

from tide_client import parsers
from tide_client.exceptions import TideParseError, TideValidationError
from tide_client.uhslc import UHSLCSource
from tests.helpers import FakeTransport, fixture_text

DAILY_CSV = fixture_text("uhslc_daily.csv")
STATIONS_CSV = fixture_text("uhslc_stations.csv")


class TestParseErddapCsv(unittest.TestCase):
    def test_two_header_rows(self):
        frame = parsers.parse_erddap_csv(DAILY_CSV)
        self.assertEqual(list(frame.columns), ["station_name", "uhslc_id", "time", "sea_level", "quality"])
        self.assertEqual(len(frame), 4)
        self.assertEqual(frame["station_name"].iloc[0], "Pohnpei")
        self.assertEqual(frame.attrs["units"]["sea_level"], "millimeters")


class TestUHSLCSource(unittest.TestCase):
    def _source(self):
        mapping = {
            "distinct()": STATIONS_CSV,
            "time,sea_level": DAILY_CSV,
        }
        return UHSLCSource(FakeTransport(mapping))

    def test_list_stations(self):
        stations = self._source().list_stations()
        self.assertEqual(len(stations), 3)
        honolulu = [s for s in stations if s.station_id == "57"][0]
        self.assertEqual(honolulu.name, "Honolulu")
        self.assertAlmostEqual(honolulu.latitude, 21.3067)
        # ERDDAP reports 0..360 longitudes; the adapter normalises them.
        self.assertAlmostEqual(honolulu.longitude, -157.8667)
        self.assertEqual(honolulu.gloss_id, "108")
        self.assertEqual(honolulu.datum, "station zero")
        nawiliwili = [s for s in stations if s.station_id == "58"][0]
        self.assertIsNone(nawiliwili.gloss_id)

    def test_get_daily_series(self):
        series = self._source().get_series("57", interval="daily", quality="fast")
        self.assertEqual(series.source, "uhslc")
        self.assertEqual(series.interval, "daily")
        self.assertEqual(series.unit, "mm")
        self.assertEqual(len(series), 4)
        self.assertEqual(series.data["value"].iloc[0], 942.0)
        self.assertIn("Caldwell", series.citation)
        self.assertIn("10.7289/V5V40S7W", series.citation)

    def test_dataset_selection(self):
        source = self._source()
        self.assertEqual(source._dataset("hourly", "fast"), "global_hourly_fast")
        self.assertEqual(source._dataset("daily", "research"), "global_daily_rqds")
        self.assertEqual(source._dataset("hourly", "gesla"), "global_hourly_gesla")
        with self.assertRaises(TideValidationError):
            source._dataset("daily", "gesla")
        with self.assertRaises(TideValidationError):
            source._dataset("monthly", "fast")

    def test_empty_series_raises(self):
        source = UHSLCSource(FakeTransport({"distinct()": STATIONS_CSV, "time,sea_level": ""}))
        with self.assertRaises(TideParseError):
            source.get_series("57", interval="daily")

    def test_bad_quality(self):
        with self.assertRaises(TideValidationError):
            self._source().get_series("57", interval="daily", quality="realtime")


if __name__ == "__main__":
    unittest.main()
