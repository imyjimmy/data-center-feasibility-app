from typing import Any

import pytest

from app.providers.models import ProviderQueryRequest
from app.providers.service import query_provider_data
from app.providers.texas_sources.travis_parcels import (
    TRAVIS_COUNTY_PARCELS,
    TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS,
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
