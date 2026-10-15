"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/api";

type Metrics = { top_1_accuracy: number; top_3_accuracy: number | null; macro_precision: number; macro_recall: number; macro_f1: number; coverage: number; abstention_rate: number; expected_calibration_error: number; multiclass_brier_score: number; selective_accuracy: number | null; top_1_wilson_95: number[] };
type Report = { status: string; reason?: string; limitation: string; evaluation_scope?: string; model_name?: string; model_version?: string; model_hash?: string; calibration_status?: string; target_top1_accuracy?: number; target_achieved?: boolean; frozen_config?: { test_disclosure: string }; manifest?: { dataset_version: string; source_sha256: string; sequences: number; events: number; samples: number; classes: string[]; protocol: string; splits: { test: { scenario_ids: string[] } } }; results?: Record<string, Metrics> };
const number = (value: number | null) => value === null ? "NOT MEASURED" : value.toFixed(4);

export default function PredictionBenchmark() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [example, setExample] = useState<unknown>(null);
  const [exampleError, setExampleError] = useState("");
  const [busy, setBusy] = useState(false);
  async function inspectExample() {
    const id = report?.manifest?.splits.test.scenario_ids[0];
    if (!id) return;
    setBusy(true); setExampleError("");
    try {
      const response = await fetch(`${API_BASE}/api/research/prediction-benchmark/examples/${encodeURIComponent(id)}`);
      const body = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${JSON.stringify(body.detail ?? body)}`);
      setExample(body);
    } catch (exception) { setExampleError(String(exception)); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(`${API_BASE}/api/research/prediction-benchmark`, { signal: controller.signal });
        const body = await response.json();
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${JSON.stringify(body.detail ?? body)}`);
        setReport(body);
      } catch (exception) { if (!controller.signal.aborted) setError(String(exception)); }
    }
    load();
    return () => controller.abort();
  }, []);
  return <section aria-label="Chronological prediction benchmark" style={{ padding: 24, border: "1px solid #334155", borderRadius: 12, marginTop: 20 }}>
    <h2>Offline temporal prediction performance</h2><p><strong>Historical experiment: CHRONOLOGICAL-V2</strong>. Dataset v2.0.0; one midpoint per sequence; 700 train / 100 selection / 50 calibration / 150 previously exposed test. These historical values are preserved, not the prospective evaluation.</p>
    {error && <p role="alert">{error}</p>}
    {!report && !error && <p>Loading measured benchmark...</p>}
    {report && <>
      <p>{report.evaluation_scope ?? report.status}</p><p>{report.limitation}</p>
      {report.reason && <p>{report.reason}</p>}
      {report.manifest && <><p>Dataset {report.manifest.dataset_version}: {report.manifest.sequences} sequences, {report.manifest.events} events, {report.manifest.samples} labelled samples, {report.manifest.classes.length} classes.</p><p>{report.manifest.protocol}</p></>}
      {report.results && <>
        {report.frozen_config && <p>{report.frozen_config.test_disclosure}</p>}
        <p>Research target: {report.target_top1_accuracy === undefined ? "NOT AVAILABLE" : `${100 * report.target_top1_accuracy}%`}. Status: {report.target_achieved === undefined ? "NOT MEASURED" : report.target_achieved ? "ACHIEVED" : "NOT ACHIEVED"}. Measured FAPT-Guard Top-1: {(100 * report.results["FAPT-Guard"].top_1_accuracy).toFixed(2)}%.</p>
        <p>Accuracy, precision, recall and F1 cover every test sample before abstention. Coverage uses the existing probability and entropy thresholds. These are synthetic generator labels, not validated ground truth.</p>
        <p>Table values are fractions from 0 to 1; Brier score is a multiclass squared probability error.</p>
        <div style={{ overflowX: "auto" }}><table style={{ width: "100%", textAlign: "left", borderSpacing: "12px" }}>
          <thead><tr>{["Model", "Top-1", "Top-3", "Precision (macro)", "Recall (macro)", "Macro F1", "Coverage", "Abstention", "Covered accuracy", "Brier", "ECE"].map(label => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{Object.entries(report.results).map(([name, m]) => <tr key={name}><th>{name}</th>{[m.top_1_accuracy, m.top_3_accuracy, m.macro_precision, m.macro_recall, m.macro_f1, m.coverage, m.abstention_rate, m.selective_accuracy, m.multiclass_brier_score, m.expected_calibration_error].map((value, index) => <td key={index}>{number(value)}</td>)}</tr>)}</tbody>
        </table></div>
        <p>{report.calibration_status}. Operational defense remains gated on validated observed-data models.</p>
        <p>Model: {report.model_name} / {report.model_version}</p>
        <button type="button" disabled={busy} onClick={inspectExample}>{busy ? "Loading prediction..." : "Inspect fixed test example"}</button>
        {exampleError && <p role="alert">{exampleError}</p>}
        {example !== null && <div aria-label="Frozen test prediction"><p>SYNTHETIC RESEARCH — No host action executed. Hindsight annotation is not validated ground truth.</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(example, null, 2)}</pre></div>}
        <details><summary>Manifest, model hashes, confidence intervals and confusion matrices</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 500, overflowY: "auto" }}>{JSON.stringify(report, null, 2)}</pre></details>
      </>}
    </>}
  </section>;
}
