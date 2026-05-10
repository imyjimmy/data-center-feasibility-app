import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import analysis
from app.mcp_smoke import McpProviderSmokeResult
from app.main import app
from app.pydantic_agent import PydanticAgentResearchResult
from app.providers.models import ProviderQueryResponse
from app.providers.texas_sources.travis_parcels import TRAVIS_COUNTY_PARCELS


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
    captured: dict[str, Any] = {}

    def fake_is_configured() -> bool:
        return True

    def fake_research_with_pydantic_agent(**kwargs: Any) -> PydanticAgentResearchResult:
        captured.update(kwargs)
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
    assert "Pydantic AI reviewed provider coverage through FastMCP." in run["agent_summary"]
    assert "candidate_context" in captured
    travis = next(
        insight
        for insight in run["provider_insights"]
        if insight["provider_id"] == "travis_county_parcels"
    )
    assert travis["status"] == "researched"
    assert travis["summary"] == "The agent selected parcel geometry as a primary zoning screen."


def test_build_candidate_parcels_ranks_area_search_features() -> None:
    evidence = [
        McpProviderSmokeResult(
            provider_id="travis_county_parcels",
            provider_name="Travis County Parcels",
            queryable=True,
            source="live_query",
            query_scope="area_parcel_search",
            query_status="returned",
            feature_count=2,
            data_preview={
                "features": [
                    {
                        "attributes": {
                            "OBJECTID": 1,
                            "PROP_ID": 101,
                            "situs_address": "LARGE AUSTIN AREA PARCEL",
                            "tcad_acres": 42,
                            "py_owner_name": "Example Owner",
                        },
                        "geometry": {
                            "rings": [
                                [
                                    [-97.7, 30.2],
                                    [-97.69, 30.2],
                                    [-97.69, 30.21],
                                    [-97.7, 30.2],
                                ]
                            ]
                        },
                    },
                    {
                        "attributes": {
                            "OBJECTID": 2,
                            "PROP_ID": 202,
                            "situs_address": "SMALL AUSTIN AREA PARCEL",
                            "tcad_acres": 10,
                        },
                        "geometry": {
                            "rings": [
                                [
                                    [-97.8, 30.3],
                                    [-97.79, 30.3],
                                    [-97.79, 30.31],
                                    [-97.8, 30.3],
                                ]
                            ]
                        },
                    },
                ]
            },
        )
    ]

    candidates = analysis._build_candidate_parcels(evidence)

    assert [candidate.id for candidate in candidates] == ["TRAVIS-101", "TRAVIS-202"]
    assert candidates[0].rank == 1
    assert candidates[0].acres == 42
    assert candidates[0].firstBlocker == "Power Interconnection"
    assert candidates[1].firstBlocker == "Parcel Scale"


def test_candidate_research_context_serializes_enriched_evidence() -> None:
    candidate = analysis.ParcelCandidate(
        rank=1,
        id="TRAVIS-7007",
        name="AUSTIN AREA INDUSTRIAL PARCEL",
        jurisdiction="Austin ETJ",
        acres=31.5,
        score=65,
        zoning="LI",
        zoningFit="industrial",
        landUse="Industrial",
        firstBlocker="Power Interconnection",
        electricService="Austin Energy service-area intersect",
        waterService="Austin Water service-area intersect",
        roadAccess="Not returned by configured MCP evidence",
        roadAccessType="any",
        distanceToSubstation=3.0,
        fiberConfidence="medium",
        floodplain=False,
        wetlands=False,
        coolingModes=["air"],
        center=[30.2, -97.7],
        mapRadius=0.012,
        evidence=["City of Austin zoning intersect at parcel centroid returned: LI."],
        scoreBreakdown=analysis.ParcelScoreBreakdown(power=14, water=12, site=20, constraints=17, market=7),
    )

    context = analysis._candidate_research_context([candidate])

    assert "TRAVIS-7007" in context
    assert "Austin Water service-area intersect" in context
    assert "City of Austin zoning intersect" in context


def test_collect_candidate_parcels_uses_direct_austin_area_provider_query(monkeypatch) -> None:
    async def fake_query_provider_data(**kwargs: Any) -> ProviderQueryResponse:
        request = kwargs["request"]
        provider = kwargs["provider"]
        if provider.id != "travis_county_parcels":
            return ProviderQueryResponse(
                provider=provider,
                request_url=provider.endpoints[0].url,
                request_params={},
                data={"features": []},
            )

        assert request.where == "GIS_acres >= 25"
        assert request.bbox is not None
        return ProviderQueryResponse(
            provider=TRAVIS_COUNTY_PARCELS,
            request_url=TRAVIS_COUNTY_PARCELS.endpoints[0].url,
            request_params={"where": request.where},
            data={
                "features": [
                    {
                        "attributes": {
                            "OBJECTID": 7,
                            "PROP_ID": 7007,
                            "situs_address": "AUSTIN AREA INDUSTRIAL PARCEL",
                            "tcad_acres": 31.5,
                        },
                        "geometry": {
                            "rings": [
                                [
                                    [-97.7, 30.2],
                                    [-97.69, 30.2],
                                    [-97.69, 30.21],
                                    [-97.7, 30.2],
                                ]
                            ]
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(analysis, "query_provider_data", fake_query_provider_data)

    candidates = asyncio.run(
        analysis._collect_candidate_parcels(
            state="TX",
            site_context="Which Austin-area parcels are plausible for a 25 MW edge data center?",
        )
    )

    assert len(candidates) == 1
    assert candidates[0].id == "TRAVIS-7007"
    assert candidates[0].acres == 31.5


def test_enrich_candidate_adds_centroid_provider_evidence(monkeypatch) -> None:
    async def fake_query_provider_data(**kwargs: Any) -> ProviderQueryResponse:
        provider = kwargs["provider"]
        data_by_provider = {
            "austin_zoning": {"features": [{"attributes": {"ZONING": "LI"}}]},
            "austin_jurisdiction": {"features": [{"attributes": {"JURISDICTION": "FULL PURPOSE"}}]},
            "austin_water_utility_service_area": {"features": [{"attributes": {"NAME": "Austin Water"}}]},
            "austin_energy_service_area": {"features": [{"attributes": {"NAME": "Austin Energy"}}]},
            "electric_power_transmission_lines": {"features": [{"attributes": {"VOLTAGE": 138}}]},
            "texas_broadband_development_map": {"summary": {"fiber_provider_count": 2}},
        }
        return ProviderQueryResponse(
            provider=provider,
            request_url=provider.endpoints[0].url,
            request_params={},
            data=data_by_provider.get(provider.id, {}),
        )

    monkeypatch.setattr(analysis, "query_provider_data", fake_query_provider_data)
    candidate = analysis.ParcelCandidate(
        rank=1,
        id="TRAVIS-7007",
        name="AUSTIN AREA INDUSTRIAL PARCEL",
        jurisdiction="Travis County / Austin-area evidence",
        acres=31.5,
        score=57,
        zoning="Zoning not returned by configured MCP evidence",
        zoningFit="review",
        landUse="Industrial",
        firstBlocker="Power Interconnection",
        electricService="Utility/TSP not returned by configured MCP evidence",
        waterService="Service area/capacity requires provider evidence",
        roadAccess="Not returned by configured MCP evidence",
        roadAccessType="any",
        distanceToSubstation=99.0,
        fiberConfidence="low",
        floodplain=False,
        wetlands=False,
        coolingModes=["air"],
        center=[30.2, -97.7],
        mapRadius=0.012,
        evidence=[],
        scoreBreakdown=analysis.ParcelScoreBreakdown(power=10, water=8, site=20, constraints=14, market=5),
    )

    enriched = asyncio.run(analysis._enrich_candidate(candidate))

    assert enriched.zoning == "LI"
    assert enriched.zoningFit == "industrial"
    assert enriched.jurisdiction == "FULL PURPOSE"
    assert enriched.waterService == "Austin Water service-area intersect"
    assert enriched.electricService == "Austin Energy service-area intersect"
    assert enriched.distanceToSubstation == 3.0
    assert enriched.fiberConfidence == "medium"
    assert enriched.score > candidate.score


def test_unknown_analysis_run_returns_404() -> None:
    response = client.get("/api/analysis-runs/missing")

    assert response.status_code == 404
