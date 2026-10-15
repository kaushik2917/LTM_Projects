"""Dataset-trained research baselines; recommendations never execute host actions."""
from functools import lru_cache
import json

from app.datasets import DATA, ARTIFACTS, features, rows
from app.services.metadata_service import config, model_report


@lru_cache(maxsize=8)
def model(name):
    import joblib
    path = DATA / "models" / f"{name}.joblib"
    if not path.exists():
        raise FileNotFoundError("Run python -m app.datasets train first")
    # Only locally trained files are loaded; never load uploaded pickle/joblib files.
    return joblib.load(path)


def predict(name, context):
    artifact = model(name)
    values = artifact["model"].predict([features(context, artifact["features"])])[0]
    return dict(zip(artifact["targets"], (float(v) for v in values)))


def future_risk(context, action, probabilities, current_risk):
    """Model estimates for represented techniques; explicit neutral fallback assumption.

    Unsupported techniques retain current-state residual risk. This is not a
    measured risk value and is exposed per class with its probability mass.
    """
    from app.temporal_prediction import entropy
    entropy(list(probabilities.values()))
    stages = {r["technique_id"]: r["attack_stage"] for r in rows("10")}
    represented = [t for t in probabilities if t in stages]
    artifact = model("aces")
    estimates = artifact["model"].predict([features(dict(context, action=action, technique_id=t,
        attack_stage=stages[t]), artifact["features"]) for t in represented]) if represented else []
    risk_index = artifact["targets"].index("residual_attack_risk")
    risk = {t: float(row[risk_index]) for t,row in zip(represented, estimates)}
    terms = [{"technique_id": t, "probability": p, "residual_risk": risk.get(t, current_risk),
        "source": "ACES synthetic model estimate" if t in risk else "Analyst modeling assumption: unchanged current-state residual risk; technique absent from response dataset",
        "contribution": p * risk.get(t, current_risk)} for t,p in probabilities.items()]
    return {"expected_future_risk": sum(t["contribution"] for t in terms), "terms": terms,
        "model_supported_probability_mass": sum(probabilities[t] for t in represented),
        "unsupported_probability_mass": sum(p for t,p in probabilities.items() if t not in risk),
        "status": "SIMULATED RESEARCH ESTIMATE", "measured_causal_effect": False}


def responses(context, future_probabilities=None):
    decision = config()["decision"]
    weights = decision["weights"]
    future_weight = decision.get("future_prediction_weight", 0.)
    import math
    if not math.isfinite(future_weight) or future_weight < 0: raise ValueError("Invalid future prediction weight")
    if set(weights) != {"risk", "normalized_loss", "business", "cost", "opportunity"} or not all(math.isfinite(w) and w >= 0 for w in weights.values()) or not math.isclose(sum(weights.values()), 1):
        raise ValueError("Decision weights must be finite, nonnegative, sum to one and match the implemented terms")
    utility = predict("cdfu", context)
    actions = sorted({r["action"] for r in rows("10")})
    candidates = []
    for action in actions:
        outcome = predict("aces", dict(context, action=action))
        total = sum(utility.values())
        loss = sum(utility["fu_" + a] * (1 - outcome["survival_" + a]) for a in ARTIFACTS)
        retention = 1 - loss / total if total else 1.0
        terms = {"risk": outcome["residual_attack_risk"], "normalized_loss": 1 - retention,
                 "business": outcome["business_impact"], "cost": outcome["response_cost"], "opportunity": outcome["evidence_opportunity_cost"]}
        contributions = {key: weights[key] * value for key, value in terms.items()}
        objective = sum(contributions.values())
        future = future_risk(context, action, future_probabilities, outcome["residual_attack_risk"]) if future_probabilities else None
        future_contribution = future_weight * future["expected_future_risk"] if future else 0.
        candidates.append({"action": action, **outcome, "evidence_loss_cost": loss,
            "normalized_evidence_loss": 1 - retention, "evidence_retention_score": retention,
            "objective_score": objective + future_contribution, "base_objective_score": objective, "objective_contributions": contributions,
            "future_risk": future, "expected_future_risk": future["expected_future_risk"] if future else None,
            "future_prediction_contribution": future_contribution,
            "prediction_uncertainty_impact": None, "uncertainty_reason": decision["uncertainty_use"]})
    candidates.sort(key=lambda r: r["objective_score"])
    return {"mode": "research_simulation", "model": "random_forest_baseline",
        "forensic_utility": utility, "candidates": candidates,
        "recommended_action": candidates[0]["action"], "execution": "recommendation_only",
        "causal_effects_validated": False, "calibrated_safety_guarantee": False,
        "objective_weights": weights, "decision_profile": decision["profile"], "future_prediction_weight": future_weight,
        "objective_normalized": not bool(future_probabilities and future_weight),
        "objective_weight_sum": sum(weights.values()) + (future_weight if future_probabilities else 0.),
        "objective_interpretation": "Unnormalized additive advisory cost: base weights sum to 1; future-risk penalty is added separately. With future weight 0.2 and unit-range terms, range is 0 to 1.2. Dividing every action score by 1.2 would preserve ranking but change reported contributions. This is not a probability, safety guarantee or measured prevention success.",
        "future_probabilities": future_probabilities, "future_risk_status": "SIMULATED RESEARCH ESTIMATE" if future_probabilities else "NOT AVAILABLE: no future distribution supplied; base objective retained",
        "objective_formula": " + ".join(f"{weight} * {key}" for key, weight in weights.items()) + (f" + {future_weight} * expected_future_risk" if future_probabilities else ""),
        "elc_definition": "sum(utility_i * (1 - survival_i)); range 0 to sum of current utilities, not a probability",
        "elc_maximum": sum(utility.values()), "normalized_loss_range": [0, 1],
        "recommendation_reason": "Minimum weighted objective among all evaluated actions; no hard safety guarantee",
        "models": {key: model_report()["models"].get(key, {}) for key in ("cdfu", "aces")}}


def anti_forensic(context):
    artifact = model("afip")
    pipeline = artifact["model"]
    probabilities = pipeline.predict_proba([features(context, artifact["features"])])[0]
    labels = pipeline[-1].classes_
    # Preservation targets/actions are explicit dataset metadata, not model inputs.
    metadata = {}
    for row in rows("11"):
        metadata.setdefault(row["anti_forensic_behavior"], (row["target_evidence"], row["recommended_preservation_action"]))
    predictions = [{"behavior": str(label), "probability": float(prob),
                    "target_evidence": metadata[label][0], "preservation_action": metadata[label][1]}
                   for label, prob in zip(labels, probabilities)]
    predictions.sort(key=lambda r: r["probability"], reverse=True)
    return {"model": "synthetic_label_baseline", "calibrated": False,
            "predictions": predictions, "execution": "recommendation_only",
            "reliability": "low: consult holdout macro-F1; no automatic preservation decision",
            "preservation_priority": "analyst_review_required"}


def trust(context):
    scores = predict("trust", context)
    artifact = model("poisoning")
    classifier = artifact["model"]
    probabilities = classifier.predict_proba([features(context, artifact["features"])])[0]
    poisoning = sum(float(p) for c, p in zip(classifier[-1].classes_, probabilities) if str(c) == "1")
    return {**scores, "poisoning_probability": poisoning,
            "handling": "reduce_weight_and_request_corroboration" if poisoning >= .5 else "retain",
            "delete_evidence": False, "calibrated": False,
            "input_assumption": "Corruption indicators supplied by upstream analysis; not detected from raw telemetry here."}


def evaluate_benchmark():
    """Audit held-out scenarios without inventing missing event-level measurements."""
    records = rows("13")
    scenarios = {}
    for row in records:
        item = scenarios.setdefault(row["scenario_name"], {"rows": 0, "expected_ers_sum": 0.0,
                                                           "missing_ratios": set()})
        item["rows"] += 1
        item["expected_ers_sum"] += float(row["expected_ers"])
        item["missing_ratios"].add(float(row["missing_event_ratio"]))
    for value in scenarios.values():
        value["mean_synthetic_expected_ers"] = value.pop("expected_ers_sum") / value["rows"]
        value["missing_ratios"] = sorted(value["missing_ratios"])
    report = {"dataset": "13", "usage": "evaluation_only", "rows": len(records),
        "scenarios": scenarios, "measured_model_metrics": None,
        "status": "scenario_audit_only",
        "reason": "CSV supplies scenario descriptors and expected synthetic scores, not raw event sequences, evidence survival observations, or true next-technique labels. Empirical robustness, conformal coverage and unsafe-action rates require replay traces and measured outcomes."}
    (DATA / "benchmark_scenario_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
