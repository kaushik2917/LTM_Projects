"use client";

import { API_BASE } from "../lib/api";
import { useEffect, useState } from "react";
const API = API_BASE;
type Metrics = { accuracy?: number; macro_precision?: number; macro_recall?: number; macro_f1?: number; weighted_f1?: number; mae?: number; rmse?: number; r2?: number; class_order?: string[]; confusion_matrix?: number[][]; per_class?: Record<string, { precision: number; recall: number; "f1-score": number; support: number }> };
type Model = { model_version?: string; algorithm: string; train_rows: number; validation_rows?: number; test_rows: number; features: string[]; targets: string[]; training_timestamp?: string; metrics: Metrics; label_limitation?: string };
type Evaluations = { training: { models: Record<string, Model> }; validation?: unknown; diagnostics: { afip: { findings: string[]; holdout_prediction_distribution: Record<string, number> }; poisoning: { findings: string[]; scenario_holdouts: { heldout_attack_scenario: string; metrics: Metrics }[] }; progression?: unknown } | null };
type Scenario = { scenario_name: string; status: string; actual_missing_ratio?: number; mean_evidence_trust?: number; robustness_degradation?: number | null; uncertainty?: number | null; reason?: string; operators?: string[] };
type Benchmark = { status: string; run_id?: string; executed_at?: string; selection?: string; coverage_reason?: string; scenarios: Scenario[]; limitations?: string[] };
const fmt = (v: number | null | undefined) => v == null ? "NOT MEASURED" : v.toFixed(4);

export default function EvaluationPanel() {
  const [evaluation, setEvaluation] = useState<Evaluations | null>(null);
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState("");
  const [importResult, setImportResult] = useState<unknown>(null);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(["evaluations", "benchmark"].map(async endpoint => {
      const r = await fetch(`${API}/api/research/${endpoint}`, { signal: controller.signal });
      if (!r.ok) { if (endpoint === "benchmark" && r.status === 503) return null; throw new Error(`${endpoint}: ${r.status}`); }
      return r.json();
    })).then(([e, b]) => { setEvaluation(e); setBenchmark(b); }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, []);
  async function run<T>(path: string, data: unknown, setter: (v: T) => void) {
    setBusy(true); setError("");
    try { const r = await fetch(`${API}/api/research/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }); const result = await r.json(); if (!r.ok) throw new Error(JSON.stringify(result.detail)); setter(result as T); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <div className="case-workspace research-sections">
    {error && <p role="alert" className="case-error">{error}</p>}
    <section className="case-panel"><h2>Import real telemetry</h2><p>Place an actual eCAR JSONL or gzip file in <code>data/optc/</code>, then enter its filename. Ground-truth PDFs and incomplete downloads are not event data. Import is limited to 100,000 records per request; use the CLI for larger windows.</p>
      <div className="case-toolbar"><input aria-label="OpTC filename" value={file} placeholder="sample.json.gz" onChange={e => setFile(e.target.value)} /><button disabled={busy || !file} onClick={() => run("dataset/import", { filename: file }, setImportResult)}>Import OpTC file</button></div>
      {importResult != null && <pre>{JSON.stringify(importResult, null, 2)}</pre>}
    </section>
    <section className="case-panel"><h2>Model readiness & detailed holdout evaluation</h2><p>TRAINING, VALIDATION and HOLDOUT counts are shown separately. No final-benchmark rows are used for fitting. Accuracy alone is insufficient for imbalanced anti-forensic classification.</p>
      {Object.entries(evaluation?.training.models ?? {}).map(([name, m]) => <details className="case-audit" key={name}><summary>{name.toUpperCase()} · {m.algorithm} · {m.train_rows} training / {m.validation_rows ?? 0} validation / {m.test_rows} holdout</summary>
        <p>Artifact version (SHA-256): <span className="case-hash">{m.model_version ?? "NOT RECORDED"}</span></p><p>Trained: {m.training_timestamp ?? "NOT RECORDED"}. {m.label_limitation}</p>
        <div className="quality-grid">{Object.entries(m.metrics).filter(([, v]) => typeof v === "number").map(([k, v]) => <div key={k}><small>{k}</small><strong>{fmt(v as number)}</strong></div>)}</div>
        {m.metrics.class_order && <><h3>Per-class holdout results</h3><div className="case-table-wrap"><table><thead><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead><tbody>{m.metrics.class_order.map(label => { const row = m.metrics.per_class?.[label]; return <tr key={label}><td>{label}</td><td>{fmt(row?.precision)}</td><td>{fmt(row?.recall)}</td><td>{fmt(row?.["f1-score"])}</td><td>{row?.support}</td></tr>; })}</tbody></table></div>
          <h3>Confusion matrix (rows: actual; columns: predicted)</h3><div className="case-table-wrap"><table><thead><tr><th>Actual / predicted</th>{m.metrics.class_order.map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{m.metrics.confusion_matrix?.map((row, i) => <tr key={i}><th>{m.metrics.class_order?.[i]}</th>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table></div></>}
        <details><summary>Features, targets, hyperparameters and split checks</summary><pre>{JSON.stringify(m, null, 2)}</pre></details>
      </details>)}
    </section>
    <section className="case-panel"><h2>AFIP and poisoning investigations</h2>
      {evaluation?.diagnostics?.afip.findings.map(f => <p key={f}>{f}</p>)}
      <p>AFIP holdout prediction counts: {JSON.stringify(evaluation?.diagnostics?.afip.holdout_prediction_distribution)}</p>
      {evaluation?.diagnostics?.poisoning.findings.map(f => <p key={f}>{f}</p>)}
      <div className="case-table-wrap"><table><thead><tr><th>Withheld attack scenario</th><th>Accuracy</th><th>Macro-F1</th></tr></thead><tbody>{evaluation?.diagnostics?.poisoning.scenario_holdouts.map(p => <tr key={p.heldout_attack_scenario}><td>{p.heldout_attack_scenario}</td><td>{fmt(p.metrics.accuracy)}</td><td>{fmt(p.metrics.macro_f1)}</td></tr>)}</tbody></table></div>
      <details><summary>Leakage checks, duplicate checks and feature-label analysis</summary><pre>{JSON.stringify(evaluation?.diagnostics, null, 2)}</pre></details>
      <details><summary>Data validation warnings and metadata checks</summary><pre>{JSON.stringify(evaluation?.validation, null, 2)}</pre></details>
    </section>
    <section className="case-panel"><h2>FAPT-Bench execution & robustness</h2><p>Execute deterministic corruption operators on the six-event fixture, using scenario descriptors from FAPT-Bench 2.0. This measures fixture retention, evidence-quality changes and prediction stability. It is not real-world validation or a replay of every CSV row.</p>
      <button disabled={busy} onClick={() => run("benchmark/run", {}, setBenchmark)}>{busy ? "Running…" : "Run fixture benchmark"}</button>
      <p>{benchmark?.status ?? "NOT RUN"} · {benchmark?.executed_at}</p><p>{benchmark?.selection}</p><p>{benchmark?.coverage_reason ?? "Coverage not measured — requires observed replay outcomes."}</p>
      {Array.isArray(benchmark?.scenarios) && <div className="case-table-wrap"><table><thead><tr><th>Scenario</th><th>Status</th><th>Missing ratio (measured)</th><th>Trust index</th><th>Distribution change</th><th>Entropy</th></tr></thead><tbody>{benchmark.scenarios.map(s => <tr key={s.scenario_name}><td>{s.scenario_name}</td><td>{s.status}</td><td>{fmt(s.actual_missing_ratio)}</td><td>{fmt(s.mean_evidence_trust)}</td><td>{fmt(s.robustness_degradation)}</td><td>{fmt(s.uncertainty)}</td></tr>)}</tbody></table></div>}
      <p>Prediction accuracy, technique metrics, true trust/utility error and observed post-response survival remain NOT MEASURED where labels or acquisition outcomes are absent.</p>
      <details><summary>Benchmark details and limitations</summary><pre>{JSON.stringify(benchmark, null, 2)}</pre></details>
    </section>
  </div>;
}
