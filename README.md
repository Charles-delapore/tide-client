# tide-client

Unified tide-gauge and sea-level time-series client for **PSMSL**, **UHSLC**,
**SONEL** and **NOAA CO-OPS**. One call searches stations across sources,
one call fetches a series, and every series comes back as a pandas
DataFrame in millimetres with its datum and citation attached.

This fills the gap found in the 2026-11-21 new-library survey: PSMSL
(2400+ stations) had no Python client at all, only an R package; UHSLC
had only a single-source tool; SONEL and NOAA each stood alone. There is
still no maintained multi-source client besides this one.

## Install

```bash
pip install tide-client
```

Python 3.10+. Dependencies: `requests`, `pandas`. `xarray` is optional
(`pip install tide-client[xarray]`) for `Series.to_xarray()`.

## Quick start

```python
from tide_client import TideClient

client = TideClient()

# find stations by name across all four sources
stations = client.search_stations("Honolulu")
for st in stations:
    print(st.source, st.station_id, st.name, st.latitude, st.longitude)

# PSMSL monthly RLR series, New York (The Battery), station 12
series = client.get_series("12", source="psmsl", interval="monthly")
print(series.data.head())
print(series.citation)

# UHSLC fast-delivery daily series, Honolulu (UHSLC id 57)
uh = client.get_series("57", source="uhslc", interval="daily",
                        start="2025-01-01", end="2025-12-31")

# SONEL validated daily means, La Rochelle (station 1787, code LROCH)
so = client.get_series("1787", source="sonel", interval="daily")

# NOAA hourly heights, San Francisco, MSL datum
no = client.get_series("9414290", source="noaa", interval="hourly",
                        datum="MSL", start="2026-01-01", end="2026-01-02")

# trend of the annual means, AR(1)-adjusted 95% CI
result = client.trend_annual(series)
print(result)  # TrendResult(slope=... mm/yr, 95% CI [...], n=..., method='ols-ar1')

# same physical gauge in the other sources
print(client.cross_reference(stations[0]))
```

## Sources

| Source | What it serves | Intervals | Datum | Key |
|---|---|---|---|---|
| PSMSL | Monthly / annual RLR means, 2400+ stations | monthly, annual | RLR (mm) | none |
| UHSLC | Fast-delivery / research-quality / GESLA via ERDDAP | hourly, daily | station reference datum (mm) | none |
| SONEL | Validated mean sea level, 1108 stations | daily, monthly, annual | MSL relative to gauge zero (mm) | none |
| NOAA CO-OPS | Water levels, 303 US stations | hourly, daily, monthly, annual | selectable (MSL default) | none |

No source needs an API key. If a source starts requiring one, it will
come from an environment variable, never from code or logs.

All values are returned in **millimetres**. NOAA reports metres and is
converted on parse. Missing observations are NaN: PSMSL and SONEL use
the -99999 sentinel, NOAA uses an empty value string.

Notes per source:

- **PSMSL.** Station list is the obtaining page HTML table; series are
  the `.rlrdata` files (`rlr.monthly.data` / `rlr.annual.data`). The old
  `rlr_monthly.php` / `rlr_data.php` endpoints return 404 and are not
  used. RLR values from different stations are not comparable as
  absolute heights.
- **UHSLC.** Served through the ERDDAP tabledap API
  (`global_hourly_fast`, `global_daily_fast`, `global_hourly_rqds`,
  `global_daily_rqds`, `global_hourly_gesla`). The legacy
  `/data/download/fd/...` file URLs return 404. `quality="fast"` is the
  default; use `"research"` for the quality-controlled archive.
- **SONEL.** No stable public REST API exists. The adapter follows the
  site's own download flow: station list from the map GeoJSON feed,
  then a POST to `ajaxJson.php` that resolves the `.slv` file URL
  (daily `dCODE.slv`, monthly `mCODE.slv`, annual `yCODE.slv`; filter
  Demerliac by default, Doodson on request). If SONEL changes that
  flow, the adapter fails loudly instead of returning wrong data.
- **NOAA.** `hourly_height` and `monthly_mean` products of the
  datagetter API. Daily means are hourly values resampled to daily
  means, because the `daily_mean` product is Great Lakes only and
  returns 400 for coastal stations. Annual means are monthly means
  resampled to annual means.

## Datums

Every `Series` carries a `datum` string; `client.describe_datum(code)`
explains it. PSMSL RLR is a local reference about 7000 mm below mean
sea level, chosen per station so the series stays positive. NOAA
datums are selectable per call (`MSL`, `MLLW`, `MHHW`, `MLW`, `MHW`,
`MTL`, `NAVD88`, `STND`, ...).

## Caching

Pass `cache_dir` to cache raw responses on disk, keyed by URL hash:

```python
client = TideClient(cache_dir="~/.cache/tide-client")
```

The cache only avoids re-downloading what you already fetched. The
library ships no data and never redistributes upstream files. Clear it
with `tide_client.cache.clear_cache()`.

## Citation

Every `Series` has a `citation` attribute. Cite the source's data
paper when you publish results built from it:

- PSMSL: Holgate et al. (2013), J. Coastal Res. 29(3), 493-504,
  doi:10.2112/JCOASTRES-D-12-00175.1
- UHSLC / JASL: Caldwell, Merrifield & Thompson (2015), NCEI Accession
  0019568, doi:10.7289/V5V40S7W
- SONEL: follow the SONEL data policy
  (https://www.sonel.org/-Data-policy,88-.html)
- NOAA: NOAA Tides and Currents (CO-OPS),
  https://tidesandcurrents.noaa.gov

## Development

```bash
python -m unittest discover -s tests -v
```

Tests are offline: HTTP is mocked and fixtures are small real captures
(a few rows each) from the live services, taken 2026-11-21.

## License

MIT. Copyright 2026 Charles-delapore.
