import { expect, test } from "@playwright/test";

test("submits a feasibility question and displays background provider signals", async ({ page }) => {
  await page.goto("/");

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
