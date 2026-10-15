import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.datasets import DATA
from app.services import workflow_service as workflow
from app.services import analysis_service as analysis
from app.services.evidence_service import get_simulated_evidence
from app.services.research_service import responses


class ValidityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(workflow, "DB", Path(self.temp.name) / "audit.db")
        self.db_patch.start()
        self.client = TestClient(app)
        self.events = [e.model_dump(mode="json") for e in get_simulated_evidence()]

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_prediction_is_temporal_and_contributors_are_actual_inputs(self):
        early = workflow.analysis("INC-00001", 4)
        full = workflow.analysis("INC-00001")
        self.assertEqual(early["current_stage"], "Execution")
        self.assertEqual(early["prediction"]["status"], "not_available")
        p = full["prediction"]
        self.assertEqual(p["status"], "available")
        self.assertEqual(set(p["supporting_evidence_ids"]), {"EV-00004", "EV-00006"})
        self.assertAlmostEqual(sum(c["probability"] for c in p["predictions"]), 1)
        self.assertTrue(0 <= p["uncertainty"] <= 1)
        self.assertTrue(all(c["predicted_technique"] is None for c in p["predictions"]))
        self.assertEqual(p["prediction_id"], workflow.analysis("INC-00001")["prediction"]["prediction_id"])

    def test_quality_reacts_to_tampering_without_inventing_sensor_measurements(self):
        clean = analysis.analyze_evidence(self.events)
        self.assertIsNone(clean[-1]["cross_sensor_consistency"])
        self.assertIsNone(clean[-1]["poisoning_probability"])
        self.assertEqual(clean[0]["mapping"]["mapping_status"], "UNMAPPED")
        self.assertEqual(clean[3]["mapping"]["mapping_status"], "CONFIRMED")
        self.assertEqual(clean[5]["mapping"]["mapping_status"], "CANDIDATE")
        self.events[-1]["object"] = "tampered"
        corrupted = analysis.analyze_evidence(self.events)
        self.assertLess(corrupted[-1]["evidence_trust"], clean[-1]["evidence_trust"])
        self.assertGreater(corrupted[-1]["poisoning_risk"], clean[-1]["poisoning_risk"])

    def test_chain_detects_modified_record_and_exports_are_audited(self):
        preserved = workflow.preserve("INC-00001")
        workflow.verification("INC-00001")
        report = workflow.export_report("INC-00001")
        self.assertTrue(report["chain_of_custody"]["verified"])
        self.assertEqual(report["audit"][0]["kind"], "report_generation")
        self.assertIn("research_provenance", report)
        with workflow.connect() as conn:
            payload = json.loads(conn.execute("SELECT payload FROM audit WHERE id=?", (preserved["id"],)).fetchone()[0])
            payload["sha256"] = "0" * 64
            conn.execute("UPDATE audit SET payload=? WHERE id=?", (json.dumps(payload), preserved["id"]))
        conn.close()
        self.assertFalse(workflow.verify_chain("INC-00001")["verified"])

    def test_import_boundary_and_missing_data_state(self):
        self.assertEqual(self.client.post("/api/research/dataset/import", json={"filename": "../../README.md"}).status_code, 422)
        self.assertEqual(self.client.post("/api/research/dataset/import", json={"filename": "missing.json.gz"}).status_code, 404)
        metadata = self.client.get("/api/research/datasets").json()
        self.assertEqual({d["id"] for d in metadata["datasets"]}, {"10", "11", "12", "13", "FAPT-GUARD-SYN-TEMPORAL-001", "synthetic_temporal_v2"})
        self.assertTrue(all(d["file_hash"] and d["dataset_name"] for d in metadata["datasets"]))

    def test_benchmark_measures_execution_and_marks_unlabeled_metrics(self):
        from app.services.benchmark_service import run_benchmark
        with patch("app.services.benchmark_service.DATA", Path(self.temp.name)):
            # Hash provenance still reads the real evaluation CSV via patched hash helper.
            with patch("app.services.benchmark_service.sha256", return_value=hashlib.sha256(b"test-provenance").hexdigest()):
                result = run_benchmark()
        scenarios = {s["scenario_name"]: s for s in result["scenarios"]}
        self.assertEqual(scenarios["missing_50"]["actual_missing_ratio"], .5)
        self.assertGreater(scenarios["fake_events_25"]["detected_anomaly_records"], 0)
        self.assertIsNone(scenarios["baseline_complete"]["prediction_accuracy"])
        self.assertEqual(scenarios["unseen_technique"]["status"], "not_measured")
        self.assertIsNone(result["coverage"])

    def test_objective_is_sum_of_exposed_terms(self):
        context = self.client.get("/api/research/examples").json()["responses"]
        result = responses(context)
        for c in result["candidates"]:
            self.assertAlmostEqual(c["objective_score"], sum(c["objective_contributions"].values()))
            self.assertLessEqual(c["evidence_loss_cost"], result["elc_maximum"])
        self.assertEqual(result["recommended_action"], min(result["candidates"], key=lambda c: c["objective_score"])["action"])


if __name__ == "__main__":
    unittest.main()
