"use client";

import { useEffect, useState } from "react";
import { API_BASE, getDefense } from "../lib/api";

type Candidate = { technique_id: string; technique_name: string; mapping_status: string; label_source: string; basis: string };
type Event = { event_id: string; timestamp_utc: string; collection_time: string; host_id: string; user: string | null; action: string; provenance: string; candidate_techniques: Candidate[]; technique_id: string | null; technique_name: string | null; technique_label_source: string | null };
type Evidence = { evidence_id: string; event_id: string; raw_event_hash: string; sha256: string; provenance: string; integrity?: { record_seal_valid: boolean; raw_event_hash_valid: boolean; verified: boolean; scope: string }; incident_ids?: string[] };
type Prediction = { prediction_id: string; event_id: string; status: string; abstain_reason: string | null; predicted_technique_id: string | null; predicted_technique_name: string | null; probability: number | null; uncertainty: number | null; model_name?: string | null; model_version?: string | null; model_hash?: string | null; training_dataset_version?: string | null; calibration_status?: string | null; top_k?: { rank: number; technique_id: string; technique_name: string; probability: number }[] };
type Risk = { risk_id: string; prediction_id: string; risk_score: number; risk_level: string; interpretation: string };
type Incident = { incident_id: string; title: string; host_id: string; mode: string; opened_at_level: string; status?: string; scope: string; chain?: Record<string, string[]> };
type DefenseResponse = { response_id: string; action_type: string; state: string; approval_required: boolean; prediction_id: string; transitions: { execution_mode?: string; host_action_executed?: boolean }[] };
type Decision = { decision_id: string; risk_id: string; internal_actions: string[]; reasons: string[]; containment_candidates: unknown[] };
type AuditEntry = { kind: string; item_id: string; payload: { risk_id?: string; decision_id?: string } };
type Health = { status: string; last_error: string | null };
type System = { response_execution_mode: string; inference: { behavior: string; gate_reason: string | null }; d3fend: { status: string; reason: string } };
type Policies = { policy: { level_actions: Record<string, string[]>; auto_execute_critical: boolean }; response: { execution_mode: string } };
type Metrics = { events: number; evidence: number; predictions: number; abstained: number; incidents: number; prediction_accuracy: number | null; prediction_accuracy_reason: string; prevention_success_rate: number | null; prevention_success_reason: string };
type Audit = { verified: boolean; records: number; failures: string[]; limitation: string };
type Resource<T> = { data?: T; error?: string; loading: boolean };

// Bind results to both path and refresh generation so selection/mode changes
// cannot display a late response belonging to a different record.
function useDefense<T>(path: string | null, revision: number): Resource<T> {
  const [result, setResult] = useState<{ path: string; revision: number; data?: T; error?: string }>();
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new Error("API request timed out after 20 seconds")), 20000);
    let active = true;
    getDefense<T>(path, controller.signal)
      .then(data => { if (active) setResult({ path, revision, data }); })
      .catch(error => { if (active) setResult({ path, revision, error: String(error) }); })
      .finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [path, revision]);
  if (!path) return { loading: false };
  if (result?.path !== path || result.revision !== revision) return { loading: true };
  return { ...result, loading: false };
}

function Feedback({ resource, empty }: { resource: Resource<unknown>; empty?: string }) {
  if (resource.error) return <p className="case-error" role="alert">{resource.error}</p>;
  if (resource.loading) return <p>Loading backend records…</p>;
  if (resource.data === undefined && empty) return <p>{empty}</p>;
  return null;
}

const value = (item: number | boolean | null | undefined) => item == null ? "NOT AVAILABLE" : String(item);

export default function DefenseDashboard() {
  const [mode, setMode] = useState("REPLAY");
  return <section className="case-panel defense-dashboard" aria-label="Current defense data">
    <h2>Current defense data</h2>
    <p>Stored telemetry from the defense API. REPLAY may include synthetic demonstrations; LIVE and LAB are separate collections.</p>
    <label>Defense mode <select aria-label="Defense mode" value={mode} onChange={e => setMode(e.target.value)}>
      {["REPLAY", "LAB", "LIVE"].map(item => <option key={item}>{item}</option>)}
    </select></label>
    <DefenseMode key={mode} mode={mode} />
  </section>;
}

function DefenseMode({ mode }: { mode: string }) {
  const [revision, setRevision] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  useEffect(() => {
    const timer = setInterval(() => setRevision(n => n + 1), 30000);
    return () => clearInterval(timer);
  }, []);
  const query = `mode=${mode}&limit=100`;
  const health = useDefense<Health>("health", revision);
  const system = useDefense<System>("system/status", revision);
  const events = useDefense<Event[]>(`events?${query}`, revision);
  const evidence = useDefense<Evidence[]>(`evidence?${query}`, revision);
  const predictions = useDefense<Prediction[]>(`predictions?${query}`, revision);
  const risks = useDefense<Risk[]>(`risk?${query}`, revision);
  const incidents = useDefense<Incident[]>(`incidents?${query}`, revision);
  const responses = useDefense<DefenseResponse[]>(`responses?${query}`, revision);
  const policies = useDefense<Policies>("policies", revision);
  const metrics = useDefense<Metrics>(`metrics?mode=${mode}`, revision);
  const audit = useDefense<Audit>("audit/verify", revision);
  const auditEntries = useDefense<AuditEntry[]>("audit?limit=500", revision);
  const rows = [...(events.data ?? [])].sort((a, b) => b.collection_time.localeCompare(a.collection_time));
  const event = rows.find(e => e.event_id === selectedId) ?? rows[0];
  const record = evidence.data?.find(e => e.event_id === event?.event_id);
  const detail = useDefense<Evidence>(record ? `evidence/${encodeURIComponent(record.evidence_id)}` : null, revision);
  const prediction = predictions.data?.find(p => p.event_id === event?.event_id);
  const risk = risks.data?.find(r => r.prediction_id === prediction?.prediction_id);
  const decisionId = risk ? auditEntries.data?.find(a => a.kind === "assessment_recorded" && a.payload.risk_id === risk.risk_id)?.payload.decision_id : undefined;
  const decision = useDefense<Decision>(decisionId ? `decisions/${encodeURIComponent(decisionId)}` : null, revision);
  const incidentId = detail.data?.incident_ids?.[0];
  const incident = useDefense<Incident>(incidentId ? `incidents/${encodeURIComponent(incidentId)}` : null, revision);
  const selectedResponses = responses.data?.filter(r => r.prediction_id === prediction?.prediction_id) ?? [];

  return <>
    <div className="case-toolbar"><button onClick={() => setRevision(n => n + 1)}>Refresh defense data</button><span>Refreshes every 30 seconds · {mode} · API: {API_BASE}</span></div>
    <Feedback resource={health} /><Feedback resource={system} />
    {health.data && <p>Defense health: <strong>{health.data.status}</strong>{health.data.last_error && ` — ${health.data.last_error}`}</p>}
    {system.data && <><p>Execution mode: <strong>{system.data.response_execution_mode}</strong>. This dashboard only reads records; no host action controls are provided.</p><p>{system.data.inference.behavior}. {system.data.inference.gate_reason}</p></>}
    <Feedback resource={metrics} />
    {metrics.data && <><div className="defense-metrics" aria-label="Defense counters">{(["events", "evidence", "predictions", "abstained", "incidents"] as const).map(key => <div key={key}><span>{key}</span><strong>{metrics.data![key]}</strong></div>)}</div>
      <p>Prediction accuracy: {metrics.data.prediction_accuracy == null ? "NOT MEASURED" : metrics.data.prediction_accuracy}. {metrics.data.prediction_accuracy_reason}</p>
      <p>Prevention success: {metrics.data.prevention_success_rate == null ? "NOT MEASURED" : metrics.data.prevention_success_rate}. {metrics.data.prevention_success_reason}</p></>}
    <h3>Defense events</h3><Feedback resource={events} />
    {events.data?.length === 0 && <p>No defense events in {mode}.</p>}
    {event && <><label>Inspect event <select aria-label="Inspect defense event" value={event.event_id} onChange={e => setSelectedId(e.target.value)}>{rows.map(e => <option key={e.event_id} value={e.event_id}>{e.host_id} · {e.event_id}</option>)}</select></label>
      <p>Showing up to 100 events from the API&apos;s latest event-time window, sorted here by collection time. Other lists show up to 100 recent records; missing links are reported as unavailable.</p>
      <p data-testid="defense-event">{event.event_id} · {event.host_id} · User: {event.user ?? "NOT AVAILABLE"} · {event.action} · {event.timestamp_utc} · Provenance: {event.provenance}</p>
      <div className="defense-grid">
        <section aria-label="Observed defense candidates"><h3>Observed ATT&amp;CK candidates</h3>
          {event.candidate_techniques.length ? event.candidate_techniques.map(c => <p key={c.technique_id}><strong>{c.technique_id} / {c.technique_name} / {c.mapping_status}</strong><br />{c.label_source}: {c.basis}</p>) : <p>No candidate rule matches for this event.</p>}
          <p>Behavior-rule observations do not establish malicious ground truth.</p>
          <h3>Validated ground truth</h3><p>{event.technique_id && event.technique_label_source ? `${event.technique_id} ${event.technique_name ?? ""} — label source: ${event.technique_label_source}` : "NOT AVAILABLE — this event has no validated technique label."}</p>
        </section>
        <section aria-label="Defense prediction"><h3>Predicted ATT&amp;CK technique</h3><Feedback resource={predictions} />
          {prediction ? <><p><strong>{prediction.status}</strong> · {prediction.prediction_id}</p><p>{prediction.abstain_reason}</p><p>Technique: {prediction.predicted_technique_id ?? "NOT AVAILABLE"} {prediction.predicted_technique_name}</p><p>Probability: {value(prediction.probability)} · Uncertainty: {value(prediction.uncertainty)}</p><p>Model: {prediction.model_name ?? "NOT AVAILABLE"} / {prediction.model_version ?? "NOT AVAILABLE"}</p><p>Training dataset: {prediction.training_dataset_version ?? "NOT AVAILABLE"}</p><p>Calibration: {prediction.calibration_status ?? "NOT MEASURED"}</p>{Boolean(prediction.top_k?.length) && <details><summary>Model top-k output (may be abstained)</summary><ul>{prediction.top_k!.map(item => <li key={item.rank}>{item.rank}. {item.technique_id} / {item.technique_name}: {value(item.probability)}</li>)}</ul><p>Model SHA-256: {prediction.model_hash ?? "NOT AVAILABLE"}</p></details>}</> : !predictions.loading && !predictions.error && <p>NOT AVAILABLE — no prediction linked to this event in the returned records. Inference may be throttled.</p>}
        </section>
        <section aria-label="Defense risk"><h3>Risk and decision</h3><Feedback resource={risks} />
          {risk ? <><p><strong>Risk score: {risk.risk_score} · {risk.risk_level}</strong> · {risk.risk_id}</p><p>{risk.interpretation}</p></> : !risks.loading && !risks.error && <p>Risk NOT AVAILABLE — no matching assessment in the returned records.</p>}
          <Feedback resource={auditEntries} /><Feedback resource={decision} empty="Decision NOT AVAILABLE — no matching link in the latest 500 audit entries." />
          {decision.data && <><p>{decision.data.decision_id}</p><p>Actions: {decision.data.internal_actions.join(", ")}</p><p>{decision.data.reasons.join(" ")}</p></>}
        </section>
        <section aria-label="Defense evidence integrity"><h3>Digital evidence integrity</h3><Feedback resource={evidence} /><Feedback resource={detail} empty="Evidence detail NOT AVAILABLE — no matching record in the returned collection." />
          {detail.data && <><p>{detail.data.evidence_id} · {detail.data.provenance}</p><p>record_seal_valid: {value(detail.data.integrity?.record_seal_valid)}<br />raw_event_hash_valid: {value(detail.data.integrity?.raw_event_hash_valid)}<br />verified: {value(detail.data.integrity?.verified)}</p><p>{detail.data.integrity?.scope}</p><details><summary>Evidence SHA-256 hashes</summary><p>Raw event: {detail.data.raw_event_hash}</p><p>Record seal: {detail.data.sha256}</p></details></>}
        </section>
      </div>
      <section aria-label="Selected defense incident"><h3>Incident linked to selected event</h3><Feedback resource={incident} />
        {incident.data ? <><p>{incident.data.incident_id} · {incident.data.title}</p><p>Host: {incident.data.host_id} · Opened at: {incident.data.opened_at_level} · Status: {incident.data.status ?? "NOT AVAILABLE — API does not supply incident status"}</p><p>{incident.data.scope}</p><details><summary>Incident references</summary><pre>{JSON.stringify(incident.data.chain, null, 2)}</pre></details></> : detail.data && !incident.loading && !incident.error && <p>No incident linked to this event. LOW risk does not reach the configured incident threshold.</p>}
      </section>
      <section aria-label="Defense responses"><h3>Responses linked to selected prediction</h3><Feedback resource={responses} />
        {responses.data && (selectedResponses.length ? selectedResponses.map(r => <div key={r.response_id}><p>{r.response_id} · {r.action_type} · {r.state} · Approval required: {String(r.approval_required)}</p><details><summary>Stored response and execution metadata</summary><pre>{JSON.stringify(r, null, 2)}</pre></details></div>) : <p>No response record linked to this prediction in the returned collection. No containment result is inferred.</p>)}
      </section>
    </>}
    <h3>Recent defense incidents</h3><Feedback resource={incidents} />
    {incidents.data && (incidents.data.length ? <ul>{incidents.data.map(i => <li key={i.incident_id}>{i.incident_id} · {i.title} · {i.host_id} · {i.opened_at_level} · {i.mode}</li>)}</ul> : <p>No incidents in {mode}.</p>)}
    <section aria-label="Defense audit verification"><h3>Audit verification (all modes)</h3><Feedback resource={audit} />
      {audit.data && <><p>verified: <strong>{value(audit.data.verified)}</strong> · Records: {audit.data.records} · Failures: {audit.data.failures.length ? audit.data.failures.join(", ") : "None"}</p><p>{audit.data.limitation}</p></>}
    </section>
    <Feedback resource={policies} />
    {policies.data && <details><summary>Configured defense policy</summary><p>Execution: {policies.data.response.execution_mode} · Auto-execute critical: {String(policies.data.policy.auto_execute_critical)}</p><pre>{JSON.stringify(policies.data.policy.level_actions, null, 2)}</pre></details>}
  </>;
}
