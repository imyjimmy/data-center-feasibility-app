from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


TEXAS_OPEN_DATA_PROVIDERS = [
    DataProviderDefinition(
        id="ercot_market_data_transparency",
        name="ERCOT Market Data Transparency",
        concern=Concern.POWER_STRESS,
        kind=ProviderKind.REST_API,
        capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
        coverage=ProviderCoverage(),
        description=(
            "ERCOT public market reports and API explorer for grid and market conditions. "
            "Use for power stress proxies such as real-time pricing, load, congestion, "
            "and market notices once report-specific endpoints are selected."
        ),
        owner="Electric Reliability Council of Texas",
        source_homepage="https://www.ercot.com/services/mdt/data-portal",
        endpoints=[
            ProviderEndpoint(
                label="Data Access Portal",
                url="https://www.ercot.com/services/mdt/data-portal",
                notes="Search and download public ERCOT reports; API access is report-specific.",
            ),
            ProviderEndpoint(
                label="Market Data Transparency",
                url="https://www.ercot.com/services/mdt/",
                notes="Documentation hub for ERCOT market data applications and API explorer.",
            ),
        ],
        queryable=False,
        authentication="ERCOT public API registration may be required for API access.",
        update_frequency="Varies by ERCOT report; real-time reports may update intra-day.",
        limitations=[
            "This app has not pinned a specific ERCOT report endpoint yet.",
            "Some ERCOT API usage requires registration/authentication.",
        ],
        tags=["ercot", "power", "market", "texas"],
    ),
    DataProviderDefinition(
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
    ),
    DataProviderDefinition(
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
    ),
    DataProviderDefinition(
        id="texas_broadband_development_map",
        name="Texas Broadband Development Map",
        concern=Concern.FIBER_AVAILABILITY,
        kind=ProviderKind.WEB_MAP,
        capabilities=[ProviderCapability.SOURCE_METADATA],
        coverage=ProviderCoverage(),
        description=(
            "Texas Broadband Development Office map and documentation for broadband availability. "
            "Useful for fiber/broadband availability context and eligibility screening."
        ),
        owner="Texas Comptroller Broadband Development Office",
        source_homepage="https://comptroller.texas.gov/programs/broadband/outreach/maps/",
        endpoints=[
            ProviderEndpoint(
                label="Broadband Development Maps",
                url="https://comptroller.texas.gov/programs/broadband/outreach/maps/",
                notes="Texas BDO explains map methodology and links to relevant coverage maps.",
            ),
            ProviderEndpoint(
                label="FCC National Broadband Map guidance from Texas BDO",
                url="https://comptroller.texas.gov/programs/broadband/outreach/maps/fcc/",
                notes="Texas BDO guidance for location-level FCC broadband map usage.",
            ),
        ],
        queryable=False,
        update_frequency="Texas BDO describes updates based on FCC BDC cycles and program updates.",
        limitations=[
            "Texas BDO states granular Texas map data is proprietary and cannot be downloaded due to FCC restrictions.",
            "Fiber availability for commercial data centers still requires carrier outreach.",
        ],
        tags=["broadband", "fiber", "bdo", "texas"],
    ),
    DataProviderDefinition(
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
    ),
    DataProviderDefinition(
        id="texas_real_estate_research_center",
        name="Texas Real Estate Research Center",
        concern=Concern.ICP,
        kind=ProviderKind.CONTACT_DIRECTORY,
        capabilities=[ProviderCapability.SOURCE_METADATA, ProviderCapability.CONTACT_LOOKUP],
        coverage=ProviderCoverage(),
        description=(
            "Texas public university real-estate research source for market context. "
            "This is a source for commercial real-estate market intelligence, not a parcel utility feed."
        ),
        owner="Texas Real Estate Research Center at Texas A&M University",
        source_homepage="https://trerc.tamu.edu/",
        endpoints=[
            ProviderEndpoint(
                label="Texas Real Estate Research Center",
                url="https://trerc.tamu.edu/",
                notes="Market reports, research, and contact routes for Texas real-estate context.",
            )
        ],
        queryable=False,
        limitations=[
            "Commercial broker or land-owner outreach is not an open-data API.",
            "Use this as an ICP/source category until a CRM/contact provider is configured.",
        ],
        tags=["real-estate", "icp", "commercial", "texas"],
    ),
    DataProviderDefinition(
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
    ),
]
