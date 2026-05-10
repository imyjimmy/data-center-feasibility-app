import os
from statistics import mean
from time import time
from typing import Any

import httpx

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

ERCOT_B2C_TOKEN_URL = (
    "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
    "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
)
ERCOT_B2C_CLIENT_ID = "fec253ea-0d06-4272-a5e6-b478baeecd70"
ERCOT_B2C_SCOPE = f"openid {ERCOT_B2C_CLIENT_ID} offline_access"
_TOKEN_CACHE: dict[str, Any] = {}


ERCOT_MARKET_DATA_TRANSPARENCY = DataProviderDefinition(
    id="ercot_market_data_transparency",
    name="ERCOT Market Data Transparency",
    concern=Concern.POWER_STRESS,
    kind=ProviderKind.REST_API,
    capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "ERCOT public market reports and API explorer for grid and market conditions. "
        "Use for power stress proxies such as real-time pricing, load, congestion, "
        "and market notices once report-specific endpoints are selected."
    ),
    owner="Electric Reliability Council of Texas",
    source_homepage="https://www.ercot.com/services/mdt/data-portal",
    endpoints=[
        ProviderEndpoint(
            label="ERCOT Grid Conditions dashboard JSON",
            url="https://www.ercot.com/api/1/services/read/dashboards/daily-prc.json",
            notes="Public dashboard JSON with current grid condition and physical responsive capability.",
        ),
        ProviderEndpoint(
            label="ERCOT Today's Outlook dashboard JSON",
            url="https://www.ercot.com/api/1/services/read/dashboards/todays-outlook.json",
            notes="Public dashboard JSON with current/forecast demand and capacity points.",
        ),
        ProviderEndpoint(
            label="ERCOT API Explorer",
            url="https://apiexplorer.ercot.com/",
            notes="Registered API access for deeper report-specific endpoints.",
        ),
        ProviderEndpoint(
            label="ERCOT Public API reports",
            url="https://api.ercot.com/api/public-reports",
            notes="Requires Ocp-Apim-Subscription-Key and Authorization bearer token headers.",
        ),
        ProviderEndpoint(
            label="Real-Time Settlement Point Prices",
            url="https://api.ercot.com/api/public-reports/np6-905-cd/spp_node_zone_hub",
            notes="15-minute settlement point prices at resource nodes, hubs, and load zones.",
        ),
        ProviderEndpoint(
            label="Real-Time LMPs by Resource Nodes, Load Zones, and Hubs",
            url="https://api.ercot.com/api/public-reports/np6-788-cd/lmp_node_zone_hub",
            notes="SCED locational marginal prices by ERCOT settlement point.",
        ),
        ProviderEndpoint(
            label="Real-Time LMPs by Electrical Bus",
            url="https://api.ercot.com/api/public-reports/np6-787-cd/lmp_electrical_bus",
            notes="SCED locational marginal prices by electrical bus.",
        ),
        ProviderEndpoint(
            label="SCED Shadow Prices and Binding Transmission Constraints",
            url="https://api.ercot.com/api/public-reports/np6-86-cd/shdw_prices_bnd_trns_const",
            notes="Binding/violated transmission constraints, limiting facilities, and shadow prices.",
        ),
        ProviderEndpoint(
            label="Day-Ahead Settlement Point Prices",
            url="https://api.ercot.com/api/public-reports/np4-190-cd/dam_stlmnt_pnt_prices",
            notes="Day-ahead settlement point prices at resource nodes, hubs, and load zones.",
        ),
        ProviderEndpoint(
            label="Day-Ahead Shadow Prices",
            url="https://api.ercot.com/api/public-reports/np4-191-cd/dam_shadow_prices",
            notes="Day-ahead market shadow prices for transmission constraints.",
        ),
    ],
    queryable=True,
    authentication=(
        "none for configured public dashboard JSON; ERCOT Public API requests require "
        "Ocp-Apim-Subscription-Key and a bearer ID token. The provider can use ERCOT_ID_TOKEN "
        "directly or obtain one from ERCOT_USERNAME/ERCOT_PASSWORD."
    ),
    update_frequency="ERCOT dashboard JSON updates throughout the operating day; Data Access Portal report cadence varies.",
    limitations=[
        "Configured dashboard endpoints provide system-level ERCOT context, not site-level interconnection capacity.",
        "Substation, transmission, feeder, and TSP-specific capacity still require utility/interconnection diligence.",
        "Deeper ERCOT Data Access Portal/API Explorer reports may require registration and subscription keys.",
    ],
    tags=["ercot", "power", "grid-conditions", "market", "texas"],
)


def _last_dict(items: Any) -> dict[str, Any]:
    if isinstance(items, list):
        for item in reversed(items):
            if isinstance(item, dict):
                return item
    return {}


async def _fetch_ercot_id_token() -> tuple[str | None, str | None]:
    username = os.getenv("ERCOT_USERNAME")
    password = os.getenv("ERCOT_PASSWORD")
    if not username or not password:
        return None, None

    cached_token = _TOKEN_CACHE.get("id_token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0)
    if isinstance(cached_token, str) and time() < expires_at:
        return cached_token, None

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                ERCOT_B2C_TOKEN_URL,
                data={
                    "username": username,
                    "password": password,
                    "grant_type": "password",
                    "scope": ERCOT_B2C_SCOPE,
                    "client_id": ERCOT_B2C_CLIENT_ID,
                    "response_type": "id_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return None, f"Unable to obtain ERCOT ID token: {type(exc).__name__}"

    id_token = payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        return None, "ERCOT token response did not include id_token."

    expires_in = payload.get("expires_in")
    try:
        ttl_seconds = int(expires_in)
    except (TypeError, ValueError):
        ttl_seconds = 3600

    _TOKEN_CACHE["id_token"] = id_token
    _TOKEN_CACHE["expires_at"] = time() + max(ttl_seconds - 60, 60)
    return id_token, None


async def _ercot_public_api_headers() -> tuple[dict[str, str], str | None]:
    headers: dict[str, str] = {}
    subscription_key = os.getenv("ERCOT_SUBSCRIPTION_KEY") or os.getenv("ERCOT_PRIMARY_KEY")
    token_error: str | None = None
    id_token = os.getenv("ERCOT_ID_TOKEN")

    if not id_token:
        id_token, token_error = await _fetch_ercot_id_token()

    if subscription_key:
        headers["Ocp-Apim-Subscription-Key"] = subscription_key
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    return headers, token_error


def _public_api_config_status(headers: dict[str, str], token_error: str | None = None) -> str:
    if "Ocp-Apim-Subscription-Key" not in headers:
        return "missing_subscription_key"
    if "Authorization" not in headers:
        if token_error:
            return "id_token_error"
        return "missing_id_token"
    return "configured"


def _dashboard_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Referer": "https://www.ercot.com/gridmktinfo/dashboards",
        "User-Agent": "Mozilla/5.0 compatible; data-center-feasibility-app/0.1",
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def _public_report_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        fields = payload.get("fields")
        data_rows = payload.get("data")
        if isinstance(fields, list) and isinstance(data_rows, list):
            field_names = [
                field.get("name")
                for field in fields
                if isinstance(field, dict) and isinstance(field.get("name"), str)
            ]
            records: list[dict[str, Any]] = []
            for row in data_rows:
                if isinstance(row, list):
                    records.append(
                        {
                            field_name: row[index] if index < len(row) else None
                            for index, field_name in enumerate(field_names)
                        }
                    )
                elif isinstance(row, dict):
                    records.append(row)
            return records

        embedded = payload.get("_embedded")
        if isinstance(embedded, dict):
            for value in embedded.values():
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        for key in ("data", "records", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _sample_records(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return records[: max(limit, 0)]


def _numeric_values(records: list[dict[str, Any]], field_terms: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for record in records:
        for key, value in record.items():
            normalized = key.lower()
            if not any(term in normalized for term in field_terms):
                continue
            if isinstance(value, (int, float)):
                values.append(float(value))
            elif isinstance(value, str):
                try:
                    values.append(float(value.replace(",", "")))
                except ValueError:
                    pass
    return values


def _numeric_summary(records: list[dict[str, Any]], field_terms: tuple[str, ...]) -> dict[str, float] | None:
    values = _numeric_values(records, field_terms)
    if not values:
        return None
    return {
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "average": round(mean(values), 2),
    }


def _record_matches_terms(record: dict[str, Any], terms: list[str]) -> bool:
    if not terms:
        return True
    haystack = " ".join(str(value).lower() for value in record.values())
    return any(term.lower() in haystack for term in terms)


def _filter_records_by_terms(records: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    return [record for record in records if _record_matches_terms(record, terms)]


def _location_mapping(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_name": params.get("site_name"),
        "latitude": params.get("latitude"),
        "longitude": params.get("longitude"),
        "county": params.get("county"),
        "load_zone": _first_present(params.get("ercot_load_zone"), params.get("load_zone")),
        "settlement_points": _as_str_list(
            _first_present(params.get("nearby_settlement_points"), params.get("settlement_points"), params.get("settlement_point"))
        ),
        "electrical_buses": _as_str_list(_first_present(params.get("electrical_buses"), params.get("electrical_bus"))),
        "nearby_grid_elements": _as_str_list(
            _first_present(params.get("nearby_grid_elements"), params.get("nearest_substations"), params.get("nearest_transmission_lines"))
        ),
        "source_confidence": params.get("source_confidence", "unknown"),
    }


def _has_location_identifiers(mapping: dict[str, Any]) -> bool:
    return bool(
        mapping.get("load_zone")
        or mapping.get("settlement_points")
        or mapping.get("electrical_buses")
        or mapping.get("nearby_grid_elements")
    )


def _report_query_params(
    report_key: str,
    mapping: dict[str, Any],
    params: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    query: dict[str, Any] = {"size": limit}
    date_from = params.get("delivery_date_from") or params.get("date_from")
    date_to = params.get("delivery_date_to") or params.get("date_to")
    sced_from = params.get("sced_timestamp_from") or params.get("timestamp_from")
    sced_to = params.get("sced_timestamp_to") or params.get("timestamp_to")

    if report_key in {"rt_settlement_point_prices", "dam_settlement_point_prices"}:
        if date_from:
            query["deliveryDateFrom"] = date_from
        if date_to:
            query["deliveryDateTo"] = date_to
        settlement_points = _as_list(mapping.get("settlement_points"))
        if settlement_points:
            query["settlementPoint"] = settlement_points[0]
        elif mapping.get("load_zone"):
            query["settlementPoint"] = mapping["load_zone"]

    if report_key in {"rt_lmp_node_zone_hub", "electrical_bus_lmp", "sced_shadow_prices"}:
        if sced_from:
            query["SCEDTimestampFrom"] = sced_from
        if sced_to:
            query["SCEDTimestampTo"] = sced_to

    if report_key == "rt_lmp_node_zone_hub":
        settlement_points = _as_list(mapping.get("settlement_points"))
        if settlement_points:
            query["settlementPoint"] = settlement_points[0]
        elif mapping.get("load_zone"):
            query["settlementPoint"] = mapping["load_zone"]

    if report_key == "electrical_bus_lmp":
        buses = _as_list(mapping.get("electrical_buses"))
        if buses:
            query["ElectricalBus"] = buses[0]

    return query


def _summarize_report(
    label: str,
    records: list[dict[str, Any]],
    location_terms: list[str],
    sample_limit: int,
) -> dict[str, Any]:
    matched_records = _filter_records_by_terms(records, location_terms)
    records_for_summary = matched_records or records
    return {
        "label": label,
        "record_count": len(records),
        "location_match_count": len(matched_records),
        "sample_fields": list(records[0].keys()) if records else [],
        "price_summary": _numeric_summary(records_for_summary, ("price", "lmp")),
        "shadow_price_summary": _numeric_summary(records_for_summary, ("shadow",)),
        "sample_records": _sample_records(records_for_summary, sample_limit),
    }


def _build_location_power_report(
    mapping: dict[str, Any],
    reports: dict[str, Any],
    dashboard_context: dict[str, Any],
    auth_status: str,
) -> dict[str, Any]:
    has_location = _has_location_identifiers(mapping)
    report_values = [report for report in reports.values() if isinstance(report, dict)]
    successful_reports = [report for report in report_values if report.get("status") == "live_query"]
    matched_reports = [
        report
        for report in successful_reports
        if int(report.get("summary", {}).get("location_match_count") or 0) > 0
    ]
    failed_reports = [report for report in report_values if report.get("status") == "error"]

    if auth_status != "configured":
        risk_level = "unknown"
        summary = (
            "ERCOT location-specific public reports could not be queried because authenticated "
            f"Public API access is {auth_status}."
        )
    elif not has_location:
        risk_level = "unknown"
        summary = (
            "ERCOT authentication is configured, but the request did not include load-zone, "
            "settlement-point, electrical-bus, or nearby grid-element identifiers."
        )
    elif matched_reports:
        risk_level = "caution"
        summary = (
            "ERCOT returned location-matched market or constraint evidence. Review the returned "
            "prices, LMPs, and shadow-price records before making a siting decision."
        )
    elif successful_reports:
        risk_level = "caution"
        summary = (
            "ERCOT returned location-relevant report data, but the sample did not clearly match the "
            "provided site identifiers. The site needs stronger electrical mapping."
        )
    elif failed_reports:
        risk_level = "unknown"
        summary = "ERCOT location-specific report queries failed; use the per-report errors to fix the request."
    else:
        risk_level = "unknown"
        summary = "ERCOT did not return enough location-specific data for a site-selection conclusion."

    observations: list[str] = []
    if mapping.get("load_zone"):
        observations.append(f"Load zone provided: {mapping['load_zone']}.")
    if mapping.get("settlement_points"):
        observations.append(f"Settlement point candidates: {', '.join(mapping['settlement_points'])}.")
    if mapping.get("electrical_buses"):
        observations.append(f"Electrical bus candidates: {', '.join(mapping['electrical_buses'])}.")
    if mapping.get("nearby_grid_elements"):
        observations.append(f"Nearby grid elements: {', '.join(mapping['nearby_grid_elements'])}.")
    if dashboard_context.get("grid_condition"):
        condition = dashboard_context["grid_condition"]
        title = _first_present(condition.get("title"), condition.get("state"))
        if title:
            observations.append(f"Statewide ERCOT dashboard context: {title}.")

    return {
        "title": "ERCOT Location Power Report",
        "site_power_risk_level": risk_level,
        "summary": summary,
        "location_mapping": mapping,
        "key_observations": observations,
        "site_selection_interpretation": (
            "Use ERCOT market and constraint records as evidence of local grid stress, not as proof of "
            "available interconnection capacity. A favorable siting conclusion still requires utility, "
            "TSP, substation, and interconnection diligence."
        ),
        "recommended_next_action": (
            "Map the parcel to confirmed ERCOT load-zone, settlement-point, electrical-bus, substation, "
            "and transmission-line identifiers; then re-query settlement prices, LMPs, and binding constraints."
        ),
    }


async def _get_dashboard_json(
    http_client: ProviderHttpClient,
    endpoint: ProviderEndpoint,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        return await http_client.get_json(str(endpoint.url), headers=_dashboard_headers()), None
    except httpx.HTTPStatusError as exc:
        return None, {
            "endpoint": endpoint.model_dump(mode="json"),
            "status_code": exc.response.status_code,
            "reason": exc.response.reason_phrase,
        }
    except httpx.HTTPError as exc:
        return None, {
            "endpoint": endpoint.model_dump(mode="json"),
            "error_type": type(exc).__name__,
            "reason": str(exc) or "ERCOT dashboard request failed.",
        }


async def _dashboard_context(
    provider: DataProviderDefinition,
    http_client: ProviderHttpClient,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prc_endpoint = provider.endpoints[0]
    outlook_endpoint = provider.endpoints[1]
    prc_data, prc_error = await _get_dashboard_json(http_client, prc_endpoint)
    outlook_data, outlook_error = await _get_dashboard_json(http_client, outlook_endpoint)
    dashboard_errors = [error for error in (prc_error, outlook_error) if error]
    prc_data = prc_data or {}
    outlook_data = outlook_data or {}

    return (
        {
            "grid_condition": prc_data.get("current_condition"),
            "grid_condition_last_updated": prc_data.get("lastUpdated"),
            "latest_prc": _last_dict(prc_data.get("data")),
            "outlook_last_updated": outlook_data.get("lastUpdated"),
            "latest_outlook": _last_dict(outlook_data.get("data")),
            "source_endpoints": [
                prc_endpoint.model_dump(mode="json"),
                outlook_endpoint.model_dump(mode="json"),
            ],
        },
        dashboard_errors,
    )


async def _query_public_report(
    http_client: ProviderHttpClient,
    endpoint: ProviderEndpoint,
    headers: dict[str, str],
    params: dict[str, Any],
) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        return await http_client.get_json(str(endpoint.url), params=params, headers=headers), None
    except httpx.HTTPStatusError as exc:
        return None, {
            "endpoint": endpoint.model_dump(mode="json"),
            "status_code": exc.response.status_code,
            "reason": exc.response.reason_phrase,
            "message": exc.response.text[:500],
        }
    except httpx.HTTPError as exc:
        return None, {
            "endpoint": endpoint.model_dump(mode="json"),
            "error_type": type(exc).__name__,
            "reason": str(exc) or "ERCOT public report request failed.",
            "message": (
                "ERCOT did not return this report before the provider timeout. "
                "Other ERCOT reports may still be usable."
            ),
        }


async def query_ercot_location_power_data(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
    headers: dict[str, str],
    public_api_config_status: str,
    public_api_token_error: str | None,
) -> ProviderQueryResponse:
    params = request.params
    mapping = _location_mapping(params)
    dashboard_data, dashboard_errors = await _dashboard_context(provider, http_client)
    sample_limit = int(params.get("sample_limit") or min(request.limit, 10))
    requested_reports = set(_as_str_list(params.get("reports")))
    report_specs = {
        "rt_settlement_point_prices": provider.endpoints[4],
        "rt_lmp_node_zone_hub": provider.endpoints[5],
        "electrical_bus_lmp": provider.endpoints[6],
        "sced_shadow_prices": provider.endpoints[7],
        "dam_settlement_point_prices": provider.endpoints[8],
        "dam_shadow_prices": provider.endpoints[9],
    }
    default_reports = {
        "rt_settlement_point_prices",
        "rt_lmp_node_zone_hub",
        "electrical_bus_lmp",
        "sced_shadow_prices",
    }
    selected_report_keys = requested_reports or default_reports

    reports: dict[str, Any] = {}
    location_terms = [
        str(term)
        for term in [
            mapping.get("load_zone"),
            *_as_list(mapping.get("settlement_points")),
            *_as_list(mapping.get("electrical_buses")),
            *_as_list(mapping.get("nearby_grid_elements")),
        ]
        if term
    ]

    if public_api_config_status == "configured":
        for report_key in selected_report_keys:
            endpoint = report_specs.get(report_key)
            if not endpoint:
                reports[report_key] = {
                    "status": "unsupported_report",
                    "message": f"Unknown ERCOT location report key: {report_key}",
                }
                continue
            report_params = _report_query_params(report_key, mapping, params, request.limit)
            payload, error = await _query_public_report(http_client, endpoint, headers, report_params)
            if error:
                reports[report_key] = {
                    "status": "error",
                    "endpoint": endpoint.model_dump(mode="json"),
                    "request_params": report_params,
                    "error": error,
                }
                continue
            records = _public_report_records(payload)
            reports[report_key] = {
                "status": "live_query",
                "endpoint": endpoint.model_dump(mode="json"),
                "request_params": report_params,
                "summary": _summarize_report(endpoint.label, records, location_terms, sample_limit),
            }
    else:
        for report_key in selected_report_keys:
            endpoint = report_specs.get(report_key)
            reports[report_key] = {
                "status": "not_queried",
                "endpoint": endpoint.model_dump(mode="json") if endpoint else None,
                "reason": public_api_config_status,
            }

    report = _build_location_power_report(mapping, reports, dashboard_data, public_api_config_status)
    data = {
        "status": "location_power_report",
        "provider_id": provider.id,
        "public_api_config_status": public_api_config_status,
        "public_api_token_error": public_api_token_error,
        "report": report,
        "ercot_reports": reports,
        "statewide_context": dashboard_data,
        "dashboard_errors": dashboard_errors,
        "limitations": [
            "ERCOT market reports can indicate local price or congestion stress but do not prove available interconnection capacity.",
            "Location-specific conclusions depend on mapping the parcel to load zones, settlement points, electrical buses, substations, and transmission elements.",
            *provider.limitations,
        ],
    }

    return ProviderQueryResponse(
        provider=provider,
        request_url=provider.endpoints[3].url,
        request_params={
            "analysis_type": "location_power",
            "selected_reports": sorted(selected_report_keys),
            "location_mapping": mapping,
        },
        data=data,
    )


async def query_ercot_dashboard_data(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    headers, public_api_token_error = await _ercot_public_api_headers()
    public_api_config_status = _public_api_config_status(headers, public_api_token_error)

    if request.params.get("analysis_type") in {"location_power", "site_power"}:
        return await query_ercot_location_power_data(
            provider=provider,
            request=request,
            http_client=http_client,
            headers=headers,
            public_api_config_status=public_api_config_status,
            public_api_token_error=public_api_token_error,
        )

    if request.params.get("endpoint") == "public-reports" and public_api_config_status == "configured":
        endpoint = provider.endpoints[3]
        data = await http_client.get_json(str(endpoint.url), headers=headers)

        return ProviderQueryResponse(
            provider=provider,
            request_url=endpoint.url,
            request_params={"endpoint": "public-reports"},
            data=data,
        )

    prc_endpoint = provider.endpoints[0]
    dashboard_data, dashboard_errors = await _dashboard_context(provider, http_client)

    data = {
        "status": "partial_query" if dashboard_errors else "live_query",
        "provider_id": provider.id,
        "public_api_config_status": public_api_config_status,
        "public_api_token_error": public_api_token_error,
        "dashboard_errors": dashboard_errors,
        **dashboard_data,
        "limitations": provider.limitations,
    }

    return ProviderQueryResponse(
        provider=provider,
        request_url=prc_endpoint.url,
        request_params={
            "dashboards": [
                "daily-prc.json",
                "todays-outlook.json",
            ]
        },
        data=data,
    )
