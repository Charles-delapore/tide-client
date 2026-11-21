"""Per-source citation strings.

Every fetch returns a citation with its Series, so a figure or table
built from the data can attribute the source without extra work. The
wording follows each source's own data policy; DOIs were read from the
source pages on 2026-11-21, not from memory.
"""

from __future__ import annotations

from datetime import date


def _today() -> str:
    return date.today().isoformat()


def citation_psmsl() -> str:
    return (
        "Data from the Permanent Service for Mean Sea Level (PSMSL), "
        f"https://psmsl.org, accessed {_today()}. Please cite Holgate, S.J., "
        "Matthews, A., Woodworth, P.L., Rickards, L.J., Tamisiea, M.E., "
        "Bradshaw, E., Foden, P.R., Gordon, K.M. and Pugh, J. (2013), "
        "New Data Systems and Products at the Permanent Service for Mean "
        "Sea Level, Journal of Coastal Research 29(3), 493-504, "
        "doi:10.2112/JCOASTRES-D-12-00175.1."
    )


def citation_uhslc() -> str:
    return (
        "Data from the University of Hawaii Sea Level Center (UHSLC), "
        f"https://uhslc.soest.hawaii.edu, accessed {_today()}. Please cite "
        "Caldwell, P.C., Merrifield, M.A. and Thompson, P.R. (2015), Sea "
        "level measured by tide gauges from global oceans - the Joint "
        "Archive for Sea Level holdings (NCEI Accession 0019568), Version "
        "5.5, NOAA National Centers for Environmental Information, "
        "doi:10.7289/V5V40S7W."
    )


def citation_sonel() -> str:
    return (
        "Data from SONEL (Système d'Observation du Niveau des Eaux "
        "Littorales), https://www.sonel.org, "
        f"accessed {_today()}. Please follow the SONEL data policy "
        "(https://www.sonel.org/-Data-policy,88-.html) for attribution."
    )


def citation_noaa() -> str:
    return (
        "Data from NOAA Tides and Currents (CO-OPS), "
        "https://tidesandcurrents.noaa.gov, "
        f"accessed {_today()}."
    )


CITATIONS = {
    "psmsl": citation_psmsl,
    "uhslc": citation_uhslc,
    "sonel": citation_sonel,
    "noaa": citation_noaa,
}


def citation_for(source: str) -> str:
    """Return the citation string for a source name."""
    func = CITATIONS.get(source)
    if func is None:
        return f"Data from {source}."
    return func()
