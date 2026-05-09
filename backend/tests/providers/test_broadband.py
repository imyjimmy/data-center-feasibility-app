import pytest

from app.providers.service import query_provider_data
from app.providers.models import ProviderQueryRequest
from app.providers.texas_sources.broadband import (
    ARCGIS_GEOCODE_URL,
    BROADBANDMAP_INTERNET_URL,
    BROADBAND_CHALLENGE_TYPES,
    BROADBAND_DILIGENCE_LIMITATIONS,
    TEXAS_BROADBAND_DEVELOPMENT_MAP,
    broadband_metadata_payload,
)


class FakeBroadbandHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def get_json(self, url: str, params: dict | None = None) -> dict:
        self.calls.append((url, params))
        if url == ARCGIS_GEOCODE_URL:
            return {
                "spatialReference": {"wkid": 4326, "latestWkid": 4326},
                "candidates": [
                    {
                        "address": "1201 S Lamar Blvd, Austin, Texas, 78704",
                        "location": {"x": -97.76196433127, "y": 30.254656369916},
                        "score": 100,
                        "attributes": {"Match_addr": "1201 S Lamar Blvd, Austin, Texas, 78704"},
                    }
                ],
            }

        if url == BROADBANDMAP_INTERNET_URL:
            return {
                "lat": 30.254656369916,
                "lng": -97.76196433127,
                "h3_hex": "88489e3445fffff",
                "h3_resolution": 8,
                "service_type": "business",
                "count": 3,
                "providers": [
                    {
                        "name": "AT&T",
                        "technology": "Fiber",
                        "technology_code": 50,
                        "max_download_mbps": 5000,
                        "max_upload_mbps": 5000,
                        "provider_id": 130077,
                    },
                    {
                        "name": "Google Fiber",
                        "technology": "Fiber",
                        "technology_code": 50,
                        "max_download_mbps": 2000,
                        "max_upload_mbps": 1000,
                        "provider_id": 240041,
                    },
                    {
                        "name": "T-Mobile",
                        "technology": "Fixed Wireless",
                        "technology_code": 79,
                        "max_download_mbps": 100,
                        "max_upload_mbps": 20,
                        "provider_id": 130403,
                    },
                ],
            }

        raise AssertionError(f"Unexpected URL: {url}")


class UnusedHttpClient:
    async def get_json(self, url: str, params: dict | None = None) -> dict:
        raise AssertionError("Broadband provider should not fetch without location input")


def test_broadband_metadata_payload_is_explicitly_location_queryable() -> None:
    request = ProviderQueryRequest(params={"site_context": "1201 S Lamar Blvd, Austin, TX 78704"})

    payload = broadband_metadata_payload(request)

    assert payload["status"] == "metadata_only"
    assert payload["provider_id"] == "texas_broadband_development_map"
    assert payload["location_queryable"] is True
    assert payload["downloadable_granular_data"] is False
    assert payload["requested_site_context"] == "1201 S Lamar Blvd, Austin, TX 78704"
    assert "FCC Broadband Data Collection" in str(payload["source_basis"])
    assert payload["fcc_challenge_types"] == BROADBAND_CHALLENGE_TYPES
    assert BROADBAND_DILIGENCE_LIMITATIONS[0] in payload["limitations"]


def test_broadband_provider_lists_correct_access_paths_and_limitations() -> None:
    endpoint_labels = {endpoint.label for endpoint in TEXAS_BROADBAND_DEVELOPMENT_MAP.endpoints}

    assert TEXAS_BROADBAND_DEVELOPMENT_MAP.queryable is True
    assert "Broadband Map location API" in endpoint_labels
    assert "FCC National Broadband Map" in endpoint_labels
    assert "FCC Broadband Funding Map" in endpoint_labels
    assert "Texas BEAD Map" in endpoint_labels
    assert any("cannot be downloaded" in limitation for limitation in TEXAS_BROADBAND_DEVELOPMENT_MAP.limitations)
    assert any("carrier outreach" in limitation for limitation in TEXAS_BROADBAND_DEVELOPMENT_MAP.limitations)


@pytest.mark.anyio
async def test_broadband_query_returns_structured_metadata_without_location_input() -> None:
    response = await query_provider_data(
        provider=TEXAS_BROADBAND_DEVELOPMENT_MAP,
        request=ProviderQueryRequest(),
        http_client=UnusedHttpClient(),
    )

    assert response.provider.id == "texas_broadband_development_map"
    assert response.data["status"] == "metadata_only"
    assert response.data["location_queryable"] is True
    assert response.data["query_status"] == "missing_location"
    assert response.data["address_lookup_path"].startswith("Provide site_context or lat/lng")
    assert response.request_params["returnGeometry"] == "true"
    access_path_labels = {item["label"] for item in response.data["access_paths"]}
    assert "FCC National Broadband Map" in access_path_labels
    assert "Texas BEAD Map" in access_path_labels


@pytest.mark.anyio
async def test_broadband_query_geocodes_address_and_returns_location_specific_providers() -> None:
    http_client = FakeBroadbandHttpClient()

    response = await query_provider_data(
        provider=TEXAS_BROADBAND_DEVELOPMENT_MAP,
        request=ProviderQueryRequest(params={"site_context": "1201 S Lamar Blvd, Austin, TX 78704"}),
        http_client=http_client,
    )

    assert [call[0] for call in http_client.calls] == [ARCGIS_GEOCODE_URL, BROADBANDMAP_INTERNET_URL]
    assert http_client.calls[1][1] == {
        "lat": 30.254656369916,
        "lng": -97.76196433127,
        "service_type": "business",
    }
    assert str(response.request_url) == BROADBANDMAP_INTERNET_URL
    assert response.data["status"] == "live_query"
    assert response.data["input"]["site_context"] == "1201 S Lamar Blvd, Austin, TX 78704"
    assert response.data["geocode"]["matched_address"] == "1201 S Lamar Blvd, Austin, Texas, 78704"
    assert response.data["h3_hex"] == "88489e3445fffff"
    assert response.data["summary"]["provider_count"] == 3
    assert response.data["summary"]["fiber_provider_count"] == 2
    assert response.data["summary"]["fiber_provider_names"] == ["AT&T", "Google Fiber"]
    assert response.data["summary"]["max_reported_download_mbps"] == 5000
    assert response.data["providers"][0]["technology"] == "Fiber"


@pytest.mark.anyio
async def test_broadband_query_uses_coordinates_without_geocoding() -> None:
    http_client = FakeBroadbandHttpClient()

    response = await query_provider_data(
        provider=TEXAS_BROADBAND_DEVELOPMENT_MAP,
        request=ProviderQueryRequest(params={"lat": 30.2545, "lng": -97.7623, "service_type": "business"}),
        http_client=http_client,
    )

    assert [call[0] for call in http_client.calls] == [BROADBANDMAP_INTERNET_URL]
    assert http_client.calls[0][1] == {"lat": 30.2545, "lng": -97.7623, "service_type": "business"}
    assert response.data["status"] == "live_query"
    assert response.request_params["lat"] == 30.2545
    assert response.request_params["lng"] == -97.7623
