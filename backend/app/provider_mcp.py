from typing import Any

from fastmcp import FastMCP

from app.providers.client import ProviderHttpClient
from app.providers.models import ProviderQueryRequest
from app.providers.registry import get_provider_registry
from app.providers.service import query_provider_data


def create_research_mcp() -> FastMCP:
    registry = get_provider_registry()
    mcp = FastMCP(
        name="Data Center Feasibility Texas Open Data MCP",
        instructions=(
            "Research MCP for Texas data-center feasibility providers. Use list_providers to "
            "discover provider IDs, provider_metadata and provider_health to inspect coverage, "
            "and query_provider for configured provider data."
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
