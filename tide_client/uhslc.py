"""UHSLC adapter (University of Hawaii Sea Level Center, via ERDDAP).

Live endpoints verified 2026-11-21:
- ERDDAP datasets: https://uhslc.soest.hawaii.edu/erddap/tabledap/allDatasets.json
- fast delivery: global_hourly_fast / global_daily_fast
- research quality: global_hourly_rqds / global_daily_rqds
- GESLA: global_hourly_gesla

The legacy ``/data/download/fd/...`` file URLs return 404; ERDDAP
tabledap is the documented machine route (linked from the UHSLC data
portal navigation). Values are sea level in millimetres with a quality
flag. The single-source ``uhslc-station-tools`` package (0.0.208) loads
local files into a database and does not fetch from the web, so it is
not a substitute for this adapter.
"""

from __future__ import annotations

import urllib.parse

from tide_client import parsers
from tide_client.citations import citation_uhslc
from tide_client.exceptions import TideParseError, TideValidationError
from tide_client.models import Series, Station
from tide_client.transport import Transport

BASE = "https://uhslc.soest.hawaii.edu/erddap/tabledap/"

DATASETS = {
    ("hourly", "fast"): "global_hourly_fast",
    ("daily", "fast"): "global_daily_fast",
    ("hourly", "research"): "global_hourly_rqds",
    ("daily", "research"): "global_daily_rqds",
    ("hourly", "gesla"): "global_hourly_gesla",
}
INTERVALS = ("hourly", "daily")
QUALITIES = ("fast", "research", "gesla")


class UHSLCSource:
    """UHSLC fast-delivery and research-quality series via ERDDAP."""

    name = "uhslc"

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._stations: dict[str, list[Station]] = {}

    def _dataset(self, interval: str, quality: str) -> str:
        key = (interval, quality)
        if key not in DATASETS:
            raise TideValidationError(
                f"UHSLC has no {quality!r} dataset for interval {interval!r}; "
                f"use one of {sorted(DATASETS)}"
            )
        return DATASETS[key]

    def list_stations(
        self, interval: str = "daily", quality: str = "fast", refresh: bool = False
    ) -> list[Station]:
        cache_key = f"{interval}:{quality}"
        if cache_key in self._stations and not refresh:
            return self._stations[cache_key]
        dataset = self._dataset(interval, quality)
        url = (
            f"{BASE}{dataset}.csv"
            "?station_name,uhslc_id,latitude,longitude,station_country,"
            "reference_datum,gloss_id&distinct()"
        )
        text = self.transport.get_text(url)
        frame = parsers.parse_erddap_csv(text)
        stations: list[Station] = []
        if frame.empty:
            self._stations[cache_key] = stations
            return stations
        for _, row in frame.iterrows():
            try:
                station_id = str(int(float(row["uhslc_id"])))
            except (KeyError, ValueError, TypeError):
                continue
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (KeyError, ValueError, TypeError):
                lat, lon = None, None
            if lon is not None and lon > 180:  # ERDDAP reports 0..360 longitudes
                lon -= 360
            gloss = str(row.get("gloss_id", ""))
            if gloss in ("", "NaN", "nan"):
                gloss = None
            stations.append(
                Station(
                    source=self.name,
                    station_id=station_id,
                    name=str(row.get("station_name", "")),
                    latitude=lat,
                    longitude=lon,
                    country=str(row.get("station_country", "")) or None,
                    datum=str(row.get("reference_datum", "")) or None,
                    unit="mm",
                    gloss_id=gloss,
                    extra={"dataset": dataset},
                )
            )
        self._stations[cache_key] = stations
        return stations

    def get_series(
        self,
        station_id: str,
        interval: str = "daily",
        quality: str = "fast",
        start: str | None = None,
        end: str | None = None,
    ) -> Series:
        if interval not in INTERVALS:
            raise TideValidationError(f"UHSLC interval must be one of {INTERVALS}, got {interval!r}")
        if quality not in QUALITIES:
            raise TideValidationError(f"UHSLC quality must be one of {QUALITIES}, got {quality!r}")
        dataset = self._dataset(interval, quality)
        station = Station(
            source=self.name,
            station_id=str(station_id),
            name="",
            datum=None,
            unit="mm",
        )
        for known in self.list_stations(interval=interval, quality=quality):
            if known.station_id == str(station_id):
                station = known
                break
        variables = "station_name,uhslc_id,time,sea_level,quality,latitude,longitude"
        query = f"{BASE}{dataset}.csv?{variables}"
        # uhslc_id is numeric in ERDDAP: a quoted string constraint ("57")
        # returns HTTP 400, an unquoted number works.
        try:
            station_num = int(station_id)
        except (TypeError, ValueError) as exc:
            raise TideValidationError(f"UHSLC station id must be numeric, got {station_id!r}") from exc
        query += f"&uhslc_id={station_num}"
        if start:
            query += f"&time%3E={urllib.parse.quote(start)}"
        if end:
            query += f"&time%3C={urllib.parse.quote(end)}"
        query += '&orderBy(%22time%22)'
        text = self.transport.get_text(query)
        raw = parsers.parse_erddap_csv(text)
        if raw.empty:
            raise TideParseError(f"UHSLC returned no rows for station {station_id!r}")
        import pandas as pd

        frame = pd.DataFrame(
            {
                "time": pd.to_datetime(raw["time"], utc=True, errors="coerce"),
                "value": pd.to_numeric(raw["sea_level"], errors="coerce"),
                "quality": pd.to_numeric(raw["quality"], errors="coerce"),
            }
        ).dropna(subset=["time"])
        frame = frame.set_index("time").sort_index()
        return Series(
            station=station,
            source=self.name,
            interval=interval,
            datum=station.datum or "UHSLC reference datum",
            unit="mm",
            data=frame,
            citation=citation_uhslc(),
            quality=quality,
        )
