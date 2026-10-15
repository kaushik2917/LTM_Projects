"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "../lib/api";

type Metrics = Record<string, number | number[] | null>;
type Report = { status: string; reason?: string; scope: string; experiment_id: string; test_sequences: number; test_dataset_sha256: string; limitations: string; frozen: { model_hash: string; selected: { kind: string }; sample_counts: Record<string, number>; temperatures: Record<string, number>; frozen_at: string }; results: Record<string, Metrics> };
const columns = ["top_1_accuracy", "top_3_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1", "multiclass_brier_score", "expected_calibration_error", "coverage", "abstention_rate", "conformal_coverage", "average_prediction_set_size"];

export default function ProspectiveEvaluation() {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/api/research/prospective-prediction`, { signal: controller.signal }).then(async response => {
      const body = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${JSON.stringify(body.detail)}`);
      setData(body);
    }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, []);
  return <section className="case-panel" aria-label="Prospective temporal evaluation">
    <h2>PROSPECTIVE-V1 — frozen synthetic evaluation</h2>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Loading prospective results...</p>}
    {data?.status !== "EVALUATED" && data && <p>{data.status}: {data.reason}</p>}
    {data?.status === "EVALUATED" && <>
      <p>{data.scope}. Dataset: existing v2.0.0 development / prospective-v1 test. Model selected: {data.frozen.selected.kind}.</p>
      <p>Partitions: {Object.entries(data.frozen.sample_counts).map(([name, count]) => `${name}: ${count}`).join("; ")}; prospective test: {data.test_sequences}. Every model uses these same test samples.</p>
      <p>Frozen: {data.frozen.frozen_at}. Model SHA-256: {data.frozen.model_hash}. Test SHA-256: {data.test_dataset_sha256}.</p>
      <p>Accuracy includes all test samples before abstention. Coverage means predictions passing the unchanged gate; conformal coverage means inclusion of the true synthetic label in the prediction set. These are different quantities. Fractions use 0–1; set size counts classes.</p>
      <div className="case-table-wrap"><table><thead><tr><th>Model</th>{columns.map(key => <th key={key}>{key.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{Object.entries(data.results).map(([name, result]) => <tr key={name}><th>{name}</th>{columns.map(key => <td key={key}>{typeof result[key] === "number" ? result[key].toFixed(4) : "NOT MEASURED"}</td>)}</tr>)}</tbody></table></div>
      <p>{data.limitations}</p>
      <p>INC-00001 remains a separate SYNTHETIC DEMONSTRATION / NOT REAL-WORLD VALIDATION. Its class probability is not benchmark accuracy. Operational telemetry remains subject to the observed-data abstention gate; DRY_RUN is not prevention success.</p>
      <details><summary>Validation candidates, calibration, per-class metrics, confusion matrices and confidence intervals</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
    </>}
  </section>;
}
