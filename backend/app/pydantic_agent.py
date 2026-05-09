import asyncio
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP


class AgentProviderInsight(BaseModel):
    provider_id: str
    status: str | None = None
    summary: str | None = None
    limitations: list[str] = Field(default_factory=list)


class AgentResearchResult(BaseModel):
    summary: str
    provider_insights: list[AgentProviderInsight] = Field(default_factory=list)


class PydanticAgentResearchResult(BaseModel):
    summary: str | None = None
    provider_insights: list[dict] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)


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


async def _research_with_pydantic_agent(question: str, state: str, run_id: str) -> PydanticAgentResearchResult:
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
            f"User request: {question}\n\n"
            "Use the MCP tools to list providers and, where useful, inspect queryable providers. "
            "Return provider_insights with provider_id, status, summary, and limitations."
        )

    return PydanticAgentResearchResult(
        summary=result.output.summary,
        provider_insights=[insight.model_dump(mode="json") for insight in result.output.provider_insights],
        tool_calls=[f"fastmcp:{pydantic_agent_mcp_url()}"],
    )


def research_with_pydantic_agent(question: str, state: str, run_id: str) -> PydanticAgentResearchResult:
    if not pydantic_agent_is_configured():
        raise PydanticAgentResearchError("Pydantic AI model is not configured")

    try:
        return asyncio.run(_research_with_pydantic_agent(question=question, state=state, run_id=run_id))
    except Exception as exc:
        raise PydanticAgentResearchError(str(exc)) from exc
