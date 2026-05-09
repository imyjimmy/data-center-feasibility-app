import os
from typing import Any

import httpx

from app.providers.client import ProviderHttpClient
from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
    ProviderQueryRequest,
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
        ProviderEndpoint(
            label="ERCOT Public API reports",
            url="https://api.ercot.com/api/public-reports",
            notes="Requires Ocp-Apim-Subscription-Key and Authorization bearer token headers.",
        ),
    ],
    queryable=True,
    authentication=(
        "none for configured public dashboard JSON; ERCOT Public API requests require "
        "Ocp-Apim-Subscription-Key and a bearer ID token."
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


def _ercot_public_api_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    subscription_key = os.getenv("ERCOT_SUBSCRIPTION_KEY") or os.getenv("ERCOT_PRIMARY_KEY")
    id_token = os.getenv("ERCOT_ID_TOKEN")

    if subscription_key:
        headers["Ocp-Apim-Subscription-Key"] = subscription_key
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    return headers


def _public_api_config_status(headers: dict[str, str]) -> str:
    if "Ocp-Apim-Subscription-Key" not in headers:
        return "missing_subscription_key"
    if "Authorization" not in headers:
        return "missing_id_token"
    return "configured"


def _dashboard_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Referer": "https://www.ercot.com/gridmktinfo/dashboards",
        "User-Agent": "Mozilla/5.0 compatible; data-center-feasibility-app/0.1",
    }


async def _get_dashboard_json(
    http_client: ProviderHttpClient,
    endpoint: ProviderEndpoint,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        return await http_client.get_json(str(endpoint.url), headers=_dashboard_headers()), None
    except httpx.HTTPStatusError as exc:
        return None, {
            "endpoint": endpoint.model_dump(mode="json"),
            "status_code": exc.response.status_code,
            "reason": exc.response.reason_phrase,
        }


async def query_ercot_dashboard_data(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    headers = _ercot_public_api_headers()
    public_api_config_status = _public_api_config_status(headers)

    if request.params.get("endpoint") == "public-reports" and public_api_config_status == "configured":
        endpoint = provider.endpoints[3]
        data = await http_client.get_json(str(endpoint.url), headers=headers)

        return ProviderQueryResponse(
            provider=provider,
            request_url=endpoint.url,
            request_params={"endpoint": "public-reports"},
            data=data,
        )

    prc_endpoint = provider.endpoints[0]
    outlook_endpoint = provider.endpoints[1]
    prc_data, prc_error = await _get_dashboard_json(http_client, prc_endpoint)
    outlook_data, outlook_error = await _get_dashboard_json(http_client, outlook_endpoint)
    dashboard_errors = [error for error in (prc_error, outlook_error) if error]
    prc_data = prc_data or {}
    outlook_data = outlook_data or {}

    data = {
        "status": "partial_query" if dashboard_errors else "live_query",
        "provider_id": provider.id,
        "public_api_config_status": public_api_config_status,
        "dashboard_errors": dashboard_errors,
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
