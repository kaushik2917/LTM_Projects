"use client";

import { API_BASE } from "../lib/api";
import { useEffect, useState } from "react";
import { FuturePrediction, type Prediction, type Calibration, type Conformal } from "./research-analysis";
import TemporalDemonstration, { type Experiment } from "./temporal-demonstration";

type Metrics = { accuracy?: number; macro_precision?: number; macro_recall?: number; top_1_accuracy?: number | null; top_3_accuracy?: number | null; top_5_accuracy?: number | null; macro_f1?: number; weighted_f1?: number; mean_reciprocal_rank?: number; multiclass_brier_score?: number; expected_calibration_error?: number; class_order?: string[]; confusion_matrix?: number[][] };
type Evaluation = { model: Metrics; majority_baseline: Metrics };
type Model = { model_name?: string; model_version?: string; features?: string[]; split_sizes?: Record<string, number>; evaluation?: Record<string, Evaluation>; errors?: unknown; leakage_checks?: unknown; [key: string]: unknown };
type EvaluationRun = { evaluation_id: string; evaluation_timestamp: string; dataset_hash: string; normalized_dataset_hash: string; metrics: Metrics; dataset_statistics: { scenarios: number; sequences: number; distinct_full_sequences: number }; uncertainty: { method: string; mean: number; median: number; class_count: number }; calibration: Calibration; conformal: Conformal };
type Readiness = {
  temporal_experiment?: Experiment;
  demonstration?: Prediction;
  synthetic_temporal?: { status: string; reason?: string; evaluation_run?: EvaluationRun | null; evaluation_error?: string; metadata?: Model & { dataset: { dataset_name: string; version: string; scenario_counts: Record<string, number>; event_count: number; sample_count: number; hash_verification: string; labels_absent_from_active_catalog: string[]; target_classes_absent_from_training: Record<string, string[]> }; candidate_evaluations: Record<string, Record<string, Evaluation>>; selection_rule: string; limitation: string; test_examples: unknown } };
  task_definition: string;
  future: Record<string, { status: string; reason: string | null; metadata: Model | null }>;
  data_audit: { reason: string; datasets?: unknown[]; synthetic_demonstration?: Model & { label: string; error_analysis?: unknown; model?: unknown } };
  robustness_reason: string;
};
const fmt = (v: number | null | undefined) => v == null ? "NOT MEASURED" : v.toFixed(4);

function Results({ evaluation }: { evaluation?: Record<string, Evaluation> }) {
  if (!evaluation) return <p>Accuracy, Top-k, Macro-F1, Weighted-F1, calibration, confusion matrix and prediction errors: NOT MEASURED — no qualified observed-data model has been evaluated.</p>;
  return <>{Object.entries(evaluation).map(([partition, results]) => <details key={partition}>
    <summary>{partition.toUpperCase()} evaluation</summary>
    <div className="case-table-wrap"><table><thead><tr><th>Metric</th><th>Model</th><th>Most frequent label baseline</th></tr></thead><tbody>
      {(["accuracy", "macro_precision", "macro_recall", "top_3_accuracy", "top_5_accuracy", "macro_f1", "weighted_f1", "mean_reciprocal_rank", "multiclass_brier_score", "expected_calibration_error"] as const).map(key => <tr key={key}><td>{key.replaceAll("_", " ")}</td><td>{fmt(results.model[key])}</td><td>{fmt(results.majority_baseline[key])}</td></tr>)}
    </tbody></table></div>
    <p>Brier/ECE describe probability reliability on this partition; no calibration fitting is implied. Top-k is NOT MEASURED when the label space has fewer than k classes.</p>
    <h3>Future task confusion matrix ({partition})</h3>
    <div className="case-table-wrap"><table><thead><tr><th>True technique / predicted</th><th>Support</th>{results.model.class_order?.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{results.model.confusion_matrix?.map((row, i) => <tr key={i}><th>{results.model.class_order?.[i]}</th><td>{row.reduce((sum, n) => sum + n, 0)}</td>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table></div>
    <details><summary>Per-class precision, recall, F1, support and reliability bins</summary><pre>{JSON.stringify(results, null, 2)}</pre></details>
  </details>)}</>;
}

export default function FutureEvaluation() {
  const [data, setData] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/api/research/future-prediction`, { signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error(`Future evaluation API: HTTP ${r.status}`); return r.json(); })
      .then(setData).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, []);
  const synthetic = data?.data_audit.synthetic_demonstration;
  const temporal = data?.synthetic_temporal?.metadata;
  const run = data?.synthetic_temporal?.evaluation_run;
  return <section className="case-panel"><h2>Future Attack Prediction Evaluation</h2>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Loading prediction readiness…</p>}
    {data && <>
      {data.temporal_experiment && <TemporalDemonstration experiment={data.temporal_experiment} />}
      <details><summary>Preserved v1.0.1 benchmark — historical model and evaluation</summary><section aria-label="Synthetic temporal benchmark">
        <h2>Future Attack Prediction — Synthetic Benchmark</h2>
        <p><strong>SYNTHETIC DATASET · NOT REAL-WORLD VALIDATION</strong></p>
        {!temporal ? <p role="status">{data.synthetic_temporal?.reason ?? "Synthetic temporal model NOT AVAILABLE"}</p> : <>
          <p>{temporal.dataset.dataset_name} v{temporal.dataset.version} · SHA-256: {temporal.dataset.hash_verification}</p>
          <p>Synthetic: YES. Real-world validation: NO.</p>
          <p>TRAINING DATA fits transition counts and classifier features. VALIDATION DATA selects the model. HELD-OUT TEST DATA supplies the test metrics below. INC-00001 DEMONSTRATION is a separate application inference case with no measured prediction accuracy.</p>
          <p>Scenarios — Train: {temporal.dataset.scenario_counts.train}, Validation: {temporal.dataset.scenario_counts.validation}, Test: {temporal.dataset.scenario_counts.test}. Events: {temporal.dataset.event_count}. Samples: {temporal.dataset.sample_count}.</p>
          <p>Sample rows — Train: {temporal.split_sizes?.train}, Validation: {temporal.split_sizes?.validation}, Test: {temporal.split_sizes?.test}.</p>
          <p>Model: {temporal.model_name} · Model version: {temporal.model_version}</p>
          <p>{temporal.selection_rule}</p>
          {run ? <section aria-label="Frozen model evaluation">
            <h3>Future Attack Prediction Evaluation — frozen model</h3>
            <p>Evaluation ID: {run.evaluation_id} · Timestamp: {run.evaluation_timestamp}</p>
            <p>Dataset hash: {run.dataset_hash}</p><p>Normalized dataset hash: {run.normalized_dataset_hash}</p>
            <p>Scenarios: {run.dataset_statistics.scenarios}; sequences: {run.dataset_statistics.sequences}; distinct full technique sequences: {run.dataset_statistics.distinct_full_sequences}.</p>
            <table><thead><tr><th>Held-out test metric</th><th>Measured value</th></tr></thead><tbody>{(["top_1_accuracy", "top_3_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1", "mean_reciprocal_rank"] as const).map(k => <tr key={k}><td>{k.replaceAll("_", " ")}</td><td>{fmt(run.metrics[k])}</td></tr>)}</tbody></table>
            <p>Uncertainty method: {run.uncertainty.method}, all {run.uncertainty.class_count} trained classes. Test mean: {fmt(run.uncertainty.mean)}; median: {fmt(run.uncertainty.median)}. These values measure dispersion, not error probability.</p>
            <p>Probability calibration diagnostics: ECE {fmt(run.calibration.ECE)}; Brier score {fmt(run.calibration.Brier_score)}. Samples: {run.calibration.calibration_sample_count}. No probability recalibration fitted.</p>
            <p>Conformal target: {(run.conformal.target_coverage * 100).toFixed(0)}% (design target). Measured coverage: {fmt(run.conformal.measured_coverage)}. Average prediction set size: {fmt(run.conformal.average_prediction_set_size)}. Evaluated coverage samples: {run.conformal.coverage_sample_count}.</p>
            <p>{run.conformal.reason}</p>
            <details><summary>Evaluation run, split checks and calibration provenance</summary><pre>{JSON.stringify(run, null, 2)}</pre></details>
          </section> : <p>{data.synthetic_temporal?.evaluation_error ?? "NOT MEASURED — evaluation run unavailable"}</p>}
          <p>Training labels are normalized using the pinned ATT&amp;CK replacement relationships. Inactive output IDs: {temporal.dataset.labels_absent_from_active_catalog.join(", ") || "None"}. Original CSV files remain preserved.</p>
          <details><summary>ATT&amp;CK technique validation and normalization</summary><pre>{JSON.stringify((temporal.dataset as unknown as Record<string, unknown>).normalization, null, 2)}</pre></details>
          <p>Target classes absent from training — Validation: {temporal.dataset.target_classes_absent_from_training.validation.join(", ") || "None"}; Test: {temporal.dataset.target_classes_absent_from_training.test.join(", ") || "None"}. The model cannot predict unseen classes.</p>
          <Results evaluation={temporal.evaluation} />
          <details><summary>Candidate model comparisons</summary>{Object.entries(temporal.candidate_evaluations).map(([name, evaluation]) => <div key={name}><h3>{name}</h3><Results evaluation={evaluation} /></div>)}</details>
          <details><summary>Synthetic held-out prediction examples</summary><pre>{JSON.stringify(temporal.test_examples, null, 2)}</pre></details>
          <details><summary>Temporal dataset, hashes, split checks and model provenance</summary><pre>{JSON.stringify(temporal, null, 2)}</pre></details>
          <p>{temporal.limitation}</p>
          <details><summary>INC-00001 DEMONSTRATION — separate from held-out test data</summary>
            <p>This incident is not a training or held-out test sample. It has no measured future ground truth. Its probabilities are model output, not test accuracy.</p>
            {data.demonstration && <FuturePrediction prediction={data.demonstration} />}
          </details>
        </>}
      </section></details>
      <p>{data.task_definition}</p>
      <p>TRAINING fits the model. VALIDATION and HOLDOUT contain separate incident/scenario/collection groups. FINAL BENCHMARK: future prediction robustness NOT MEASURED. The fixture benchmark below remains a synthetic stress test.</p>
      {Object.entries(data.future).map(([task, item]) => <div key={task}>
        <h3>Observed-data next {task}: {item.status === "evaluated" ? "DATASET EVALUATED" : "NOT AVAILABLE"}</h3>
        <p>{item.reason}</p>
        <p>TRAINING rows: {item.metadata?.split_sizes?.training ?? "NOT AVAILABLE"} · VALIDATION rows: {item.metadata?.split_sizes?.validation ?? "NOT AVAILABLE"} · HOLDOUT rows: {item.metadata?.split_sizes?.holdout ?? "NOT AVAILABLE"}</p>
        <p>Uncertainty method: normalized predictive entropy when a model is available; not a calibrated error probability. Coverage: NOT MEASURED.</p>
        <Results evaluation={item.metadata?.evaluation} />
        <details><summary>Model, features, provenance, split checks and error analysis ({task})</summary><pre>{JSON.stringify(item.metadata ?? { reason: item.reason, error_analysis: "NOT AVAILABLE — no observed future targets" }, null, 2)}</pre></details>
      </div>)}
      <details><summary>Available datasets: schemas, counts, hashes and future-label readiness</summary><pre>{JSON.stringify(data.data_audit.datasets, null, 2)}</pre></details>
      <details><summary>Dataset Demonstration Scenario - Synthetic next-stage evaluation</summary>
        <p>{synthetic?.label ?? "NOT AVAILABLE — run the prediction audit"}</p>
        <p>TRAINING: {synthetic?.split_sizes?.training ?? "NOT AVAILABLE"} · VALIDATION: {synthetic?.split_sizes?.validation ?? "NOT AVAILABLE"} · HOLDOUT: {synthetic?.split_sizes?.holdout ?? "NOT AVAILABLE"}. These counts are synthetic rows, not observed event sequences.</p>
        <Results evaluation={synthetic?.evaluation} />
        <details><summary>Synthetic leakage findings</summary><pre>{JSON.stringify(synthetic?.leakage_checks, null, 2)}</pre></details>
        <details><summary>Correct, incorrect, low-confidence, high-uncertainty and unsupported examples</summary><pre>{JSON.stringify(synthetic?.error_analysis, null, 2)}</pre></details>
        <details><summary>Synthetic model and dataset provenance</summary><pre>{JSON.stringify(synthetic?.model, null, 2)}</pre></details>
      </details>
      <p>{data.robustness_reason}</p>
    </>}
  </section>;
}
