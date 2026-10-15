"""Synthetic benchmark plumbing and leakage checks; no operational accuracy claims."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from app import prediction_benchmark as benchmark
from app.main import app


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads(benchmark.SOURCE.read_text())
        cls.manifest, cls.parts = benchmark.build()
        cls.events = cls.bundle["scenarios"][0]["events"]
        cls.cutoff = cls.parts["train"][0]["cutoff_timestamp"]

    def test_sorting_cutoff_and_future_fields(self):
        expected = benchmark.features(benchmark.safe_prefix(self.events, self.cutoff))
        altered = deepcopy(self.events)
        for event in altered:
            event.update(next_technique_id="FUTURE SECRET", target="FUTURE", host="IGNORED", user="IGNORED", object="IGNORED")
            if benchmark.stamp(event["timestamp"]) > benchmark.stamp(self.cutoff):
                event.update(technique_id="INVALID FUTURE", action="FUTURE", source="FUTURE")
        self.assertEqual(expected, benchmark.features(benchmark.safe_prefix(list(reversed(altered)), self.cutoff)))
        self.assertEqual(expected["event_count"], sum(benchmark.stamp(e["timestamp"]) <= benchmark.stamp(self.cutoff) for e in self.events))
        self.assertNotIn("target", expected)
        self.assertNotIn("host", expected)
        self.assertIn("last_tactics", expected)

    def test_invalid_and_unavailable_inputs(self):
        for changes in ({"timestamp": "invalid"}, {"label_known_at": "2099-01-01T00:00:00Z"},
                        {"source": None}, {"action": None}, {"simulated": False}, {"label_status": "CANDIDATE"}):
            with self.subTest(changes=changes):
                events = deepcopy(self.events)
                events[0].update(changes)
                with self.assertRaises((ValueError, KeyError)):
                    benchmark.safe_prefix(events, self.cutoff)
        with self.assertRaisesRegex(ValueError, "two labelled"):
            benchmark.safe_prefix(self.events[:1], self.cutoff)
        with self.assertRaisesRegex(ValueError, "outside supported"):
            benchmark.safe_prefix(self.events, self.cutoff, {"UNSUPPORTED"})

    def test_temporal_groups_and_exact_paths_disjoint(self):
        self.assertEqual([len(self.parts[key]) for key in ("train", "validation", "test")], [700, 150, 150])
        group_sets = [set(x["scenario_id"] for x in self.parts[key]) for key in self.parts]
        self.assertFalse(group_sets[0] & group_sets[1] or group_sets[0] & group_sets[2] or group_sets[1] & group_sets[2])
        paths = [tuple(e["technique_id"] for e in group["events"]) for group in self.bundle["scenarios"]]
        self.assertEqual(len(paths), len(set(paths)))
        for left, right in (("train", "validation"), ("validation", "test")):
            self.assertLess(max(benchmark.stamp(x["end"]) for x in self.parts[left]), min(benchmark.stamp(x["start"]) for x in self.parts[right]))
        for part in self.parts.values():
            for row in part:
                self.assertLess(benchmark.stamp(row["cutoff_timestamp"]), benchmark.stamp(row["target_timestamp"]))
        self.assertEqual(self.manifest["source_sha256"], benchmark.sha256(benchmark.SOURCE))

    def test_rejects_invalid_rows_and_duplicate_paths(self):
        bundle = deepcopy(self.bundle)
        bundle["scenarios"][0]["events"][0]["timestamp"] = "bad timestamp"
        bundle["scenarios"].append(deepcopy(bundle["scenarios"][1]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(bundle))
            manifest, _ = benchmark.build(path)
        self.assertEqual(len(manifest["rejected_sequences"]), 2)
        self.assertGreater(manifest["rejected_rows"], 0)

    def test_probabilities_uncertainty_gate_and_metrics(self):
        thresholds = {"abstain_below_probability": .5, "abstain_above_uncertainty": .6}
        labels = ["A", "B", "C"]
        confident = benchmark.gate([.9, .08, .02], labels, thresholds)
        self.assertEqual(confident["status"], "PREDICTED")
        self.assertEqual(confident["predicted_technique_id"], "A")
        self.assertEqual([p["rank"] for p in confident["top_k"]], [1, 2, 3])
        uncertain = benchmark.gate([.4, .3, .3], labels, thresholds)
        self.assertEqual(uncertain["status"], "ABSTAINED")
        self.assertIsNone(uncertain["probability"])
        self.assertIsNone(uncertain["predicted_technique_id"])
        for bad in ([float("nan"), .1, .2], [.9, .2, .1], [-.1, .6, .5], [.5, .5]):
            with self.assertRaises(ValueError):
                benchmark.gate(bad, labels, thresholds)
        values = benchmark.metrics(["A", "B", "C"], [[.9, .08, .02], [.1, .8, .1], [.4, .3, .3]], labels, thresholds)
        self.assertAlmostEqual(values["top_1_accuracy"], 2/3)
        self.assertEqual(values["top_3_accuracy"], 1.)
        self.assertAlmostEqual(values["macro_precision"], .5)
        self.assertAlmostEqual(values["macro_recall"], 2/3)
        self.assertAlmostEqual(values["macro_f1"], 5/9)
        self.assertAlmostEqual(values["coverage"], 2/3)
        self.assertEqual(values["selective_accuracy"], 1.)
        self.assertTrue(0 <= values["expected_calibration_error"] <= 1)

    def test_temperature_scaling_preserves_ranking(self):
        original = np.array([[.8, .15, .05], [.2, .7, .1]])
        result = benchmark.temperature_scale(original, 2.)
        np.testing.assert_allclose(result.sum(axis=1), 1)
        np.testing.assert_array_equal(result.argmax(axis=1), original.argmax(axis=1))
        self.assertTrue(np.isfinite(result).all())
        self.assertGreater(benchmark.entropy(result[0]), benchmark.entropy(original[0]))

    def test_missing_artifact_abstains(self):
        with tempfile.TemporaryDirectory() as directory:
            result = benchmark.predict(self.events, self.cutoff, Path(directory))
        self.assertEqual(result["status"], "ABSTAINED")
        self.assertIsNone(result["probability"])
        self.assertTrue(result["abstain_reason"])


class TrainedBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.output = Path(cls.temp.name)
        cls.report = benchmark.train(output=cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_training_metadata_and_class_balance(self):
        frozen = self.report["frozen_config"]
        self.assertEqual(frozen["selection_sequences"], 100)
        self.assertEqual(frozen["calibration_sequences"], 50)
        self.assertEqual(len(self.report["model_hash"]), 64)
        self.assertEqual(self.report["feature_version"], "future_prediction_v2")
        for kind in ("forest", "boosting"):
            self.assertEqual({trial["parameters"]["class_weight"] for trial in frozen["tuning"]["hyperparameter_trials"] if trial["model"] == kind}, {None, "balanced"})
        self.assertAlmostEqual(sum(frozen["tuning"]["selected_weights"].values()), 1.)
        self.assertEqual(set(self.report["results"]), {"Most frequent", "Markov", "Random Forest", "Gradient Boosting", "Sequence model", "FAPT-Guard"})

    def test_real_prediction_matches_saved_test_probabilities(self):
        bundle = json.loads(benchmark.SOURCE.read_text())
        samples = json.loads((self.output / "samples.json").read_text())["test"]
        stored = json.loads((self.output / "test_predictions.json").read_text())[0]
        scenario = next(s for s in bundle["scenarios"] if s["scenario_id"] == samples[0]["scenario_id"])
        result = benchmark.predict(scenario["events"], samples[0]["cutoff_timestamp"], self.output)
        expected = benchmark.gate(stored["probabilities"]["FAPT-Guard"], self.report["supported_classes"], self.report["thresholds"])
        self.assertEqual(result["status"], expected["status"])
        self.assertAlmostEqual(result["uncertainty"], expected["uncertainty"])
        self.assertEqual(result["top_k"], expected["top_k"])
        self.assertTrue(result["prediction_id"].startswith("RESEARCH-"))
        self.assertEqual(result["execution_mode"], "DRY_RUN")

    def test_hash_verification_and_api(self):
        loaded = benchmark.report(self.output)
        with patch.object(benchmark, "report", return_value=loaded):
            response = TestClient(app).get("/api/research/prediction-benchmark")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], self.report["results"])
        model = self.output / "model.joblib"
        original = model.read_bytes()
        try:
            model.write_bytes(original + b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                benchmark.report(self.output)
            with patch.object(benchmark, "report", side_effect=ValueError("hash mismatch")):
                response = TestClient(app).get("/api/research/prediction-benchmark")
            self.assertEqual(response.status_code, 503)
            self.assertIn("hash mismatch", response.text)
        finally:
            model.write_bytes(original)
