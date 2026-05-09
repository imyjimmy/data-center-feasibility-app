from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import HttpUrl

from app.providers.client import ProviderHttpClient
from app.providers.models import (
    Concern,
    DataProviderDefinition,
    ProviderHealthResponse,
    ProviderListResponse,
    ProviderQueryRequest,
    ProviderQueryResponse,
)
from app.providers.registry import ProviderRegistry, get_provider_registry


router = APIRouter(prefix="/api/providers", tags=["providers"])


def get_http_client() -> ProviderHttpClient:
    return ProviderHttpClient()


def _get_provider_or_404(registry: ProviderRegistry, provider_id: str) -> DataProviderDefinition:
    try:
        return registry.get(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "",
    response_model=ProviderListResponse,
    operation_id="list_data_providers",
    summary="List configured data providers",
)
def list_data_providers(
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    concern: Concern | None = Query(default=None),
    state: str | None = Query(default="TX", min_length=2, max_length=2),
) -> ProviderListResponse:
    return ProviderListResponse(providers=registry.list(concern=concern, state=state))


@router.get(
    "/{provider_id}",
    response_model=DataProviderDefinition,
    operation_id="get_data_provider",
    summary="Get one configured data provider",
)
def get_data_provider(
    provider_id: str,
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> DataProviderDefinition:
    return _get_provider_or_404(registry, provider_id)


@router.get(
    "/{provider_id}/health",
    response_model=ProviderHealthResponse,
    operation_id="check_data_provider_configuration",
    summary="Check whether a provider is queryable or metadata-only",
)
def check_data_provider_configuration(
    provider_id: str,
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProviderHealthResponse:
    provider = _get_provider_or_404(registry, provider_id)
    return ProviderHealthResponse(
        provider_id=provider.id,
        queryable=provider.queryable,
        status="configured" if provider.queryable else "metadata_only",
        reason=None if provider.queryable else "; ".join(provider.limitations[:2]),
    )


@router.post(
    "/{provider_id}/query",
    response_model=ProviderQueryResponse,
    operation_id="query_data_provider",
    summary="Query a configured data provider",
)
async def query_data_provider(
    provider_id: str,
    request: ProviderQueryRequest,
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    http_client: Annotated[ProviderHttpClient, Depends(get_http_client)],
) -> ProviderQueryResponse:
    provider = _get_provider_or_404(registry, provider_id)

    if not provider.queryable:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {provider.id} is metadata-only until a queryable endpoint is configured.",
        )

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

    data = await http_client.get_json(str(endpoint.url), params=params)

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(str(endpoint.url)),
        request_params=params,
        data=data,
    )
