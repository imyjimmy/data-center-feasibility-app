from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class Concern(StrEnum):
    POWER_STRESS = "power_stress"
    WATER = "water"
    FIBER_AVAILABILITY = "fiber_availability"
    ZONING = "zoning"
    ICP = "icp"
    PARCEL_GEOCODING = "parcel_geocoding"


class ProviderKind(StrEnum):
    ARCGIS_FEATURE_SERVICE = "arcgis_feature_service"
    ARCGIS_MAP_SERVICE = "arcgis_map_service"
    REST_API = "rest_api"
    OPEN_DATA_PORTAL = "open_data_portal"
    CONTACT_DIRECTORY = "contact_directory"
    WEB_MAP = "web_map"


class ProviderCapability(StrEnum):
    QUERY_FEATURES = "query_features"
    FETCH_JSON = "fetch_json"
    SOURCE_METADATA = "source_metadata"
    CONTACT_LOOKUP = "contact_lookup"


class ProviderCoverage(BaseModel):
    country: str = "US"
    state: str = "TX"
    counties: list[str] = Field(default_factory=list)
    municipalities: list[str] = Field(default_factory=list)


class ProviderEndpoint(BaseModel):
    label: str
    url: HttpUrl
    method: Literal["GET"] = "GET"
    notes: str | None = None


class DataProviderDefinition(BaseModel):
    id: str
    name: str
    concern: Concern
    kind: ProviderKind
    capabilities: list[ProviderCapability]
    coverage: ProviderCoverage
    description: str
    owner: str
    source_homepage: HttpUrl
    endpoints: list[ProviderEndpoint]
    queryable: bool
    authentication: str = "none"
    update_frequency: str | None = None
    limitations: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ProviderListResponse(BaseModel):
    providers: list[DataProviderDefinition]


class ProviderQueryRequest(BaseModel):
    where: str = "1=1"
    out_fields: str = "*"
    limit: int = Field(default=25, ge=1, le=500)
    return_geometry: bool = True
    bbox: str | None = Field(
        default=None,
        description="Optional ArcGIS envelope: xmin,ymin,xmax,ymax in the provider spatial reference.",
    )
    params: dict[str, Any] = Field(default_factory=dict)


class ProviderQueryResponse(BaseModel):
    provider: DataProviderDefinition
    request_url: HttpUrl
    request_params: dict[str, Any]
    data: dict[str, Any]


class ProviderHealthResponse(BaseModel):
    provider_id: str
    queryable: bool
    status: Literal["configured", "metadata_only"]
    reason: str | None = None
