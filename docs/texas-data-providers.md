# Texas Open Data Providers

This catalog maps feasibility concerns to Texas-first public data sources. The
backend exposes the same catalog at `GET /api/providers`; every provider can be
called through `POST /api/providers/{provider_id}/query`.

For live-queryable ArcGIS providers, query calls reach the public FeatureServer.
For metadata-safe providers whose machine endpoint is not pinned yet, query
calls return structured source metadata and known limitations.

## Provider Categories

| Concern | Provider | Current integration | Source |
| --- | --- | --- | --- |
| Power stress | ERCOT Market Data Transparency | Metadata-safe until report-specific public API endpoints are pinned | https://www.ercot.com/services/mdt/data-portal |
| Water | Austin Water Utility Service Area | Queryable ArcGIS FeatureServer | https://www.arcgis.com/home/item.html?id=da0a5e49a603496c9272a92233981c1b |
| Water | TWDB Water Data for Texas | Metadata-safe until dataset-specific API endpoints are pinned | https://www.waterdatafortexas.org/ |
| Fiber availability | Texas Broadband Development Map | Metadata-safe; Texas BDO notes granular map data cannot be downloaded due to FCC restrictions | https://comptroller.texas.gov/programs/broadband/outreach/maps/ |
| Zoning / parcels | Travis County Parcels | Queryable ArcGIS FeatureServer | https://taxmaps.traviscountytx.gov/arcgis/rest/services/Parcels/FeatureServer |
| ICP / real-estate context | Texas Real Estate Research Center | Metadata-safe contact/source category | https://trerc.tamu.edu/ |
| Parcel/geocoding | Texas Geographic Information Office and Texas Open Data Portal | Metadata-safe catalog source category | https://tnris.org/about.html |

## Local Execution

Run the API and frontend:

```sh
make dev
```

Run the API, frontend, and FastMCP HTTP server:

```sh
make dev-all
```

Local URLs:

- FastAPI: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- FastMCP HTTP endpoint: `http://127.0.0.1:9000/mcp/`

Run only the MCP server:

```sh
make mcp-dev
```

Run a provider-scoped MCP:

```sh
PROVIDER_ID=austin_water_utility_service_area make mcp-provider-dev
```

Run all provider-scoped MCPs:

```sh
make mcp-providers-dev
```

## Extension Pattern

Add new states or providers by creating another provider catalog module under
`backend/app/providers/` and registering it through `ProviderRegistry`. Keep
provider definitions declarative: concern, coverage, owner, source homepage,
endpoints, capabilities, limitations, and whether the source is directly
queryable.

Provider query tests should mock outbound HTTP. CI intentionally runs backend
tests without live public-data calls so source outages do not block unrelated
application work.
