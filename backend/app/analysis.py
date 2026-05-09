from datetime import UTC, datetime
from queue import Queue
from threading import Lock
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.providers.models import Concern
from app.providers.registry import get_provider_registry


class AnalysisRunCreate(BaseModel):
    question: str = Field(min_length=1)
    state: str = Field(default="TX", min_length=2, max_length=2)


class ProviderInsight(BaseModel):
    provider_id: str
    provider_name: str
    concern: Concern
    status: str
    summary: str
    source_url: str
    queryable: bool
    limitations: list[str]


class AnalysisRunResponse(BaseModel):
    run_id: str
    status: str
    question: str
    state: str
    created_at: datetime
    updated_at: datetime
    provider_insights: list[ProviderInsight]


class _AnalysisRun:
    def __init__(self, question: str, state: str) -> None:
        now = datetime.now(UTC)
        self.run_id = str(uuid4())
        self.status = "queued"
        self.question = question
        self.state = state
        self.created_at = now
        self.updated_at = now
        self.provider_insights: list[ProviderInsight] = []

    def response(self) -> AnalysisRunResponse:
        return AnalysisRunResponse(
            run_id=self.run_id,
            status=self.status,
            question=self.question,
            state=self.state,
            created_at=self.created_at,
            updated_at=self.updated_at,
            provider_insights=self.provider_insights,
        )


class AnalysisRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, _AnalysisRun] = {}
        self._lock = Lock()

    def create(self, request: AnalysisRunCreate) -> AnalysisRunResponse:
        run = _AnalysisRun(question=request.question, state=request.state.upper())
        with self._lock:
            self._runs[run.run_id] = run
        return run.response()

    def get(self, run_id: str) -> AnalysisRunResponse:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            return run.response()

    def complete(self, run_id: str, insights: list[ProviderInsight]) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "complete"
            run.provider_insights = insights
            run.updated_at = datetime.now(UTC)

    def fail(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "failed"
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
            except Exception:
                self._store.fail(run_id)
            finally:
                self._queue.task_done()


analysis_store = AnalysisRunStore()
analysis_worker = AnalysisWorker(analysis_store)
router = APIRouter(prefix="/api/analysis-runs", tags=["analysis"])


def build_provider_insights(run_id: str) -> None:
    run = analysis_store.get(run_id)
    registry = get_provider_registry()
    providers = registry.list(state=run.state)
    insights = [
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
    analysis_store.complete(run_id, insights)


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
