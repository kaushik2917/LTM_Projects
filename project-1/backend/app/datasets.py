"""Reproducible dataset preparation and baseline training. Run from backend/."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
FILES = {
    "10": "10_fapt_guard_cyber_forensic_response.csv",
    "11": "11_fapt_anti_forensic.csv",
    "12": "12_fapt_evidence_trust_poisoning.csv",
    "13": "13_fapt_bench_2_0.csv",
}
ROLES = {
    "10": ["ACES", "CDFU", "ELC", "ERS", "JCFE", "U-EPPC"],
    "11": ["AFIP", "Predictive Evidence Preservation"],
    "12": ["DETP", "P3R", "EGIS", "TC-FAPN robustness"],
    "13": ["final robustness evaluation only"],
}
ARTIFACTS = ["memory", "process_state", "active_connections", "sysmon_logs",
             "security_logs", "powershell_history", "registry", "disk_artifacts",
             "dns_logs", "auth_logs", "network_flows"]
CONTEXT = ["attack_stage", "technique_id", "attacker_intent", "asset_criticality",
           "baseline_attack_risk", "evidence_trust", "anti_forensic_risk",
           "prediction_uncertainty"]
AF_FEATURES = ["observed_prev_stage", "observed_current_stage", "current_technique_id",
               "attacker_intent", "evidence_trust", "graph_integrity_score"]
TRUST_FEATURES = ["source", "missing_ratio", "timestamp_shift_seconds", "edge_deleted",
                  "fake_node", "fake_edge", "sensor_spoof", "duplicate_event",
                  "contradiction_count", "corroboration_count", "source_reliability",
                  "integrity_hash_valid", "sensor_health", "temporal_consistency",
                  "graph_consistency", "corroboration_score"]
NUMERIC = set(CONTEXT[3:] + AF_FEATURES[-2:] + TRUST_FEATURES[1:])


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def rows(dataset_id):
    with (DATA / "custom" / FILES[dataset_id]).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def features(row, keys):
    return {k: float(row[k]) if k in NUMERIC else str(row[k]) for k in keys}


def prepare(source):
    (DATA / "custom").mkdir(parents=True, exist_ok=True)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "datasets": []}
    for dataset_id, filename in FILES.items():
        src, dst = Path(source) / filename, DATA / "custom" / filename
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        records = rows(dataset_id)
        if not records or any(v in (None, "") for r in records for v in r.values()):
            raise ValueError(f"Dataset {dataset_id}: empty data or missing values")
        manifest["datasets"].append({
            "id": dataset_id, "filename": filename, "rows": len(records),
            "sha256": sha256(dst), "columns": list(records[0]), "modules": ROLES[dataset_id],
            "usage": "evaluation_only" if dataset_id == "13" else "development",
            "provenance": "user_supplied_research_table",
            "synthetic_labels": dataset_id in ("11", "13"),
        })
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def train():
    from app.training import train_research
    return train_research()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source-dir", type=Path, required=True)
    sub.add_parser("train")
    sub.add_parser("evaluate")
    temporal_import = sub.add_parser("import-temporal")
    temporal_import.add_argument("path", type=Path)
    sub.add_parser("train-temporal")
    sub.add_parser("evaluate-temporal")
    sub.add_parser("experiment-temporal")
    optc = sub.add_parser("import-optc")
    optc.add_argument("path", type=Path)
    optc.add_argument("--limit", type=int, default=100000)
    args = parser.parse_args()
    if args.command == "experiment-temporal":
        from app.temporal_experiment import train_experiment
        result = train_experiment()
    elif args.command == "import-temporal":
        from app.synthetic_temporal import import_archive
        result = import_archive(args.path)
    elif args.command == "train-temporal":
        from app.synthetic_temporal import train
        result = train()
    elif args.command == "evaluate-temporal":
        from app.prediction_evaluation import run_evaluation
        result = run_evaluation()
    elif args.command == "prepare":
        result = prepare(args.source_dir)
    elif args.command == "train":
        result = train()
    elif args.command == "evaluate":
        from app.services.benchmark_service import run_benchmark as evaluate_benchmark
        result = evaluate_benchmark()
    else:
        from app.services.optc_service import import_optc
        result = import_optc(args.path, args.limit)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
