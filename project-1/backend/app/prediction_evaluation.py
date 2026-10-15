"""Evaluation of the frozen synthetic model. Never fits or replaces the model."""
import json
import math
from pathlib import Path
from statistics import mean, median
from uuid import uuid4

from app.datasets import DATA, sha256
from app.temporal_prediction import digest, entropy, evaluate, now, stamp

METHOD = "Normalized predictive entropy"
FORMULA = "-sum(p_i * ln(p_i), p_i > 0) / ln(K); K = all trained active classes, including zero-probability classes"
VERSION = "frozen-temporal-evaluation-v1"
POINTER = DATA / "models" / "synthetic_temporal_evaluation.json"


def split_checks(groups):
    """Full technique sequences ignore IDs/hosts/timestamps so duplicates cannot hide."""
    scenarios = {p: set() for p in ("train", "validation", "test")}
    sequences = {p: set() for p in scenarios}
    incidents = {p: set() for p in scenarios}
    for scenario, events in groups.items():
        ordered = sorted(events, key=lambda e: stamp(e["timestamp"]))
        parts = {e["split"] for e in ordered}
        if len(parts) != 1: raise ValueError("Scenario crosses evaluation partitions")
        part = parts.pop()
        scenarios[part].add(scenario)
        incidents[part].update(e["incident_id"] for e in ordered)
        sequences[part].add(digest([e["technique_id"] for e in ordered]))
    overlap = {}
    for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
        overlap[f"{a}/{b}"] = {"scenario_ids": sorted(scenarios[a] & scenarios[b]),
            "incident_ids": sorted(incidents[a] & incidents[b]), "full_sequence_hashes": sorted(sequences[a] & sequences[b])}
        if any(overlap[f"{a}/{b}"].values()): raise ValueError(f"Scenario, incident or duplicated full sequence crosses {a}/{b}")
    return {"scenario_ids": {p: sorted(v) for p, v in scenarios.items()},
        "scenario_counts": {p: len(v) for p, v in scenarios.items()},
        "unique_sequence_counts": {p: len(v) for p, v in sequences.items()},
        "full_sequence_hashes": {p: sorted(v) for p, v in sequences.items()}, "overlap": overlap,
        "definition": "Complete timestamp-ordered normalized technique sequence, independent of IDs, host names and absolute time",
        "limitation": "Repeated prefixes and sequences within a partition remain correlated; sample counts are not independent trial counts."}


def conformal_readiness(report, checks):
    """No experiment is claimed when a separate calibration partition is unavailable."""
    target = .9
    # Group exact duplicate full sequences together; leave at least one test group.
    unused_groups = checks["unique_sequence_counts"]["test"]
    minimum_calibration_groups = math.ceil(target / (1 - target) - 1e-10)
    reasons = [
        "Validation outcomes were already used to select this model; they are not an independent conformal calibration set.",
        f"The unchanged test partition has {unused_groups} distinct full technique sequences. Keeping duplicates together and reserving a test group leaves fewer than {minimum_calibration_groups} calibration groups needed for a finite, non-vacuous 90% split-conformal quantile.",
        "Validation/test contain targets outside the trained class space; a closed-label prediction set would exclude those outcomes.",
        "New labelled calibration and test sequence groups, unused for model selection and drawn from a defensible common distribution, are required."
    ]
    return {"status": "NOT MEASURED", "experiment_executed": False, "target_coverage": target,
        "target_coverage_scope": "Configured design target only, not a measured guarantee",
        "measured_coverage": None, "average_prediction_set_size": None, "coverage_sample_count": 0,
        "calibration_scenario_count": 0, "calibration_group_count": 0,
        "available_test_sequence_groups": unused_groups, "minimum_calibration_groups_at_target": minimum_calibration_groups,
        "unsupported_target_classes": report["dataset"]["target_classes_absent_from_training"],
        "reason": " ".join(reasons), "method": None,
        "proposed_method": "Split conformal with score 1 - p(true class), one maximum score per independent sequence group; ceil((n+1)*target) order statistic"}


def run_evaluation():
    from app.synthetic_temporal import qualified_model, load_dataset, sequence_features
    from app.attack_normalization import normalize
    model, report, reason = qualified_model()
    if reason: raise ValueError(reason)
    if report["model_name"] != "transition_frequency": raise ValueError("This evaluation requires the existing transition_frequency model")
    metadata, groups, records = normalize(*load_dataset(Path(report["dataset"]["dataset_path"])))
    checks = split_checks(groups)
    labels = list(model.classes_)
    test_rows = [r for r in records if r["split"] == "test"]
    if not test_rows: raise ValueError("Insufficient held-out labelled outcomes: no test rows")
    features = []
    for row in test_rows:
        events = [e for e in groups[row["scenario_id"]] if stamp(e["timestamp"]) <= stamp(row["cutoff_timestamp"])]
        if [e["event_id"] for e in events] != row["supporting_evidence_ids"].split("|"):
            raise ValueError("Evaluation input evidence does not match cutoff")
        if row["target_event_id"] in row["supporting_evidence_ids"].split("|"):
            raise ValueError("Future target leaked into input")
        features.append(sequence_features(events))
    probabilities = model.predict_proba(features)
    actual = [r["target_next_technique_id"] for r in test_rows]
    metrics = evaluate(actual, probabilities, labels)
    uncertainty = [entropy(p) for p in probabilities]
    result = {"evaluation_id": str(uuid4()), "evaluation_version": VERSION, "evaluation_timestamp": now(),
        "model_name": report["model_name"], "model_version": report["model_version"], "model_retrained": False,
        "dataset": metadata["dataset_name"], "dataset_version": metadata["version"],
        "dataset_hash": metadata["manifest_sha256"], "normalized_dataset_hash": report["normalized_dataset_sha256"],
        "dataset_statistics": {"scenarios": metadata["scenario_count"], "sequences": len(groups),
            "distinct_full_sequences": sum(checks["unique_sequence_counts"].values()), "events": metadata["event_count"], "samples": metadata["sample_count"]},
        "splits": {**checks, "sample_counts": metadata["sample_counts"], "strategy": "Supplied train/validation/test partitions unchanged"},
        "random_seed": report["random_seed"], "random_seed_usage": "No randomized operation in evaluation; inherited training-comparison seed",
        "evaluation_partition": "test", "sample_count": len(test_rows), "metrics": metrics,
        "uncertainty": {"method": METHOD, "formula": FORMULA, "class_count": len(labels),
            "class_order": labels, "mean": mean(uncertainty), "median": median(uncertainty), "sample_count": len(uncertainty),
            "interpretation": "Dispersion of the complete model distribution, not probability of error or out-of-distribution reliability"},
        "calibration": {"status": "MEASURED — held-out synthetic diagnostics", "calibration_method": "Top-label ECE, 10 equal-width confidence bins; multiclass Brier score",
            "calibration_dataset": metadata["dataset_name"], "calibration_dataset_version": metadata["version"],
            "calibration_partition": "test", "calibration_sample_count": len(test_rows), "calibration_scenario_count": checks["scenario_counts"]["test"],
            "ECE": metrics["expected_calibration_error"], "Brier_score": metrics["multiclass_brier_score"], "reliability_bins": metrics["reliability_bins"],
            "probability_calibration_fitted": False, "scope": "Aggregate synthetic held-out outcomes; not incident-specific calibration or fitted probability correction",
            "brier_definition": "Mean sum over union of trained and outcome classes; unseen true class has probability zero and contributes 1"},
        "conformal": conformal_readiness(report, checks), "synthetic_data": True, "real_world_validation": False,
        "predictions": [{"sample_id": row["sample_id"], "scenario_id": row["scenario_id"], "cutoff_timestamp": row["cutoff_timestamp"],
            "supporting_evidence_ids": row["supporting_evidence_ids"].split("|"), "target_event_id": row["target_event_id"],
            "true_technique": y, "probability_distribution": dict(zip(labels, p)), "uncertainty_value": u}
            for row, y, p, u in zip(test_rows, actual, probabilities, uncertainty)]}
    folder = DATA / "model_evaluations"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{result['evaluation_id']}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    POINTER.write_text(json.dumps({"evaluation_id": result["evaluation_id"], "path": str(path.resolve()), "sha256": sha256(path)}, indent=2), encoding="utf-8")
    return {"evaluation_id": result["evaluation_id"], "model_version": result["model_version"], "path": str(path),
        "metrics": {k: metrics[k] for k in ("top_1_accuracy", "top_3_accuracy", "macro_f1", "weighted_f1", "mean_reciprocal_rank")},
        "uncertainty": result["uncertainty"], "calibration": result["calibration"], "conformal": result["conformal"]}


def current_evaluation(report):
    try:
        pointer = json.loads(POINTER.read_text(encoding="utf-8"))
        path = Path(pointer["path"])
        if sha256(path) != pointer["sha256"]: raise ValueError("Evaluation record SHA-256 mismatch")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["evaluation_id"] != pointer["evaluation_id"] or result["evaluation_version"] != VERSION:
            raise ValueError("Evaluation ID or version mismatch")
        if result["model_version"] != report["model_version"] or result["dataset_hash"] != report["dataset"]["manifest_sha256"] or result["normalized_dataset_hash"] != report["normalized_dataset_sha256"]:
            raise ValueError("Evaluation is stale for the current model or dataset")
        return {k: v for k, v in result.items() if k != "predictions"}, None
    except (OSError, ValueError, KeyError) as exc:
        return None, f"NOT MEASURED — {exc}. Run python -m app.datasets evaluate-temporal"
