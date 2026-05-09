import { expect, test } from "@playwright/test";

test("submits a feasibility question and displays background provider signals", async ({ page }) => {
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

  await expect(page.getByRole("heading", { name: "Agent Research" })).toBeVisible();
  await expect(page.getByText("FastMCP:", { exact: false })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole("heading", { name: "Open Data Provider Signals" })).toBeVisible();
  await expect(page.getByText(/Updated by Pydantic AI|Backend provider fallback/)).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByText("ERCOT Market Data Transparency", { exact: true })).toBeVisible();
  await expect(page.getByText("Austin Water Utility Service Area", { exact: true })).toBeVisible();
  await expect(page.getByText("Texas Broadband Development Map", { exact: true })).toBeVisible();
});

test("runs direct MCP agent test page", async ({ page }) => {
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
        evidence: [
          {
            provider_id: "travis_county_parcels",
            provider_name: "Travis County Parcels",
            queryable: true,
            source: "live_query",
            mcp_tools: ["provider_health", "query_provider"],
            request_url: "https://example.test/FeatureServer/0/query",
            request_params: { resultRecordCount: 2 },
            health_status: "configured",
            query_status: "returned",
            data_status: null,
            data_keys: ["features", "fields"],
            feature_count: 2,
            sample_attributes: { OBJECTID: 1, situs_address: "123 Main" },
            error: null,
          },
        ],
      },
    });
  });

  await page.goto("/mcp_test");
  await expect(page.getByRole("heading", { name: "MCP Agent Test" })).toBeVisible();
  await page.getByLabel("Agent prompt").fill("Use MCPs to inspect provider readiness.");
  await page.getByRole("button", { name: "Run Agent With MCPs" }).click();

  await expect(page.getByText("Agent used MCP tools and returned provider context.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Raw MCP Evidence" })).toBeVisible();
  await expect(page.getByText("live_query")).toBeVisible();
  await expect(page.getByText("2 features", { exact: false })).toBeVisible();
  await expect(
    page.getByLabel("Raw MCP provider evidence").getByText("travis_county_parcels"),
  ).toBeVisible();
  await expect(page.getByText("fastmcp:http://127.0.0.1:9000/mcp")).toBeVisible();
});
