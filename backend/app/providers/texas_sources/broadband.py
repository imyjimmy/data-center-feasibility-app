from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


TEXAS_BROADBAND_DEVELOPMENT_MAP = DataProviderDefinition(
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
)
