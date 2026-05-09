from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


TWDB_WATER_DATA_FOR_TEXAS = DataProviderDefinition(
    id="twdb_water_data_for_texas",
    name="TWDB Water Data for Texas",
    concern=Concern.WATER,
    kind=ProviderKind.OPEN_DATA_PORTAL,
    capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "Texas Water Development Board water data portal for reservoirs, drought, "
        "groundwater wells, water levels, and related statewide water context."
    ),
    owner="Texas Water Development Board",
    source_homepage="https://www.waterdatafortexas.org/",
    endpoints=[
        ProviderEndpoint(
            label="Water Data for Texas",
            url="https://www.waterdatafortexas.org/",
            notes="Statewide portal for water data products.",
        ),
        ProviderEndpoint(
            label="TWDB groundwater data",
            url="https://www.twdb.texas.gov/groundwater/data/index.asp",
            notes="Groundwater database and water-level/water-quality data documentation.",
        ),
    ],
    queryable=False,
    update_frequency="Varies by dataset.",
    limitations=[
        "Provider is registered as catalog metadata until dataset-specific API paths are pinned.",
        "Water availability for a data center requires utility confirmation beyond public water data.",
    ],
    tags=["twdb", "water", "groundwater", "reservoirs", "texas"],
)
