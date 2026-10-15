"""One source of research names, provenance, splits and missing-data states."""
from datetime import datetime, timezone
from functools import lru_cache
import json
from app.datasets import DATA, ROOT, FILES, ROLES, rows, sha256


def config():
    return json.loads((ROOT / "backend/config/research.json").read_text())


def model_report():
    path = DATA / "models/training_report.json"
    report = json.loads(path.read_text()) if path.exists() else {"models": {}}
    for model in report["models"].values():
        model.pop("train_indices", None)
        model.pop("test_indices", None)
    return report


def refresh_metadata():
    path = DATA / "manifest.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    imports = {r["id"]: r for r in old.get("datasets", [])}
    models = model_report()["models"]
    result = []
    for dataset_id, filename in FILES.items():
        source = DATA / "custom" / filename
        definition = config()["datasets"][dataset_id]
        if not source.exists():
            result.append({"id": dataset_id, "dataset_id": dataset_id, "dataset_name": definition["name"],
                           "processing_status": "unavailable", "rows": 0, "filename": filename})
            continue
        records = rows(dataset_id)
        columns = list(records[0]) if records else []
        related = {name: m for name, m in models.items() if m["dataset"] == dataset_id}
        features = sorted({f for m in related.values() for f in m["features"]})
        labels = sorted({t for m in related.values() for t in m["targets"]})
        result.append({"id": dataset_id, "dataset_id": dataset_id, "dataset_name": definition["name"],
            **definition, "filename": filename, "file_name": filename, "sha256": sha256(source),
            "file_hash": sha256(source), "rows": len(records), "number_of_rows": len(records),
            "number_of_events": None, "number_of_incidents": len({r["incident_id"] for r in records}) if "incident_id" in columns else None,
            "feature_count": len(features), "label_count": len(labels), "columns": columns,
            "feature_columns": features, "label_columns": labels,
            "label_count_definition": "Number of model target columns; benchmark descriptors are not training features",
            "split_by_model": {name: {key: m.get(key) for key in ("train_rows", "validation_rows", "test_rows", "random_seed", "validation_method")} for name, m in related.items()},
            "train_rows": next(iter(related.values())).get("train_rows") if related else None,
            "validation_rows": next(iter(related.values())).get("validation_rows") if related else None,
            "test_rows": next(iter(related.values())).get("test_rows") if related else None,
            "import_timestamp": imports.get(dataset_id, {}).get("import_timestamp", old.get("created_at")),
            "processed_at": datetime.now(timezone.utc).isoformat(), "processing_status": "available",
            "preprocessing_version": config()["preprocessing_version"], "modules": ROLES[dataset_id],
            "usage": "evaluation_only" if dataset_id == "13" else "development",
            "synthetic_labels": dataset_id in ("11", "13"), "event_count_reason": "Tabular research rows are not raw telemetry events"})
    from app.synthetic_temporal import DIRECTORY, load_dataset
    if DIRECTORY.exists():
        try:
            temporal, _, _ = load_dataset()
            result.append({**temporal, "id": temporal["dataset_id"], "filename": "synthetic_temporal/dataset_manifest.json",
                "rows": temporal["sample_count"], "number_of_events": temporal["event_count"],
                "modules": ["Future ATT&CK Technique Prediction"], "usage": "Synthetic Dataset — NOT REAL-WORLD VALIDATION",
                "processing_status": "available", "sha256": temporal["manifest_sha256"], "file_hash": temporal["manifest_sha256"]})
        except (ValueError, OSError, KeyError) as error:
            result.append({"id": "synthetic_temporal", "filename": "synthetic_temporal/dataset_manifest.json", "rows": 0,
                "modules": ["Future ATT&CK Technique Prediction"], "usage": "Synthetic Dataset", "processing_status": "invalid", "reason": str(error)})
    from app.temporal_experiment import DATASET, VERSION, GENERATOR, validate
    if DATASET.exists():
        bundle = json.loads(DATASET.read_text(encoding="utf-8"))
        checks = validate(bundle)
        result.append({"id": "synthetic_temporal_v2", "dataset_name": bundle["dataset_name"] + " v" + VERSION,
            "version": VERSION, "generator_version": GENERATOR, "seed": bundle["seed"],
            "filename": "synthetic_temporal_v2/scenarios.json", "rows": len(bundle["scenarios"]),
            "number_of_events": sum(len(s["events"]) for s in bundle["scenarios"]),
            "modules": ["Future prediction", "Calibration", "Conformal evaluation", "Synthetic demonstration"],
            "usage": "Synthetic research; scenario-disjoint train/calibration/test", "processing_status": "available",
            "sha256": sha256(DATASET), "file_hash": sha256(DATASET), "split_checks": checks, "assumptions": bundle["assumptions"],
            "synthetic": True, "real_world_validation": False})
    result = {"created_at": old.get("created_at"), "datasets": result}
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def provenance():
    path = DATA / "manifest.json"
    return {"datasets": json.loads(path.read_text()).get("datasets", []) if path.exists() else [],
            "models": model_report(), "configuration": config()}
