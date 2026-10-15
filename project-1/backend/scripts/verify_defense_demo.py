r"""Submit inert REPLAY telemetry to the existing API; never execute host commands.

Run from backend: ..\.venv\Scripts\python.exe scripts/verify_defense_demo.py
Each run appends two events and one quarantine entry to the configured API store.
"""
import hashlib
import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    base = "http://127.0.0.1:8001"

    def api(path, body=None):
        headers = {"Content-Type": "application/json"}
        if os.environ.get("FAPT_INGEST_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["FAPT_INGEST_TOKEN"]
        request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(request, timeout=60) as response:
            return json.load(response)

    def submit(event):
        return api("/api/defense/events", {"mode": "REPLAY", "source_format": "canonical", "synchronous": True, "events": [event]})["results"][0]

    before = api("/api/defense/metrics?mode=REPLAY")
    run_id = uuid4().hex[:8]
    report = {"run_id": run_id, "scope": "SYNTHETIC REPLAY ONLY; telemetry strings are never executed", "before": before}
    for name, image, command, score, level, actions in (
        ("lsass", r"C:\Windows\System32\rundll32.exe", r"rundll32.exe C:\Windows\System32\comsvcs.dll,MiniDump", 0.225, "LOW", ["MONITOR"]),
        ("shadow", r"C:\Windows\System32\vssadmin.exe", "vssadmin delete shadows /all /quiet", 0.25, "MEDIUM", ["ALERT", "PRESERVE_EVIDENCE"]),
    ):
        event = {"timestamp": "2026-10-07T10:05:00Z", "event_source": "sysmon", "event_category": "process",
                 "hostname": f"SYNTHETIC-{name}-{run_id}", "user": "synthetic-analyst", "action": "PROCESS_CREATE",
                 "process_id": 7200, "parent_process_id": 3000, "image_path": image, "command_line": command}
        result = submit(event)
        assert result["status"] == "accepted", result
        objects = {"ingestion": result, "event": api("/api/defense/events/" + result["event_id"]),
                   "evidence": api("/api/defense/evidence/" + result["evidence_id"]),
                   "prediction": api("/api/defense/predictions/" + result["prediction"]["prediction_id"]),
                   "risk": api("/api/defense/risk/" + result["risk"]["risk_id"]),
                   "decision": api("/api/defense/decisions/" + result["decision"]["decision_id"])}
        assert all(objects["evidence"]["integrity"][k] for k in ("record_seal_valid", "raw_event_hash_valid", "verified"))
        canonical_raw = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        assert hashlib.sha256(canonical_raw).hexdigest() == objects["evidence"]["raw_event_hash"]
        sealed = {k: v for k, v in objects["evidence"].items() if k not in ("sha256", "incident_ids", "relations", "integrity")}
        canonical_seal = json.dumps(sealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        assert hashlib.sha256(canonical_seal).hexdigest() == objects["evidence"]["sha256"]
        assert objects["prediction"]["status"] == "ABSTAINED"
        assert all(objects["prediction"][k] is None for k in ("predicted_technique_id", "probability", "uncertainty"))
        assert objects["prediction"]["abstain_reason"]
        assert abs(objects["risk"]["risk_score"] - score) < 1e-9 and objects["risk"]["risk_level"] == level
        assert objects["decision"]["internal_actions"] == actions
        assert result["response_ids"] == []
        if name == "lsass":
            assert objects["evidence"]["candidate_techniques"][0]["technique_id"] == "T1003.001"
            assert result["incident_id"] is None
        else:
            objects["incident"] = api("/api/defense/incidents/" + result["incident_id"] + "?expand=true")
            assert all(objects["incident"]["chain"][k] for k in ("event", "evidence", "prediction", "risk", "decision"))
        counts = api("/api/defense/metrics?mode=REPLAY")
        objects["duplicate"] = submit(event)
        assert objects["duplicate"]["status"] == "duplicate"
        assert api("/api/defense/metrics?mode=REPLAY") == counts
        report[name] = objects
    report["quarantine"] = submit({"timestamp": "2026-10-07T10:05:00Z", "unsupported_demo_field": run_id})
    assert report["quarantine"]["status"] == "quarantined"
    assert "unsupported_demo_field" in report["quarantine"]["reason"]
    assert any(q["quarantine_id"] == report["quarantine"]["quarantine_id"] for q in api("/api/defense/quarantine"))
    report["mapping"] = api("/api/defense/mappings/T1003.001")
    assert report["mapping"]["technique_known"] and report["mapping"]["attack_version"] == "19.2"
    report["audit"] = api("/api/defense/audit/verify")
    assert report["audit"]["verified"] and not report["audit"]["failures"]
    report["audit_records"] = [a for a in api("/api/defense/audit") if a["item_id"] in {
        report[n]["ingestion"][k] if k == "event_id" else report[n]["prediction"][k]
        for n in ("lsass", "shadow") for k in ("event_id", "prediction_id")}]
    assert len(report["audit_records"]) == 4
    report["after"] = api("/api/defense/metrics?mode=REPLAY")
    for key in ("events", "evidence", "predictions", "abstained"):
        assert report["after"][key] - before[key] == 2
    assert report["after"]["incidents"] - before["incidents"] == 1
    report["health"] = api("/api/defense/health")
    assert report["health"]["status"] == "ok"
    report["system"] = api("/api/defense/system/status")
    assert report["system"]["response_execution_mode"] == "DRY_RUN"
    report["status"] = api("/api/status")
    schema = api("/openapi.json")
    report["openapi"] = {"defense_paths": sorted(p for p in schema["paths"] if p.startswith("/api/defense")),
                         "ingest_schema": schema["components"]["schemas"]["IngestRequest"]}
    assert len(report["openapi"]["defense_paths"]) == 28
    ingest = report["openapi"]["ingest_schema"]
    assert not ingest["additionalProperties"]
    assert ingest["properties"]["mode"]["enum"] == ["LIVE", "LAB", "REPLAY"]
    assert set(ingest["properties"]) == {"mode", "source_format", "events", "synchronous"}
    with urlopen(base + "/docs") as response:
        report["docs_http_status"] = response.status
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
