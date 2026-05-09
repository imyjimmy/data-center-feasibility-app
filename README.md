# Data Center Feasibility App

Monorepo for an Austin/Travis County data center feasibility MVP.

The app is organized into two packages:

- `frontend/`: React + Vite application
- `backend/`: FastAPI application managed with `uv`

## Local Development

Run both apps together:

```sh
make dev
```

Run the API, frontend, and local FastMCP HTTP server together:

```sh
make dev-all
```

The MCP endpoint runs at `http://127.0.0.1:9000/mcp/` by default.

Run a provider-scoped MCP:

```sh
PROVIDER_ID=travis_county_parcels make mcp-provider-dev
```

The root `Makefile` uses global `uv` when available. If `uv` is not installed, it creates an ignored repo-local copy under `.tools/uv`.

### Backend

Install `uv` if needed:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Run the API:

```sh
cd backend
uv sync
uv run fastapi dev app/main.py
```

The API runs at `http://localhost:8000`.

### Frontend

```sh
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`.

Set `VITE_API_BASE_URL` if the backend is running somewhere else.

## Pydantic AI Agent

The implemented delegated analysis flow uses a backend Pydantic AI agent with the local FastMCP
server attached as its MCP toolset.

```sh
PYDANTIC_AI_MODEL=openai:gpt-5.2 make dev-all
```

Create a local `.env` at the repo root:

```sh
cp .env.example .env
```

Then edit `.env` and set `OPENAI_API_KEY`.

When `PYDANTIC_AI_MODEL` is set, `POST /api/analysis-runs` sends the user's request to the
Pydantic AI agent. The agent connects to the FastMCP server at `PYDANTIC_AI_MCP_URL`
(`http://127.0.0.1:9000/mcp` by default), uses its tools for provider research, and returns
structured provider insight updates for the frontend to render. If the agent or model is not
configured, the backend completes with the local provider registry fallback and reports that
orchestration status in the response.

## MCP Agent Test Page

Run the full local stack:

```sh
make dev-all
```

Open `http://localhost:5173/mcp_test`. This page lets you send a freeform prompt directly to
the backend Pydantic AI agent. The agent runs with the configured FastMCP toolset and returns
its summary, provider insights, and tool-call record. The backend endpoint is
`POST /api/mcp-smoke/agent`.

## Make Targets

```sh
make install          # Install backend and frontend dependencies
make dev              # Run FastAPI and Vite together
make dev-all          # Run FastAPI, Vite, and the MCP HTTP server together
make backend-dev      # Run only the FastAPI backend
make frontend-dev     # Run only the Vite frontend
make mcp-dev          # Run only the FastMCP HTTP server
make mcp-provider-dev  # Run one provider MCP; pass PROVIDER_ID=...
make mcp-providers-dev # Run one MCP server per configured provider
make test             # Run backend tests and frontend build
make test-e2e         # Run Playwright end-to-end tests
make test-all         # Run backend, frontend, and Playwright tests
make lint             # Run backend lint checks
```

See `docs/texas-data-providers.md` for the Texas open-data provider catalog.
