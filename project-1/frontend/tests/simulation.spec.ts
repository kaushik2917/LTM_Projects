import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { writeFile } from "node:fs/promises";

for (const width of [1365, 390]) {
  test(`preservation and simulation give visible verified results at width ${width}`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto("/prevention?incident=INC-00001");
    await expect(page.getByRole("heading", { name: "Scenario assumptions" })).toBeVisible({ timeout: 30000 });
    if (!await page.getByRole("button", { name: "Preserve & simulate", exact: true }).count()) {
      await page.getByRole("button", { name: "Run assessment", exact: true }).click();
    }
    const button = page.getByRole("button", { name: "Preserve & simulate", exact: true });
    await expect(button).toBeEnabled();
    await page.getByLabel("Response to simulate").selectOption("NETWORK_ISOLATE");
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/workflow/*/simulate", async route => {
      await gate;
      await route.continue();
    });
    const responsePromise = page.waitForResponse(r => r.url().endsWith("/simulate"));
    await button.click();
    try {
      await expect(page.getByRole("button", { name: "Preserving & simulating…" })).toBeDisabled();
      await expect(page.getByRole("status")).toContainText("verifying the snapshot");
      await expect(page.getByRole("status")).toBeInViewport();
    } finally { release(); }
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const result = await response.json();
    expect(response.request().postDataJSON()).toEqual({ assessment_id: result.assessment_id, action: "NETWORK_ISOLATE" });
    expect(result.incident_id).toBe("INC-00001");
    expect(result.simulated).toBe(true);
    expect(result.host_action_executed).toBe(false);
    expect(result.observed_post_response_survival).toBeNull();
    await expect(page.getByRole("status")).toContainText("Preservation completed. Simulation completed.");
    await expect(page.getByRole("status")).toBeInViewport();
    const details = page.getByLabel("Preservation and simulation result");
    await expect(details).toContainText("SIMULATED ENVIRONMENT — No host action executed");
    await expect(details).toContainText(result.preservation.snapshot_id);
    await expect(details).toContainText(result.preservation.sha256);
    await expect(details).toContainText("NOT MEASURED");
    const reportResponse = await request.get(response.url().replace(/simulate$/, "report"));
    expect(reportResponse.ok()).toBe(true);
    const report = await reportResponse.json();
    const saved = report.audit.find((e: { id: string }) => e.id === result.preservation_id);
    expect(createHash("sha256").update(saved.snapshot_json, "utf8").digest("hex")).toBe(saved.sha256);
    expect(saved.sha256).toBe(result.preservation.sha256);
    expect(saved.snapshot_integrity_valid).toBe(true);
    expect(JSON.parse(saved.snapshot_json).evidence).toHaveLength(result.preservation.evidence_count);
    expect(report.audit.find((e: { id: string }) => e.id === result.id)).toEqual(result);
    expect(report.chain_of_custody.verified).toBe(true);
    await expect(page.locator(".case-stats")).toContainText(String(report.audit.filter((e: { kind: string }) => e.kind === "preservation").length));
    await page.reload();
    await expect(page.getByRole("button", { name: "Preserve & simulate", exact: true })).toBeEnabled();
    await page.getByRole("link", { name: "Forensic reports", exact: true }).click();
    await expect(page.locator(".case-audit").filter({ hasText: result.id })).toContainText("SIMULATION NETWORK_ISOLATE");
    expect(errors).toEqual([]);
    await writeFile(testInfo.outputPath("simulation-result.json"), JSON.stringify({ result, independentlyVerifiedSha256: saved.sha256, auditChainVerified: report.chain_of_custody.verified, browserErrors: errors }, null, 2));
  });
}

test("actual backend rejection and non-JSON failure appear beside the button", async ({ page }) => {
  await page.goto("/prevention");
  const button = page.getByRole("button", { name: "Preserve & simulate", exact: true });
  await expect(button).toBeEnabled();
  await page.route("**/api/workflow/*/simulate", route => route.continue({ postData: JSON.stringify({ ...route.request().postDataJSON(), assessment_id: "missing-test-assessment" }) }));
  await button.click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("HTTP 404: Assessment not found for this incident");
  await expect(page.getByRole("main").getByRole("alert")).toBeInViewport();
  await expect(button).toBeEnabled();
  await expect(page.getByLabel("Preservation and simulation result")).toHaveCount(0);
  await page.unroute("**/api/workflow/*/simulate");
  // Inject a plain-text server failure to exercise the response parser.
  await page.route("**/api/workflow/*/simulate", route => route.fulfill({ status: 500, contentType: "text/plain", body: "Test storage failure" }));
  await button.click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("HTTP 500 Internal Server Error: Test storage failure");
  await expect(page.getByRole("main").getByRole("alert")).toBeInViewport();
  await expect(button).toBeEnabled();
  await expect(page.getByLabel("Preservation and simulation result")).toHaveCount(0);
});

test("refresh failure preserves the successful result and explains what failed", async ({ page }) => {
  await page.goto("/prevention");
  const button = page.getByRole("button", { name: "Preserve & simulate", exact: true });
  await expect(button).toBeEnabled();
  await page.route("**/api/workflow/*/report", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Test report refresh failure" }) }));
  await button.click();
  await expect(page.getByRole("status")).toContainText("Simulation completed");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("The simulation was recorded, but refreshing the incident failed");
  await expect(page.getByRole("main").getByRole("alert")).toBeInViewport();
  await expect(page.getByLabel("Preservation and simulation result")).toContainText("Snapshot ID:");
});
