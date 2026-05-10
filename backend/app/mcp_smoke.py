import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic_ai.mcp import MCPServerStreamableHTTP

from app.pydantic_agent import (
    AgentToolCallRecord,
    PydanticAgentResearchError,
    pydantic_agent_is_configured,
    pydantic_agent_mcp_url,
    research_with_pydantic_agent_async,
)
from app.providers.texas_sources.travis_parcels import build_travis_parcel_site_request


class McpToolSummary(BaseModel):
    name: str
    description: str | None = None


class McpGeoFeature(BaseModel):
    provider_id: str
    provider_name: str
    label: str
    geometry_type: str
    rings: list[list[list[float]]] = Field(default_factory=list)
    paths: list[list[list[float]]] = Field(default_factory=list)
    point: list[float] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class McpProviderSmokeResult(BaseModel):
    provider_id: str
    provider_name: str
    queryable: bool
    source: str
    query_scope: str = "metadata_only"
    mcp_tools: list[str] = Field(default_factory=list)
    request_url: str | None = None
    request_params: dict[str, Any] = Field(default_factory=dict)
    health_status: str | None = None
    query_status: str
    data_status: str | None = None
    data_keys: list[str] = Field(default_factory=list)
    data_preview: dict[str, Any] = Field(default_factory=dict)
    feature_count: int | None = None
    sample_attributes: dict[str, Any] = Field(default_factory=dict)
    geo_features: list[McpGeoFeature] = Field(default_factory=list)
    error: str | None = None


class McpSmokeResponse(BaseModel):
    mcp_url: str
    tools: list[McpToolSummary]
    providers: list[McpProviderSmokeResult]


class McpAgentTestRequest(BaseModel):
    prompt: str = Field(min_length=1)
    state: str = Field(default="TX", min_length=2, max_length=2)
    site_context: str | None = Field(default=None, max_length=240)


class McpAgentTestResponse(BaseModel):
    mcp_url: str
    summary: str | None = None
    agent_summary: str | None = None
    provider_insights: list[dict] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_records: list[AgentToolCallRecord] = Field(default_factory=list)
    evidence: list[McpProviderSmokeResult] = Field(default_factory=list)
    site_context: str | None = None


router = APIRouter(prefix="/api/mcp-smoke", tags=["mcp-smoke"])


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _data_keys(value: Any) -> list[str]:
    return sorted(value.keys()) if isinstance(value, dict) else []


def _sample_attributes(features: list[Any]) -> dict[str, Any]:
    if not features:
        return {}

    first_feature = _as_dict(features[0])
    attributes = _as_dict(first_feature.get("attributes"))
    return {key: attributes[key] for key in list(attributes)[:8]}


def _compact_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value)
        return value if len(text) <= 220 else f"{text[:217]}..."
    if isinstance(value, list):
        compact_items = []
        for item in value[:4]:
            if isinstance(item, dict):
                compact_items.append({key: _compact_value(item[key]) for key in list(item)[:5]})
            else:
                compact_items.append(_compact_value(item))
        if len(value) > 4:
            compact_items.append(f"+{len(value) - 4} more")
        return compact_items
    if isinstance(value, dict):
        return {key: _compact_value(value[key]) for key in list(value)[:8]}
    return str(value)


def _data_preview(data: dict[str, Any]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key in (
        "status",
        "provider_id",
        "public_api_config_status",
        "public_api_token_error",
        "report",
        "ercot_reports",
        "statewide_context",
        "grid_condition",
        "grid_condition_last_updated",
        "latest_prc",
        "outlook_last_updated",
        "latest_outlook",
        "input",
        "geocode",
        "h3_hex",
        "h3_resolution",
        "count",
        "summary",
        "providers",
        "queries",
        "match_count",
        "matches",
        "data_center_interpretation",
        "source_endpoints",
        "searches",
        "result_count",
        "results",
        "source_homepage",
        "endpoints",
        "limitations",
        "features",
        "fields",
        "exceededTransferLimit",
    ):
        if key in data:
            preview[key] = _compact_value(data[key])

    return preview or {key: _compact_value(data[key]) for key in list(data)[:8]}


def _lat_lng_pairs(coordinates: Any) -> list[list[float]]:
    pairs: list[list[float]] = []
    if not isinstance(coordinates, list):
        return pairs

    for coordinate in coordinates:
        if (
            isinstance(coordinate, list)
            and len(coordinate) >= 2
            and isinstance(coordinate[0], (int, float))
            and isinstance(coordinate[1], (int, float))
        ):
            lon = float(coordinate[0])
            lat = float(coordinate[1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                pairs.append([lat, lon])

    return pairs


def _point_geo_feature(provider_id: str, provider_name: str, data: dict[str, Any]) -> McpGeoFeature | None:
    geocode = _as_dict(data.get("geocode"))
    lat = geocode.get("lat")
    lng = geocode.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        input_data = _as_dict(data.get("input"))
        lat = input_data.get("lat")
        lng = input_data.get("lng")

    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None

    latitude = float(lat)
    longitude = float(lng)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    label = str(geocode.get("matched_address") or _as_dict(data.get("input")).get("site_context") or provider_name)
    return McpGeoFeature(
        provider_id=provider_id,
        provider_name=provider_name,
        label=label,
        geometry_type="point",
        point=[latitude, longitude],
        attributes={
            key: value
            for key, value in {
                "source": data.get("source"),
                "matched_address": geocode.get("matched_address"),
                "score": geocode.get("score"),
            }.items()
            if value is not None
        },
    )


def _geocode_point(data: dict[str, Any]) -> tuple[float, float] | None:
    geocode = _as_dict(data.get("geocode"))
    lat = geocode.get("lat")
    lng = geocode.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def _extent_ring(extent: Any) -> list[list[float]]:
    if not (
        isinstance(extent, list)
        and len(extent) >= 2
        and isinstance(extent[0], list)
        and isinstance(extent[1], list)
        and len(extent[0]) >= 2
        and len(extent[1]) >= 2
    ):
        return []

    xmin, ymin = extent[0][0], extent[0][1]
    xmax, ymax = extent[1][0], extent[1][1]
    if not all(isinstance(value, (int, float)) for value in (xmin, ymin, xmax, ymax)):
        return []

    west = float(xmin)
    south = float(ymin)
    east = float(xmax)
    north = float(ymax)
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90):
        return []

    return [[south, west], [south, east], [north, east], [north, west], [south, west]]


def _catalog_extent_geo_features(provider_id: str, provider_name: str, data: dict[str, Any]) -> list[McpGeoFeature]:
    geo_features: list[McpGeoFeature] = []
    for match in _as_list(data.get("matches"))[:8]:
        match_dict = _as_dict(match)
        ring = _extent_ring(match_dict.get("extent"))
        if not ring:
            continue

        title = str(match_dict.get("title") or match_dict.get("id") or provider_name)
        geo_features.append(
            McpGeoFeature(
                provider_id=provider_id,
                provider_name=provider_name,
                label=title,
                geometry_type="catalog_extent",
                rings=[ring],
                attributes={
                    key: match_dict[key]
                    for key in ("id", "title", "type", "owner", "service_url", "item_url")
                    if key in match_dict
                },
            )
        )

    return geo_features


def _geo_features(
    provider_id: str,
    provider_name: str,
    data: dict[str, Any],
    features: list[Any],
) -> list[McpGeoFeature]:
    geo_features: list[McpGeoFeature] = []
    point_feature = _point_geo_feature(provider_id, provider_name, data)
    if point_feature:
        geo_features.append(point_feature)
    geo_features.extend(_catalog_extent_geo_features(provider_id, provider_name, data))

    geometry_type = str(data.get("geometryType") or "unknown")

    for feature in features[:8]:
        feature_dict = _as_dict(feature)
        geometry = _as_dict(feature_dict.get("geometry"))
        if not geometry:
            continue

        attributes = _as_dict(feature_dict.get("attributes"))
        label = (
            str(attributes.get("situs_address") or "")
            or str(attributes.get("TITLE") or "")
            or str(attributes.get("OBJECTID") or provider_name)
        )
        rings = [
            ring
            for ring in (_lat_lng_pairs(ring) for ring in geometry.get("rings", []))
            if ring
        ]
        paths = [
            path
            for path in (_lat_lng_pairs(path) for path in geometry.get("paths", []))
            if path
        ]
        point = None
        x = geometry.get("x")
        y = geometry.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            lon = float(x)
            lat = float(y)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                point = [lat, lon]

        if rings or paths or point:
            geo_features.append(
                McpGeoFeature(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    label=label,
                    geometry_type=geometry_type,
                    rings=rings,
                    paths=paths,
                    point=point,
                    attributes={key: attributes[key] for key in list(attributes)[:8]},
                )
            )

    return geo_features


def _site_query_args(
    provider_id: str,
    site_context: str | None,
    limit: int,
    resolved_point: tuple[float, float] | None = None,
) -> tuple[dict[str, Any], str]:
    args: dict[str, Any] = {
        "provider_id": provider_id,
        "limit": limit,
        "return_geometry": False,
    }
    if not site_context:
        if provider_id == "ercot_market_data_transparency":
            args["limit"] = min(limit, 5)
            args["params"] = {
                "analysis_type": "location_power",
                "site_name": "Austin / Travis County default test location",
                "latitude": 30.2672,
                "longitude": -97.7431,
                "county": "Travis",
                "municipality": "Austin",
                "load_zone": "LZ_AEN",
                "nearby_settlement_points": ["LZ_AEN"],
                "reports": ["rt_settlement_point_prices", "rt_lmp_node_zone_hub"],
                "sample_limit": 2,
            }
            return args, "site_power_market_context"
        return args, "provider_sample"

    coordinate_match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", site_context)
    if provider_id == "ercot_market_data_transparency":
        params: dict[str, Any] = {
            "analysis_type": "location_power",
            "site_name": site_context,
            "county": "Travis",
            "municipality": "Austin",
            "load_zone": "LZ_AEN",
            "nearby_settlement_points": ["LZ_AEN"],
            "reports": ["rt_settlement_point_prices", "rt_lmp_node_zone_hub"],
            "sample_limit": 2,
        }
        if coordinate_match:
            first = float(coordinate_match.group(1))
            second = float(coordinate_match.group(2))
            lat, lon = (second, first) if abs(first) > 90 and abs(second) <= 90 else (first, second)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                params["latitude"] = lat
                params["longitude"] = lon
        else:
            params["latitude"] = 30.2672
            params["longitude"] = -97.7431
        args["limit"] = min(limit, 5)
        args["params"] = params
        return args, "site_power_market_context"

    if provider_id == "texas_broadband_development_map":
        if coordinate_match:
            first = float(coordinate_match.group(1))
            second = float(coordinate_match.group(2))
            lat, lon = (second, first) if abs(first) > 90 and abs(second) <= 90 else (first, second)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                args["params"] = {"lat": lat, "lng": lon, "service_type": "business", "site_context": site_context}
                return args, "site_point"
        args["params"] = {"site_context": site_context, "service_type": "business"}
        return args, "site_address_geocode"

    if provider_id == "txgio_geospatial_catalog":
        args["params"] = {"site_context": site_context}
        args["limit"] = min(limit, 5)
        return args, "site_catalog_search"

    if provider_id == "texas_real_estate_research_center":
        args["params"] = {"site_context": site_context}
        args["limit"] = min(limit, 5)
        return args, "market_research_search"

    if resolved_point and provider_id == "austin_water_utility_service_area":
        lat, lon = resolved_point
        delta = 0.001
        args["bbox"] = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
        args["params"] = {"inSR": 4326, "outSR": 4326}
        return args, "site_geocode_intersection"

    if coordinate_match:
        first = float(coordinate_match.group(1))
        second = float(coordinate_match.group(2))
        lat, lon = (second, first) if abs(first) > 90 and abs(second) <= 90 else (first, second)
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            delta = 0.01
            args["bbox"] = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
            args["return_geometry"] = True
            args["params"] = {"inSR": 4326, "outSR": 4326}
            return args, "site_bbox"

    if provider_id == "travis_county_parcels":
        request = build_travis_parcel_site_request(site_context, limit=limit)
        if request:
            args.update(
                {
                    "where": request.where,
                    "out_fields": request.out_fields,
                    "limit": request.limit,
                    "return_geometry": request.return_geometry,
                    "params": request.params,
                }
            )
            return args, "site_address_filter"

    return args, "provider_sample"


def _provider_result_by_id(
    evidence: list[McpProviderSmokeResult],
    provider_id: str,
) -> McpProviderSmokeResult | None:
    return next((provider for provider in evidence if provider.provider_id == provider_id), None)


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _parcel_attributes(parcel: McpProviderSmokeResult | None) -> dict[str, Any]:
    if not parcel:
        return {}
    if parcel.sample_attributes:
        return parcel.sample_attributes

    features = _as_list(parcel.data_preview.get("features"))
    if not features:
        return {}
    return _as_dict(_as_dict(features[0]).get("attributes"))


def _status_line(label: str, value: str) -> str:
    return f"{label}: {value}"


def _build_actionable_summary(
    evidence: list[McpProviderSmokeResult],
    agent_summary: str | None,
    site_context: str | None,
) -> str:
    parcel = _provider_result_by_id(evidence, "travis_county_parcels")
    broadband = _provider_result_by_id(evidence, "texas_broadband_development_map")
    water = _provider_result_by_id(evidence, "austin_water_utility_service_area")
    ercot = _provider_result_by_id(evidence, "ercot_market_data_transparency")
    txgio = _provider_result_by_id(evidence, "txgio_geospatial_catalog")

    parcel_attrs = _parcel_attributes(parcel)
    parcel_id = _first_value(parcel_attrs.get("PROP_ID"), parcel_attrs.get("prop_id"))
    parcel_address = _first_value(parcel_attrs.get("situs_address"), parcel_attrs.get("SITEADDRESS"))
    owner = _first_value(parcel_attrs.get("py_owner_name"), parcel_attrs.get("OWNER_NAME"))
    acres = _float_value(_first_value(parcel_attrs.get("tcad_acres"), parcel_attrs.get("GIS_acres"), parcel_attrs.get("ACRES")))

    resolved_site = bool(parcel and (parcel.feature_count or 0) > 0)
    broadband_summary = _as_dict((broadband.data_preview if broadband else {}).get("summary"))
    fiber_count = broadband_summary.get("fiber_provider_count")
    fiber_names = _as_list(broadband_summary.get("fiber_provider_names"))
    grid_condition = _as_dict((ercot.data_preview if ercot else {}).get("grid_condition"))
    prc = _as_dict((ercot.data_preview if ercot else {}).get("latest_prc")).get("prc")
    txgio_matches = (txgio.data_preview if txgio else {}).get("match_count")

    recommendation = "Needs site resolution before ranking."
    first_blocker = "Parcel/coordinates are not resolved from the configured evidence."
    if resolved_site and acres is not None and acres < 5:
        recommendation = "Screen out for a 25 MW or campus-style data-center search."
        first_blocker = f"Parcel scale: {acres:g} acres is the first blocker before power, water, or fiber diligence."
    elif resolved_site:
        recommendation = "Keep only as a preliminary candidate until utility and zoning blockers are cleared."
        first_blocker = "Power interconnection, zoning, and water/wastewater capacity remain unproven."

    lines = [
        _status_line("Recommendation", recommendation),
        _status_line("First blocker", first_blocker),
    ]

    if site_context:
        lines.append(_status_line("Input", site_context))

    if resolved_site:
        parcel_bits = ["Travis parcel matched"]
        if parcel_id:
            parcel_bits.append(f"PROP_ID {parcel_id}")
        if parcel_address:
            parcel_bits.append(str(parcel_address))
        if acres is not None:
            parcel_bits.append(f"{acres:g} acres")
        if owner:
            parcel_bits.append(f"owner {owner}")
        lines.append(_status_line("Site evidence", "; ".join(parcel_bits)))
    elif parcel:
        lines.append(_status_line("Site evidence", "No Travis parcel feature matched the configured site query."))

    location_evidence: list[str] = []
    if broadband and broadband.geo_features:
        location_evidence.append("broadband/geocoder returned a mapped point")
    if broadband_summary:
        if fiber_count is not None:
            names = ", ".join(str(name) for name in fiber_names[:4])
            location_evidence.append(
                f"broadband availability returned {fiber_count} fiber provider signal(s)"
                + (f" ({names})" if names else "")
            )
    if water:
        if water.query_scope == "site_geocode_intersection" and (water.feature_count or 0) > 0:
            location_evidence.append("Austin Water service-area boundary intersected the geocoded site area")
        elif water.query_scope == "provider_sample":
            location_evidence.append("Austin Water returned only a generic sample, not a site intersect")
    if location_evidence:
        lines.append(_status_line("Location-specific signals", "; ".join(location_evidence)))

    context_signals: list[str] = []
    if grid_condition:
        condition = _first_value(grid_condition.get("title"), grid_condition.get("state"))
        context_signals.append(f"ERCOT system context: {condition}" + (f", PRC {prc:g}" if isinstance(prc, (int, float)) else ""))
    if txgio_matches is not None:
        context_signals.append(f"TxGIO returned {txgio_matches} catalog match(es) for follow-on parcel/zoning datasets")
    if context_signals:
        lines.append(_status_line("Context signals", "; ".join(context_signals)))

    lines.append(
        _status_line(
            "Not yet decision-grade",
            "serving electric utility/substation capacity, City of Austin zoning/overlays, water and wastewater capacity, and carrier-grade fiber route diversity",
        )
    )
    lines.append(
        _status_line(
            "Actionable next step",
            "For this site, verify zoning only if evaluating a small edge/retrofit use; otherwise shift the search to larger industrial parcels with known utility capacity and nearby transmission/substation access.",
        )
    )

    if agent_summary:
        lines.append(_status_line("Agent research note", agent_summary))

    return "\n".join(lines)


def _build_evidence_provider_insights(
    evidence: list[McpProviderSmokeResult],
    agent_insights: list[dict],
) -> list[dict]:
    insights: list[dict] = []
    seen: set[str] = set()

    for provider in evidence:
        seen.add(provider.provider_id)
        status = "metadata_only"
        summary = provider.query_status
        limitations: list[str] = []

        if provider.error:
            status = "failed"
            summary = provider.error
        elif provider.provider_id == "travis_county_parcels":
            attrs = _parcel_attributes(provider)
            acres = _float_value(_first_value(attrs.get("tcad_acres"), attrs.get("GIS_acres"), attrs.get("ACRES")))
            parcel_id = _first_value(attrs.get("PROP_ID"), attrs.get("prop_id"))
            if (provider.feature_count or 0) > 0:
                status = "site_evidence"
                summary = f"Matched {provider.feature_count} Travis parcel feature(s)"
                if parcel_id:
                    summary += f"; PROP_ID {parcel_id}"
                if acres is not None:
                    summary += f"; {acres:g} acres"
                    if acres < 5:
                        limitations.append("Parcel scale is likely a first blocker for a 25 MW or campus-style data-center site.")
            else:
                status = "no_match"
                summary = "No Travis parcel feature matched the configured site query."
            limitations.append("Parcel data does not prove zoning, entitlements, power capacity, or water/wastewater capacity.")
        elif provider.provider_id == "texas_broadband_development_map":
            data_summary = _as_dict(provider.data_preview.get("summary"))
            fiber_count = data_summary.get("fiber_provider_count")
            if provider.geo_features or fiber_count is not None:
                status = "site_evidence"
                summary = "Returned a site geocode/broadband availability response"
                if fiber_count is not None:
                    summary += f" with {fiber_count} fiber provider signal(s)"
            else:
                status = "not_site_queryable"
                summary = "No location-specific broadband availability response was returned."
            limitations.append("Broadband availability is not proof of data-center-grade on-net fiber, route diversity, dark fiber, SLA, or lateral build feasibility.")
        elif provider.provider_id == "austin_water_utility_service_area":
            if provider.query_scope == "site_geocode_intersection" and (provider.feature_count or 0) > 0:
                status = "site_evidence"
                summary = "Service-area boundary returned for the geocoded site area."
            else:
                status = "generic_sample"
                summary = "Returned service-area data without a site-specific utility capacity determination."
            limitations.append("Service-area evidence does not prove available flow, pressure, tap size, wastewater capacity, or utility commitment.")
        elif provider.provider_id == "ercot_market_data_transparency":
            location_report = _as_dict(provider.data_preview.get("report"))
            if location_report:
                status = "site_power_market_context"
                risk_level = location_report.get("site_power_risk_level")
                report_summary = location_report.get("summary")
                summary = f"ERCOT location power report returned {risk_level or 'unknown'} risk."
                if report_summary:
                    summary += f" {report_summary}"
                limitations.append(
                    "ERCOT market and constraint records can indicate local stress but do not prove available interconnection capacity."
                )
            else:
                grid_condition = _as_dict(provider.data_preview.get("grid_condition"))
                status = "generic_grid_context"
                summary = f"ERCOT dashboard context returned {grid_condition.get('title') or provider.data_status or 'grid status'}."
                limitations.append("ERCOT dashboard data is system-wide and does not answer site-level interconnection capacity.")
        elif provider.provider_id == "txgio_geospatial_catalog":
            status = "dataset_discovery"
            summary = f"Returned {provider.data_preview.get('match_count', 0)} catalog match(es) for follow-on GIS datasets."
            limitations.append("Catalog matches are not parcel/zoning decisions; selected services still need site-level queries.")
        elif provider.provider_id == "texas_real_estate_research_center":
            status = "market_context"
            summary = f"Returned {provider.data_preview.get('result_count', 0)} market research result(s)."
            limitations.append("Market research is not parcel/site control, zoning, utility, or fiber serviceability evidence.")
        elif provider.source == "metadata_only":
            status = "metadata_only"
            summary = "Provider is metadata-only in this workflow."

        insights.append(
            {
                "provider_id": provider.provider_id,
                "status": status,
                "summary": summary,
                "limitations": limitations,
            }
        )

    for insight in agent_insights:
        provider_id = str(insight.get("provider_id") or "")
        if provider_id and provider_id not in seen:
            insights.append(insight)

    return insights


async def run_mcp_provider_smoke(
    state: str = "TX",
    limit: int = 2,
    site_context: str | None = None,
) -> McpSmokeResponse:
    server = MCPServerStreamableHTTP(pydantic_agent_mcp_url())
    tools = await server.list_tools()
    tool_summaries = [
        McpToolSummary(name=tool.name, description=tool.description)
        for tool in sorted(tools, key=lambda item: item.name)
    ]

    providers_result = await server.direct_call_tool("list_providers", {"state": state})
    providers = _as_list(providers_result)
    results: list[McpProviderSmokeResult] = []
    resolved_point: tuple[float, float] | None = None

    for provider in providers:
        provider_dict = _as_dict(provider)
        provider_id = str(provider_dict.get("id") or "unknown")
        provider_name = str(provider_dict.get("name") or provider_id)
        queryable = bool(provider_dict.get("queryable"))

        try:
            if not queryable:
                metadata = _as_dict(await server.direct_call_tool("provider_metadata", {"provider_id": provider_id}))
                endpoints = _as_list(metadata.get("endpoints"))
                source_homepage = str(metadata.get("source_homepage") or "")
                request_url = str(_as_dict(endpoints[0]).get("url") or source_homepage) if endpoints else source_homepage

                results.append(
                    McpProviderSmokeResult(
                        provider_id=provider_id,
                        provider_name=provider_name,
                        queryable=False,
                        source="metadata_only",
                        query_scope="metadata_only",
                        mcp_tools=["provider_metadata"],
                        request_url=request_url,
                        health_status="metadata_only",
                        query_status="metadata_returned",
                        data_status="metadata_only",
                        data_keys=_data_keys(metadata),
                        data_preview=_data_preview(metadata),
                    )
                )
                continue

            query_args, query_scope = _site_query_args(
                provider_id=provider_id,
                site_context=site_context,
                limit=limit,
                resolved_point=resolved_point,
            )
            query_result = _as_dict(
                await server.direct_call_tool(
                    "query_provider",
                    query_args,
                )
            )
            data = _as_dict(query_result.get("data"))
            if resolved_point is None:
                resolved_point = _geocode_point(data)
            features = _as_list(data.get("features"))
            request_params = _as_dict(query_result.get("request_params"))

            results.append(
                McpProviderSmokeResult(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    queryable=queryable,
                    source="live_query" if queryable else "metadata_only",
                    query_scope=query_scope if queryable else "metadata_only",
                    mcp_tools=["query_provider"],
                    request_url=str(query_result.get("request_url") or ""),
                    request_params=request_params,
                    health_status="configured" if queryable else "metadata_only",
                    query_status="returned",
                    data_status=str(data.get("status")) if data.get("status") else None,
                    data_keys=_data_keys(data),
                    data_preview=_data_preview(data),
                    feature_count=len(features) if "features" in data else None,
                    sample_attributes=_sample_attributes(features),
                    geo_features=_geo_features(
                        provider_id=provider_id,
                        provider_name=provider_name,
                        data=data,
                        features=features,
                    ),
                )
            )
        except Exception as exc:
            results.append(
                McpProviderSmokeResult(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    queryable=queryable,
                    source="failed",
                    mcp_tools=["query_provider"],
                    query_status="failed",
                    error=str(exc),
                )
            )

    return McpSmokeResponse(
        mcp_url=pydantic_agent_mcp_url(),
        tools=tool_summaries,
        providers=results,
    )


@router.post("/providers", response_model=McpSmokeResponse, operation_id="run_mcp_provider_smoke_test")
async def smoke_providers(
    state: str = Query(default="TX", min_length=2, max_length=2),
    limit: int = Query(default=2, ge=1, le=10),
    site_context: str | None = Query(default=None, max_length=240),
) -> McpSmokeResponse:
    return await run_mcp_provider_smoke(state=state.upper(), limit=limit, site_context=site_context)


@router.post("/agent", response_model=McpAgentTestResponse, operation_id="run_mcp_agent_test")
async def test_agent(request: McpAgentTestRequest) -> McpAgentTestResponse:
    if not pydantic_agent_is_configured():
        raise HTTPException(status_code=503, detail="Pydantic AI agent is not configured")

    site_context = request.site_context.strip() if request.site_context else None
    try:
        evidence, result = await asyncio.gather(
            run_mcp_provider_smoke(
                state=request.state.upper(),
                limit=2,
                site_context=site_context,
            ),
            research_with_pydantic_agent_async(
                question=request.prompt,
                state=request.state.upper(),
                run_id="mcp-test",
                site_context=site_context,
            ),
        )
    except PydanticAgentResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    summary = _build_actionable_summary(
        evidence=evidence.providers,
        agent_summary=result.summary,
        site_context=site_context,
    )

    return McpAgentTestResponse(
        mcp_url=pydantic_agent_mcp_url(),
        summary=summary,
        agent_summary=result.summary,
        provider_insights=_build_evidence_provider_insights(evidence.providers, result.provider_insights),
        tool_calls=result.tool_calls,
        tool_call_records=result.tool_call_records,
        evidence=evidence.providers,
        site_context=site_context,
    )
