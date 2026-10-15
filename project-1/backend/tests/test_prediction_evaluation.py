"""Independent checks of frozen-model evaluation and distribution-based entropy."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import prediction_evaluation as evaluation
from app import synthetic_temporal as synthetic
from app.attack_normalization import normalize
from app.datasets import sha256
from app.temporal_prediction import entropy, evaluate
from app.services.future_prediction_service import predict
from app.services import workflow_service as workflow


class PredictionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.legacy = patch("app.temporal_experiment.POINTER", Path("__legacy_test_no_v2_pointer__"))
        self.legacy.start()
        self.addCleanup(self.legacy.stop)

    @classmethod
    def setUpClass(cls):
        cls.model, cls.metadata, reason = synthetic.qualified_model()
        if reason: raise AssertionError(reason)

    def test_entropy_complete_class_space_and_edge_cases(self):
        self.assertAlmostEqual(entropy([1 / 16] * 16), 1)
        self.assertEqual(entropy([1.] + [0.] * 15), 0)
        self.assertEqual(entropy([1.]), 0)
        probabilities = [.9281045751633987, .0718954248366013] + [0.] * 14
        expected = -sum(p * math.log(p) for p in probabilities if p) / math.log(16)
        self.assertAlmostEqual(entropy(probabilities), expected, places=14)
        self.assertNotAlmostEqual(entropy(probabilities), entropy(probabilities[:3]))
        for invalid in ([.3, .3], [float("nan"), 1.], [-.1, 1.1], []):
            with self.assertRaises(ValueError): entropy(invalid)

    def test_calibration_metrics_against_hand_calculation(self):
        metrics = evaluate(["A", "A"], [[.8, .2], [.4, .6]], ["A", "B"])
        self.assertAlmostEqual(metrics["expected_calibration_error"], .4)
        self.assertAlmostEqual(metrics["multiclass_brier_score"], .4)
        self.assertEqual(evaluate(["C"], [[1., 0.]], ["A", "B"])["multiclass_brier_score"], 2.)

    def test_run_freezes_model_and_reconstructs_actual_test_outputs(self):
        original_hash = sha256(synthetic.MODEL)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(evaluation, "DATA", root), patch.object(evaluation, "POINTER", root / "latest.json"):
                summary = evaluation.run_evaluation()
                run = json.loads(Path(summary["path"]).read_text(encoding="utf-8"))
                self.assertEqual(run["model_version"], original_hash)
                self.assertFalse(run["model_retrained"])
                self.assertEqual(run["sample_count"], 360)
                self.assertEqual(run["splits"]["scenario_counts"], {"train": 480, "validation": 60, "test": 60})
                self.assertEqual(run["splits"]["unique_sequence_counts"], {"train": 38, "validation": 4, "test": 6})
                actual = [p["true_technique"] for p in run["predictions"]]
                probabilities = [[p["probability_distribution"][c] for c in self.model.classes_] for p in run["predictions"]]
                self.assertEqual(run["metrics"], evaluate(actual, probabilities, list(self.model.classes_)))
                self.assertEqual(sum(map(sum, run["metrics"]["confusion_matrix"])), 360)
                self.assertEqual(run["calibration"]["calibration_sample_count"], 360)
                self.assertEqual(run["calibration"]["calibration_partition"], "test")
                self.assertEqual(run["calibration"]["ECE"], run["metrics"]["expected_calibration_error"])
                self.assertIsNone(run["conformal"]["measured_coverage"])
                self.assertFalse(run["conformal"]["experiment_executed"])
                self.assertIn("already used to select", run["conformal"]["reason"])
                self.assertEqual(run["conformal"]["minimum_calibration_groups_at_target"], 9)
                self.assertIsNone(evaluation.current_evaluation(self.metadata)[1])
                stale = {**self.metadata, "model_version": "changed"}
                self.assertIn("stale", evaluation.current_evaluation(stale)[1])
                Path(summary["path"]).write_text("{}", encoding="utf-8")
                self.assertIn("SHA-256 mismatch", evaluation.current_evaluation(self.metadata)[1])
        self.assertEqual(sha256(synthetic.MODEL), original_hash)

    def test_duplicate_full_sequences_are_rejected_even_with_distinct_ids(self):
        _, groups, _ = normalize(*synthetic.load_dataset())
        checks = evaluation.split_checks(groups)
        self.assertTrue(all(not v for pair in checks["overlap"].values() for v in pair.values()))
        changed = deepcopy(groups)
        train = next(g for g in changed.values() if g[0]["split"] == "train")
        test = next(s for s,g in changed.items() if g[0]["split"] == "test")
        changed[test] = [{**e, "scenario_id": test, "incident_id": "DISTINCT", "event_id": f"NEW-{i}", "split": "test"} for i,e in enumerate(train)]
        with self.assertRaisesRegex(ValueError, "duplicated full sequence"): evaluation.split_checks(changed)

    def test_incident_record_is_reproducible_without_ground_truth(self):
        events = workflow.snapshot("INC-00001")["evidence"]
        cutoff = "2026-09-25T10:05:02"
        with tempfile.TemporaryDirectory() as directory, patch.object(workflow, "DB", Path(directory) / "audit.db"):
            first = workflow.run_prediction("INC-00001", cutoff)
            again = workflow.run_prediction("INC-00001", cutoff)
            self.assertEqual(first["prediction_id"], again["prediction_id"])
            self.assertEqual(first["probability_distribution"], again["probability_distribution"])
            self.assertEqual(len(first["probability_distribution"]), len(self.model.classes_))
            self.assertAlmostEqual(first["uncertainty_value"], entropy(list(first["probability_distribution"].values())))
            self.assertIsNone(first["observed_future_outcome"])
            self.assertIsNone(first["prediction_correctness"])
            self.assertEqual(first["supporting_evidence_ids"], [e["evidence_id"] for e in events])
            self.assertTrue(all(e["timestamp"] <= cutoff and e["incident_id"] == "INC-00001" for e in events))
            stored = workflow.history("INC-00001")[0]["result"]
            for key in ("prediction_id", "incident_id", "cutoff_timestamp", "current_technique", "predicted_technique", "probability", "uncertainty", "uncertainty_method", "supporting_evidence_ids", "model_name", "model_version", "training_dataset", "training_dataset_version", "probability_distribution", "evaluation_id"):
                self.assertEqual(stored[key], first[key])
            self.assertTrue(workflow.verify_chain("INC-00001")["verified"])
        changed = deepcopy(events); changed[0]["incident_id"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "different incident"): predict(changed, "INC-00001", cutoff)
        changed = deepcopy(events); changed[0]["evidence_id"] = "INVALID"
        with self.assertRaisesRegex(ValueError, "inventory"): predict(changed, "INC-00001", cutoff)


if __name__ == "__main__":
    unittest.main()
