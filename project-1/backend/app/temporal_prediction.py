"""Prefix-only next observed label baseline. No supplied custom CSV is an event sequence."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math

from app.datasets import DATA, sha256
from app.services.attack_service import catalog

FEATURE_VERSION = "future_prediction_v1"
SEED = 42
PARAMETERS = dict(n_estimators=80, max_depth=12, min_samples_leaf=2, random_state=SEED, n_jobs=1)
TASKS = {"technique": "technique_id", "stage": "attack_stage"}
HORIZON = "Next independently labelled observed event strictly after the cutoff; no fixed time horizon"
REASON = ("Insufficient observed sequential ATT&CK-labelled training/evaluation data. "
          "Dataset 11 has synthetic next-stage labels and no event timestamps; datasets 10/12/13 "
          "are response alternatives, unordered quality rows and benchmark descriptors. OpTC ground-truth sequences are not supplied.")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def stamp(value, naive=False):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid or missing timestamp: {value}") from None
    if result.tzinfo is None and not naive:
        raise ValueError("Timestamp requires timezone; real sequences must not assume UTC")
    return result if result.tzinfo is None else result.astimezone(timezone.utc)


def prefix(events, cutoff=None, upto=None):
    """Fixture-naive clocks are retained, never silently converted to UTC."""
    if cutoff is not None and upto is not None:
        raise ValueError("Choose cutoff_timestamp or legacy upto, not both")
    if not events:
        if cutoff is not None: stamp(cutoff, naive=True)
        return [], cutoff
    naive = all(e.get("simulated") is True for e in events)
    timed = [(stamp(e.get("timestamp"), naive), e) for e in events]
    awareness = {t.tzinfo is not None for t, _ in timed}
    if len(awareness) > 1:
        raise ValueError("Mixed timezone-aware and naive event timestamps")
    timed.sort(key=lambda pair: (pair[0], pair[1]["evidence_id"]))
    if cutoff is None:
        if upto is not None:
            # All records at the boundary timestamp are visible together.
            timed = timed if upto >= len(timed) else [] if upto == 0 else [p for p in timed if p[0] <= timed[upto - 1][0]]
        cutoff = timed[-1][0].isoformat() if timed else None
    boundary = stamp(cutoff, naive) if cutoff is not None else None
    if boundary is not None and awareness and (boundary.tzinfo is not None) not in awareness:
        raise ValueError("Cutoff timezone must match the incident clock; the demo uses timezone-unspecified timestamps")
    selected = []
    for time, event in timed:
        if boundary is None or time > boundary:
            continue
        seen = stamp(event.get("observed_at", event["timestamp"]), naive)
        if (seen.tzinfo is None) != (boundary.tzinfo is None):
            raise ValueError("Observation timestamp clock does not match cutoff")
        if seen <= boundary:
            selected.append(event)
    return selected, cutoff


def feature_values(events, cutoff):
    """Explicit whitelist. No IDs, targets, final incident state or response outcomes."""
    events, cutoff = prefix(events, cutoff)
    if not events:
        raise ValueError("No evidence at or before cutoff")
    naive = all(e.get("simulated") is True for e in events)
    end = stamp(cutoff, naive)
    values = {"event_count": len(events), "distinct_hosts": len({e.get("host") for e in events if e.get("host")}),
              "distinct_entities": len({e[k] for e in events for k in ("subject", "object") if e.get(k)}),
              "elapsed_seconds": (end - stamp(events[0]["timestamp"], naive)).total_seconds(),
              "since_last_event_seconds": (end - stamp(events[-1]["timestamp"], naive)).total_seconds()}
    techniques, stages = [], []
    for event in events:
        for key in ("source", "action", "subject_type", "object_type"):
            if event.get(key):
                field = f"count:{key}:{event[key]}"
                values[field] = values.get(field, 0) + 1
        # Training labels annotated retrospectively must not appear in prefix features.
        known = event.get("label_known_at")
        if known and stamp(known, naive) <= end:
            if event.get("technique_id"):
                techniques.append(event["technique_id"])
            if event.get("attack_stage"):
                stages.append(event["attack_stage"])
    for name, sequence in (("technique", techniques), ("stage", stages)):
        if sequence:
            values[f"current_{name}"] = sequence[-1]
            if len(sequence) > 1:
                values[f"previous_{name}"] = sequence[-2]
            for value, count in Counter(sequence).items():
                values[f"count:{name}:{value}"] = count
    return values


def load_sequences(path):
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    meta, events = bundle["metadata"], bundle["events"]
    for key in ("dataset_name", "version", "source", "ground_truth_reference", "domain", "data_kind"):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise ValueError(f"Dataset metadata missing {key}")
    if meta["data_kind"] not in ("observed", "synthetic"):
        raise ValueError("data_kind must be observed or synthetic")
    if not events:
        raise ValueError("No observed events supplied")
    ids, signatures = set(), set()
    incident_groups = {}
    techniques = catalog()["techniques"]
    for event in events:
        for key in ("evidence_id", "incident_id", "scenario_id", "collection_id", "timestamp", "observed_at", "source", "host", "subject", "object", "action"):
            if not isinstance(event.get(key), str) or not event[key].strip():
                raise ValueError(f"Malformed event: missing {key}")
        if event.get("simulated") is not (meta["data_kind"] == "synthetic"):
            raise ValueError("Every event's simulated flag must match data_kind")
        if event["evidence_id"] in ids:
            raise ValueError("Duplicate event ID")
        ids.add(event["evidence_id"])
        time, seen = stamp(event["timestamp"]), stamp(event["observed_at"])
        if seen < time:
            raise ValueError("observed_at precedes event timestamp")
        group = (event["scenario_id"], event["collection_id"])
        if event["incident_id"] in incident_groups and incident_groups[event["incident_id"]] != group:
            raise ValueError("Incident spans inconsistent scenario/collection identifiers")
        incident_groups[event["incident_id"]] = group
        if event.get("technique_id") and event["technique_id"] not in techniques:
            raise ValueError(f"Invalid/inactive ATT&CK ID: {event['technique_id']}")
        valid_stages = {t.replace("-", " ").title().replace(" And ", " and ") for item in techniques.values() for t in item["tactics"]}
        if event.get("attack_stage") and event["attack_stage"] not in valid_stages:
            raise ValueError(f"Invalid ATT&CK stage: {event['attack_stage']}")
        if event.get("technique_id") or event.get("attack_stage"):
            if event.get("label_basis") != "independent_ground_truth" or not event.get("label_reference"):
                raise ValueError("Labels require independent_ground_truth and a source reference; behavior rules are not ground truth")
            if stamp(event.get("label_known_at")) < time:
                raise ValueError("label_known_at precedes event timestamp")
        signature = digest({k: event.get(k) for k in ("timestamp", "source", "host", "subject", "action", "object")})
        if signature in signatures:
            raise ValueError("Duplicate observation content across dataset")
        signatures.add(signature)
        forbidden = {k for k in event if k.startswith(("predicted_", "next_", "future_", "target_", "final_", "survival_"))}
        if forbidden:
            raise ValueError(f"Feature-label leakage fields in event: {sorted(forbidden)}")
    return meta, events


def samples(events, task):
    key = TASKS[task]
    groups = defaultdict(list)
    for event in events:
        groups[event["incident_id"]].append(event)
    result = []
    for incident, sequence in sorted(groups.items()):
        sequence.sort(key=lambda e: (stamp(e["timestamp"]), e["evidence_id"]))
        cutoffs = sorted({stamp(e["observed_at"]) for e in sequence})
        for boundary in cutoffs:
            cutoff = boundary.isoformat()
            inputs, _ = prefix(sequence, cutoff)
            future = [e for e in sequence if stamp(e["timestamp"]) > boundary and e.get(key)]
            if not inputs or not future:
                continue
            first_time = stamp(future[0]["timestamp"])
            targets = [e for e in future if stamp(e["timestamp"]) == first_time]
            if len({e[key] for e in targets}) != 1:
                raise ValueError("Ambiguous simultaneous future labels; no arbitrary next-event ordering")
            target = targets[0]
            result.append({"incident_id": incident, "scenario_id": sequence[0]["scenario_id"],
                "collection_id": sequence[0]["collection_id"], "cutoff_timestamp": cutoff,
                "supporting_evidence_ids": [e["evidence_id"] for e in inputs],
                "features": feature_values(inputs, cutoff), "target": target[key],
                "target_event_id": target["evidence_id"], "target_timestamp": target["timestamp"],
                "observed_sequence": [e.get(key) for e in inputs if e.get(key) and stamp(e["label_known_at"]) <= boundary]})
    return result


def split_samples(records):
    """Connected incident/scenario/collection groups cannot straddle a partition."""
    from sklearn.model_selection import GroupShuffleSplit
    parent = list(range(len(records)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    for i, row in enumerate(records):
        for key in ("incident_id", "scenario_id", "collection_id"):
            label = (key, row[key])
            if label in seen:
                parent[root(i)] = root(seen[label])
            seen[label] = i
    groups = [root(i) for i in range(len(records))]
    if len(set(groups)) < 5:
        raise ValueError("Need at least five independent incident/scenario/collection groups for train/validation/holdout")
    development, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=SEED).split(records, groups=groups))
    a, b = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=SEED + 1).split(development, groups=[groups[i] for i in development]))
    partitions = {"training": development[a].tolist(), "validation": development[b].tolist(), "holdout": test.tolist()}
    temporal_errors = sum(stamp(row["target_timestamp"]) <= stamp(row["cutoff_timestamp"]) or row["target_event_id"] in row["supporting_evidence_ids"] for row in records)
    forbidden = sorted({k for row in records for k in row["features"] if k.startswith(("next_", "future_", "target_", "predicted_", "final_", "survival_"))})
    if temporal_errors or forbidden:
        raise ValueError("Temporal or feature-label leakage in prediction samples")
    checks = {"split_strategy": "Connected incident/scenario/collection groups; GroupShuffleSplit 60/20/20; fixed seeds 42/43",
              "temporal_leakage": temporal_errors, "feature_target_overlap": forbidden, "overlap": {}, "source_overlap": {}}
    for left, right in (("training", "validation"), ("training", "holdout"), ("validation", "holdout")):
        pair = left + "/" + right
        checks["overlap"][pair] = {key: sorted({records[i][key] for i in partitions[left]} & {records[i][key] for i in partitions[right]}) for key in ("incident_id", "scenario_id", "collection_id")}
        # Identical feature/label samples across partitions would permit memorization.
        fingerprints = {side: {digest({"x": records[i]["features"], "y": records[i]["target"]}) for i in partitions[side]} for side in (left, right)}
        overlap = len(fingerprints[left] & fingerprints[right])
        checks["overlap"][pair]["duplicate_feature_target_rows"] = overlap
        if overlap:
            raise ValueError(f"Duplicate feature/target samples across {pair}; obtain independent sequences")
    for name, indices in partitions.items():
        counts = Counter(records[i]["target"] for i in indices)
        if len(counts) < 2 or min(counts.values()) < 2:
            raise ValueError(f"Insufficient labelled {name} samples: require two classes with at least two examples each")
    training_labels = {records[i]["target"] for i in partitions["training"]}
    checks["unsupported_labels"] = {part: sorted({records[i]["target"] for i in ids} - training_labels) for part, ids in partitions.items()}
    checks["all_checks_passed"] = not any(checks["unsupported_labels"].values())
    if not checks["all_checks_passed"]:
        raise ValueError(f"Unseen validation/holdout labels: {checks['unsupported_labels']}")
    return partitions, checks


def entropy(probabilities):
    values = [float(v) for v in probabilities]
    if not values or not all(math.isfinite(v) and 0 <= v <= 1 for v in values) or not math.isclose(sum(values), 1, abs_tol=1e-6):
        raise ValueError("Invalid prediction probabilities or probability sum")
    return -sum(p * math.log(p) for p in values if p > 0) / math.log(len(values)) if len(values) > 1 else 0.0


def evaluate(actual, probabilities, labels):
    from app.training import classification_metrics
    ordered = [sorted(zip(labels, p), key=lambda pair: (-pair[1], pair[0])) for p in probabilities]
    predicted = [p[0][0] for p in ordered]
    result = classification_metrics(actual, predicted, sorted(set(actual) | set(labels)))
    for k in (1, 3, 5):
        result[f"top_{k}_accuracy"] = sum(y in [c for c, _ in p[:k]] for y, p in zip(actual, ordered)) / len(actual) if k <= len(labels) else None
    result["top_k_reason"] = "Top-k is NOT MEASURED when fewer than k trained classes exist"
    result["mean_reciprocal_rank"] = sum(next((1 / (i + 1) for i, (c, _) in enumerate(p) if c == y), 0) for y, p in zip(actual, ordered)) / len(actual)
    # Unseen held-out classes have model probability zero and contribute 1.
    result["multiclass_brier_score"] = sum(sum((float(p) - int(c == y)) ** 2 for c, p in zip(labels, row)) + int(y not in labels) for y, row in zip(actual, probabilities)) / len(actual)
    bins = []
    for i in range(10):
        ids = [j for j, p in enumerate(ordered) if i / 10 <= p[0][1] <= (i + 1) / 10 and (i == 0 or p[0][1] > i / 10)]
        bins.append({"lower": i / 10, "upper": (i + 1) / 10, "count": len(ids),
                     "mean_confidence": sum(ordered[j][0][1] for j in ids) / len(ids) if ids else None,
                     "accuracy": sum(predicted[j] == actual[j] for j in ids) / len(ids) if ids else None})
    result["expected_calibration_error"] = sum(b["count"] / len(actual) * abs(b["mean_confidence"] - b["accuracy"]) for b in bins if b["count"])
    result["reliability_bins"] = bins
    for p in probabilities:
        entropy(p)
    return result


def train(path, output, task="technique", allow_synthetic=False):
    import joblib
    import sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.pipeline import make_pipeline
    meta, events = load_sequences(path)
    if meta["data_kind"] == "synthetic" and not allow_synthetic:
        raise ValueError("Synthetic sequences require --allow-synthetic and cannot activate genuine prediction")
    records = samples(events, task)
    if not records:
        raise ValueError("No genuine strictly later observed labels available for the selected task")
    partitions, checks = split_samples(records)
    model = make_pipeline(DictVectorizer(sparse=False), RandomForestClassifier(**PARAMETERS))
    train_ids = partitions["training"]
    model.fit([records[i]["features"] for i in train_ids], [records[i]["target"] for i in train_ids])
    labels = model[-1].classes_.tolist()
    majority = Counter(records[i]["target"] for i in train_ids).most_common(1)[0][0]
    report = {"status": "evaluated", "prediction_mode": "observed_dataset_evaluation" if meta["data_kind"] == "observed" else "synthetic_temporal_test",
              "task": task, "target": "next_observed_" + task, "prediction_horizon": HORIZON,
              "model_name": "RandomForest temporal prefix baseline", "algorithm": "RandomForestClassifier", "sklearn_version": sklearn.__version__,
              "dataset": meta, "dataset_sha256": sha256(path), "dataset_path": str(Path(path).resolve()),
              "feature_version": FEATURE_VERSION, "features": model[0].get_feature_names_out().tolist(),
              "random_seed": SEED, "hyperparameters": PARAMETERS, "training_timestamp": now(),
              "partitions": partitions, "split_sizes": {k: len(v) for k, v in partitions.items()}, "leakage_checks": checks,
              "partition_groups": {part: {key: sorted({records[i][key] for i in ids}) for key in ("incident_id", "scenario_id", "collection_id")} for part, ids in partitions.items()},
              "calibration_status": "Diagnostics measured; probabilities NOT calibrated", "calibration_method": None,
              "uncertainty_method": "normalized predictive entropy; not error probability", "coverage": None,
              "coverage_reason": "NOT MEASURED — no conformal prediction sets evaluated", "evaluation": {}, "errors": [],
              "label_provenance_warning": "Ground-truth provenance is supplied by the dataset owner and must be reviewed; schema validation does not establish authenticity."}
    source_sets = {part: {e["source"] for e in events if e["evidence_id"] in {eid for i in ids for eid in records[i]["supporting_evidence_ids"]}} for part, ids in partitions.items()}
    checks["source_overlap"] = {f"{a}/{b}": sorted(source_sets[a] & source_sets[b]) for a, b in (("training", "validation"), ("training", "holdout"), ("validation", "holdout"))}
    checks["source_overlap_reason"] = "Sensor types may be shared; collection identities are held out. Source/domain generalization is not claimed."
    for part in ("validation", "holdout"):
        selected = [records[i] for i in partitions[part]]
        probabilities = model.predict_proba([r["features"] for r in selected]).tolist()
        actual = [r["target"] for r in selected]
        report["evaluation"][part] = {"model": evaluate(actual, probabilities, labels),
            "majority_baseline": evaluate(actual, [[float(c == majority) for c in labels]] * len(actual), labels), "evaluated_at": now()}
        for row, p in zip(selected, probabilities):
            best = max(range(len(p)), key=p.__getitem__)
            report["errors"].append({**row, "partition": part, "predicted": labels[best], "probability": p[best],
                "uncertainty": entropy(p), "correct": labels[best] == row["target"], "low_confidence": p[best] < .5, "high_uncertainty": entropy(p) > .75})
    report["explanation"] = {"method": "Global RandomForest impurity importance; not a local causal explanation",
        "feature_importance": dict(zip(report["features"], model[-1].feature_importances_.tolist()))}
    report["attack_catalog_sha256"] = catalog()["sha256"]
    report["attack_catalog_version"] = catalog()["version"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    artifact_path = output / f"future_{task}.joblib"
    # A synthetic/test run must never replace an operational artifact.
    if meta["data_kind"] == "synthetic" and output.resolve() == (DATA / "models").resolve():
        raise ValueError("Synthetic pipeline tests must write to a separate test directory")
    joblib.dump({"model": model, "metadata": report}, artifact_path)
    report["model_version"] = sha256(artifact_path)
    (output / f"future_{task}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Reviewed JSON event bundle; see docs/future-prediction.md")
    parser.add_argument("--output", type=Path, default=DATA / "models")
    parser.add_argument("--task", choices=TASKS, default="technique")
    parser.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args()
    report = train(args.path, args.output, args.task, args.allow_synthetic)
    print(json.dumps({k: report[k] for k in ("status", "prediction_mode", "model_version", "split_sizes")}, indent=2))


if __name__ == "__main__":
    main()
