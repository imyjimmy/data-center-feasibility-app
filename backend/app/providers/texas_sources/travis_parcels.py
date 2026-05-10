import re
from typing import Any

import httpx
from pydantic import HttpUrl

from app.providers.client import ProviderHttpClient
from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderCapability,
    ProviderCoverage,
    ProviderEndpoint,
    ProviderKind,
    ProviderQueryRequest,
    ProviderQueryResponse,
)


TRAVIS_PARCEL_DILIGENCE_FIELDS = (
    "OBJECTID",
    "PROP_ID",
    "py_owner_name",
    "situs_address",
    "situs_num",
    "situs_street",
    "situs_zip",
    "tcad_acres",
    "GIS_acres",
    "market_value",
    "appraised_val",
    "assessed_val",
    "land_type_desc",
    "legal_desc",
    "geo_id",
    "deed_date",
    "hyperlink",
)

TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS = ",".join(TRAVIS_PARCEL_DILIGENCE_FIELDS)

AUSTIN_AREA_SEARCH_BBOX = "-98.5801,29.5443,-96.9063,30.9912"
TRAVIS_PARCEL_QUERY_URL = "https://taxmaps.traviscountytx.gov/arcgis/rest/services/Parcels/FeatureServer/0/query"
_ACREAGE_FILTER_RE = re.compile(r"\b(?:acres|ACRES|GIS_ACRES|GIS_acres|tcad_acres)\s*>=\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

_ADDRESS_STOPWORDS = {
    "AUSTIN",
    "COUNTY",
    "ROAD",
    "STREET",
    "TEXAS",
    "TX",
    "BLVD",
    "BOULEVARD",
    "AVE",
    "AVENUE",
    "DR",
    "DRIVE",
    "LN",
    "LANE",
    "RD",
    "ST",
    "S",
    "N",
    "E",
    "W",
    "SUITE",
    "UNIT",
}


def _sql_string(value: str) -> str:
    return value.replace("'", "''")


def _float_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_min_acres(where: str) -> float | None:
    match = _ACREAGE_FILTER_RE.search(where)
    return float(match.group(1)) if match else None


def _normalize_where(where: str) -> str:
    normalized = re.sub(r"\bGIS_ACRES\b", "GIS_acres", where, flags=re.IGNORECASE)
    normalized = re.sub(r"\bACRES\b", "tcad_acres", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bacres\b", "tcad_acres", normalized, flags=re.IGNORECASE)
    return normalized


def _build_query_params(request: ProviderQueryRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "f": "json",
        "where": _normalize_where(request.where),
        "outFields": request.out_fields,
        "resultRecordCount": request.limit,
        "returnGeometry": str(request.return_geometry).lower(),
        **request.params,
    }

    if request.bbox:
        params.update(
            {
                "geometry": request.bbox,
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )

    return params


def _feature_acres(feature: object) -> float | None:
    if not isinstance(feature, dict):
        return None
    attrs = feature.get("attributes")
    if not isinstance(attrs, dict):
        return None
    return _float_value(attrs.get("GIS_acres") or attrs.get("tcad_acres") or attrs.get("ACRES"))


def _filter_features_by_acres(data: dict[str, Any], min_acres: float, limit: int) -> dict[str, Any]:
    features = data.get("features")
    if not isinstance(features, list):
        return data

    filtered = [
        feature
        for feature in features
        if (acres := _feature_acres(feature)) is not None and acres >= min_acres
    ]
    filtered.sort(key=lambda feature: _feature_acres(feature) or 0, reverse=True)
    updated = dict(data)
    updated["features"] = filtered[:limit]
    updated["client_side_filter"] = {
        "field_candidates": ["GIS_acres", "tcad_acres"],
        "min_acres": min_acres,
        "input_feature_count": len(features),
        "returned_feature_count": len(updated["features"]),
    }
    return updated


def _arcgis_error(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    return error if isinstance(error, dict) else None


def build_travis_parcel_site_request(site_context: str, limit: int = 5) -> ProviderQueryRequest | None:
    """Build a Travis parcel lookup from an address-like site context.

    Travis County's parcel layer stores the street number separately as `situs_num`.
    Matching it exactly avoids false positives such as 1201 matching 12014.
    """

    normalized = site_context.upper()
    street_number = re.search(r"\b\d{2,6}\b", normalized)
    if street_number and re.search(rf"\bTX\s+{street_number.group(0)}\b", normalized):
        street_number = None
    if street_number and re.search(rf"\b{street_number.group(0)}\s*(MW|MEGAWATT|MEGAWATTS|MI|MILE|MILES)\b", normalized):
        street_number = None

    street_tokens = [
        token
        for token in re.findall(r"[A-Z]{2,}", normalized)
        if token not in _ADDRESS_STOPWORDS and not token.isdigit()
    ]

    if not street_number:
        return None

    clauses: list[str] = []
    clauses.append(f"situs_num = '{_sql_string(street_number.group(0))}'")

    for token in street_tokens[:2]:
        clauses.append(f"situs_address LIKE '%{_sql_string(token)}%'")

    if not clauses:
        return None

    return ProviderQueryRequest(
        where=" AND ".join(clauses),
        out_fields=TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS,
        limit=limit,
        return_geometry=True,
        params={"outSR": 4326},
    )


def build_travis_parcel_area_search_request(
    location_context: str,
    min_acres: float = 25,
    limit: int = 25,
) -> ProviderQueryRequest | None:
    """Build a broad Austin-area parcel search from a location-oriented prompt.

    The current configured parcel source is Travis County, so an "Austin-area" search
    can only be evidence-backed within that county until broader TxGIO parcel querying
    is added.
    """

    normalized = location_context.upper()
    if not any(term in normalized for term in ("AUSTIN", "TRAVIS")):
        return None

    return ProviderQueryRequest(
        where=f"GIS_acres >= {min_acres:g}",
        out_fields=TRAVIS_PARCEL_DILIGENCE_OUT_FIELDS,
        limit=limit,
        return_geometry=True,
        bbox=AUSTIN_AREA_SEARCH_BBOX,
        params={
            "inSR": 4326,
            "orderByFields": "GIS_acres DESC",
            "outSR": 4326,
        },
    )


async def query_travis_parcel_data(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    params = _build_query_params(request)
    min_acres = _extract_min_acres(request.where)

    data: Any
    fallback_reason: str | None = None
    try:
        data = await http_client.get_json(TRAVIS_PARCEL_QUERY_URL, params=params)
        if _arcgis_error(data) and min_acres is not None:
            fallback_reason = "arcgis_error_payload"
    except httpx.HTTPStatusError:
        if min_acres is None:
            raise
        data = {}
        fallback_reason = "http_error"

    if fallback_reason is not None and min_acres is not None:
        fallback_request = request.model_copy(
            update={
                "where": "1=1",
                "limit": max(request.limit * 4, 100),
                "params": {
                    **request.params,
                    "orderByFields": "GIS_acres DESC",
                },
            }
        )
        fallback_params = _build_query_params(fallback_request)
        data = await http_client.get_json(TRAVIS_PARCEL_QUERY_URL, params=fallback_params)

        if _arcgis_error(data):
            no_sort_request = fallback_request.model_copy(
                update={
                    "params": {
                        key: value
                        for key, value in fallback_request.params.items()
                        if key != "orderByFields"
                    }
                }
            )
            fallback_params = _build_query_params(no_sort_request)
            data = await http_client.get_json(TRAVIS_PARCEL_QUERY_URL, params=fallback_params)

        if isinstance(data, dict):
            data = _filter_features_by_acres(data, min_acres=min_acres, limit=request.limit)
            data["query_fallback"] = {
                "reason": "acreage_filter_rejected_by_provider",
                "original_where": request.where,
                "fallback_where": "1=1",
                "trigger": fallback_reason,
            }
        params = fallback_params

    if isinstance(data, dict) and min_acres is not None and "client_side_filter" not in data:
        data = _filter_features_by_acres(data, min_acres=min_acres, limit=request.limit)

    if (
        isinstance(data, dict)
        and request.bbox
        and min_acres is not None
        and not data.get("features")
    ):
        countywide_request = request.model_copy(update={"bbox": None, "limit": max(request.limit * 4, 100)})
        countywide_params = _build_query_params(countywide_request)
        countywide_data = await http_client.get_json(TRAVIS_PARCEL_QUERY_URL, params=countywide_params)
        if _arcgis_error(countywide_data):
            no_sort_request = countywide_request.model_copy(
                update={
                    "params": {
                        key: value
                        for key, value in countywide_request.params.items()
                        if key != "orderByFields"
                    }
                }
            )
            countywide_params = _build_query_params(no_sort_request)
            countywide_data = await http_client.get_json(TRAVIS_PARCEL_QUERY_URL, params=countywide_params)
        if isinstance(countywide_data, dict):
            countywide_data = _filter_features_by_acres(
                countywide_data,
                min_acres=min_acres,
                limit=request.limit,
            )
            countywide_data["query_fallback"] = {
                "reason": "bbox_query_returned_no_acreage_candidates",
                "original_where": request.where,
                "fallback_scope": "travis_county_no_bbox",
            }
            data = countywide_data
            params = countywide_params

    if not isinstance(data, dict):
        msg = f"Travis parcel provider returned {type(data).__name__}, expected object"
        raise ValueError(msg)

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(TRAVIS_PARCEL_QUERY_URL),
        request_params=params,
        data=data,
    )


TRAVIS_COUNTY_PARCELS = DataProviderDefinition(
    id="travis_county_parcels",
    name="Travis County Parcels",
    concern=Concern.ZONING,
    kind=ProviderKind.ARCGIS_FEATURE_SERVICE,
    capabilities=[ProviderCapability.QUERY_FEATURES, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(counties=["Travis"]),
    description="Travis County parcel FeatureServer for parcel geometry and appraisal-map attributes.",
    owner="Travis County",
    source_homepage="https://taxmaps.traviscountytx.gov/arcgis/rest/services/Parcels/FeatureServer",
    endpoints=[
        ProviderEndpoint(
            label="Parcel layer query",
            url=TRAVIS_PARCEL_QUERY_URL,
            notes="Queryable DBO.Parcels layer.",
        )
    ],
    queryable=True,
    update_frequency="County-controlled operational GIS dataset.",
    limitations=[
        "Parcel data does not by itself prove zoning entitlement or data center permissibility.",
        "Zoning overlays may need city/ETJ-specific layers in addition to parcel geometry.",
        "Address matching uses Travis County situs fields and still needs parcel ID confirmation for legal diligence.",
    ],
    tags=["parcels", "travis-county", "zoning", "arcgis"],
)
