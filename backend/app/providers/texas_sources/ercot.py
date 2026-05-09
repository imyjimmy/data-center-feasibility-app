from typing import Any

from app.providers.client import ProviderHttpClient
from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
    ProviderQueryResponse,
)


ERCOT_MARKET_DATA_TRANSPARENCY = DataProviderDefinition(
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
            label="ERCOT Grid Conditions dashboard JSON",
            url="https://www.ercot.com/api/1/services/read/dashboards/daily-prc.json",
            notes="Public dashboard JSON with current grid condition and physical responsive capability.",
        ),
        ProviderEndpoint(
            label="ERCOT Today's Outlook dashboard JSON",
            url="https://www.ercot.com/api/1/services/read/dashboards/todays-outlook.json",
            notes="Public dashboard JSON with current/forecast demand and capacity points.",
        ),
        ProviderEndpoint(
            label="ERCOT API Explorer",
            url="https://apiexplorer.ercot.com/",
            notes="Registered API access for deeper report-specific endpoints.",
        ),
    ],
    queryable=True,
    authentication=(
        "none for configured public dashboard JSON; registered API access is required for deeper "
        "API Explorer reports."
    ),
    update_frequency="ERCOT dashboard JSON updates throughout the operating day; Data Access Portal report cadence varies.",
    limitations=[
        "Configured dashboard endpoints provide system-level ERCOT context, not site-level interconnection capacity.",
        "Substation, transmission, feeder, and TSP-specific capacity still require utility/interconnection diligence.",
        "Deeper ERCOT Data Access Portal/API Explorer reports may require registration and subscription keys.",
    ],
    tags=["ercot", "power", "grid-conditions", "market", "texas"],
)


def _last_dict(items: Any) -> dict[str, Any]:
    if isinstance(items, list):
        for item in reversed(items):
            if isinstance(item, dict):
                return item
    return {}


async def query_ercot_dashboard_data(
    provider: DataProviderDefinition,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    prc_endpoint = provider.endpoints[0]
    outlook_endpoint = provider.endpoints[1]
    prc_data = await http_client.get_json(str(prc_endpoint.url))
    outlook_data = await http_client.get_json(str(outlook_endpoint.url))

    data = {
        "status": "live_query",
        "provider_id": provider.id,
        "grid_condition": prc_data.get("current_condition"),
        "grid_condition_last_updated": prc_data.get("lastUpdated"),
        "latest_prc": _last_dict(prc_data.get("data")),
        "outlook_last_updated": outlook_data.get("lastUpdated"),
        "latest_outlook": _last_dict(outlook_data.get("data")),
        "source_endpoints": [
            prc_endpoint.model_dump(mode="json"),
            outlook_endpoint.model_dump(mode="json"),
        ],
        "limitations": provider.limitations,
    }

    return ProviderQueryResponse(
        provider=provider,
        request_url=prc_endpoint.url,
        request_params={
            "dashboards": [
                "daily-prc.json",
                "todays-outlook.json",
            ]
        },
        data=data,
    )
