"""Future-risk engine, separate from the model. Formula and weights live in config/defense.json."""
from app.defense.store import config, config_ref, new_id, now
from app.services.attack_service import catalog


def technique_impact(technique_id):
    settings = config()["risk"]
    tactics = catalog()["techniques"].get(technique_id, {}).get("tactics", [])
    known = [settings["tactic_impact"][t] for t in tactics if t in settings["tactic_impact"]]
    return (max(known), "tactic_impact:" + ",".join(tactics)) if known else (settings["default_technique_impact"], "default_technique_impact")


def asset_criticality(host_id):
    settings = config()["risk"]
    if host_id in settings["asset_criticality"]:
        return settings["asset_criticality"][host_id], "configured"
    return settings["default_asset_criticality"], "default_assumption"


def evidence_strength(events):
    """Integrity/completeness of supporting telemetry in [0,1]; not a probability of maliciousness."""
    if not events:
        return 0.0
    penalties = config()["risk"]["evidence_quality_penalties"]
    scores = [max(0.0, 1.0 - sum(penalties.get(flag, 0.0) for flag in e.get("quality_flags", []))) for e in events]
    return sum(scores) / len(scores)


def level(score):
    current = "LOW"
    for name, threshold in config()["risk"]["levels"]:
        if score >= threshold:
            current = name
    return current


def assess(prediction, events):
    settings = config()["risk"]
    strength = evidence_strength(events)
    criticality, criticality_source = asset_criticality(prediction["host_id"])
    predictive, predicted_impact = 0.0, None
    if prediction["status"] == "PREDICTED":
        predicted_impact, impact_source = technique_impact(prediction["predicted_technique_id"])
        predictive = prediction["probability"] * (1 - prediction["uncertainty"]) * strength * predicted_impact * criticality
    observed = [(c["technique_id"], *technique_impact(c["technique_id"])) for e in events for c in e.get("candidate_techniques", [])]
    observed_impact = max((impact for _, impact, _ in observed), default=0.0)
    observed_component = settings["candidate_discount"] * strength * observed_impact * criticality
    score = max(predictive, observed_component)
    return {"risk_id": new_id("RISK"), "prediction_id": prediction["prediction_id"], "host_id": prediction["host_id"],
            "mode": prediction["mode"], "created_at": now(), "risk_score": score, "risk_level": level(score),
            "risk_version": config()["version"], **config_ref(), "formula": settings["formula"],
            "risk_factors": {"prediction_status": prediction["status"], "probability": prediction["probability"],
                             "uncertainty": prediction["uncertainty"], "evidence_strength": strength,
                             "predicted_technique_impact": predicted_impact, "asset_criticality": criticality,
                             "asset_criticality_source": criticality_source, "predictive_component": predictive,
                             "observed_candidate_techniques": sorted({t for t, _, _ in observed}),
                             "observed_component": observed_component, "candidate_discount": settings["candidate_discount"],
                             "dominant_component": "predictive" if predictive >= observed_component and predictive > 0 else "observed_candidate" if observed_component > 0 else "none"},
            "supporting_evidence_ids": prediction["supporting_evidence_ids"],
            "interpretation": "Configured risk estimate for prioritisation; factor values are analyst assumptions, not measured attack likelihood."}
