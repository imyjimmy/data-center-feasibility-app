from typing import Any

from pydantic import HttpUrl

from app.providers.client import ProviderHttpClient
from app.providers.models import DataProviderDefinition, ProviderQueryRequest, ProviderQueryResponse
from app.providers.texas_sources.broadband import query_broadband_location_data
from app.providers.texas_sources.ercot import query_ercot_dashboard_data
from app.providers.texas_sources.real_estate import query_real_estate_research_matches
from app.providers.texas_sources.travis_parcels import query_travis_parcel_data
from app.providers.texas_sources.txgio import query_txgio_catalog_matches
from app.providers.texas_sources.web_search import query_web_search_leads


def build_provider_query(provider: DataProviderDefinition, request: ProviderQueryRequest) -> tuple[str, dict[str, Any]]:
    endpoint = provider.endpoints[0]
    params = {
        "f": "json",
        "where": request.where,
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

    return str(endpoint.url), params


async def query_provider_data(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    if provider.id == "ercot_market_data_transparency":
        return await query_ercot_dashboard_data(provider=provider, request=request, http_client=http_client)

    if provider.id == "texas_broadband_development_map":
        return await query_broadband_location_data(provider=provider, request=request, http_client=http_client)

    if provider.id == "txgio_geospatial_catalog":
        return await query_txgio_catalog_matches(provider=provider, request=request, http_client=http_client)

    if provider.id == "texas_real_estate_research_center":
        return await query_real_estate_research_matches(provider=provider, request=request, http_client=http_client)

    if provider.id == "data_center_web_search":
        return await query_web_search_leads(provider=provider, request=request, http_client=http_client)

    if provider.id == "travis_county_parcels":
        return await query_travis_parcel_data(provider=provider, request=request, http_client=http_client)

    if not provider.queryable:
        endpoint = provider.endpoints[0]
        metadata = {
            "status": "metadata_only",
            "provider_id": provider.id,
            "source_homepage": str(provider.source_homepage),
            "endpoints": [endpoint.model_dump(mode="json") for endpoint in provider.endpoints],
            "limitations": provider.limitations,
        }
        return ProviderQueryResponse(
            provider=provider,
            request_url=HttpUrl(str(endpoint.url)),
            request_params={},
            data=metadata,
        )

    url, params = build_provider_query(provider, request)
    data = await http_client.get_json(url, params=params)

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(url),
        request_params=params,
        data=data,
    )
