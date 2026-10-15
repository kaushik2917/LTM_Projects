"use client";

import { API_BASE } from "../lib/api";
import { useEffect, useState } from "react";
import { FuturePrediction, Prediction, metric } from "./research-analysis";

type Scenario = { scenario_id: string; incident_id: string; default_cutoff: string; cutoffs: string[] };
export type Experiment = { status: string; reason?: string; dataset_version: string; model_version: string; evaluation_id: string; split_checks: { scenario_counts: Record<string, number> }; sample_counts: Record<string, number>; metrics: Record<string, number>; partition_metrics: unknown; calibration: { temperature: number; ECE: number; Brier_score: number }; conformal: { target_coverage: number; measured_coverage: number; average_prediction_set_size: number; minimum_prediction_set_size: number; maximum_prediction_set_size: number; coverage_sample_count: number; reason: string } };
const api = API_BASE;
async function request(path: string, body?: object) {
  const response = await fetch(api + "/api/research/" + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  return data;
}

export default function TemporalDemonstration({ experiment }: { experiment: Experiment }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("");
  const [cutoff, setCutoff] = useState("");
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    request("temporal-scenarios").then((items: Scenario[]) => {
      if (active) { setScenarios(items); setScenario(items[0]?.scenario_id ?? ""); setCutoff(items[0]?.default_cutoff ?? ""); }
    }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, []);
  async function run(reveal = false) {
    setBusy(true); setError("");
    try {
      const result = await request(`temporal-scenarios/${scenario}/${reveal ? "reveal" : "predict"}`, reveal ? { prediction_id: prediction?.prediction_id } : { cutoff_timestamp: cutoff });
      setPrediction(result);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function downloadReport() {
    setBusy(true); setError("");
    try {
      const report = await request(`temporal-scenarios/${scenario}/report`, { prediction_id: prediction?.prediction_id });
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${scenario}-prediction-report.json`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  const observed = prediction?.observed_prefix as { evidence_id: string; timestamp: string; subject: string; action: string; object: string; technique_id: string }[] | undefined;
  const truth = prediction?.ground_truth as { status: string; event?: { evidence_id: string; timestamp: string; subject: string; action: string; object: string; technique_id: string } } | undefined;
  if (experiment.status !== "evaluated") return <p role="alert">{experiment.reason}</p>;
  return <section className="case-panel" aria-label="Synthetic evaluation demonstration">
    <h2>Synthetic Evaluation / Demonstration</h2><p><strong>Historical experiment: V2-RANDOM-TRANSITION</strong>. Transition-frequency model; randomly assigned scenario groups, not a chronological holdout. This is a different experiment from CHRONOLOGICAL-V2 and PROSPECTIVE-V1.</p><p>Evaluation ID: {experiment.evaluation_id}. Model SHA-256: {experiment.model_version}. Sample counts: {Object.entries(experiment.sample_counts).map(([part, count]) => `${part}: ${count}`).join("; ")}.</p>
    <p>Dataset v{experiment.dataset_version}. SYNTHETIC RESEARCH — Not real-world validated. No host action executed.</p>
    <p>Scenarios: {Object.entries(experiment.split_checks.scenario_counts).map(([k,v]) => `${k.replaceAll("_", " ")}: ${v}`).join("; ")}. One predetermined cutoff per held-out scenario. Interactive cutoff changes below do not alter the frozen test metrics.</p>
    <table><thead><tr><th>Held-out test metric</th><th>Calculated value</th></tr></thead><tbody>{["top_1_accuracy", "top_3_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1"].map(k => <tr key={k}><td>{k.replaceAll("_", " ")}</td><td>{metric(experiment.metrics[k])}</td></tr>)}</tbody></table>
    <p>Probability calibration — ECE: {experiment.calibration.ECE.toFixed(4)}; Brier: {experiment.calibration.Brier_score.toFixed(4)} on the independent calibration diagnostic subgroup. Fitted temperature: {experiment.calibration.temperature.toFixed(2)}.</p>
    <p>Conformal target: {metric(experiment.conformal.target_coverage)}. Empirical test coverage: {metric(experiment.conformal.measured_coverage)} on {experiment.conformal.coverage_sample_count} scenarios. Average set size: {experiment.conformal.average_prediction_set_size.toFixed(2)}; minimum {experiment.conformal.minimum_prediction_set_size}, maximum {experiment.conformal.maximum_prediction_set_size}.</p>
    <p>{experiment.conformal.reason}</p>
    <details><summary>Confusion matrix, per-class metrics, raw/calibrated reliability and provenance</summary><pre>{JSON.stringify(experiment, null, 2)}</pre></details>
    <div className="case-form"><label>Synthetic scenario<select disabled={busy} value={scenario} onChange={e => { setScenario(e.target.value); setCutoff(scenarios.find(s => s.scenario_id === e.target.value)!.default_cutoff); setPrediction(null); }}>{scenarios.map(s => <option key={s.scenario_id}>{s.scenario_id}</option>)}</select></label>
      <label>Prediction cutoff<select disabled={busy} value={cutoff} onChange={e => { setCutoff(e.target.value); setPrediction(null); }}>{scenarios.find(s => s.scenario_id === scenario)?.cutoffs.map(c => <option key={c}>{c}</option>)}</select></label></div>
    <button disabled={busy || !scenario} onClick={() => run()}>Predict observed prefix</button>
    {prediction && <button disabled={busy || truth?.status === "OBSERVED"} onClick={() => run(true)}>Reveal hidden ground truth</button>}
    {prediction && <button disabled={busy} onClick={downloadReport}>Export demonstration report</button>}
    {busy && <p role="status">Calculating and saving audit record…</p>}{error && <p role="alert">{error}</p>}
    {prediction && <><h3>Observed prefix — temporal relationships</h3>
      <div className="case-graph"><svg role="img" aria-label="Observed synthetic temporal graph" viewBox={`0 0 1000 ${(observed?.length ?? 1) * 75 + 20}`}><title>Observed prefix only; labels are synthetic annotations</title>{observed?.map((e, i) => <g key={e.evidence_id} transform={`translate(0 ${i * 75 + 10})`}>
        <rect x="15" y="8" width="235" height="40" rx="5" fill="#142a37" stroke="#4de7e0" /><text x="25" y="32" fill="#dcebf4" fontSize="12">{e.subject.length > 29 ? e.subject.slice(0, 26) + "…" : e.subject}</text>
        <line x1="250" y1="28" x2="735" y2="28" stroke="#4de7e0" /><path d="M725 22 L735 28 L725 34" fill="none" stroke="#4de7e0" />
        <text x="270" y="20" fill="#dcebf4" fontSize="12">{e.action} · {e.technique_id}</text><text x="270" y="47" fill="#a6b7c7" fontSize="11">{e.evidence_id} · {e.timestamp}</text>
        <rect x="735" y="8" width="250" height="40" rx="5" fill="#142a37" stroke="#4de7e0" /><text x="745" y="32" fill="#dcebf4" fontSize="12">{e.object.length > 30 ? e.object.slice(0, 27) + "…" : e.object}</text>
      </g>)}</svg></div>
      <div className="case-table-wrap"><table><thead><tr><th>Evidence / time</th><th>Subject → action → object</th><th>Annotated technique</th></tr></thead><tbody>{observed?.map(e => <tr key={e.evidence_id}><td>{e.evidence_id}<br />{e.timestamp}</td><td>{e.subject} → {e.action} → {e.object}</td><td>{e.technique_id}</td></tr>)}</tbody></table></div>
      <h3>Model prediction</h3><FuturePrediction prediction={prediction} />
      <h3>Hidden future ground truth</h3>{truth?.event ? <p data-testid="revealed-future">{truth.event.evidence_id} · {truth.event.timestamp}: {truth.event.subject} → {truth.event.action} → {truth.event.object} · {truth.event.technique_id}. Synthetic annotation revealed after prediction; excluded from model input.</p> : <p>HIDDEN — select Reveal after prediction to evaluate the saved probabilities.</p>}
      <p>Prediction audit ID: {prediction.prediction_id}. Evaluation audit ID: {String(prediction.evaluation_audit_id ?? "Pending reveal")}</p></>}
  </section>;
}
