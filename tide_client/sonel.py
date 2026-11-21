"""SONEL adapter (Système d'Observation du Niveau des Eaux Littorales).

Live endpoints verified 2026-11-21:
- station list: https://www.sonel.org/squelettes/outils/getdatamaps.php?page=1
  (GeoJSON, 1108 features; sta_id, sta_name, sta_acro, sta_pays, sta_lon, sta_lat)
- station page: https://www.sonel.org/spip.php?page=maregraphe&idStation={id}
- validated data: POST https://www.sonel.org/ajaxJson.php
  {a: "getUrlMSLValidatedData", type: "Demerliac"|"Doodson",
   name: "{d|m|y}{CODE}.slv"} -> {"success": true, "url": "msl/.../dLROCH.slv"}
- data file: https://www.sonel.org/msl/Demerliac/VALIDATED/dLROCH.slv
  (tab-separated ``YYYY-MM-DD\\tvalue`` in mm; monthly mCODE.slv, annual yCODE.slv)

SONEL publishes no stable public REST API; this adapter follows the
site's own download flow (the same POST the station page's "Download
this validated data" button makes). If SONEL changes that flow, the
adapter raises a clear error instead of silently returning wrong data.
"""

from __future__ import annotations

from tide_client import parsers
from tide_client.citations import citation_sonel
from tide_client.exceptions import TideParseError, TideValidationError
from tide_client.models import Series, Station
from tide_client.transport import Transport

BASE = "https://www.sonel.org/"
MAP_URL = BASE + "squelettes/outils/getdatamaps.php?page=1"
AJAX_URL = BASE + "ajaxJson.php"
DATUM = "MSL (relative to tide-gauge zero)"
INTERVALS = {"daily": "d", "monthly": "m", "annual": "y"}
FILTERS = ("Demerliac", "Doodson")


class SONELSource:
    """SONEL validated mean-sea-level series (daily, monthly, annual)."""

    name = "sonel"

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._stations: list[Station] | None = None

    def list_stations(self, refresh: bool = False) -> list[Station]:
        if self._stations is not None and not refresh:
            return self._stations
        payload = self.transport.get_json(MAP_URL)
        stations: list[Station] = []
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            try:
                station_id = str(int(props["sta_id"]))
            except (KeyError, ValueError, TypeError):
                continue
            try:
                lat = float(props["sta_lat"])
                lon = float(props["sta_lon"])
            except (KeyError, ValueError, TypeError):
                lat, lon = None, None
            stations.append(
                Station(
                    source=self.name,
                    station_id=station_id,
                    name=str(props.get("sta_name", "")),
                    code=str(props.get("sta_acro", "")) or None,
                    latitude=lat,
                    longitude=lon,
                    country=str(props.get("sta_pays", "")) or None,
                    datum=DATUM,
                    unit="mm",
                    extra={"sta_type": props.get("sta_type"), "sta_etat": props.get("sta_etat")},
                )
            )
        self._stations = stations
        return stations

    def _resolve_code(self, station: str) -> tuple[str, Station]:
        """Return (station code, Station) for an id or a code."""
        for known in self.list_stations():
            if known.station_id == str(station):
                if not known.code:
                    raise TideValidationError(f"SONEL station {station!r} has no station code")
                return known.code, known
            if known.code and known.code.upper() == str(station).upper():
                return known.code, known
        raise TideValidationError(f"no SONEL station with id or code {station!r}")

    def get_series(
        self,
        station: str,
        interval: str = "daily",
        filter_name: str = "Demerliac",
        decimal_date: bool = False,
    ) -> Series:
        if interval not in INTERVALS:
            raise TideValidationError(
                f"SONEL interval must be one of {sorted(INTERVALS)}, got {interval!r}"
            )
        if filter_name not in FILTERS:
            raise TideValidationError(
                f"SONEL filter must be one of {FILTERS}, got {filter_name!r}"
            )
        code, station_obj = self._resolve_code(station)
        prefix = INTERVALS[interval]
        suffix = "_dec.slv" if decimal_date else ".slv"
        name = f"{prefix}{code}{suffix}"
        reply = self.transport.post_form(
            AJAX_URL,
            {"a": "getUrlMSLValidatedData", "type": filter_name, "name": name},
        )
        if not reply.get("success") or not reply.get("url"):
            raise TideParseError(
                f"SONEL could not resolve a download URL for {name!r}: {reply}"
            )
        url = reply["url"]
        if not url.startswith("http"):
            url = BASE + url.lstrip("/")
        text = self.transport.get_text(url)
        frame = parsers.parse_sonel_slv(text, decimal_date=decimal_date)
        return Series(
            station=station_obj,
            source=self.name,
            interval=interval,
            datum=DATUM,
            unit="mm",
            data=frame,
            citation=citation_sonel(),
        )
