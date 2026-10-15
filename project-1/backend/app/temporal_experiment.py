"""Versioned synthetic experiment; no execution capability or observed-data claims.

Reuses the original transition estimator, prefix features and metric functions.
Calibration fitting and conformal calibration use disjoint scenario subgroups.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import math
import random
import statistics
from pathlib import Path
from uuid import uuid4

from app.datasets import DATA, sha256
from app.temporal_prediction import entropy, evaluate, now, prefix, stamp, digest
from app.services.attack_service import catalog

VERSION = "2.0.0"
GENERATOR = "source-transition-walk-v1"
SEED = 20261003
DATASET = DATA / "custom/synthetic_temporal_v2/scenarios.json"
POINTER = DATA / "models/temporal_experiment.json"
PARTS = ("train", "calibration_probability", "calibration_conformal", "test")
LIMITATION = "Synthetic-trained research model applied to simulated incident. Not real-world validated. Generated paths are research assumptions, not observed attacks; calibration does not establish accuracy or causal prevention effects."


def ground_truth(events, cutoff):
    return next((e for e in sorted(events, key=lambda e: stamp(e["timestamp"]))
                 if stamp(e["timestamp"]) > stamp(cutoff) and e.get("technique_id")), None)


def outcome(events, cutoff, probabilities):
    target = ground_truth(events, cutoff)
    if target is None:
        return {"ground_truth": {"status": "PENDING", "event": None},
                "evaluation": {"status": "PENDING_GROUND_TRUTH", "correct": None,
                "actual_next_technique": None, "prediction_rank": None, "prediction_probability_for_actual_class": None}}
    ranked = sorted(probabilities, key=lambda t: (-probabilities[t], t))
    actual = target["technique_id"]
    correct = ranked[0] == actual
    return {"ground_truth": {"status": "OBSERVED", "event": target, "source": "synthetic scenario annotation"},
            "evaluation": {"status": "CORRECT" if correct else "INCORRECT", "correct": correct,
            "actual_next_technique": actual, "prediction_rank": ranked.index(actual) + 1 if actual in ranked else None,
            "prediction_probability_for_actual_class": probabilities.get(actual, 0.)}}


def validate(bundle):
    seen, incidents, evidence, patterns = set(), set(), set(), {}
    groups = {p: [] for p in PARTS}
    for scenario in bundle["scenarios"]:
        sid, iid, part = (scenario[k] for k in ("scenario_id", "incident_id", "split"))
        if sid in seen or iid in incidents: raise ValueError("Duplicate scenario/incident across partitions")
        seen.add(sid); incidents.add(iid)
        if part not in groups: raise ValueError("Unknown split")
        groups[part].append(sid)
        events = scenario["events"]
        if len(events) < 3: raise ValueError("Incomplete scenario")
        fingerprint = digest([e.get("technique_id") for e in events])
        if fingerprint in patterns: raise ValueError("Duplicated full technique sequence")
        patterns[fingerprint] = part
        for index, event in enumerate(events):
            if event["scenario_id"] != sid or event["incident_id"] != iid: raise ValueError("Mismatched event ownership")
            if event["evidence_id"] in evidence: raise ValueError("Duplicate evidence ID")
            evidence.add(event["evidence_id"])
            if index and stamp(events[index-1]["timestamp"]) >= stamp(event["timestamp"]): raise ValueError("Nonchronological events")
            if event["sequence_position"] != index + 1: raise ValueError("Invalid sequence position")
            if event["technique_id"] and event["technique_id"] not in catalog()["techniques"]: raise ValueError("Inactive technique")
            future = ground_truth(events, event["timestamp"])
            if event["next_technique_id"] != (future["technique_id"] if future else None): raise ValueError("Incorrect next label")
            if event["next_event_timestamp"] != (future["timestamp"] if future else None): raise ValueError("Incorrect next time")
        observed, _ = prefix(events, scenario["cutoff_timestamp"])
        target = ground_truth(events, scenario["cutoff_timestamp"])
        if not observed or target is None: raise ValueError("Missing prefix/future")
        if target["evidence_id"] in {e["evidence_id"] for e in observed}: raise ValueError("Future leakage")
    if not all(groups.values()): raise ValueError("Empty partition")
    return {"scenario_ids": groups, "scenario_counts": {p: len(ids) for p, ids in groups.items()},
            "scenario_and_incident_disjoint": True, "unique_full_sequences": True, "prefix_targets_verified": True}


def generate():
    from app.synthetic_temporal import load_dataset
    from app.attack_normalization import normalize
    metadata, groups, _ = normalize(*load_dataset())
    adjacency, templates = defaultdict(Counter), defaultdict(list)
    for events in groups.values():
        for e in events: templates[e["technique_id"]].append(e)
        for a, b in zip(events, events[1:]): adjacency[a["technique_id"]][b["technique_id"]] += 1
    rng = random.Random(SEED)
    labels = sorted(templates)
    scenarios, fingerprints = [], set()
    while len(scenarios) < 1000:
        path = [rng.choice(labels)]
        for _ in range(rng.randint(5, 11)):
            choices = adjacency[path[-1]]
            # Existing transitions dominate. Self repeats and restarts are explicit
            # synthetic assumptions, widening paths without inventing technique IDs.
            roll = rng.random()
            if roll < .1: path.append(path[-1])
            elif roll < .2 or not choices: path.append(rng.choice(labels))
            else: path.append(rng.choices(sorted(choices), [choices[t] for t in sorted(choices)])[0])
        if tuple(path) in fingerprints: continue
        fingerprints.add(tuple(path))
        index = len(scenarios)
        sid, iid = f"SYN2-{index+1:05d}", f"SYN2-INC-{index+1:05d}"
        clock = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
        events = []
        for position, tid in enumerate(path, 1):
            source = rng.choice(templates[tid])
            clock += timedelta(seconds=rng.randint(20, 120))
            events.append({"scenario_id": sid, "incident_id": iid, "evidence_id": f"{sid}-EV-{position:03d}",
                "host": f"SYN-HOST-{index % 40:02d}", "user": f"syn-user-{index % 25:02d}",
                "timestamp": clock.isoformat(), "label_known_at": clock.isoformat(),
                "action": source["action"], "source": source["source"], "subject": source["subject"], "object": source["object"],
                "technique_id": tid, "attack_technique_id": tid, "technique_name": source["technique_name"], "tactic": source["tactic"],
                "mapping_status": "CONFIRMED", "mapping_confidence": None, "label_status": "synthetic_annotation",
                "mapping_reason": "Generator annotation, not sensor-confirmed behavior or a confidence measurement",
                "sequence_position": position, "simulated": True})
        for i, event in enumerate(events):
            nxt = events[i+1] if i+1 < len(events) else None
            event.update(next_technique_id=nxt["technique_id"] if nxt else None, next_event_timestamp=nxt["timestamp"] if nxt else None)
        # One cutoff sampled without reference to its future label for calibration/test.
        cutoff = events[rng.randrange(len(events)-1)]["timestamp"]
        scenarios.append({"scenario_id": sid, "incident_id": iid, "events": events, "cutoff_timestamp": cutoff})
    order = list(range(len(scenarios))); rng.shuffle(order)
    for rank, i in enumerate(order):
        scenarios[i]["split"] = "train" if rank < 700 else "calibration_probability" if rank < 775 else "calibration_conformal" if rank < 850 else "test"
    bundle = {"version": VERSION, "dataset_name": "FAPT-Guard Synthetic Temporal ATT&CK Sequence Dataset", "generator_version": GENERATOR,
        "seed": SEED, "source_manifest_sha256": metadata["manifest_sha256"], "catalog_sha256": catalog()["sha256"],
        "normalization": metadata["normalization"], "synthetic": True, "real_world_validation": False,
        "assumptions": "Source transition walks; 10% repeats, 10% uniform restarts, 6-12 events; source event text reused as synthetic templates. Unique full paths by rejection sampling. No claim of template/domain generalization or exact exchangeability after deduplication.",
        "scenarios": scenarios}
    bundle["split_checks"] = validate(bundle)
    DATASET.parent.mkdir(parents=True, exist_ok=True)
    DATASET.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle


def scale(probabilities, temperature):
    entropy(probabilities)  # Reject malformed vectors before applying calibration.
    logits = [math.log(max(p, 1e-6)) / temperature for p in probabilities]
    values = [math.exp(v - max(logits)) for v in logits]
    return [v / sum(values) for v in values]


def conformal_quantile(scores, coverage=.9):
    if not scores: raise ValueError("Insufficient independent calibration outcomes")
    rank = math.ceil((len(scores)+1)*coverage)
    # +infinity threshold at rank n+1 represented as 1: scores lie in [0,1].
    return sorted(scores)[rank-1] if rank <= len(scores) else 1.


def prediction_set(probabilities, labels, threshold):
    return [t for t, p in zip(labels, probabilities) if 1-p <= threshold]


def train_experiment():
    import joblib
    from app.synthetic_temporal import TransitionFrequency, sequence_features
    bundle = generate()
    checks = validate(bundle)
    samples = {part: [] for part in PARTS}
    for s in bundle["scenarios"]:
        cutoffs = [e["timestamp"] for e in s["events"][:-1]] if s["split"] == "train" else [s["cutoff_timestamp"]]
        for cutoff in cutoffs:
            observed, _ = prefix(s["events"], cutoff)
            target = ground_truth(s["events"], cutoff)
            samples[s["split"]].append({"scenario_id": s["scenario_id"], "cutoff_timestamp": cutoff,
                "input_evidence_ids": [e["evidence_id"] for e in observed], "target_event_id": target["evidence_id"],
                "target": target["technique_id"], "features": sequence_features(observed)})
    train = samples["train"]
    model = TransitionFrequency().fit([s["features"] for s in train], [s["target"] for s in train],
                                      [s["input_evidence_ids"][-1] for s in train])
    labels = model.classes_
    if any(s["target"] not in labels for p in PARTS for s in samples[p]): raise ValueError("Untrained future class")
    raw = {p: model.predict_proba([s["features"] for s in samples[p]]) for p in PARTS if p != "train"}
    actual = {p: [s["target"] for s in samples[p]] for p in raw}
    # Reproducible grid search, selected on probability calibration only.
    grid = [.25 + .05*i for i in range(76)]
    def nll(t):
        return -sum(math.log(scale(row, t)[labels.index(y)]) for row,y in zip(raw["calibration_probability"], actual["calibration_probability"])) / len(actual["calibration_probability"])
    temperature = min(grid, key=lambda t: (nll(t), t))
    calibrated = {p: [scale(row, temperature) for row in values] for p, values in raw.items()}
    scores = [1-row[labels.index(y)] for row,y in zip(calibrated["calibration_conformal"], actual["calibration_conformal"])]
    q = conformal_quantile(scores)
    sets = [prediction_set(row, labels, q) for row in calibrated["test"]]
    coverage = sum(y in s for y,s in zip(actual["test"], sets)) / len(sets)
    metrics = {p: {"raw": evaluate(actual[p], raw[p], labels), "calibrated": evaluate(actual[p], calibrated[p], labels)} for p in raw}
    diagnostics = metrics["calibration_conformal"]["calibrated"]
    calibration = {"status": "MEASURED", "calibration_method": "temperature scaling of log(max(raw_p, 1e-6))",
        "version": "temperature-grid-v1", "temperature": temperature, "probability_floor": 1e-6, "grid": grid,
        "fit_partition": "calibration_probability", "diagnostic_partition": "calibration_conformal", "dataset_version": VERSION,
        "calibration_sample_count": len(scores), "calibration_scenario_count": len(scores), "fit_sample_count": len(actual["calibration_probability"]),
        "ECE": diagnostics["expected_calibration_error"], "Brier_score": diagnostics["multiclass_brier_score"],
        "reliability_bins": diagnostics["reliability_bins"], "scope": "Independent calibration subgroup, one cutoff per scenario; test diagnostics reported separately",
        "brier_definition": "Mean over outcomes of sum over all classes (p_k - 1[y=k])^2; no division by class count",
        "ece_definition": "10 equal-width top-confidence bins, weighted absolute confidence/accuracy gap"}
    conformal = {"status": "MEASURED", "method": "split conformal, score=1-p(true), rank=ceil((n+1)*0.90)",
        "target_coverage": .9, "threshold": q, "calibration_partition": "calibration_conformal", "calibration_sample_count": len(scores),
        "calibration_scores": scores, "measured_coverage": coverage, "empirical_coverage": coverage,
        "average_prediction_set_size": statistics.mean(map(len, sets)), "minimum_prediction_set_size": min(map(len, sets)), "maximum_prediction_set_size": max(map(len, sets)),
        "coverage_sample_count": len(sets), "experiment_executed": True, "dataset_level": True,
        "reason": "Measured on independent synthetic TEST scenarios, one predetermined cutoff each. Population procedure metric, not incident confidence. Unique-path rejection sampling limits exact exchangeability claims; no real-world coverage guarantee."}
    calibration["calibration_version"] = digest(calibration)
    eval_id = str(uuid4())
    root = DATA / "model_evaluations" / eval_id
    root.mkdir(parents=True, exist_ok=True)
    artifact_path = root / "transition_frequency.joblib"
    joblib.dump(model, artifact_path)
    report = {"evaluation_id": eval_id, "evaluation_timestamp": now(), "model_name": "transition_frequency",
        "model_version": sha256(artifact_path), "model_path": str(artifact_path.resolve()), "dataset_version": VERSION,
        "dataset_path": str(DATASET.resolve()), "dataset_hash": sha256(DATASET), "catalog_sha256": catalog()["sha256"],
        "dataset_name": bundle["dataset_name"], "generator_version": GENERATOR, "seed": SEED, "split_checks": checks,
        "sample_counts": {p: len(s) for p,s in samples.items()}, "class_order": labels,
        "metrics": metrics["test"]["calibrated"], "partition_metrics": metrics, "calibration": calibration, "conformal": conformal,
        "feature_definition": "Existing sequence_features whitelist; selected model uses only last 3/2/1 mapped techniques, then global training prior. Unsmoothed raw counts; calibration floor applied separately.",
        "prediction_horizon": "Next chronological labelled event strictly after cutoff", "limitation": LIMITATION,
        "uncertainty": {"method": "Normalized predictive entropy", "mean": statistics.mean(entropy(p) for p in calibrated["test"]),
                        "median": statistics.median(entropy(p) for p in calibrated["test"]), "class_count": len(labels)},
        "predictions": {p: [{**{k:v for k,v in s.items() if k != "features"}, "raw_probabilities": dict(zip(labels, r)),
            "calibrated_probabilities": dict(zip(labels,c)), "prediction_set": prediction_set(c, labels, q)}
            for s,r,c in zip(samples[p], raw[p], calibrated[p])] for p in raw}}
    path = root / "evaluation.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    POINTER.write_text(json.dumps({"path": str(path.resolve()), "sha256": sha256(path)}, indent=2), encoding="utf-8")
    from app.services.metadata_service import refresh_metadata
    refresh_metadata()
    return {k: report[k] for k in ("evaluation_id", "model_version", "dataset_version", "sample_counts", "metrics", "calibration", "conformal")}


@lru_cache(maxsize=2)
def _load(path, version):
    import joblib
    return joblib.load(path)


def load():
    pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    if sha256(pointer["path"]) != pointer["sha256"]: raise ValueError("Experiment evaluation SHA-256 mismatch")
    report = json.loads(Path(pointer["path"]).read_text(encoding="utf-8"))
    for path, expected in ((report["model_path"], report["model_version"]), (report["dataset_path"], report["dataset_hash"])):
        if sha256(path) != expected: raise ValueError("Experiment artifact SHA-256 mismatch")
    if report["catalog_sha256"] != catalog()["sha256"]: raise ValueError("Experiment catalog changed")
    return _load(report["model_path"], report["model_version"]), report


def status():
    if not POINTER.exists(): return None
    try:
        _, report = load()
        return {"status": "evaluated", **{k:v for k,v in report.items() if k not in ("predictions", "model_path")}}
    except (ValueError, OSError, KeyError) as exc:
        return {"status": "not_available", "reason": str(exc)}


def infer(events, base, inventory=None):
    from app.synthetic_temporal import sequence_features
    from app.services.analysis_service import mapping
    from app.services.evidence_service import get_evidence_for_incident
    model, report = load()
    observed, cutoff = prefix(events, base["cutoff_timestamp"])
    if not observed: return {**base, "reason": "No evidence at cutoff"}
    if any(e.get("simulated") is not True for e in observed): raise ValueError("Synthetic model requires simulated evidence")
    if any(e["incident_id"] != base["incident_id"] for e in observed): raise ValueError("Evidence belongs to a different incident")
    ids = [e["evidence_id"] for e in observed]
    inventory = inventory if inventory is not None else {e.evidence_id for e in get_evidence_for_incident(base["incident_id"])}
    if len(ids) != len(set(ids)) or not set(ids).issubset(inventory): raise ValueError("Evidence IDs invalid for incident inventory")
    # Only input fields enter sequence_features; next_* annotations are excluded.
    observed = [{**e, "technique_id": e.get("technique_id") or mapping(e)["technique_id"]} for e in observed]
    mapped = [e for e in observed if e["technique_id"]]
    if not mapped: return {**base, "reason": "No mapped technique at cutoff"}
    features = sequence_features(observed)
    raw = model.predict_proba([features])[0]
    calibrated = scale(raw, report["calibration"]["temperature"])
    labels = model.classes_
    probabilities = dict(zip(labels, calibrated))
    ranked = sorted(probabilities, key=lambda t: (-probabilities[t], t))
    uncertainty = entropy(calibrated)
    current = mapped[-1]["technique_id"]
    return {**base, "status": "available", "prediction_mode": "synthetic_temporal_model", "synthetic_data": True,
        "real_world_validation": False, "scenario_id": observed[0].get("scenario_id"), "cutoff_timestamp": cutoff,
        "current_technique": current, "current_technique_id": current, "current_technique_name": catalog()["techniques"][current]["name"],
        "current_mapping_status": mapped[-1].get("mapping_status") or mapping(mapped[-1])["mapping_status"],
        "supporting_evidence_ids": ids, "input_evidence_ids": ids, "features": features,
        "observed_prefix": [{k:e.get(k) for k in ("evidence_id", "timestamp", "source", "host", "user", "subject", "action", "object", "technique_id", "mapping_status")} for e in observed],
        "observed_technique_prefix": [e["technique_id"] for e in mapped], "probability_kind": "CALIBRATED MODEL PROBABILITY",
        "raw_probabilities": dict(zip(labels, raw)), "calibrated_probabilities": probabilities, "probability_distribution": probabilities,
        "predicted_technique": ranked[0], "predicted_technique_id": ranked[0], "predicted_technique_name": catalog()["techniques"][ranked[0]]["name"], "probability": probabilities[ranked[0]],
        "predictions": [{"rank": rank, "predicted_technique": t, "predicted_technique_id": t, "predicted_stage": None,
                         "technique_name": catalog()["techniques"][t]["name"], "probability": probabilities[t],
                         "raw_probability": raw[labels.index(t)], "catalog_status": "active"} for rank,t in enumerate(ranked, 1)],
        "uncertainty": uncertainty, "uncertainty_value": uncertainty, "uncertainty_status": "MEASURED",
        "uncertainty_method": "Normalized predictive entropy", "uncertainty_formula": "-sum(p*log2(p))/log2(K)", "uncertainty_class_count": len(labels),
        "uncertainty_interpretation": "Dispersion of calibrated probabilities, not empirical error probability",
        "model_name": "transition_frequency", "model_version": report["model_version"], "training_dataset": report["dataset_name"],
        "training_dataset_version": VERSION, "training_dataset_sha256": report["dataset_hash"], "prediction_horizon": report["prediction_horizon"],
        "calibration": report["calibration"], "calibration_status": "MEASURED", "conformal": report["conformal"],
        "prediction_set": prediction_set(calibrated, labels, report["conformal"]["threshold"]), "coverage": report["conformal"]["measured_coverage"],
        "coverage_reason": report["conformal"]["reason"], "dataset_evaluation": report["metrics"], "evaluation_id": report["evaluation_id"],
        "model_provenance": {k:report[k] for k in ("generator_version", "seed", "dataset_version", "dataset_hash", "catalog_sha256", "split_checks", "sample_counts", "feature_definition", "evaluation_timestamp")},
        "transition_evidence": model.transition_evidence(features), "limitation": LIMITATION,
        "observed_future_outcome": None, "prediction_correctness": None,
        **outcome([], cutoff, probabilities)}


def scenarios():
    _, report = load()
    bundle = json.loads(DATASET.read_text(encoding="utf-8"))
    return [{"scenario_id": s["scenario_id"], "incident_id": s["incident_id"], "split": s["split"],
        "default_cutoff": s["cutoff_timestamp"], "cutoffs": [e["timestamp"] for e in s["events"][:-1]],
        "dataset_version": report["dataset_version"]} for s in bundle["scenarios"] if s["split"] == "test"]


def demonstrate(scenario_id, cutoff):
    from app.services.workflow_service import record
    load()
    bundle = json.loads(DATASET.read_text(encoding="utf-8"))
    s = next((s for s in bundle["scenarios"] if s["scenario_id"] == scenario_id and s["split"] == "test"), None)
    if s is None: raise ValueError("Choose a held-out synthetic test scenario")
    if cutoff not in [e["timestamp"] for e in s["events"][:-1]]: raise ValueError("Choose a listed cutoff with hidden future")
    result = infer(s["events"], {"incident_id": s["incident_id"], "cutoff_timestamp": cutoff}, {e["evidence_id"] for e in s["events"]})
    result.update(ground_truth={"status": "HIDDEN", "event": None}, evaluation={"status": "PENDING_REVEAL", "correct": None})
    return record(s["incident_id"], "future_prediction", {"result": result})["result"]


def reveal(scenario_id, prediction_id):
    from app.services.workflow_service import history, record, verify_chain
    load()
    bundle = json.loads(DATASET.read_text(encoding="utf-8"))
    s = next((s for s in bundle["scenarios"] if s["scenario_id"] == scenario_id and s["split"] == "test"), None)
    if s is None: raise ValueError("Unknown test scenario")
    if not verify_chain(s["incident_id"])["verified"]: raise ValueError("Audit chain mismatch")
    saved = next((e for e in history(s["incident_id"]) if e["id"] == prediction_id and e["kind"] == "future_prediction"), None)
    if saved is None: raise ValueError("Predict before revealing the future")
    result = saved["result"]
    if result["training_dataset_sha256"] != sha256(DATASET): raise ValueError("Dataset changed since prediction")
    result = {**result, **outcome(s["events"], result["cutoff_timestamp"], result["probability_distribution"])}
    result.update(observed_future_outcome=result["ground_truth"]["event"], prediction_correctness=result["evaluation"]["correct"])
    audit = record(s["incident_id"], "prediction_evaluation", {"prediction_id": prediction_id, "result": result,
                   "host_action_executed": False, "simulated": True})
    return {**result, "evaluation_audit_id": audit["id"]}


def demonstration_report(scenario_id, prediction_id):
    """Export only what was already predicted/revealed; never reveal by exporting."""
    from app.services.workflow_service import history, record, verify_chain
    incident_id = "SYN2-INC-" + scenario_id.removeprefix("SYN2-")
    entries = history(incident_id)
    saved = next((e for e in entries if e["id"] == prediction_id and e["kind"] == "future_prediction"
                  and e["result"]["scenario_id"] == scenario_id), None)
    if saved is None: raise ValueError("Prediction not found for scenario")
    if not verify_chain(incident_id)["verified"]: raise ValueError("Audit chain mismatch")
    evaluated = next((e for e in entries if e["kind"] == "prediction_evaluation" and e["prediction_id"] == prediction_id), None)
    result = evaluated["result"] if evaluated else saved["result"]
    exported = record(incident_id, "report_generation", {"prediction_id": prediction_id, "simulated": True, "host_action_executed": False})
    material = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    import hashlib
    return {"generated_at": exported["created_at"], "incident_id": incident_id, "scenario_id": scenario_id,
        "future_attack_prediction": result, "evidence": result["observed_prefix"],
        "prediction_payload_sha256": hashlib.sha256(material.encode()).hexdigest(),
        "hash_scope": "Canonical prediction JSON; does not authenticate original sensors",
        "audit": [e for e in history(incident_id) if e["id"] == prediction_id or e.get("prediction_id") == prediction_id],
        "chain_of_custody": verify_chain(incident_id),
        "preservation_actions": [], "prevention_actions": [], "host_action_executed": False,
        "limitations": [LIMITATION, "This demonstration records prediction and reveal only; no host evidence acquisition or prevention response occurred."]}
