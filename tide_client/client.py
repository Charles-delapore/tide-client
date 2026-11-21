"""Unified entry point: TideClient.

One client for PSMSL, UHSLC, SONEL and NOAA CO-OPS. Station search
runs across sources; series fetch dispatches to the source adapter;
cross-references match the same physical gauge across sources by GLOSS
id, then by name + position. No API key is needed by any of the four
sources today; if a source starts requiring one, pass it through the
environment and never through code or logs.
"""

from __future__ import annotations

import math
from pathlib import Path

import requests

from tide_client import trend as trend_mod
from tide_client.citations import citation_for
from tide_client.datums import describe as describe_datum
from tide_client.exceptions import TideValidationError
from tide_client.models import Series, Station, TrendResult
from tide_client.noaa import NOAASource
from tide_client.psmsl import PSMSLSource
from tide_client.sonel import SONELSource
from tide_client.transport import Transport
from tide_client.uhslc import UHSLCSource

SOURCES = ("psmsl", "uhslc", "sonel", "noaa")
INTERVALS = ("hourly", "daily", "monthly", "annual")


class TideClient:
    """Unified tide-gauge client.

    Parameters
    ----------
    timeout: seconds for one HTTP request (default 60).
    max_retries: retries on 429/5xx before giving up (default 3).
    cache_dir: optional directory for raw-response caching. When set,
        responses are stored as files keyed by URL hash and reused on
        later calls. The library ships no data; the cache only avoids
        re-downloading what the user already fetched.
    session: optional requests.Session (tests inject a mock here).
    """

    def __init__(
        self,
        timeout: float = 60.0,
        max_retries: int = 3,
        cache_dir: str | Path | None = None,
        session: requests.Session | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.transport = transport or Transport(
            session=session, timeout=timeout, max_retries=max_retries, cache_dir=cache_dir
        )
        self.psmsl = PSMSLSource(self.transport)
        self.uhslc = UHSLCSource(self.transport)
        self.sonel = SONELSource(self.transport)
        self.noaa = NOAASource(self.transport)
        self._source_map = {
            "psmsl": self.psmsl,
            "uhslc": self.uhslc,
            "sonel": self.sonel,
            "noaa": self.noaa,
        }

    def _check_source(self, source: str) -> None:
        if source not in SOURCES:
            raise TideValidationError(f"source must be one of {SOURCES}, got {source!r}")

    def _check_interval(self, interval: str) -> None:
        if interval not in INTERVALS:
            raise TideValidationError(f"interval must be one of {INTERVALS}, got {interval!r}")

    def list_stations(self, source: str, **kwargs) -> list[Station]:
        """List stations of one source (keyword args go to the adapter)."""
        self._check_source(source)
        return self._source_map[source].list_stations(**kwargs)

    def search_stations(
        self,
        query: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        source: str | None = None,
    ) -> list[Station]:
        """Search stations across sources by name substring and/or bbox.

        ``bbox`` is (lon_min, lat_min, lon_max, lat_max). Sources that
        need a station list fetch it once and cache it in memory.
        """
        sources = (source,) if source else SOURCES
        found: list[Station] = []
        for name in sources:
            self._check_source(name)
            for station in self._source_map[name].list_stations():
                if query and query.lower() not in station.name.lower():
                    continue
                if bbox and station.longitude is not None and station.latitude is not None:
                    lon_min, lat_min, lon_max, lat_max = bbox
                    if not (lon_min <= station.longitude <= lon_max and lat_min <= station.latitude <= lat_max):
                        continue
                found.append(station)
        return found

    def get_series(
        self,
        station: str | Station,
        source: str,
        interval: str = "monthly",
        **kwargs,
    ) -> Series:
        """Fetch one series.

        ``station`` is a station id string or a Station object. Extra
        keyword arguments go to the source adapter: PSMSL takes none;
        UHSLC takes ``quality`` (fast/research/gesla) and ``start``/``end``;
        SONEL takes ``filter_name`` (Demerliac/Doodson) and
        ``decimal_date``; NOAA takes ``datum`` and requires ``start``/``end``
        (YYYY-MM-DD) for every interval.
        """
        self._check_source(source)
        self._check_interval(interval)
        station_id = station.station_id if isinstance(station, Station) else str(station)
        if source == "psmsl":
            return self.psmsl.get_series(station_id, interval=interval)
        if source == "uhslc":
            return self.uhslc.get_series(station_id, interval=interval, **kwargs)
        if source == "sonel":
            return self.sonel.get_series(station_id, interval=interval, **kwargs)
        return self.noaa.get_series(station_id, interval=interval, **kwargs)

    def cross_reference(self, station: Station) -> dict[str, str]:
        """Find the same physical gauge in the other sources.

        First by shared GLOSS id, then by name similarity plus position
        within 0.05 degrees. Returns {source: station_id}; the input
        station's own source is not included.
        """
        matches: dict[str, str] = {}
        for name in SOURCES:
            if name == station.source:
                continue
            for other in self._source_map[name].list_stations():
                if station.gloss_id and other.gloss_id and station.gloss_id == other.gloss_id:
                    matches[name] = other.station_id
                    break
                if (
                    station.name
                    and other.name
                    and station.name.lower() in other.name.lower()
                    or other.name.lower() in station.name.lower()
                ) and (
                    station.latitude is not None
                    and other.latitude is not None
                    and station.longitude is not None
                    and other.longitude is not None
                    and abs(station.latitude - other.latitude) < 0.05
                    and abs(station.longitude - other.longitude) < 0.05
                ):
                    matches[name] = other.station_id
                    break
        return matches

    def trend(self, series: Series, ar1: bool = False) -> TrendResult:
        """Linear trend (mm/yr) with a 95% confidence interval."""
        return trend_mod.trend(series, ar1=ar1)

    def trend_annual(self, series: Series, ar1: bool = True) -> TrendResult:
        """Trend of the annual means of a series."""
        return trend_mod.trend_annual(series, ar1=ar1)

    @staticmethod
    def describe_datum(datum: str) -> str:
        """Human-readable annotation for a datum code."""
        return describe_datum(datum)

    @staticmethod
    def citation(source: str) -> str:
        """Citation string for a source."""
        return citation_for(source)

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in kilometres between two positions."""
        radius = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        return 2 * radius * math.asin(math.sqrt(a))
