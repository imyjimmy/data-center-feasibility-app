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

## Make Targets

```sh
make install
make dev
make backend-dev
make frontend-dev
make mcp-dev
make mcp-provider-dev
make mcp-providers-dev
make test
make test-e2e
make test-all
make lint
```

See `docs/texas-data-providers.md` for the Texas open-data provider catalog.
