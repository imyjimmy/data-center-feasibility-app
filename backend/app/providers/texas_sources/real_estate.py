import re
from typing import Any

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


TRERC_SEARCH_URL = "https://trerc.tamu.edu/wp-json/wp/v2/search"

AREA_HINTS = {
    "austin": "Austin",
    "round rock": "Round Rock",
    "pflugerville": "Pflugerville",
    "hutto": "Hutto",
    "taylor": "Taylor",
    "san antonio": "San Antonio",
    "dallas": "Dallas",
    "fort worth": "Fort Worth",
    "houston": "Houston",
}


def _area_term(site_context: str | None) -> str:
    if not site_context:
        return "Texas"

    normalized = site_context.lower()
    for needle, area in AREA_HINTS.items():
        if needle in normalized:
            return area

    city_match = re.search(r",\s*([A-Za-z .'-]+),\s*TX\b", site_context)
    if city_match:
        return city_match.group(1).strip()

    return "Texas"


def _search_terms(request: ProviderQueryRequest) -> list[str]:
    explicit_terms = request.params.get("search_terms")
    if isinstance(explicit_terms, str) and explicit_terms.strip():
        return [explicit_terms.strip()]

    site_context = request.params.get("site_context")
    site_text = site_context if isinstance(site_context, str) else None
    area = _area_term(site_text)
    return [
        f"{area} industrial real estate",
        f"{area} land market",
        "Texas commercial land industrial market",
    ]


def _result_item(item: dict[str, Any], search_term: str) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "url": item.get("url"),
        "type": item.get("type"),
        "subtype": item.get("subtype"),
        "search_term": search_term,
    }


async def query_real_estate_research_matches(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    terms = _search_terms(request)
    per_page = max(1, min(request.limit, 10))
    seen_urls: set[str] = set()
    results: list[dict[str, Any]] = []
    searches: list[dict[str, Any]] = []

    for term in terms:
        params = {"search": term, "per_page": per_page}
        payload = await http_client.get_json(
            TRERC_SEARCH_URL,
            params=params,
            headers={"User-Agent": "data-center-feasibility-app/0.1 (+https://trerc.tamu.edu/)"},
        )
        raw_items = payload if isinstance(payload, list) else payload.get("results", [])
        if not isinstance(raw_items, list):
            raw_items = []

        searches.append({"search_term": term, "returned": len(raw_items)})
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(_result_item(item, term))

    site_context = request.params.get("site_context")
    data = {
        "status": "live_query",
        "provider_id": provider.id,
        "source": "trerc_wordpress_search",
        "input": {
            "site_context": site_context if isinstance(site_context, str) else None,
            "market_area": _area_term(site_context) if isinstance(site_context, str) else "Texas",
        },
        "searches": searches,
        "result_count": len(results),
        "results": results,
        "data_center_interpretation": {
            "use": "Use these as market-context reading and source leads for industrial/land demand, not as parcel-level diligence.",
            "not_a_substitute_for": "Broker outreach, land comps, title/site-control checks, zoning, power, water, or fiber diligence.",
        },
        "limitations": provider.limitations,
        "source_endpoints": [endpoint.model_dump(mode="json") for endpoint in provider.endpoints],
    }

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(TRERC_SEARCH_URL),
        request_params={
            "per_page": per_page,
            "search_terms": terms,
            "site_context": site_context if isinstance(site_context, str) else None,
        },
        data=data,
    )


TEXAS_REAL_ESTATE_RESEARCH_CENTER = DataProviderDefinition(
    id="texas_real_estate_research_center",
    name="Texas Real Estate Research Center",
    concern=Concern.ICP,
    kind=ProviderKind.REST_API,
    capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "Texas public university real-estate research source for market context. "
        "Queries TRERC articles, reports, and press posts for area-specific land and industrial market signals."
    ),
    owner="Texas Real Estate Research Center at Texas A&M University",
    source_homepage="https://trerc.tamu.edu/",
    endpoints=[
        ProviderEndpoint(
            label="TRERC content search API",
            url=TRERC_SEARCH_URL,
            notes="WordPress REST search over TRERC posts, articles, reports, and press releases.",
        ),
        ProviderEndpoint(
            label="Texas Real Estate Research Center",
            url="https://trerc.tamu.edu/",
            notes="Market reports, research, and contact routes for Texas real-estate context.",
        ),
    ],
    queryable=True,
    limitations=[
        "TRERC content search provides market context, not parcel/site-level land availability or comps.",
        "Commercial broker or land-owner outreach is still required for site control, pricing, and transaction evidence.",
        "Search results may be statewide or regional; confirm relevance before using them in scoring.",
    ],
    tags=["real-estate", "icp", "commercial", "industrial", "land", "texas"],
)
