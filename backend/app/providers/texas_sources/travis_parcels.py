import re

from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
    ProviderQueryRequest,
)


TRAVIS_PARCEL_DILIGENCE_FIELDS = (
    "OBJECTID",
    "PROP_ID",
    "py_owner_name",
    "situs_address",
    "situs_num",
    "situs_street",
    "situs_zip",
    "tcad_acres",
    "GIS_acres",
    "market_value",
    "appraised_val",
    "assessed_val",
    "land_type_desc",
    "legal_desc",
    "geo_id",
    "deed_date",
    "hyperlink",
)

TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS = ",".join(TRAVIS_PARCEL_DILIGENCE_FIELDS)

_ADDRESS_STOPWORDS = {
    "AUSTIN",
    "COUNTY",
    "ROAD",
    "STREET",
    "TEXAS",
    "TX",
    "BLVD",
    "BOULEVARD",
    "AVE",
    "AVENUE",
    "DR",
    "DRIVE",
    "LN",
    "LANE",
    "RD",
    "ST",
    "S",
    "N",
    "E",
    "W",
    "SUITE",
    "UNIT",
}


def _sql_string(value: str) -> str:
    return value.replace("'", "''")


def build_travis_parcel_site_request(site_context: str, limit: int = 5) -> ProviderQueryRequest | None:
    """Build a Travis parcel lookup from an address-like site context.

    Travis County's parcel layer stores the street number separately as `situs_num`.
    Matching it exactly avoids false positives such as 1201 matching 12014.
    """

    normalized = site_context.upper()
    street_number = re.search(r"\b\d{2,6}\b", normalized)
    if street_number and re.search(rf"\bTX\s+{street_number.group(0)}\b", normalized):
        street_number = None

    street_tokens = [
        token
        for token in re.findall(r"[A-Z]{2,}", normalized)
        if token not in _ADDRESS_STOPWORDS and not token.isdigit()
    ]

    if not street_number:
        return None

    clauses: list[str] = []
    clauses.append(f"situs_num = '{_sql_string(street_number.group(0))}'")

    for token in street_tokens[:2]:
        clauses.append(f"situs_address LIKE '%{_sql_string(token)}%'")

    if not clauses:
        return None

    return ProviderQueryRequest(
        where=" AND ".join(clauses),
        out_fields=TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS,
        limit=limit,
        return_geometry=True,
        params={"outSR": 4326},
    )


TRAVIS_COUNTY_PARCELS = DataProviderDefinition(
    id="travis_county_parcels",
    name="Travis County Parcels",
    concern=Concern.ZONING,
    kind=ProviderKind.ARCGIS_FEATURE_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(counties=["Travis"]),
    description="Travis County parcel FeatureServer for parcel geometry and appraisal-map attributes.",
    owner="Travis County",
    source_homepage="https://taxmaps.traviscountytx.gov/arcgis/rest/services/Parcels/FeatureServer",
    endpoints=[
        ProviderEndpoint(
            label="Parcel layer query",
            url="https://taxmaps.traviscountytx.gov/arcgis/rest/services/Parcels/FeatureServer/0/query",
            notes="Queryable DBO.Parcels layer.",
        )
    ],
    queryable=True,
    update_frequency="County-controlled operational GIS dataset.",
    limitations=[
        "Parcel data does not by itself prove zoning entitlement or data center permissibility.",
        "Zoning overlays may need city/ETJ-specific layers in addition to parcel geometry.",
        "Address matching uses Travis County situs fields and still needs parcel ID confirmation for legal diligence.",
    ],
    tags=["parcels", "travis-county", "zoning", "arcgis"],
)
