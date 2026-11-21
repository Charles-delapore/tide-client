"""Format parsers for the four sources.

Every parser works on text already fetched by the transport, so it is
unit-testable without network. Missing observations become NaN; the
source sentinel (-99999 for PSMSL/SONEL, empty string for NOAA) is
converted here, never leaked into the returned frame.
"""

from __future__ import annotations

import csv
import io
import math
import re
from datetime import date

import pandas as pd

MISSING = -99999


def _year_end_freq() -> str:
    """Year-end resample frequency across pandas versions.

    pandas 2.2 renamed "Y" to "YE" and pandas 3 removed "Y".
    """
    major, minor = (int(x) for x in pd.__version__.split(".")[:2])
    return "YE" if (major, minor) >= (2, 2) else "Y"


YE_FREQ = _year_end_freq()


def _decimal_year_to_date(value: float) -> pd.Timestamp:
    """Convert a PSMSL decimal year (mid-month, e.g. 1856.0417) to a date.

    PSMSL monthly values sit at the middle of the month: January is
    year + 0.5/12, February year + 1.5/12, and so on. The returned stamp
    is the first day of that month.
    """
    year = int(math.floor(value))
    frac = value - year
    month = int(round(frac * 12 - 0.5)) + 1
    month = max(1, min(12, month))
    return pd.Timestamp(year=year, month=month, day=1)


def parse_psmsl_monthly(text: str) -> pd.DataFrame:
    """Parse a PSMSL ``rlr.monthly.data`` file.

    Lines look like ``1856.0417;  6721; 0;000``: decimal year, RLR value
    in mm, days missing, flag. A value of -99999 means the month is
    missing (verified in the live New York file: 190 such rows).
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:
            continue
        try:
            dec_year = float(parts[0])
            value = float(parts[1])
        except ValueError:
            continue
        days_missing = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else None
        flag = parts[3] if len(parts) > 3 else ""
        rows.append(
            {
                "time": _decimal_year_to_date(dec_year),
                "value": float("nan") if value == MISSING else value,
                "days_missing": days_missing,
                "flag": flag,
            }
        )
    frame = pd.DataFrame(rows, columns=["time", "value", "days_missing", "flag"])
    if not frame.empty:
        frame = frame.set_index("time").sort_index()
    return frame


def parse_psmsl_annual(text: str) -> pd.DataFrame:
    """Parse a PSMSL ``rlr.annual.data`` file.

    Lines look like ``1856;  6698;N;000``: year, RLR value in mm, flag,
    flag. -99999 means the year is missing.
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:
            continue
        try:
            year = int(parts[0])
            value = float(parts[1])
        except ValueError:
            continue
        rows.append(
            {
                "time": pd.Timestamp(year=year, month=1, day=1),
                "value": float("nan") if value == MISSING else value,
                "flag": parts[2] if len(parts) > 2 else "",
                "flag2": parts[3] if len(parts) > 3 else "",
            }
        )
    frame = pd.DataFrame(rows, columns=["time", "value", "flag", "flag2"])
    if not frame.empty:
        frame = frame.set_index("time").sort_index()
    return frame


def parse_sonel_slv(text: str, decimal_date: bool = False) -> pd.DataFrame:
    """Parse a SONEL ``.slv`` mean-sea-level file.

    Lines look like ``1941-05-20\\t3782``: date, mean sea level in mm.
    With ``decimal_date`` the first field is ``YYYY.CCCC`` instead.
    Empty or non-numeric values become NaN; -99999 is also treated as
    missing, matching the PSMSL convention.
    """
    rows = []
    for line in text.splitlines():
        raw = line.rstrip("\r\n")
        if not raw.strip():
            continue
        parts = raw.split("\t") if "\t" in raw else raw.split()
        if len(parts) < 2:
            continue
        raw_date, raw_value = parts[0].strip(), parts[1].strip()
        try:
            if decimal_date:
                dec = float(raw_date)
                year = int(math.floor(dec))
                frac = dec - year
                month = int(round(frac * 12 - 0.5)) + 1
                month = max(1, min(12, month))
                stamp = pd.Timestamp(year=year, month=month, day=1)
            else:
                stamp = pd.Timestamp(raw_date)
        except (ValueError, TypeError):
            continue
        try:
            value = float(raw_value)
        except ValueError:
            value = float("nan")
        if value == MISSING:
            value = float("nan")
        rows.append({"time": stamp, "value": value})
    frame = pd.DataFrame(rows, columns=["time", "value"])
    if not frame.empty:
        frame = frame.set_index("time").sort_index()
    return frame


def parse_noaa_hourly(payload: dict) -> pd.DataFrame:
    """Parse a NOAA CO-OPS datagetter JSON reply for hourly_height.

    Records look like ``{"t": "2026-01-01 00:00", "v": "-1.049",
    "s": "0.033", "f": "0,0"}`` with values in metres; an empty ``v``
    means missing. Values are converted to millimetres here so every
    source in the library speaks the same unit.
    """
    rows = []
    for rec in payload.get("data", []):
        raw = (rec.get("v") or "").strip()
        try:
            value = float(raw) * 1000.0 if raw else float("nan")
        except ValueError:
            value = float("nan")
        try:
            stamp = pd.Timestamp(rec.get("t", ""))
        except (ValueError, TypeError):
            continue
        rows.append(
            {
                "time": stamp,
                "value": value,
                "sigma": float(rec["s"]) if rec.get("s") not in (None, "") else None,
                "flag": rec.get("f", ""),
            }
        )
    frame = pd.DataFrame(rows, columns=["time", "value", "sigma", "flag"])
    if not frame.empty:
        frame = frame.set_index("time").sort_index()
    return frame


def parse_noaa_monthly(payload: dict, datum: str = "MSL") -> pd.DataFrame:
    """Parse a NOAA CO-OPS monthly_mean reply.

    Records look like ``{"year": "2025", "month": "1", "MSL": "0.018",
    "MHHW": "0.896", ...}`` with values in metres for each datum. The
    requested datum column is read and converted to millimetres.
    """
    rows = []
    for rec in payload.get("data", []):
        try:
            year = int(rec["year"])
            month = int(rec["month"])
        except (KeyError, ValueError, TypeError):
            continue
        raw = (rec.get(datum) or "").strip()
        try:
            value = float(raw) * 1000.0 if raw else float("nan")
        except ValueError:
            value = float("nan")
        rows.append(
            {
                "time": pd.Timestamp(year=year, month=month, day=1),
                "value": value,
                "inferred": rec.get("inferred", ""),
            }
        )
    frame = pd.DataFrame(rows, columns=["time", "value", "inferred"])
    if not frame.empty:
        frame = frame.set_index("time").sort_index()
    return frame


def parse_erddap_csv(text: str) -> pd.DataFrame:
    """Parse an ERDDAP tabledap CSV reply.

    ERDDAP CSV has two header rows (variable names, then units). The
    first data column set is returned as-is; callers rename as needed.
    """
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r]
    if len(rows) < 3:
        return pd.DataFrame()
    header, units = rows[0], rows[1]
    frame = pd.DataFrame(rows[2:], columns=header)
    frame.attrs["units"] = dict(zip(header, units))
    return frame


def parse_psmsl_station_table(html: str) -> list[dict]:
    """Parse the PSMSL obtaining page station table.

    Rows look like
    ``<tr><td>NEW YORK (THE BATTERY)</td><td><a href="./stations/12.php">12</a>
    </td><td> 40.700</td><td> -74.013</td><td></td><td>USA</td>
    <td>27/01/2026</td><td> 960</td><td> 121</td></tr>``.
    Returns dicts with name, id, lat, lon, country, updated, gloss_id,
    coastline. Implemented with the stdlib HTML parser, no extra
    dependency.
    """
    from html.parser import HTMLParser

    class _TableParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.rows: list[list[str]] = []
            self.links: list[list[str]] = []
            self._row: list[str] | None = None
            self._cell: list[str] | None = None
            self._row_links: list[str] = []

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag == "tr":
                self._row = []
                self._row_links = []
            elif tag == "td" and self._row is not None:
                self._cell = []
            elif tag == "a" and self._row is not None:
                for key, val in attrs:
                    if key == "href":
                        self._row_links.append(val)

        def handle_data(self, data: str) -> None:
            if self._cell is not None:
                self._cell.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag == "td" and self._row is not None and self._cell is not None:
                self._row.append("".join(self._cell).strip())
                self._cell = None
            elif tag == "tr" and self._row is not None:
                self.rows.append(self._row)
                self.links.append(self._row_links)
                self._row = None

    parser = _TableParser()
    parser.feed(html)
    stations: list[dict] = []
    for cells, links in zip(parser.rows, parser.links):
        if len(cells) < 9:
            continue
        station_id = None
        for href in links:
            match = re.search(r"stations/(\d+)\.php", href)
            if match:
                station_id = match.group(1)
                break
        if station_id is None:
            continue
        try:
            lat = float(cells[2])
            lon = float(cells[3])
        except ValueError:
            lat, lon = None, None
        try:
            updated = date(int(cells[6].split("/")[2]), int(cells[6].split("/")[1]), int(cells[6].split("/")[0]))
        except (ValueError, IndexError):
            updated = None
        stations.append(
            {
                "name": cells[0],
                "id": station_id,
                "lat": lat,
                "lon": lon,
                "country": cells[5],
                "updated": updated,
                "gloss_id": cells[7] or None,
                "coastline": cells[8] or None,
            }
        )
    return stations
