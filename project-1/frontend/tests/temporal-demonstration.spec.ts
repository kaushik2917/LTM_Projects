import { test, expect } from "@playwright/test";

test("synthetic prediction excludes hidden future until audited reveal", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto("/research");
  const panel = page.getByLabel("Synthetic evaluation demonstration");
  await expect(panel.getByRole("button", { name: "Predict observed prefix" })).toBeEnabled({ timeout: 30000 });
  await expect(panel).toContainText("Empirical test coverage:");
  const predicted = page.waitForResponse(r => r.url().includes("temporal-scenarios/") && r.url().endsWith("/predict"));
  await panel.getByRole("button", { name: "Predict observed prefix" }).click();
  const response = await predicted;
  expect(response.ok()).toBe(true);
  const result = await response.json();
  expect(result.ground_truth.event).toBeNull();
  expect(result.ground_truth.status).toBe("HIDDEN");
  await expect(panel.getByTestId("revealed-future")).toHaveCount(0);
  await expect(panel).toContainText("CALIBRATED MODEL PROBABILITY");
  const reveal = page.waitForResponse(r => r.url().endsWith("/reveal"));
  await panel.getByRole("button", { name: "Reveal hidden ground truth" }).click();
  const revealed = await (await reveal).json();
  expect(revealed.probability_distribution).toEqual(result.probability_distribution);
  expect(result.input_evidence_ids).not.toContain(revealed.ground_truth.event.evidence_id);
  expect(["CORRECT", "INCORRECT"]).toContain(revealed.evaluation.status);
  expect(revealed.evaluation_audit_id).toBeTruthy();
  await expect(panel.getByTestId("revealed-future")).toContainText(revealed.ground_truth.event.evidence_id);
  await expect(panel).toContainText(`Prediction correctness: ${revealed.evaluation.status}`);
  await expect(panel.getByRole("img", { name: "Observed synthetic temporal graph" })).not.toContainText(revealed.ground_truth.event.evidence_id);
  const download = page.waitForEvent("download");
  await panel.getByRole("button", { name: "Export demonstration report" }).click();
  expect((await download).suggestedFilename()).toContain("prediction-report.json");
  await page.screenshot({ path: "../docs/screenshots/temporal-demonstration.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("prevention uses future risk while preserving simulation and pending report", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/prevention");
  await expect(page.getByRole("slider", { name: /Analyst uncertainty assumption/ })).toBeVisible();
  const response = page.waitForResponse(r => r.url().endsWith("/assessment") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Run assessment" }).click();
  const saved = await (await response).json();
  for (const candidate of saved.response_analysis.candidates) {
    expect(candidate.objective_score).toBeCloseTo(candidate.base_objective_score + candidate.future_prediction_contribution, 12);
    expect(candidate.expected_future_risk).toBeGreaterThanOrEqual(0);
  }
  await expect(page.getByRole("columnheader", { name: "Future prediction contribution" })).toBeVisible();
  await page.screenshot({ path: "../docs/screenshots/prediction-aware-prevention.png", fullPage: true });
  await page.goto("/reports");
  await expect(page.getByLabel("Future attack prediction")).toContainText("PENDING_GROUND_TRUTH");
  expect(errors).toEqual([]);
});
