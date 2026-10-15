"use client";

import { API_BASE } from "../../lib/api";

import Link from "next/link";
import { useEffect, useState } from "react";
import EvaluationPanel from "../../components/evaluation-panel";
import FutureEvaluation from "../../components/future-evaluation";
import PredictionBenchmark from "../../components/prediction-benchmark";
import ProspectiveEvaluation from "../../components/prospective-evaluation";

const API = API_BASE;
type Dataset = { id: string; dataset_name?: string; filename: string; rows: number; usage: string; modules: string[] };
type Model = { train_rows: number; test_rows: number; metrics: { mae?: number; accuracy?: number; macro_f1?: number } };
type Status = { datasets: Dataset[]; optc: { status: string; events: number }; attack: { status: string; version: string }; training: { models: Record<string, Model> } | null };
type Candidate = { action: string; residual_attack_risk: number; evidence_retention_score: number; evidence_loss_cost: number; objective_score: number; business_impact: number };
type Result = { candidates?: Candidate[]; recommended_action?: string; [key: string]: unknown };
const panel = { padding: 24, border: "1px solid #334155", borderRadius: 12, marginTop: 20, background: "#111827" };
const button = { padding: "10px 18px", borderRadius: 6, background: "#2563eb", color: "white", cursor: "pointer", marginRight: 10 };

export default function ResearchPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [examples, setExamples] = useState<Record<string, unknown>>({});
  const [mode, setMode] = useState("responses");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const responses = await Promise.all(["datasets", "examples"].map(path => fetch(`${API}/api/research/${path}`, { signal: controller.signal })));
        if (responses.some(r => !r.ok)) throw new Error("Research API unavailable. Start the backend with the research environment.");
        const [data, samples] = await Promise.all(responses.map(r => r.json()));
        setStatus(data); setExamples(samples); setInput(JSON.stringify(samples.responses, null, 2));
      } catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    }
    load();
    return () => controller.abort();
  }, []);

  async function run() {
    setBusy(true); setError(""); setResult(null);
    try {
      const body = JSON.stringify(JSON.parse(input));
      const response = await fetch(`${API}/api/research/${mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
      const data = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(data.detail));
      setResult(data);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return <main style={{ minHeight: "100vh", background: "#030712", color: "#e2e8f0", padding: "40px 5%", fontFamily: "Arial, sans-serif" }}>
    <Link href="/" style={{ color: "#93c5fd" }}>← Command center</Link>
    <h1 style={{ fontSize: 32, marginTop: 20 }}>FAPT-Guard dataset research</h1>
    <p>Dataset-trained baselines · Advisory responses · No host actions executed</p>
    <section style={panel}>
      <h2>Data readiness</h2>
      {!status && <p>Loading dataset status…</p>}
      {status && <>
        <p>OpTC: {status.optc.status} ({status.optc.events.toLocaleString()} events) · ATT&amp;CK {status.attack.version}: {status.attack.status}</p>
        <div style={{ overflowX: "auto" }}><table style={{ width: "100%", textAlign: "left", borderSpacing: "0 14px" }}>
          <thead><tr><th>Dataset</th><th>Rows</th><th>Use</th><th>Modules</th></tr></thead>
          <tbody>{status.datasets.map(d => <tr key={d.id}><td>{d.dataset_name ?? d.filename}</td><td>{d.rows.toLocaleString()}</td><td>{d.usage}</td><td>{d.modules.join(", ")}</td></tr>)}</tbody>
        </table></div>
      </>}
    </section>
    <section style={panel}>
      <h2>Holdout results</h2>
      <p>Agreement with research labels is not real-world validation. AFIP has low macro-F1; its behavior predictions require analyst review. Trust inputs include upstream corruption indicators.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, marginTop: 16 }}>
        {Object.entries(status?.training?.models ?? {}).map(([name, m]) => <div key={name}>
          <strong>{name.toUpperCase()}</strong><p>{m.test_rows.toLocaleString()} holdout rows</p>
          {m.metrics.mae !== undefined && <p>MAE: {m.metrics.mae.toFixed(4)}</p>}
          {m.metrics.accuracy !== undefined && <p>Accuracy: {(100 * m.metrics.accuracy).toFixed(1)}%</p>}
          {m.metrics.macro_f1 !== undefined && <p>Macro-F1: {m.metrics.macro_f1.toFixed(3)}</p>}
        </div>)}
      </div>
    </section>
    <section style={panel}>
      <h2>Dataset Demonstration Scenario — not linked to INC-00001</h2>
      <p>Edit the context to compare response survival estimates or inspect anti-forensic and trust predictions. Examples are demonstrations, not test-set results.</p>
      <label htmlFor="model-mode">Analysis </label>
      <select id="model-mode" value={mode} disabled={busy} style={{ color: "#111", padding: 8, margin: "16px 0" }} onChange={e => { setMode(e.target.value); setInput(JSON.stringify(examples[e.target.value], null, 2)); setResult(null); }}>
        <option value="responses">Response comparison</option><option value="anti-forensic">Anti-forensic behavior</option><option value="trust">Evidence trust / poisoning</option>
      </select>
      <label htmlFor="context-input" style={{ display: "block" }}>Incident / evidence context (JSON)</label>
      <textarea id="context-input" value={input} onChange={e => setInput(e.target.value)} spellCheck={false} style={{ width: "100%", minHeight: 270, background: "#030712", color: "#cbd5e1", padding: 16, margin: "12px 0", fontFamily: "monospace" }} />
      <button style={button} disabled={busy || !status} onClick={run}>{busy ? "Computing…" : "Run analysis"}</button>
      {error && <p role="alert" style={{ color: "#fca5a5", marginTop: 16 }}>{error}</p>}
      {result?.candidates && <div style={{ overflowX: "auto", marginTop: 24 }}>
        <p>Advisory recommendation: <strong>{result.recommended_action}</strong>. Estimates are not validated causal effects.</p>
        <table style={{ width: "100%", textAlign: "left", borderSpacing: "0 14px" }}><thead><tr><th>Action</th><th>Residual risk</th><th>ERS</th><th>ELC</th><th>Business impact</th><th>Objective ↓</th></tr></thead>
          <tbody>{result.candidates.map(c => <tr key={c.action}><td>{c.action}</td><td>{c.residual_attack_risk.toFixed(3)}</td><td>{c.evidence_retention_score.toFixed(3)}</td><td>{c.evidence_loss_cost.toFixed(3)}</td><td>{c.business_impact.toFixed(3)}</td><td>{c.objective_score.toFixed(3)}</td></tr>)}</tbody>
        </table>
      </div>}
      {result && <details style={{ marginTop: 20 }} open={!result.candidates}><summary>Full analysis</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(result, null, 2)}</pre></details>}
    </section>
    <section style={panel}><h2>Dataset provenance</h2><p>File hashes, source, version, import date, feature/target counts and per-model split sizes are taken from the stored manifest. Unknown versions and raw-event counts remain null.</p><details><summary>Inspect dataset provenance</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 500, overflowY: "auto" }}>{JSON.stringify(status?.datasets, null, 2)}</pre></details></section>
    <FutureEvaluation />
    <ProspectiveEvaluation />
    <PredictionBenchmark />
    <EvaluationPanel />
  </main>;
}
