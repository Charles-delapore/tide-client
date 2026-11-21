"""Datum annotations.

Sea-level series only mean something against a stated reference. This
module records what each source's datum is, in the source's own terms,
so a Series always carries a human-readable datum string.
"""

DATUMS: dict[str, str] = {
    "RLR": (
        "Revised Local Reference (PSMSL). Each station's RLR datum is a "
        "local reference about 7000 mm below mean sea level, chosen so the "
        "series stays positive; values from different stations are not "
        "directly comparable as absolute heights."
    ),
    "MSL": (
        "Mean sea level. For NOAA this is the datum selected in the "
        "datagetter call; for SONEL it is the mean sea level relative to "
        "the tide-gauge zero."
    ),
    "MLLW": "Mean lower low water (NOAA tidal datum).",
    "MHHW": "Mean higher high water (NOAA tidal datum).",
    "MLW": "Mean low water (NOAA tidal datum).",
    "MHW": "Mean high water (NOAA tidal datum).",
    "MTL": "Mean tide level (NOAA tidal datum).",
    "NAVD88": "North American Vertical Datum of 1988 (NOAA).",
    "STND": "Station datum (NOAA).",
    "LWI": "Low water interval datum (NOAA monthly_mean field).",
    "HWI": "High water interval datum (NOAA monthly_mean field).",
    "UHSLC": (
        "UHSLC reference datum, reported per station by the ERDDAP "
        "dataset (reference_datum). Fast-delivery values are relative to "
        "the station reference; research-quality values are quality "
        "controlled against the same reference."
    ),
}


def describe(datum: str) -> str:
    """Return the annotation for a datum code, or the code itself."""
    key = datum.split(" ")[0].upper()
    return DATUMS.get(key, datum)
