"""Reproducible evaluation; dataset 13 is never used for fitting or selection."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import numpy as np
import joblib
import sklearn
from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.metrics import (accuracy_score, precision_recall_fscore_support, f1_score,
                             classification_report, confusion_matrix, mean_absolute_error,
                             mean_squared_error, r2_score)
from app.datasets import DATA, FILES, CONTEXT, AF_FEATURES, TRUST_FEATURES, ARTIFACTS, features, rows, sha256

STAGE_FEATURES = ["observed_prev_stage", "observed_current_stage", "current_technique_id"]
QUALITY_FEATURES = ["source", "source_reliability", "integrity_hash_valid", "sensor_health",
                    "temporal_consistency", "graph_consistency", "corroboration_score",
                    "contradiction_count", "corroboration_count"]


def classification_metrics(actual, predicted, labels):
    precision, recall, f1, _ = precision_recall_fscore_support(actual, predicted, labels=labels, average="macro", zero_division=0)
    return {"accuracy": float(accuracy_score(actual, predicted)), "macro_precision": float(precision),
        "macro_recall": float(recall), "macro_f1": float(f1), "weighted_f1": float(f1_score(actual, predicted, average="weighted", zero_division=0)),
        "per_class": classification_report(actual, predicted, labels=labels, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(actual, predicted, labels=labels).tolist(), "class_order": list(labels),
        "actual_distribution": dict(Counter(actual)), "predicted_distribution": dict(Counter(predicted))}


def pipeline(classification=True):
    cls = RandomForestClassifier if classification else RandomForestRegressor
    return make_pipeline(DictVectorizer(sparse=False), cls(n_estimators=80, max_depth=12, min_samples_leaf=4, random_state=42, n_jobs=2))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def train_research():
    folder = DATA / "models"
    folder.mkdir(exist_ok=True)
    old = folder / "training_report.json"
    history = folder / "historical_training_report.json"
    if old.exists() and not history.exists():
        history.write_bytes(old.read_bytes())
    specifications = {
        "cdfu": ("10", CONTEXT, ["fu_" + a for a in ARTIFACTS], "incident_id", False),
        "aces": ("10", CONTEXT + ["action"], ["survival_" + a for a in ARTIFACTS] + ["residual_attack_risk", "business_impact", "response_cost", "evidence_opportunity_cost"], "incident_id", False),
        "afip": ("11", AF_FEATURES, ["anti_forensic_behavior"], "sequence_id", True),
        "trust": ("12", TRUST_FEATURES, ["calculated_evidence_trust", "graph_integrity_score"], "incident_id", False),
        "poisoning": ("12", TRUST_FEATURES, ["poisoning_label"], "incident_id", True),
        "progression": ("11", STAGE_FEATURES, ["predicted_next_stage"], "sequence_id", True),
    }
    report = {"model_family": "RandomForest research baselines; not TC-FAPN", "seed": 42,
              "benchmark_13_used_for_training": False, "models": {},
              "coverage": None, "coverage_reason": "Coverage not measured — requires observed replay outcomes."}
    for name, (dataset_id, keys, targets, group, classification) in specifications.items():
        records = rows(dataset_id)
        if any(not r.get(k) for r in records for k in keys + targets + [group]):
            raise ValueError(f"Missing required training values for {name}")
        x = [features(r, keys) for r in records]
        y = [r[targets[0]] if classification else [float(r[t]) for t in targets] for r in records]
        if any(not math.isfinite(v) for row in x for v in row.values() if isinstance(v, float)):
            raise ValueError("Nonfinite feature")
        if not classification and not np.isfinite(y).all():
            raise ValueError("Nonfinite target")
        groups = [r[group] for r in records]
        train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(x, y, groups))
        validation_idx = []
        if name == "progression":
            a, b = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=43).split(train_idx, groups=[groups[i] for i in train_idx]))
            validation_idx, train_idx = train_idx[b], train_idx[a]
        model = pipeline(classification)
        model.fit([x[i] for i in train_idx], [y[i] for i in train_idx])
        actual = [y[i] for i in test_idx]
        predicted = model.predict([x[i] for i in test_idx])
        metrics = classification_metrics(actual, predicted, sorted(set(y))) if classification else {
            "mae": float(mean_absolute_error(actual, predicted)), "rmse": float(mean_squared_error(actual, predicted) ** .5),
            "r2": float(r2_score(actual, predicted)),
            "mae_by_target": dict(zip(targets, mean_absolute_error(actual, predicted, multioutput="raw_values").tolist()))}
        validation_metrics = None
        if len(validation_idx):
            validation_metrics = classification_metrics([y[i] for i in validation_idx], model.predict([x[i] for i in validation_idx]), sorted(set(y)))
        feature_rows = [fingerprint({k: v for k, v in r.items() if k not in (group, "evidence_id", "sequence_id")}) for r in records]
        metadata = {"model_name": name, "algorithm": type(model[-1]).__name__, "dataset": dataset_id,
            "training_dataset": FILES[dataset_id], "source_sha256": sha256(DATA / "custom" / FILES[dataset_id]),
            "features": keys, "targets": targets, "training_timestamp": datetime.now(timezone.utc).isoformat(),
            "random_seed": 42, "sklearn_version": sklearn.__version__, "feature_version": "research-v2",
            "hyperparameters": model[-1].get_params(), "group_key": group,
            "train_rows": len(train_idx), "validation_rows": len(validation_idx), "test_rows": len(test_idx),
            "validation_method": "GroupShuffleSplit; fixed hyperparameters; reported scores are held-out synthetic/research-label agreement",
            "group_overlap": len(set(groups[i] for i in train_idx) & set(groups[i] for i in test_idx)),
            "duplicate_records": len(feature_rows) - len(set(feature_rows)),
            "duplicate_train_test_records": len(set(feature_rows[i] for i in train_idx) & set(feature_rows[i] for i in test_idx)),
            "feature_target_overlap": sorted(set(keys) & set(targets)), "metrics": metrics, "validation_metrics": validation_metrics,
            "split_indices_sha256": fingerprint({"train": train_idx.tolist(), "test": test_idx.tolist()}),
            "test_indices": test_idx.tolist(), "train_indices": train_idx.tolist()}
        if classification:
            majority = Counter(y[i] for i in train_idx).most_common(1)[0][0]
            metadata["majority_baseline"] = classification_metrics(actual, [majority] * len(actual), sorted(set(y)))
        if name == "progression":
            metadata["label_limitation"] = "Target is dataset 11's synthetic predicted_next_stage, not an observed future stage. Future technique labels are unavailable."
        artifact = {"model": model, "features": keys, "targets": targets, "dataset_id": dataset_id,
                    "source_sha256": metadata["source_sha256"], "metadata": metadata}
        joblib.dump(artifact, folder / f"{name}.joblib")
        metadata["model_version"] = sha256(folder / f"{name}.joblib")
        report["models"][name] = metadata
    old.write_text(json.dumps(report, indent=2), encoding="utf-8")
    diagnostics = poisoning_diagnostics(report["models"]["poisoning"])
    af = report["models"]["afip"]
    diagnostics["afip"] = {"class_distribution": dict(Counter(r["anti_forensic_behavior"] for r in rows("11"))),
        "holdout_prediction_distribution": af["metrics"]["predicted_distribution"],
        "majority_baseline": af["majority_baseline"],
        "findings": ["Accuracy alone is insufficient for imbalanced anti-forensic classification.",
                     "Compare per-class recall and predicted class counts: a majority-only model can retain high accuracy.",
                     "Probability, presence, preservation targets/actions and future-stage labels are excluded from AFIP inputs.",
                     "Unique sequence IDs prevent row identity overlap but do not establish campaign/temporal generalization."]}
    stage_targets = {}
    for row in rows("11"):
        stage_targets.setdefault(row["observed_current_stage"], set()).add(row["predicted_next_stage"])
    diagnostics["progression"] = {"current_stage_to_target_labels": {k: sorted(v) for k, v in stage_targets.items()},
        "deterministic_target_by_current_stage": all(len(v) == 1 for v in stage_targets.values()),
        "finding": "A perfect synthetic-label holdout score can reflect the dataset generator's stage transition rule. It is not evidence of learned real-world attack forecasting."}
    (folder / "evaluation_diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    from app.services.metadata_service import refresh_metadata
    refresh_metadata()
    from app.services.validation_service import validate_research_data
    validate_research_data()
    return {"models": {name: {"metrics": m["metrics"], "model_version": m["model_version"]} for name, m in report["models"].items()},
            "diagnostics": "data/models/evaluation_diagnostics.json"}


def poisoning_diagnostics(metadata):
    records = rows("12")
    train_ids, test_ids = metadata["train_indices"], metadata["test_indices"]
    quality_x = [features(r, QUALITY_FEATURES) for r in records]
    y = [r["poisoning_label"] for r in records]
    probes = []
    for heldout in sorted({r["scenario"] for r in records} - {"clean"}):
        train = [i for i in train_ids if records[i]["scenario"] != heldout]
        test = [i for i in test_ids if records[i]["scenario"] in (heldout, "clean")]
        model = pipeline()
        model.fit([quality_x[i] for i in train], [y[i] for i in train])
        predicted = model.predict([quality_x[i] for i in test])
        probes.append({"heldout_attack_scenario": heldout, "train_rows": len(train), "test_rows": len(test),
            "unseen_attack_scenario_overlap": 0, "incident_overlap": 0,
            "shared_baseline_scenario": "clean; separate incident groups", "features": QUALITY_FEATURES,
            "metrics": classification_metrics([y[i] for i in test], predicted, ["0", "1"])})
    feature_label = {}
    for key in TRUST_FEATURES[1:]:
        if key in ("fake_node", "fake_edge", "sensor_spoof", "edge_deleted", "duplicate_event", "integrity_hash_valid"):
            feature_label[key] = {v: dict(Counter(r["poisoning_label"] for r in records if r[key] == v)) for v in sorted({r[key] for r in records})}
    return {"poisoning": {"original_holdout": metadata["metrics"],
        "checks": {"duplicate_records": metadata["duplicate_records"], "duplicate_train_test_records": metadata["duplicate_train_test_records"],
                   "group_overlap": metadata["group_overlap"], "target_in_features": False,
                   "original_scenario_overlap": sorted({records[i]["scenario"] for i in train_ids} & {records[i]["scenario"] for i in test_ids})},
        "feature_label_cross_tabs": feature_label, "scenario_holdouts": probes,
        "findings": ["Original inputs expose corruption flags; target is not named as a feature, but flags are label proxies.",
                     "Original random incident split shares synthetic scenario generators across train and test.",
                     "Stress evaluation removes explicit corruption flags and withholds each attack scenario and test incident groups.",
                     "Quality measurements can still encode synthetic generation rules; these results are not raw telemetry detection or real-world validation."]}}
