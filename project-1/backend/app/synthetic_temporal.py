"""Supplied synthetic temporal benchmark, using the existing dataset/model store.

This research model is only applied to simulated incidents. It never qualifies
as observed-data validation and never executes prevention actions.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import csv
import hashlib
import io
import json
import zipfile

from app.datasets import DATA, sha256
from app.temporal_prediction import evaluate, now, prefix, stamp, PARAMETERS, digest, entropy
from app.services.attack_service import catalog
from app.attack_normalization import normalize, VERSION as NORMALIZATION_VERSION

DIRECTORY = DATA / "custom" / "synthetic_temporal"
MODEL = DATA / "models" / "synthetic_temporal.joblib"
FEATURE_VERSION = "synthetic-temporal-prefix-v2-normalized-attack"
HORIZON = "Next chronological labelled event after cutoff; no fixed time horizon"
FILES = {"temporal_evidence_events.csv", "next_technique_samples.csv", "scenario_summary.csv", "transition_statistics.csv", "README.md"}
LIMITATION = ("Synthetic-trained research model applied to simulated incident. "
              "NOT REAL-WORLD VALIDATION. Scenario separation does not establish template or real-world generalization. "
              "Probabilities are uncalibrated model outputs; evidence mappings may be incomplete or uncertain.")


def csv_rows(content):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def validate(contents):
    """Verify bytes and every supplied prefix/target against chronological events."""
    manifest = json.loads(contents["dataset_manifest.json"])
    if manifest.get("synthetic") is not True or manifest.get("real_world_validation") is not False:
        raise ValueError("This importer requires an explicitly synthetic dataset without real-world validation")
    for key in ("dataset_id", "dataset_name", "version"):
        if not manifest.get(key): raise ValueError(f"Manifest missing {key}")
    hashes = {}
    for name in sorted(FILES):
        content = contents[name]
        hashes[name] = hashlib.sha256(content).hexdigest()
        expected = manifest["files"][name]
        if hashes[name] != expected["sha256"] or len(content) != expected["bytes"]:
            raise ValueError(f"SHA-256 or size mismatch: {name}")
    events = csv_rows(contents["temporal_evidence_events.csv"])
    records = csv_rows(contents["next_technique_samples.csv"])
    summaries = csv_rows(contents["scenario_summary.csv"])
    groups, event_ids, incident_splits = defaultdict(list), set(), {}
    for event in events:
        if event["event_id"] in event_ids: raise ValueError("Duplicate event ID")
        event_ids.add(event["event_id"])
        if event["split"] not in ("train", "validation", "test") or event["synthetic"].lower() != "true":
            raise ValueError("Invalid split or synthetic flag")
        stamp(event["timestamp"])
        key = event["incident_id"]
        if key in incident_splits and incident_splits[key] != event["split"]:
            raise ValueError("Incident appears in multiple splits")
        incident_splits[key] = event["split"]
        groups[event["scenario_id"]].append(event)
    partitions = {key: set() for key in ("train", "validation", "test")}
    for scenario, sequence in groups.items():
        sequence.sort(key=lambda e: stamp(e["timestamp"]))
        if len({e["split"] for e in sequence}) != 1: raise ValueError("Scenario appears in multiple splits")
        if len({e["incident_id"] for e in sequence}) != 1: raise ValueError("Scenario has inconsistent incident IDs")
        if len({stamp(e["timestamp"]) for e in sequence}) != len(sequence):
            raise ValueError("Ambiguous simultaneous events in synthetic scenario")
        partitions[sequence[0]["split"]].add(scenario)
    seen, boundaries = set(), set()
    for row in records:
        if row["sample_id"] in seen: raise ValueError("Duplicate sample ID")
        seen.add(row["sample_id"])
        sequence = groups[row["scenario_id"]]
        cutoff = stamp(row["cutoff_timestamp"])
        observed = [e for e in sequence if stamp(e["timestamp"]) <= cutoff]
        future = [e for e in sequence if stamp(e["timestamp"]) > cutoff]
        if not observed or not future: raise ValueError("Sample has no prefix or strictly later target")
        if cutoff != stamp(observed[-1]["timestamp"]): raise ValueError("Cutoff is not a supplied event boundary")
        boundary = (row["scenario_id"], cutoff)
        if boundary in boundaries: raise ValueError("Duplicate scenario cutoff")
        boundaries.add(boundary)
        target = future[0]
        checks = {
            "incident_id": observed[0]["incident_id"], "split": observed[0]["split"],
            "prefix_length": str(len(observed)), "current_technique_id": observed[-1]["technique_id"],
            "current_technique_name": observed[-1]["technique_name"],
            "prefix_technique_ids": "|".join(e["technique_id"] for e in observed),
            "prefix_tactics": "|".join(e["tactic"] for e in observed),
            "prefix_event_ids": "|".join(e["event_id"] for e in observed),
            "supporting_evidence_ids": "|".join(e["event_id"] for e in observed),
            "target_event_id": target["event_id"], "target_next_technique_id": target["technique_id"],
            "target_next_technique_name": target["technique_name"], "target_next_tactic": target["tactic"],
        }
        for key, expected in checks.items():
            if row[key] != expected: raise ValueError(f"Sample {row['sample_id']} inconsistent {key}")
        if row["synthetic"].lower() != "true": raise ValueError("Non-synthetic sample in synthetic benchmark")
    if len(records) != sum(len(g) - 1 for g in groups.values()): raise ValueError("Missing next-event prefix samples")
    if len(summaries) != len(groups) or {r["scenario_id"] for r in summaries} != set(groups):
        raise ValueError("Scenario summary mismatch")
    for row in summaries:
        sequence = groups[row["scenario_id"]]
        if int(row["event_count"]) != len(sequence) or row["split"] != sequence[0]["split"] or row["sequence_techniques"] != "|".join(e["technique_id"] for e in sequence):
            raise ValueError("Scenario summary disagrees with temporal events")
    generation = manifest["generation"]
    for key, actual in (("scenario_count", len(groups)), ("event_count", len(events)), ("next_technique_sample_count", len(records))):
        if generation[key] != actual: raise ValueError(f"Manifest {key} mismatch")
    for part, ids in partitions.items():
        if manifest["splits"][part + "_scenarios"] != len(ids): raise ValueError("Manifest split count mismatch")
    overlaps = {f"{a}/{b}": sorted(partitions[a] & partitions[b]) for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    if any(overlaps.values()): raise ValueError("Scenario overlap between splits")
    names = {}
    for e in events:
        if e["technique_id"] in names and names[e["technique_id"]] != e["technique_name"]: raise ValueError("Inconsistent technique names")
        names[e["technique_id"]] = e["technique_name"]
    unsupported = sorted(set(names) - set(catalog()["techniques"]))
    target_sets = {p: {r["target_next_technique_id"] for r in records if r["split"] == p} for p in partitions}
    metadata = {**manifest, "seed": generation["seed"], "scenario_count": len(groups), "event_count": len(events), "sample_count": len(records),
        "scenario_counts": {p: len(ids) for p, ids in partitions.items()}, "sample_counts": dict(Counter(r["split"] for r in records)),
        "verified_sha256": hashes, "manifest_sha256": hashlib.sha256(contents["dataset_manifest.json"]).hexdigest(),
        "hash_verification": "VERIFIED", "scenario_overlap": overlaps, "technique_names": names,
        "target_classes_absent_from_training": {p: sorted(ids - target_sets["train"]) for p, ids in target_sets.items()},
        "template_counts": {p: dict(Counter(r["template_id"] for r in summaries if r["split"] == p)) for p in partitions},
        "catalog_version": catalog()["version"], "labels_absent_from_active_catalog": unsupported,
        "label_policy": "Original supplied IDs and names retained, including legacy labels; no target relabelling. Names are dataset labels.",
        "label_availability_assumption": "Synthetic technique annotations are available at event timestamp; not measured sensor detection latency."}
    return metadata, groups, records


def load_dataset(directory=None):
    directory = Path(directory or DIRECTORY)
    return validate({name: (directory / name).read_bytes() for name in FILES | {"dataset_manifest.json"}})


def import_archive(path):
    with zipfile.ZipFile(path) as archive:
        required = FILES | {"dataset_manifest.json"}
        if set(archive.namelist()) != required or len(archive.namelist()) != len(required):
            raise ValueError("Archive must contain exactly the six expected root files")
        contents = {name: archive.read(name) for name in required}
    metadata, _, _ = validate(contents)  # Nothing is installed before verification.
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items(): (DIRECTORY / name).write_bytes(content)
    metadata.update(archive_filename=Path(path).name, archive_sha256=sha256(path), imported_at=now())
    (DIRECTORY / "import_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    registry_path = DATA / "manifest.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {"datasets": []}
    registry["datasets"] = [r for r in registry.get("datasets", []) if r["id"] != metadata["dataset_id"]]
    registry["datasets"].append({**metadata, "id": metadata["dataset_id"], "dataset_name": metadata["dataset_name"], "version": metadata["version"], "modules": ["Future ATT&CK Technique Prediction"], "file_hash": metadata["manifest_sha256"],
        "filename": "synthetic_temporal/dataset_manifest.json", "sha256": metadata["manifest_sha256"], "rows": metadata["sample_count"],
        "synthetic": True, "real_world_validation": False, "usage": "Synthetic Dataset — NOT REAL-WORLD VALIDATION", "import_timestamp": metadata["imported_at"]})
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return metadata


def sequence_features(events):
    """Shared train/inference whitelist. IDs, targets, split and template are excluded."""
    sequence = [e["technique_id"] for e in events if e.get("technique_id")]
    values = {"event_count": len(events), "mapped_count": len(sequence)}
    for n in (1, 2, 3):
        values[f"technique_suffix_{n}"] = "|".join(sequence[-n:]) if sequence else "UNMAPPED"
    for technique, count in Counter(sequence).items(): values["technique_count:" + technique] = count
    for a, b in zip(sequence, sequence[1:]):
        key = "transition:" + a + ">" + b
        values[key] = values.get(key, 0) + 1
    if events:
        times = [stamp(e["timestamp"], naive=True) for e in events]
        values["elapsed_seconds"] = (times[-1] - times[0]).total_seconds()
        values["last_interval_seconds"] = (times[-1] - times[-2]).total_seconds() if len(times) > 1 else 0
        for source, count in Counter(e["source"] for e in events).items(): values["source_count:" + source] = count
    return values


class TransitionFrequency:
    """Maximum-likelihood suffix counts, backing off from length 3 to 1 then prior."""
    def fit(self, inputs, targets, sample_ids=None):
        self.classes_ = sorted(set(targets))
        self.counts = {n: defaultdict(Counter) for n in (1, 2, 3)}
        self.prior = Counter(targets)
        self.sample_ids = list(sample_ids or [])
        self.support = {n: defaultdict(list) for n in self.counts}
        for index, (row, target) in enumerate(zip(inputs, targets)):
            for n in self.counts:
                self.counts[n][row[f"technique_suffix_{n}"]][target] += 1
                if self.sample_ids: self.support[n][row[f"technique_suffix_{n}"]].append(self.sample_ids[index])
        return self

    def transition_evidence(self, row):
        for n in (3, 2, 1):
            key = row[f"technique_suffix_{n}"]
            if key in self.counts[n]:
                counts = self.counts[n][key]
                return {"basis": "training suffix transition counts", "suffix_feature_length": n,
                    "matched_technique_suffix": key.split("|"), "target_counts": dict(sorted(counts.items())),
                    "total_training_samples": sum(counts.values()), "training_sample_ids": self.support[n][key],
                    "formula": "Model output probability = target count / total matching training samples"}
        return {"basis": "training prior; no observed suffix matched", "suffix_feature_length": 0,
            "matched_technique_suffix": [], "target_counts": dict(sorted(self.prior.items())),
            "total_training_samples": sum(self.prior.values()), "training_sample_ids": self.sample_ids,
            "formula": "Model output probability = training class count / total training samples"}

    def predict_proba(self, inputs):
        result = []
        for row in inputs:
            evidence = self.transition_evidence(row)
            counts, total = evidence["target_counts"], evidence["total_training_samples"]
            result.append([counts.get(c, 0) / total for c in self.classes_])
        return result


def train(directory=None, output=None):
    import joblib
    import sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.pipeline import make_pipeline
    directory, output = Path(directory or DIRECTORY), Path(output or MODEL)
    metadata, groups, records = load_dataset(directory)
    metadata, groups, records = normalize(metadata, groups, records)
    x = [sequence_features([e for e in groups[r["scenario_id"]] if stamp(e["timestamp"]) <= stamp(r["cutoff_timestamp"])]) for r in records]
    partitions = {p: [i for i, r in enumerate(records) if r["split"] == p] for p in ("train", "validation", "test")}
    inputs = [x[i] for i in partitions["train"]]
    targets = [records[i]["target_next_technique_id"] for i in partitions["train"]]
    candidates = {"transition_frequency": TransitionFrequency().fit(inputs, targets, [records[i]["sample_id"] for i in partitions["train"]]),
        "random_forest": make_pipeline(DictVectorizer(sparse=False), RandomForestClassifier(**PARAMETERS)).fit(inputs, targets)}
    labels = sorted(set(targets))
    majority = Counter(targets).most_common(1)[0][0]
    evaluations, probabilities = {}, {}
    for name, model in candidates.items():
        model_labels = list(model.classes_)
        if model_labels != labels: raise ValueError("Inconsistent model class order")
        evaluations[name], probabilities[name] = {}, {}
        for part, indices in partitions.items():
            actual = [records[i]["target_next_technique_id"] for i in indices]
            p = model.predict_proba([x[i] for i in indices])
            p = p.tolist() if hasattr(p, "tolist") else p
            probabilities[name][part] = p
            evaluations[name][part] = {"model": evaluate(actual, p, labels),
                "majority_baseline": evaluate(actual, [[float(c == majority) for c in labels]] * len(actual), labels)}
    # Fixed selection rule uses validation only; test outcomes do not select or fit the model.
    selected = max(candidates, key=lambda name: (evaluations[name]["validation"]["model"]["macro_f1"], name == "transition_frequency"))
    fingerprints = {p: {digest(x[i]) for i in ids} for p, ids in partitions.items()}
    metadata.update(dataset_path=str(directory.resolve()))
    imported = directory / "import_metadata.json"
    if imported.exists():
        previous = json.loads(imported.read_text(encoding="utf-8"))
        if previous["manifest_sha256"] == metadata["manifest_sha256"]:
            metadata.update({k: previous[k] for k in ("archive_filename", "archive_sha256", "imported_at")})
    report = {"status": "evaluated", "prediction_mode": "synthetic_temporal_model", "synthetic_data": True, "real_world_validation": False,
        "dataset": metadata, "feature_version": FEATURE_VERSION, "model_name": selected, "training_timestamp": now(),
        "algorithm": "Suffix-conditioned transition frequency with backoff" if selected == "transition_frequency" else "RandomForestClassifier",
        "training_dataset": metadata["dataset_name"], "training_dataset_version": metadata["version"],
        "training_scenarios": metadata["scenario_counts"]["train"], "validation_scenarios": metadata["scenario_counts"]["validation"], "test_scenarios": metadata["scenario_counts"]["test"],
        "random_seed": 42, "random_seed_usage": "Random Forest comparison uses seed 42; transition counts are deterministic without randomness",
        "feature_definition": {"available_features": "Last 1/2/3 mapped techniques, technique and transition counts, event/mapped counts, elapsed time, last interval, source counts",
            "selected_model_features": ["technique_suffix_3", "technique_suffix_2", "technique_suffix_1"] if selected == "transition_frequency" else candidates[selected][0].get_feature_names_out().tolist(),
            "excluded": "Targets, future events, incident/scenario/template IDs, sample IDs and split"},
        "target_definition": "Supplied target_next_technique_id normalized through pinned ATT&CK revoked-by relationships; next chronological labelled event after cutoff",
        "selection_rule": "Highest validation macro-F1; ties favor transition frequency. Test never used for fitting or selection.",
        "training_configuration": {"random_seed": 42, "random_forest": PARAMETERS, "transition_frequency": "Suffix lengths 3,2,1 then training prior; unsmoothed frequencies", "sklearn_version": sklearn.__version__},
        "split_sizes": metadata["sample_counts"], "evaluation": evaluations[selected], "candidate_evaluations": evaluations,
        "scenario_groups": {p: sorted({records[i]["scenario_id"] for i in ids}) for p, ids in partitions.items()},
        "leakage_checks": {"scenario_overlap": metadata["scenario_overlap"], "all_prefix_targets_verified": True,
            "training_only_fit": True, "provided_split_preserved": True,
            "duplicate_feature_patterns": {f"{a}/{b}": len(fingerprints[a] & fingerprints[b]) for a,b in (("train","validation"),("train","test"),("validation","test"))}},
        "uncertainty_status": "NOT MEASURED", "calibration_status": "NOT MEASURED — no probability calibration fitted; held-out Brier/ECE diagnostics reported separately",
        "coverage": None, "prediction_horizon": HORIZON, "limitation": LIMITATION,
        "explanation": "Feature-level explanation unavailable for this baseline model." if selected == "transition_frequency" else {
            "method": "Global RandomForest impurity importance; not a local causal explanation",
            "feature_importance": dict(zip(candidates[selected][0].get_feature_names_out(), candidates[selected][-1].feature_importances_.tolist()))}}
    report["test_examples"] = []
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized_path = output.with_name(output.stem + "_normalized.json")
    normalized_path.write_text(json.dumps({"normalization": metadata["normalization"], "source_manifest_sha256": metadata["manifest_sha256"],
        "events": [e for scenario in sorted(groups) for e in groups[scenario]], "samples": records}, indent=2), encoding="utf-8")
    report["normalized_dataset_path"] = str(normalized_path.resolve())
    report["normalized_dataset_sha256"] = sha256(normalized_path)
    predictions_path = output.with_name(output.stem + "_test_predictions.csv")
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "scenario_id", "cutoff_timestamp", "supporting_evidence_ids", "target_event_id", "true_technique", "predicted_technique", "probability", "probabilities"])
        writer.writeheader()
        for i, p in zip(partitions["test"], probabilities[selected]["test"]):
            row = records[i]
            best = sorted(zip(labels, p), key=lambda pair: (-pair[1], pair[0]))[0]
            prediction = {k: row[k] for k in ("sample_id", "scenario_id", "cutoff_timestamp", "supporting_evidence_ids", "target_event_id")}
            prediction.update(true_technique=row["target_next_technique_id"], predicted_technique=best[0], probability=best[1], probabilities=json.dumps(dict(zip(labels, p))))
            writer.writerow(prediction)
            if len(report["test_examples"]) < 5: report["test_examples"].append(prediction)
    report["test_predictions_path"] = str(predictions_path.resolve())
    report["test_predictions_sha256"] = sha256(predictions_path)
    joblib.dump({"model": candidates[selected], "metadata": report}, output)
    report["model_version"] = sha256(output)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"model_name": selected, "model_version": report["model_version"], "split_sizes": report["split_sizes"],
        "test": report["evaluation"]["test"]["model"], "report": str(output.with_suffix(".json"))}


@lru_cache(maxsize=2)
def _artifact(path, version):
    import joblib
    return joblib.load(path)  # Locally trained artifact only, not uploaded pickle files.


def qualified_model():
    if not MODEL.exists() or not MODEL.with_suffix(".json").exists():
        return None, None, "Synthetic temporal model NOT AVAILABLE — import dataset and run python -m app.datasets train-temporal"
    try:
        report = json.loads(MODEL.with_suffix(".json").read_text(encoding="utf-8"))
        version = sha256(MODEL)
        if version != report["model_version"]: raise ValueError("Synthetic model SHA-256 mismatch")
        dataset = report["dataset"]
        normalization = dataset.get("normalization", {})
        if normalization.get("preprocessing_version") != NORMALIZATION_VERSION or normalization.get("catalog_sha256") != catalog()["sha256"]:
            raise ValueError("ATT&CK normalization missing or catalog changed; retrain synthetic temporal model")
        if sha256(report["normalized_dataset_path"]) != report["normalized_dataset_sha256"]: raise ValueError("Normalized training data SHA-256 mismatch")
        directory = Path(dataset["dataset_path"])
        for name, expected in {**dataset["verified_sha256"], "dataset_manifest.json": dataset["manifest_sha256"]}.items():
            if sha256(directory / name) != expected: raise ValueError(f"Dataset SHA-256 mismatch: {name}")
        if sha256(report["test_predictions_path"]) != report["test_predictions_sha256"]: raise ValueError("Test predictions SHA-256 mismatch")
        artifact = _artifact(str(MODEL), version)
        if artifact["metadata"] != {k:v for k,v in report.items() if k != "model_version"}: raise ValueError("Synthetic model metadata mismatch")
        if report["feature_version"] != FEATURE_VERSION or report["prediction_mode"] != "synthetic_temporal_model": raise ValueError("Synthetic feature version/mode mismatch")
        if dataset["synthetic"] is not True or dataset["real_world_validation"] is not False: raise ValueError("Invalid synthetic provenance")
        if any(label not in catalog()["techniques"] for label in artifact["model"].classes_): raise ValueError("Inactive ATT&CK class in trained model")
        return artifact["model"], report, None
    except (ValueError, OSError, KeyError) as error:
        return None, None, str(error)


def research_status():
    from app.prediction_evaluation import current_evaluation
    _, metadata, reason = qualified_model()
    evaluation, evaluation_error = current_evaluation(metadata) if metadata else (None, reason)
    return {"status": "not_available" if reason else "evaluated", "reason": reason, "metadata": metadata,
        "evaluation_run": evaluation, "evaluation_error": evaluation_error}


def predict(events, base):
    from app import temporal_experiment
    if temporal_experiment.POINTER.exists():
        try:
            return temporal_experiment.infer(events, base)
        except (OSError, KeyError) as exc:
            return {**base, "reason": str(exc)}
    from app.services.analysis_service import mapping
    from app.services.evidence_service import get_evidence_for_incident
    from app.prediction_evaluation import current_evaluation, METHOD, FORMULA
    model, report, reason = qualified_model()
    if reason: return {**base, "reason": reason}
    if not events: return {**base, "reason": "No evidence is available at this cutoff"}
    if any(e.get("simulated") is not True for e in events):
        return {**base, "reason": "Synthetic research model is restricted to simulated incidents"}
    events, _ = prefix(events, base["cutoff_timestamp"])
    if any(e.get("incident_id") != base["incident_id"] for e in events): raise ValueError("Prediction evidence belongs to a different incident")
    ids = [e["evidence_id"] for e in events]
    if len(set(ids)) != len(ids): raise ValueError("Duplicate supporting evidence ID")
    inventory = {e.evidence_id for e in get_evidence_for_incident(base["incident_id"])}
    if not set(ids).issubset(inventory): raise ValueError("Prediction evidence IDs are not in the incident evidence inventory")
    observed = []
    for e in events:
        mapped = mapping(e)
        observed.append({**e, "technique_id": mapped["technique_id"], "mapping_status": mapped["mapping_status"]})
    if not any(e["technique_id"] for e in observed):
        return {**base, "reason": "No mapped technique available in evidence prefix"}
    features = sequence_features(observed)
    probabilities = [float(p) for p in model.predict_proba([features])[0]]
    labels = list(model.classes_)
    uncertainty = entropy(probabilities)
    evaluation, evaluation_error = current_evaluation(report)
    dataset = report["dataset"]
    ranked = sorted(zip(labels, probabilities), key=lambda pair: (-pair[1], pair[0]))
    result = {**base, "status": "available", "prediction_mode": "synthetic_temporal_model", "synthetic_data": True,
        "real_world_validation": False, "training_dataset": dataset["dataset_name"], "training_dataset_version": dataset["version"],
        "training_dataset_sha256": dataset["manifest_sha256"], "model_name": report["model_name"], "model_version": report["model_version"],
        "features": features, "feature_version": FEATURE_VERSION, "prediction_horizon": HORIZON,
        "uncertainty": uncertainty, "uncertainty_value": uncertainty, "uncertainty_status": "MEASURED", "uncertainty_method": METHOD,
        "uncertainty_formula": FORMULA, "uncertainty_class_count": len(labels), "probability_distribution": dict(zip(labels, probabilities)),
        "uncertainty_interpretation": "Distribution dispersion across all trained classes, not probability of error; low entropy can accompany an incorrect or unsupported prediction",
        "evaluation_id": evaluation["evaluation_id"] if evaluation else None,
        "calibration_status": evaluation["calibration"]["status"] if evaluation else evaluation_error,
        "calibration": evaluation["calibration"] if evaluation else None,
        "conformal": evaluation["conformal"] if evaluation else None,
        "coverage": None, "coverage_reason": evaluation["conformal"]["reason"] if evaluation else evaluation_error,
        "observed_future_outcome": None, "prediction_correctness": None,
        "ground_truth_reason": "No observed future ground truth supplied for this simulated inference case; model output is not an observed event",
        "evidence_validation": {"incident_id": base["incident_id"], "all_ids_in_incident_inventory": True,
            "all_timestamps_at_or_before_cutoff": True, "unique_ids": True},
        "limitation": LIMITATION, "explanation": report["explanation"],
        "observed_prefix": [{k: e.get(k) for k in ("evidence_id", "timestamp", "source", "host", "user", "subject", "action", "object", "technique_id", "mapping_status")} for e in observed],
        "model_provenance": {"training_timestamp": report["training_timestamp"], "dataset_id": dataset["dataset_id"],
            **{key: report[key] for key in ("algorithm", "training_dataset", "training_dataset_version", "training_scenarios", "validation_scenarios", "test_scenarios", "random_seed", "feature_definition", "target_definition", "normalized_dataset_path", "normalized_dataset_sha256")},
            "file_sha256": dataset["verified_sha256"], "selection_rule": report["selection_rule"], "split_sizes": report["split_sizes"],
            "normalization": dataset["normalization"],
            "catalog_warning": dataset["labels_absent_from_active_catalog"], "label_policy": dataset["label_policy"]},
        "inference_case": "Application demonstration; INC-00001 is not a training dataset incident",
        "predictions": [{"rank": i, "predicted_technique": str(label), "predicted_technique_id": str(label), "predicted_stage": None,
            "technique_name": dataset["technique_names"][label], "predicted_technique_name": dataset["technique_names"][label],
            "probability": p, "uncertainty": uncertainty, "uncertainty_method": METHOD, "supporting_evidence_ids": base["supporting_evidence_ids"],
            "catalog_status": "active" if label in catalog()["techniques"] else "NOT IN ACTIVE CATALOG — original dataset label"}
            for i, (label, p) in enumerate(ranked, 1)]}
    result.update(current_technique_id=base["current_technique"], predicted_technique_id=str(ranked[0][0]),
        predicted_technique=str(ranked[0][0]), predicted_technique_name=dataset["technique_names"][ranked[0][0]], probability=ranked[0][1])
    result["observed_technique_prefix"] = [e["technique_id"] for e in observed if e["technique_id"]]
    result["transition_evidence"] = model.transition_evidence(features) if isinstance(model, TransitionFrequency) else None
    return result
