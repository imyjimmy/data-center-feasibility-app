from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.analysis import router as analysis_router
from app.mcp_smoke import router as mcp_smoke_router
from app.providers.api import router as providers_router

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(APP_DIR / ".env", override=True)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ProjectQuestionResponse(BaseModel):
    question: str
    scope: str
    caveat: str


app = FastAPI(
    title="Data Center Feasibility API",
    version="0.1.0",
    summary="APIs for screening Austin-area parcels for data center diligence.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(providers_router)
app.include_router(analysis_router)
app.include_router(mcp_smoke_router)


@app.get("/health", response_model=HealthResponse, operation_id="get_service_health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="data-center-feasibility-backend",
        version=app.version,
    )


@app.get(
    "/api/project-question",
    response_model=ProjectQuestionResponse,
    operation_id="get_project_question",
)
def project_question() -> ProjectQuestionResponse:
    return ProjectQuestionResponse(
        question="Is this parcel worth a first utility/fiber diligence call for a 25 MW edge data center?",
        scope="Austin/Travis County public-data parcel screening",
        caveat="Public data can screen likely blockers, but cannot prove private utility capacity or fiber availability.",
    )
