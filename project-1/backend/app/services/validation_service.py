"""Data-quality warnings are observations, not silent repairs of research inputs."""
from collections import Counter
import json
import math
from app.datasets import DATA, FILES, rows
from app.services.attack_service import catalog
from app.services.metadata_service import model_report


def validate_research_data():
    techniques = catalog()["techniques"]
    result = {}
    for dataset_id in FILES:
        records = rows(dataset_id)
        identity = {"10": ["incident_id", "action"], "11": ["sequence_id"], "12": ["evidence_id"], "13": ["benchmark_id"]}[dataset_id]
        identifiers = Counter(tuple(r[k] for k in identity) for r in records)
        technique_key = "current_technique_id" if dataset_id == "11" else "technique_id"
        invalid = sorted({r.get(technique_key) for r in records if r.get(technique_key) not in techniques})
        bounded = [k for k in records[0] if k.startswith(("fu_", "survival_")) or k in ("baseline_attack_risk", "residual_attack_risk", "evidence_trust", "anti_forensic_probability", "prediction_uncertainty", "calculated_evidence_trust", "graph_integrity_score")]
        numeric_errors = []
        for index, row in enumerate(records):
            for key in bounded:
                try:
                    value = float(row[key])
                    if not math.isfinite(value) or not 0 <= value <= 1: raise ValueError()
                except (TypeError, ValueError): numeric_errors.append({"row": index + 2, "column": key})
        result[dataset_id] = {"missing_values": sum(v in (None, "") for row in records for v in row.values()),
            "duplicate_identifiers": sum(n - 1 for n in identifiers.values() if n > 1), "identity_columns": identity,
            "invalid_or_inactive_attack_ids": invalid, "invalid_probability_or_unit_values": numeric_errors[:50],
            "duplicate_complete_records": len(records) - len({json.dumps(r, sort_keys=True) for r in records}),
            "warning": "Inactive ATT&CK IDs are retained as original dataset labels; do not silently relabel training targets." if invalid else None}
    models = model_report()["models"]
    for name, meta in models.items():
        result["model:" + name] = {"missing_metadata": [key for key in ("model_version", "training_timestamp", "features", "source_sha256", "random_seed") if meta.get(key) is None],
            "group_overlap": meta.get("group_overlap"), "duplicate_train_test_records": meta.get("duplicate_train_test_records"),
            "feature_target_overlap": meta.get("feature_target_overlap")}
    output = {"checks": result, "policy": "Report warnings without fabricating or relabeling evidence"}
    (DATA / "validation_report.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output
