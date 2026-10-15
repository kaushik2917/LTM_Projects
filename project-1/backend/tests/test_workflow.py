import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.services import workflow_service as workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(workflow, "DB", Path(self.temp.name) / "audit.sqlite3")
        self.patch.start()
        self.client = TestClient(app)
        self.base = "/api/workflow/INC-00001"

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_graph_preserve_report(self):
        graph = self.client.get(self.base + "/graph").json()
        self.assertEqual(len(graph["edges"]), 6)
        snapshot = self.client.post(self.base + "/preserve").json()
        self.assertEqual(hashlib.sha256(snapshot["snapshot_json"].encode()).hexdigest(), snapshot["sha256"])
        self.assertEqual(snapshot["evidence_count"], 6)
        report = self.client.get(self.base + "/report").json()
        self.assertTrue(report["audit"][0]["snapshot_integrity_valid"])
        self.assertEqual(self.client.get("/api/workflow/unknown/report").status_code, 404)

    def test_assessment_and_simulation_are_linked_and_persistent(self):
        context = self.client.get("/api/research/examples").json()["responses"]
        response = self.client.post(self.base + "/assessment", json={"context": context, "previous_stage": "Execution", "graph_integrity": .8})
        self.assertEqual(response.status_code, 200)
        assessment = response.json()
        self.assertFalse(assessment["safety_certificate"]["certified_safe"])
        self.assertEqual(self.client.post(self.base + "/simulate", json={"assessment_id": "missing", "action": "OBSERVE"}).status_code, 404)
        self.assertEqual(self.client.post(self.base + "/simulate", json={"assessment_id": assessment["id"], "action": "INVALID"}).status_code, 422)
        simulation = self.client.post(self.base + "/simulate", json={"assessment_id": assessment["id"], "action": "NETWORK_ISOLATE"})
        self.assertEqual(simulation.status_code, 200)
        self.assertFalse(simulation.json()["host_action_executed"])
        report = self.client.get(self.base + "/report").json()
        self.assertEqual({r["kind"] for r in report["audit"]}, {"assessment", "preservation", "simulation"})
        preserved = next(r for r in report["audit"] if r["kind"] == "preservation")
        self.assertEqual(simulation.json()["preservation_id"], preserved["id"])
        result = simulation.json()
        self.assertEqual(result["preservation"]["snapshot_id"], preserved["snapshot_id"])
        self.assertEqual(result["preservation"]["sha256"], hashlib.sha256(preserved["snapshot_json"].encode("utf-8")).hexdigest())
        self.assertEqual(result["preservation"]["evidence_count"], len(json.loads(preserved["snapshot_json"])["evidence"]))
        self.assertEqual(result["snapshot_verification"], "VERIFIED")
        self.assertIsNone(result["observed_post_response_survival"])
        self.assertTrue(all(e["observed_post_response_survival"] is None for e in result["evidence_at_risk"]))
        self.assertTrue(report["chain_of_custody"]["verified"])
        self.assertEqual(next(r for r in report["audit"] if r["kind"] == "simulation"), result)

    def test_failed_snapshot_readback_verification_prevents_simulation(self):
        context = self.client.get("/api/research/examples").json()["responses"]
        assessment = workflow.assessment("INC-00001", context, "Execution", .8)
        original_history = workflow.history

        def corrupted_readback(incident_id):
            entries = original_history(incident_id)
            for entry in entries:
                if entry["kind"] == "preservation":
                    entry["snapshot_json"] += "tampered"
            return entries

        with patch.object(workflow, "history", side_effect=corrupted_readback):
            response = self.client.post(self.base + "/simulate", json={"assessment_id": assessment["id"], "action": "NETWORK_ISOLATE"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Preservation verification failed")
        self.assertFalse(any(e["kind"] == "simulation" for e in original_history("INC-00001")))

    def test_every_response_is_only_a_stored_simulation(self):
        context = self.client.get("/api/research/examples").json()["responses"]
        assessment = workflow.assessment("INC-00001", context, "Execution", .8)
        for candidate in assessment["response_analysis"]["candidates"]:
            with self.subTest(action=candidate["action"]):
                result = workflow.simulate("INC-00001", assessment["id"], candidate["action"])
                self.assertTrue(result["simulated"])
                self.assertFalse(result["host_action_executed"])
                self.assertEqual(result["predicted_outcome"], candidate)
                self.assertIsNone(result["observed_post_response_survival"])
        self.assertTrue(workflow.verify_chain("INC-00001")["verified"])


if __name__ == "__main__":
    unittest.main()
