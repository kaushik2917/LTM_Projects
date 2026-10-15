"""Prospective synthetic protocol: prepare -> freeze -> generate/evaluate once.

Old test rows never enter fit/select/calibrate. A new test draw is created only
after the model and generator specification are frozen. No operational activation.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import argparse
import json
import math
from pathlib import Path
import random
import secrets

import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from app import prediction_benchmark as b
from app.datasets import DATA, sha256
from app.temporal_prediction import digest, stamp, now

ROOT = DATA / "model_evaluations/prospective_temporal_v1"
NAMES = ("Most frequent", "Markov", "Random Forest", "Gradient Boosting", "Sequence model", "FAPT-Guard")


class SmoothedHistory:
    """Hierarchical Dirichlet smoothing backs sparse suffixes toward shorter history."""
    def __init__(self, order=3, strength=5):
        self.order, self.strength = order, strength

    def fit(self, rows, targets):
        self.classes_ = sorted(set(targets))
        self.prior = Counter(targets)
        self.counts = {n: defaultdict(Counter) for n in range(1, self.order+1)}
        for row, target in zip(rows, targets):
            for n in self.counts:
                self.counts[n][row[f"technique_suffix_{n}"]][target] += 1
        return self

    def predict_proba(self, rows):
        result = []
        for row in rows:
            p = np.array([self.prior[label]/sum(self.prior.values()) for label in self.classes_])
            for n in self.counts:
                counts = self.counts[n].get(row[f"technique_suffix_{n}"], {})
                total = sum(counts.values())
                p = (np.array([counts.get(label, 0) for label in self.classes_]) + self.strength*p)/(total+self.strength)
            result.append(p)
        return np.asarray(result)


def feature_row(events, cutoff):
    visible = b.safe_prefix(events, cutoff, b.catalog()["techniques"])
    values = b.features(visible)
    ids = [e["technique_id"] for e in visible]
    for n in (4, 5):
        values[f"technique_suffix_{n}"] = "|".join(ids[-n:])
    elapsed = values["elapsed_seconds"]
    values["event_density_per_second"] = len(visible)/max(1., elapsed)
    for i, event in enumerate(visible):
        age = (stamp(cutoff)-stamp(event["timestamp"])).total_seconds()
        key = "decayed_count:"+event["technique_id"]
        values[key] = values.get(key, 0.) + math.exp(-age/300.)
        if i >= 2:
            key = "trigram:"+"|".join(ids[i-2:i+1])
            values[key] = values.get(key, 0)+1
    values["tactic_suffix_3"] = " / ".join("|".join(b.catalog()["techniques"][tid]["tactics"]) for tid in ids[-3:])
    return values


def sample(scenario, index):
    events = sorted(scenario["events"], key=lambda e: stamp(e["timestamp"]))
    cutoff = events[index]["timestamp"]
    target = events[index+1]
    if stamp(target["timestamp"]) <= stamp(cutoff):
        raise ValueError("Target must be strictly after cutoff")
    return {"scenario_id": scenario["scenario_id"], "incident_id": scenario["incident_id"],
            "cutoff_timestamp": cutoff, "target_event_id": target["evidence_id"], "target_timestamp": target["timestamp"],
            "target": target["technique_id"], "features": feature_row(events, cutoff)}


def development():
    bundle = json.loads(b.SOURCE.read_text())
    groups = sorted(bundle["scenarios"], key=lambda s: stamp(s["events"][0]["timestamp"]))
    # Membership fixed from the pre-existing chronological protocol; no old test labels used.
    roles = {"train": groups[:700], "validation": groups[700:800], "probability_calibration": groups[800:825], "conformal_calibration": groups[825:850]}
    rows = {role: [sample(s, max(1, (len(s["events"])-1)//2)) for s in selected] for role, selected in roles.items()}
    # Entire historical dataset is an exclusion registry only: hashes forbid reuse in new test.
    registry = {"scenario_ids": [s["scenario_id"] for s in groups], "incident_ids": [s["incident_id"] for s in groups],
                "paths": [digest([e["technique_id"] for e in s["events"]]) for s in groups],
                "last_timestamp": max(e["timestamp"] for s in groups for e in s["events"])}
    return rows, {role: [s["scenario_id"] for s in selected] for role, selected in roles.items()}, registry


def raw_outputs(model, rows):
    outputs = b.model_outputs(model, rows)
    if model["proposed_kind"] == "smoothed":
        outputs["FAPT-Guard"] = model["smoothed"].predict_proba(rows)
    elif model["proposed_kind"] == "ensemble":
        outputs["FAPT-Guard"] = b.proposed(model, outputs, calibrated=False)
    else:
        outputs["FAPT-Guard"] = outputs[model["proposed_kind"]]
    return outputs


def calibrated_outputs(model, rows):
    return {name: b.temperature_scale(values, model["temperatures"][name]) for name, values in raw_outputs(model, rows).items()}


def conformal_threshold(probabilities, targets, labels):
    scores = [1-row[labels.index(target)] if target in labels else 1. for row, target in zip(probabilities, targets)]
    rank = math.ceil((len(scores)+1)*.9)
    return sorted(scores)[rank-1] if rank <= len(scores) else 1.


def set_metrics(probabilities, targets, labels, threshold):
    sets = [[label for label, p in zip(labels, row) if 1-p <= threshold] for row in probabilities]
    return {"conformal_target_coverage": .9, "conformal_coverage": sum(y in s for y,s in zip(targets,sets))/len(sets),
            "average_prediction_set_size": sum(map(len,sets))/len(sets), "minimum_prediction_set_size": min(map(len,sets)),
            "maximum_prediction_set_size": max(map(len,sets))}


def write_exclusive(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


@threadpool_limits.wrap(limits=1)
def prepare(root=ROOT):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root/"frozen.json").exists():
        raise ValueError("Already frozen: refuse refitting this experiment")
    rows, roles, registry = development()
    model, tuning = b.fit_models(rows["train"], rows["validation"], rows["probability_calibration"])
    vx, vy = [r["features"] for r in rows["validation"]], [r["target"] for r in rows["validation"]]
    outputs = b.model_outputs(model, vx)
    outputs["ensemble"] = b.proposed(model, outputs, calibrated=False)
    candidates = []
    for name, values in outputs.items():
        candidates.append({"kind": name, "parameters": None, "score": b.score(vy, values, model["labels"])})
    fitted = {}
    for order in (1, 2, 3, 5):
        for strength in (1, 5, 20):
            estimator = SmoothedHistory(order, strength).fit([r["features"] for r in rows["train"]], [r["target"] for r in rows["train"]])
            key = f"smoothed-{order}-{strength}"
            fitted[key] = estimator
            candidates.append({"kind": key, "parameters": {"order": order, "strength": strength}, "score": b.score(vy, estimator.predict_proba(vx), model["labels"])})
    # Select by validation Top-1 then macro F1; stable declared candidate order breaks ties.
    best = max(candidates, key=lambda c: c["score"])
    model["proposed_kind"] = "smoothed" if best["kind"].startswith("smoothed-") else best["kind"]
    if model["proposed_kind"] == "smoothed":
        model["smoothed"] = fitted[best["kind"]]
    validation_outputs = raw_outputs(model, vx)
    # Calibrate each frozen candidate model identically, using probability subgroup only.
    px, py = [r["features"] for r in rows["probability_calibration"]], [r["target"] for r in rows["probability_calibration"]]
    temperatures = {}
    temperature_trials = {}
    for name, values in raw_outputs(model, px).items():
        trials = []
        for temperature in (.5, .75, 1., 1.25, 1.5, 2., 3., 4.):
            scaled = b.temperature_scale(values, temperature)
            loss = -sum(math.log(max(row[model["labels"].index(y)] if y in model["labels"] else 0., 1e-12)) for row,y in zip(scaled,py))/len(py)
            trials.append({"temperature": temperature, "nll": loss})
        temperature_trials[name] = trials
        temperatures[name] = min(trials, key=lambda t: (t["nll"], abs(t["temperature"]-1)))["temperature"]
    model["temperatures"] = temperatures
    cx, cy = [r["features"] for r in rows["conformal_calibration"]], [r["target"] for r in rows["conformal_calibration"]]
    model["conformal_thresholds"] = {name: conformal_threshold(values, cy, model["labels"]) for name,values in calibrated_outputs(model,cx).items()}
    config_path = Path(__file__).resolve().parents[1]/"config/defense.json"
    model["thresholds"] = json.loads(config_path.read_text())["inference"]
    # Generator parameters are unchanged from the historical v2 distribution and frozen now.
    from app.synthetic_temporal import load_dataset
    from app.attack_normalization import normalize
    metadata, groups, _ = normalize(*load_dataset())
    adjacency, templates = defaultdict(Counter), defaultdict(list)
    for events in groups.values():
        for event in events:
            templates[event["technique_id"]].append({k:event[k] for k in ("source", "action")})
        for a, z in zip(events,events[1:]):
            adjacency[a["technique_id"]][z["technique_id"]] += 1
    generator = {"version": "prospective-source-transition-walk-v1", "source_manifest_sha256": metadata["manifest_sha256"],
                 "adjacency": dict(adjacency), "templates": dict(templates), "scenario_count": 300,
                 "repeat_probability": .1, "restart_probability": .1, "length_range": [6,12], "gap_seconds": [20,120],
                 "cutoff": "midpoint; independent of labels", "registry": registry}
    write_exclusive(root/"generator.json", generator)
    write_exclusive(root/"development_samples.json", rows)
    joblib.dump(model, root/"model.joblib")
    frozen = {"experiment_id": "prospective-temporal-v1", "frozen_at": now(), "dataset_version": "2.0.0 development / prospective-v1 test",
              "development_sha256": sha256(b.SOURCE), "feature_version": "future_prediction_v3", "catalog_sha256": b.catalog()["sha256"],
              "model_hash": sha256(root/"model.joblib"), "generator_sha256": sha256(root/"generator.json"),
              "development_samples_sha256": sha256(root/"development_samples.json"), "implementation_sha256": sha256(Path(__file__)),
              "roles": roles, "sample_counts": {name:len(items) for name,items in rows.items()}, "classes": model["labels"],
              "selected": best, "validation_candidates": candidates, "baseline_tuning": tuning,
              "validation_results": {name:b.evaluate(vy,values,model["labels"]) for name,values in validation_outputs.items()},
              "temperature_trials": temperature_trials, "temperatures": temperatures, "conformal_thresholds": model["conformal_thresholds"],
              "conformal_method": "Fixed LAC score=1-p(true), ceil((n+1)*.90) order statistic; no test optimization",
              "limitations": "Synthetic only. Development cohorts previously exposed in historical experiments; prospective test generated after freeze. Not independent real-world or attack-family validation. Deduplication and temporal ordering limit exchangeability guarantees."}
    write_exclusive(root/"frozen.json", frozen)
    return frozen


def load_frozen(root):
    frozen = json.loads((root/"frozen.json").read_text())
    for filename,key in (("model.joblib","model_hash"),("generator.json","generator_sha256"),("development_samples.json","development_samples_sha256")):
        if sha256(root/filename) != frozen[key]:
            raise ValueError("Frozen artifact changed: "+filename)
    if sha256(Path(__file__)) != frozen["implementation_sha256"]:
        raise ValueError("Implementation changed after freeze")
    return frozen


def generate_test(spec, seed):
    rng = random.Random(seed)
    labels = sorted(spec["templates"])
    seen = set(spec["registry"]["paths"])
    groups = []
    rejected = 0
    start = stamp(spec["registry"]["last_timestamp"]) + timedelta(days=1)
    while len(groups) < spec["scenario_count"]:
        ids = [rng.choice(labels)]
        for _ in range(rng.randint(5,11)):
            choices = spec["adjacency"].get(ids[-1], {})
            roll = rng.random()
            if roll < .1:
                ids.append(ids[-1])
            elif roll < .2 or not choices:
                ids.append(rng.choice(labels))
            else:
                ids.append(rng.choices(sorted(choices), [choices[k] for k in sorted(choices)])[0])
        hashed = digest(ids)
        if hashed in seen:
            rejected += 1
            continue
        seen.add(hashed)
        sid = f"PROSPECTIVE-{len(groups)+1:05}"
        clock = start + timedelta(days=len(groups))
        events = []
        for i, technique in enumerate(ids):
            template = rng.choice(spec["templates"][technique])
            clock += timedelta(seconds=rng.randint(20,120))
            events.append({"evidence_id": f"{sid}-E{i:03}", "scenario_id": sid, "incident_id": sid,
                           "timestamp": clock.isoformat(), "label_known_at": clock.isoformat(), "technique_id": technique,
                           "simulated": True, "label_status": "synthetic_annotation", **template})
        groups.append({"scenario_id": sid, "incident_id": sid, "events": events})
    return {"version": "prospective-v1", "synthetic": True, "seed": seed, "duplicate_paths_rejected": rejected, "scenarios": groups}


@threadpool_limits.wrap(limits=1)
def evaluate_once(root=ROOT):
    root = Path(root)
    frozen = load_frozen(root)
    # Exclusive lock makes a second score operation impossible; do not erase on failure.
    write_exclusive(root/"evaluation_started.json", {"started_at": now(), "frozen_sha256": sha256(root/"frozen.json"), "seed": secrets.randbits(63)})
    started = json.loads((root/"evaluation_started.json").read_text())
    spec = json.loads((root/"generator.json").read_text())
    dataset = generate_test(spec, started["seed"])
    write_exclusive(root/"test_dataset.json", dataset)
    records = [sample(s, max(1,(len(s["events"])-1)//2)) for s in dataset["scenarios"]]
    model = joblib.load(root/"model.joblib")
    x,y = [r["features"] for r in records], [r["target"] for r in records]
    raw = raw_outputs(model,x)
    probabilities = calibrated_outputs(model,x)
    results = {name:{**b.metrics(y, values, model["labels"], model["thresholds"]),
                     **set_metrics(values,y,model["labels"],model["conformal_thresholds"][name]),
                     "raw_calibration": {k:b.evaluate(y,raw[name],model["labels"])[k] for k in ("multiclass_brier_score","expected_calibration_error")}}
               for name,values in probabilities.items()}
    write_exclusive(root/"test_predictions.json", {"samples": records, "probabilities": {k:v.tolist() for k,v in probabilities.items()}})
    report = {"status": "EVALUATED", "experiment_id": frozen["experiment_id"], "scope": "PROSPECTIVE SYNTHETIC TEST - NOT REAL-WORLD VALIDATION",
              "frozen": frozen, "evaluated_at": now(), "test_dataset_sha256": sha256(root/"test_dataset.json"),
              "test_predictions_sha256": sha256(root/"test_predictions.json"), "frozen_sha256": sha256(root/"frozen.json"),
              "test_sequences":len(records), "test_events":sum(len(s["events"]) for s in dataset["scenarios"]),
              "test_class_counts":dict(Counter(y)), "results":results, "target_top1_accuracy":.9,
              "target_achieved":results["FAPT-Guard"]["top_1_accuracy"]>=.9,
              "leakage_checks": {"generated_after_freeze":True,"historical_test_excluded_from_selection":True,
                                 "scenario_incident_path_disjoint":True,"strict_future_targets":True,"one_evaluation_lock":True},
              "limitations":frozen["limitations"]}
    write_exclusive(root/"report.json",report)
    return report


def status():
    if not (ROOT/"report.json").exists():
        return {"status":"NOT EVALUATED", "reason":"Prospective protocol not evaluated"}
    value=json.loads((ROOT/"report.json").read_text())
    load_frozen(ROOT)
    for filename,key in (("test_dataset.json","test_dataset_sha256"),("test_predictions.json","test_predictions_sha256"),("frozen.json","frozen_sha256")):
        if sha256(ROOT/filename)!=value[key]:
            raise ValueError("Prospective artifact hash mismatch: "+filename)
    return value


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare","evaluate","status"])
    args=parser.parse_args()
    # Stable module class identity for locally persisted joblib artifacts.
    from app.prospective_prediction import prepare, evaluate_once, status
    value={"prepare":prepare,"evaluate":evaluate_once,"status":status}[args.phase]()
    print(json.dumps({k:value[k] for k in ("status","selected","results") if k in value},indent=2))
