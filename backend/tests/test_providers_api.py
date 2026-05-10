import os
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.providers.api import get_http_client
from app.providers.texas_sources import ercot


class FakeProviderHttpClient:
    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "called_url": url,
            "called_params": params,
            "called_headers": headers,
            "features": [{"attributes": {"OBJECTID": 1}}],
        }


class FakeErcotHttpClient:
    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if url.endswith("daily-prc.json"):
            return {
                "lastUpdated": "2026-05-09 16:40:05-0500",
                "current_condition": {
                    "title": "Normal Conditions",
                    "state": "normal",
                    "condition_note": "There is enough power for current demand.",
                    "prc_value": "15,914",
                },
                "data": [{"timestamp": "2026-05-09 16:40:05-0500", "prc": 15914}],
            }

        return {
            "lastUpdated": "2026-05-09 16:40:05-0500",
            "data": [
                {
                    "hourEnding": 17,
                    "interval": 55,
                    "demand": 40643,
                    "capacity": 50026,
                    "forecast": 0,
                }
            ],
        }


class FakeErcotLocationHttpClient:
    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if url.endswith("daily-prc.json"):
            return {
                "lastUpdated": "2026-05-09 16:40:05-0500",
                "current_condition": {
                    "title": "Normal Conditions",
                    "state": "normal",
                    "condition_note": "There is enough power for current demand.",
                    "eea_level": 0,
                },
                "data": [{"timestamp": "2026-05-09 16:40:05-0500", "prc": 15914}],
            }
        if url.endswith("todays-outlook.json"):
            return {"lastUpdated": "2026-05-09 16:40:05-0500", "data": []}
        if url.endswith("spp_node_zone_hub"):
            return {
                "fields": [
                    {"name": "deliveryDate"},
                    {"name": "deliveryHour"},
                    {"name": "deliveryInterval"},
                    {"name": "settlementPoint"},
                    {"name": "settlementPointType"},
                    {"name": "settlementPointPrice"},
                ],
                "data": [["2026-05-09", 16, 4, "HB_NORTH", "HU", 42.5]],
            }
        if url.endswith("lmp_node_zone_hub"):
            return {
                "fields": [
                    {"name": "SCEDTimestamp"},
                    {"name": "settlementPoint"},
                    {"name": "settlementPointType"},
                    {"name": "LMP"},
                ],
                "data": [["2026-05-09T16:40:00", "HB_NORTH", "HU", 43.1]],
            }
        if url.endswith("lmp_electrical_bus"):
            return {
                "fields": [
                    {"name": "SCEDTimestamp"},
                    {"name": "ElectricalBus"},
                    {"name": "LMP"},
                ],
                "data": [["2026-05-09T16:40:00", "TESTBUS_345", 41.2]],
            }

        return {
            "fields": [
                {"name": "SCEDTimestamp"},
                {"name": "constraintName"},
                {"name": "contingencyName"},
                {"name": "shadowPrice"},
            ],
            "data": [["2026-05-09T16:40:00", "TESTBUS_345 constraint", "N-1", 125.75]],
        }


client = TestClient(app)


def test_list_data_providers_defaults_to_texas() -> None:
    response = client.get("/api/providers")

    assert response.status_code == 200
    provider_ids = {provider["id"] for provider in response.json()["providers"]}
    assert "austin_energy_service_area" in provider_ids
    assert "austin_jurisdiction" in provider_ids
    assert "austin_zoning" in provider_ids
    assert "austin_water_utility_service_area" in provider_ids
    assert "data_center_web_search" in provider_ids
    assert "electric_power_transmission_lines" in provider_ids
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


def test_query_ercot_provider_fetches_public_dashboard_json() -> None:
    app.dependency_overrides[get_http_client] = lambda: FakeErcotHttpClient()
    try:
        response = client.post(
            "/api/providers/ercot_market_data_transparency/query",
            json={"limit": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["id"] == "ercot_market_data_transparency"
    assert body["data"]["status"] == "live_query"
    assert body["data"]["grid_condition"]["state"] == "normal"
    assert body["data"]["latest_prc"]["prc"] == 15914
    assert body["data"]["latest_outlook"]["demand"] == 40643
    assert body["request_params"]["dashboards"] == ["daily-prc.json", "todays-outlook.json"]


def test_query_ercot_provider_returns_location_power_report() -> None:
    previous_key = os.environ.get("ERCOT_SUBSCRIPTION_KEY")
    previous_token = os.environ.get("ERCOT_ID_TOKEN")
    os.environ["ERCOT_SUBSCRIPTION_KEY"] = "test-subscription-key"
    os.environ["ERCOT_ID_TOKEN"] = "test-id-token"
    app.dependency_overrides[get_http_client] = lambda: FakeErcotLocationHttpClient()
    try:
        response = client.post(
            "/api/providers/ercot_market_data_transparency/query",
            json={
                "limit": 2,
                "params": {
                    "analysis_type": "location_power",
                    "site_name": "Candidate Parcel A",
                    "county": "Milam",
                    "load_zone": "HB_NORTH",
                    "nearby_settlement_points": ["HB_NORTH"],
                    "electrical_buses": ["TESTBUS_345"],
                    "nearby_grid_elements": ["TESTBUS_345"],
                },
            },
        )
    finally:
        app.dependency_overrides.clear()
        if previous_key is None:
            os.environ.pop("ERCOT_SUBSCRIPTION_KEY", None)
        else:
            os.environ["ERCOT_SUBSCRIPTION_KEY"] = previous_key
        if previous_token is None:
            os.environ.pop("ERCOT_ID_TOKEN", None)
        else:
            os.environ["ERCOT_ID_TOKEN"] = previous_token

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "location_power_report"
    assert body["data"]["public_api_config_status"] == "configured"
    assert body["data"]["report"]["site_power_risk_level"] == "caution"
    assert body["data"]["report"]["location_mapping"]["load_zone"] == "HB_NORTH"
    assert body["data"]["ercot_reports"]["rt_settlement_point_prices"]["status"] == "live_query"
    assert body["data"]["ercot_reports"]["sced_shadow_prices"]["summary"]["location_match_count"] == 1
    assert body["data"]["statewide_context"]["grid_condition"]["state"] == "normal"


def test_ercot_headers_can_fetch_id_token_from_credentials(monkeypatch) -> None:
    class FakeTokenResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"id_token": "fetched-id-token", "expires_in": "3600"}

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def post(
            self,
            url: str,
            data: dict[str, str],
            headers: dict[str, str],
        ) -> FakeTokenResponse:
            assert url == ercot.ERCOT_B2C_TOKEN_URL
            assert data["grant_type"] == "password"
            assert data["response_type"] == "id_token"
            assert data["client_id"] == ercot.ERCOT_B2C_CLIENT_ID
            return FakeTokenResponse()

    monkeypatch.setenv("ERCOT_SUBSCRIPTION_KEY", "test-subscription-key")
    monkeypatch.delenv("ERCOT_ID_TOKEN", raising=False)
    monkeypatch.setenv("ERCOT_USERNAME", "user@example.com")
    monkeypatch.setenv("ERCOT_PASSWORD", "secret")
    monkeypatch.setattr(ercot.httpx, "AsyncClient", FakeAsyncClient)
    ercot._TOKEN_CACHE.clear()

    import asyncio

    headers, token_error = asyncio.run(ercot._ercot_public_api_headers())

    assert token_error is None
    assert headers["Ocp-Apim-Subscription-Key"] == "test-subscription-key"
    assert headers["Authorization"] == "Bearer fetched-id-token"
