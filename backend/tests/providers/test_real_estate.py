import pytest

from app.providers.models import ProviderQueryRequest
from app.providers.service import query_provider_data
from app.providers.texas_sources.real_estate import TEXAS_REAL_ESTATE_RESEARCH_CENTER, TRERC_SEARCH_URL


class FakeRealEstateHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def get_json(
        self,
        url: str,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> list[dict]:
        self.calls.append((url, params))
        assert headers and "data-center-feasibility-app" in headers["User-Agent"]
        search_term = str((params or {}).get("search") or "")
        if "industrial real estate" in search_term:
            return [
                {
                    "id": 81544,
                    "title": "Does Texas Have the Energy to Reindustrialize?",
                    "url": "https://trerc.tamu.edu/blog/does-texas-have-the-energy-to-reindustrialize/",
                    "type": "post",
                    "subtype": "post",
                }
            ]

        if "land market" in search_term:
            return [
                {
                    "id": 65179,
                    "title": "Texas Small Rural Land",
                    "url": "https://trerc.tamu.edu/reports/texas-small-rural-land-2391/",
                    "type": "post",
                    "subtype": "reports",
                }
            ]

        return [
            {
                "id": 65089,
                "title": "Industrial Space Race",
                "url": "https://trerc.tamu.edu/article/industrial-space-race-2377/",
                "type": "post",
                "subtype": "article",
            }
        ]


def test_real_estate_provider_is_queryable_search() -> None:
    assert TEXAS_REAL_ESTATE_RESEARCH_CENTER.queryable is True
    assert TEXAS_REAL_ESTATE_RESEARCH_CENTER.endpoints[0].label == "TRERC content search API"
    assert str(TEXAS_REAL_ESTATE_RESEARCH_CENTER.endpoints[0].url) == TRERC_SEARCH_URL


@pytest.mark.anyio
async def test_real_estate_query_returns_market_context_results() -> None:
    http_client = FakeRealEstateHttpClient()

    response = await query_provider_data(
        provider=TEXAS_REAL_ESTATE_RESEARCH_CENTER,
        request=ProviderQueryRequest(params={"site_context": "Austin, TX 78704"}, limit=3),
        http_client=http_client,
    )

    assert len(http_client.calls) == 3
    assert all(call[0] == TRERC_SEARCH_URL for call in http_client.calls)
    assert http_client.calls[0][1]["search"] == "Austin industrial real estate"
    assert http_client.calls[1][1]["search"] == "Austin land market"
    assert response.data["status"] == "live_query"
    assert response.data["source"] == "trerc_wordpress_search"
    assert response.data["input"]["market_area"] == "Austin"
    assert response.data["result_count"] == 3
    assert response.data["results"][0]["title"] == "Does Texas Have the Energy to Reindustrialize?"
    assert response.data["results"][1]["subtype"] == "reports"
    assert response.data["results"][2]["title"] == "Industrial Space Race"
