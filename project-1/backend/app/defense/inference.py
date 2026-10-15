"""Live/replay inference wrapper around services.future_prediction_service.predict.

Training stays in temporal_prediction/synthetic_temporal; this module only
loads an already-qualified model through the existing gate. When the gate
refuses (no observed-data model), the result is an explicit ABSTAIN.
"""
from datetime import datetime, timedelta
import json

from app.defense.store import config, new_id, now, read
from app.services.attack_service import catalog


def window(event, online):
    """Events visible at the cutoff: same host and mode, inside the observation window."""
    settings = config()["inference"]
    cutoff = event["collection_time"] if online else event["timestamp_utc"]
    start = (datetime.fromisoformat(cutoff) - timedelta(minutes=settings["observation_window_minutes"])).isoformat(timespec="microseconds")
    rows = read("SELECT e.record, v.evidence_id FROM events e LEFT JOIN evidence v ON v.event_id = e.event_id "
                "WHERE e.mode=? AND e.host_id=? AND e.timestamp_utc>=? AND e.timestamp_utc<=? ORDER BY e.timestamp_utc",
                (event["mode"], event["host_id"], start, cutoff))
    visible = []
    for record_text, evidence_id in rows:
        item = json.loads(record_text)
        if online and item["collection_time"] > cutoff:
            continue  # not yet available to the system at prediction time
        visible.append({**item, "evidence_id": evidence_id})
    return cutoff, visible


def as_prefix_event(item, online):
    """Shape expected by temporal_prediction.prefix/feature_values (whitelisted fields only)."""
    return {"evidence_id": item["evidence_id"], "timestamp": item["timestamp_utc"],
            "observed_at": item["collection_time"] if online else item["timestamp_utc"], "simulated": False,
            "host": item["host_id"], "source": item["event_source"], "action": item["action"],
            "subject_type": "process", "subject": item.get("process_name") or item.get("actor_id"),
            "object_type": item.get("object_type"), "object": item.get("object_id")}


def throttled(event, cutoff):
    interval = config()["inference"]["min_interval_seconds"]
    last = read("SELECT record FROM predictions WHERE mode=? AND host_id=? ORDER BY created_at DESC LIMIT 1", (event["mode"], event["host_id"]))
    if not last or interval <= 0:
        return False
    previous = json.loads(last[0][0])["cutoff_timestamp"]
    return 0 <= (datetime.fromisoformat(cutoff) - datetime.fromisoformat(previous)).total_seconds() < interval


def infer(event, force=False):
    """Return an unsaved prediction record, or None when throttled."""
    from app.services.future_prediction_service import predict
    settings = config()["inference"]
    online = event["mode"] in ("LIVE", "LAB")
    cutoff, visible = window(event, online)
    if not force and throttled(event, cutoff):
        return None
    started = datetime.now()
    base = {"prediction_id": new_id("PRED"), "event_id": event["event_id"], "host_id": event["host_id"], "mode": event["mode"],
            "prediction_timestamp": now(), "cutoff_timestamp": cutoff, "estimand": settings["estimand"][event["mode"]],
            "observation_window_minutes": settings["observation_window_minutes"],
            "supporting_event_ids": [v["event_id"] for v in visible],
            "supporting_evidence_ids": [v["evidence_id"] for v in visible if v["evidence_id"]],
            "attack_version": catalog().get("version"), "attack_catalog_sha256": catalog().get("sha256"),
            "status": "ABSTAINED", "abstain_reason": None, "predicted_technique_id": None, "predicted_technique_name": None,
            "probability": None, "uncertainty": None, "top_k": [], "prediction_horizon": None,
            "model_name": None, "model_version": None, "model_hash": None, "feature_version": None,
            "training_dataset_version": None, "calibration_status": "NOT MEASURED", "decision": "MONITOR_ONLY"}
    try:
        result = predict([as_prefix_event(v, online) for v in visible], f"{event['mode']}:{event['host_id']}", cutoff)
    except (ValueError, KeyError) as exc:
        return {**base, "abstain_reason": f"Inference input rejected: {exc}", "latency_ms": (datetime.now() - started).total_seconds() * 1000}
    base.update(feature_version=result.get("feature_version"), prediction_horizon=result.get("prediction_horizon"),
                calibration_status=result.get("calibration_status", "NOT MEASURED"),
                latency_ms=(datetime.now() - started).total_seconds() * 1000)
    if result.get("status") != "available" or not result.get("predictions"):
        return {**base, "abstain_reason": result.get("reason") or "No model output"}
    top = result["predictions"][0]
    base.update(model_name=result["model_name"], model_version=result["model_version"], model_hash=result["model_version"],
                training_dataset_version=result.get("training_dataset_version"), uncertainty=result["uncertainty"],
                top_k=[{"rank": p["rank"], "technique_id": p["predicted_technique"], "technique_name": p["technique_name"],
                        "probability": p["probability"]} for p in result["predictions"][:5]])
    if top["probability"] < settings["abstain_below_probability"]:
        return {**base, "abstain_reason": f"Top probability {top['probability']:.3f} below abstention threshold"}
    if result["uncertainty"] > settings["abstain_above_uncertainty"]:
        return {**base, "abstain_reason": f"Uncertainty {result['uncertainty']:.3f} above abstention threshold"}
    return {**base, "status": "PREDICTED", "predicted_technique_id": top["predicted_technique"],
            "predicted_technique_name": top["technique_name"], "probability": top["probability"], "decision": "POLICY_EVALUATION"}
