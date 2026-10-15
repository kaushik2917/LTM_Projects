"""Audit every supplied table and evaluate the existing synthetic artifact honestly."""
from collections import Counter, defaultdict
import json
from app.datasets import DATA, FILES, rows, sha256
from app.temporal_prediction import digest, evaluate, entropy, now, REASON
from app.services.metadata_service import config


def run():
    datasets = []
    reasons = {"10": "Current-state response alternatives; each incident repeats across actions, not future events",
               "11": "Synthetic rule-based next-stage labels; unique row IDs, no timestamps or observed future events",
               "12": "Unordered evidence-quality/corruption rows; no event timestamps or future outcomes",
               "13": "Synthetic benchmark descriptors and expected scores; no observed event sequences"}
    for key, filename in FILES.items():
        records = rows(key)
        columns = list(records[0])
        grouped = defaultdict(set)
        for row in records:
            if "incident_id" in row:
                grouped[row["incident_id"]].add((row.get("timestamp"), row.get("technique_id")))
        datasets.append({"id": key, **config()["datasets"][key], "filename": filename, "sha256": sha256(DATA / "custom" / filename),
            "rows": len(records), "schema": columns, "unique_values": {k: len({r[k] for r in records}) for k in columns if k.endswith("_id") or k in ("host", "scenario", "scenario_name", "source", "dataset_source", "label_source")},
            "timestamps": {"present": "timestamp" in columns, "min": min((r["timestamp"] for r in records if "timestamp" in r), default=None), "max": max((r["timestamp"] for r in records if "timestamp" in r), default=None)},
            "identifiers": {k: k in columns for k in ("incident_id", "sequence_id", "evidence_id", "host", "user", "process_id", "source_ip", "scenario")},
            "label_sources": dict(Counter(r["label_source"] for r in records)) if "label_source" in columns else None,
            "max_distinct_current_states_per_incident": max(map(len, grouped.values()), default=None),
            "full_row_duplicates": len(records) - len({digest(r) for r in records}),
            "genuine_future_outcomes": False, "future_prediction_readiness": "NOT AVAILABLE", "reason": reasons[key]})
    from app.services.optc_service import status
    report = {"audited_at": now(), "status": "insufficient_observed_sequences", "reason": REASON, "datasets": datasets,
              "optc": status(), "synthetic_demonstration": synthetic_evaluation()}
    (DATA / "models/prediction_readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def synthetic_evaluation():
    import joblib
    from sklearn.model_selection import GroupShuffleSplit
    path = DATA / "models/progression.joblib"
    if not path.exists():
        return {"status": "not_available", "reason": "Train the existing progression artifact first"}
    artifact = joblib.load(path)
    metadata = json.loads((DATA / "models/training_report.json").read_text())["models"]["progression"]
    if metadata["model_version"] != sha256(path) or metadata["source_sha256"] != sha256(DATA / "custom" / FILES["11"]):
        return {"status": "not_available", "reason": "Synthetic model or dataset hash differs from training metadata; retrain"}
    data = rows("11")
    x = [{k: r[k] for k in artifact["features"]} for r in data]
    y = [r["predicted_next_stage"] for r in data]
    groups = [r["sequence_id"] for r in data]
    development, holdout = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(x, y, groups))
    a, b = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=43).split(development, groups=[groups[i] for i in development]))
    split = {"training": development[a].tolist(), "validation": development[b].tolist(), "holdout": holdout.tolist()}
    if split["training"] != metadata["train_indices"] or split["holdout"] != metadata["test_indices"]:
        raise ValueError("Cannot reproduce stored synthetic model split")
    labels = artifact["model"][-1].classes_.tolist()
    majority = Counter(y[i] for i in split["training"]).most_common(1)[0][0]
    result = {"status": "evaluated", "prediction_mode": "synthetic_next_stage", "label": "Dataset Demonstration Scenario — synthetic next-stage prediction; not validated future ATT&CK technique prediction",
              "model": {k: v for k, v in metadata.items() if k not in ("train_indices", "test_indices")},
              "dataset_version": config()["datasets"]["11"]["version"], "split_sizes": {k: len(v) for k, v in split.items()},
              "evaluation_timestamp": now(), "evaluation": {}, "error_analysis": [], "leakage_checks": {},
              "calibration_status": "Brier/ECE diagnostics measured on synthetic labels; no calibration fitted", "coverage": None}
    for part in ("validation", "holdout"):
        ids = split[part]
        probabilities = artifact["model"].predict_proba([x[i] for i in ids]).tolist()
        result["evaluation"][part] = {"model": evaluate([y[i] for i in ids], probabilities, labels),
            "majority_baseline": evaluate([y[i] for i in ids], [[float(c == majority) for c in labels]] * len(ids), labels)}
        examples = defaultdict(list)
        for i, p in zip(ids, probabilities):
            best = max(range(len(p)), key=p.__getitem__)
            item = {"sequence_id": groups[i], "features": x[i], "actual_synthetic_stage": y[i], "predicted_stage": labels[best], "probability": p[best], "uncertainty": entropy(p), "cutoff_timestamp": None}
            categories = ["correct" if labels[best] == y[i] else "incorrect"]
            if p[best] < .5: categories.append("low_confidence")
            if entropy(p) > .75: categories.append("high_uncertainty")
            for category in categories:
                if len(examples[category]) < 5: examples[category].append(item)
        result["error_analysis"].append({"partition": part, "examples": dict(examples), "reason": "Empty categories mean no such examples in this evaluation; no examples are invented", "unsupported": "No observed future-technique targets; temporal errors cannot be assessed"})
    for left, right in (("training", "validation"), ("training", "holdout"), ("validation", "holdout")):
        result["leakage_checks"][left + "/" + right] = {
            "sequence_id_overlap": len({groups[i] for i in split[left]} & {groups[i] for i in split[right]}),
            "duplicate_feature_target_patterns": len({digest([x[i], y[i]]) for i in split[left]} & {digest([x[i], y[i]]) for i in split[right]})}
    result["leakage_checks"].update(feature_target_overlap=sorted(set(artifact["features"]) & {"predicted_next_stage"}),
        scenario_overlap=None, source_overlap=["synthetic_rule_based"], temporal_leakage_check="NOT AVAILABLE — no event timestamps",
        warning="Unique sequence IDs are row IDs, not independent campaigns. Repeated feature/target patterns and deterministic stage rules mean perfect holdout scores do not establish forecasting.")
    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "datasets": len(result["datasets"]), "synthetic_evaluation": result["synthetic_demonstration"]["status"]}, indent=2))
