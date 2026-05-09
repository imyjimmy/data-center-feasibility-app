from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
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
    ],
    tags=["parcels", "travis-county", "zoning", "arcgis"],
)
