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


ARCGIS_GEOCODE_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
BROADBANDMAP_INTERNET_URL = "https://broadbandmap.com/api/v1/location/internet"

BROADBAND_ACCESS_PATHS = [
    {
        "label": "Texas Broadband Development Maps",
        "url": "https://comptroller.texas.gov/programs/broadband/outreach/maps/",
        "use": "Texas BDO map/documentation hub for broadband availability and program-map context.",
    },
    {
        "label": "Texas BDO FCC National Broadband Map guidance",
        "url": "https://comptroller.texas.gov/programs/broadband/outreach/maps/fcc/",
        "use": "Texas BDO guidance for address-level FCC map lookup and map challenges.",
    },
    {
        "label": "Broadband Map location API",
        "url": BROADBANDMAP_INTERNET_URL,
        "use": "Coordinate-level internet provider lookup derived from FCC Broadband Data Collection data.",
    },
    {
        "label": "FCC National Broadband Map",
        "url": "https://broadbandmap.fcc.gov/home",
        "use": "Manual address/location-level broadband availability lookup based on FCC Broadband Data Collection submissions.",
    },
    {
        "label": "FCC Broadband Funding Map",
        "url": "https://fundingmap.fcc.gov/home",
        "use": "Federally funded broadband infrastructure project context.",
    },
    {
        "label": "Texas BEAD Map",
        "url": "https://register.broadband.texas.gov/award/bead/map",
        "use": "Texas BEAD project awards and coverage areas.",
    },
]

BROADBAND_CHALLENGE_TYPES = [
    "availability_challenge",
    "location_challenge",
    "bulk_fabric_challenge",
    "bulk_fixed_availability_challenge",
]

BROADBAND_DILIGENCE_LIMITATIONS = [
    "Texas BDO states granular Texas map data is proprietary and cannot be downloaded due to FCC restrictions.",
    "This provider is not a carrier route, dark-fiber, SLA, meet-me-room, or diverse-path source.",
        "FCC/BDO broadband availability does not prove enterprise data-center-grade fiber serviceability.",
    "Site diligence still requires carrier outreach for on-net status, lateral construction, diverse entrances, route diversity, and commercial terms.",
]


def broadband_metadata_payload(request: ProviderQueryRequest | None = None) -> dict[str, object]:
    """Return source-specific metadata for broadband/fiber screening.

    The Texas BDO source is useful context, but it does not expose a public
    programmatic location API in this app. Keep the output explicit so agents do
    not treat it as parcel-level fiber evidence.
    """

    return {
        "status": "metadata_only",
        "provider_id": TEXAS_BROADBAND_DEVELOPMENT_MAP.id,
        "source_homepage": str(TEXAS_BROADBAND_DEVELOPMENT_MAP.source_homepage),
        "source_basis": "Texas BDO describes the map as using FCC Broadband Data Collection data reported by ISPs.",
        "update_cadence": "FCC Broadband Data Collection cycles are updated every six months; Texas BDO program maps update as programs change.",
        "location_queryable": False,
        "downloadable_granular_data": False,
        "address_lookup_path": "Use the FCC National Broadband Map manually for address/location-level broadband availability.",
        "requested_site_context": request.params.get("site_context") if request else None,
        "access_paths": BROADBAND_ACCESS_PATHS,
        "fcc_challenge_types": BROADBAND_CHALLENGE_TYPES,
        "data_center_diligence_use": [
            "Use as public broadband/funding-map context only.",
            "Treat any map availability signal as a starting point for carrier validation, not as fiber feasibility evidence.",
            "For a data-center site, collect carrier route maps, on-net confirmation, lateral cost/timing, diverse-path proof, and SLA/commercial availability.",
        ],
        "limitations": BROADBAND_DILIGENCE_LIMITATIONS,
    }


def _float_param(params: dict[str, object], key: str) -> float | None:
    value = params.get(key)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coordinate_input(request: ProviderQueryRequest) -> tuple[float, float] | None:
    lat = _float_param(request.params, "lat")
    lng = _float_param(request.params, "lng")
    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng

    if request.bbox:
        try:
            xmin, ymin, xmax, ymax = [float(part.strip()) for part in request.bbox.split(",", maxsplit=3)]
        except ValueError:
            return None
        lat = (ymin + ymax) / 2
        lng = (xmin + xmax) / 2
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng

    return None


def _provider_summary(providers: list[object]) -> dict[str, object]:
    records = [provider for provider in providers if isinstance(provider, dict)]
    fiber = [provider for provider in records if str(provider.get("technology", "")).lower() == "fiber"]
    terrestrial = [
        provider
        for provider in records
        if str(provider.get("technology", "")).lower() not in {"gso satellite", "leo satellite"}
    ]
    max_download = max(
        [float(provider["max_download_mbps"]) for provider in records if isinstance(provider.get("max_download_mbps"), int | float)],
        default=None,
    )
    max_upload = max(
        [float(provider["max_upload_mbps"]) for provider in records if isinstance(provider.get("max_upload_mbps"), int | float)],
        default=None,
    )

    return {
        "provider_count": len(records),
        "fiber_provider_count": len(fiber),
        "terrestrial_provider_count": len(terrestrial),
        "fiber_provider_names": [str(provider.get("name")) for provider in fiber if provider.get("name")],
        "max_reported_download_mbps": max_download,
        "max_reported_upload_mbps": max_upload,
    }


async def _geocode_site_context(site_context: str, http_client: ProviderHttpClient) -> dict[str, object] | None:
    geocode = await http_client.get_json(
        ARCGIS_GEOCODE_URL,
        params={
            "SingleLine": site_context,
            "f": "json",
            "outFields": "Match_addr,Addr_type",
            "maxLocations": 1,
        },
    )
    candidates = geocode.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        return None
    location = candidate.get("location")
    if not isinstance(location, dict):
        return None
    lat = location.get("y")
    lng = location.get("x")
    if not isinstance(lat, int | float) or not isinstance(lng, int | float):
        return None

    return {
        "lat": float(lat),
        "lng": float(lng),
        "matched_address": candidate.get("address"),
        "score": candidate.get("score"),
        "source": "arcgis_world_geocoder",
    }


async def query_broadband_location_data(
    provider: DataProviderDefinition,
    request: ProviderQueryRequest,
    http_client: ProviderHttpClient,
) -> ProviderQueryResponse:
    endpoint = provider.endpoints[0]
    params = dict(request.params)
    service_type = str(params.get("service_type") or "business")
    site_context = params.get("site_context")
    coordinates = _coordinate_input(request)
    geocode: dict[str, object] | None = None

    if coordinates is None and isinstance(site_context, str) and site_context.strip():
        geocode = await _geocode_site_context(site_context.strip(), http_client=http_client)
        if geocode:
            coordinates = (float(geocode["lat"]), float(geocode["lng"]))

    request_params = {
        "where": request.where,
        "outFields": request.out_fields,
        "resultRecordCount": request.limit,
        "returnGeometry": str(request.return_geometry).lower(),
        "service_type": service_type,
        "site_context": site_context,
    }

    if coordinates is None:
        metadata = broadband_metadata_payload(request)
        metadata.update(
            {
                "status": "metadata_only",
                "location_queryable": True,
                "query_status": "missing_location",
                "required_location_input": "Provide lat/lng, bbox, or site_context address in request.params.",
            }
        )
        return ProviderQueryResponse(
            provider=provider,
            request_url=HttpUrl(str(endpoint.url)),
            request_params=request_params,
            data=metadata,
        )

    lat, lng = coordinates
    broadband = await http_client.get_json(
        BROADBANDMAP_INTERNET_URL,
        params={"lat": lat, "lng": lng, "service_type": service_type},
    )
    providers = broadband.get("providers") if isinstance(broadband.get("providers"), list) else []
    summary = _provider_summary(providers)

    return ProviderQueryResponse(
        provider=provider,
        request_url=HttpUrl(BROADBANDMAP_INTERNET_URL),
        request_params={
            **request_params,
            "lat": lat,
            "lng": lng,
            "broadband_api": BROADBANDMAP_INTERNET_URL,
        },
        data={
            "status": "live_query",
            "provider_id": provider.id,
            "source": "broadbandmap_com_fcc_bdc_derived",
            "source_basis": "Broadband Map API uses FCC Broadband Data Collection availability data as its foundation.",
            "input": {
                "site_context": site_context,
                "lat": lat,
                "lng": lng,
                "service_type": service_type,
            },
            "geocode": geocode,
            "h3_hex": broadband.get("h3_hex"),
            "h3_resolution": broadband.get("h3_resolution"),
            "count": broadband.get("count"),
            "summary": summary,
            "providers": providers,
            "data_center_interpretation": [
                "This is location-specific reported business broadband availability.",
                "Fiber providers in this result are a useful carrier-outreach lead list.",
                "This does not prove data-center-grade on-net fiber, route diversity, available waves/dark fiber, SLA, or lateral construction feasibility.",
            ],
            "limitations": BROADBAND_DILIGENCE_LIMITATIONS,
            "access_paths": BROADBAND_ACCESS_PATHS,
        },
    )


TEXAS_BROADBAND_DEVELOPMENT_MAP = DataProviderDefinition(
    id="texas_broadband_development_map",
    name="Texas Broadband Development Map",
    concern=Concern.FIBER_AVAILABILITY,
    kind=ProviderKind.REST_API,
    capabilities=[ProviderCapability.FETCH_JSON, ProviderCapability.SOURCE_METADATA],
    coverage=ProviderCoverage(),
    description=(
        "Texas Broadband Development Office map and documentation for broadband availability. "
        "Useful for fiber/broadband availability context and eligibility screening."
    ),
    owner="Texas Comptroller Broadband Development Office",
    source_homepage="https://comptroller.texas.gov/programs/broadband/outreach/maps/",
    endpoints=[
        ProviderEndpoint(
            label="Broadband Map location API",
            url=BROADBANDMAP_INTERNET_URL,
            notes="Coordinate-level internet provider lookup derived from FCC BDC data.",
        ),
        ProviderEndpoint(
            label="Broadband Development Maps",
            url="https://comptroller.texas.gov/programs/broadband/outreach/maps/",
            notes="Texas BDO explains map methodology and links to relevant coverage maps.",
        ),
        ProviderEndpoint(
            label="FCC National Broadband Map guidance from Texas BDO",
            url="https://comptroller.texas.gov/programs/broadband/outreach/maps/fcc/",
            notes="Texas BDO guidance for location-level FCC broadband map usage.",
        ),
        ProviderEndpoint(
            label="FCC National Broadband Map",
            url="https://broadbandmap.fcc.gov/home",
            notes="Manual address/location lookup for FCC BDC broadband availability data.",
        ),
        ProviderEndpoint(
            label="FCC Broadband Funding Map",
            url="https://fundingmap.fcc.gov/home",
            notes="Federal broadband infrastructure funding/project context.",
        ),
        ProviderEndpoint(
            label="Texas BEAD Map",
            url="https://register.broadband.texas.gov/award/bead/map",
            notes="Texas BEAD project awards and coverage areas.",
        ),
    ],
    queryable=True,
    update_frequency="Texas BDO describes updates based on FCC BDC cycles and program updates.",
    limitations=BROADBAND_DILIGENCE_LIMITATIONS,
    tags=["broadband", "fiber", "bdo", "texas"],
)
