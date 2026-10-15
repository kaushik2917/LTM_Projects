"""Future technique inference is separate from the synthetic stage demonstration."""
import json
from pathlib import Path
from app.datasets import DATA, sha256
from app.temporal_prediction import FEATURE_VERSION, HORIZON, REASON, entropy, feature_values, now, prefix, stamp
from app.services.attack_service import catalog
from app.services.analysis_service import mapping


def qualified_model(task="technique"):
    import joblib
    path = DATA / "models" / f"future_{task}.joblib"
    metadata_path = path.with_suffix(".json")
    if not path.exists() or not metadata_path.exists():
        return None, None, REASON
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    if meta.get("model_version") != sha256(path):
        return None, None, "Model artifact SHA-256 mismatch; retrain and evaluate before inference"
    artifact = joblib.load(path)  # Trusted local training artifact only; never accepts uploads.
    if artifact.get("metadata") != {k: v for k, v in meta.items() if k != "model_version"}:
        return None, None, "Model metadata does not match the trained artifact"
    if meta.get("prediction_mode") != "observed_dataset_evaluation" or meta.get("dataset", {}).get("data_kind") != "observed":
        return None, None, "Synthetic pipeline artifacts cannot provide genuine future predictions"
    if meta.get("feature_version") != FEATURE_VERSION or meta.get("task") != task or not meta.get("leakage_checks", {}).get("all_checks_passed"):
        return None, None, "Model feature version, task or leakage checks are invalid"
    if not meta.get("evaluation", {}).get("holdout") or not meta.get("evaluation", {}).get("validation"):
        return None, None, "Independent validation and holdout evaluation are missing"
    source = Path(meta.get("dataset_path", ""))
    if not source.is_file() or sha256(source) != meta.get("dataset_sha256"):
        return None, None, "Training dataset unavailable or its SHA-256 changed"
    if meta.get("attack_catalog_sha256") != catalog().get("sha256"):
        return None, None, "ATT&CK catalog changed; reevaluate label validity"
    return artifact["model"], meta, None


def predict(events, incident_id, cutoff_timestamp, task="technique", domain=None):
    if task not in ("technique", "stage"):
        raise ValueError("Unknown future prediction task")
    events, cutoff = prefix(events, cutoff_timestamp)
    mapped = []
    for event in events:
        if event.get("technique_id"):
            if not event.get("label_known_at") or stamp(event["label_known_at"]) > stamp(cutoff):
                continue
            event = {**event, "attack_technique_id": event["technique_id"]}
        mapped.append(mapping(event))
    current = next((m for m in reversed(mapped) if m["mapping_status"] != "UNMAPPED"), None)
    values = feature_values(events, cutoff) if events else {}
    result = {"status": "not_available", "prediction_mode": "unavailable", "task": "next_observed_" + task,
        "incident_id": incident_id, "cutoff_timestamp": cutoff, "prediction_timestamp": now(),
        "clock_policy": "Fixture timestamps have no supplied timezone" if events and all(e.get("simulated") for e in events) else "UTC normalized",
        "current_technique": current["technique_id"] if current else None,
        "current_technique_name": current["technique_name"] if current else None,
        "current_mapping_status": current["mapping_status"] if current else "UNMAPPED",
        "predictions": [], "uncertainty": None, "uncertainty_value": None, "uncertainty_method": "normalized predictive entropy when a model is available",
        "calibration_status": "NOT MEASURED", "coverage": None, "coverage_reason": "NOT MEASURED — no conformal evaluation",
        "prediction_horizon": HORIZON, "supporting_evidence_ids": [e["evidence_id"] for e in events],
        "features": values, "feature_version": FEATURE_VERSION, "model_name": None, "model_version": None,
        "training_dataset": None, "training_dataset_version": None, "training_dataset_sha256": None,
        "explanation": "Prefix features are shown for traceability; no model output is claimed when unavailable."}
    if task == "technique" and events and all(e.get("simulated") is True for e in events):
        from app.synthetic_temporal import predict as synthetic_predict
        return synthetic_predict(events, result)
    model, meta, reason = qualified_model(task)
    if reason:
        return {**result, "reason": reason}
    if not events:
        return {**result, "reason": "No evidence is available at this cutoff"}
    if any(e.get("simulated") is not False for e in events):
        return {**result, "reason": "This incident is a synthetic fixture; an observed-data model is not validated for it"}
    if domain != meta["dataset"]["domain"]:
        return {**result, "reason": "Incident source domain does not match the evaluated training domain"}
    training_groups = meta.get("partition_groups", {}).get("training")
    if training_groups is None:
        return {**result, "reason": "Model has no training-group provenance; cannot exclude incident leakage"}
    if any(any(e.get(key) in training_groups[key] for key in ("incident_id", "scenario_id", "collection_id")) for e in events):
        return {**result, "reason": "Incident/scenario/collection was used for model fitting; its future labels cannot be treated as unseen"}
    probabilities = model.predict_proba([values])[0]
    uncertainty = entropy(probabilities)
    labels = model[-1].classes_
    if task == "technique" and any(label not in catalog()["techniques"] for label in labels):
        return {**result, "reason": "Model contains labels absent from the active ATT&CK catalog"}
    result.update(status="available", prediction_mode="observed_dataset_model", uncertainty=uncertainty, uncertainty_value=uncertainty,
        model_name=meta["model_name"], model_version=meta["model_version"], training_dataset=meta["dataset"]["dataset_name"],
        training_dataset_version=meta["dataset"]["version"], training_dataset_sha256=meta["dataset_sha256"],
        calibration_status=meta["calibration_status"], evaluation=meta["evaluation"], explanation=meta["explanation"],
        model_provenance={k: meta[k] for k in ("algorithm", "training_timestamp", "random_seed", "hyperparameters", "split_sizes", "feature_version", "dataset_sha256", "attack_catalog_version")},
        limitation="Evaluated on held-out dataset groups; not a calibrated real-world forecasting guarantee.")
    result["predictions"] = [{"rank": rank, "predicted_technique": str(label) if task == "technique" else None,
        "predicted_stage": str(label) if task == "stage" else None,
        "technique_name": catalog()["techniques"][label]["name"] if task == "technique" else None,
        "probability": float(p), "uncertainty": uncertainty, "supporting_evidence_ids": result["supporting_evidence_ids"]}
        for rank, (label, p) in enumerate(sorted(zip(labels, probabilities), key=lambda pair: (-pair[1], pair[0])), 1)]
    return result


def evaluation_status():
    from app.temporal_experiment import status as experiment_status
    from app.synthetic_temporal import research_status
    from app.services.workflow_service import run_prediction
    path = DATA / "models/prediction_readiness.json"
    audit = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "not_audited", "reason": "Run python -m app.prediction_audit"}
    for source in audit.get("datasets", []):
        dataset_path = DATA / "custom" / source["filename"]
        if not dataset_path.exists() or sha256(dataset_path) != source["sha256"]:
            audit["status"] = "stale_audit"
            audit["reason"] = "Dataset content changed; rerun python -m app.prediction_audit"
            audit["synthetic_demonstration"] = {"status": "not_available", "label": audit["reason"]}
    result = {}
    for task in ("technique", "stage"):
        _, meta, reason = qualified_model(task)
        result[task] = {"status": "not_available" if reason else "evaluated", "reason": reason, "metadata": meta}
    return {"task_definition": "Given evidence known at T, predict the next independently labelled observed event strictly after T",
        "future": result, "synthetic_temporal": research_status(), "temporal_experiment": experiment_status(),
        "demonstration": run_prediction("INC-00001", "2026-09-25T10:05:02"),
        "data_audit": audit, "future_prediction_robustness": None,
        "robustness_reason": "NOT MEASURED — no observed labelled robustness replay has been run", "coverage": None}
