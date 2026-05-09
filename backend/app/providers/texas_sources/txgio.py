from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


TXGIO_GEOSPATIAL_CATALOG = DataProviderDefinition(
    id="txgio_geospatial_catalog",
    name="Texas Geographic Information Office Data Catalog",
    concern=Concern.PARCEL_GEOCODING,
    kind=ProviderKind.OPEN_DATA_PORTAL,
    capabilities=[ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "Texas Geographic Information Office/TWDB geospatial catalog for statewide GIS datasets. "
        "Use as the Texas-government replacement category for geospatial lookup inputs before "
        "adding a licensed geocoder."
    ),
    owner="Texas Geographic Information Office / Texas Water Development Board",
    source_homepage="https://tnris.org/about.html",
    endpoints=[
        ProviderEndpoint(
            label="TxGIO overview",
            url="https://tnris.org/about.html",
            notes="TxGIO is a TWDB division and state GIS resource.",
        ),
        ProviderEndpoint(
            label="Texas Open Data Portal",
            url="https://data.texas.gov/",
            notes="Official state open-data portal linking statewide and local Texas data sites.",
        ),
    ],
    queryable=False,
    limitations=[
        "This is not a direct OpenCage replacement; it catalogs authoritative Texas geospatial sources.",
        "Address-level geocoding may still require a configured geocoder, but source preference is Texas open data.",
    ],
    tags=["geocoding", "txgio", "tnris", "open-data", "texas"],
)
