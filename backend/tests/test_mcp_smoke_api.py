from fastapi.testclient import TestClient

from app import mcp_smoke
from app.main import app
from app.pydantic_agent import PydanticAgentResearchResult


client = TestClient(app)


def test_mcp_smoke_endpoint_returns_provider_results(monkeypatch) -> None:
    async def fake_run_mcp_provider_smoke(state: str = "TX", limit: int = 2) -> mcp_smoke.McpSmokeResponse:
        return mcp_smoke.McpSmokeResponse(
            mcp_url="http://127.0.0.1:9000/mcp",
            tools=[mcp_smoke.McpToolSummary(name="list_providers")],
            providers=[
                mcp_smoke.McpProviderSmokeResult(
                    provider_id="travis_county_parcels",
                    provider_name="Travis County Parcels",
                    queryable=True,
                    health_status="configured",
                    query_status="returned",
                    data_keys=["features"],
                    feature_count=2,
                )
            ],
        )

    monkeypatch.setattr(mcp_smoke, "run_mcp_provider_smoke", fake_run_mcp_provider_smoke)

    response = client.post("/api/mcp-smoke/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["mcp_url"] == "http://127.0.0.1:9000/mcp"
    assert body["tools"][0]["name"] == "list_providers"
    assert body["providers"][0]["provider_id"] == "travis_county_parcels"
    assert body["providers"][0]["query_status"] == "returned"


def test_mcp_agent_test_endpoint_invokes_agent(monkeypatch) -> None:
    def fake_is_configured() -> bool:
        return True

    def fake_research_with_pydantic_agent(**_: object) -> PydanticAgentResearchResult:
        return PydanticAgentResearchResult(
            summary="Agent used MCP tools.",
            provider_insights=[{"provider_id": "travis_county_parcels", "summary": "Returned parcel data."}],
            tool_calls=["fastmcp:http://127.0.0.1:9000/mcp"],
        )

    monkeypatch.setattr(mcp_smoke, "pydantic_agent_is_configured", fake_is_configured)
    monkeypatch.setattr(mcp_smoke, "research_with_pydantic_agent", fake_research_with_pydantic_agent)

    response = client.post("/api/mcp-smoke/agent", json={"prompt": "Use MCPs to inspect parcel data."})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Agent used MCP tools."
    assert body["provider_insights"][0]["provider_id"] == "travis_county_parcels"
    assert body["tool_calls"] == ["fastmcp:http://127.0.0.1:9000/mcp"]


def test_mcp_agent_test_endpoint_requires_configured_agent(monkeypatch) -> None:
    monkeypatch.setattr(mcp_smoke, "pydantic_agent_is_configured", lambda: False)

    response = client.post("/api/mcp-smoke/agent", json={"prompt": "Use MCPs."})

    assert response.status_code == 503
