"use client";

import { API_BASE } from "../lib/api";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Analysis, EvidenceQuality, FuturePrediction, Prediction, PredictionDetails, metric } from "./research-analysis";

const API = API_BASE;
type View = "incidents" | "graph" | "evidence" | "prevention" | "reports";
type Incident = { incident_id: string; title: string; status: string; severity: string; affected_host: string; current_tactic: string; current_technique_id: string; evidence_count: number };
type Evidence = { evidence_id: string; timestamp: string; source: string; subject: string; action: string; object: string; evidence_type: string; confidence: number; volatility: number; attack_technique_id: string | null; integrity_hash: string };
type Candidate = { action: string; residual_attack_risk: number; evidence_retention_score: number; evidence_loss_cost: number; business_impact: number; objective_score: number; expected_future_risk?: number | null; future_prediction_contribution?: number; response_cost?: number; evidence_opportunity_cost?: number; future_risk?: { unsupported_probability_mass: number } };
type Audit = { id: string; kind: string; created_at: string; action?: string; sha256?: string; snapshot_integrity_valid?: boolean; response_analysis?: { recommended_action: string; candidates: Candidate[]; objective_formula?: string; elc_definition?: string; elc_maximum?: number }; anti_forensic?: { predictions: { behavior: string; probability: number; preservation_action: string }[] } };
type Report = { future_attack_prediction: Prediction; incident: Incident; evidence: Evidence[]; integrity: { evidence_id: string; valid: boolean; scope: string }[]; audit: Audit[]; limitations: string[] };
type Simulation = { id: string; incident_id: string; action: string; preservation_id: string; snapshot_verification: string; simulated: boolean; host_action_executed: boolean; observed_survival_reason: string; preservation?: { snapshot_id: string; sha256: string; evidence_count: number; verification_status: string; scope: string }; predicted_outcome: Candidate; evidence_at_risk: { evidence_id: string; artifact_mapping: string | null; predicted_survival: number | null; predicted_loss: number | null }[] };
type Graph = { nodes: { id: string; label: string; type: string }[]; edges: { source: string; target: string; action: string; evidence_id: string; timestamp: string; technique_id: string | null }[] };
const titles: Record<View, string> = { incidents: "Incident investigation", graph: "Temporal provenance graph", evidence: "Digital evidence intelligence", prevention: "Evidence-aware prevention", reports: "Forensic reports & audit trail" };
const defaults = { asset_criticality: 0.8, baseline_attack_risk: 0.8, evidence_trust: 0.8, anti_forensic_risk: 0.5, prediction_uncertainty: 0.3, graph_integrity: 0.8 };

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(API + path, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); }
  catch {
    throw new Error(`HTTP ${response.status} ${response.statusText}: ${text || "Empty API response"}`);
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data)}`);
  return data;
}

function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function IncidentConsole({ view }: { view: View }) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [id, setId] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [cutoff, setCutoff] = useState<number | null>(null);
  const [cutoffTime, setCutoffTime] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [values, setValues] = useState(defaults);
  const [intent, setIntent] = useState("credential_theft");
  const [previousStage, setPreviousStage] = useState("Execution");
  const [selectedAction, setSelectedAction] = useState("");
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [simulating, setSimulating] = useState(false);
  const simulationFeedback = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (view === "prevention" && (simulating || notice || error)) {
      simulationFeedback.current?.scrollIntoView({ block: "nearest" });
    }
  }, [view, simulating, notice, error]);

  useEffect(() => {
    let active = true;
    request<Incident[]>("/api/incidents").then(data => {
      if (!active) return;
      setIncidents(data);
      const selected = new URLSearchParams(window.location.search).get("incident");
      setId(current => data.some(i => i.incident_id === current) ? current : data.find(i => i.incident_id === selected)?.incident_id ?? data[0]?.incident_id ?? "");
      if (!data.length) setLoading(false);
    }).catch(e => { if (active) { setError(String(e)); setLoading(false); } });
    return () => { active = false; };
  }, [revision]);

  useEffect(() => {
    if (!id) return;
    let active = true;
    Promise.all([request<Report>(`/api/workflow/${id}/report`), request<Analysis>(`/api/workflow/${id}/analysis${cutoff === null ? "" : cutoff === 0 ? "?upto=0" : `?cutoff_timestamp=${encodeURIComponent(cutoffTime ?? "")}`}`)]).then(([data, g]) => {
      if (active) { setReport(data); setGraph(g.graph); setAnalysis(g); setLoading(false); }
    }).catch(e => { if (active) { setError(String(e)); setLoading(false); } });
    return () => { active = false; };
  }, [id, revision, cutoff, cutoffTime]);

  async function action(label: string, operation: () => Promise<unknown>) {
    setBusy(true); setError(""); setNotice("");
    try { await operation(); setNotice(label); setRevision(r => r + 1); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  const incident = report?.incident;
  const latest = report?.audit.find(a => a.kind === "assessment");
  const candidates = latest?.response_analysis?.candidates ?? [];
  const chosen = candidates.some(c => c.action === selectedAction) ? selectedAction : candidates[0]?.action ?? "";
  const evidence = report?.evidence.filter(e => `${e.evidence_id} ${e.source} ${e.subject} ${e.action} ${e.object}`.toLowerCase().includes(search.toLowerCase())) ?? [];

  async function assess() {
    if (!incident) return;
    setSimulation(null);
    const { graph_integrity, ...context } = values;
    await request(`/api/workflow/${id}/assessment`, { context: { ...context, attack_stage: incident.current_tactic, technique_id: incident.current_technique_id, attacker_intent: intent }, graph_integrity, previous_stage: previousStage });
  }

  async function simulateResponse() {
    if (!latest || !chosen || busy) return;
    setSimulating(true); setSimulation(null);
    try {
      await action("Preservation completed. Simulation completed. No host action was executed.", async () => {
        const result = await request<Simulation>(`/api/workflow/${id}/simulate`, { assessment_id: latest.id, action: chosen });
        setSimulation(result);
      });
    } finally { setSimulating(false); }
  }

  return <main className="case-workspace">
    <header className="case-header"><div><p className="eyebrow">FAPT-GUARD / INVESTIGATION WORKSPACE</p><h1>{titles[view]}</h1></div><span className="case-badge">SIMULATION · RESEARCH BASELINES</span></header>
    <div className="case-toolbar">
      <label>Incident <select aria-label="Select incident" value={id} disabled={busy || loading} onChange={e => { setId(e.target.value); setLoading(true); setReport(null); setGraph(null); setSelectedNode(null); setSelectedEvidence(null); setSelectedAction(""); setCutoff(null); setCutoffTime(null); setSimulation(null); setNotice(""); setError(""); }}>
        {incidents.map(i => <option key={i.incident_id} value={i.incident_id}>{i.incident_id} · {i.affected_host}</option>)}
      </select></label>
      <button disabled={busy} onClick={() => { setError(""); setLoading(true); setRevision(r => r + 1); }}>Refresh</button>
      {incident && <span>Current ATT&amp;CK assessment: {analysis?.current_stage ?? "Unmapped"} · {analysis?.current_technique ?? "No technique mapped"} · Status: {analysis?.future_prediction.current_mapping_status ?? "NOT AVAILABLE"}</span>}
    </div>
    {error && !(view === "prevention" && latest && !loading) && <div className="case-error" role="alert">{error}</div>}
    {notice && view !== "prevention" && <div className="case-notice" role="status">{notice}</div>}
    {loading && <p role="status">Loading incident records…</p>}
    {!loading && !incidents.length && !error && <p>No incidents available.</p>}
    {report && !loading && <>
      <div className="case-stats"><div><small>Incident</small><strong>{id}</strong></div><div><small>Evidence records</small><strong>{report.evidence.length}</strong></div><div><small>Snapshot collections</small><strong>{report.audit.filter(a => a.kind === "preservation").length}</strong></div><div><small>Saved assessments</small><strong>{report.audit.filter(a => a.kind === "assessment").length}</strong></div></div>

      {view === "incidents" && <>
        <section className="case-panel"><h2>{incident?.title}</h2><p>{incident?.affected_host} · Severity: {incident?.severity} · Status: {incident?.status}</p>
          <p>This incident contains simulated evidence. Use the workflow below to investigate, preserve a snapshot, compare responses, and review the resulting audit trail.</p>
          <div className="case-actions">{[["graph", "Explore graph"], ["evidence", "Inspect evidence"], ["prevention", "Compare responses"], ["reports", "View report"]].map(([path, label]) => <Link key={path} href={`/${path}?incident=${encodeURIComponent(id)}`}>{label} →</Link>)}</div>
        </section>
        <section className="case-panel"><h2>Attack chronology</h2><ol className="case-timeline">{report.evidence.map(e => <li key={e.evidence_id}><time>{e.timestamp.replace("T", " ")}</time><strong>{e.subject} → {e.action} → {e.object}</strong><span>{e.evidence_id} · {e.source}{e.attack_technique_id ? ` · ${e.attack_technique_id}` : ""}</span></li>)}</ol></section>
      </>}

      {view === "graph" && analysis && <section className="case-panel"><h2>Temporal evidence cutoff</h2><label>Show observations up to: {analysis.evidence.at(-1)?.timestamp ?? "No observations"}<input aria-label="Temporal cutoff" type="range" min="0" max={report.evidence.length} value={cutoff ?? report.evidence.length} onChange={e => { const n = Number(e.target.value); setCutoff(n); setCutoffTime(n ? report.evidence[n - 1].timestamp : null); }} /></label><p>Current state: {analysis.current_stage ?? "Unmapped"} · {analysis.current_technique ?? "NOT AVAILABLE"}. Status: {analysis.future_prediction.current_mapping_status}. Only this evidence prefix supplies prediction inputs.</p><FuturePrediction prediction={analysis.future_prediction} /><details><summary>Dataset Demonstration Scenario - Synthetic next-stage prediction</summary><PredictionDetails prediction={analysis.synthetic_prediction} /></details></section>}
      {view === "graph" && graph && <section className="case-panel"><h2>Evidence-derived relationships</h2><p>{graph.nodes.length} entities · {graph.edges.length} temporal edges. Select an entity to inspect its relationships.</p>
        <div className="case-graph"><svg viewBox="0 0 1000 560" role="img" aria-label="Temporal provenance graph">
          <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#4de7e0" /></marker></defs>
          {graph.edges.map(e => {
            const point = (node: string) => { const i = graph.nodes.findIndex(n => n.id === node); const a = i * 2 * Math.PI / graph.nodes.length; return { x: 500 + 350 * Math.cos(a), y: 275 + 210 * Math.sin(a) }; };
            const a = point(e.source), b = point(e.target); const linked = !selectedNode || selectedNode === e.source || selectedNode === e.target;
            return <g key={e.evidence_id} opacity={linked ? 1 : .15}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#4de7e0" strokeWidth="1.5" markerEnd="url(#arrow)" /><text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 8} fill="#b9cad9" fontSize="11">{e.action}</text></g>;
          })}
          {graph.nodes.map((n, i) => { const a = i * 2 * Math.PI / graph.nodes.length; return <g key={n.id} transform={`translate(${500 + 350 * Math.cos(a)},${275 + 210 * Math.sin(a)})`}>
            <rect x="-82" y="-28" width="164" height="56" rx="10" fill={selectedNode === n.id ? "#174643" : "#111f2d"} stroke="#4de7e0" /><text textAnchor="middle" y="-6" fill="#74a7ff" fontSize="10">{n.type.toUpperCase()}</text><text textAnchor="middle" y="14" fill="#edf5fb" fontSize="12">{n.label.length > 23 ? n.label.slice(0, 20) + "…" : n.label}</text></g>; })}
        </svg></div>
        <div className="case-actions"><button onClick={() => setSelectedNode(null)}>All entities</button>{graph.nodes.map(n => <button aria-pressed={selectedNode === n.id} key={n.id} onClick={() => setSelectedNode(n.id)}>{n.label}</button>)}</div>
        <div className="case-table-wrap"><table><thead><tr><th>Evidence</th><th>Time</th><th>Relationship</th><th>ATT&amp;CK</th></tr></thead><tbody>{graph.edges.filter(e => !selectedNode || e.source === selectedNode || e.target === selectedNode).map(e => <tr key={e.evidence_id}><td>{e.evidence_id}</td><td>{e.timestamp}</td><td>{graph.nodes.find(n => n.id === e.source)?.label} → {e.action} → {graph.nodes.find(n => n.id === e.target)?.label}</td><td>{e.technique_id ?? "Unmapped"}</td></tr>)}</tbody></table></div>
      </section>}

      {view === "evidence" && <section className="case-panel"><h2>Evidence inventory</h2><div className="case-toolbar"><input aria-label="Search evidence" placeholder="Search ID, source, process or action" value={search} onChange={e => setSearch(e.target.value)} />
        <button disabled={busy} onClick={() => action("Evidence snapshot saved with SHA-256. See Reports for the custody record.", () => request(`/api/workflow/${id}/preserve`, {}))}>Preserve snapshot</button>
        <button disabled={busy} onClick={() => action("Fixture integrity checks refreshed. Full snapshot hashes are shown in Reports.", () => request(`/api/workflow/${id}/verify`, {}))}>Verify integrity</button></div>
        <p>Fixture hashes cover ID, subject, action and object. Snapshot preservation hashes all captured fields; neither proves sensor authenticity.</p>
        <div className="case-table-wrap"><table><thead><tr><th>Evidence</th><th>Source</th><th>Observation</th><th>Volatility</th><th>Fixture hash</th><th>Details</th></tr></thead><tbody>{evidence.map(e => <tr key={e.evidence_id}><td>{e.evidence_id}</td><td>{e.source}</td><td>{e.subject} → {e.action} → {e.object}</td><td>{Math.round(e.volatility * 100)}%</td><td>{report.integrity.find(i => i.evidence_id === e.evidence_id)?.valid ? "Match" : "Mismatch"}</td><td><button onClick={() => setSelectedEvidence(selectedEvidence === e.evidence_id ? null : e.evidence_id)}>Inspect {e.evidence_id}</button></td></tr>)}</tbody></table></div>
        {!evidence.length && <p>No evidence matches this search.</p>}
        <div className="case-table-wrap"><table><thead><tr><th>Evidence</th><th>Trust (heuristic)</th><th>Anomaly risk</th><th>ATT&amp;CK status</th><th>Utility (heuristic)</th></tr></thead><tbody>{analysis?.evidence.filter(e => evidence.some(item => item.evidence_id === e.evidence_id)).map(e => <tr key={e.evidence_id}><td>{e.evidence_id}</td><td>{metric(e.evidence_trust)}</td><td>{metric(e.poisoning_risk)}</td><td>{e.mapping.mapping_status} · {e.mapping.technique_id ?? "Unmapped"}</td><td>{metric(e.forensic_utility)}</td></tr>)}</tbody></table></div>
        {selectedEvidence && analysis?.evidence.find(e => e.evidence_id === selectedEvidence) && <EvidenceQuality evidence={analysis.evidence.find(e => e.evidence_id === selectedEvidence)!} />}
        {selectedEvidence && <div className="case-detail"><h3>{selectedEvidence}</h3><pre>{JSON.stringify(report.evidence.find(e => e.evidence_id === selectedEvidence), null, 2)}</pre></div>}
      </section>}

      {view === "prevention" && <>
        <section className="case-panel"><h2>Prediction context</h2><p>{analysis?.future_prediction.status === "available" ? "Future probabilities weight action-conditioned residual-risk estimates in a configurable additional objective term. Unsupported techniques retain current-state risk as an explicit modeling assumption." : "Future technique prediction unavailable; prevention assessment uses available current-state context."}</p><p>SIMULATED RESEARCH ESTIMATES — no measured causal effects. Analyst uncertainty assumption below remains separate from model predictive entropy.</p>{analysis?.future_prediction.predictions.slice(0, 3).map(p => <p key={p.predicted_technique}>Future prediction influence: {p.predicted_technique} · {(p.probability * 100).toFixed(1)}%</p>)}</section>
        {latest?.response_analysis && <section className="case-panel"><h2>Decision formula and evidence-loss scale</h2><p>Unnormalized advisory cost: base weights total 1.0; the additional future-risk penalty has weight 0.2. With future risk supplied, total weight is 1.2. This is not a probability or measured prevention success; lower scores rank advisory actions. No host action is executed.</p><p>Objective: {latest.response_analysis.objective_formula ?? "Legacy assessment; rerun to record the configured formula"}</p><p>{latest.response_analysis.elc_definition ?? "ELC is utility-weighted loss, not a probability"}. Current ELC maximum: {latest.response_analysis.elc_maximum?.toFixed(3) ?? "Not recorded"}. Normalized loss and ERS range: 0–1.</p><p>Recommendation minimizes the weighted objective. Uncertainty is a model input; action-induced uncertainty change is NOT MEASURED and has no separate objective term.</p></section>}
        <section className="case-panel"><h2>Scenario assumptions</h2><p>Adjust analyst-supplied context before comparing 11 response actions. These defaults are simulation assumptions, not measured incident scores.</p>
          <div className="case-form"><label>Attacker intent<select value={intent} onChange={e => setIntent(e.target.value)}>{["credential_theft", "ransomware", "data_theft", "lateral_movement", "privilege_escalation", "persistence"].map(v => <option key={v}>{v}</option>)}</select></label><label>Previous observed stage<select value={previousStage} onChange={e => setPreviousStage(e.target.value)}>{["Initial Access", "Execution", "Persistence", "Defense Evasion", "Credential Access", "Discovery", "Lateral Movement", "Collection", "Command and Control", "Exfiltration", "Impact"].map(v => <option key={v}>{v}</option>)}</select></label>
          {Object.entries(values).map(([key, value]) => <label key={key}>{key === "prediction_uncertainty" ? "Analyst uncertainty assumption" : key.replaceAll("_", " ")} · {value.toFixed(2)}<input type="range" min="0" max="1" step="0.01" value={value} onChange={e => setValues(v => ({ ...v, [key]: Number(e.target.value) }))} /></label>)}</div>
          <button className="case-primary" disabled={busy} onClick={() => action("Assessment saved. Review the estimates below before recording a simulated response.", assess)}>{busy ? "Working…" : "Run assessment"}</button>
        </section>
        {latest?.response_analysis ? <section className="case-panel"><h2>Response comparison</h2><p>Saved assessment: {new Date(latest.created_at).toLocaleString()} · Suggested action: <strong>{latest.response_analysis.recommended_action}</strong></p><p>Results reflect the saved assessment. Rerun after changing assumptions. Estimates are not validated causal effects.</p>
          <div className="case-table-wrap"><table><thead><tr><th>Action</th><th>Residual risk</th><th>Expected future risk</th><th>Future prediction contribution</th><th>Assumed risk probability mass</th><th>ERS</th><th>ELC</th><th>Business impact</th><th>Cost</th><th>Opportunity</th><th>Objective ↓</th></tr></thead><tbody>{candidates.map(c => <tr key={c.action}><td>{c.action}</td><td>{c.residual_attack_risk.toFixed(3)}</td><td>{c.expected_future_risk?.toFixed(3) ?? "NOT AVAILABLE — rerun assessment"}</td><td>{c.future_prediction_contribution?.toFixed(3) ?? "NOT AVAILABLE"}</td><td>{c.future_risk ? `${(c.future_risk.unsupported_probability_mass * 100).toFixed(1)}%` : "NOT AVAILABLE"}</td><td>{c.evidence_retention_score.toFixed(3)}</td><td>{c.evidence_loss_cost.toFixed(3)}</td><td>{c.business_impact.toFixed(3)}</td><td>{c.response_cost?.toFixed(3)}</td><td>{c.evidence_opportunity_cost?.toFixed(3)}</td><td>{c.objective_score.toFixed(3)}</td></tr>)}</tbody></table></div>
          <div className="case-toolbar"><label>Response to simulate<select value={chosen} disabled={busy} onChange={e => setSelectedAction(e.target.value)}>{candidates.map(c => <option key={c.action}>{c.action}</option>)}</select></label><button disabled={busy || !chosen} className="case-primary" onClick={simulateResponse}>{simulating ? "Preserving & simulating…" : "Preserve & simulate"}</button></div>
          <div ref={simulationFeedback}>
            {simulating && <p role="status">Preserving evidence, verifying the snapshot, and recording the simulation…</p>}
            {error && <div className="case-error" role="alert">{error}{simulation && " The simulation was recorded, but refreshing the incident failed. Use Refresh to reload the audit trail."}</div>}
            {!simulating && notice && <div className="case-notice" role="status">{notice}</div>}
          </div>
          {simulation && <div className="case-detail" aria-label="Preservation and simulation result">
            <h3>Simulation result: {simulation.action}</h3>
            <p>{simulation.simulated && !simulation.host_action_executed ? "SIMULATED ENVIRONMENT — No host action executed" : "NOT AVAILABLE — API did not confirm simulation-only execution."}</p>
            <p>Incident: {simulation.incident_id} · Simulation / audit record: {simulation.id}</p>
            {simulation.preservation ? <>
              <p>Preserved {simulation.preservation.evidence_count} application evidence records. {simulation.preservation.scope}.</p>
              <p>Snapshot ID: {simulation.preservation.snapshot_id}</p>
              <p className="case-hash">SHA-256: {simulation.preservation.sha256}</p>
            </> : <p>Snapshot details: NOT AVAILABLE in this API response. See the linked preservation record in Reports.</p>}
            <p>Snapshot hash verification: {simulation.snapshot_verification}. Preservation audit record: {simulation.preservation_id}</p>
            <p>Predicted evidence retention: {metric(simulation.predicted_outcome.evidence_retention_score)} (saved model estimate; not observed survival).</p>
            <p>Observed post-response evidence survival: NOT MEASURED. {simulation.observed_survival_reason}.</p>
            <details><summary>Evidence at risk (model estimates)</summary>
              <ul>{simulation.evidence_at_risk.map(e => <li key={e.evidence_id}>{e.evidence_id} · {e.artifact_mapping ?? "NOT AVAILABLE — no artifact mapping"} · Predicted survival: {e.predicted_survival === null ? "NOT AVAILABLE — no mapped survival estimate" : metric(e.predicted_survival)} · Predicted loss: {e.predicted_loss === null ? "NOT AVAILABLE — no mapped survival estimate" : metric(e.predicted_loss)}</li>)}</ul>
            </details>
            <Link href={`/reports?incident=${encodeURIComponent(simulation.incident_id)}`}>View preservation and simulation audit trail</Link>
          </div>}
          <h3>Anti-forensic behavior estimates</h3><p>AFIP has low holdout macro-F1. These estimates require analyst review and do not trigger collection automatically.</p><ul>{latest.anti_forensic?.predictions.slice(0, 4).map(p => <li key={p.behavior}>{p.behavior} · {(p.probability * 100).toFixed(1)}% · {p.preservation_action}</li>)}</ul>
        </section> : <section className="case-panel"><p>Run an assessment to generate response comparisons and preservation recommendations.</p></section>}
      </>}

      {view === "reports" && <>
        <section className="case-panel"><h2>Future Attack Prediction</h2><FuturePrediction prediction={report.future_attack_prediction} /></section>
        <section className="case-panel"><h2>Export investigation</h2><p>Includes evidence, integrity checks, analyst context, model estimates, preservation snapshots and simulated-action records.</p><div className="case-actions"><button className="case-primary" disabled={busy} onClick={() => action("Report generated and recorded in the audit trail.", async () => { const exported = await request(`/api/workflow/${id}/report/export`, {}); download(`${id}-forensic-report.json`, exported); })}>Download report</button><button onClick={() => window.print()}>Print report</button></div><details><summary>Dataset/model provenance, prediction records, evidence quality and custody verification</summary><pre>{JSON.stringify(report, null, 2)}</pre></details><h3>Research limitations</h3><ul>{report.limitations.map(item => <li key={item}>{item}</li>)}</ul></section>
        <section className="case-panel"><h2>Audit trail</h2>{!report.audit.length && <p>No actions recorded. Preserve evidence or run a prevention assessment to create the audit trail.</p>}
          {report.audit.map(entry => <article className="case-audit" key={entry.id}><h3>{entry.kind.toUpperCase()} {entry.action ?? ""}</h3><p>{new Date(entry.created_at).toLocaleString()} · {entry.id}</p>{entry.sha256 && <p className="case-hash">SHA-256: {entry.sha256} · {entry.snapshot_integrity_valid ? "Verified" : "Mismatch"}</p>}<details><summary>Record details</summary><pre>{JSON.stringify(entry, null, 2)}</pre></details></article>)}
        </section>
      </>}
    </>}
  </main>;
}
