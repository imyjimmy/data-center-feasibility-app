from typing import Any

import httpx
import pytest

from app.providers.models import ProviderQueryRequest
from app.providers.service import query_provider_data
from app.providers.texas_sources.web_search import DATA_CENTER_WEB_SEARCH


class FakeWebSearchHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None, dict[str, str] | None]] = []

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((url, params, headers))
        return {
            "web": {
                "results": [
                    {
                        "title": "Austin Data Center",
                        "url": "https://example.com/austin-data-center",
                        "description": "A public address lead for an Austin data center.",
                    }
                ]
            }
        }


class FakeRateLimitedWebSearchHttpClient:
    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = httpx.Request("GET", url, params=params)
        response = httpx.Response(status_code=429, request=request)
        raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)


@pytest.mark.anyio
async def test_web_search_provider_returns_not_configured_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    response = await query_provider_data(
        provider=DATA_CENTER_WEB_SEARCH,
        request=ProviderQueryRequest(params={"site_context": "Austin area data centers"}),
        http_client=FakeWebSearchHttpClient(),
    )

    assert response.data["status"] == "not_configured"
    assert response.data["missing_env"] == "BRAVE_SEARCH_API_KEY"
    assert response.data["results"] == []
    assert response.data["queries"][0] == "Austin Texas data center address"


@pytest.mark.anyio
async def test_web_search_provider_queries_configured_search_api(monkeypatch) -> None:
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")
    http_client = FakeWebSearchHttpClient()

    response = await query_provider_data(
        provider=DATA_CENTER_WEB_SEARCH,
        request=ProviderQueryRequest(limit=2, params={"site_context": "Austin area data centers"}),
        http_client=http_client,
    )

    assert response.data["status"] == "live_query"
    assert response.data["result_count"] == 1
    assert response.data["results"][0]["title"] == "Austin Data Center"
    assert http_client.calls
    _, params, headers = http_client.calls[0]
    assert params is not None
    assert params["q"] == "Austin Texas data center address"
    assert params["count"] == 2
    assert headers is not None
    assert headers["X-Subscription-Token"] == "test-key"


@pytest.mark.anyio
async def test_web_search_provider_returns_rate_limited_result(monkeypatch) -> None:
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")

    response = await query_provider_data(
        provider=DATA_CENTER_WEB_SEARCH,
        request=ProviderQueryRequest(limit=2, params={"site_context": "Austin area data centers"}),
        http_client=FakeRateLimitedWebSearchHttpClient(),
    )

    assert response.data["status"] == "rate_limited"
    assert response.data["result_count"] == 0
    assert response.data["searches"][0]["status"] == "rate_limited"
    assert "HTTP 429 Too Many Requests" in response.data["limitations"][-1]
