from typing import Any

import httpx
import pytest

from app.providers.models import ProviderQueryRequest
from app.providers.service import query_provider_data
from app.providers.texas_sources.travis_parcels import (
    AUSTIN_AREA_SEARCH_BBOX,
    TRAVIS_COUNTY_PARCELS,
    TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS,
    build_travis_parcel_area_search_request,
    build_travis_parcel_site_request,
)


class FakeTravisParcelHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((url, params))
        return {
            "objectIdFieldName": "OBJECTID",
            "geometryType": "esriGeometryPolygon",
            "spatialReference": {"wkid": 4326, "latestWkid": 4326},
            "fields": [
                {"name": "OBJECTID", "alias": "OBJECTID", "type": "esriFieldTypeOID"},
                {"name": "PROP_ID", "alias": "Property ID", "type": "esriFieldTypeInteger"},
                {"name": "py_owner_name", "alias": "Physical Owner Name", "type": "esriFieldTypeString"},
                {"name": "situs_address", "alias": "Situs Address", "type": "esriFieldTypeString"},
                {"name": "tcad_acres", "alias": "TCAD Acres", "type": "esriFieldTypeDouble"},
                {"name": "GIS_acres", "alias": "GIS Acres", "type": "esriFieldTypeDouble"},
                {"name": "market_value", "alias": "Market Value", "type": "esriFieldTypeInteger"},
                {"name": "legal_desc", "alias": "Legal Description", "type": "esriFieldTypeString"},
            ],
            "features": [
                {
                    "attributes": {
                        "OBJECTID": 369992,
                        "PROP_ID": 100008,
                        "py_owner_name": "DJB INVESTMENT PROPERTY LLC",
                        "situs_address": "S 1201 LAMAR BLVD   TX 78704",
                        "situs_num": "1201",
                        "situs_zip": "78704",
                        "tcad_acres": 0.5399,
                        "GIS_acres": 0.53976333,
                        "market_value": 4233880,
                        "legal_desc": "LOT 1-4 TEMPLER LOTS",
                    },
                    "geometry": {
                        "rings": [
                            [
                                [-97.76230963350642, 30.254480025479307],
                                [-97.76223625229957, 30.25460185626802],
                                [-97.76216287303333, 30.25472368525375],
                                [-97.76230963350642, 30.254480025479307],
                            ]
                        ]
                    },
                }
            ],
        }


class FakeFallbackTravisParcelHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((url, params))
        if params and params.get("where") == "GIS_acres >= 25":
            request = httpx.Request("GET", url, params=params)
            response = httpx.Response(status_code=400, request=request)
            raise httpx.HTTPStatusError("Unable to complete operation", request=request, response=response)

        return {
            "features": [
                {
                    "attributes": {
                        "PROP_ID": 1,
                        "situs_address": "LARGE PARCEL",
                        "tcad_acres": 42,
                    },
                    "geometry": {"rings": [[[-97.7, 30.2], [-97.69, 30.2], [-97.7, 30.2]]]},
                },
                {
                    "attributes": {
                        "PROP_ID": 2,
                        "situs_address": "SMALL PARCEL",
                        "tcad_acres": 5,
                    },
                    "geometry": {"rings": [[[-97.8, 30.3], [-97.79, 30.3], [-97.8, 30.3]]]},
                },
            ]
        }


class FakeArcgisErrorPayloadTravisParcelHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((url, params))
        if params and params.get("where") == "GIS_acres >= 25":
            return {"error": {"code": 400, "message": "Unable to complete operation"}}

        return {
            "features": [
                {
                    "attributes": {
                        "PROP_ID": 3,
                        "situs_address": "ERROR FALLBACK LARGE PARCEL",
                        "tcad_acres": 55,
                    },
                    "geometry": {"rings": [[[-97.7, 30.2], [-97.69, 30.2], [-97.7, 30.2]]]},
                }
            ]
        }


class FakeArcgisErrorThenNoSortTravisParcelHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((url, params))
        if params and params.get("where") == "GIS_acres >= 25":
            return {"error": {"code": 400, "message": "Unable to complete operation"}}
        if params and params.get("orderByFields"):
            return {"error": {"code": 400, "message": "Unable to complete operation"}}

        return {
            "features": [
                {
                    "attributes": {
                        "PROP_ID": 4,
                        "situs_address": "NO SORT FALLBACK LARGE PARCEL",
                        "tcad_acres": 35,
                    },
                    "geometry": {"rings": [[[-97.7, 30.2], [-97.69, 30.2], [-97.7, 30.2]]]},
                }
            ]
        }


class FakeEmptyBboxTravisParcelHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((url, params))
        if params and params.get("geometry"):
            return {"features": []}

        return {
            "features": [
                {
                    "attributes": {
                        "PROP_ID": 5,
                        "situs_address": "COUNTYWIDE LARGE PARCEL",
                        "tcad_acres": 75,
                    },
                    "geometry": {"rings": [[[-97.7, 30.2], [-97.69, 30.2], [-97.7, 30.2]]]},
                }
            ]
        }


def test_build_travis_parcel_site_request_uses_exact_situs_number() -> None:
    request = build_travis_parcel_site_request("1201 S Lamar Blvd, Austin, TX 78704", limit=3)

    assert request is not None
    assert request.where == "situs_num = '1201' AND situs_address LIKE '%LAMAR%'"
    assert request.out_fields == TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS
    assert "tcad_acres" in request.out_fields
    assert "GIS_acres" in request.out_fields
    assert "ACRES" not in request.out_fields
    assert request.limit == 3
    assert request.return_geometry is True
    assert request.params == {"outSR": 4326}


def test_build_travis_parcel_site_request_returns_none_without_address_tokens() -> None:
    assert build_travis_parcel_site_request("Austin, TX") is None
    assert build_travis_parcel_site_request("Austin, TX 78704") is None
    assert build_travis_parcel_site_request("Austin-area parcels for 25 MW edge data center") is None


def test_build_travis_parcel_area_search_request_for_austin_prompt() -> None:
    request = build_travis_parcel_area_search_request(
        "Which Austin-area parcels are plausible for a 25 MW edge data center?",
        min_acres=25,
        limit=12,
    )

    assert request is not None
    assert request.where == "GIS_acres >= 25"
    assert request.bbox == AUSTIN_AREA_SEARCH_BBOX
    assert request.limit == 12
    assert request.return_geometry is True
    assert request.params["orderByFields"] == "GIS_acres DESC"
    assert request.params["inSR"] == 4326
    assert request.params["outSR"] == 4326


@pytest.mark.anyio
async def test_travis_parcel_query_normalizes_acres_alias_filter() -> None:
    http_client = FakeTravisParcelHttpClient()
    request = ProviderQueryRequest(
        where="acres >= 25",
        out_fields=TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS,
        bbox=AUSTIN_AREA_SEARCH_BBOX,
    )

    await query_provider_data(
        provider=TRAVIS_COUNTY_PARCELS,
        request=request,
        http_client=http_client,
    )

    _, params = http_client.calls[0]
    assert params is not None
    assert params["where"] == "GIS_acres >= 25"


@pytest.mark.anyio
async def test_travis_parcel_query_falls_back_to_client_side_acreage_filter() -> None:
    http_client = FakeFallbackTravisParcelHttpClient()
    request = build_travis_parcel_area_search_request(
        "Which Austin-area parcels are plausible for a 25 MW edge data center?",
        min_acres=25,
        limit=10,
    )
    assert isinstance(request, ProviderQueryRequest)

    response = await query_provider_data(
        provider=TRAVIS_COUNTY_PARCELS,
        request=request,
        http_client=http_client,
    )

    assert len(http_client.calls) == 2
    assert http_client.calls[1][1]["where"] == "1=1"
    assert response.data["query_fallback"]["reason"] == "acreage_filter_rejected_by_provider"
    assert response.data["client_side_filter"]["returned_feature_count"] == 1
    assert response.data["features"][0]["attributes"]["PROP_ID"] == 1


@pytest.mark.anyio
async def test_travis_parcel_query_falls_back_on_arcgis_error_payload() -> None:
    http_client = FakeArcgisErrorPayloadTravisParcelHttpClient()
    request = build_travis_parcel_area_search_request(
        "Which Austin-area parcels are plausible for a 25 MW edge data center?",
        min_acres=25,
        limit=10,
    )
    assert isinstance(request, ProviderQueryRequest)

    response = await query_provider_data(
        provider=TRAVIS_COUNTY_PARCELS,
        request=request,
        http_client=http_client,
    )

    assert len(http_client.calls) == 2
    assert response.data["query_fallback"]["trigger"] == "arcgis_error_payload"
    assert response.data["features"][0]["attributes"]["PROP_ID"] == 3


@pytest.mark.anyio
async def test_travis_parcel_query_retries_fallback_without_order_by() -> None:
    http_client = FakeArcgisErrorThenNoSortTravisParcelHttpClient()
    request = build_travis_parcel_area_search_request(
        "Which Austin-area parcels are plausible for a 25 MW edge data center?",
        min_acres=25,
        limit=10,
    )
    assert isinstance(request, ProviderQueryRequest)

    response = await query_provider_data(
        provider=TRAVIS_COUNTY_PARCELS,
        request=request,
        http_client=http_client,
    )

    assert len(http_client.calls) == 3
    assert "orderByFields" not in http_client.calls[-1][1]
    assert response.data["features"][0]["attributes"]["PROP_ID"] == 4


@pytest.mark.anyio
async def test_travis_parcel_query_retries_without_bbox_when_bbox_has_no_candidates() -> None:
    http_client = FakeEmptyBboxTravisParcelHttpClient()
    request = build_travis_parcel_area_search_request(
        "Which Austin-area parcels are plausible for a 25 MW edge data center?",
        min_acres=25,
        limit=10,
    )
    assert isinstance(request, ProviderQueryRequest)

    response = await query_provider_data(
        provider=TRAVIS_COUNTY_PARCELS,
        request=request,
        http_client=http_client,
    )

    assert len(http_client.calls) == 2
    assert "geometry" in http_client.calls[0][1]
    assert "geometry" not in http_client.calls[1][1]
    assert response.data["query_fallback"]["fallback_scope"] == "travis_county_no_bbox"
    assert response.data["features"][0]["attributes"]["PROP_ID"] == 5


def test_build_travis_parcel_area_search_request_ignores_unknown_location() -> None:
    assert build_travis_parcel_area_search_request("Find parcels near Dallas") is None


@pytest.mark.anyio
async def test_travis_parcel_query_returns_realistic_attributes_and_geometry() -> None:
    http_client = FakeTravisParcelHttpClient()
    request = build_travis_parcel_site_request("1201 S Lamar Blvd, Austin, TX 78704", limit=1)
    assert isinstance(request, ProviderQueryRequest)

    response = await query_provider_data(
        provider=TRAVIS_COUNTY_PARCELS,
        request=request,
        http_client=http_client,
    )

    assert str(response.request_url).startswith(
        "https://taxmaps.traviscountytx.gov/arcgis/rest/services/Parcels/FeatureServer/0/query"
    )
    assert http_client.calls
    _, params = http_client.calls[0]
    assert params is not None
    assert params["where"] == "situs_num = '1201' AND situs_address LIKE '%LAMAR%'"
    assert params["outFields"] == TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS
    assert params["returnGeometry"] == "true"
    assert params["outSR"] == 4326

    feature = response.data["features"][0]
    assert feature["attributes"]["PROP_ID"] == 100008
    assert feature["attributes"]["situs_address"] == "S 1201 LAMAR BLVD   TX 78704"
    assert feature["attributes"]["tcad_acres"] == 0.5399
    assert feature["attributes"]["GIS_acres"] == 0.53976333
    assert feature["geometry"]["rings"][0][0] == [-97.76230963350642, 30.254480025479307]
