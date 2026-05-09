# Provider and MCP Integration Notes

This app now separates provider integration into three layers:

1. Provider catalog and query adapters in FastAPI.
2. Background analysis runs that collect provider context server-side.
3. FastMCP exposure of the FastAPI API for agent integrations.

The frontend only calls FastAPI. It does not call MCP servers directly.

## Backend Structure

Provider code lives under `backend/app/providers/`.

- `models.py`: Pydantic models for provider metadata, capabilities, coverage, query requests, and query responses.
- `texas.py`: Texas-first open-data provider catalog.
- `registry.py`: Provider registry used by API routes and analysis runs.
- `client.py`: Small async HTTP client wrapper for provider calls.
- `api.py`: FastAPI routes under `/api/providers`.

Background analysis lives in `backend/app/analysis.py`.

- `POST /api/analysis-runs` creates an analysis run and schedules provider-context aggregation with FastAPI `BackgroundTasks`.
- `GET /api/analysis-runs/{run_id}` returns run status and provider insights.
- The current implementation uses an in-memory store. Replace it with a database or job queue before multi-worker or production deployment.

FastMCP exposure lives in `backend/app/mcp.py` and `backend/app/provider_mcp.py`.

- It wraps the existing FastAPI app with `FastMCP.from_fastapi(...)`.
- Local HTTP transport defaults to `127.0.0.1:9000`.
- The MCP endpoint is available at `http://127.0.0.1:9000/mcp/`.
- Setting `PROVIDER_ID` starts a provider-scoped MCP instead of the full-app MCP.
- Provider-scoped MCPs expose `provider_metadata`, `provider_health`, and `query_provider` tools.

## Provider Catalog

The current catalog is Texas-only and uses public/open government sources where practical.

Live-queryable providers:

- `austin_water_utility_service_area`: City of Austin ArcGIS FeatureServer.
- `travis_county_parcels`: Travis County parcel ArcGIS FeatureServer.

Metadata-safe providers:

- `ercot_market_data_transparency`: ERCOT market data hub; report-specific API endpoints still need to be pinned.
- `twdb_water_data_for_texas`: TWDB water data portal; dataset-specific API endpoints still need to be pinned.
- `texas_broadband_development_map`: Texas BDO broadband map documentation. Texas BDO notes granular FCC-derived map data cannot be downloaded from the Texas map due to FCC restrictions.
- `texas_real_estate_research_center`: ICP/commercial real-estate context source category.
- `txgio_geospatial_catalog`: Texas geospatial/open-data catalog source category for parcel/geocoding inputs.

Every provider can be queried through FastAPI and its provider MCP. If the source is not yet a pinned machine-queryable endpoint, the query returns a structured metadata response with source URLs and limitations rather than raising an error.

Add another provider by appending a `DataProviderDefinition` in a state catalog module, then registering that module through `ProviderRegistry`.

## Frontend Flow

The `Go` button starts a FastAPI analysis run:

```text
React -> POST /api/analysis-runs
React -> GET /api/analysis-runs/{run_id} until complete
FastAPI worker thread -> provider registry -> provider insights
```

Provider results render in the detail inspector as “Open Data Provider Signals”.
This keeps browser code decoupled from MCP and provider-specific APIs.

The current worker is a daemon thread backed by an in-memory queue and store. It is suitable for local development and tests. For production, replace it with a durable queue and persistent run store.

## Local Execution

Run API, frontend, and the FastMCP HTTP server:

```sh
make dev
```

Run only API and frontend without MCP:

```sh
make dev-web
```

Run only the MCP server:

```sh
make mcp-dev
```

Run one provider-scoped MCP:

```sh
PROVIDER_ID=travis_county_parcels make mcp-provider-dev
```

Run one MCP server per configured provider:

```sh
make mcp-providers-dev
```

Default local URLs:

- FastAPI: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- FastMCP: `http://127.0.0.1:9000/mcp/`
- Provider MCPs from `make mcp-providers-dev`: `http://127.0.0.1:9100/mcp/` and above

## Tests

Backend tests cover:

- Provider registry filtering.
- Provider API listing and metadata-safe query responses.
- ArcGIS query parameter generation with mocked outbound HTTP.
- Background analysis-run population of provider insights.
- Provider-scoped MCP creation.

Frontend E2E tests live in `frontend/tests/e2e/`.

The Playwright flow starts the backend and Vite dev server, submits a feasibility question, opens parcel results, selects a parcel, and verifies background provider signals appear. It verifies the frontend observes provider context through FastAPI, not through a direct MCP call.

CI is defined in `.github/workflows/ci.yml` and is structured so additional backend, frontend, or E2E tests can be added without changing the basic workflow shape.
