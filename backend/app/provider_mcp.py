from typing import Any

from fastmcp import FastMCP

from app.providers.client import ProviderHttpClient
from app.providers.models import ProviderQueryRequest
from app.providers.registry import get_provider_registry
from app.providers.service import query_provider_data
from app.providers.texas_sources.travis_parcels import (
    build_travis_parcel_area_search_request,
)


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _feature_center(feature: dict[str, Any]) -> list[float] | None:
    geometry = _as_dict(feature.get("geometry"))
    points: list[list[float]] = []
    for ring in _as_list(geometry.get("rings")):
        for coordinate in _as_list(ring):
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            lon, lat = coordinate[0], coordinate[1]
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                points.append([float(lat), float(lon)])
    if points:
        return [
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        ]
    return None


def _parcel_candidate(feature: dict[str, Any]) -> dict[str, Any] | None:
    attrs = _as_dict(feature.get("attributes"))
    acres = _float_value(attrs.get("tcad_acres") or attrs.get("GIS_acres") or attrs.get("ACRES"))
    if acres is None:
        return None
    return {
        "prop_id": attrs.get("PROP_ID") or attrs.get("prop_id") or attrs.get("OBJECTID"),
        "situs_address": attrs.get("situs_address") or attrs.get("SITEADDRESS"),
        "owner": attrs.get("py_owner_name") or attrs.get("OWNER_NAME"),
        "tcad_acres": acres,
        "land_type": attrs.get("land_type_desc"),
        "legal_desc": attrs.get("legal_desc"),
        "center": _feature_center(feature),
        "attributes": attrs,
    }


async def build_austin_area_parcel_shortlist(
    site_context: str,
    min_acres: float = 25,
    limit: int = 10,
) -> dict[str, Any]:
    registry = get_provider_registry()
    request = build_travis_parcel_area_search_request(
        site_context,
        min_acres=min_acres,
        limit=max(limit, 10),
    )
    if request is None:
        return {
            "status": "unsupported_location",
            "site_context": site_context,
            "candidates": [],
            "limitations": ["The configured shortlist tool currently supports Austin/Travis-area prompts."],
        }

    provider = registry.get("travis_county_parcels")
    response = await query_provider_data(
        provider=provider,
        request=request,
        http_client=ProviderHttpClient(),
    )
    features = _as_list(response.data.get("features"))
    candidates = [
        candidate
        for feature in features
        if isinstance(feature, dict) and (candidate := _parcel_candidate(feature)) is not None
    ]
    candidates.sort(key=lambda candidate: candidate["tcad_acres"], reverse=True)
    return {
        "status": "returned",
        "site_context": site_context,
        "min_acres": min_acres,
        "candidate_count": len(candidates[:limit]),
        "candidates": candidates[:limit],
        "request": {
            "provider_id": provider.id,
            "where": request.where,
            "bbox": request.bbox,
            "request_params": response.request_params,
        },
        "query_fallback": response.data.get("query_fallback"),
        "client_side_filter": response.data.get("client_side_filter"),
        "limitations": [
            "Parcel shortlist is acreage/geometry evidence, not zoning, utility capacity, or site-control proof.",
            "Use candidate centroids for follow-on zoning, jurisdiction, water, power, and broadband checks.",
        ],
    }


def create_research_mcp() -> FastMCP:
    registry = get_provider_registry()
    mcp = FastMCP(
        name="Data Center Feasibility Texas Open Data MCP",
        instructions=(
            "Research MCP for Texas data-center site diligence. Use list_providers once to discover "
            "provider IDs, concern areas, coverage, and queryability. Use query_provider for "
            "site-specific evidence from queryable providers. Use provider_metadata to explain "
            "coverage, endpoint, authentication, and limitation gaps for metadata-only providers. "
            "Use provider_health only when one provider's configured/queryable status is ambiguous."
        ),
    )

    @mcp.tool
    def list_providers(state: str = "TX") -> list[dict[str, Any]]:
        return [provider.model_dump(mode="json") for provider in registry.list(state=state)]

    @mcp.tool
    def provider_metadata(provider_id: str) -> dict[str, Any]:
        return registry.get(provider_id).model_dump(mode="json")

    @mcp.tool
    def provider_health(provider_id: str) -> dict[str, Any]:
        provider = registry.get(provider_id)
        return {
            "provider_id": provider.id,
            "queryable": provider.queryable,
            "status": "configured" if provider.queryable else "metadata_only",
            "limitations": provider.limitations,
        }

    @mcp.tool
    async def austin_area_parcel_shortlist(
        site_context: str,
        min_acres: float = 25,
        limit: int = 10,
    ) -> dict[str, Any]:
        return await build_austin_area_parcel_shortlist(
            site_context=site_context,
            min_acres=min_acres,
            limit=limit,
        )

    @mcp.tool
    async def query_provider(
        provider_id: str,
        where: str = "1=1",
        out_fields: str = "*",
        limit: int = 25,
        return_geometry: bool = True,
        bbox: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        provider = registry.get(provider_id)
        request = ProviderQueryRequest(
            where=where,
            out_fields=out_fields,
            limit=limit,
            return_geometry=return_geometry,
            bbox=bbox,
            params=params or {},
        )
        response = await query_provider_data(
            provider=provider,
            request=request,
            http_client=ProviderHttpClient(),
        )
        return response.model_dump(mode="json")

    return mcp


def create_provider_mcp(provider_id: str) -> FastMCP:
    registry = get_provider_registry()
    provider = registry.get(provider_id)
    mcp = FastMCP(
        name=f"{provider.name} MCP",
        instructions=(
            f"Provider-scoped MCP for {provider.name}. Use provider_metadata to inspect source "
            "coverage and query_provider for provider data or metadata-safe query responses."
        ),
    )

    @mcp.tool
    def provider_metadata() -> dict[str, Any]:
        return provider.model_dump(mode="json")

    @mcp.tool
    def provider_health() -> dict[str, Any]:
        return {
            "provider_id": provider.id,
            "queryable": provider.queryable,
            "status": "configured" if provider.queryable else "metadata_only",
            "limitations": provider.limitations,
        }

    @mcp.tool
    async def query_provider(
        where: str = "1=1",
        out_fields: str = "*",
        limit: int = 25,
        return_geometry: bool = True,
        bbox: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = ProviderQueryRequest(
            where=where,
            out_fields=out_fields,
            limit=limit,
            return_geometry=return_geometry,
            bbox=bbox,
            params=params or {},
        )
        response = await query_provider_data(
            provider=provider,
            request=request,
            http_client=ProviderHttpClient(),
        )
        return response.model_dump(mode="json")

    return mcp
