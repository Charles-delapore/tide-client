"""NOAA CO-OPS adapter (tidesandcurrents.noaa.gov).

Live endpoints verified 2026-11-21:
- stations: https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json
  (303 stations; id, name, lat, lng, state, timezone, tidal, products)
- data: https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
  (no key; products hourly_height and monthly_mean verified live)

Intervals: hourly -> hourly_height; monthly -> monthly_mean (the datum
column of each month record); daily -> hourly_height resampled to daily
means (the datagetter ``daily_mean`` product is Great Lakes only and
returns 400 for coastal stations); annual -> monthly_mean resampled to
annual means. All values are converted to millimetres so every source
in the library speaks the same unit; the source unit is metres.
"""

from __future__ import annotations

import pandas as pd

from tide_client import parsers
from tide_client.citations import citation_noaa
from tide_client.exceptions import TideValidationError
from tide_client.models import Series, Station
from tide_client.transport import Transport

MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/"
DATAGETTER = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
INTERVALS = ("hourly", "daily", "monthly", "annual")
DATUMS = (
    "MSL",
    "MLLW",
    "MHHW",
    "MLW",
    "MHW",
    "MTL",
    "NAVD88",
    "STND",
    "LWI",
    "HWI",
)


class NOAASource:
    """NOAA CO-OPS water-level series."""

    name = "noaa"

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._stations: list[Station] | None = None

    def list_stations(self, refresh: bool = False) -> list[Station]:
        if self._stations is not None and not refresh:
            return self._stations
        payload = self.transport.get_json(MDAPI + "stations.json")
        stations: list[Station] = []
        for rec in payload.get("stations", []):
            try:
                station_id = str(int(rec["id"]))
            except (KeyError, ValueError, TypeError):
                continue
            try:
                lat = float(rec["lat"])
                lon = float(rec["lng"])
            except (KeyError, ValueError, TypeError):
                lat, lon = None, None
            stations.append(
                Station(
                    source=self.name,
                    station_id=station_id,
                    name=str(rec.get("name", "")),
                    latitude=lat,
                    longitude=lon,
                    country="USA" if rec.get("state") else None,
                    datum="MSL",
                    unit="mm",
                    extra={
                        "state": rec.get("state"),
                        "timezone": rec.get("timezone"),
                        "tidal": rec.get("tidal"),
                        "greatlakes": rec.get("greatlakes"),
                    },
                )
            )
        self._stations = stations
        return stations

    def get_station(self, station_id: str) -> Station:
        for station in self.list_stations():
            if station.station_id == str(station_id):
                return station
        raise TideValidationError(f"no NOAA station with id {station_id!r}")

    def _datagetter(
        self,
        station_id: str,
        product: str,
        datum: str,
        start: str,
        end: str,
    ) -> dict:
        params = {
            "begin_date": start.replace("-", ""),
            "end_date": end.replace("-", ""),
            "station": str(station_id),
            "product": product,
            "datum": datum,
            "units": "metric",
            "time_zone": "gmt",
            "application": "tide-client",
            "format": "json",
        }
        return self.transport.get_json(DATAGETTER, params=params)

    def get_series(
        self,
        station_id: str,
        interval: str = "hourly",
        datum: str = "MSL",
        start: str | None = None,
        end: str | None = None,
    ) -> Series:
        if interval not in INTERVALS:
            raise TideValidationError(f"NOAA interval must be one of {INTERVALS}, got {interval!r}")
        if datum not in DATUMS:
            raise TideValidationError(f"NOAA datum must be one of {DATUMS}, got {datum!r}")
        station = self.get_station(station_id)
        if interval in ("hourly", "daily"):
            if start is None or end is None:
                raise TideValidationError(
                    "NOAA hourly and daily series need start and end dates (YYYY-MM-DD)"
                )
            payload = self._datagetter(station_id, "hourly_height", datum, start, end)
            frame = parsers.parse_noaa_hourly(payload)
            if interval == "daily":
                frame = frame.resample("D")["value"].mean().to_frame()
                frame = frame.dropna(subset=["value"])
        else:
            if start is None or end is None:
                raise TideValidationError(
                    "NOAA monthly and annual series need start and end dates (YYYY-MM-DD)"
                )
            payload = self._datagetter(station_id, "monthly_mean", datum, start, end)
            frame = parsers.parse_noaa_monthly(payload, datum=datum)
            if interval == "annual":
                frame = frame.resample(parsers.YE_FREQ)["value"].mean().to_frame()
                frame = frame.dropna(subset=["value"])
                frame.index = frame.index.normalize().to_period("Y").to_timestamp()
        return Series(
            station=station,
            source=self.name,
            interval=interval,
            datum=datum,
            unit="mm",
            data=frame,
            citation=citation_noaa(),
        )
