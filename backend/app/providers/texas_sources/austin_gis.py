from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


AUSTIN_ZONING = DataProviderDefinition(
    id="austin_zoning",
    name="City of Austin Zoning",
    concern=Concern.ZONING,
    kind=ProviderKind.ARCGIS_MAP_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(counties=["Travis"], municipalities=["Austin"]),
    description="City of Austin zoning layer for zoning district text and entitlement-screening context.",
    owner="City of Austin",
    source_homepage="https://maps.austintexas.gov/gis/rest/Shared/Zoning_2/MapServer",
    endpoints=[
        ProviderEndpoint(
            label="Zoning Text query",
            url="https://maps.austintexas.gov/arcgis/rest/services/Shared/Zoning_1/MapServer/1/query",
            notes="Queryable zoning text layer. Use spatial intersection with parcel centroids for screening.",
        )
    ],
    queryable=True,
    limitations=[
        "Zoning district text does not by itself prove data-center use permissibility.",
        "Overlay districts, conditional overlays, compatibility standards, and site-plan requirements still need code review.",
    ],
    tags=["austin", "zoning", "entitlements", "arcgis"],
)


AUSTIN_JURISDICTION = DataProviderDefinition(
    id="austin_jurisdiction",
    name="City of Austin Jurisdiction and ETJ",
    concern=Concern.ZONING,
    kind=ProviderKind.ARCGIS_MAP_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(counties=["Travis"], municipalities=["Austin"]),
    description="City of Austin jurisdiction and regulatory boundary layer for city-limit and ETJ screening.",
    owner="City of Austin",
    source_homepage="https://maps.austintexas.gov/arcgis/rest/services/Shared/JurisdictionsFill/MapServer",
    endpoints=[
        ProviderEndpoint(
            label="Jurisdiction boundary query",
            url="https://maps.austintexas.gov/arcgis/rest/services/Shared/JurisdictionsFill/MapServer/0/query",
            notes="Queryable jurisdiction polygons including full purpose, limited purpose, and ETJ categories.",
        )
    ],
    queryable=True,
    limitations=[
        "Jurisdiction boundaries are approximate GIS screening data and not a legal survey.",
        "Entitlement path still depends on parcel facts, zoning, overlays, utilities, and current code requirements.",
    ],
    tags=["austin", "jurisdiction", "etj", "city-limits", "arcgis"],
)


AUSTIN_ENERGY_SERVICE_AREA = DataProviderDefinition(
    id="austin_energy_service_area",
    name="Austin Energy Electric Service Area",
    concern=Concern.POWER_STRESS,
    kind=ProviderKind.ARCGIS_MAP_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(counties=["Travis"], municipalities=["Austin"]),
    description="Austin Energy electric utility service area boundary for preliminary serving-utility screening.",
    owner="City of Austin / Austin Energy",
    source_homepage="https://maps.austintexas.gov/gis/rest/Shared/BoundariesGrids_2/MapServer",
    endpoints=[
        ProviderEndpoint(
            label="Austin Energy Utility Service Area query",
            url="https://maps.austintexas.gov/gis/rest/Shared/BoundariesGrids_2/MapServer/1/query",
            notes="Queryable Austin Energy service-area polygon layer.",
        )
    ],
    queryable=True,
    limitations=[
        "Service-area presence does not prove 25 MW capacity, feeder availability, substation capacity, or interconnection timeline.",
        "Serving utility and interconnection path must be confirmed with Austin Energy or the applicable TSP.",
    ],
    tags=["austin-energy", "electric", "service-area", "power", "arcgis"],
)


ELECTRIC_POWER_TRANSMISSION_LINES = DataProviderDefinition(
    id="electric_power_transmission_lines",
    name="Electric Power Transmission Lines",
    concern=Concern.POWER_STRESS,
    kind=ProviderKind.ARCGIS_FEATURE_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description="Public transmission-line GIS layer for high-level proximity screening near candidate parcels.",
    owner="Homeland Infrastructure Foundation-Level Data / ArcGIS public data",
    source_homepage="https://services2.arcgis.com/1cdV1mIckpAyI7Wo/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer",
    endpoints=[
        ProviderEndpoint(
            label="Transmission line query",
            url="https://services2.arcgis.com/1cdV1mIckpAyI7Wo/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0/query",
            notes="Queryable public transmission-line features. Use as proximity proxy only.",
        )
    ],
    queryable=True,
    limitations=[
        "Transmission-line proximity is only a proxy; it does not prove available capacity, interconnection feasibility, voltage suitability, or right-of-way access.",
        "Feature freshness and ownership should be verified before investment decisions.",
    ],
    tags=["transmission", "power", "proximity", "arcgis"],
)
