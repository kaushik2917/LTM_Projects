import { test, expect } from "@playwright/test";

test("research metrics identify their experiment and preserve pending incident truth", async ({ page, request }) => {
  const response = await request.get("http://127.0.0.1:8001/api/research/prospective-prediction");
  expect(response.ok()).toBe(true);
  const data = await response.json();
  expect(data.status).toBe("EVALUATED");
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("/research");
  await expect(page.getByText("Historical experiment: V2-RANDOM-TRANSITION", { exact: true })).toBeVisible();
  await expect(page.getByText("Historical experiment: CHRONOLOGICAL-V2", { exact: true })).toBeVisible();
  const panel = page.getByRole("region", { name: "Prospective temporal evaluation" });
  await expect(panel).toContainText(data.frozen.model_hash);
  await expect(panel).toContainText(data.test_dataset_sha256);
  for (const [name, values] of Object.entries(data.results) as [string, { top_1_accuracy: number; conformal_coverage: number; average_prediction_set_size: number }][]) {
    const row = panel.getByRole("row").filter({ has: page.getByRole("rowheader", { name, exact: true }) });
    for (const value of [values.top_1_accuracy, values.conformal_coverage, values.average_prediction_set_size]) await expect(row).toContainText(value.toFixed(4));
  }
  await panel.screenshot({ path: "test-results/prospective-evaluation.png" });
  await page.goto("/");
  const prediction = page.getByLabel("Future attack prediction", { exact: true });
  await expect(prediction).toContainText("SYNTHETIC DEMONSTRATION / NOT REAL-WORLD VALIDATION");
  await expect(prediction).toContainText("PENDING_GROUND_TRUTH");
  expect(errors).toEqual([]);
});
