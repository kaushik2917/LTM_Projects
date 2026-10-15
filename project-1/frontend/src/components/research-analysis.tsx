"use client";
import { useState } from "react";

export type Prediction = { status: string; reason?: string; prediction_mode?: string; cutoff_timestamp?: string | null; current_technique?: string | null; current_technique_name?: string | null; current_mapping_status?: string; prediction_id?: string; prediction_timestamp?: string; predictions: { predicted_stage: string | null; technique_name?: string; catalog_status?: string; predicted_technique: string | null; probability: number }[]; uncertainty: number | null; model_name?: string; model_version?: string; supporting_evidence_ids?: string[]; limitation?: string; technique_prediction_status?: string; [key: string]: unknown };
export type AnalyzedEvidence = { evidence_id: string; timestamp: string; source: string; subject: string; action: string; object: string; volatility: number; evidence_trust: number | null; poisoning_probability: number | null; poisoning_risk: number; forensic_utility: number | null; timestamp_consistency: number | null; cross_sensor_consistency: number | null; provenance_completeness: number; integrity_status: string; warnings: string[]; mapping: { technique_id: string | null; technique_name: string | null; mapping_status: string; mapping_reason: string }; calculation: Record<string, unknown> };
export type Analysis = { future_prediction: Prediction; synthetic_prediction: Prediction; cutoff_timestamp: string | null; incident: { incident_id: string; title: string; affected_host: string; affected_user: string; current_technique_name: string }; evidence: AnalyzedEvidence[]; prediction: Prediction; current_stage: string | null; current_technique: string | null; timeline: { evidence_id: string; timestamp: string }[]; graph: { nodes: { id: string; label: string; type: string }[]; edges: { source: string; target: string; action: string; evidence_id: string; timestamp: string; technique_id: string | null }[] }; latest_assessment: { response_analysis: { recommended_action: string; objective_formula: string; elc_definition: string; candidates: { action: string; residual_attack_risk: number; evidence_retention_score: number; normalized_evidence_loss: number; evidence_loss_cost: number; business_impact: number; objective_score: number }[] } } | null };
export const metric = (v: number | null | undefined) => v == null ? "NOT AVAILABLE" : `${(v * 100).toFixed(1)}%`;

export type Calibration = { status: string; calibration_method: string; calibration_sample_count: number; calibration_scenario_count: number; ECE: number; Brier_score: number; scope: string; temperature?: number };
export type Conformal = { status: string; target_coverage: number; measured_coverage: number | null; average_prediction_set_size: number | null; coverage_sample_count: number; experiment_executed: boolean; reason: string };

export function PredictionEvaluationFeedback({ prediction }: { prediction: Prediction }) {
  const calibration = prediction.calibration as Calibration | null | undefined;
  const conformal = prediction.conformal as Conformal | null | undefined;
  return <>
    <p>Prediction uncertainty: {prediction.uncertainty == null ? "NOT MEASURED" : metric(prediction.uncertainty)}. Method: {String(prediction.uncertainty_method ?? "NOT AVAILABLE")}.</p>
    {prediction.uncertainty_class_count != null && <p>Uses all {String(prediction.uncertainty_class_count)} trained classes, including zero-probability classes. Entropy measures distribution dispersion, not probability of error.</p>}
    {calibration ? <><p>Probability calibration: ECE {calibration.ECE.toFixed(4)} · Brier score {calibration.Brier_score.toFixed(4)} · {calibration.calibration_sample_count} labelled outcomes from {calibration.calibration_scenario_count} scenarios.</p><p>{calibration.scope}. Method: {calibration.calibration_method}. These aggregate diagnostics do not measure correctness for this incident or establish accuracy.</p></> : <p>Probability calibration: {String(prediction.calibration_status ?? "NOT AVAILABLE — no evaluation attached")}</p>}
    <p>Coverage: {conformal?.experiment_executed && conformal.measured_coverage != null ? metric(conformal.measured_coverage) : "NOT MEASURED — independent calibration outcomes required"}.</p>
    {conformal?.experiment_executed && <p>Conformal target: {metric(conformal.target_coverage)}. Empirical test coverage above uses {conformal.coverage_sample_count} held-out scenarios. Average prediction set size: {conformal.average_prediction_set_size?.toFixed(2)}. This is a population metric, not coverage for this incident.</p>}
    {prediction.prediction_set != null && <p>Current conformal prediction set: {(prediction.prediction_set as string[]).join(", ")}</p>}
    {prediction.coverage_reason != null && <details><summary>Conformal coverage eligibility</summary><p>{String(prediction.coverage_reason)}</p></details>}
  </>;
}

export function PredictionDetails({ prediction }: { prediction: Prediction }) {
  const [selected, setSelected] = useState<string | null>(null);
  const choice = prediction.predictions.find(p => (p.predicted_technique ?? p.predicted_stage) === selected);
  const transitions = prediction.transition_evidence as { basis: string; matched_technique_suffix: string[]; total_training_samples: number; target_counts: Record<string, number>; training_sample_ids: string[]; formula: string } | null | undefined;
  return <>
    {prediction.status !== "available" ? <p>{prediction.reason}</p> : <>
      <p className="research-note">{prediction.prediction_mode === "synthetic_temporal_model" ? "Synthetic-trained research model applied to simulated incident. NOT REAL-WORLD VALIDATION." : prediction.prediction_mode === "observed_dataset_model" ? "PREDICTED — Dataset model output; not an observed event." : "SYNTHETIC — Synthetic research demonstration — not validated future ATT&CK prediction."}</p>
      {prediction.predictions.slice(0, 3).map(item => <button className="prediction-choice" key={item.predicted_technique ?? item.predicted_stage} onClick={() => setSelected(item.predicted_technique ?? item.predicted_stage)}>
        <span>{item.predicted_technique ?? item.predicted_stage} {item.technique_name ?? ""}{item.catalog_status && item.catalog_status !== "active" && <small> · {item.catalog_status}</small>}</span><strong>{String(prediction.probability_kind ?? "RAW MODEL PROBABILITY")}: {metric(item.probability)}</strong>
        <span className="path-line"><span className="path-fill" style={{ width: metric(item.probability) }} /></span>
      </button>)}
      <PredictionEvaluationFeedback prediction={prediction} />
      <p className="research-note">Evidence: {prediction.supporting_evidence_ids?.join(", ")}</p><p className="research-note">{prediction.limitation}</p>
    </>}
    {selected && <div className="research-modal-backdrop" onClick={() => setSelected(null)}><section role="dialog" aria-modal="true" aria-label="Prediction explanation" className="research-modal" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === "Escape") setSelected(null); }}>
      <button autoFocus onClick={() => setSelected(null)}>Close explanation</button><h2>{selected}</h2><p>{prediction.model_name} · Model version: {prediction.model_version}</p>
      <dl className="quality-grid">
        <div><dt>Predicted technique</dt><dd>{choice?.predicted_technique ?? choice?.predicted_stage} {choice?.technique_name}</dd></div>
        <div><dt>Model output probability</dt><dd>{metric(choice?.probability)}</dd></div>
        <div><dt>Current ATT&amp;CK assessment</dt><dd>{prediction.current_technique} {prediction.current_technique_name}</dd></div>
        <div><dt>Current technique status</dt><dd>{prediction.current_mapping_status ?? "NOT AVAILABLE"}</dd></div>
        <div><dt>Training dataset</dt><dd>{String(prediction.training_dataset ?? "NOT AVAILABLE")}</dd></div>
        <div><dt>Dataset version</dt><dd>{String(prediction.training_dataset_version ?? "NOT AVAILABLE")}</dd></div>
        <div><dt>Supporting evidence IDs</dt><dd>{prediction.supporting_evidence_ids?.join(", ")}</dd></div>
        <div><dt>Observed technique prefix</dt><dd>{(prediction.observed_technique_prefix as string[] | undefined)?.join(" → ") ?? "NOT AVAILABLE"}</dd></div>
      </dl>
      {transitions && <>
        <p>Feature-level explanation unavailable for this baseline model.</p>
        <h3>Actual training transition evidence</h3>
        <p>{transitions.basis}: {transitions.matched_technique_suffix.join(" → ") || "Training prior"}. Matching training samples: {transitions.total_training_samples}.</p>
        <p>{transitions.formula}. These counts explain RAW MODEL PROBABILITY. Calibrated output, when available, applies the separately fitted temperature.</p>
        <table><thead><tr><th>Next technique</th><th>Training count</th><th>Model output probability</th></tr></thead><tbody>{Object.entries(transitions.target_counts).map(([id, count]) => <tr key={id}><td>{id}</td><td>{count}</td><td>{metric(count / transitions.total_training_samples)}</td></tr>)}</tbody></table>
        <details><summary>Matching training sample IDs</summary><p>{transitions.training_sample_ids.join(", ")}</p></details>
      </>}
      <PredictionEvaluationFeedback prediction={prediction} />
      <p>Only the listed evidence IDs contribute to the recorded feature values. Global feature importance is not a local causal explanation.</p><p>Prediction ID: {prediction.prediction_id ?? "NOT AVAILABLE"}</p><p>Prediction timestamp: {prediction.prediction_timestamp ?? "NOT AVAILABLE"} - Cutoff: {prediction.cutoff_timestamp ?? "NOT AVAILABLE"}</p><pre>{JSON.stringify(prediction, null, 2)}</pre>
    </section></div>}
  </>;
}

export function FuturePrediction({ prediction }: { prediction: Prediction }) {
  const truth = prediction.ground_truth as { status: string; event?: { technique_id: string; timestamp: string } | null } | undefined;
  const evaluation = prediction.evaluation as { status?: string; correct?: boolean | null; prediction_rank?: number; prediction_probability_for_actual_class?: number } | undefined;
  const metrics = prediction.dataset_evaluation as Record<string, number> | undefined;
  return <div aria-label="Future attack prediction"><p>{prediction.synthetic_data === true ? "SYNTHETIC DEMONSTRATION / NOT REAL-WORLD VALIDATION. " : ""}Model: {prediction.model_name}; version/hash: {prediction.model_version}. Class probability is not accuracy. INC-00001 is not a benchmark sample; future correctness remains PENDING_GROUND_TRUTH until an actual future labelled event exists.</p>
    <p>Current ATT&amp;CK assessment: {prediction.current_technique ?? "UNMAPPED"} {prediction.current_technique_name ?? ""} · Status: {prediction.current_mapping_status ?? "NOT AVAILABLE"}</p>
    <p>Prediction cutoff: {prediction.cutoff_timestamp ?? "No evidence selected"}</p>
    <p><strong>Future ATT&amp;CK technique prediction: {prediction.status === "available" ? "PREDICTED" : "NOT AVAILABLE"}</strong></p>
    {prediction.status === "available" ? <PredictionDetails prediction={prediction} /> : <><p>{prediction.reason}</p><p>Uncertainty: NOT MEASURED. Probability calibration: NOT MEASURED. Coverage: NOT MEASURED.</p></>}
    <p>Input evidence: {prediction.supporting_evidence_ids?.join(", ") || "None"}</p>
    <p>Observed future outcome for {prediction.incident_id == null ? "this incident" : String(prediction.incident_id)}: {truth?.status ?? "PENDING"}{truth?.event && ` — ${truth.event.technique_id} at ${truth.event.timestamp}`}.</p>
    <p>Prediction correctness: {evaluation?.status ?? "PENDING_GROUND_TRUTH"}{evaluation?.correct == null && " — no future ground truth has been revealed or observed after the cutoff."}</p>
    {evaluation?.prediction_rank != null && <p>Actual technique rank: {evaluation.prediction_rank}. Probability assigned to actual technique: {metric(evaluation.prediction_probability_for_actual_class)}.</p>}
    {metrics && <p>Held-out synthetic dataset evaluation — Top-1: {metric(metrics.top_1_accuracy)}; Top-3: {metric(metrics.top_3_accuracy)}; Macro-F1: {metric(metrics.macro_f1)}.</p>}
    {prediction.raw_probabilities != null && <details><summary>Raw and calibrated model probabilities</summary><pre>{JSON.stringify({ raw: prediction.raw_probabilities, calibrated: prediction.calibrated_probabilities }, null, 2)}</pre></details>}
    {prediction.status === "available" && <><p>Training: {String(prediction.training_dataset)} v{String(prediction.training_dataset_version)}</p><p>Model: {prediction.model_name} · Model version: {prediction.model_version}</p><p>Prediction horizon: {String(prediction.prediction_horizon)}</p></>}
    <details><summary>Future prediction inputs and provenance</summary><pre>{JSON.stringify(prediction, null, 2)}</pre></details>
  </div>;
}

export function EvidenceQuality({ evidence }: { evidence: AnalyzedEvidence }) {
  return <section className="case-detail"><h3>Evidence quality: {evidence.evidence_id}</h3><dl className="quality-grid">
    {Object.entries({ "Evidence trust (heuristic)": metric(evidence.evidence_trust), "Poisoning anomaly risk (heuristic)": metric(evidence.poisoning_risk), "Poisoning probability": metric(evidence.poisoning_probability), "Cross-sensor consistency": metric(evidence.cross_sensor_consistency), "Timestamp consistency": metric(evidence.timestamp_consistency), "Provenance completeness": metric(evidence.provenance_completeness), "Forensic utility (heuristic)": metric(evidence.forensic_utility), "Integrity scope": evidence.integrity_status }).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl><p>ATT&amp;CK: {evidence.mapping.mapping_status} · {evidence.mapping.technique_id ?? "Unmapped"} · {evidence.mapping.mapping_reason}</p>
    <p>Warnings: {evidence.warnings.join(", ") || "None detected"}. Missing measurements are not replaced with assumed sensor scores.</p><details><summary>Supporting fields and calculation</summary><pre>{JSON.stringify(evidence.calculation, null, 2)}</pre></details></section>;
}
