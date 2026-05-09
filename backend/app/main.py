import os
from typing import Any

import httpx
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.analysis import router as analysis_router
from app.providers.api import router as providers_router

OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
OPENCLAW_GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ProjectQuestionResponse(BaseModel):
    question: str
    scope: str
    caveat: str


class OpenClawRequest(BaseModel):
    model: str = "openclaw"
    input: str | list[Any]
    instructions: str | None = None
    tools: list[Any] | None = None
    tool_choice: Any | None = None
    stream: bool = False
    max_output_tokens: int | None = None
    user: str | None = None
    previous_response_id: str | None = None


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


def _openclaw_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {OPENCLAW_GATEWAY_TOKEN}"}


@app.get("/api/openclaw/models")
async def openclaw_models():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{OPENCLAW_GATEWAY_URL}/v1/models",
            headers=_openclaw_headers(),
            timeout=30.0,
        )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@app.post("/api/openclaw/responses")
async def openclaw_responses(body: OpenClawRequest):
    headers = {**_openclaw_headers(), "Content-Type": "application/json"}
    payload = body.model_dump(exclude_none=True)

    if body.stream:

        async def stream_response():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{OPENCLAW_GATEWAY_URL}/v1/responses",
                    json=payload,
                    headers=headers,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(stream_response(), media_type="text/event-stream")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{OPENCLAW_GATEWAY_URL}/v1/responses",
            json=payload,
            headers=headers,
            timeout=120.0,
        )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )
