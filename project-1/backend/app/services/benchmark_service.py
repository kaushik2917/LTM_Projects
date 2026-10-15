"""Measured deterministic fixture replay. Never treats expected CSV scores as observations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
from uuid import uuid4
from app.datasets import DATA, FILES, rows, sha256
from app.services.evidence_service import get_simulated_evidence
from app.services.analysis_service import analyze_evidence, prediction


def average(values):
    available = [v for v in values if v is not None]
    return sum(available) / len(available) if available else None


def run_benchmark():
    definitions = rows("13")
    templates = {}
    for row in definitions: templates.setdefault(row["scenario_name"], row)
    original = [e.model_dump(mode="json") for e in get_simulated_evidence()]
    baseline = analyze_evidence(original)
    baseline_prediction = prediction(original, "INC-00001")
    baseline_trust = average([e["evidence_trust"] for e in baseline])
    baseline_utility = sum(e["forensic_utility"] or 0 for e in baseline)
    results = []
    for name, descriptor in templates.items():
        events = deepcopy(original)
        operators = []
        supported = True
        sensor = descriptor["sensor_disabled"]
        if sensor != "none":
            source = {"netflow": "network"}.get(sensor, sensor)
            events = [e for e in events if e["source"] != source]
            operators.append(f"Remove source {source}; fixture network mapped to netflow")
        ratio = float(descriptor["missing_event_ratio"])
        if ratio and sensor == "none":
            count = math.ceil(len(events) * ratio)
            events = events[:-count]
            operators.append(f"Remove last {count} observed records (ceil of requested ratio)")
        injected = math.ceil(len(original) * float(descriptor["fake_event_ratio"]))
        for i in range(injected):
            fake = deepcopy(original[-1])
            fake["evidence_id"] = f"INJECTED-{i}"
            fake["object"] = "fabricated-object"
            if descriptor["poisoning_type"] == "fake_node": fake["subject"] = "fabricated-process"
            if descriptor["poisoning_type"] == "contradiction": fake["evidence_id"] = original[-1]["evidence_id"]
            # Deliberately retain original hash so validation sees altered evidence.
            events.append(fake)
        if injected: operators.append(f"Inject {injected} inconsistent fixture records with invalid original hashes")
        shift = int(descriptor["timestamp_shift_seconds"])
        if shift:
            events[0]["timestamp"] = (datetime.fromisoformat(events[0]["timestamp"]) + timedelta(seconds=shift)).isoformat()
            operators.append(f"Shift first event by {shift} seconds without reordering input")
        if descriptor["concept_drift_or_unseen"] == "1":
            supported = False
            operators.append("Not executed: genuine drift/unseen-technique evaluation needs held-out observed traces and labels")
        if not supported:
            results.append({"scenario_id": descriptor["benchmark_id"], "scenario_name": name, "status": "not_measured", "reason": operators[-1],
                            "prediction_accuracy": None, "technique_prediction_metric": None, "coverage": None})
            continue
        quality = analyze_evidence(events)
        forecast = prediction(events, "INC-00001")
        surviving_ids = set(e["evidence_id"] for e in events) & set(e["evidence_id"] for e in original)
        utility_remaining = sum(e["forensic_utility"] or 0 for e in baseline if e["evidence_id"] in surviving_ids)
        trust = average([e["evidence_trust"] for e in quality])
        distribution = {p["predicted_stage"]: p["probability"] for p in forecast["predictions"]}
        original_distribution = {p["predicted_stage"]: p["probability"] for p in baseline_prediction["predictions"]}
        total_variation = sum(abs(distribution.get(k, 0) - original_distribution.get(k, 0)) for k in set(distribution) | set(original_distribution)) / 2 if distribution and original_distribution else None
        results.append({"scenario_id": descriptor["benchmark_id"], "scenario_name": name, "status": "executed_fixture_replay",
            "operators": operators or ["Unmodified six-event fixture"], "input_events": len(original), "output_events": len(events),
            "injected_events": injected, "actual_missing_ratio": 1 - len(surviving_ids) / len(original),
            "mean_evidence_trust": trust, "trust_change_from_clean": trust - baseline_trust if trust is not None else None,
            "detected_anomaly_records": sum(bool(set(e["warnings"]) - {"timezone_unspecified"}) for e in quality),
            "retained_fixture_utility_ratio": utility_remaining / baseline_utility if baseline_utility else None,
            "evidence_loss": 1 - len(surviving_ids) / len(original),
            "robustness_degradation": total_variation, "robustness_metric": "Total variation of next-stage distribution, not accuracy loss",
            "uncertainty": forecast["uncertainty"], "prediction_status": forecast["status"],
            "prediction_accuracy": None, "technique_prediction_metric": None, "evidence_trust_error": None,
            "forensic_utility_error": None, "response_survival": None, "coverage": None,
            "not_measured_reason": "No observed future labels, true trust/utility labels or post-response acquisition. Fixture retention measures a replay operator, not host survival."})
    report = {"run_id": str(uuid4()), "executed_at": datetime.now(timezone.utc).isoformat(), "seed": None,
        "determinism": "Fixed operators; no random corruption", "dataset": "13", "dataset_sha256": sha256(DATA / "custom" / FILES["13"]),
        "usage": "evaluation_only", "rows": len(definitions), "templates_selected": len(templates),
        "selection": "First CSV row per named scenario; not a replay of all 1,890 rows", "scenarios": results,
        "fixture_sha256": __import__('hashlib').sha256(json.dumps(original, sort_keys=True).encode()).hexdigest(),
        "model_version": baseline_prediction.get("model_version"), "measured_model_metrics": {"prediction_stability": "per executed scenario"},
        "status": "executed_fixture_replay", "coverage": None,
        "prediction_mode": "synthetic_next_stage", "future_prediction_robustness": None,
        "future_prediction_robustness_reason": "NOT MEASURED — no genuine observed future labels for fixture replay",
        "coverage_reason": "Coverage not measured — requires observed replay outcomes.",
        "limitations": ["Deterministic six-event synthetic fixture stress test; not OpTC or real-world evaluation.",
                        "CSV expected_* values are not used as model measurements.",
                        "Concept drift and unseen-technique scenarios are explicitly unmeasured.",
                        "No post-response outcome observations exist; predicted ACES survival remains separate."]}
    (DATA / "benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    folder = DATA / "benchmark_runs"
    folder.mkdir(exist_ok=True)
    (folder / f"{report['run_id']}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    from app.services.workflow_service import record
    record("RESEARCH", "benchmark_execution", {"run_id": report["run_id"], "dataset_sha256": report["dataset_sha256"],
        "executed_scenarios": sum(r["status"] == "executed_fixture_replay" for r in results), "result_file": f"benchmark_runs/{report['run_id']}.json"})
    return report
