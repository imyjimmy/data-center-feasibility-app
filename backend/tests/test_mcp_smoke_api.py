from fastapi.testclient import TestClient

from app import mcp_smoke
from app.main import app
from app.pydantic_agent import PydanticAgentResearchResult


client = TestClient(app)


def test_mcp_smoke_endpoint_returns_provider_results(monkeypatch) -> None:
    async def fake_run_mcp_provider_smoke(
        state: str = "TX",
        limit: int = 2,
        site_context: str | None = None,
    ) -> mcp_smoke.McpSmokeResponse:
        return mcp_smoke.McpSmokeResponse(
            mcp_url="http://127.0.0.1:9000/mcp",
            tools=[mcp_smoke.McpToolSummary(name="list_providers")],
            providers=[
                mcp_smoke.McpProviderSmokeResult(
                    provider_id="travis_county_parcels",
                    provider_name="Travis County Parcels",
                    queryable=True,
                    source="live_query",
                    query_scope="site_address_filter",
                    mcp_tools=["query_provider"],
                    request_url="https://example.test/query",
                    health_status="configured",
                    query_status="returned",
                    data_keys=["features"],
                    data_preview={"features": "2 items"},
                    feature_count=2,
                    sample_attributes={"OBJECTID": 1},
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
    assert body["providers"][0]["source"] == "live_query"
    assert body["providers"][0]["data_preview"] == {"features": "2 items"}
    assert body["providers"][0]["sample_attributes"] == {"OBJECTID": 1}


def test_mcp_smoke_builds_broadband_site_query_from_address() -> None:
    args, scope = mcp_smoke._site_query_args(
        provider_id="texas_broadband_development_map",
        site_context="1201 S Lamar Blvd, Austin, TX 78704",
        limit=2,
    )

    assert scope == "site_address_geocode"
    assert args["provider_id"] == "texas_broadband_development_map"
    assert args["params"] == {
        "site_context": "1201 S Lamar Blvd, Austin, TX 78704",
        "service_type": "business",
    }


def test_mcp_smoke_builds_broadband_site_query_from_coordinates() -> None:
    args, scope = mcp_smoke._site_query_args(
        provider_id="texas_broadband_development_map",
        site_context="30.2545,-97.7623",
        limit=2,
    )

    assert scope == "site_point"
    assert args["params"] == {
        "lat": 30.2545,
        "lng": -97.7623,
        "service_type": "business",
        "site_context": "30.2545,-97.7623",
    }


def test_mcp_smoke_builds_txgio_site_catalog_search() -> None:
    args, scope = mcp_smoke._site_query_args(
        provider_id="txgio_geospatial_catalog",
        site_context="1201 S Lamar Blvd, Austin, TX 78704",
        limit=2,
    )

    assert scope == "site_catalog_search"
    assert args["provider_id"] == "txgio_geospatial_catalog"
    assert args["limit"] == 2
    assert args["params"] == {"site_context": "1201 S Lamar Blvd, Austin, TX 78704"}


def test_mcp_smoke_builds_real_estate_market_search() -> None:
    args, scope = mcp_smoke._site_query_args(
        provider_id="texas_real_estate_research_center",
        site_context="Austin, TX 78704",
        limit=2,
    )

    assert scope == "market_research_search"
    assert args["provider_id"] == "texas_real_estate_research_center"
    assert args["limit"] == 2
    assert args["params"] == {"site_context": "Austin, TX 78704"}


def test_mcp_smoke_data_preview_keeps_broadband_provider_results() -> None:
    preview = mcp_smoke._data_preview(
        {
            "status": "live_query",
            "provider_id": "texas_broadband_development_map",
            "input": {"lat": 30.2545, "lng": -97.7623, "service_type": "business"},
            "summary": {
                "provider_count": 10,
                "fiber_provider_count": 5,
                "fiber_provider_names": ["AT&T", "Google Fiber", "Astound Broadband", "Spectrum", "Xfinity"],
            },
            "providers": [
                {"name": "AT&T", "technology": "Fiber", "max_download_mbps": 5000, "max_upload_mbps": 5000},
                {"name": "Google Fiber", "technology": "Fiber", "max_download_mbps": 2000, "max_upload_mbps": 1000},
            ],
            "limitations": ["Needs carrier validation."],
        }
    )

    assert preview["status"] == "live_query"
    assert preview["summary"]["provider_count"] == 10
    assert preview["summary"]["fiber_provider_count"] == 5
    assert preview["providers"][0]["name"] == "AT&T"
    assert preview["providers"][0]["technology"] == "Fiber"


def test_mcp_smoke_data_preview_keeps_txgio_catalog_matches() -> None:
    preview = mcp_smoke._data_preview(
        {
            "status": "live_query",
            "provider_id": "txgio_geospatial_catalog",
            "queries": [{"query": "TxGIO StratMap Parcels Latest", "total": 1, "returned": 1}],
            "match_count": 1,
            "matches": [
                {
                    "title": "TxGIO StratMap Parcels (Latest)",
                    "type": "Feature Service",
                    "service_url": "https://feature.tnris.org/arcgis/rest/services/Parcels/stratmap_land_parcels_48_most_recent/MapServer/0",
                    "item_url": "https://www.arcgis.com/home/item.html?id=3b262ce74a864836972188fca772ca48",
                }
            ],
        }
    )

    assert preview["status"] == "live_query"
    assert preview["match_count"] == 1
    assert preview["matches"][0]["title"] == "TxGIO StratMap Parcels (Latest)"
    assert preview["matches"][0]["service_url"].startswith("https://feature.tnris.org/")


def test_mcp_smoke_data_preview_keeps_real_estate_search_results() -> None:
    preview = mcp_smoke._data_preview(
        {
            "status": "live_query",
            "provider_id": "texas_real_estate_research_center",
            "searches": [{"search_term": "Austin industrial real estate", "returned": 1}],
            "result_count": 1,
            "results": [
                {
                    "title": "Industrial Space Race",
                    "url": "https://trerc.tamu.edu/article/industrial-space-race-2377/",
                    "subtype": "article",
                }
            ],
        }
    )

    assert preview["status"] == "live_query"
    assert preview["result_count"] == 1
    assert preview["results"][0]["title"] == "Industrial Space Race"
    assert preview["results"][0]["url"].startswith("https://trerc.tamu.edu/")


def test_mcp_smoke_maps_broadband_geocode_point() -> None:
    geo_features = mcp_smoke._geo_features(
        provider_id="texas_broadband_development_map",
        provider_name="Texas Broadband Development Map",
        data={
            "source": "broadbandmap_com_fcc_bdc_derived",
            "geocode": {
                "lat": 30.254656369916,
                "lng": -97.76196433127,
                "matched_address": "Austin, Texas, 78704",
                "score": 100,
            },
        },
        features=[],
    )

    assert len(geo_features) == 1
    assert geo_features[0].geometry_type == "point"
    assert geo_features[0].point == [30.254656369916, -97.76196433127]
    assert geo_features[0].label == "Austin, Texas, 78704"


def test_mcp_smoke_maps_txgio_catalog_match_extents() -> None:
    geo_features = mcp_smoke._geo_features(
        provider_id="txgio_geospatial_catalog",
        provider_name="Texas Geographic Information Office Data Catalog",
        data={
            "matches": [
                {
                    "id": "3b262ce74a864836972188fca772ca48",
                    "title": "TxGIO StratMap Parcels (Latest)",
                    "type": "Feature Service",
                    "owner": "DETCOG.GIS",
                    "service_url": "https://feature.tnris.org/arcgis/rest/services/Parcels/stratmap_land_parcels_48_most_recent/MapServer/0",
                    "extent": [[-106.9276, 25.511789], [-93.353691, 36.815432]],
                }
            ],
        },
        features=[],
    )

    assert len(geo_features) == 1
    assert geo_features[0].geometry_type == "catalog_extent"
    assert geo_features[0].label == "TxGIO StratMap Parcels (Latest)"
    assert geo_features[0].rings == [
        [
            [25.511789, -106.9276],
            [25.511789, -93.353691],
            [36.815432, -93.353691],
            [36.815432, -106.9276],
            [25.511789, -106.9276],
        ]
    ]


def test_mcp_agent_test_endpoint_invokes_agent(monkeypatch) -> None:
    def fake_is_configured() -> bool:
        return True

    async def fake_research_with_pydantic_agent_async(**_: object) -> PydanticAgentResearchResult:
        return PydanticAgentResearchResult(
            summary="Agent used MCP tools.",
            provider_insights=[{"provider_id": "travis_county_parcels", "summary": "Returned parcel data."}],
            tool_calls=["fastmcp:http://127.0.0.1:9000/mcp"],
        )

    async def fake_run_mcp_provider_smoke(
        state: str = "TX",
        limit: int = 2,
        site_context: str | None = None,
    ) -> mcp_smoke.McpSmokeResponse:
        return mcp_smoke.McpSmokeResponse(
            mcp_url="http://127.0.0.1:9000/mcp",
            tools=[],
            providers=[
                mcp_smoke.McpProviderSmokeResult(
                    provider_id="travis_county_parcels",
                    provider_name="Travis County Parcels",
                    queryable=True,
                    source="live_query",
                    query_scope="site_address_filter",
                    query_status="returned",
                    feature_count=2,
                )
            ],
        )

    monkeypatch.setattr(mcp_smoke, "pydantic_agent_is_configured", fake_is_configured)
    monkeypatch.setattr(
        mcp_smoke,
        "research_with_pydantic_agent_async",
        fake_research_with_pydantic_agent_async,
    )
    monkeypatch.setattr(mcp_smoke, "run_mcp_provider_smoke", fake_run_mcp_provider_smoke)

    response = client.post(
        "/api/mcp-smoke/agent",
        json={"prompt": "Use MCPs to inspect parcel data.", "site_context": "1201 S Lamar Blvd"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Agent used MCP tools."
    assert body["provider_insights"][0]["provider_id"] == "travis_county_parcels"
    assert body["tool_calls"] == ["fastmcp:http://127.0.0.1:9000/mcp"]
    assert body["evidence"][0]["source"] == "live_query"
    assert body["site_context"] == "1201 S Lamar Blvd"


def test_mcp_agent_test_endpoint_requires_configured_agent(monkeypatch) -> None:
    monkeypatch.setattr(mcp_smoke, "pydantic_agent_is_configured", lambda: False)

    response = client.post("/api/mcp-smoke/agent", json={"prompt": "Use MCPs."})

    assert response.status_code == 503
