"""Evidence-derived, explainable analysis; unavailable measurements stay null."""
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from app.services.attack_service import catalog
from app.services.research_service import model
from app.services.metadata_service import model_report
from app.datasets import features


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def mapping(event):
    technique = event.get("attack_technique_id")
    observed = f"{event.get('subject', '')} {event.get('object', '')}".lower()
    reason, status = "Unmapped — insufficient evidence for ATT&CK classification", "UNMAPPED"
    if not technique and "powershell" in observed and event.get("action") in ("SPAWN", "CREATE"):
        technique = "T1059.001"
    if technique:
        status = "CANDIDATE"
        reason = "Supplied technique annotation; not independently confirmed by this mapper"
        if technique == "T1059.001" and "powershell" in observed and event.get("action") in ("SPAWN", "CREATE"):
            status, reason = "CONFIRMED", "Observed process creation involving PowerShell; behavior confirmation is not proof of malicious intent"
        elif technique == "T1003.001":
            reason = "LSASS access is observed, but access alone does not prove credential dumping"
    item = catalog()["techniques"].get(technique)
    if technique and item is None:
        status, reason = "UNMAPPED", "Technique is absent, revoked or deprecated in the loaded ATT&CK catalog"
    confidence = event.get("confidence") if status != "UNMAPPED" else None
    return {"evidence_id": event["evidence_id"], "technique_id": technique if item else None,
            "technique_name": item["name"] if item else None, "mapping_status": status,
            "mapping_confidence": confidence, "confidence_source": "supplied observation confidence, not calibrated mapping probability",
            "mapping_reason": reason, "tactics": item["tactics"] if item else []}


def analyze_evidence(events):
    identifiers = Counter(e.get("evidence_id") for e in events)
    signatures = Counter(json.dumps({k: e.get(k) for k in ("timestamp", "source", "subject", "action", "object")}, sort_keys=True) for e in events)
    results = []
    times = [parse_time(e.get("timestamp")) for e in events]
    for index, event in enumerate(events):
        mapped = mapping(event)
        stamp = times[index]
        warnings = []
        material = "|".join(str(event.get(k, "")) for k in ("evidence_id", "subject", "action", "object"))
        stored_hash = event.get("integrity_hash")
        integrity = hashlib.sha256(material.encode()).hexdigest() == stored_hash if stored_hash else None
        if integrity is False: warnings.append("legacy_hash_mismatch")
        if identifiers[event.get("evidence_id")] > 1: warnings.append("duplicate_evidence_id")
        signature = json.dumps({k: event.get(k) for k in ("timestamp", "source", "subject", "action", "object")}, sort_keys=True)
        if signatures[signature] > 1: warnings.append("duplicate_observation")
        temporal = None
        if stamp is None:
            warnings.append("missing_or_invalid_timestamp")
        else:
            temporal = 1.0
            if stamp.tzinfo is None:
                warnings.append("timezone_unspecified")
                temporal = .5
            preceding = [t for t in times[:index] if t is not None and (t.tzinfo is None) == (stamp.tzinfo is None)]
            if preceding and stamp < max(preceding):
                warnings.append("out_of_order_timestamp")
                temporal = 0.0
        required = ["timestamp", "source", "host", "subject", "action", "object", "subject_type", "object_type"]
        completeness = sum(bool(event.get(k)) for k in required) / len(required)
        if completeness < 1: warnings.append("missing_normalized_fields")
        parent_known = event.get("subject_type") != "process" or any(
            p.get("object", "").lower() == event.get("subject", "").lower() and p.get("action") in ("SPAWN", "CREATE") for p in events[:index])
        provenance = completeness * (1 if parent_known else .5)
        independent = [p for p in events if p.get("evidence_id") != event.get("evidence_id") and p.get("source") != event.get("source")
                       and all(p.get(k) == event.get(k) for k in ("subject", "action", "object", "timestamp"))]
        cross_sensor = 1.0 if independent else None
        factors = [v for v in (float(integrity) if integrity is not None else None, temporal, provenance, cross_sensor) if v is not None]
        trust = sum(factors) / len(factors) if factors else None
        anomaly_flags = ["legacy_hash_mismatch", "duplicate_evidence_id", "duplicate_observation", "missing_or_invalid_timestamp", "out_of_order_timestamp", "missing_normalized_fields"]
        anomaly = sum(w in warnings for w in anomaly_flags) / len(anomaly_flags)
        if trust is not None: trust *= 1 - anomaly
        relevance = 1 if mapped["mapping_status"] != "UNMAPPED" else 0
        volatility = event.get("volatility")
        utility = (float(volatility) + relevance + 1 / signatures[signature]) / 3 if volatility is not None else None
        results.append({**event, "mapping": mapped, "evidence_trust": trust,
            "poisoning_probability": None, "poisoning_risk": anomaly,
            "poisoning_method": "Fraction of six detected anomaly flags; heuristic risk, not a calibrated probability. Trained tabular model needs unavailable sensor-health/reliability features.",
            "integrity_status": "VERIFIED_LEGACY_FIELDS" if integrity else "MISMATCH" if integrity is False else "NOT_AVAILABLE",
            "cross_sensor_consistency": cross_sensor, "cross_sensor_reason": "Matching independent observation" if independent else "Not available — no independent matching observation",
            "timestamp_consistency": temporal, "provenance_completeness": provenance,
            "forensic_utility": utility, "warnings": warnings,
            "calculation": {"method": "evidence-quality-v1", "trust_formula": "mean(available integrity, timestamp, provenance, cross_sensor) * (1 - anomaly_fraction)",
                "timestamp_formula": "1 for timezone-aware ordered timestamp; 0.5 if timezone missing; 0 if out of order; null if missing",
                "provenance_formula": "required field coverage * (1 if non-process or known preceding spawn else 0.5)",
                "utility_formula": "(supplied volatility + mapped behavior relevance + inverse observation multiplicity) / 3",
                "supporting_fields": {k: event.get(k) for k in required + ["integrity_hash", "volatility"]},
                "cross_sensor_evidence_ids": [p["evidence_id"] for p in independent], "parent_known": parent_known,
                "limitation": "Research quality/utility heuristics; no authenticity guarantee. Fixture volatility is a supplied simulation assumption."}})
    return results


def stage_name(mapping_result):
    if mapping_result["technique_id"] == "T1059.001": return "Execution"
    if mapping_result["technique_id"] == "T1003.001": return "Credential Access"
    tactics = mapping_result.get("tactics", [])
    if not tactics: return None
    return tactics[0].replace("-", " ").title().replace(" And ", " and ")


def prediction(events, incident_id):
    """Legacy synthetic next-stage demonstration, never a future-technique forecast."""
    mapped = [(e, mapping(e)) for e in events]
    usable = [(e, m) for e, m in mapped if m["mapping_status"] != "UNMAPPED" and stage_name(m)]
    if len(usable) < 2:
        return {"status": "not_available", "reason": "Requires two observed mapped events to supply previous/current stage features", "predictions": [], "uncertainty": None}
    previous, current = usable[-2], usable[-1]
    x = {"observed_prev_stage": stage_name(previous[1]), "observed_current_stage": stage_name(current[1]), "current_technique_id": current[1]["technique_id"]}
    try:
        artifact = model("progression")
        metadata = model_report()["models"]["progression"]
    except (FileNotFoundError, KeyError):
        return {"status": "not_available", "reason": "Train the progression baseline first", "predictions": [], "uncertainty": None}
    probabilities = artifact["model"].predict_proba([features(x, artifact["features"])])[0]
    if not all(math.isfinite(float(p)) and 0 <= p <= 1 for p in probabilities) or not math.isclose(sum(probabilities), 1, abs_tol=1e-6):
        raise ValueError("Invalid prediction probabilities")
    uncertainty = -sum(float(p) * math.log(float(p)) for p in probabilities if p > 0) / math.log(len(probabilities)) if len(probabilities) > 1 else 0.0
    return {"status": "available", "prediction_mode": "synthetic_next_stage", "incident_id": incident_id, "current_technique": current[1]["technique_id"],
        "current_stage": x["observed_current_stage"], "current_mapping_status": current[1]["mapping_status"],
        "predictions": sorted([{"predicted_stage": str(label), "predicted_technique": None, "probability": float(p)} for label, p in zip(artifact["model"][-1].classes_, probabilities)], key=lambda p: -p["probability"]),
        "uncertainty": uncertainty, "uncertainty_method": "normalized predictive entropy; not calibrated error probability",
        "calibration_status": "Probability calibration: NOT MEASURED for this fixture", "coverage": None,
        "training_dataset_version": None, "feature_version": metadata["feature_version"],
        "model_name": "RandomForest next-stage baseline", "model_version": metadata["model_version"],
        "training_dataset": metadata["training_dataset"], "training_dataset_sha256": metadata["source_sha256"],
        "supporting_evidence_ids": list(dict.fromkeys([previous[0]["evidence_id"], current[0]["evidence_id"]])),
        "features": x, "feature_evidence": {"observed_prev_stage": previous[0]["evidence_id"], "observed_current_stage": current[0]["evidence_id"], "current_technique_id": current[0]["evidence_id"]},
        "prediction_horizon": "Next synthetic attack stage label; no time horizon labels available",
        "explanation": "Model-level explanation unavailable; prediction is based on the configured feature set. Only the two listed mapped events supply inputs.",
        "limitation": metadata["label_limitation"], "technique_prediction_status": "NOT AVAILABLE — no labeled future-technique dataset"}
