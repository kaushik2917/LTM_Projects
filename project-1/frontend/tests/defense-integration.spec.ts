import { test, expect } from "@playwright/test";

const api = "http://127.0.0.1:8001/api/defense";

test("dashboard reads the current defense API and preserves research content", async ({ page, request }) => {
  const browserErrors: string[] = [];
  const reads = new Set<string>();
  const writes: string[] = [];
  page.on("pageerror", e => browserErrors.push(e.message));
  page.on("console", m => { if (m.type() === "error") browserErrors.push(m.text()); });
  page.on("request", r => {
    if (r.url().includes("/api/defense/")) {
      expect(r.url().startsWith(api)).toBe(true);
      if (r.method() !== "GET") writes.push(r.url());
      reads.add(new URL(r.url()).pathname.replace("/api/defense/", ""));
    }
  });
  const eventsResponse = await request.get(`${api}/events?mode=REPLAY&limit=100`);
  expect(eventsResponse.ok()).toBe(true);
  const events = await eventsResponse.json();
  const lsass = events.find((e: { candidate_techniques: { technique_id: string }[] }) => e.candidate_techniques.some(c => c.technique_id === "T1003.001"));
  expect(lsass, "Existing synthetic LSASS replay is required for this integration check").toBeTruthy();
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Current defense data", exact: true });
  await expect(panel.getByLabel("Inspect defense event")).toBeVisible();
  await panel.getByLabel("Inspect defense event").selectOption(lsass.event_id);
  await expect(panel.getByRole("region", { name: "Observed defense candidates" })).toContainText("T1003.001 / LSASS Memory / CANDIDATE");
  await expect(panel).toContainText("NOT AVAILABLE — this event has no validated technique label");
  const predictions = await (await request.get(`${api}/predictions?mode=REPLAY&limit=100`)).json();
  const prediction = predictions.find((p: { event_id: string }) => p.event_id === lsass.event_id);
  expect(prediction.status).toBe("ABSTAINED");
  const predictionPanel = panel.getByRole("region", { name: "Defense prediction", exact: true });
  await expect(predictionPanel).toContainText(prediction.abstain_reason);
  await expect(predictionPanel).toContainText("ABSTAINED");
  await expect(predictionPanel).toContainText("Probability: NOT AVAILABLE");
  const risks = await (await request.get(`${api}/risk?mode=REPLAY&limit=100`)).json();
  const risk = risks.find((r: { prediction_id: string }) => r.prediction_id === prediction.prediction_id);
  await expect(panel.getByRole("region", { name: "Defense risk", exact: true })).toContainText(`Risk score: ${risk.risk_score} · ${risk.risk_level}`);
  await expect(panel.getByRole("region", { name: "Defense risk", exact: true })).toContainText("Actions: MONITOR");
  const integrity = panel.getByRole("region", { name: "Defense evidence integrity" });
  for (const key of ["record_seal_valid", "raw_event_hash_valid", "verified"]) await expect(integrity).toContainText(`${key}: true`);
  await expect(panel.getByRole("region", { name: "Defense audit verification" })).toContainText("verified: true");
  await expect(panel).toContainText("Execution mode: DRY_RUN");
  await expect(panel).toContainText("Prediction accuracy: NOT MEASURED");
  const shadow = events.find((e: { candidate_techniques: { technique_id: string }[] }) => e.candidate_techniques.some(c => c.technique_id === "T1490"));
  expect(shadow).toBeTruthy();
  await panel.getByLabel("Inspect defense event").selectOption(shadow.event_id);
  await expect(panel.getByRole("region", { name: "Defense risk", exact: true })).toContainText("Actions: ALERT, PRESERVE_EVIDENCE");
  await expect(panel.getByRole("region", { name: "Selected defense incident" })).toContainText("INC-D-");
  await expect(panel.getByRole("region", { name: "Selected defense incident" })).toContainText(shadow.host_id);
  for (const endpoint of ["health", "system/status", "events", "evidence", "predictions", "risk", "incidents", "responses", "policies", "metrics", "audit/verify"]) expect(reads.has(endpoint), endpoint).toBe(true);
  await expect(page.getByRole("heading", { name: "Research demonstration", exact: true })).toBeVisible();
  await expect(page.getByLabel("Future attack prediction", { exact: true })).toContainText("Synthetic-trained research model");
  expect(browserErrors).toEqual([]);
  expect(writes).toEqual([]);
  await page.screenshot({ path: "test-results/defense-dashboard.png", fullPage: true });
});

test("defense requests work from localhost with backend CORS", async ({ page }) => {
  await page.goto("http://localhost:3000");
  const panel = page.getByRole("region", { name: "Current defense data", exact: true });
  await expect(panel).toContainText("Defense health: ok");
  await expect(panel.getByLabel("Inspect defense event")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.getByLabel("Defense mode").selectOption("LAB");
  await expect(panel).toContainText("No defense events in LAB");
  await expect(panel.getByTestId("defense-event")).toHaveCount(0);
  await panel.getByLabel("Defense mode").selectOption("REPLAY");
  await expect(panel.getByTestId("defense-event")).toBeVisible();
  await expect(panel.getByRole("alert")).toHaveCount(0);
});

test("failed defense reads show the actual error and recover on refresh", async ({ page }) => {
  await page.route("**/api/defense/metrics?*", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Integration test: metrics store unavailable" }) }));
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Current defense data", exact: true });
  await expect(panel.getByRole("alert")).toContainText("HTTP 503: Integration test: metrics store unavailable");
  await expect(panel.getByLabel("Defense counters")).toHaveCount(0);
  await expect(panel.getByLabel("Inspect defense event")).toBeVisible();
  await page.unroute("**/api/defense/metrics?*");
  await panel.getByRole("button", { name: "Refresh defense data" }).click();
  await expect(panel.getByLabel("Defense counters")).toBeVisible();
  await expect(panel.getByRole("alert")).toHaveCount(0);
});

test("negative integrity and audit verification are never displayed as success", async ({ page }) => {
  await page.route("**/api/defense/evidence/*", async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.integrity = { ...body.integrity, record_seal_valid: false, raw_event_hash_valid: false, verified: false };
    await route.fulfill({ response, json: body });
  });
  await page.route("**/api/defense/audit/verify", route => route.fulfill({ json: { verified: false, records: 1, failures: ["TEST-AUDIT-FAILURE"], limitation: "Injected browser test result" } }));
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Current defense data", exact: true });
  await expect(panel.getByRole("region", { name: "Defense evidence integrity" })).toContainText("verified: false");
  await expect(panel.getByRole("region", { name: "Defense audit verification" })).toContainText("TEST-AUDIT-FAILURE");
});
