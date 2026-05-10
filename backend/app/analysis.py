import asyncio
import json
from datetime import UTC, datetime
from queue import Queue
from threading import Lock
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.mcp_smoke import McpProviderSmokeResult
from app.pydantic_agent import (
    PydanticAgentResearchError,
    pydantic_agent_is_configured,
    research_with_pydantic_agent,
)
from app.providers.client import ProviderHttpClient
from app.providers.models import Concern, ProviderQueryRequest
from app.providers.registry import get_provider_registry
from app.providers.service import query_provider_data
from app.providers.texas_sources.travis_parcels import (
    build_travis_parcel_area_search_request,
    build_travis_parcel_site_request,
)


class AnalysisRunCreate(BaseModel):
    question: str = Field(min_length=1)
    state: str = Field(default="TX", min_length=2, max_length=2)
    site_context: str | None = Field(default=None, max_length=240)


class ProviderInsight(BaseModel):
    provider_id: str
    provider_name: str
    concern: Concern
    status: str
    summary: str
    source_url: str
    queryable: bool
    limitations: list[str]


class AnalysisOrchestration(BaseModel):
    status: str
    detail: str | None = None
    tool_calls: list[str] = Field(default_factory=list)


class ParcelScoreBreakdown(BaseModel):
    power: int
    water: int
    site: int
    constraints: int
    market: int


class ParcelCandidate(BaseModel):
    rank: int
    id: str
    name: str
    jurisdiction: str
    acres: float
    score: int
    zoning: str
    zoningFit: str
    landUse: str
    firstBlocker: str
    electricService: str
    waterService: str
    roadAccess: str
    roadAccessType: str
    distanceToSubstation: float
    fiberConfidence: str
    floodplain: bool
    wetlands: bool
    coolingModes: list[str]
    center: list[float]
    mapRadius: float
    evidence: list[str]
    scoreBreakdown: ParcelScoreBreakdown
    imageUrl: str | None = None


class AnalysisRunResponse(BaseModel):
    run_id: str
    status: str
    question: str
    state: str
    site_context: str | None = None
    created_at: datetime
    updated_at: datetime
    provider_insights: list[ProviderInsight]
    candidate_parcels: list[ParcelCandidate] = Field(default_factory=list)
    agent_summary: str | None = None
    orchestration: AnalysisOrchestration


class _AnalysisRun:
    def __init__(self, question: str, state: str, site_context: str | None = None) -> None:
        now = datetime.now(UTC)
        self.run_id = str(uuid4())
        self.status = "queued"
        self.question = question
        self.state = state
        self.site_context = site_context
        self.created_at = now
        self.updated_at = now
        self.provider_insights: list[ProviderInsight] = []
        self.candidate_parcels: list[ParcelCandidate] = []
        self.agent_summary: str | None = None
        self.orchestration = AnalysisOrchestration(
            status="queued",
            detail="Analysis run is waiting for the backend worker.",
        )

    def response(self) -> AnalysisRunResponse:
        return AnalysisRunResponse(
            run_id=self.run_id,
            status=self.status,
            question=self.question,
            state=self.state,
            site_context=self.site_context,
            created_at=self.created_at,
            updated_at=self.updated_at,
            provider_insights=self.provider_insights,
            candidate_parcels=self.candidate_parcels,
            agent_summary=self.agent_summary,
            orchestration=self.orchestration,
        )


class AnalysisRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, _AnalysisRun] = {}
        self._lock = Lock()

    def create(self, request: AnalysisRunCreate) -> AnalysisRunResponse:
        run = _AnalysisRun(
            question=request.question,
            state=request.state.upper(),
            site_context=request.site_context,
        )
        with self._lock:
            self._runs[run.run_id] = run
        return run.response()

    def get(self, run_id: str) -> AnalysisRunResponse:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            return run.response()

    def complete(
        self,
        run_id: str,
        insights: list[ProviderInsight],
        orchestration: AnalysisOrchestration,
        agent_summary: str | None = None,
        candidate_parcels: list[ParcelCandidate] | None = None,
    ) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "complete"
            run.provider_insights = insights
            run.candidate_parcels = candidate_parcels or []
            run.agent_summary = agent_summary
            run.orchestration = orchestration
            run.updated_at = datetime.now(UTC)

    def fail(self, run_id: str, detail: str | None = None) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "failed"
            run.orchestration = AnalysisOrchestration(status="failed", detail=detail)
            run.updated_at = datetime.now(UTC)


class AnalysisWorker:
    def __init__(self, store: AnalysisRunStore) -> None:
        self._store = store
        self._queue: Queue[str] = Queue()
        self._thread = Thread(target=self._work, name="analysis-provider-worker", daemon=True)
        self._thread.start()

    def submit(self, run_id: str) -> None:
        self._queue.put(run_id)

    def _work(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                build_provider_insights(run_id)
            except Exception as exc:
                self._store.fail(run_id, detail=str(exc))
            finally:
                self._queue.task_done()


analysis_store = AnalysisRunStore()
analysis_worker = AnalysisWorker(analysis_store)
router = APIRouter(prefix="/api/analysis-runs", tags=["analysis"])


def _base_provider_insights(state: str) -> list[ProviderInsight]:
    registry = get_provider_registry()
    providers = registry.list(state=state)
    return [
        ProviderInsight(
            provider_id=provider.id,
            provider_name=provider.name,
            concern=provider.concern,
            status="queryable" if provider.queryable else "metadata_only",
            summary=provider.description,
            source_url=str(provider.source_homepage),
            queryable=provider.queryable,
            limitations=provider.limitations[:2],
        )
        for provider in providers
    ]


def _merge_agent_insights(
    base_insights: list[ProviderInsight],
    agent_insights: list[dict],
) -> list[ProviderInsight]:
    base_by_id = {insight.provider_id: insight for insight in base_insights}

    for update in agent_insights:
        if not isinstance(update, dict):
            continue
        provider_id = update.get("provider_id")
        if not isinstance(provider_id, str) or provider_id not in base_by_id:
            continue

        current = base_by_id[provider_id]
        limitations = update.get("limitations", current.limitations)
        if not isinstance(limitations, list):
            limitations = current.limitations

        base_by_id[provider_id] = current.model_copy(
            update={
                "status": update.get("status") or current.status,
                "summary": update.get("summary") or current.summary,
                "limitations": [str(item) for item in limitations[:2]],
            }
        )

    return [base_by_id[insight.provider_id] for insight in base_insights]


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _first_value(*values: object) -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _parcel_acres(attrs: dict[str, object]) -> float | None:
    return _float_value(
        _first_value(attrs.get("GIS_acres"), attrs.get("tcad_acres"), attrs.get("ACRES"))
    )


def _parcel_attributes(provider: McpProviderSmokeResult) -> dict[str, object]:
    if provider.sample_attributes:
        return provider.sample_attributes

    for feature in _as_list(provider.data_preview.get("features")):
        attributes = _as_dict(_as_dict(feature).get("attributes"))
        if attributes:
            return attributes

    if provider.geo_features:
        return provider.geo_features[0].attributes

    return {}


def _feature_attributes(feature: object) -> dict[str, object]:
    return _as_dict(_as_dict(feature).get("attributes"))


def _feature_center(feature: object) -> list[float] | None:
    geometry = _as_dict(_as_dict(feature).get("geometry"))
    points: list[list[float]] = []

    for ring in _as_list(geometry.get("rings")):
        for coordinate in _as_list(ring):
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            lon, lat = coordinate[0], coordinate[1]
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                points.append([float(lat), float(lon)])

    if points:
        return [
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        ]

    x = geometry.get("x")
    y = geometry.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return [float(y), float(x)]

    return None


def _parcel_features(provider: McpProviderSmokeResult) -> list[tuple[dict[str, object], list[float] | None]]:
    features = _as_list(provider.data_preview.get("features"))
    if features:
        return [(_feature_attributes(feature), _feature_center(feature)) for feature in features]

    attrs = _parcel_attributes(provider)
    center = _geo_feature_center(provider)
    return [(attrs, center)] if attrs else []


def _geo_feature_center(provider: McpProviderSmokeResult) -> list[float] | None:
    for feature in provider.geo_features:
        if feature.point:
            return [feature.point[0], feature.point[1]]

        points = [point for ring in feature.rings for point in ring]
        if points:
            lat = sum(point[0] for point in points) / len(points)
            lng = sum(point[1] for point in points) / len(points)
            return [lat, lng]

    return None


def _score_breakdown(acres: float, has_geometry: bool) -> ParcelScoreBreakdown:
    site = 20 if acres >= 25 else 12 if acres >= 5 else 4
    constraints = 14 if has_geometry else 8
    power = 10 if acres >= 25 else 6
    water = 8
    market = 5
    return ParcelScoreBreakdown(
        power=power,
        water=water,
        site=site,
        constraints=constraints,
        market=market,
    )


def _parcel_candidate_from_attrs(
    *,
    attrs: dict[str, object],
    center: list[float],
    rank: int,
    has_geometry: bool,
) -> ParcelCandidate | None:
    acres = _parcel_acres(attrs)
    if acres is None:
        return None

    parcel_id = str(
        _first_value(attrs.get("PROP_ID"), attrs.get("prop_id"), attrs.get("OBJECTID"))
        or f"rank-{rank}"
    )
    address = str(_first_value(attrs.get("situs_address"), attrs.get("SITEADDRESS")) or "Travis parcel match")
    owner = _first_value(attrs.get("py_owner_name"), attrs.get("OWNER_NAME"))
    land_use = str(_first_value(attrs.get("land_type_desc"), attrs.get("legal_desc")) or "Parcel land-use not returned")

    breakdown = _score_breakdown(acres=acres, has_geometry=has_geometry)
    score = breakdown.power + breakdown.water + breakdown.site + breakdown.constraints + breakdown.market
    first_blocker = "Parcel Scale" if acres < 25 else "Power Interconnection"

    evidence_lines = [
        f"MCP Travis County parcel search returned PROP_ID {parcel_id}.",
        f"Parcel acreage from GIS/appraisal attributes: {acres:g} acres.",
        "Within configured Austin-area Travis County parcel search envelope.",
    ]
    if owner:
        evidence_lines.append(f"Owner attribute returned: {owner}.")

    return ParcelCandidate(
        rank=rank,
        id=f"TRAVIS-{parcel_id}",
        name=address,
        jurisdiction="Travis County / Austin-area evidence",
        acres=round(acres, 4),
        score=score,
        zoning="Zoning not returned by configured MCP evidence",
        zoningFit="review",
        landUse=land_use,
        firstBlocker=first_blocker,
        electricService="Utility/TSP not returned by configured MCP evidence",
        waterService="Service area/capacity requires provider evidence",
        roadAccess="Not returned by configured MCP evidence",
        roadAccessType="any",
        distanceToSubstation=99.0,
        fiberConfidence="low",
        floodplain=False,
        wetlands=False,
        coolingModes=["air"],
        center=center,
        mapRadius=0.003 if acres < 5 else 0.012,
        evidence=evidence_lines,
        scoreBreakdown=breakdown,
    )


def _candidate_point_bbox(center: list[float], delta: float = 0.001) -> str:
    lat, lon = center
    return f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"


def _provider_features(data: dict[str, object]) -> list[dict[str, object]]:
    return [
        feature
        for feature in _as_list(data.get("features"))
        if isinstance(feature, dict)
    ]


def _first_feature_attrs(data: dict[str, object]) -> dict[str, object]:
    for feature in _provider_features(data):
        attrs = _as_dict(feature.get("attributes"))
        if attrs:
            return attrs
    return {}


def _first_text_attr(attrs: dict[str, object], names: tuple[str, ...]) -> str | None:
    lowered = {key.lower(): value for key, value in attrs.items()}
    for name in names:
        value = attrs.get(name)
        if value not in (None, ""):
            return str(value)
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value)
    for key, value in attrs.items():
        key_lower = key.lower()
        if any(name.lower() in key_lower for name in names) and value not in (None, ""):
            return str(value)
    return None


async def _query_provider_safely(
    provider_id: str,
    request: ProviderQueryRequest,
    *,
    timeout: float = 6.0,
) -> dict[str, object]:
    try:
        provider = get_provider_registry().get(provider_id)
        response = await query_provider_data(
            provider=provider,
            request=request,
            http_client=ProviderHttpClient(timeout=timeout),
        )
        return response.data
    except Exception:
        return {}


async def _enrich_candidate(candidate: ParcelCandidate) -> ParcelCandidate:
    bbox = _candidate_point_bbox(candidate.center)
    broad_bbox = _candidate_point_bbox(candidate.center, delta=0.05)
    lat, lon = candidate.center

    zoning_data, jurisdiction_data, water_data, energy_data, transmission_data, broadband_data = await asyncio.gather(
        _query_provider_safely(
            "austin_zoning",
            ProviderQueryRequest(
                out_fields="*",
                limit=3,
                return_geometry=False,
                bbox=bbox,
                params={"inSR": 4326, "outSR": 4326},
            ),
        ),
        _query_provider_safely(
            "austin_jurisdiction",
            ProviderQueryRequest(
                out_fields="*",
                limit=3,
                return_geometry=False,
                bbox=bbox,
                params={"inSR": 4326, "outSR": 4326},
            ),
        ),
        _query_provider_safely(
            "austin_water_utility_service_area",
            ProviderQueryRequest(
                out_fields="*",
                limit=3,
                return_geometry=False,
                bbox=bbox,
                params={"inSR": 4326, "outSR": 4326},
            ),
        ),
        _query_provider_safely(
            "austin_energy_service_area",
            ProviderQueryRequest(
                out_fields="*",
                limit=3,
                return_geometry=False,
                bbox=bbox,
                params={"inSR": 4326, "outSR": 4326},
            ),
        ),
        _query_provider_safely(
            "electric_power_transmission_lines",
            ProviderQueryRequest(
                out_fields="*",
                limit=5,
                return_geometry=False,
                bbox=broad_bbox,
                params={"inSR": 4326, "outSR": 4326},
            ),
        ),
        _query_provider_safely(
            "texas_broadband_development_map",
            ProviderQueryRequest(
                limit=1,
                return_geometry=False,
                params={"lat": lat, "lng": lon, "service_type": "business"},
            ),
        ),
    )

    update: dict[str, object] = {}
    evidence = list(candidate.evidence)

    zoning_attrs = _first_feature_attrs(zoning_data)
    zoning = _first_text_attr(
        zoning_attrs,
        ("zoning", "zoning_zty", "zoning_label", "zone", "base_zone", "zoningtext", "zoning_text"),
    )
    if zoning:
        update["zoning"] = zoning
        update["zoningFit"] = "industrial" if any(token in zoning.upper() for token in ("LI", "MI", "IP", "IND")) else "review"
        evidence.append(f"City of Austin zoning intersect at parcel centroid returned: {zoning}.")

    jurisdiction_attrs = _first_feature_attrs(jurisdiction_data)
    jurisdiction = _first_text_attr(
        jurisdiction_attrs,
        ("jurisdiction", "jurisdict", "juris", "type", "name", "description"),
    )
    if jurisdiction:
        update["jurisdiction"] = jurisdiction
        evidence.append(f"City of Austin jurisdiction/ETJ intersect returned: {jurisdiction}.")

    water_count = len(_provider_features(water_data))
    if water_count > 0:
        update["waterService"] = "Austin Water service-area intersect"
        evidence.append("Austin Water service-area boundary intersects the parcel centroid.")

    energy_count = len(_provider_features(energy_data))
    if energy_count > 0:
        update["electricService"] = "Austin Energy service-area intersect"
        evidence.append("Austin Energy service-area boundary intersects the parcel centroid.")

    transmission_count = len(_provider_features(transmission_data))
    if transmission_count > 0:
        update["distanceToSubstation"] = 3.0
        evidence.append(f"Public transmission-line screen returned {transmission_count} feature(s) within roughly 3 miles.")

    broadband_summary = _as_dict(broadband_data.get("summary"))
    fiber_count = broadband_summary.get("fiber_provider_count")
    if isinstance(fiber_count, int):
        update["fiberConfidence"] = "high" if fiber_count >= 3 else "medium" if fiber_count > 0 else "low"
        evidence.append(f"Broadband location lookup at parcel centroid returned {fiber_count} fiber provider signal(s).")

    if update:
        update["evidence"] = evidence
        breakdown = candidate.scoreBreakdown.model_copy()
        if "electricService" in update or transmission_count > 0:
            breakdown.power = min(25, breakdown.power + 4)
        if "waterService" in update:
            breakdown.water = min(25, breakdown.water + 4)
        if "zoning" in update and update.get("zoningFit") == "industrial":
            breakdown.constraints = min(25, breakdown.constraints + 3)
        if "fiberConfidence" in update and update["fiberConfidence"] != "low":
            breakdown.market = min(15, breakdown.market + 2)
        update["scoreBreakdown"] = breakdown
        update["score"] = breakdown.power + breakdown.water + breakdown.site + breakdown.constraints + breakdown.market

    return candidate.model_copy(update=update)


async def _enrich_candidates(candidates: list[ParcelCandidate]) -> list[ParcelCandidate]:
    enriched = await asyncio.gather(*(_enrich_candidate(candidate) for candidate in candidates[:10]))
    enriched_list = list(enriched)
    enriched_list.sort(key=lambda candidate: (candidate.score, candidate.acres), reverse=True)
    for index, candidate in enumerate(enriched_list, start=1):
        candidate.rank = index
    return enriched_list


def _candidate_research_context(candidates: list[ParcelCandidate]) -> str:
    if not candidates:
        return "No backend parcel candidates were collected before agent research."

    rows = [
        {
            "rank": candidate.rank,
            "id": candidate.id,
            "name": candidate.name,
            "jurisdiction": candidate.jurisdiction,
            "acres": candidate.acres,
            "score": candidate.score,
            "zoning": candidate.zoning,
            "zoning_fit": candidate.zoningFit,
            "land_use": candidate.landUse,
            "first_blocker": candidate.firstBlocker,
            "electric_service": candidate.electricService,
            "water_service": candidate.waterService,
            "distance_to_substation_or_transmission_proxy": candidate.distanceToSubstation,
            "fiber_confidence": candidate.fiberConfidence,
            "evidence": candidate.evidence[:8],
        }
        for candidate in candidates[:10]
    ]
    return json.dumps(rows, indent=2)


def _build_candidate_parcels(evidence: list[McpProviderSmokeResult]) -> list[ParcelCandidate]:
    parcel_provider = next(
        (
            provider
            for provider in evidence
            if provider.provider_id == "travis_county_parcels" and (provider.feature_count or 0) > 0
        ),
        None,
    )
    if parcel_provider is None:
        return []

    candidates: list[ParcelCandidate] = []
    for attrs, center in _parcel_features(parcel_provider):
        if center is None:
            continue
        candidate = _parcel_candidate_from_attrs(
            attrs=attrs,
            center=center,
            rank=1,
            has_geometry=True,
        )
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(key=lambda candidate: (candidate.score, candidate.acres), reverse=True)
    for index, candidate in enumerate(candidates[:10], start=1):
        candidate.rank = index
    return candidates[:10]


async def _collect_candidate_parcels(state: str, site_context: str) -> list[ParcelCandidate]:
    if state.upper() != "TX":
        return []

    request = build_travis_parcel_site_request(site_context, limit=10)
    if request is None:
        request = build_travis_parcel_area_search_request(site_context, min_acres=25, limit=25)
    if request is None:
        return []

    provider = get_provider_registry().get("travis_county_parcels")
    response = await query_provider_data(
        provider=provider,
        request=request,
        http_client=ProviderHttpClient(timeout=8.0),
    )
    data = response.data
    features = _as_list(data.get("features"))
    provider_result = McpProviderSmokeResult(
        provider_id=provider.id,
        provider_name=provider.name,
        queryable=True,
        source="live_query",
        query_scope="area_parcel_search" if request.bbox else "site_address_filter",
        query_status="returned",
        request_url=str(response.request_url),
        request_params=response.request_params,
        data_preview=data,
        feature_count=len(features),
    )
    candidates = _build_candidate_parcels([provider_result])
    return await _enrich_candidates(candidates)


def build_provider_insights(run_id: str) -> None:
    run = analysis_store.get(run_id)
    insights = _base_provider_insights(run.state)
    site_context = run.site_context or run.question

    try:
        candidate_parcels = asyncio.run(_collect_candidate_parcels(state=run.state, site_context=site_context))
    except Exception:
        candidate_parcels = []

    if not pydantic_agent_is_configured():
        analysis_store.complete(
            run_id,
            insights,
            orchestration=AnalysisOrchestration(
                status="agent_skipped",
                detail="Pydantic AI model is not configured; used backend provider registry.",
            ),
            candidate_parcels=candidate_parcels,
        )
        return

    try:
        agent_result = research_with_pydantic_agent(
            question=run.question,
            state=run.state,
            run_id=run.run_id,
            site_context=site_context,
            candidate_context=_candidate_research_context(candidate_parcels),
        )
    except PydanticAgentResearchError as exc:
        analysis_store.complete(
            run_id,
            insights,
            orchestration=AnalysisOrchestration(
                status="agent_failed",
                detail=f"Pydantic AI research failed; used backend provider registry. {exc}",
            ),
            candidate_parcels=candidate_parcels,
        )
        return

    analysis_store.complete(
        run_id,
        _merge_agent_insights(insights, agent_result.provider_insights),
        orchestration=AnalysisOrchestration(
            status="agent_complete",
            detail="Pydantic AI completed delegated MCP research and returned backend data updates.",
            tool_calls=agent_result.tool_calls,
        ),
        agent_summary=agent_result.summary,
        candidate_parcels=candidate_parcels,
    )


@router.post(
    "",
    response_model=AnalysisRunResponse,
    operation_id="start_feasibility_analysis_run",
    summary="Start a background feasibility analysis run",
)
def start_analysis_run(
    request: AnalysisRunCreate,
) -> AnalysisRunResponse:
    run = analysis_store.create(request)
    analysis_worker.submit(run.run_id)
    return run


@router.get(
    "/{run_id}",
    response_model=AnalysisRunResponse,
    operation_id="get_feasibility_analysis_run",
    summary="Get a feasibility analysis run and provider context",
)
def get_analysis_run(run_id: str) -> AnalysisRunResponse:
    try:
        return analysis_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown analysis run: {run_id}") from exc
