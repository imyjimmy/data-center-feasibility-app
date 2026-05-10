from typing import Any

import pytest

from app.providers.models import ProviderQueryResponse
from app.provider_mcp import build_austin_area_parcel_shortlist, create_provider_mcp, create_research_mcp
from app.providers.texas_sources.travis_parcels import TRAVIS_COUNTY_PARCELS


def test_create_research_mcp() -> None:
    mcp = create_research_mcp()

    assert mcp.name == "Data Center Feasibility Texas Open Data MCP"


@pytest.mark.anyio
async def test_austin_area_parcel_shortlist_returns_candidates(monkeypatch) -> None:
    async def fake_query_provider_data(**_: Any) -> ProviderQueryResponse:
        return ProviderQueryResponse(
            provider=TRAVIS_COUNTY_PARCELS,
            request_url=TRAVIS_COUNTY_PARCELS.endpoints[0].url,
            request_params={"where": "1=1"},
            data={
                "query_fallback": {"reason": "acreage_filter_rejected_by_provider"},
                "client_side_filter": {"min_acres": 25},
                "features": [
                    {
                        "attributes": {
                            "PROP_ID": 100,
                            "situs_address": "LARGE PARCEL",
                            "py_owner_name": "OWNER LLC",
                            "tcad_acres": 42,
                            "land_type_desc": "COMMERCIAL",
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
                ],
            },
        )

    monkeypatch.setattr("app.provider_mcp.query_provider_data", fake_query_provider_data)
    result = await build_austin_area_parcel_shortlist(
        site_context="Which Austin-area parcels are plausible for a 25 MW edge data center?",
        min_acres=25,
        limit=10,
    )

    assert result["status"] == "returned"
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["prop_id"] == 100
    assert result["query_fallback"]["reason"] == "acreage_filter_rejected_by_provider"


def test_create_provider_scoped_mcp() -> None:
    mcp = create_provider_mcp("travis_county_parcels")

    assert mcp.name == "Travis County Parcels MCP"


def test_create_provider_scoped_mcp_rejects_unknown_provider() -> None:
    try:
        create_provider_mcp("missing")
    except KeyError as exc:
        assert "Unknown provider" in str(exc)
    else:
        raise AssertionError("Expected missing provider to raise KeyError")
