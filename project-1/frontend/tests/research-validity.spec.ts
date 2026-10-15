import { test, expect } from "@playwright/test";

test("dashboard explains model output and temporal cutoff excludes future evidence", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await page.getByText("Dataset Demonstration Scenario - Synthetic next-stage prediction", { exact: true }).click();
  await expect(page.locator(".prediction-choice").first()).toBeVisible();
  await page.locator(".prediction-choice").first().click();
  await expect(page.getByRole("dialog", { name: "Prediction explanation" })).toContainText("EV-00006");
  await expect(page.getByRole("dialog")).toContainText("model_version");
  await page.getByRole("button", { name: "Close explanation" }).click();
  await page.getByRole("link", { name: "Attack graph", exact: true }).click();
  await page.getByText("Dataset Demonstration Scenario - Synthetic next-stage prediction", { exact: true }).click();
  const cutoff = page.getByRole("slider", { name: "Temporal cutoff" });
  await cutoff.focus();
  await cutoff.press("Home");
  for (let i = 0; i < 4; i++) await cutoff.press("ArrowRight");
  await expect(cutoff).toHaveValue("4");
  await expect(page.getByText("Current state: Execution", { exact: false })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(4);
  await expect(page.locator("tbody")).not.toContainText("EV-00006");
  await expect(page.getByText("Dataset Demonstration Scenario - Synthetic next-stage prediction", { exact: true }).locator("..").locator(".prediction-choice")).toHaveCount(0);
  await expect(page.getByLabel("Future attack prediction").locator(".prediction-choice")).toHaveCount(3);
  await cutoff.press("End");
  await expect(page.locator("tbody tr")).toHaveCount(6);
  const demo = page.getByText("Dataset Demonstration Scenario - Synthetic next-stage prediction", { exact: true });
  if (await demo.locator("..").getAttribute("open") === null) await demo.click();
  await expect(page.locator(".prediction-choice").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("evidence quality shows methods and research benchmark executes", async ({ page }) => {
  await page.goto("/evidence");
  await page.getByRole("button", { name: "Inspect EV-00006" }).click();
  await expect(page.getByRole("heading", { name: "Evidence quality: EV-00006" })).toBeVisible();
  await page.getByText("Supporting fields and calculation", { exact: true }).click();
  await expect(page.locator(".case-detail").first()).toContainText("trust_formula");
  await page.getByRole("link", { name: "Dataset research", exact: true }).click();
  await expect(page.getByRole("cell", { name: "FAPT Anti-Forensic Dataset", exact: true })).toBeVisible();
  await page.getByText(/^AFIP ·/).click();
  await expect(page.getByRole("heading", { name: "Confusion matrix (rows: actual; columns: predicted)" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Run fixture benchmark", exact: true }).click();
  await expect(page.getByText("executed_fixture_replay", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "missing_50", exact: true })).toBeVisible();
  await expect(page.getByText("Coverage not measured", { exact: false }).first()).toBeVisible();
});
