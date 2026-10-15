# Frontend defense integration — 2026-10-08

## Findings

The original dashboard was API-driven research content, with a mixture of fixed backend fixtures, calculated model outputs, stored assessments, and static presentation/default inputs. It did not consume `/api/defense/*`.

`backend/app/api/incidents.py` deliberately calls `get_simulated_incidents()`. That service constructs `INC-00001`, with `simulated=True`, a fixed title, host, user and initial technique. This is intentional research content, not the current defense incident store. It remains available on all existing pages.

All frontend source files were inspected: the seven page components, shared layout/navigation, research and incident components, and CSS. The favicon is a static asset. The package scripts, Playwright config, environment override and installed Next.js guides were also inspected.

| Dashboard information | Original source | Current defense section |
|---|---|---|
| Active incident | `/api/incidents`, first simulated fixture | `/api/defense/incidents`, plus incident linked by evidence ID |
| ATT&CK assessment | Fixture fields and workflow analysis mapping | Selected event's `candidate_techniques`; validated label fields shown separately |
| Prediction | `/api/workflow/{id}/analysis`, rendered by `research-analysis.tsx` | `/api/defense/predictions`, matched by exact event ID |
| Evidence | Workflow analysis/report; fixture evidence with calculated quality | `/api/defense/evidence`, matched by event ID, then detail endpoint for integrity |
| Risk | Saved research assessment's response candidates and analyst assumptions | `/api/defense/risk`, matched by prediction ID; score/level displayed unchanged |
| Decision | Research response recommendation | Audit `assessment_recorded` link identifies `/api/defense/decisions/{id}` |
| Response | Saved research assessment/simulation records | `/api/defense/responses`, matched by prediction ID |
| Metrics | Fixture counts, synthetic evaluation APIs and saved estimates | `/api/defense/metrics?mode=REPLAY` (or selected LAB/LIVE mode) |

Research pages also use `/api/research/datasets`, `examples`, `evaluations`, `benchmark`, `future-prediction`, and temporal scenario APIs. Existing preservation, simulation, export, graph, cutoff and evaluation features were retained.

## Implementation

- Added `frontend/src/components/defense-dashboard.tsx` above the existing research dashboard. It defaults to REPLAY, offers LAB/LIVE separately, refreshes every 30 seconds, and supports manual refresh and event selection.
- Added `frontend/src/lib/api.ts` with shared `API_BASE`, defaulting to `http://127.0.0.1:8001`. The existing `.env.local` already uses this URL and was not changed. All previous source fallbacks to port 8000 now use the shared constant. Next.js embeds public environment values at build time.
- Updated `frontend/src/app/page.tsx` to mount the defense section and explicitly label the preserved fixture as “Research demonstration” / “RESEARCH INCIDENT”.
- Updated the API constant imports in `app/research/page.tsx` and `components/{evaluation-panel,future-evaluation,incident-console,temporal-demonstration}.tsx`.
- Added scoped layout styles in `frontend/src/app/globals.css`.
- Added four browser tests in `frontend/tests/defense-integration.spec.ts`.
- Updated the evidence inventory readiness assertion in `frontend/tests/workflow.spec.ts` to wait at most 15 seconds. The traced successful analysis response took 5.12 seconds, exceeding its former five-second assertion limit; no assertion was removed.

No backend code or thresholds were changed in this task. The pre-existing LSASS rule change and earlier untracked backend tests/demo/report were preserved. No commit or push was made.

## Defense API reads

All requests use `http://127.0.0.1:8001`. The dashboard makes GET requests only:

```text
/api/defense/health
/api/defense/system/status
/api/defense/events?mode=REPLAY&limit=100
/api/defense/evidence?mode=REPLAY&limit=100
/api/defense/predictions?mode=REPLAY&limit=100
/api/defense/risk?mode=REPLAY&limit=100
/api/defense/incidents?mode=REPLAY&limit=100
/api/defense/responses?mode=REPLAY&limit=100
/api/defense/policies
/api/defense/metrics?mode=REPLAY
/api/defense/audit/verify
/api/defense/audit?limit=500
/api/defense/evidence/{evidence_id}
/api/defense/decisions/{decision_id}
/api/defense/incidents/{incident_id}
```

Mode-specific queries change to LAB or LIVE when selected. Audit verification is explicitly labeled as covering all modes. Every requested list/status endpoint returned HTTP 200 and the appropriate CORS origin for `http://localhost:3000`; browser tests also exercise both localhost and 127.0.0.1.

Requests have a 20-second timeout and cancellation on selection/mode/unmount. Results are keyed by request path and refresh generation. Failed requests display the URL, HTTP status and actual API detail instead of a success/zero fallback. Failure in one resource does not suppress successful independent resources.

## Research integrity and safety

- `T1003.001 / LSASS Memory / CANDIDATE` is an observed behavior-rule candidate. It is not promoted to ground truth.
- `ABSTAINED` and the backend's actual reason are displayed. Null technique, probability and uncertainty remain NOT AVAILABLE.
- Risk is displayed exactly as returned. The existing LSASS record shows 0.225 LOW / MONITOR; the shadow-copy record shows 0.25 MEDIUM / ALERT, PRESERVE_EVIDENCE.
- Evidence detail displays `record_seal_valid`, `raw_event_hash_valid`, and `verified`, including false values. Local integrity is distinguished from sensor authenticity.
- Incident IDs, titles, hosts, opened severity and reference chains are returned backend values. Status is explicitly unavailable because the existing defense API does not provide it.
- The response panel displays stored records and execution metadata. There are no approval, execution or containment buttons. Backend execution remains DRY_RUN.
- Accuracy and prevention-success metrics remain NOT MEASURED with their backend explanations. No probabilities, models or metrics were invented.

## Validation and running services

Commands run from `frontend`:

```powershell
npm.cmd run lint
npm.cmd run build
npm.cmd run start -- --port 3000
npx.cmd playwright test --output=test-results/defense-integration-final-20261008
```

PASS: Lint and the production build passed, including TypeScript and all existing routes. The final full browser run passed all 18 tests in 2.1 minutes. Successful integration scenarios had no captured browser errors. `git diff --check` passed; line-ending advisories are not whitespace failures.

Browser tests regenerated two reference screenshots and the benchmark report. Their generated outputs were retained under `frontend/test-results/defense-integration-final-20261008/generated/`, and the exact original bytes saved before testing were restored. Existing fixture simulation/audit records created by browser tests remain preserved.

Initial sandbox attempts to build/run browser workers failed with `spawn EPERM`; approved retries outside the sandbox ran successfully. An initial browser run against the pre-existing development server encountered HMR WebSocket handshake errors on 127.0.0.1 and unhydrated loading views. That run was interrupted after failures. Only the verified project development processes were stopped; the completed production build was started on port 3000. Backend Uvicorn was neither restarted nor modified.

The first full production run passed 17/18 tests. The evidence workflow timed out at five seconds although both report and analysis returned HTTP 200 (4.92 and 5.12 seconds). After changing only that bounded readiness assertion, the complete suite was rerun. This failure is retained in `frontend/test-results/defense-integration-production-20261008/`.

The four new tests verify actual stored replay records against their API responses, unchanged research content, GET-only defense access, localhost CORS, mode switching, HTTP error feedback/recovery and false integrity/audit results. Error/negative-integrity responses in two tests are explicitly intercepted test inputs, not stored evidence changes. A full-page screenshot was inspected visually at `frontend/test-results/defense-dashboard.png`.

Verified live URLs:

- Frontend: `http://localhost:3000` and `http://127.0.0.1:3000` — HTTP 200.
- Backend: `http://127.0.0.1:8001` — defense health ok, no pipeline error.
- Current REPLAY metrics: 10 events, 10 evidence records, 10 predictions, 10 abstained, two incidents, zero responses.
- Audit: 23 records, verified true, no failures. Defense reads did not add telemetry or audit records.

## Limitations

- List views intentionally show at most 100 returned records; decision lookup uses the latest 500 audit entries because there is no decision-list endpoint. Missing/older links are disclosed as unavailable. There is no pagination or push stream; refresh is every 30 seconds.
- The existing research routes remain fixture views. Current defense objects are browsed in the new command-center section.
- No validated observed-data sequential model exists; real forecasting accuracy and prevention success remain unmeasured. The separate synthetic research workflow may legitimately display its own model probabilities.
- Evidence verification authenticates local stored bytes, not the original sensor. Audit integrity has no external anchor.
- The final demonstration uses the production server. The development HMR origin issue was not fixed by changing backend logic.
