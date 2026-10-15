"""Frozen synthetic temporal benchmark. Never installs an operational model.

Run from backend: python -m app.prediction_benchmark
"""
from collections import Counter
import json
import math
from pathlib import Path
import platform

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits

from app.datasets import DATA, sha256
from app.services.attack_service import catalog
from app.synthetic_temporal import sequence_features, TransitionFrequency
from app.temporal_prediction import digest, entropy, evaluate, stamp

SOURCE = DATA / "custom/synthetic_temporal_v2/scenarios.json"
OUTPUT = DATA / "model_evaluations/chronological_prediction_v2"
VERSION = "chronological-synthetic-v2"
FEATURE_VERSION = "future_prediction_v2"
TARGET_TOP1_ACCURACY = .90
SEED = 20261003
RF_PARAMS = dict(n_estimators=80, max_depth=12, min_samples_leaf=2, random_state=SEED, n_jobs=1)
LIMITATION = "Offline synthetic annotations only; not independently observed ground truth or real-world accuracy. This model cannot activate operational defense prediction."


def safe_prefix(events, cutoff, supported=None):
    """Reject ambiguous input; ignore all future fields and labels unavailable at cutoff."""
    end = stamp(cutoff)
    visible = []
    seen = set()
    times = set()
    for event in events:
        time = stamp(event["timestamp"])
        if time > end:
            continue
        if event.get("simulated") is not True or event.get("label_status") != "synthetic_annotation":
            raise ValueError("Only explicit synthetic annotations supported by this research model")
        if not event.get("source") or not event.get("evidence_id"):
            raise ValueError("Missing required source or evidence identifier")
        if event["evidence_id"] in seen or time in times:
            raise ValueError("Duplicate identifier or ambiguous timestamp")
        seen.add(event["evidence_id"])
        times.add(time)
        known = stamp(event["label_known_at"])
        if known < time:
            raise ValueError("Label availability precedes event")
        technique = event.get("technique_id") if known <= end else None
        if not technique:
            raise ValueError("Required prefix label unavailable at cutoff")
        if supported is not None and technique not in supported:
            raise ValueError("Prefix technique outside supported classes")
        if not event.get("action"):
            raise ValueError("Missing required action")
        visible.append({"timestamp": event["timestamp"], "technique_id": technique, "source": event["source"], "action": event["action"]})
    visible.sort(key=lambda event: stamp(event["timestamp"]))
    if len(visible) < 2:
        raise ValueError("At least two labelled prefix events required")
    return visible


def features(events):
    """No identity, absolute timestamp, text template, target or future fields."""
    values = sequence_features(events)
    for event in events:
        key = "action_count:" + event["action"]
        values[key] = values.get(key, 0) + 1
    recent = events[-3:]
    for technique, count in Counter(event["technique_id"] for event in recent).items():
        values["recent3_count:" + technique] = count
    values["adjacent_repeats"] = sum(a["technique_id"] == b["technique_id"] for a, b in zip(events, events[1:]))
    values["last_tactics"] = "|".join(catalog()["techniques"][events[-1]["technique_id"]]["tactics"])
    return values


def build(path=SOURCE):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("synthetic") is not True:
        raise ValueError("This adapter only accepts the existing explicit synthetic dataset")
    accepted, rejected = [], []
    ids, incidents, evidence_ids, paths = set(), set(), set(), set()
    for scenario in raw["scenarios"]:
        try:
            sid, iid = scenario["scenario_id"], scenario["incident_id"]
            if sid in ids or iid in incidents:
                raise ValueError("Repeated sequence or incident identifier")
            ids.add(sid)
            incidents.add(iid)
            events = sorted(scenario["events"], key=lambda event: stamp(event["timestamp"]))
            if len(events) < 3:
                raise ValueError("Fewer than three events")
            local_ids = [event["evidence_id"] for event in events]
            if len(set(local_ids)) != len(local_ids) or evidence_ids.intersection(local_ids):
                raise ValueError("Repeated evidence identifier across sequences")
            evidence_ids.update(local_ids)
            for event in events:
                if event.get("scenario_id") != sid or event.get("incident_id") != iid:
                    raise ValueError("Event belongs to another sequence")
            safe_prefix(events, events[-1]["timestamp"], catalog()["techniques"])
            sequence_path = tuple(event["technique_id"] for event in events)
            if sequence_path in paths:
                raise ValueError("Duplicate complete technique sequence")
            paths.add(sequence_path)
            # One midpoint per group, selected without consulting target labels.
            index = max(1, (len(events) - 1) // 2)
            cutoff = events[index]["timestamp"]
            target = events[index + 1]
            if stamp(target["timestamp"]) <= stamp(cutoff):
                raise ValueError("Target not strictly after cutoff")
            prefix_features = features(safe_prefix(events, cutoff, catalog()["techniques"]))
            accepted.append({"scenario_id": sid, "incident_id": iid, "start": events[0]["timestamp"],
                             "end": events[-1]["timestamp"], "events": len(events), "cutoff_timestamp": cutoff,
                             "target_timestamp": target["timestamp"], "target_event_id": target["evidence_id"],
                             "target": target["technique_id"], "features": prefix_features})
        except (ValueError, KeyError, TypeError) as exc:
            rejected.append({"scenario_id": scenario.get("scenario_id"), "rows": len(scenario.get("events", [])), "reason": str(exc)})
    accepted.sort(key=lambda sample: stamp(sample["start"]))
    if len(accepted) < 30:
        raise ValueError("Insufficient valid sequences: at least 30 required")
    a, b = int(len(accepted) * .7), int(len(accepted) * .85)
    parts = dict(train=accepted[:a], validation=accepted[a:b], test=accepted[b:])
    for left, right in (("train", "validation"), ("validation", "test")):
        if max(stamp(x["end"]) for x in parts[left]) >= min(stamp(x["start"]) for x in parts[right]):
            raise ValueError("Sequence time ranges overlap across split boundary")
    manifest = {"dataset_version": raw.get("version", raw.get("dataset_version")), "source_sha256": sha256(Path(path)),
                "data_kind": "synthetic", "label_source": "generator annotations", "limitation": LIMITATION,
                "sequences": len(accepted), "events": sum(x["events"] for x in accepted), "samples": len(accepted),
                "classes": sorted({x["target"] for x in accepted}), "rejected_sequences": rejected,
                "class_counts": dict(sorted(Counter(x["target"] for x in accepted).items())),
                "duplicate_sequence_policy": "Reject exact complete technique paths; repeated prefixes remain legitimate ambiguity",
                "rejected_rows": sum(x["rows"] for x in rejected), "timestamp_quality": "Timezone-aware, unique per sequence; synthetic clock, not collection time",
                "protocol": "Whole sequences ordered by start; 70/15/15%; one label-independent midpoint prefix per sequence; immediate next event target",
                "splits": {name: {"sequences": len(items), "samples": len(items), "start": items[0]["start"], "end": items[-1]["end"],
                                  "class_counts": dict(sorted(Counter(x["target"] for x in items).items())),
                                  "sample_sha256": digest(items), "scenario_ids": [x["scenario_id"] for x in items]} for name, items in parts.items()}}
    return manifest, parts


def markov(rows, labels, counts, prior):
    result = []
    for row in rows:
        values = counts.get(row["technique_suffix_1"], Counter())
        # Unit Dirichlet mass distributed according to training prior.
        result.append([(values.get(label, 0) + prior[label]) / (sum(values.values()) + 1) for label in labels])
    return np.asarray(result)


def gate(probabilities, labels, thresholds):
    if len(probabilities) != len(labels) or len(labels) < 2 or len(set(labels)) != len(labels):
        raise ValueError("Invalid class/probability vector")
    uncertainty = entropy(probabilities)
    ordered = sorted(zip(labels, probabilities), key=lambda pair: (-pair[1], pair[0]))
    reason = None
    if ordered[0][1] < thresholds["abstain_below_probability"]:
        reason = "Top probability below configured threshold"
    elif uncertainty > thresholds["abstain_above_uncertainty"]:
        reason = "Normalized entropy above configured threshold"
    return {"status": "ABSTAINED" if reason else "PREDICTED", "abstain_reason": reason,
            "predicted_technique_id": None if reason else ordered[0][0],
            "probability": None if reason else float(ordered[0][1]), "uncertainty": uncertainty,
            "top_k": [{"rank": i + 1, "technique_id": label, "probability": float(p)} for i, (label, p) in enumerate(ordered[:5])]}


def metrics(actual, probabilities, labels, thresholds):
    measured = evaluate(actual, probabilities, labels)
    decisions = [gate(row, labels, thresholds) for row in probabilities]
    chosen = [i for i, decision in enumerate(decisions) if decision["status"] == "PREDICTED"]
    measured.update(coverage=len(chosen) / len(actual), abstention_rate=1 - len(chosen) / len(actual),
                    selective_accuracy=sum(decisions[i]["predicted_technique_id"] == actual[i] for i in chosen) / len(chosen) if chosen else None)
    # Wilson interval: one test sample per sequence; generator dependence remains a limitation.
    p, n, z = measured["top_1_accuracy"], len(actual), 1.95996398454
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    measured["top_1_wilson_95"] = [center-radius, center+radius]
    return measured


def temperature_scale(probabilities, temperature):
    probabilities = np.asarray(probabilities, dtype=float)
    logits = np.log(np.maximum(probabilities, 1e-12)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    values = np.exp(logits)
    return values / values.sum(axis=1, keepdims=True)


def score(actual, probabilities, labels):
    result = evaluate(actual, probabilities, labels)
    return result["top_1_accuracy"], result["macro_f1"]


def model_outputs(model, rows):
    labels = model["labels"]
    return {"Most frequent": np.asarray([[model["prior"][label] for label in labels]] * len(rows)),
            "Markov": markov(rows, labels, model["counts"], model["prior"]),
            "Random Forest": model["forest"].predict_proba(rows),
            "Gradient Boosting": model["boosting"].predict_proba(rows),
            "Sequence model": np.asarray(model["sequence"].predict_proba(rows))}


def proposed(model, outputs, calibrated=True):
    mixed = sum(model["weights"][name] * outputs[name] for name in model["weights"])
    return temperature_scale(mixed, model["temperature"]) if calibrated else mixed


def fit_models(train_rows, selection, calibration):
    """No test parameter: all model choices end here, before evaluation."""
    labels = sorted({row["target"] for row in train_rows})
    if len(labels) < 2:
        raise ValueError("Insufficient training classes")
    x = [row["features"] for row in train_rows]
    y = [row["target"] for row in train_rows]
    vx, vy = [row["features"] for row in selection], [row["target"] for row in selection]
    prior = {label: y.count(label) / len(y) for label in labels}
    counts = {}
    for row, target in zip(x, y):
        counts.setdefault(row["technique_suffix_1"], Counter())[target] += 1
    trials = []
    selected = {}
    # Small predeclared grids; no test-based adaptive searching.
    grids = {
        "forest": [{**RF_PARAMS, "max_depth": depth, "class_weight": balance} for depth in (6, 12) for balance in (None, "balanced")],
        "boosting": [dict(max_iter=80, max_leaf_nodes=leaves, learning_rate=.1, l2_regularization=1., early_stopping=False,
                          random_state=SEED, class_weight=balance) for leaves in (7, 15) for balance in (None, "balanced")],
    }
    for name, grid in grids.items():
        candidates = []
        for parameters in grid:
            estimator = RandomForestClassifier(**parameters) if name == "forest" else HistGradientBoostingClassifier(**parameters)
            fitted = make_pipeline(DictVectorizer(sparse=name == "forest"), estimator).fit(x, y)
            accuracy, f1 = score(vy, fitted.predict_proba(vx), labels)
            trial = {"model": name, "parameters": parameters, "selection_accuracy": accuracy, "selection_macro_f1": f1}
            trials.append(trial)
            candidates.append(((accuracy, f1), fitted, parameters))
        best = max(candidates, key=lambda item: item[0])
        selected[name] = best[1]
        selected[name + "_parameters"] = best[2]
    sequence = TransitionFrequency().fit(x, y)
    model = {**selected, "sequence": sequence, "counts": counts, "prior": prior, "labels": labels}
    validation = model_outputs(model, vx)
    names = ("Markov", "Random Forest", "Gradient Boosting", "Sequence model")
    weight_trials = []
    for a in range(5):
        for b in range(5-a):
            for c in range(5-a-b):
                weights = (a/4, b/4, c/4, (4-a-b-c)/4)
                if sum(weight > 0 for weight in weights) < 2:
                    continue
                mapping = dict(zip(names, weights))
                accuracy, f1 = score(vy, sum(mapping[name] * validation[name] for name in names), labels)
                weight_trials.append({"weights": mapping, "selection_accuracy": accuracy, "selection_macro_f1": f1})
    best = max(weight_trials, key=lambda trial: (trial["selection_accuracy"], trial["selection_macro_f1"]))
    model["weights"] = best["weights"]
    cx, cy = [row["features"] for row in calibration], [row["target"] for row in calibration]
    uncalibrated = proposed(model, model_outputs(model, cx), calibrated=False)
    temperatures = []
    for temperature in (.5, .75, 1., 1.25, 1.5, 2.):
        probabilities = temperature_scale(uncalibrated, temperature)
        loss = -sum(math.log(max(probabilities[i][labels.index(target)] if target in labels else 0., 1e-12)) for i, target in enumerate(cy)) / len(cy)
        temperatures.append({"temperature": temperature, "calibration_log_loss": loss})
    model["temperature"] = min(temperatures, key=lambda trial: trial["calibration_log_loss"])["temperature"]
    return model, {"hyperparameter_trials": trials, "ensemble_trials": weight_trials, "temperature_trials": temperatures,
                   "selected_weights": model["weights"], "selected_temperature": model["temperature"],
                   "selected_forest_parameters": model["forest_parameters"], "selected_boosting_parameters": model["boosting_parameters"],
                   "selection_rule": "Maximize selection Top-1, then macro F1; grid order breaks remaining ties. Minimize calibration NLL separately.",
                   "class_balancing": "Training-only class_weight None vs balanced; no sample duplication or validation/test resampling"}


@threadpool_limits.wrap(limits=1)
def train(path=SOURCE, output=OUTPUT):
    manifest, parts = build(path)
    # Keep previously evaluated groups fixed. Never move samples to meet the target.
    initial = DATA / "model_evaluations/chronological_prediction/initial-evaluation-v1/report.json"
    if initial.exists() and Path(path).resolve() == SOURCE.resolve():
        previous = json.loads(initial.read_text())["manifest"]
        for part in parts:
            if manifest["splits"][part]["scenario_ids"] != previous["splits"][part]["scenario_ids"]:
                raise ValueError("Frozen scenario split changed")
    validation = parts["validation"]
    boundary = len(validation)*2//3
    selection, calibration = validation[:boundary], validation[boundary:]
    model, tuning = fit_models(parts["train"], selection, calibration)
    config_path = Path(__file__).resolve().parents[1] / "config/defense.json"
    thresholds = json.loads(config_path.read_text())["inference"]
    model.update(thresholds=thresholds, model_name="FAPT-Guard Temporal Prediction Model", model_version=VERSION,
                 feature_version=FEATURE_VERSION, training_dataset_version=manifest["dataset_version"], dataset_sha256=manifest["source_sha256"])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frozen = {"version": VERSION, "source_sha256": manifest["source_sha256"], "feature_version": FEATURE_VERSION,
              "split_hashes": {name: info["sample_sha256"] for name, info in manifest["splits"].items()},
              "tuning": tuning, "thresholds": thresholds, "selection_sequences": len(selection), "calibration_sequences": len(calibration),
              "test_disclosure": "Same fixed test scenarios were previously evaluated under v1. Results are exploratory, not an untouched confirmatory test.",
              "target_top1_accuracy": TARGET_TOP1_ACCURACY}
    frozen_path = output / "frozen_config.json"
    if frozen_path.exists() and json.loads(frozen_path.read_text()) != frozen:
        raise ValueError("Frozen configuration differs; do not silently overwrite the evaluated protocol")
    frozen_path.write_text(json.dumps(frozen, indent=2, allow_nan=False), encoding="utf-8")
    # Model configuration is now frozen, before accessing final test labels for scoring.
    joblib.dump(model, output / "model.joblib")
    model_hash = sha256(output / "model.joblib")
    tx, ty = [row["features"] for row in parts["test"]], [row["target"] for row in parts["test"]]
    predictions = model_outputs(model, tx)
    predictions["FAPT-Guard"] = proposed(model, predictions)
    results = {name: metrics(ty, proba, model["labels"], thresholds) for name, proba in predictions.items()}
    uncalibrated = proposed(model, predictions, calibrated=False)
    # Predeclared ablation/robustness: suppress timing/source/action context, no retraining or tuning.
    reduced = [{key: value for key, value in row.items() if not key.startswith(("source_count:", "action_count:")) and key not in ("elapsed_seconds", "last_interval_seconds")} for row in tx]
    robustness = metrics(ty, proposed(model, model_outputs(model, reduced)), model["labels"], thresholds)
    test_rows = [{"scenario_id": row["scenario_id"], "target": row["target"],
                  "probabilities": {name: values[i].tolist() for name, values in predictions.items()}}
                 for i, row in enumerate(parts["test"])]
    value = {"status": "AVAILABLE", "evaluation_scope": "OFFLINE TEMPORAL EVALUATION - SYNTHETIC", "limitation": LIMITATION,
             "manifest": manifest, "model_name": model["model_name"], "model_version": VERSION, "model_hash": model_hash,
             "feature_version": FEATURE_VERSION, "supported_classes": model["labels"], "seed": SEED,
             "implementation_sha256": sha256(Path(__file__)), "samples_sha256": digest(parts), "frozen_config": frozen,
             "frozen_config_sha256": sha256(frozen_path), "thresholds": thresholds,
             "config_sha256": sha256(config_path), "catalog_sha256": catalog()["sha256"],
             "software": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "joblib": joblib.__version__},
             "calibration_status": "Temperature scaling fitted on last 50 validation sequences; baselines uncalibrated",
             "neural_sequence_model": "NOT MEASURED: torch/tensorflow unavailable; non-neural variable-order suffix model evaluated",
             "robustness": {"unseen_sequences": "All test sequence identifiers and full technique paths absent from training",
                            "leave_family_out": "NOT AVAILABLE: v2 has no independent scenario-family annotations; random transition walks are not attack families",
                            "context_removed": robustness},
             "uncalibrated_proposed_metrics": metrics(ty, uncalibrated, model["labels"], thresholds),
             "results": results, "test_predictions_sha256": digest(test_rows),
             "target_top1_accuracy": TARGET_TOP1_ACCURACY,
             "target_achieved": results["FAPT-Guard"]["top_1_accuracy"] >= TARGET_TOP1_ACCURACY}
    for name, obj in (("samples", parts), ("test_predictions", test_rows), ("report", value)):
        (output / f"{name}.json").write_text(json.dumps(obj, indent=2, allow_nan=False), encoding="utf-8")
    return value


def report(output=OUTPUT):
    output = Path(output)
    path = output / "report.json"
    if not path.exists():
        return {"status": "NOT AVAILABLE", "reason": "Run python -m app.prediction_benchmark from backend", "limitation": LIMITATION}
    value = json.loads(path.read_text(encoding="utf-8"))
    if sha256(output / "model.joblib") != value["model_hash"] or sha256(SOURCE) != value["manifest"]["source_sha256"]:
        raise ValueError("Benchmark model or dataset hash mismatch; rerun reproducible training")
    predictions = json.loads((output / "test_predictions.json").read_text(encoding="utf-8"))
    if digest(predictions) != value["test_predictions_sha256"]:
        raise ValueError("Benchmark test predictions hash mismatch")
    samples = json.loads((output / "samples.json").read_text(encoding="utf-8"))
    if digest(samples) != value["samples_sha256"]:
        raise ValueError("Benchmark samples hash mismatch")
    if sha256(output / "frozen_config.json") != value["frozen_config_sha256"]:
        raise ValueError("Benchmark frozen configuration hash mismatch")
    return value


@threadpool_limits.wrap(limits=1)
def predict(events, cutoff, output=OUTPUT):
    result = {"status": "ABSTAINED", "predicted_technique_id": None, "probability": None, "uncertainty": None,
              "top_k": [], "abstain_reason": None, "cutoff_timestamp": cutoff, "limitation": LIMITATION}
    try:
        metadata = report(output)
        if metadata["status"] != "AVAILABLE":
            raise ValueError(metadata["reason"])
        model = joblib.load(Path(output) / "model.joblib")
        row = features(safe_prefix(events, cutoff, model["labels"]))
        probabilities = proposed(model, model_outputs(model, [row]))[0]
        decision = gate(probabilities, model["labels"], model["thresholds"])
        supporting = [event["evidence_id"] for event in events if stamp(event["timestamp"]) <= stamp(cutoff)]
        return {**result, **decision, **{key: metadata[key] for key in ("model_name", "model_version", "model_hash", "feature_version", "calibration_status")},
                "prediction_id": "RESEARCH-" + digest([metadata["model_hash"], supporting, cutoff])[:24],
                "predicted_technique_name": catalog()["techniques"][decision["predicted_technique_id"]]["name"] if decision["predicted_technique_id"] else None,
                "training_dataset_version": model["training_dataset_version"], "prediction_horizon": "Immediate next annotated event; elapsed time not predicted",
                "observation_window_minutes": None, "observation_window_reason": "Entire available scenario prefix, not a fixed-duration operational window",
                "supporting_event_ids": supporting, "supporting_evidence_ids": supporting,
                "execution_mode": "DRY_RUN", "scope": "SYNTHETIC RESEARCH ONLY"}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {**result, "abstain_reason": str(exc)}


def demonstration(scenario_id):
    metadata = report()
    if metadata["status"] != "AVAILABLE":
        raise ValueError(metadata["reason"])
    samples = json.loads((OUTPUT / "samples.json").read_text())["test"]
    sample = next((item for item in samples if item["scenario_id"] == scenario_id), None)
    if sample is None:
        raise ValueError("Choose a frozen test scenario from the benchmark manifest")
    scenario = next(item for item in json.loads(SOURCE.read_text())["scenarios"] if item["scenario_id"] == scenario_id)
    return {"scenario_id": scenario_id, "prediction": predict(scenario["events"], sample["cutoff_timestamp"]),
            "hindsight_target": {"technique_id": sample["target"], "timestamp": sample["target_timestamp"],
                                 "label_source": "synthetic_annotation", "validated_ground_truth": False},
            "notice": "Hindsight target shown separately for evaluation; never an inference input. No host action executed."}


if __name__ == "__main__":
    result = train()
    print(json.dumps({name: {key: value[key] for key in ("top_1_accuracy", "top_3_accuracy", "macro_f1", "coverage", "abstention_rate")} for name, value in result["results"].items()}, indent=2))
