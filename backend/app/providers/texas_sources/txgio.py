import re
from html import unescape
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


ARCGIS_ONLINE_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
TXGIO_ITEM_URL_PREFIX = "https://www.arcgis.com/home/item.html?id="

AREA_HINTS = {
    "austin": "Austin Travis County",
    "round rock": "Round Rock Williamson Travis County",
    "pflugerville": "Pflugerville Travis County",
    "hutto": "Hutto Williamson County",
    "taylor": "Taylor Williamson County",
    "san antonio": "San Antonio Bexar County",
    "dallas": "Dallas Dallas County",
    "fort worth": "Fort Worth Tarrant County",
    "houston": "Houston Harris County",
}

DEFAULT_CATALOG_QUERIES = [
    "TxGIO StratMap Parcels Latest",
    "TxGIO Address Points",
    "Texas zoning GIS",
]


def _clean_html(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text[:500] if text else None


def _compact_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return [str(item) for item in value[:8] if str(item).strip()]


def _area_terms(site_context: str | None) -> str | None:
    if not site_context:
        return None

    normalized = site_context.lower()
    for needle, area in AREA_HINTS.items():
        if needle in normalized:
            return area

    county_match = re.search(r"\b([A-Za-z]+)\s+County\b", site_context)
    if county_match:
        return f"{county_match.group(1)} County"

    city_match = re.search(r",\s*([A-Za-z .'-]+),\s*TX\b", site_context)
    if city_match:
        return city_match.group(1).strip()

    return site_context


def _city_terms(site_context: str | None) -> str | None:
    if not site_context:
        return None

    normalized = site_context.lower()
    for needle in AREA_HINTS:
        if needle in normalized:
            return " ".join(part.capitalize() for part in needle.split())

    city_match = re.search(r",\s*([A-Za-z .'-]+),\s*TX\b", site_context)
    if city_match:
        return city_match.group(1).strip()

    return None


def _county_terms(area: str | None) -> str | None:
    if not area:
        return None

    county_match = re.search(r"\b([A-Za-z]+ County)\b", area)
    return county_match.group(1) if county_match else area


def _catalog_queries(request: ProviderQueryRequest) -> list[str]:
    explicit_terms = request.params.get("search_terms")
    if isinstance(explicit_terms, str) and explicit_terms.strip():
        return [explicit_terms.strip()]

    site_context = request.params.get("site_context")
    site_text = site_context if isinstance(site_context, str) else None
    area = _area_terms(site_text)
    city = _city_terms(site_text)
    county = _county_terms(area)
    if not area:
        return DEFAULT_CATALOG_QUERIES

    return [
        "TxGIO StratMap Parcels Latest",
        f"TxGIO Address Points {county}",
        f"{city or area} Zoning Feature Service",
    ]


def _catalog_match(item: dict[str, Any]) -> dict[str, Any]:
    item_id = str(item.get("id") or "")
    service_url = item.get("url")
    return {
        "id": item_id,
        "title": str(item.get("title") or item_id or "Untitled ArcGIS item"),
        "type": item.get("type"),
        "owner": item.get("owner"),
        "service_url": service_url,
        "item_url": f"{TXGIO_ITEM_URL_PREFIX}{item_id}" if item_id else None,
        "snippet": _clean_html(item.get("snippet") or item.get("description")),
        "tags": _compact_tags(item.get("tags")),
        "extent": item.get("extent"),
        "modified": item.get("modified"),
        "score_completeness": item.get("scoreCompleteness"),
        "access": item.get("access"),
    }


async def query_txgio_catalog_matches(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    queries = _catalog_queries(request)
    limit = max(1, min(request.limit, 10))
    seen_ids: set[str] = set()
    matches: list[dict[str, Any]] = []
    raw_totals: list[dict[str, Any]] = []

    for query in queries:
        params = {
            "f": "json",
            "q": query,
            "num": limit,
        }
        payload = await http_client.get_json(ARCGIS_ONLINE_SEARCH_URL, params=params)
        raw_totals.append(
            {
                "query": query,
                "total": payload.get("total"),
                "returned": len(payload.get("results", [])) if isinstance(payload.get("results"), list) else 0,
            }
        )

        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            matches.append(_catalog_match(item))

    site_context = request.params.get("site_context")
    data = {
        "status": "live_query",
        "provider_id": provider.id,
        "source": "arcgis_online_catalog_search",
        "input": {
            "site_context": site_context if isinstance(site_context, str) else None,
            "derived_area_terms": _area_terms(site_context) if isinstance(site_context, str) else None,
        },
        "queries": raw_totals,
        "match_count": len(matches),
        "matches": matches[: limit * len(queries)],
        "data_center_interpretation": {
            "parcel": "Use TxGIO StratMap parcel matches for statewide parcel layer discovery; county appraisal data remains more authoritative for parcel attributes.",
            "address_geocoding": "Use address-point matches to find regional 9-1-1/address-point feature services that can support site resolution.",
            "zoning": "Zoning matches are usually municipal datasets; confirm the returned service owner and jurisdiction before using for entitlements.",
        },
        "limitations": provider.limitations,
        "source_endpoints": [endpoint.model_dump(mode="json") for endpoint in provider.endpoints],
    }

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(ARCGIS_ONLINE_SEARCH_URL),
        request_params={
            "f": "json",
            "num": limit,
            "queries": queries,
            "site_context": site_context if isinstance(site_context, str) else None,
        },
        data=data,
    )


TXGIO_GEOSPATIAL_CATALOG = DataProviderDefinition(
    id="txgio_geospatial_catalog",
    name="Texas Geographic Information Office Data Catalog",
    concern=Concern.PARCEL_GEOCODING,
    kind=ProviderKind.OPEN_DATA_PORTAL,
    capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "Texas Geographic Information Office and Texas GIS catalog search for parcel, address-point, "
        "zoning, and other geospatial datasets used to resolve site-level diligence sources."
    ),
    owner="Texas Geographic Information Office / Texas Water Development Board",
    source_homepage="https://geographic.texas.gov/",
    endpoints=[
        ProviderEndpoint(
            label="ArcGIS Online catalog search",
            url=ARCGIS_ONLINE_SEARCH_URL,
            notes="Searches ArcGIS Online for TxGIO and Texas GIS dataset items relevant to the site/diligence topic.",
        ),
        ProviderEndpoint(
            label="TxGIO land parcels program",
            url="https://geographic.texas.gov/stratmap/land-parcels.html",
            notes="Program page for TxGIO statewide parcel schema and DataHub downloads.",
        ),
        ProviderEndpoint(
            label="TxGIO address points program",
            url="https://geographic.texas.gov/stratmap/address-points.html",
            notes="Program page for TxGIO statewide address-point schema and DataHub downloads.",
        ),
    ],
    queryable=True,
    limitations=[
        "Catalog matches identify candidate datasets; they are not a legal parcel, zoning, or entitlement determination.",
        "Returned ArcGIS items may be statewide, regional, or municipal; jurisdiction and freshness must be checked per match.",
        "Address-level geocoding still requires querying a returned address-point/geocoder service or another configured geocoder.",
    ],
    tags=["geocoding", "txgio", "tnris", "open-data", "texas", "arcgis"],
)
