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


class PydanticAgentResearchResult(BaseModel):
    summary: str | None = None
    provider_insights: list[dict] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_records: list[AgentToolCallRecord] = Field(default_factory=list)


class PydanticAgentResearchError(RuntimeError):
    pass


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
        instructions=(
            "You are a data-center feasibility research agent. Use the attached FastMCP tools to "
            "inspect configured Texas open-data providers before answering. Return concise, "
            "evidence-focused structured output. Do not invent provider IDs; use IDs returned by "
            "the MCP tools. Prefer providers relevant to power, water, fiber, parcel, zoning, and "
            "market diligence."
        ),
    )

    async with agent:
        result = await agent.run(
            f"Run id: {run_id}\n"
            f"State: {state}\n"
            f"Site/location context: {site_context or 'No site provided'}\n"
            f"User request: {question}\n\n"
            "Use the MCP tools to list providers and inspect queryable providers. If a site or "
            "address is provided, make the query_provider calls location-specific using a where "
            "filter or bbox when practical, and say when a provider cannot answer site-level "
            "questions. Return provider_insights with provider_id, status, summary, and limitations."
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
            _research_with_pydantic_agent(
                question=question,
                state=state,
                run_id=run_id,
                site_context=site_context,
            )
        )
    except Exception as exc:
        raise PydanticAgentResearchError(str(exc)) from exc
