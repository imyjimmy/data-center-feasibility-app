from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


AUSTIN_WATER_UTILITY_SERVICE_AREA = DataProviderDefinition(
    id="austin_water_utility_service_area",
    name="Austin Water Utility Service Area",
    concern=Concern.WATER,
    kind=ProviderKind.ARCGIS_FEATURE_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(counties=["Travis"], municipalities=["Austin"]),
    description="City of Austin ArcGIS feature service for Austin Water service area boundaries.",
    owner="City of Austin / Austin Water",
    source_homepage="https://www.arcgis.com/home/item.html?id=da0a5e49a603496c9272a92233981c1b",
    endpoints=[
        ProviderEndpoint(
            label="Feature service layer 0 query",
            url=(
                "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/"
                "Austin_Water_Utility_Service_Area/FeatureServer/0/query"
            ),
            notes="Queryable ArcGIS FeatureServer layer for service-area geometry.",
        ),
        ProviderEndpoint(
            label="Austin Property Profile water map",
            url="https://maps.austintexas.gov/gis/rest/PropertyProfile/AustinWater/MapServer",
            notes="MapServer alternative with Austin Water Service Area as layer 3.",
        ),
    ],
    queryable=True,
    update_frequency="ArcGIS item metadata shows item updates; operational cadence is City of Austin controlled.",
    limitations=[
        "Informational GIS product; not a legal engineering or surveying determination.",
        "Capacity must still be confirmed directly with Austin Water.",
    ],
    tags=["water", "austin", "service-area", "arcgis"],
)
