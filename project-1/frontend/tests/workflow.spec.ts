import { test, expect } from "@playwright/test";

test("all seven navigation links reach their pages", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  for (const [name, path, title] of [
    ["Dataset research", "/research", "FAPT-Guard dataset research"],
    ["Command center", "/", "Cyber Defense Intelligence Center"],
    ["Incidents", "/incidents", "Incident investigation"],
    ["Attack graph", "/graph", "Temporal provenance graph"],
    ["Evidence intelligence", "/evidence", "Digital evidence intelligence"],
    ["Prevention simulator", "/prevention", "Evidence-aware prevention"],
    ["Forensic reports", "/reports", "Forensic reports & audit trail"],
  ]) {
    const link = page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name, exact: true });
    await link.click();
    await expect(page).toHaveURL(new RegExp(`${path === "/" ? "/" : path}$`));
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await expect(link).toHaveAttribute("aria-current", "page");
  }
  expect(errors).toEqual([]);
});

test("evidence search, graph filtering, preservation, assessment and report download", async ({ page }) => {
  await page.goto("/evidence");
  // Report and model analysis can exceed five seconds on the persisted research store.
  await expect(page.getByRole("heading", { name: "Evidence inventory" })).toBeVisible({ timeout: 15000 });
  await page.getByRole("textbox", { name: "Search evidence" }).fill("lsass");
  await expect(page.locator(".case-table-wrap").first().locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Inspect EV-00006" }).click();
  await expect(page.locator(".case-detail").last()).toContainText("integrity_hash");
  await page.getByRole("button", { name: "Verify integrity", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("integrity checks refreshed");
  await page.getByRole("button", { name: "Preserve snapshot" }).click();
  await expect(page.getByRole("status")).toContainText("snapshot saved");

  await page.getByRole("link", { name: "Attack graph", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await page.getByRole("button", { name: "lsass.exe", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "All entities" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(6);

  await page.getByRole("link", { name: "Prevention simulator" }).click();
  await page.getByRole("button", { name: "Run assessment", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Response comparison" })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(11);
  await page.getByLabel("Response to simulate").selectOption("NETWORK_ISOLATE");
  await page.getByRole("button", { name: "Preserve & simulate", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("No host action was executed");

  await page.getByRole("link", { name: "Forensic reports" }).click();
  await expect(page.locator(".case-audit").first()).toContainText("SIMULATION NETWORK_ISOLATE");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download report" }).click();
  expect((await download).suggestedFilename()).toBe("INC-00001-forensic-report.json");
  await page.screenshot({ path: "test-results/reports.png", fullPage: true });
});

test("mobile navigation remains visible and dashboard action opens prevention", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Forensic reports" })).toBeVisible();
  await page.locator(".contain-button").click();
  await expect(page).toHaveURL(/\/prevention$/);
  await expect(page.getByRole("heading", { name: "Evidence-aware prevention" })).toBeVisible();
  await page.screenshot({ path: "test-results/mobile-prevention.png", fullPage: true });
});
