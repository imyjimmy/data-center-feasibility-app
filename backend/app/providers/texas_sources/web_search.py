import os
from typing import Any

import httpx
from pydantic import HttpUrl

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


WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _area_from_context(site_context: str | None) -> str:
    if not site_context:
        return "Austin Texas"

    lowered = site_context.lower()
    for area in ("Austin", "Round Rock", "Pflugerville", "Hutto", "Taylor", "Cedar Park"):
        if area.lower() in lowered:
            return f"{area} Texas"

    return "Austin Texas" if "austin-area" in lowered else "Texas"


def _search_queries(request: ProviderQueryRequest) -> list[str]:
    explicit_queries = request.params.get("queries")
    if isinstance(explicit_queries, list):
        queries = [str(query).strip() for query in explicit_queries if str(query).strip()]
        if queries:
            return queries[:5]

    site_context = request.params.get("site_context")
    site_text = site_context if isinstance(site_context, str) else None
    area = _area_from_context(site_text)
    return [
        f"{area} data center address",
        f"{area} colocation data center address",
        f"{area} data center campus industrial land",
        f"{area} data center site development",
    ]


def _result_item(item: dict[str, Any], query: str) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "url": item.get("url"),
        "description": item.get("description"),
        "age": item.get("age"),
        "query": query,
    }


async def query_web_search_leads(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    queries = _search_queries(request)
    limit = max(1, min(request.limit, 10))

    if not api_key:
        return ProviderQueryResponse(
            provider=provider,
            request_url=HttpUrl(WEB_SEARCH_ENDPOINT),
            request_params={"queries": queries, "count": limit},
            data={
                "status": "not_configured",
                "provider_id": provider.id,
                "missing_env": "BRAVE_SEARCH_API_KEY",
                "queries": queries,
                "results": [],
                "data_center_interpretation": {
                    "use": "Configure this provider to discover public web leads for existing data-center addresses, campuses, operators, and nearby industrial areas.",
                    "next_step": "After a web lead yields an address or named campus, pass that address back through parcel/geocoding providers before treating nearby land as a candidate.",
                },
                "limitations": provider.limitations,
            },
        )

    searches: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for query in queries:
        params = {
            "q": query,
            "count": limit,
            "search_lang": "en",
            "country": "US",
            "safesearch": "moderate",
        }
        try:
            payload = await http_client.get_json(
                WEB_SEARCH_ENDPOINT,
                params=params,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                searches.append({"query": query, "status": "rate_limited", "returned": 0})
                return ProviderQueryResponse(
                    provider=provider,
                    request_url=HttpUrl(WEB_SEARCH_ENDPOINT),
                    request_params={"queries": queries, "count": limit},
                    data={
                        "status": "rate_limited",
                        "provider_id": provider.id,
                        "source": "brave_web_search",
                        "searches": searches,
                        "result_count": len(results),
                        "results": results[:25],
                        "data_center_interpretation": {
                            "use": "Use any returned public web results as lead generation only.",
                            "next_step": "Retry later or reduce web-search use; continue parcel screening from configured parcel/geospatial providers.",
                        },
                        "limitations": [
                            *provider.limitations,
                            "The web-search API returned HTTP 429 Too Many Requests, so web lead generation is incomplete for this run.",
                        ],
                    },
                )
            raise
        web_results = payload.get("web", {}).get("results", []) if isinstance(payload, dict) else []
        if not isinstance(web_results, list):
            web_results = []
        searches.append({"query": query, "returned": len(web_results)})

        for item in web_results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(_result_item(item, query))

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(WEB_SEARCH_ENDPOINT),
        request_params={"queries": queries, "count": limit},
        data={
            "status": "live_query",
            "provider_id": provider.id,
            "source": "brave_web_search",
            "searches": searches,
            "result_count": len(results),
            "results": results[:25],
            "data_center_interpretation": {
                "use": "Use these public web results as lead generation for existing data-center addresses or named campuses near the target market.",
                "not_a_substitute_for": "Parcel geometry, site control, zoning, utility capacity, carrier route evidence, or distance-based suitability scoring.",
            },
            "limitations": provider.limitations,
        },
    )


DATA_CENTER_WEB_SEARCH = DataProviderDefinition(
    id="data_center_web_search",
    name="Data Center Web Search",
    concern=Concern.ICP,
    kind=ProviderKind.REST_API,
    capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "Configurable web search provider for public leads about existing data centers, colocation "
        "facilities, campus names, operator pages, and addresses near a target Texas market."
    ),
    owner="Configurable web search API",
    source_homepage="https://brave.com/search/api/",
    endpoints=[
        ProviderEndpoint(
            label="Brave Search API",
            url=WEB_SEARCH_ENDPOINT,
            notes="Requires BRAVE_SEARCH_API_KEY. Used for public lead generation, not parcel proof.",
        )
    ],
    queryable=True,
    authentication="BRAVE_SEARCH_API_KEY",
    limitations=[
        "Web results are lead-generation context and can be stale, promotional, duplicated, or ambiguous.",
        "Addresses or campus names found by web search must be verified through parcel/geocoding providers before ranking candidate land.",
        "Nearby existing data centers do not prove available land, utility capacity, zoning compatibility, or site control.",
    ],
    tags=["web-search", "data-centers", "addresses", "lead-generation", "icp"],
)
