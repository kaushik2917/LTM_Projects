import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.datasets import DATA, CONTEXT, AF_FEATURES, TRUST_FEATURES
from app.services import optc_service as optc
from app.services import research_service as research


class ImportTests(unittest.TestCase):
    def test_raw_integrity_duplicates_conflicts_and_timezone(self):
        event = {"id": "event1", "timestamp": 1569232800000, "hostname": "host1",
                 "actorID": "parent", "objectID": "child", "object": "PROCESS", "action": "CREATE"}
        original = json.dumps(event).encode() + b"\n"
        changed = json.dumps(dict(event, action="OPEN")).encode() + b"\n"
        with tempfile.TemporaryDirectory() as temp:
            source, db = Path(temp) / "fixture.json.gz", Path(temp) / "test.db"
            with gzip.open(source, "wb") as f:
                f.write(original + original + changed + b"invalid\n")
            result = optc.import_optc(source, db_path=db)
            self.assertEqual((result["imported"], result["duplicates"], result["rejected"]), (2, 1, 1))
            events = optc.events(db_path=db)
            self.assertEqual(len(events), 2)
            self.assertIn(hashlib.sha256(original).hexdigest(), {e["integrity_hash"] for e in events})
            self.assertTrue(all(e["timestamp"].endswith("+00:00") for e in events))
            self.assertTrue(all(e["attack_mappings"] == [] for e in events))

    def test_limit_and_no_silent_missing_time(self):
        with self.assertRaises(ValueError):
            optc.normalize({"hostname": "h", "actorID": "a", "objectID": "o", "object": "FILE", "action": "WRITE"}, "d", "ref")
        with self.assertRaises(ValueError):
            optc.import_optc("unused", 0)

    def test_parallel_events_preserved_in_graph(self):
        events = [{"evidence_id": str(i), "host": "h", "subject": "p", "object": "f",
                   "subject_type": "process", "object_type": "file", "timestamp": str(i),
                   "action": "WRITE", "attack_mappings": []} for i in range(2)]
        with patch.object(optc, "events", return_value=events):
            graph = optc.graph("test")
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(len(graph["edges"]), 2)


class ResearchTests(unittest.TestCase):
    def test_no_target_or_benchmark_features(self):
        self.assertNotIn("optimal_action", CONTEXT)
        self.assertNotIn("anti_forensic_probability", AF_FEATURES)
        self.assertNotIn("predicted_next_stage", AF_FEATURES)
        self.assertNotIn("poisoning_label", TRUST_FEATURES)
        report = json.loads((DATA / "models" / "training_report.json").read_text())
        self.assertFalse(report["benchmark_13_used_for_training"])
        for model in report["models"].values():
            self.assertEqual(model["group_overlap"], 0)
            self.assertNotEqual(model["dataset"], "13")

    def test_response_math_and_api_validation(self):
        client = TestClient(app)
        examples = client.get("/api/research/examples").json()
        response = client.post("/api/research/responses", json=examples["responses"])
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(len(result["candidates"]), 11)
        total = sum(result["forensic_utility"].values())
        for candidate in result["candidates"]:
            self.assertAlmostEqual(candidate["evidence_retention_score"], 1 - candidate["evidence_loss_cost"] / total)
        invalid = dict(examples["responses"], evidence_trust=2)
        self.assertEqual(client.post("/api/research/responses", json=invalid).status_code, 422)
        for mode in ("trust", "anti-forensic"):
            self.assertEqual(client.post("/api/research/" + mode, json=examples[mode]).status_code, 200)
        self.assertEqual(client.get("/api/research/datasets").status_code, 200)

    def test_benchmark_does_not_call_models(self):
        with patch.object(research, "model", side_effect=AssertionError("Benchmark must not fit/load models with incompatible columns")):
            report = research.evaluate_benchmark()
        self.assertEqual(report["rows"], 1890)
        self.assertIsNone(report["measured_model_metrics"])


if __name__ == "__main__":
    unittest.main()
