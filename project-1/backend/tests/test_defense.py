import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.defense import evidence, executor, incidents, inference, pipeline, policy, responses, risk, store, verification
from app.defense.events import normalize
from app.defense.store import sha
from app.main import app

CONFIG = json.loads(store.CONFIG.read_text(encoding="utf-8"))


def sysmon(code=1, utc="2026-10-07 10:00:00.000", host="LAB-WIN-01", **data):
    base = {"Image": r"C:\Windows\System32\cmd.exe", "CommandLine": "cmd.exe /c whoami", "ProcessId": "4242",
            "ParentProcessId": "1000", "ParentImage": r"C:\Windows\explorer.exe", "User": r"LAB\analyst", "UtcTime": utc}
    return {"EventID": code, "Computer": host, "Channel": "Microsoft-Windows-Sysmon/Operational", "EventRecordID": hash(utc) % 10**6,
            "EventData": {**base, **data}}


def network(utc, destination="203.0.113.50", **data):
    fields = {"DestinationIp": destination, "DestinationPort": "443", "SourceIp": "10.0.0.5", "SourcePort": "50000", "Protocol": "tcp", **data}
    return sysmon(3, utc, **fields)


def available(technique="T1071.001", probability=0.9, uncertainty=0.1):
    """Mocked qualified-model output: exercises the downstream path without claiming a real model exists."""
    def fake(events, incident_id, cutoff, task="technique", domain=None):
        return {"status": "available", "predictions": [{"rank": 1, "predicted_technique": technique, "technique_name": "test",
                "probability": probability}, {"rank": 2, "predicted_technique": "T1041", "technique_name": "test", "probability": 1 - probability}],
                "uncertainty": uncertainty, "model_name": "test-model", "model_version": "a" * 64, "feature_version": "future_prediction_v1",
                "training_dataset_version": "test", "prediction_horizon": "test", "calibration_status": "NOT MEASURED"}
    return patch("app.services.future_prediction_service.predict", side_effect=fake)


class DefenseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temp.name)
        settings = json.loads(json.dumps(CONFIG))
        settings["inference"]["min_interval_seconds"] = 0
        self.settings = settings
        (root / "defense.json").write_text(json.dumps(settings), encoding="utf-8")
        self.patches = [patch.object(store, "DB", root / "defense.sqlite3"), patch.object(store, "CONFIG", root / "defense.json")]
        for item in self.patches:
            item.start()
        store.config.cache_clear()
        pipeline.HEALTH.__init__()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        store.config.cache_clear()
        self.temp.cleanup()

    def rewrite(self, change):
        change(self.settings)
        (Path(self.temp.name) / "defense.json").write_text(json.dumps(self.settings), encoding="utf-8")
        store.config.cache_clear()

    # ---------------- ingestion ----------------
    def test_valid_sysmon_event_is_normalized_and_preserved(self):
        result = pipeline.process(sysmon(), "sysmon", "REPLAY")
        self.assertEqual(result["status"], "accepted")
        event = store.record("events", "event_id", result["event_id"])
        self.assertEqual((event["process_id"], event["parent_process_id"], event["process_name"]), (4242, 1000, "cmd.exe"))
        self.assertEqual(event["timestamp_utc"], "2026-10-07T10:00:00.000000+00:00")
        self.assertEqual(event["timestamp_basis"], "sysmon_UtcTime_documented_utc")
        self.assertIsNone(event["technique_id"])
        self.assertIsNone(event["destination_ip"])

    def test_malformed_events_are_quarantined_without_crashing(self):
        for raw, fmt in (({"EventID": 9999, "Computer": "x"}, "sysmon"), ({"Computer": "x"}, "sysmon"), ("not-an-object", "canonical"),
                         ({"timestamp": "2026-10-07T10:00:00", "action": "X", "event_source": "s", "hostname": "h"}, "canonical")):
            self.assertEqual(pipeline.process(raw, fmt, "LAB")["status"], "quarantined")
        self.assertEqual(store.read("SELECT COUNT(*) FROM quarantine")[0][0], 4)
        self.assertEqual(store.read("SELECT COUNT(*) FROM events")[0][0], 0)
        self.assertEqual(pipeline.process(sysmon(), "unknown_format", "LAB")["status"], "quarantined")
        self.assertEqual(pipeline.process(sysmon(), "sysmon", "PRODUCTION")["status"], "quarantined")

    def test_duplicate_event_is_idempotent_and_modes_are_separate(self):
        first = pipeline.process(sysmon(), "sysmon", "LAB")
        self.assertEqual(pipeline.process(sysmon(), "sysmon", "LAB"), {"status": "duplicate", "event_id": first["event_id"]})
        self.assertEqual(pipeline.process(sysmon(), "sysmon", "REPLAY")["status"], "accepted")
        self.assertEqual(store.read("SELECT mode, COUNT(*) FROM events GROUP BY mode ORDER BY mode"), [("LAB", 1), ("REPLAY", 1)])

    def test_timestamp_handling(self):
        event = normalize({"timestamp": "2026-10-07T15:30:00+05:30", "action": "LOGIN", "event_source": "test", "hostname": "H"},
                          "canonical", "LAB", "2026-10-07T10:00:01.000000+00:00")
        self.assertEqual(event["timestamp_utc"], "2026-10-07T10:00:00.000000+00:00")
        with self.assertRaises(ValueError):  # naive timestamp without a documented-UTC source
            normalize({"timestamp": "2026-10-07T10:00:00", "action": "X", "event_source": "s", "hostname": "h"}, "canonical", "LAB", "2026-10-07T10:00:00+00:00")
        skewed = normalize(sysmon(utc="2026-10-07 12:00:00.000"), "sysmon", "LAB", "2026-10-07T10:00:00.000000+00:00")
        self.assertIn("future_skew", skewed["quality_flags"])
        pipeline.process(sysmon(utc="2026-10-07 10:05:00.000"), "sysmon", "REPLAY")
        late = pipeline.process(sysmon(utc="2026-10-07 10:01:00.000"), "sysmon", "REPLAY")
        self.assertIn("out_of_order", store.record("events", "event_id", late["event_id"])["quality_flags"])

    def test_security_and_wazuh_adapters(self):
        security = {"EventID": 4688, "Computer": "DC1", "TimeCreated": "2026-10-07T10:00:00Z",
                    "EventData": {"NewProcessId": "0x1a4", "ProcessId": "0x10", "NewProcessName": r"C:\x\a.exe", "SubjectUserName": "bob"}}
        event = normalize(security, "windows_security", "LAB", "2026-10-07T10:00:01+00:00")
        self.assertEqual((event["process_id"], event["parent_process_id"], event["user"]), (0x1a4, 0x10, "bob"))
        alert = {"id": "1696", "agent": {"id": "007", "name": "lab"}, "data": {"win": {
            "system": {"providerName": "Microsoft-Windows-Sysmon", "eventID": "3", "computer": "LAB-WIN-01", "systemTime": "2026-10-07T10:00:00.1Z"},
            "eventdata": {"image": r"C:\a\b.exe", "destinationIp": "198.51.100.7", "destinationPort": "8443", "utcTime": "2026-10-07 10:00:00.100"}}}}
        event = normalize(alert, "wazuh", "LAB", "2026-10-07T10:00:01+00:00")
        self.assertEqual((event["destination_ip"], event["destination_port"], event["event_category"]), ("198.51.100.7", 8443, "network"))
        self.assertTrue(event["sensor"].startswith("wazuh-agent:007"))

    def test_ndjson_preserves_exact_bytes(self):
        line = json.dumps(sysmon(), separators=(", ", ": ")).encode()
        response = TestClient(app).post("/api/defense/events/ndjson?mode=REPLAY&source_format=sysmon&synchronous=true", content=line + b"\n{bad json\n")
        self.assertEqual(response.status_code, 200)
        statuses = [r["status"] for r in response.json()["results"]]
        self.assertEqual(statuses, ["accepted", "quarantined"])
        event = store.record("events", "event_id", response.json()["results"][0]["event_id"])
        self.assertEqual((event["raw_event_hash"], event["raw_hash_basis"]), (sha(line), "exact_received_bytes"))

    # ---------------- evidence ----------------
    def test_evidence_hash_provenance_and_immutability(self):
        result = pipeline.process(sysmon(), "sysmon", "LAB")
        check = evidence.verify(result["evidence_id"])
        self.assertTrue(check["verified"])
        body = store.record("evidence", "evidence_id", result["evidence_id"])
        self.assertEqual((body["event_id"], body["provenance"], body["schema_version"]), (result["event_id"], "LAB:sysmon", "canonical-event-v1"))
        connection = sqlite3.connect(store.DB)
        try:
            for statement in ("UPDATE evidence SET record='x'", "DELETE FROM evidence", "UPDATE events SET raw=x'00'", "DELETE FROM audit_log"):
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)
        finally:
            connection.close()

    # ---------------- prediction ----------------
    def test_no_qualified_model_abstains_and_never_contains(self):
        result = pipeline.process(sysmon(Image=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", CommandLine="powershell -enc AAA"), "sysmon", "LAB")
        prediction = store.record("predictions", "prediction_id", result["prediction"]["prediction_id"])
        self.assertEqual(prediction["status"], "ABSTAINED")
        self.assertIn("Insufficient observed", prediction["abstain_reason"])
        self.assertIsNone(prediction["predicted_technique_id"])
        self.assertEqual(result["response_ids"], [])
        event = store.record("events", "event_id", result["event_id"])
        self.assertEqual(event["candidate_techniques"][0]["assertion"], "OBSERVED_CANDIDATE")
        self.assertIsNone(event["technique_id"])

    def test_inference_uses_only_prefix_events(self):
        pipeline.process(sysmon(utc="2026-10-07 10:10:00.000"), "sysmon", "REPLAY")  # later event already stored
        earlier = pipeline.process(sysmon(utc="2026-10-07 10:00:00.000", CommandLine="other"), "sysmon", "REPLAY")
        prediction = store.record("predictions", "prediction_id", earlier["prediction"]["prediction_id"])
        self.assertEqual(prediction["supporting_event_ids"], [earlier["event_id"]])
        self.assertEqual(prediction["cutoff_timestamp"], "2026-10-07T10:00:00.000000+00:00")
        # LIVE/LAB: an event whose collection_time is after the cutoff is invisible.
        event = store.record("events", "event_id", earlier["event_id"])
        cutoff, visible = inference.window({**event, "mode": "REPLAY", "collection_time": "2026-10-07T10:00:00.000000+00:00"}, online=True)
        self.assertEqual(visible, [])

    def test_abstention_and_confidence(self):
        with available(probability=0.4):
            low = pipeline.process(network("2026-10-07 10:00:00.000"), "sysmon", "LAB")
        self.assertEqual(low["prediction"]["status"], "ABSTAINED")
        with available(probability=0.9, uncertainty=0.9):
            uncertain = pipeline.process(network("2026-10-07 10:00:01.000"), "sysmon", "LAB")
        self.assertIn("Uncertainty", store.record("predictions", "prediction_id", uncertain["prediction"]["prediction_id"])["abstain_reason"])
        with available(probability=0.9):
            high = pipeline.process(network("2026-10-07 10:00:02.000"), "sysmon", "LAB")
        prediction = store.record("predictions", "prediction_id", high["prediction"]["prediction_id"])
        self.assertEqual((prediction["status"], prediction["predicted_technique_id"]), ("PREDICTED", "T1071.001"))
        self.assertEqual(prediction["calibration_status"], "NOT MEASURED")
        self.assertEqual(len(prediction["top_k"]), 2)

    def test_inference_throttle(self):
        self.rewrite(lambda s: s["inference"].update(min_interval_seconds=60))
        first = pipeline.process(sysmon(utc="2026-10-07 10:00:00.000"), "sysmon", "REPLAY")
        second = pipeline.process(sysmon(utc="2026-10-07 10:00:30.000", CommandLine="b"), "sysmon", "REPLAY")
        third = pipeline.process(sysmon(utc="2026-10-07 10:01:30.000", CommandLine="c"), "sysmon", "REPLAY")
        self.assertIsNotNone(first["prediction"]); self.assertIsNone(second["prediction"]); self.assertIsNotNone(third["prediction"])

    # ---------------- risk ----------------
    def test_risk_formula_levels_and_evidence_weighting(self):
        prediction = {"prediction_id": "P", "host_id": "h", "mode": "LAB", "status": "PREDICTED", "predicted_technique_id": "T1041",
                      "probability": 0.8, "uncertainty": 0.25, "supporting_evidence_ids": []}
        clean = risk.assess(prediction, [{"quality_flags": []}])
        expected = 0.8 * 0.75 * 1.0 * 1.0 * 0.5  # exfiltration impact 1.0, default criticality 0.5
        self.assertAlmostEqual(clean["risk_score"], expected)
        self.assertEqual(clean["risk_level"], "MEDIUM")
        weak = risk.assess(prediction, [{"quality_flags": ["future_skew", "missing_user"]}])
        self.assertAlmostEqual(weak["risk_factors"]["evidence_strength"], 0.65)
        self.assertLess(weak["risk_score"], clean["risk_score"])
        self.assertEqual([risk.level(v) for v in (0.1, 0.25, 0.5, 0.75)], ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        abstained = risk.assess({**prediction, "status": "ABSTAINED"}, [{"quality_flags": [], "candidate_techniques": [{"technique_id": "T1059.001"}]}])
        self.assertEqual(abstained["risk_factors"]["predictive_component"], 0.0)
        self.assertAlmostEqual(abstained["risk_score"], 0.5 * 1.0 * 0.6 * 0.5)
        self.assertEqual(abstained["risk_factors"]["dominant_component"], "observed_candidate")

    # ---------------- policy ----------------
    def decision(self, technique="T1071.001", probability=0.9, level="HIGH", status="PREDICTED", trigger=None, strength=1.0):
        prediction = {"prediction_id": "P", "status": status, "probability": probability, "predicted_technique_id": technique}
        risk_record = {"risk_id": "R", "risk_level": level, "mode": "LAB", "host_id": "h", "risk_factors": {"evidence_strength": strength}}
        return policy.decide(risk_record, prediction, trigger or {"destination_ip": "203.0.113.50"})

    def test_policy_allowed_denied_and_approval(self):
        allowed = self.decision()
        self.assertEqual([c["action_type"] for c in allowed["containment_candidates"]], ["BLOCK_DESTINATION_IP"])
        self.assertTrue(allowed["containment_candidates"][0]["approval_required"])
        self.assertEqual(allowed["containment_candidates"][0]["justification"], ["M1031", "M1037"])
        self.assertEqual(self.decision(trigger={"destination_ip": "127.0.0.1"})["containment_candidates"], [])
        self.assertEqual(self.decision(level="MEDIUM")["containment_candidates"], [])
        self.assertIn("ANALYST_REVIEW", self.decision(status="ABSTAINED")["internal_actions"])
        self.assertEqual(self.decision(probability=0.6)["containment_candidates"], [])
        self.assertEqual(self.decision(strength=0.5)["containment_candidates"], [])
        protected = self.decision("T1204.002", trigger={"process_id": 700, "process_name": "lsass.exe"})
        self.assertEqual(protected["containment_candidates"], [])
        self.assertIn("protected", protected["refused_candidates"][0]["reason"])
        self.rewrite(lambda s: s["policy"].update(auto_execute_critical=True))
        critical = self.decision("T1204.002", level="CRITICAL", trigger={"process_id": 700, "process_name": "evil.exe"})
        self.assertTrue(critical["containment_candidates"][0]["approval_required"])  # irreversible: never automatic
        automatic = self.decision(level="CRITICAL")
        self.assertFalse(automatic["containment_candidates"][0]["approval_required"])

    def test_executor_allowlist_and_validation(self):
        self.assertEqual(executor.validate("RUN_SHELL", {})[1], "Action 'RUN_SHELL' is not allowlisted")
        self.assertIn("Invalid", executor.validate("BLOCK_DESTINATION_IP", {"destination_ip": "1.2.3.4; del *"})[1])
        self.assertIn("protected", executor.validate("DISABLE_LOCAL_ACCOUNT", {"user": "Administrator"})[1])
        self.assertIsNotNone(executor.validate("DISABLE_LOCAL_ACCOUNT", {"user": "bob & net user x"})[1])
        command, undo = executor.plan("BLOCK_DESTINATION_IP", {"destination_ip": "203.0.113.50"}, "RESP-1")
        self.assertEqual(command[-1], "remoteip=203.0.113.50")
        self.assertIn("delete", undo)
        self.assertIsNone(executor.plan("TERMINATE_PROCESS", {"process_id": 9, "process_name": "x.exe"}, "R")[1])

    # ---------------- prevention + verification ----------------
    def contained(self, utc="2026-10-07 10:00:00.000"):
        self.rewrite(lambda s: s["risk"].update(default_asset_criticality=1.0))
        with available(probability=0.95, uncertainty=0.05):
            result = pipeline.process(network(utc), "sysmon", "REPLAY")
        self.assertEqual(len(result["response_ids"]), 1, result)
        return result

    def test_response_lifecycle_duplicates_and_rollback(self):
        result = self.contained()
        response_id = result["response_ids"][0]
        self.assertEqual(responses.get(response_id)["state"], "PENDING_APPROVAL")
        with self.assertRaises(ValueError):
            responses.execute(response_id, "analyst-1")  # not approved
        with self.assertRaises(ValueError):
            responses.approve(response_id, " ", "ok")
        responses.approve(response_id, "analyst-1", "Confirmed outbound beacon")
        executed = responses.execute(response_id, "analyst-1")
        self.assertEqual(executed["state"], "EXECUTED_DRY_RUN")
        self.assertFalse(executed["transitions"][-1]["host_action_executed"])
        self.assertEqual(executed["transitions"][1]["approved_by"], "analyst-1")
        with self.assertRaises(ValueError):
            responses.execute(response_id, "analyst-1")  # no double execution
        with available(probability=0.95, uncertainty=0.05):
            repeat = pipeline.process(network("2026-10-07 10:00:05.000", SourcePort="50001"), "sysmon", "REPLAY")
        self.assertEqual(repeat["response_ids"], [])
        decision = store.record("policy_decisions", "decision_id", repeat["decision"]["decision_id"])
        self.assertEqual(decision["suppressed_duplicates"][0]["duplicate_of"], response_id)
        self.assertEqual(responses.rollback(response_id, "analyst-1")["state"], "ROLLED_BACK_DRY_RUN")

    def test_verification_outcomes(self):
        classify = verification.classify
        self.assertEqual(classify(False, 10, 0, 0.9, 0.1, 0.5)[0], "UNKNOWN")
        self.assertEqual(classify(True, 0, 0, 0.9, None, 0.5)[0], "UNKNOWN")
        self.assertEqual(classify(True, 5, 2, 0.9, 0.9, 0.5)[0], "FAILED")
        self.assertEqual(classify(True, 5, 0, 0.9, 0.24, 0.5)[0], "SUCCESS")
        self.assertEqual(classify(True, 5, 0, 0.9, 0.8, 0.5)[0], "PARTIAL_SUCCESS")
        result = self.contained()
        response_id = result["response_ids"][0]
        with self.assertRaises(ValueError):
            verification.verify(response_id, "analyst-1")
        responses.approve(response_id, "analyst-1", "ok")
        responses.execute(response_id, "analyst-1")
        with available(probability=0.95, uncertainty=0.05):
            pipeline.process(network("2026-10-07 10:03:00.000", SourcePort="50002"), "sysmon", "REPLAY")
        abstained = verification.verify(response_id, "analyst-1")  # reassessment without a model abstains -> LOW
        self.assertEqual((abstained["risk_after"]["level"], abstained["escalate"]), ("LOW", False))
        with available(probability=0.95, uncertainty=0.05):
            checked = verification.verify(response_id, "analyst-1")
        self.assertEqual(checked["outcome"], "UNKNOWN")
        self.assertIn("Dry run", checked["reason"])
        self.assertEqual(len(checked["indicator_event_ids"]), 1)
        self.assertEqual(checked["risk_after"]["level"], "HIGH")
        self.assertTrue(checked["escalate"])
        self.assertEqual(verification.latest(response_id)["verification_id"], checked["verification_id"])

    # ---------------- API + integration ----------------
    def test_response_api_requires_token_and_analyst(self):
        response_id = self.contained()["response_ids"][0]
        client = TestClient(app)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FAPT_RESPONSE_TOKEN", None)
            self.assertEqual(client.post(f"/api/defense/responses/{response_id}/approve", json={"comment": "x"}).status_code, 503)
        with patch.dict(os.environ, {"FAPT_RESPONSE_TOKEN": "s3cret"}):
            self.assertEqual(client.post(f"/api/defense/responses/{response_id}/approve", json={"comment": "x"},
                                         headers={"Authorization": "Bearer wrong", "X-Analyst-Id": "a"}).status_code, 401)
            self.assertEqual(client.post(f"/api/defense/responses/{response_id}/approve", json={"comment": "x"},
                                         headers={"Authorization": "Bearer s3cret"}).status_code, 400)
            ok = client.post(f"/api/defense/responses/{response_id}/approve", json={"comment": "x"},
                             headers={"Authorization": "Bearer s3cret", "X-Analyst-Id": "analyst-7"})
            self.assertEqual((ok.status_code, ok.json()["state"]), (200, "APPROVED"))
            self.assertEqual(client.post(f"/api/defense/responses/{response_id}/approve", json={"comment": "x"},
                                         headers={"Authorization": "Bearer s3cret", "X-Analyst-Id": "analyst-7"}).status_code, 409)

    def test_end_to_end_chain_is_queryable_and_audited(self):
        result = self.contained()
        response_id = result["response_ids"][0]
        client = TestClient(app)
        with patch.dict(os.environ, {"FAPT_RESPONSE_TOKEN": "t"}):
            headers = {"Authorization": "Bearer t", "X-Analyst-Id": "analyst-9"}
            client.post(f"/api/defense/responses/{response_id}/approve", json={"comment": "approved"}, headers=headers)
            client.post(f"/api/defense/responses/{response_id}/execute", headers=headers)
            verified = client.post(f"/api/defense/responses/{response_id}/verify", headers=headers).json()
        incident = client.get(f"/api/defense/incidents/{result['incident_id']}?expand=true").json()
        chain = incident["chain"]
        self.assertEqual(chain["response"], [response_id])
        self.assertEqual(chain["verification"], [verified["verification_id"]])
        self.assertIn(result["evidence_id"], chain["evidence"])
        self.assertIn(result["prediction"]["prediction_id"], chain["prediction"])
        self.assertEqual(incident["records"]["decision"][0]["response_ids"], [response_id])
        detail = client.get(f"/api/defense/evidence/{result['evidence_id']}").json()
        self.assertEqual({r["relation"] for r in detail["relations"]}, {"supports_prediction", "supports_risk", "supports_incident", "supports_response"})
        self.assertEqual(detail["incident_ids"], [result["incident_id"]])
        self.assertTrue(client.get("/api/defense/audit/verify").json()["verified"])
        self.assertEqual(client.get(f"/api/defense/responses/{response_id}/verification").json()["outcome"], "UNKNOWN")
        metrics = client.get("/api/defense/metrics?mode=REPLAY").json()
        self.assertEqual((metrics["events"], metrics["prediction_accuracy"]), (1, None))
        self.assertEqual(client.get("/api/defense/metrics?mode=LIVE").json()["events"], 0)
        self.assertEqual(client.get("/api/defense/health").json()["counters"]["accepted"], 1)

    def test_async_worker_survives_malformed_events(self):
        with patch.object(pipeline, "WORKER", pipeline.Worker()):
            client = TestClient(app)
            body = {"mode": "LAB", "source_format": "sysmon", "events": [{"EventID": "x"}, sysmon()]}
            queued = client.post("/api/defense/events", json=body).json()
            self.assertEqual(queued["queued"], 2)
            pipeline.WORKER.queue.join()
            self.assertTrue(pipeline.WORKER.thread.is_alive())
            health = client.get("/api/defense/health").json()
        self.assertEqual((health["counters"]["quarantined"], health["counters"]["accepted"]), (1, 1))
        self.assertEqual(health["failed_ingestion_rate"], 0.5)

    def test_queue_backpressure_and_rate_limit(self):
        self.rewrite(lambda s: s["ingestion"].update(queue_capacity=1))
        worker = pipeline.Worker()
        with patch.object(worker, "ensure", lambda: setattr(worker, "queue", worker.queue or __import__("queue").Queue(maxsize=1))):
            self.assertTrue(worker.submit(sysmon(), "sysmon", "LAB"))
            self.assertFalse(worker.submit(sysmon(), "sysmon", "LAB"))
        self.assertEqual(pipeline.HEALTH.counters["rejected_backpressure"], 1)
        self.rewrite(lambda s: s["ingestion"].update(rate_limit_burst=1, rate_limit_events_per_second=0))
        from app.api import defense as api
        api.BUCKET.tokens = None
        client = TestClient(app)
        body = {"mode": "LAB", "source_format": "sysmon", "events": [sysmon(), sysmon(utc="2026-10-07 10:00:01.000")], "synchronous": True}
        self.assertEqual(client.post("/api/defense/events", json=body).status_code, 429)
        api.BUCKET.tokens = None


if __name__ == "__main__":
    unittest.main()
