from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
)


TEXAS_REAL_ESTATE_RESEARCH_CENTER = DataProviderDefinition(
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
)
