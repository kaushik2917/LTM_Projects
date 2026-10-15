# Preserve & simulate: implementation trace

## Cause and incremental fix

The button's handler and backend were working. A browser reproduction returned HTTP 200, created preservation and simulation records, and refreshed the report without console errors. However, the success notice was rendered near the page header, approximately 1,260 pixels above the viewport after clicking the button. The button had no operation-specific progress label, and the frontend discarded the returned simulation record.

The existing prevention view now shows progress, success, errors and the returned result beside the button. Feedback scrolls into view. The result includes the snapshot ID, SHA-256, verification status, evidence count, selected action and audit identifiers. Existing CSS and page structure are reused. The API includes a small preservation summary from the already verified record. No build or UI redesign is required.

## Complete flow

1. `frontend/src/components/incident-console.tsx`: the button calls `simulateResponse`. The selected incident is `id`; the action is `chosen`; the assessment is the latest saved assessment for that incident. Controls are disabled during the request.
2. `request` posts to `${NEXT_PUBLIC_API_URL}/api/workflow/${id}/simulate` with JSON `{ assessment_id, action }`. In the current local setup the API is `http://127.0.0.1:8001`.
3. `backend/app/api/workflow.py`: `SimulationRequest` validates the body, and the route calls `workflow_service.simulate`. Missing incident/assessment produces HTTP 404; invalid action or failed integrity verification produces HTTP 422.
4. `simulate` confirms the incident exists, verifies the existing audit chain, finds the assessment for this incident and requires that the selected action belongs to that assessment.
5. It analyzes the fixture evidence and maps evidence sources to artifact categories. Survival estimates come from the saved response candidate; predicted loss is `1 - predicted_survival`. Unmapped categories retain null estimates. These are model estimates, not observed survival.
6. `preserve` calls `snapshot`, which serializes the incident, all evidence fields and existing fixture integrity checks. Snapshot material is canonical JSON: sorted keys, compact separators, Unicode retained.
7. `hashlib.sha256(material.encode()).hexdigest()` hashes the actual UTF-8 snapshot content. A preservation audit record stores the content, snapshot UUID, hash, evidence identifiers/count and acquisition scope.
8. `record` writes the record to `data/workflow.sqlite3`, table `audit`, in a committed SQLite transaction. Each record receives its own UUID, timestamp, predecessor hash and SHA-256 over the canonical audit payload.
9. `preserve` reads the saved snapshot back through `history`, recomputes SHA-256 and compares it with the stored digest. A mismatch raises `Preservation verification failed`; no simulation record is created. A match returns `VERIFIED`.
10. `simulate` records the chosen action, assessment ID, linked preservation audit ID, verified snapshot summary, evidence risk estimates and saved candidate estimates. This is the simulation result and its audit record. It stores `simulated: true`, `host_action_executed: false` and `observed_post_response_survival: null`.
11. The frontend retains this response and displays `Preservation completed`, `Simulation completed`, and `SIMULATED ENVIRONMENT — No host action executed`. It increments `revision`, which refetches incidents, report and analysis. The snapshot count and audit data refresh. The Reports link exposes the persistent records.
12. HTTP errors retain the response status and actual API detail/body, including non-JSON responses. Network errors are shown. If saving succeeds but report refresh fails, the successful result stays visible with an explicit refresh error.

## What is measured

- Stored application evidence count and snapshot content.
- Actual SHA-256 equality after database readback.
- Audit payload hash-chain consistency.
- Model-derived retention/loss estimates, explicitly labeled as estimates.

Observed evidence survival is **NOT MEASURED** because no host response occurs. Missing artifact mappings/estimates are **NOT AVAILABLE**. No live memory, disk or log acquisition is performed. Identical evidence content can legitimately produce the same hash across different snapshot UUIDs.

## Safety and storage boundaries

The simulation path has no action executor, subprocess command, process termination, firewall change, account change or host shutdown. Action names only select saved candidate data. This holds for all 11 available response actions.

Preservation and simulation use separate committed audit writes. If a later step fails, the earlier preservation record can remain; the request reports failure rather than inventing a simulation result. Local hashes detect content changes but do not authenticate original sensor evidence or protect against replacement of the entire database without an external anchor.

## Verification

- `backend/tests/test_workflow.py`: stored snapshot rehash, record linkage/persistence, all response choices, null observed survival, and rejection of corrupted snapshot readback.
- `backend/tests/test_validity.py`: audit tampering detection and existing validity checks.
- `frontend/tests/simulation.spec.ts`: desktop/mobile clicks, visible progress and feedback, selected action payload, independent Node SHA-256 rehash, persistent report records, browser errors, real backend rejection, injected plain-text HTTP failure and injected refresh failure.

Browser tests intentionally create local simulated audit records. Injected error responses are test inputs, not claimed real service failures.

### Verified local run, 2026-09-29

- Incident/action: `INC-00001` / `NETWORK_ISOLATE`.
- Endpoint: `POST http://127.0.0.1:8001/api/workflow/INC-00001/simulate`; HTTP 200.
- Snapshot: `359ae72e-2b4e-4578-9349-17fd71e4be28`; six application evidence records.
- SHA-256: `2ec70127537232e242d13e777a615c55378a0fcf90cd6611f6b20ab70edc7d52`.
- Preservation audit ID: `e083c5bc-9519-4688-94bc-e0d658e8232e`.
- Simulation/audit ID: `8fdf7b33-2a8e-481d-91f1-4881058b0a2e`.
- Backend readback verification, independent Node rehash, and direct SQLite read-only Python rehash all matched. The persisted audit chain also verified.
- Stored retention estimate: `0.912021135214478` (91.2% displayed); observed survival remains null / NOT MEASURED.
- `host_action_executed` is false; no host response was executed.
- Ten backend tests and four browser tests passed. TypeScript checking and targeted ESLint passed. Successful browser runs had no console/page errors; API logs showed successful simulation/report requests and the expected 404 from the rejection test.
