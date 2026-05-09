import pytest

from app.providers.models import ProviderQueryRequest
from app.providers.service import query_provider_data
from app.providers.texas_sources.txgio import ARCGIS_ONLINE_SEARCH_URL, TXGIO_GEOSPATIAL_CATALOG


class FakeTxgioHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def get_json(self, url: str, params: dict | None = None) -> dict:
        self.calls.append((url, params))
        query = str((params or {}).get("q") or "")
        if "StratMap Parcels" in query:
            return {
                "total": 1,
                "results": [
                    {
                        "id": "3b262ce74a864836972188fca772ca48",
                        "title": "TxGIO StratMap Parcels (Latest)",
                        "type": "Feature Service",
                        "owner": "DETCOG.GIS",
                        "url": "https://feature.tnris.org/arcgis/rest/services/Parcels/stratmap_land_parcels_48_most_recent/MapServer/0",
                        "snippet": "Statewide land parcel boundaries collected by TxGIO.",
                        "tags": ["Parcel", "Property", "Boundary", "Land Parcel"],
                        "extent": [[-106.9276, 25.511789], [-93.353691, 36.815432]],
                        "modified": 1767628805000,
                        "scoreCompleteness": 100,
                        "access": "public",
                    }
                ],
            }

        if "Address Points" in query:
            return {
                "total": 1,
                "results": [
                    {
                        "id": "610d111483584999b40389b85a319ec2",
                        "title": "AddressPointsatCityLimits",
                        "type": "Feature Service",
                        "owner": "mburrell99",
                        "url": "https://services5.arcgis.com/L9cGEA18yPzG7Xak/arcgis/rest/services/AddressPointsatCityLimits/FeatureServer",
                        "snippet": "<p>Address Points dataset acquired by TxGIO for Travis County.</p>",
                        "tags": ["Address Points", "Travis County"],
                        "extent": [[-97.58336966876608, 30.326628401163493], [-97.45581065455393, 30.3911567381577]],
                        "modified": 1770043982000,
                        "scoreCompleteness": 81,
                        "access": "public",
                    }
                ],
            }

        return {
            "total": 1,
            "results": [
                {
                    "id": "austin-zoning",
                    "title": "Austin Zoning",
                    "type": "Feature Service",
                    "owner": "AustinGIS",
                    "url": "https://services.arcgis.com/example/arcgis/rest/services/Zoning/FeatureServer",
                    "snippet": "Municipal zoning polygons for Austin.",
                    "tags": ["Zoning", "Austin"],
                    "extent": [[-98.0, 30.0], [-97.5, 30.6]],
                    "modified": 1760000000000,
                    "scoreCompleteness": 90,
                    "access": "public",
                }
            ],
        }


def test_txgio_provider_is_queryable_catalog_search() -> None:
    assert TXGIO_GEOSPATIAL_CATALOG.queryable is True
    assert TXGIO_GEOSPATIAL_CATALOG.endpoints[0].label == "ArcGIS Online catalog search"
    assert str(TXGIO_GEOSPATIAL_CATALOG.endpoints[0].url) == ARCGIS_ONLINE_SEARCH_URL


@pytest.mark.anyio
async def test_txgio_query_returns_actual_catalog_matches_for_site_context() -> None:
    http_client = FakeTxgioHttpClient()

    response = await query_provider_data(
        provider=TXGIO_GEOSPATIAL_CATALOG,
        request=ProviderQueryRequest(params={"site_context": "1201 S Lamar Blvd, Austin, TX 78704"}, limit=3),
        http_client=http_client,
    )

    assert len(http_client.calls) == 3
    assert all(call[0] == ARCGIS_ONLINE_SEARCH_URL for call in http_client.calls)
    assert http_client.calls[1][1]["q"] == "TxGIO Address Points Travis County"
    assert http_client.calls[2][1]["q"] == "Austin Zoning Feature Service"
    assert response.data["status"] == "live_query"
    assert response.data["source"] == "arcgis_online_catalog_search"
    assert response.data["input"]["derived_area_terms"] == "Austin Travis County"
    assert response.data["match_count"] == 3
    assert response.data["matches"][0]["title"] == "TxGIO StratMap Parcels (Latest)"
    assert response.data["matches"][0]["service_url"].startswith("https://feature.tnris.org/")
    assert response.data["matches"][1]["title"] == "AddressPointsatCityLimits"
    assert response.data["matches"][1]["snippet"] == "Address Points dataset acquired by TxGIO for Travis County."
    assert response.data["matches"][2]["title"] == "Austin Zoning"
    assert response.request_params["queries"] == [
        "TxGIO StratMap Parcels Latest",
        "TxGIO Address Points Travis County",
        "Austin Zoning Feature Service",
    ]
