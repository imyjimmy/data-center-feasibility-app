import asyncio
import os
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.mcp import MCPServerStreamableHTTP


class AgentProviderInsight(BaseModel):
    provider_id: str
    status: str | None = None
    summary: str | None = None
    limitations: list[str] = Field(default_factory=list)


class AgentResearchResult(BaseModel):
    summary: str
    provider_insights: list[AgentProviderInsight] = Field(default_factory=list)


class AgentToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str = "called"
    result_preview: str | None = None
    result_items: list[dict[str, Any]] = Field(default_factory=list)
    result_fields: dict[str, Any] = Field(default_factory=dict)


class PydanticAgentResearchResult(BaseModel):
    summary: str | None = None
    provider_insights: list[dict] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_records: list[AgentToolCallRecord] = Field(default_factory=list)


class PydanticAgentResearchError(RuntimeError):
    pass


AGENT_INSTRUCTIONS = (
    "You are a data-center site feasibility research agent for Texas locations. Use the attached "
    "FastMCP tools to collect evidence before answering. Treat the task as a site-selection diligence "
    "screen, not a generic provider inventory.\n\n"
    "Evaluation framework:\n"
    "1. Site resolution: determine whether the input has coordinates, parcel geometry, or only an "
    "address string. Do not invent coordinates, parcel geometry, or bounding boxes.\n"
    "2. Parcel and land-use: look for parcel match, owner/address attributes, parcel geometry, zoning "
    "or entitlement coverage gaps, ETJ/city dependency, and whether the evidence is parcel-specific.\n"
    "3. Power: look for grid/interconnection evidence, substation/transmission/utility proximity, "
    "capacity constraints, ERCOT market/congestion context, and explicitly flag missing utility/TSP "
    "interconnection data.\n"
    "4. Water/wastewater/cooling: look for utility service-area evidence, available capacity gaps, "
    "wastewater constraints, cooling-water risk, and where utility confirmation is required.\n"
    "5. Fiber/connectivity: look for broadband/fiber evidence, carrier/on-net limitations, diverse path "
    "gaps, and where carrier outreach is required.\n"
    "6. Other diligence: note flood/environmental, site control/market, permits, and civil constraints "
    "only when supported by configured data or as explicit gaps.\n\n"
    "Tool-use rules:\n"
    "- Call list_providers once first; it includes provider IDs, concern areas, queryability, and "
    "coverage hints.\n"
    "- Prefer query_provider for queryable providers when it can produce site-specific evidence.\n"
    "- Use provider_metadata for provider coverage, authentication, endpoint, or limitation details, "
    "especially for metadata-only providers that explain a diligence gap.\n"
    "- Do not call provider_health for every provider; use it only when a specific provider status is "
    "ambiguous after list_providers/query_provider.\n"
    "- For address-only sites, use evidence-backed attribute filters where available, such as Travis "
    "County parcel situs_address filters. Do not use bbox unless numeric coordinates were supplied by "
    "the user or returned by a tool.\n"
    "- If a query returns provider_sample scope or where=1=1 data, label it as generic context, not "
    "site-specific evidence.\n\n"
    "Answering rules:\n"
    "- Be concise and evidence-focused. Separate providers that returned location-specific evidence "
    "from providers that only returned metadata or generic samples.\n"
    "- Do not overstate feasibility. If a configured provider cannot answer a site-level question, say "
    "what missing endpoint/tool/data would be needed.\n"
    "- Return provider_insights with provider_id, status, summary, and limitations. Status should make "
    "the evidence level clear, for example: site_evidence, generic_sample, metadata_only, no_match, "
    "not_site_queryable, or failed."
)


def pydantic_agent_is_configured() -> bool:
    enabled = os.getenv("PYDANTIC_AI_ENABLED", "true").lower() not in {"0", "false", "no"}
    model = os.getenv("PYDANTIC_AI_MODEL", "")
    if model.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        return False
    return enabled and bool(model)


def _model() -> str:
    return os.getenv("PYDANTIC_AI_MODEL", "openai:gpt-5.2")


def pydantic_agent_mcp_url() -> str:
    return os.getenv("PYDANTIC_AI_MCP_URL", "http://127.0.0.1:9000/mcp")


def _preview_tool_return(content: Any) -> str:
    if isinstance(content, dict):
        keys = ", ".join(sorted(str(key) for key in content.keys())[:8])
        return f"returned object keys: {keys}" if keys else "returned empty object"
    if isinstance(content, list):
        return f"returned list with {len(content)} items"
    text = str(content)
    return text if len(text) <= 180 else f"{text[:177]}..."


def _compact_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value)
        return value if len(text) <= 140 else f"{text[:137]}..."
    if isinstance(value, list):
        return f"{len(value)} items"
    if isinstance(value, dict):
        return f"object keys: {', '.join(sorted(str(key) for key in value.keys())[:6])}"
    return str(value)


def _tool_return_items(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []

    items: list[dict[str, Any]] = []
    for item in content[:12]:
        if isinstance(item, dict):
            compact = {
                key: _compact_value(item[key])
                for key in (
                    "id",
                    "name",
                    "concern",
                    "queryable",
                    "coverage",
                    "status",
                    "summary",
                )
                if key in item
            }
            items.append(compact or {key: _compact_value(item[key]) for key in list(item)[:4]})
        else:
            items.append({"value": _compact_value(item)})

    return items


def _tool_return_fields(content: Any) -> dict[str, Any]:
    if not isinstance(content, dict):
        return {}

    fields: dict[str, Any] = {}
    for key in (
        "provider_id",
        "provider",
        "status",
        "queryable",
        "request_url",
        "request_params",
        "data",
        "limitations",
        "endpoints",
        "coverage",
        "capabilities",
    ):
        if key in content:
            fields[key] = _compact_value(content[key])

    return fields or {key: _compact_value(content[key]) for key in list(content)[:8]}


def _extract_tool_call_records(result: Any) -> list[AgentToolCallRecord]:
    records_by_id: dict[str, AgentToolCallRecord] = {}
    output_tool_name = getattr(result, "_output_tool_name", None)

    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                if part.tool_name == output_tool_name:
                    continue
                records_by_id[part.tool_call_id] = AgentToolCallRecord(
                    tool_name=part.tool_name,
                    arguments=part.args_as_dict(),
                )
            elif isinstance(part, ToolReturnPart):
                record = records_by_id.get(part.tool_call_id)
                if record is not None:
                    record.status = "returned"
                    record.result_preview = _preview_tool_return(part.content)
                    record.result_items = _tool_return_items(part.content)
                    record.result_fields = _tool_return_fields(part.content)

    return list(records_by_id.values())


async def _research_with_pydantic_agent(
    question: str,
    state: str,
    run_id: str,
    site_context: str | None = None,
) -> PydanticAgentResearchResult:
    server = MCPServerStreamableHTTP(pydantic_agent_mcp_url())
    agent = Agent(
        _model(),
        toolsets=[server],
        output_type=AgentResearchResult,
        instructions=AGENT_INSTRUCTIONS,
    )

    async with agent:
        result = await agent.run(
            f"Run id: {run_id}\n"
            f"State: {state}\n"
            f"Site/location context: {site_context or 'No site provided'}\n"
            f"User request: {question}\n\n"
            "Run the site diligence workflow from the system instructions. Prioritize actual "
            "site-specific evidence over provider inventory. Start with list_providers, query the "
            "providers that can plausibly answer this site, use metadata to explain gaps, and finish "
            "with a clear feasibility evidence summary across power, water/wastewater, parcel/zoning, "
            "fiber/connectivity, and remaining diligence blockers."
        )

    tool_call_records = _extract_tool_call_records(result)

    return PydanticAgentResearchResult(
        summary=result.output.summary,
        provider_insights=[insight.model_dump(mode="json") for insight in result.output.provider_insights],
        tool_calls=[
            f"{record.tool_name}({record.arguments})"
            for record in tool_call_records
        ]
        or [f"fastmcp:{pydantic_agent_mcp_url()}"],
        tool_call_records=tool_call_records,
    )


def research_with_pydantic_agent(
    question: str,
    state: str,
    run_id: str,
    site_context: str | None = None,
) -> PydanticAgentResearchResult:
    if not pydantic_agent_is_configured():
        raise PydanticAgentResearchError("Pydantic AI model is not configured")

    try:
        return asyncio.run(
            research_with_pydantic_agent_async(
                question=question,
                state=state,
                run_id=run_id,
                site_context=site_context,
            )
        )
    except Exception as exc:
        raise PydanticAgentResearchError(str(exc)) from exc


async def research_with_pydantic_agent_async(
    question: str,
    state: str,
    run_id: str,
    site_context: str | None = None,
) -> PydanticAgentResearchResult:
    if not pydantic_agent_is_configured():
        raise PydanticAgentResearchError("Pydantic AI model is not configured")

    try:
        return await _research_with_pydantic_agent(
            question=question,
            state=state,
            run_id=run_id,
            site_context=site_context,
        )
    except Exception as exc:
        raise PydanticAgentResearchError(str(exc)) from exc
