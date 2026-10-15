"""Synthetic fixtures test plumbing only; these are never research validation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import temporal_prediction as temporal
from app.services import workflow_service as workflow
from app.services import future_prediction_service as future
from app.services.evidence_service import get_simulated_evidence


def synthetic_bundle():
    events = []
    for group in range(15):
        for index in range(9):
            time = (datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=group, seconds=index * (group + 1))).isoformat()
            events.append({"evidence_id": f"TEST-{group}-{index}", "incident_id": f"TEST-{group}",
                "scenario_id": f"SCENARIO-{group}", "collection_id": f"COLLECTION-{group}",
                "timestamp": time, "observed_at": (datetime.fromisoformat(time) + timedelta(milliseconds=group + 1)).isoformat(), "label_known_at": time, "source": "test_sensor",
                "host": f"test-host-{group}", "subject": "test-process", "object": f"test-object-{index}",
                "action": "TEST_OBSERVATION", "simulated": True,
                "technique_id": "T1059.001" if index % 2 else "T1003.001",
                "attack_stage": "Execution" if index % 2 else "Credential Access",
                "label_basis": "independent_ground_truth", "label_reference": "TEST ONLY synthetic fixture; not real ground truth"})
    return {"metadata": {"dataset_name": "TEST ONLY synthetic temporal fixture", "version": "test-v1",
            "source": "unit test generator", "domain": "test-only", "ground_truth_reference": "TEST ONLY",
            "data_kind": "synthetic"}, "events": events}


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.legacy = patch("app.temporal_experiment.POINTER", Path("__legacy_test_no_v2_pointer__"))
        self.legacy.start()
        self.addCleanup(self.legacy.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(workflow, "DB", self.root / "workflow.db")
        self.db_patch.start()
        self.client = TestClient(app)
        self.events = [e.model_dump(mode="json") for e in get_simulated_evidence()]

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def write_bundle(self, bundle):
        path = self.root / "events.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        return path

    def test_cutoff_uses_timestamps_not_input_order_and_filters_future(self):
        cutoff = self.events[3]["timestamp"]
        selected, _ = temporal.prefix(list(reversed(self.events)), cutoff)
        self.assertEqual([e["evidence_id"] for e in selected], [f"EV-{i:05}" for i in range(1, 5)])
        original = temporal.feature_values(self.events, cutoff)
        changed = deepcopy(self.events)
        for e in changed[4:]:
            e.update(subject="FUTURE SECRET", action="LEAKED", attack_technique_id="T1021.002")
        self.assertEqual(original, temporal.feature_values(changed, cutoff))
        before, _ = temporal.prefix(self.events, "2026-09-25T00:00:00")
        self.assertEqual(before, [])
        with self.assertRaises(ValueError): temporal.prefix(self.events, "bad")
        with self.assertRaises(ValueError): temporal.prefix(self.events, cutoff + "Z")
        with self.assertRaises(ValueError): temporal.prefix(self.events, cutoff, 3)

    @patch("app.synthetic_temporal.qualified_model", return_value=(None, None, "Synthetic temporal model unavailable in test"))
    def test_api_unavailable_is_audited_without_fake_probabilities(self, _model):
        cutoff = self.events[3]["timestamp"]
        response = self.client.post("/api/workflow/INC-00001/prediction", json={"cutoff_timestamp": cutoff})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "not_available")
        self.assertEqual(result["predictions"], [])
        self.assertIsNone(result["uncertainty"])
        self.assertNotIn("EV-00005", result["supporting_evidence_ids"])
        self.assertEqual(result["current_technique"], "T1059.001")
        self.assertEqual(self.client.post("/api/workflow/INC-00001/prediction", json={"cutoff_timestamp": cutoff}).json()["prediction_id"], result["prediction_id"])
        stored = workflow.history("INC-00001")[0]
        self.assertEqual(stored["id"], result["prediction_id"])
        self.assertEqual(stored["kind"], "future_prediction")
        self.assertEqual(self.client.post("/api/workflow/INC-00001/prediction", json={"cutoff_timestamp": "invalid"}).status_code, 422)
        self.assertEqual(self.client.post("/api/workflow/missing/prediction", json={"cutoff_timestamp": cutoff}).status_code, 404)
        report = self.client.get("/api/workflow/INC-00001/report").json()
        self.assertEqual(report["future_attack_prediction"]["status"], "not_available")
        self.assertTrue(report["chain_of_custody"]["verified"])

    def test_graph_and_both_modes_share_cutoff(self):
        result = workflow.analysis("INC-00001", cutoff_timestamp=self.events[3]["timestamp"])
        self.assertEqual(len(result["graph"]["edges"]), 4)
        self.assertEqual(len(result["evidence"]), 4)
        self.assertEqual(result["synthetic_prediction"]["prediction_mode"], "synthetic_next_stage")
        self.assertEqual(result["future_prediction"]["features"]["event_count"], 4)
        before = workflow.analysis("INC-00001", cutoff_timestamp="2026-09-25T00:00:00")
        self.assertEqual(before["future_prediction"]["supporting_evidence_ids"], [])

    def test_target_and_late_annotation_never_enter_features(self):
        bundle = synthetic_bundle()
        event = bundle["events"][1]
        event["label_known_at"] = "2026-01-01T00:00:00Z"
        meta, events = temporal.load_sequences(self.write_bundle(bundle))
        samples = temporal.samples(events, "technique")
        for sample in samples:
            self.assertNotIn(sample["target_event_id"], sample["supporting_evidence_ids"])
            self.assertGreater(temporal.stamp(sample["target_timestamp"]), temporal.stamp(sample["cutoff_timestamp"]))
        features = temporal.feature_values(events[:2], event["observed_at"])
        self.assertNotIn("count:technique:T1059.001", features)
        delayed = deepcopy(events[:2])
        delayed[1]["observed_at"] = "2026-01-01T00:00:00Z"
        self.assertEqual(temporal.feature_values(delayed, event["observed_at"])["event_count"], 1)

    def test_schema_rejects_duplicates_invalid_labels_and_leakage(self):
        for mutate in (
            lambda b: b["events"].append(b["events"][0]),
            lambda b: b["events"][0].update(technique_id="T9999"),
            lambda b: b["events"][0].update(timestamp=""),
            lambda b: b["events"][0].update(label_basis="behavior_rule"),
            lambda b: b["events"][0].update(predicted_next_stage="Impact"),
            lambda b: b["events"][0].update(simulated=False),
        ):
            bundle = synthetic_bundle(); mutate(bundle)
            with self.assertRaises(ValueError): temporal.load_sequences(self.write_bundle(bundle))
        events = synthetic_bundle()["events"]
        for e in events: e["scenario_id"] = "same-scenario"
        with self.assertRaises(ValueError): temporal.split_samples(temporal.samples(events, "technique"))

    def test_synthetic_pipeline_train_evaluate_and_refuse_genuine_activation(self):
        import joblib
        path = self.write_bundle(synthetic_bundle())
        with self.assertRaises(ValueError): temporal.train(path, self.root / "models")
        report = temporal.train(path, self.root / "models", allow_synthetic=True)
        self.assertEqual(report["prediction_mode"], "synthetic_temporal_test")
        self.assertTrue(report["leakage_checks"]["all_checks_passed"])
        self.assertEqual(sum(report["split_sizes"].values()), 120)
        self.assertIsNone(report["evaluation"]["holdout"]["model"]["top_3_accuracy"])
        self.assertIn("majority_baseline", report["evaluation"]["holdout"])
        with patch.object(future, "DATA", self.root):
            model, metadata, reason = future.qualified_model()
            self.assertIsNone(model)
            self.assertIn("Synthetic", reason)
        # Exercise the inference branch with an explicitly mocked qualification gate.
        # This temporary synthetic test is not deployment or real-data validation.
        model = joblib.load(self.root / "models/future_technique.joblib")["model"]
        heldout = report["partition_groups"]["holdout"]["incident_id"][0]
        events = deepcopy([e for e in synthetic_bundle()["events"] if e["incident_id"] == heldout])
        for event in events: event["simulated"] = False
        cutoff = events[3]["observed_at"]
        with patch.object(future, "qualified_model", return_value=(model, report, None)):
            result = future.predict(events, "TEST-0", cutoff, domain="test-only")
            self.assertEqual(result["status"], "available")
            self.assertAlmostEqual(sum(p["probability"] for p in result["predictions"]), 1)
            self.assertEqual(result["supporting_evidence_ids"], [e["evidence_id"] for e in events[:4]])
            self.assertTrue(all(p["predicted_technique"] in ("T1003.001", "T1059.001") for p in result["predictions"]))
            changed = deepcopy(events)
            changed[-1].update(subject="future changed", technique_id="T1021.002")
            self.assertEqual(result["predictions"], future.predict(changed, "TEST-0", cutoff, domain="test-only")["predictions"])
            self.assertEqual(future.predict(events, "TEST-0", cutoff, domain="wrong")["status"], "not_available")
            leaked = deepcopy(events)
            for e in leaked: e["scenario_id"] = report["partition_groups"]["training"]["scenario_id"][0]
            self.assertIn("used for model fitting", future.predict(leaked, "TEST-0", cutoff, domain="test-only")["reason"])
        sidecar = self.root / "models/future_technique.json"
        changed_meta = json.loads(sidecar.read_text()); changed_meta["model_version"] = "0" * 64
        sidecar.write_text(json.dumps(changed_meta))
        with patch.object(future, "DATA", self.root):
            self.assertIn("SHA-256 mismatch", future.qualified_model()[2])
        stage = temporal.train(path, self.root / "models", task="stage", allow_synthetic=True)
        self.assertEqual(stage["target"], "next_observed_stage")

    def test_duplicate_sample_patterns_and_simultaneous_targets_are_rejected(self):
        events = synthetic_bundle()["events"]
        for event in events: event["observed_at"] = event["timestamp"]
        with self.assertRaisesRegex(ValueError, "Duplicate feature/target"):
            temporal.split_samples(temporal.samples(events, "technique"))
        events = synthetic_bundle()["events"][:9]
        events[2]["timestamp"] = events[1]["timestamp"]
        with self.assertRaisesRegex(ValueError, "Ambiguous simultaneous"):
            temporal.samples(events, "technique")

    def test_probability_validation(self):
        self.assertAlmostEqual(temporal.entropy([.5, .5]), 1)
        self.assertEqual(temporal.entropy([1., 0.]), 0)
        for values in ([.2, .2], [float("nan"), .5], [-.1, 1.1]):
            with self.assertRaises(ValueError): temporal.entropy(values)


if __name__ == "__main__":
    unittest.main()
