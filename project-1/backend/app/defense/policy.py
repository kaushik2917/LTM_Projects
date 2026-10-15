"""Policy engine between risk and response. The model predicts; this decides."""
from app.defense import executor
from app.defense.knowledge import defensive_mapping
from app.defense.store import config, config_ref, new_id, now


def decide(risk, prediction, trigger):
    settings = config()["policy"]
    actions = settings["level_actions"][risk["risk_level"]]
    record = {"decision_id": new_id("POL"), "risk_id": risk["risk_id"], "prediction_id": prediction["prediction_id"],
              "mode": risk["mode"], "host_id": risk["host_id"], "created_at": now(), "policy_version": settings["version"],
              **config_ref(), "risk_level": risk["risk_level"],
              "internal_actions": [a for a in actions if a != "CONTAINMENT_REQUIRES_APPROVAL"],
              "containment_candidates": [], "refused_candidates": [], "defensive_mapping": None, "reasons": []}
    if "CONTAINMENT_REQUIRES_APPROVAL" not in actions:
        record["reasons"].append(f"Risk level {risk['risk_level']} does not permit containment")
        return record
    if prediction["status"] != "PREDICTED":
        record["reasons"].append("Prediction abstained; containment requires a qualified prediction. Analyst review only.")
        record["internal_actions"] = sorted(set(record["internal_actions"]) | {"ALERT", "ANALYST_REVIEW"})
        return record
    strength = risk["risk_factors"]["evidence_strength"]
    if prediction["probability"] < settings["containment_min_probability"] or strength < settings["containment_min_evidence_strength"]:
        record["reasons"].append(f"Probability {prediction['probability']:.3f} or evidence strength {strength:.3f} below containment thresholds")
        record["internal_actions"] = sorted(set(record["internal_actions"]) | {"ANALYST_REVIEW"})
        return record
    mapping = defensive_mapping(prediction["predicted_technique_id"])
    record["defensive_mapping"] = {k: mapping[k] for k in ("technique_id", "mapping_version", "attack_version", "local_controls")}
    if not mapping["local_controls"]:
        record["reasons"].append("No allowlisted local control maps to the predicted technique's ATT&CK mitigations")
    catalogue = config()["response"]["containment_actions"]
    for action_type in mapping["local_controls"]:
        parameters = {key: trigger.get(key) for key in catalogue.get(action_type, {}).get("requires", [])}
        clean, refusal = executor.validate(action_type, parameters)
        if refusal:
            record["refused_candidates"].append({"action_type": action_type, "reason": refusal})
            continue
        reversible = catalogue[action_type]["reversible"]
        automatic = (risk["risk_level"] == "CRITICAL" and settings["auto_execute_critical"] and reversible)
        record["containment_candidates"].append({"action_type": action_type, "parameters": clean, "reversible": reversible,
            "approval_required": not automatic,
            "justification": [m["mitigation_id"] for m in mapping["mitigations"] if action_type in m["local_controls"]]})
    return record
