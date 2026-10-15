import { test, expect } from "@playwright/test";

const api = "http://127.0.0.1:8001/api/research/prediction-benchmark";

test("offline benchmark displays measured API results and a fixed synthetic prediction", async ({ page, request }) => {
  const response = await request.get(api);
  expect(response.ok()).toBe(true);
  const report = await response.json();
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto("/research");
  const panel = page.getByRole("region", { name: "Chronological prediction benchmark" });
  await expect(panel).toContainText("OFFLINE TEMPORAL EVALUATION");
  await expect(panel).toContainText("not an untouched confirmatory test");
  await expect(panel).toContainText(`Measured FAPT-Guard Top-1: ${(report.results["FAPT-Guard"].top_1_accuracy * 100).toFixed(2)}%`);
  for (const [name, metrics] of Object.entries(report.results) as [string, { top_1_accuracy: number; coverage: number }][]) {
    const row = panel.getByRole("row").filter({ has: page.getByRole("rowheader", { name, exact: true }) });
    await expect(row).toContainText(metrics.top_1_accuracy.toFixed(4));
    await expect(row).toContainText(metrics.coverage.toFixed(4));
  }
  await panel.screenshot({ path: "test-results/prediction-benchmark.png" });
  await panel.getByRole("button", { name: "Inspect fixed test example" }).click();
  const example = panel.getByLabel("Frozen test prediction");
  await expect(example).toContainText("No host action executed", { timeout: 20000 });
  await expect(example).toContainText('"validated_ground_truth": false');
  await expect(example).toContainText(report.model_hash);
  expect(errors).toEqual([]);
});

test("benchmark request failures display actual API errors", async ({ page }) => {
  await page.route(api, route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Benchmark model hash mismatch" }) }));
  await page.goto("/research");
  await expect(page.getByRole("region", { name: "Chronological prediction benchmark" }).getByRole("alert")).toContainText('HTTP 503: "Benchmark model hash mismatch"');
});
