"""Auditable, simulation-only incident workflow built on the dataset baselines."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4

from app.datasets import DATA
from app.services.evidence_service import get_evidence_for_incident, verify_evidence_integrity
from app.services.incident_service import get_simulated_incident
from app.services.research_service import responses, anti_forensic
from app.services.analysis_service import analyze_evidence, prediction, stage_name, mapping
from app.services.metadata_service import provenance
from app.temporal_prediction import prefix

DB = DATA / "workflow.sqlite3"


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB)
    connection.execute("CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, incident TEXT, kind TEXT, created TEXT, payload TEXT)")
    return connection


def record(incident_id, kind, payload):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT payload FROM audit WHERE incident=? ORDER BY rowid DESC LIMIT 1", (incident_id,)).fetchone()
        last = json.loads(previous[0]) if previous else None
        previous_hash = last.get("current_hash", hashlib.sha256(previous[0].encode()).hexdigest()) if last else None
        entry = {**payload, "id": str(uuid4()), "incident_id": incident_id, "kind": kind, "created_at": now(),
                 "actor": "local-research-system", "status": "recorded", "previous_hash": previous_hash,
                 "chain_method": "sha256-canonical-json-v1", "legacy_predecessor": bool(last and "current_hash" not in last)}
        if kind == "future_prediction":
            entry["result"] = {**entry["result"], "prediction_id": entry["id"], "timestamp": entry["created_at"], "prediction_timestamp": entry["created_at"]}
        entry["current_hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        connection.execute("INSERT INTO audit VALUES (?, ?, ?, ?, ?)",
            (entry["id"], incident_id, kind, entry["created_at"], json.dumps(entry)))
    return entry


def history(incident_id):
    with closing(connect()) as connection:
        return [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM audit WHERE incident=? ORDER BY rowid DESC", (incident_id,))]


def verify_chain(incident_id):
    entries = list(reversed(history(incident_id)))
    previous = None
    checked = []
    for entry in entries:
        saved = entry.get("current_hash")
        if saved:
            calculated = hashlib.sha256(json.dumps({k: v for k, v in entry.items() if k != "current_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            valid = calculated == saved and entry.get("previous_hash") == previous
        else:
            valid = None
        checked.append({"id": entry["id"], "hash_valid": valid, "status": "legacy_unsealed" if valid is None else "verified" if valid else "mismatch"})
        previous = saved or hashlib.sha256(json.dumps(entry).encode()).hexdigest()
    return {"records": checked, "verified": all(e["hash_valid"] is not False for e in checked),
            "legacy_unsealed_count": sum(e["hash_valid"] is None for e in checked),
            "limitation": "Local hash chain detects edits and internal deletion; no external anchor/signature, so tail truncation or full database replacement is not authenticated."}


def snapshot(incident_id):
    incident = get_simulated_incident(incident_id)
    if incident is None:
        raise LookupError("Incident not found")
    evidence = get_evidence_for_incident(incident_id)
    return {"incident": incident.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "integrity": [{"evidence_id": e.evidence_id, "valid": verify_evidence_integrity(e.evidence_id),
                           "scope": "legacy fixture ID/subject/action/object hash; not whole-record authentication"} for e in evidence]}


def graph(incident_id, upto=None, cutoff_timestamp=None):
    state = snapshot(incident_id)
    state["evidence"], _ = prefix(state["evidence"], cutoff_timestamp, upto)
    nodes, edges = {}, []
    for event in state["evidence"]:
        keys = []
        for side in ("subject", "object"):
            key = json.dumps([event["host"], event[side + "_type"], event[side].lower()])
            node = nodes.setdefault(key, {"id": key, "label": event[side], "type": event[side + "_type"], "first_seen": event["timestamp"], "evidence_ids": []})
            node["last_seen"] = event["timestamp"]
            node["evidence_ids"].append(event["evidence_id"])
            keys.append(key)
        edges.append({"source": keys[0], "target": keys[1], "action": event["action"],
                      "timestamp": event["timestamp"], "evidence_id": event["evidence_id"],
                      "technique_id": event["attack_technique_id"], "source_sensor": event["source"],
                      "confidence": event["confidence"], "relationship": event["action"], "mapping": mapping(event)})
    return {"nodes": list(nodes.values()), "edges": sorted(edges, key=lambda e: e["timestamp"]),
            "simulated": True, "identity_scope": "Fixture names within host; OpTC uses UUID identities"}


def preserve(incident_id):
    state = snapshot(incident_id)
    # Persist the full snapshot as canonical bytes, including all event fields.
    material = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    entry = record(incident_id, "preservation", {"snapshot_json": material, "snapshot_id": str(uuid4()),
        "sha256": hashlib.sha256(material.encode()).hexdigest(), "evidence_count": len(state["evidence"]),
        "evidence_ids": [e["evidence_id"] for e in state["evidence"]],
        "provider": "local_simulation_snapshot", "simulated": True,
        "scope": "Application evidence snapshot; no live-host memory or log acquisition"})
    stored = next(e for e in history(incident_id) if e["id"] == entry["id"])
    valid = hashlib.sha256(stored["snapshot_json"].encode()).hexdigest() == stored["sha256"]
    if not valid: raise ValueError("Preservation verification failed")
    return {**entry, "verification_status": "VERIFIED"}


def assessment(incident_id, context, previous_stage, graph_integrity):
    state = snapshot(incident_id)
    future = run_prediction(incident_id, persist=False)
    results = responses(context, future.get("probability_distribution") if future["status"] == "available" else None)
    afip = anti_forensic({"observed_prev_stage": previous_stage,
        "observed_current_stage": context["attack_stage"], "current_technique_id": context["technique_id"],
        "attacker_intent": context["attacker_intent"], "evidence_trust": context["evidence_trust"],
        "graph_integrity_score": graph_integrity})
    return record(incident_id, "assessment", {"context": context, "context_source": "analyst_supplied_scenario",
        "future_prediction_context": future,
        "prediction_integration": "Future probabilities weight per-technique action-conditioned residual-risk estimates plus explicit fallback assumptions; a separate configurable term extends the base objective." if future["status"] == "available" else "Future prediction unavailable; base objective retained.",
        "uncertainty_source": "Analyst-supplied simulation assumption; not substituted with synthetic stage uncertainty",
        "preservation_priority": {"method": "Descending supplied evidence volatility; advisory only, no observed loss claimed",
            "evidence_ids": [e["evidence_id"] for e in sorted(state["evidence"], key=lambda e: -e["volatility"])],
            "future_relevance": None, "reason": "No validated technique-to-artifact relevance model; future relevance is NOT AVAILABLE"},
        "response_analysis": results, "anti_forensic": afip,
        "evidence_ids": [e["evidence_id"] for e in state["evidence"]],
        "autonomy": {"decision": "RECOMMEND_ONLY", "reason": "Uncalibrated research baselines; no real host execution"},
        "safety_certificate": {"type": "research_decision_record", "certified_safe": False,
            "simulated": True, "calibrated": False, "model_family": "random_forest_baseline"}})


def simulate(incident_id, assessment_id, action):
    snapshot(incident_id)
    if not verify_chain(incident_id)["verified"]:
        raise ValueError("Audit-chain verification failed; investigate before recording a simulation")
    run = next((entry for entry in history(incident_id) if entry["id"] == assessment_id and entry["kind"] == "assessment"), None)
    if run is None:
        raise LookupError("Assessment not found for this incident")
    candidate = next((c for c in run["response_analysis"]["candidates"] if c["action"] == action), None)
    if candidate is None:
        raise ValueError("Action is not in the selected assessment")
    evidence_risk = []
    for event in analyze_evidence(snapshot(incident_id)["evidence"]):
        artifact = {"sysmon": "sysmon_logs", "authentication": "auth_logs", "network": "network_flows", "process": "process_state"}.get(event["source"])
        survival = candidate.get("survival_" + artifact) if artifact else None
        evidence_risk.append({"evidence_id": event["evidence_id"], "volatility": event["volatility"],
            "predicted_survival": survival, "predicted_loss": 1 - survival if survival is not None else None,
            "artifact_mapping": artifact, "observed_post_response_survival": None})
    preservation = preserve(incident_id)
    return record(incident_id, "simulation", {"assessment_id": assessment_id, "action": action,
        "preservation_id": preservation["id"], "predicted_outcome": candidate,
        "preservation": {key: preservation[key] for key in
            ("snapshot_id", "sha256", "evidence_count", "verification_status", "scope")},
        "evidence_at_risk": evidence_risk, "snapshot_verification": preservation["verification_status"],
        "observed_post_response_survival": None, "observed_survival_reason": "No host response was executed; only local snapshot existence and hash are measured",
        "simulated": True, "host_action_executed": False,
        "message": "Evidence snapshot saved; selected action recorded as a simulation only."})


def report(incident_id):
    state = snapshot(incident_id)
    entries = history(incident_id)
    benchmark_path = DATA / "benchmark_report.json"
    for entry in entries:
        if entry["kind"] == "preservation":
            entry["snapshot_integrity_valid"] = hashlib.sha256(entry["snapshot_json"].encode()).hexdigest() == entry["sha256"]
    return {"generated_at": now(), "mode": "simulation", **state, "audit": entries,
            "evidence_analysis": analyze_evidence(state["evidence"]), "temporal_provenance": graph(incident_id),
            "stored_predictions": [e for e in entries if e["kind"] in ("prediction", "future_prediction")],
            "future_attack_prediction": run_prediction(incident_id, persist=False),
            "chain_of_custody": verify_chain(incident_id), "research_provenance": provenance(),
            "benchmark": json.loads(benchmark_path.read_text()) if benchmark_path.exists() else None,
            "benchmark_scope": "Separate synthetic fixture stress suite; not observed validation of this incident's response",
            "limitations": ["Fixture incident; not an imported OpTC attack.",
                            "Scores are research estimates, not calibrated safety guarantees.",
                            "Local snapshot hashes detect changes; they do not authenticate the original sensor."]}


def run_prediction(incident_id, cutoff_timestamp=None, persist=True, task="technique", events=None):
    from app.services.future_prediction_service import predict
    domain = None
    if events is None:
        if get_simulated_incident(incident_id) is not None:
            events = snapshot(incident_id)["evidence"]
        else:
            from app.temporal_prediction import load_sequences
            path = DATA / "temporal_events.json"
            if not path.exists():
                raise LookupError("Incident not found; no reviewed temporal event bundle has been supplied")
            meta, all_events = load_sequences(path)
            domain = meta["domain"]
            events = [e for e in all_events if e["incident_id"] == incident_id]
            if not events: raise LookupError("Incident not found in reviewed temporal event bundle")
    result = predict(events, incident_id, cutoff_timestamp, task, domain)
    signature = hashlib.sha256(json.dumps({k: v for k, v in result.items() if k != "prediction_timestamp"}, sort_keys=True).encode()).hexdigest()
    saved = next((e for e in history(incident_id) if e["kind"] == "future_prediction" and e.get("input_hash") == signature), None)
    if persist and saved is None:
        saved = record(incident_id, "future_prediction", {"result": result, "input_hash": signature,
            "evidence_ids": result["supporting_evidence_ids"], "cutoff_timestamp": result["cutoff_timestamp"]})
    if saved:
        result = {**saved["result"], "prediction_id": saved["id"], "prediction_timestamp": saved["created_at"], "timestamp": saved["created_at"]}
        result["predictions"] = [{**p, **{k: result[k] for k in ("prediction_id", "incident_id", "cutoff_timestamp", "prediction_timestamp", "current_technique", "model_name", "model_version", "training_dataset", "prediction_horizon", "prediction_mode")}} for p in result["predictions"]]
    return result


def analysis(incident_id, upto=None, persist=True, cutoff_timestamp=None):
    state = snapshot(incident_id)
    events, cutoff = prefix(state["evidence"], cutoff_timestamp, upto)
    prediction_result = prediction(events, incident_id)
    prediction_result.update(prediction_mode="synthetic_next_stage", cutoff_timestamp=cutoff)
    if persist and prediction_result["status"] == "available":
        signature = hashlib.sha256(json.dumps({"events": events, "cutoff": cutoff, "model": prediction_result["model_version"]}, sort_keys=True).encode()).hexdigest()
        existing = next((e for e in history(incident_id) if e["kind"] == "prediction" and e.get("input_hash") == signature), None)
        saved = existing or record(incident_id, "prediction", {"result": prediction_result, "input_hash": signature,
                    "evidence_ids": prediction_result["supporting_evidence_ids"], "model_version": prediction_result["model_version"]})
        prediction_result = {**prediction_result, "prediction_id": saved["id"], "timestamp": saved["created_at"], "prediction_timestamp": saved["created_at"]}
    mapped = [mapping(e) for e in events]
    latest = next((m for m in reversed(mapped) if m["mapping_status"] != "UNMAPPED"), None)
    audit = history(incident_id)
    return {"incident": state["incident"], "evidence": analyze_evidence(events), "graph": graph(incident_id, upto, cutoff_timestamp),
        "cutoff_timestamp": cutoff, "synthetic_prediction": prediction_result,
        "future_prediction": run_prediction(incident_id, cutoff, persist=persist, events=events),
        "prediction": prediction_result, "current_stage": stage_name(latest) if latest else None,
        "current_technique": latest["technique_id"] if latest else None, "mappings": mapped,
        "timeline": [{"evidence_id": e["evidence_id"], "timestamp": e["timestamp"]} for e in state["evidence"]],
        "latest_assessment": next((e for e in audit if e["kind"] == "assessment"), None),
        "coverage": None, "coverage_reason": "Coverage not measured — requires observed replay outcomes."}


def verification(incident_id):
    state = report(incident_id)
    return record(incident_id, "verification", {"chain": state["chain_of_custody"], "integrity": state["integrity"],
        "snapshot_checks": [{"id": e["id"], "valid": e["snapshot_integrity_valid"]} for e in state["audit"] if e["kind"] == "preservation"],
        "evidence_ids": [e["evidence_id"] for e in state["evidence"]]})


def export_report(incident_id):
    snapshot(incident_id)
    record(incident_id, "report_generation", {"result": "JSON forensic report", "status": "generated"})
    return report(incident_id)
