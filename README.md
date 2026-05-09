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

## OpenClaw Gateway

The repo includes an OpenClaw gateway via Docker Compose. It runs on port `18789`.

### Prerequisites

- Docker and Docker Compose installed and running

### First-time setup

Optionally pin a specific image version:

```sh
export OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:2026.2.26
```

Then run onboarding (pulls the image and configures the gateway):

```sh
make openclaw-setup
```

The setup command prints a dashboard URL with an auth token:

```
Dashboard: http://localhost:18789/#token=<token>
```

### Day-to-day

```sh
make openclaw-up      # Start the gateway (detached)
make openclaw-down    # Stop all OpenClaw services
make openclaw-logs    # Tail gateway logs
```

### Local AI providers

If you run a local model server, use the Docker-internal host instead of `localhost`:

| Provider | URL |
|----------|-----|
| Ollama | `http://host.docker.internal:11434` |
| LM Studio | `http://host.docker.internal:1234` |

The provider must bind to `0.0.0.0` (not `127.0.0.1`) to be reachable from within the container.

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

make openclaw-setup   # Pull image and run onboarding (first-time)
make openclaw-up      # Start the OpenClaw gateway
make openclaw-down    # Stop OpenClaw services
make openclaw-logs    # Tail OpenClaw gateway logs
```

See `docs/texas-data-providers.md` for the Texas open-data provider catalog.
