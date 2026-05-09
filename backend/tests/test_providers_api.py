from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.providers.api import get_http_client


class FakeProviderHttpClient:
    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "called_url": url,
            "called_params": params,
            "features": [{"attributes": {"OBJECTID": 1}}],
        }


client = TestClient(app)


def test_list_data_providers_defaults_to_texas() -> None:
    response = client.get("/api/providers")

    assert response.status_code == 200
    provider_ids = {provider["id"] for provider in response.json()["providers"]}
    assert "austin_water_utility_service_area" in provider_ids
    assert "travis_county_parcels" in provider_ids


def test_filter_data_providers_by_concern() -> None:
    response = client.get("/api/providers", params={"concern": "fiber_availability"})

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert [provider["id"] for provider in providers] == ["texas_broadband_development_map"]


def test_metadata_only_provider_returns_safe_metadata_response() -> None:
    response = client.post(
        "/api/providers/texas_broadband_development_map/query",
        json={"where": "1=1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["id"] == "texas_broadband_development_map"
    assert body["data"]["status"] == "metadata_only"
    assert body["data"]["limitations"]


def test_query_arcgis_provider_uses_standard_query_parameters() -> None:
    app.dependency_overrides[get_http_client] = lambda: FakeProviderHttpClient()
    try:
        response = client.post(
            "/api/providers/travis_county_parcels/query",
            json={"where": "OBJECTID = 1", "out_fields": "OBJECTID", "limit": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["id"] == "travis_county_parcels"
    assert body["request_params"]["where"] == "OBJECTID = 1"
    assert body["request_params"]["outFields"] == "OBJECTID"
    assert body["request_params"]["resultRecordCount"] == 1
    assert body["data"]["features"][0]["attributes"]["OBJECTID"] == 1
