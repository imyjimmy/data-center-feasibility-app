import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import analysis
from app.main import app
from app.pydantic_agent import PydanticAgentResearchResult


client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_real_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYDANTIC_AI_ENABLED", "false")


def test_analysis_run_populates_provider_insights_in_background() -> None:
    response = client.post(
        "/api/analysis-runs",
        json={"question": "Find Texas parcels with power, water, fiber, and zoning context."},
    )

    assert response.status_code == 200
    created = response.json()
    assert created["question"].startswith("Find Texas parcels")

    run_response = client.get(f"/api/analysis-runs/{created['run_id']}")
    for _ in range(20):
        if run_response.json()["status"] == "complete":
            break
        time.sleep(0.05)
        run_response = client.get(f"/api/analysis-runs/{created['run_id']}")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "complete"
    assert run["orchestration"]["status"] in {
        "agent_skipped",
        "agent_complete",
        "agent_failed",
    }
    insight_ids = {insight["provider_id"] for insight in run["provider_insights"]}
    assert "ercot_market_data_transparency" in insight_ids
    assert "travis_county_parcels" in insight_ids


def test_analysis_run_skips_agent_when_model_missing(monkeypatch) -> None:
    monkeypatch.delenv("PYDANTIC_AI_MODEL", raising=False)

    response = client.post(
        "/api/analysis-runs",
        json={"question": "Find Texas parcel provider context."},
    )

    assert response.status_code == 200
    created = response.json()

    run_response = client.get(f"/api/analysis-runs/{created['run_id']}")
    for _ in range(20):
        if run_response.json()["status"] == "complete":
            break
        time.sleep(0.05)
        run_response = client.get(f"/api/analysis-runs/{created['run_id']}")

    run = run_response.json()
    assert run["status"] == "complete"
    assert run["orchestration"]["status"] == "agent_skipped"
    assert run["agent_summary"] is None


def test_analysis_run_merges_pydantic_agent_provider_updates(monkeypatch) -> None:
    def fake_is_configured() -> bool:
        return True

    def fake_research_with_pydantic_agent(**_: Any) -> PydanticAgentResearchResult:
        return PydanticAgentResearchResult(
            summary="Pydantic AI reviewed provider coverage through FastMCP.",
            provider_insights=[
                {
                    "provider_id": "travis_county_parcels",
                    "status": "researched",
                    "summary": "The agent selected parcel geometry as a primary zoning screen.",
                    "limitations": ["Still requires zoning entitlement confirmation."],
                }
            ],
            tool_calls=["fastmcp:http://127.0.0.1:9000/mcp"],
        )

    monkeypatch.setattr(analysis, "pydantic_agent_is_configured", fake_is_configured)
    monkeypatch.setattr(analysis, "research_with_pydantic_agent", fake_research_with_pydantic_agent)

    response = client.post(
        "/api/analysis-runs",
        json={"question": "Find Texas parcels with zoning evidence."},
    )

    assert response.status_code == 200
    created = response.json()

    run_response = client.get(f"/api/analysis-runs/{created['run_id']}")
    for _ in range(20):
        if run_response.json()["status"] == "complete":
            break
        time.sleep(0.05)
        run_response = client.get(f"/api/analysis-runs/{created['run_id']}")

    run = run_response.json()
    assert run["orchestration"] == {
        "status": "agent_complete",
        "detail": "Pydantic AI completed delegated MCP research and returned backend data updates.",
        "tool_calls": ["fastmcp:http://127.0.0.1:9000/mcp"],
    }
    assert run["agent_summary"] == "Pydantic AI reviewed provider coverage through FastMCP."
    travis = next(
        insight
        for insight in run["provider_insights"]
        if insight["provider_id"] == "travis_county_parcels"
    )
    assert travis["status"] == "researched"
    assert travis["summary"] == "The agent selected parcel geometry as a primary zoning screen."


def test_unknown_analysis_run_returns_404() -> None:
    response = client.get("/api/analysis-runs/missing")

    assert response.status_code == 404
