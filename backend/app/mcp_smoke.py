import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic_ai.mcp import MCPServerStreamableHTTP

from app.pydantic_agent import (
    AgentToolCallRecord,
    PydanticAgentResearchError,
    pydantic_agent_is_configured,
    pydantic_agent_mcp_url,
    research_with_pydantic_agent,
)


class McpToolSummary(BaseModel):
    name: str
    description: str | None = None


class McpProviderSmokeResult(BaseModel):
    provider_id: str
    provider_name: str
    queryable: bool
    source: str
    mcp_tools: list[str] = Field(default_factory=list)
    request_url: str | None = None
    request_params: dict[str, Any] = Field(default_factory=dict)
    health_status: str | None = None
    query_status: str
    data_status: str | None = None
    data_keys: list[str] = Field(default_factory=list)
    feature_count: int | None = None
    sample_attributes: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class McpSmokeResponse(BaseModel):
    mcp_url: str
    tools: list[McpToolSummary]
    providers: list[McpProviderSmokeResult]


class McpAgentTestRequest(BaseModel):
    prompt: str = Field(min_length=1)
    state: str = Field(default="TX", min_length=2, max_length=2)
    site_context: str | None = Field(default=None, max_length=240)


class McpAgentTestResponse(BaseModel):
    mcp_url: str
    summary: str | None = None
    provider_insights: list[dict] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_records: list[AgentToolCallRecord] = Field(default_factory=list)
    evidence: list[McpProviderSmokeResult] = Field(default_factory=list)
    site_context: str | None = None


router = APIRouter(prefix="/api/mcp-smoke", tags=["mcp-smoke"])


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _data_keys(value: Any) -> list[str]:
    return sorted(value.keys()) if isinstance(value, dict) else []


def _sample_attributes(features: list[Any]) -> dict[str, Any]:
    if not features:
        return {}

    first_feature = _as_dict(features[0])
    attributes = _as_dict(first_feature.get("attributes"))
    return {key: attributes[key] for key in list(attributes)[:8]}


def _site_query_args(provider_id: str, site_context: str | None, limit: int) -> dict[str, Any]:
    args: dict[str, Any] = {
        "provider_id": provider_id,
        "limit": limit,
        "return_geometry": False,
    }
    if not site_context:
        return args

    coordinate_match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", site_context)
    if coordinate_match:
        first = float(coordinate_match.group(1))
        second = float(coordinate_match.group(2))
        lat, lon = (second, first) if abs(first) > 90 and abs(second) <= 90 else (first, second)
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            delta = 0.01
            args["bbox"] = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
            args["params"] = {"inSR": 4326}
            return args

    if provider_id == "travis_county_parcels":
        upper_context = site_context.upper()
        street_number = re.search(r"\b\d{2,6}\b", upper_context)
        street_tokens = [
            token
            for token in re.findall(r"[A-Z]{3,}", upper_context)
            if token
            not in {
                "AUSTIN",
                "TEXAS",
                "COUNTY",
                "ROAD",
                "STREET",
                "BLVD",
                "BOULEVARD",
            }
        ]
        clauses: list[str] = []
        if street_number:
            clauses.append(f"situs_address LIKE '%{street_number.group(0)}%'")
        for token in street_tokens[:2]:
            clauses.append(f"situs_address LIKE '%{token}%'")
        if clauses:
            args["where"] = " AND ".join(clauses)

    return args


async def run_mcp_provider_smoke(
    state: str = "TX",
    limit: int = 2,
    site_context: str | None = None,
) -> McpSmokeResponse:
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
                    _site_query_args(provider_id=provider_id, site_context=site_context, limit=limit),
                )
            )
            data = _as_dict(query_result.get("data"))
            features = _as_list(data.get("features"))
            request_params = _as_dict(query_result.get("request_params"))

            results.append(
                McpProviderSmokeResult(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    queryable=queryable,
                    source="live_query" if queryable else "metadata_only",
                    mcp_tools=["provider_health", "query_provider"],
                    request_url=str(query_result.get("request_url") or ""),
                    request_params=request_params,
                    health_status=str(health.get("status")) if health.get("status") else None,
                    query_status="returned",
                    data_status=str(data.get("status")) if data.get("status") else None,
                    data_keys=_data_keys(data),
                    feature_count=len(features) if "features" in data else None,
                    sample_attributes=_sample_attributes(features),
                )
            )
        except Exception as exc:
            results.append(
                McpProviderSmokeResult(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    queryable=queryable,
                    source="failed",
                    mcp_tools=["provider_health", "query_provider"],
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
    site_context: str | None = Query(default=None, max_length=240),
) -> McpSmokeResponse:
    return await run_mcp_provider_smoke(state=state.upper(), limit=limit, site_context=site_context)


@router.post("/agent", response_model=McpAgentTestResponse, operation_id="run_mcp_agent_test")
def test_agent(request: McpAgentTestRequest) -> McpAgentTestResponse:
    if not pydantic_agent_is_configured():
        raise HTTPException(status_code=503, detail="Pydantic AI agent is not configured")

    try:
        site_context = request.site_context.strip() if request.site_context else None
        evidence = asyncio.run(
            run_mcp_provider_smoke(
                state=request.state.upper(),
                limit=2,
                site_context=site_context,
            )
        )
        result = research_with_pydantic_agent(
            question=request.prompt,
            state=request.state.upper(),
            run_id="mcp-test",
            site_context=site_context,
        )
    except PydanticAgentResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return McpAgentTestResponse(
        mcp_url=pydantic_agent_mcp_url(),
        summary=result.summary,
        provider_insights=result.provider_insights,
        tool_calls=result.tool_calls,
        tool_call_records=result.tool_call_records,
        evidence=evidence.providers,
        site_context=site_context,
    )
