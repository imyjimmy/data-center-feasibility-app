from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from pydantic_ai.mcp import MCPServerStreamableHTTP

from app.pydantic_agent import pydantic_agent_mcp_url


class McpToolSummary(BaseModel):
    name: str
    description: str | None = None


class McpProviderSmokeResult(BaseModel):
    provider_id: str
    provider_name: str
    queryable: bool
    health_status: str | None = None
    query_status: str
    data_status: str | None = None
    data_keys: list[str] = Field(default_factory=list)
    feature_count: int | None = None
    error: str | None = None


class McpSmokeResponse(BaseModel):
    mcp_url: str
    tools: list[McpToolSummary]
    providers: list[McpProviderSmokeResult]


router = APIRouter(prefix="/api/mcp-smoke", tags=["mcp-smoke"])


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _data_keys(value: Any) -> list[str]:
    return sorted(value.keys()) if isinstance(value, dict) else []


async def run_mcp_provider_smoke(state: str = "TX", limit: int = 2) -> McpSmokeResponse:
    server = MCPServerStreamableHTTP(pydantic_agent_mcp_url())
    tools = await server.list_tools()
    tool_summaries = [
        McpToolSummary(name=tool.name, description=tool.description)
        for tool in sorted(tools, key=lambda item: item.name)
    ]

    providers_result = await server.direct_call_tool("list_providers", {"state": state})
    providers = _as_list(providers_result)
    results: list[McpProviderSmokeResult] = []

    for provider in providers:
        provider_dict = _as_dict(provider)
        provider_id = str(provider_dict.get("id") or "unknown")
        provider_name = str(provider_dict.get("name") or provider_id)
        queryable = bool(provider_dict.get("queryable"))

        try:
            health = _as_dict(await server.direct_call_tool("provider_health", {"provider_id": provider_id}))
            query_result = _as_dict(
                await server.direct_call_tool(
                    "query_provider",
                    {
                        "provider_id": provider_id,
                        "limit": limit,
                        "return_geometry": False,
                    },
                )
            )
            data = _as_dict(query_result.get("data"))
            features = _as_list(data.get("features"))

            results.append(
                McpProviderSmokeResult(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    queryable=queryable,
                    health_status=str(health.get("status")) if health.get("status") else None,
                    query_status="returned",
                    data_status=str(data.get("status")) if data.get("status") else None,
                    data_keys=_data_keys(data),
                    feature_count=len(features) if "features" in data else None,
                )
            )
        except Exception as exc:
            results.append(
                McpProviderSmokeResult(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    queryable=queryable,
                    query_status="failed",
                    error=str(exc),
                )
            )

    return McpSmokeResponse(
        mcp_url=pydantic_agent_mcp_url(),
        tools=tool_summaries,
        providers=results,
    )


@router.post("/providers", response_model=McpSmokeResponse, operation_id="run_mcp_provider_smoke_test")
async def smoke_providers(
    state: str = Query(default="TX", min_length=2, max_length=2),
    limit: int = Query(default=2, ge=1, le=10),
) -> McpSmokeResponse:
    return await run_mcp_provider_smoke(state=state.upper(), limit=limit)
