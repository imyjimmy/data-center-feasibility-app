from fastapi.testclient import TestClient

from app import mcp_smoke
from app.main import app


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
