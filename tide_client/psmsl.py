"""PSMSL adapter (Permanent Service for Mean Sea Level).

Live endpoints verified 2026-11-21:
- station list: https://psmsl.org/data/obtaining/ (HTML table, 2400+ rows)
- monthly RLR: https://psmsl.org/data/obtaining/rlr.monthly.data/{id}.rlrdata
- annual RLR:  https://psmsl.org/data/obtaining/rlr.annual.data/{id}.rlrdata
- station page: https://psmsl.org/data/obtaining/stations/{id}.php

Values are Revised Local Reference (RLR) heights in millimetres.
The old ``rlr_monthly.php`` / ``rlr_data.php`` endpoints return 404 and
are not used.
"""

from __future__ import annotations

from tide_client import parsers
from tide_client.citations import citation_psmsl
from tide_client.exceptions import TideValidationError
from tide_client.models import Series, Station
from tide_client.transport import Transport

BASE = "https://psmsl.org/data/obtaining/"
DATUM = "RLR (Revised Local Reference)"
INTERVALS = ("monthly", "annual")


class PSMSLSource:
    """PSMSL monthly and annual RLR series."""

    name = "psmsl"

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._stations: list[Station] | None = None

    def list_stations(self, refresh: bool = False) -> list[Station]:
        if self._stations is not None and not refresh:
            return self._stations
        html = self.transport.get_text(BASE)
        rows = parsers.parse_psmsl_station_table(html)
        stations = [
            Station(
                source=self.name,
                station_id=row["id"],
                name=row["name"],
                latitude=row["lat"],
                longitude=row["lon"],
                country=row["country"] or None,
                datum=DATUM,
                unit="mm",
                end=row["updated"],
                gloss_id=row["gloss_id"],
            )
            for row in rows
        ]
        self._stations = stations
        return stations

    def get_station(self, station_id: str) -> Station:
        for station in self.list_stations():
            if station.station_id == str(station_id):
                return station
        raise TideValidationError(f"no PSMSL station with id {station_id!r}")

    def get_series(self, station_id: str, interval: str = "monthly") -> Series:
        if interval not in INTERVALS:
            raise TideValidationError(f"PSMSL interval must be one of {INTERVALS}, got {interval!r}")
        station = self.get_station(station_id)
        subdir = "rlr.monthly.data" if interval == "monthly" else "rlr.annual.data"
        text = self.transport.get_text(f"{BASE}{subdir}/{station_id}.rlrdata")
        if interval == "monthly":
            frame = parsers.parse_psmsl_monthly(text)
        else:
            frame = parsers.parse_psmsl_annual(text)
        return Series(
            station=station,
            source=self.name,
            interval=interval,
            datum=DATUM,
            unit="mm",
            data=frame,
            citation=citation_psmsl(),
        )
