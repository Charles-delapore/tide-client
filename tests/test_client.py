"""Tests for the unified TideClient: search, dispatch, cross-reference."""

import unittest

from tide_client.client import TideClient
from tide_client.exceptions import TideValidationError
from tide_client.models import Station
from tests.helpers import FakeTransport, fixture_json, fixture_text

MAPPING = {
    "rlr.monthly.data/12.rlrdata": fixture_text("psmsl_monthly.txt"),
    "rlr.annual.data/12.rlrdata": fixture_text("psmsl_annual.txt"),
    "psmsl.org/data/obtaining/": fixture_text("psmsl_stations.html"),
    "distinct()": fixture_text("uhslc_stations.csv"),
    "time,sea_level": fixture_text("uhslc_daily.csv"),
    "getdatamaps.php": fixture_json("sonel_stations.geojson"),
    "ajaxJson.php": fixture_json("sonel_ajax.json"),
    "msl/Demerliac/VALIDATED/dLROCH.slv": fixture_text("sonel_slv.txt"),
    "stations.json": fixture_json("noaa_stations.json"),
    "product=hourly_height": fixture_json("noaa_hourly.json"),
    "product=monthly_mean": fixture_json("noaa_monthly.json"),
}


def make_client() -> TideClient:
    return TideClient(transport=FakeTransport(MAPPING))


class TestSearchStations(unittest.TestCase):
    def test_name_search(self):
        found = make_client().search_stations("Honolulu")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "uhslc")
        self.assertEqual(found[0].station_id, "57")

    def test_name_search_case_insensitive(self):
        found = make_client().search_stations("san francisco")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "noaa")

    def test_bbox_search(self):
        found = make_client().search_stations(bbox=(-123, 37, -122, 38))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].station_id, "9414290")

    def test_source_filter(self):
        found = make_client().search_stations(source="psmsl")
        self.assertEqual(len(found), 2)
        self.assertTrue(all(s.source == "psmsl" for s in found))

    def test_no_match(self):
        self.assertEqual(make_client().search_stations("ZZZNOPE"), [])

    def test_bad_source(self):
        with self.assertRaises(TideValidationError):
            make_client().search_stations(source="nasa")


class TestGetSeriesDispatch(unittest.TestCase):
    def test_psmsl(self):
        series = make_client().get_series("12", source="psmsl", interval="monthly")
        self.assertEqual(len(series), 9)

    def test_uhslc(self):
        series = make_client().get_series("57", source="uhslc", interval="daily")
        self.assertEqual(len(series), 4)

    def test_sonel(self):
        series = make_client().get_series("1787", source="sonel", interval="daily")
        self.assertEqual(len(series), 6)

    def test_noaa(self):
        series = make_client().get_series(
            "9414290", source="noaa", interval="hourly", start="2026-01-01", end="2026-01-02"
        )
        self.assertEqual(len(series), 3)

    def test_station_object_accepted(self):
        station = Station(source="psmsl", station_id="12", name="NEW YORK (THE BATTERY)")
        series = make_client().get_series(station, source="psmsl", interval="annual")
        self.assertEqual(len(series), 6)

    def test_bad_interval(self):
        with self.assertRaises(TideValidationError):
            make_client().get_series("12", source="psmsl", interval="weekly")


class TestCrossReference(unittest.TestCase):
    def test_gloss_match(self):
        station = Station(
            source="psmsl",
            station_id="12",
            name="Honolulu",
            latitude=21.3067,
            longitude=-157.8667,
            gloss_id="108",
        )
        self.assertEqual(make_client().cross_reference(station), {"uhslc": "57"})

    def test_name_and_position_match(self):
        station = Station(
            source="noaa",
            station_id="x",
            name="Honolulu",
            latitude=21.31,
            longitude=-157.87,
        )
        self.assertEqual(make_client().cross_reference(station), {"uhslc": "57"})

    def test_no_match(self):
        station = Station(source="psmsl", station_id="12", name="Nowhere", latitude=0.0, longitude=0.0)
        self.assertEqual(make_client().cross_reference(station), {})


class TestClientHelpers(unittest.TestCase):
    def test_describe_datum(self):
        self.assertIn("Revised Local Reference", TideClient.describe_datum("RLR"))

    def test_citation(self):
        self.assertIn("10.2112/JCOASTRES-D-12-00175.1", TideClient.citation("psmsl"))
        self.assertIn("10.7289/V5V40S7W", TideClient.citation("uhslc"))
        self.assertIn("SONEL", TideClient.citation("sonel"))
        self.assertIn("NOAA", TideClient.citation("noaa"))

    def test_haversine(self):
        dist = TideClient.haversine_km(37.8063, -122.4659, 21.3067, -157.8667)
        self.assertGreater(dist, 3800)
        self.assertLess(dist, 3900)


if __name__ == "__main__":
    unittest.main()
