from datetime import UTC, datetime
from queue import Queue
from threading import Lock
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.pydantic_agent import (
    PydanticAgentResearchError,
    pydantic_agent_is_configured,
    research_with_pydantic_agent,
)
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


class AnalysisOrchestration(BaseModel):
    status: str
    detail: str | None = None
    tool_calls: list[str] = Field(default_factory=list)


class AnalysisRunResponse(BaseModel):
    run_id: str
    status: str
    question: str
    state: str
    created_at: datetime
    updated_at: datetime
    provider_insights: list[ProviderInsight]
    agent_summary: str | None = None
    orchestration: AnalysisOrchestration


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
            created_at=self.created_at,
            updated_at=self.updated_at,
            provider_insights=self.provider_insights,
            agent_summary=self.agent_summary,
            orchestration=self.orchestration,
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

    def complete(
        self,
        run_id: str,
        insights: list[ProviderInsight],
        orchestration: AnalysisOrchestration,
        agent_summary: str | None = None,
    ) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "complete"
            run.provider_insights = insights
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


def build_provider_insights(run_id: str) -> None:
    run = analysis_store.get(run_id)
    insights = _base_provider_insights(run.state)

    if not pydantic_agent_is_configured():
        analysis_store.complete(
            run_id,
            insights,
            orchestration=AnalysisOrchestration(
                status="agent_skipped",
                detail="Pydantic AI model is not configured; used backend provider registry.",
            ),
        )
        return

    try:
        agent_result = research_with_pydantic_agent(
            question=run.question,
            state=run.state,
            run_id=run.run_id,
        )
    except PydanticAgentResearchError as exc:
        analysis_store.complete(
            run_id,
            insights,
            orchestration=AnalysisOrchestration(
                status="agent_failed",
                detail=f"Pydantic AI research failed; used backend provider registry. {exc}",
            ),
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
