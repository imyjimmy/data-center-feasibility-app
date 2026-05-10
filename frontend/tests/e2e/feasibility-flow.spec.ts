import { expect, test } from "@playwright/test";

test("submits a feasibility question and displays background provider signals", async ({ page }) => {
  await page.route("**/api/analysis-runs", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        run_id: "e2e-analysis-run",
        status: "complete",
        question: "Find Austin-area parcels with power stress, water service, fiber, zoning, and parcel context.",
        state: "TX",
        site_context: "Find Austin-area parcels with power stress, water service, fiber, zoning, and parcel context.",
        created_at: "2026-05-10T00:00:00Z",
        updated_at: "2026-05-10T00:00:01Z",
        provider_insights: [
          {
            provider_id: "travis_county_parcels",
            provider_name: "Travis County Parcels",
            concern: "zoning",
            status: "returned",
            summary: "Parcel provider returned evidence-backed candidates for the requested Austin-area screen.",
            source_url: "https://example.test/FeatureServer/0",
            queryable: true,
            limitations: ["Entitlements still require confirmation."],
          },
        ],
        candidate_parcels: [
          {
            rank: 1,
            id: "TCAD-031908",
            name: "Hutto - CR 110",
            jurisdiction: "Travis / Williamson edge",
            acres: 63.4,
            score: 81,
            zoning: "ETJ review",
            zoningFit: "review",
            landUse: "Agricultural / undeveloped",
            firstBlocker: "Water Capacity",
            electricService: "Oncor",
            waterService: "Jonah SUD",
            roadAccess: "Arterial",
            roadAccessType: "arterial",
            distanceToSubstation: 8.6,
            fiberConfidence: "medium",
            floodplain: false,
            wetlands: false,
            coolingModes: ["air", "hybrid", "liquid"],
            center: [30.548, -97.551],
            mapRadius: 0.022,
            evidence: ["Large contiguous acreage", "Good highway proximity", "Utility territory needs call"],
            scoreBreakdown: { power: 16, water: 16, site: 20, constraints: 19, market: 10 },
          },
        ],
        agent_summary: null,
        orchestration: {
          status: "agent_skipped",
          detail: "Pydantic AI model is not configured; used backend provider registry.",
          tool_calls: [],
        },
      },
    });
  });

  await page.goto("/");

  await expect(page.getByRole("button", { name: "MCP Test" })).toHaveCount(0);
  await page.getByLabel("Question").fill(
    "Find Austin-area parcels with power stress, water service, fiber, zoning, and parcel context.",
  );
  await page.getByRole("button", { name: "Go" }).click();

  await expect(page.getByRole("heading", { name: "Top Candidate Parcels" })).toBeVisible();
  const huttoRow = page.getByRole("row", { name: /Hutto - CR 110/ });
  await expect(huttoRow).toBeVisible();

  await huttoRow.click();
  await expect(page.getByRole("heading", { name: "Hutto - CR 110" })).toBeVisible();
  await expect(page.getByText("Distance to Substation", { exact: true })).toBeVisible();

  await expect(page.getByRole("heading", { name: /Research (Progress|Complete)/ })).toBeVisible();
  await expect(page.getByText(/MCP tool (call|calls) recorded|MCP tools pending/)).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole("heading", { name: "Diligence Checklist" })).toBeVisible();
  await expect(page.getByText(/Updated by Pydantic AI|Backend provider fallback/)).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByText("Power & Interconnection", { exact: true })).toBeVisible();
  await expect(page.getByText("Water, Wastewater & Cooling", { exact: true })).toBeVisible();
  await expect(page.getByText("Fiber & Connectivity", { exact: true })).toBeVisible();
});

test("runs direct MCP agent test page", async ({ page }) => {
  const providerEvidence = [
    {
      provider_id: "travis_county_parcels",
      provider_name: "Travis County Parcels",
      queryable: true,
      source: "live_query",
      query_scope: "site_address_filter",
      mcp_tools: ["query_provider"],
      request_url: "https://example.test/FeatureServer/0/query",
      request_params: { resultRecordCount: 2 },
      health_status: "configured",
      query_status: "returned",
      data_status: null,
      data_keys: ["features", "fields"],
      data_preview: {
        features: [
          {
            attributes: {
              OBJECTID: 1,
              situs_address: "123 Main",
            },
          },
        ],
        fields: "2 items",
      },
      feature_count: 2,
      sample_attributes: { OBJECTID: 1, situs_address: "123 Main" },
      geo_features: [
        {
          provider_id: "travis_county_parcels",
          provider_name: "Travis County Parcels",
          label: "123 Main",
          geometry_type: "esriGeometryPolygon",
          rings: [
            [
              [30.267, -97.744],
              [30.267, -97.742],
              [30.265, -97.742],
              [30.265, -97.744],
              [30.267, -97.744],
            ],
          ],
          paths: [],
          point: null,
          attributes: { OBJECTID: 1, situs_address: "123 Main" },
        },
      ],
      error: null,
    },
  ];

  await page.route("**/api/mcp-smoke/providers**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        mcp_url: "http://127.0.0.1:9000/mcp",
        tools: [{ name: "list_providers", description: "List providers" }],
        providers: providerEvidence,
      },
    });
  });

  await page.route("**/api/mcp-smoke/agent", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        mcp_url: "http://127.0.0.1:9000/mcp",
        summary: "Agent used MCP tools and returned provider context.",
        provider_insights: [
          {
            provider_id: "travis_county_parcels",
            status: "returned",
            summary: "Parcel MCP returned data.",
            limitations: ["Entitlements still require confirmation."],
          },
        ],
        tool_calls: ["fastmcp:http://127.0.0.1:9000/mcp"],
        tool_call_records: [
          {
            tool_name: "list_providers",
            arguments: { state: "TX" },
            status: "returned",
            result_preview: "returned list with 1 items",
            result_items: [
              {
                id: "travis_county_parcels",
                name: "Travis County Parcels",
                concern: "zoning",
                queryable: true,
              },
            ],
            result_fields: {},
          },
          {
            tool_name: "query_provider",
            arguments: {
              provider_id: "travis_county_parcels",
              where: "situs_address LIKE '%1201%'",
              limit: 2,
            },
            status: "returned",
            result_preview: "returned object keys: data, provider, request_params, request_url",
            result_items: [],
            result_fields: {
              request_url: "https://example.test/FeatureServer/0/query",
              request_params: "object keys: resultRecordCount",
              data: "object keys: features, fields",
            },
          },
        ],
        evidence: providerEvidence,
        site_context: "1201 S Lamar Blvd, Austin, TX 78704",
      },
    });
  });

  await page.goto("/mcp_test");
  await expect(page.getByRole("heading", { name: "Feasibility Analysis Debug" })).toBeVisible();
  await expect(page.getByLabel("Site / location context")).toHaveValue("1201 S Lamar Blvd, Austin, TX 78704");
  await page.getByLabel("Feasibility question").fill("Use MCPs to inspect provider readiness.");
  await page.getByRole("button", { name: "Start Analysis" }).click();

  await expect(page.locator(".mcp-agent-summary").getByText("Agent used MCP tools and returned provider context.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "MCP Collaboration" })).toBeVisible();
  await expect(page.getByLabel("MCP collaboration transcript").getByText("Site feasibility request")).toBeVisible();
  await expect(page.getByLabel("MCP collaboration transcript").getByText("returned 1 configured providers")).toBeVisible();
  await expect(page.getByLabel("Tool return items").getByText("travis_county_parcels", { exact: true })).toHaveCount(2);
  await expect(page.getByLabel("MCP collaboration transcript").getByText("FastMCP query_provider")).toBeVisible();
  await expect(page.getByLabel("MCP collaboration transcript").getByText("Pydantic AI agent called query_provider")).toBeVisible();
  await expect(page.getByLabel("MCP collaboration transcript").getByText("Final site evidence conclusion")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Geo Evidence Map" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Raw MCP Evidence" })).toHaveCount(0);
  await expect(page.getByLabel("MCP collaboration transcript").getByText("live_query", { exact: true })).toHaveCount(2);
  await expect(
    page.getByLabel("MCP collaboration transcript").getByText("site_address_filter", { exact: true }),
  ).toHaveCount(2);
  await expect(page.getByLabel("MCP collaboration transcript").getByText("returned 2 features", { exact: false })).toBeVisible();
  await expect(
    page.getByLabel("Mapped MCP geo features").getByText("Travis County Parcels", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Site: 1201 S Lamar Blvd, Austin, TX 78704")).toBeVisible();
});
